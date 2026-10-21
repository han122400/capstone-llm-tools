"""Local Ollama integration for the Sentinel report workspace."""

import asyncio
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, ValidationInfo, field_validator, model_validator
from starlette.background import BackgroundTask

from backend.thinking import ThinkingSplitter
from backend.settings import (
    SettingsConflict, SettingsError, SettingsStore, model_matches,
    validate_model_name, validate_ollama_url,
)

OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
FOUNDATION_MODEL = "hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q4_K_M-GGUF:Q4_K_M"
MODELFILE = Path(__file__).resolve().parent.parent / "Modelfile"
settings_store = SettingsStore(MODELFILE, MODELFILE.parent / ".ollama-settings.json", OLLAMA_URL)
initial_settings = settings_store.load()
OLLAMA_MODEL = initial_settings.model
SYSTEM_PROMPT = initial_settings.system_prompt
generation_lock = asyncio.Lock()

FindingClass = Literal["CONFIRMED", "SUSPECTED", "ATTACK_SURFACE", "INFORMATIONAL"]
ReportClass = Literal["CONFIRMED", "SUSPECTED", "ATTACK_SURFACE", "INFORMATIONAL", "NO_EVIDENCE"]


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: str | None
    endpoint: str | None
    classification: FindingClass
    vulnerability_type: str | None
    CWE: str | None
    OWASP: str | None
    evidence: list[str] = Field(min_length=1)
    confidence: float | None = Field(ge=0, le=1)
    reason_validation_is_needed: str | None

    @model_validator(mode="after")
    def check_evidence_and_category(self):
        if any(not excerpt.strip() for excerpt in self.evidence):
            raise ValueError("근거에는 비어 있지 않은 입력 인용이 필요합니다.")
        if self.classification in {"ATTACK_SURFACE", "INFORMATIONAL"}:
            if any(value is not None for value in (self.vulnerability_type, self.CWE, self.OWASP)):
                raise ValueError("공격 표면과 정보성 항목에는 취약점 분류를 지정할 수 없습니다.")
        return self


class ModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    classification: ReportClass
    findings: list[Finding]

    @model_validator(mode="after")
    def check_aggregation(self, info: ValidationInfo):
        if self.classification == "NO_EVIDENCE":
            if self.findings:
                raise ValueError("NO_EVIDENCE에는 분석 항목이 없어야 합니다.")
        else:
            if not self.findings:
                raise ValueError("판정에는 최소 한 개의 분석 항목이 필요합니다.")
            rank = {"CONFIRMED": 4, "SUSPECTED": 3, "ATTACK_SURFACE": 2, "INFORMATIONAL": 1}
            highest = max((f.classification for f in self.findings), key=rank.__getitem__)
            if self.classification != highest:
                if info.context and info.context.get("derive_summary"):
                    self.classification = highest
                else:
                    raise ValueError("최종 판정과 분석 항목의 판정이 일치하지 않습니다.")
        return self


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=100)
    input_data: str = Field(min_length=1, max_length=20000)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("제목을 입력해주세요.")
        return value.strip()

    @field_validator("input_data")
    @classmethod
    def validate_input_data(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("입력 데이터를 넣어주세요.")
        return value


class SaveOllamaSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ollama_url: str = Field(min_length=1, max_length=2048)
    modelfile: str = Field(min_length=1, max_length=100000)
    keep_alive: Literal["0", "1m", "5m", "15m", "1h"]
    revision: str = Field(pattern=r"^[a-f0-9]{64}$")


class CheckOllama(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ollama_url: str = Field(min_length=1, max_length=2048)
    model: str = Field(min_length=1, max_length=200)


app = FastAPI(
    title="Sentinel API",
    description="로컬 Ollama를 이용한 근거 기반 웹 취약점 보고서 생성 API",
    version="0.4.0",
)


def load_settings():
    try:
        return settings_store.load()
    except (OSError, ValueError, TypeError, KeyError) as error:
        raise HTTPException(503, f"저장된 Ollama 설정을 읽을 수 없습니다. Modelfile과 설정 파일을 확인해주세요. ({error})") from error


def explicit_case_count(user_input: str):
    markers = list(re.finditer(r"(?im)^[ \t]*\[(CASE-\d+)\][ \t]*\r?$", user_input))
    cases = set()
    for index, marker in enumerate(markers):
        end = markers[index + 1].start() if index + 1 < len(markers) else len(user_input)
        section = user_input[marker.end():end]
        # A case label alone is not target evidence and must not force findings.
        if re.search(r"(?im)^[ \t]*(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS|CONNECT|TRACE)[ \t]+\S+[ \t]+HTTP/\d", section):
            cases.add(marker.group(1).upper())
    return len(cases)


def report_format(user_input: str):
    schema = ModelOutput.model_json_schema()
    # The grammar must allow only verbatim source lines/paragraphs as evidence.
    # Preserve whitespace, line endings and quotes rather than repairing citations.
    excerpts = list(dict.fromkeys(
        part for part in [*user_input.splitlines(), *re.split(r"\r?\n[ \t]*\r?\n|\r[ \t]*\r", user_input)]
        if part.strip()
    ))
    schema["$defs"]["Finding"]["properties"]["evidence"]["items"]["enum"] = excerpts
    count = explicit_case_count(user_input)
    if count > 1:
        schema["properties"]["findings"]["minItems"] = count
    return schema


def output_validation_error(error: ValidationError):
    issues = error.errors(include_input=False, include_context=False, include_url=False)
    if any(issue["type"] == "json_invalid" for issue in issues):
        return {"code": "invalid_json", "message": "모델이 하나의 완전한 보고서 JSON 객체를 반환하지 않았습니다. 다시 생성해주세요."}
    fields = list(dict.fromkeys(".".join(map(str, issue["loc"])) or "최종 판정" for issue in issues))
    return {"code": "invalid_report", "message": f"모델 보고서의 필드 검증에 실패했습니다. 확인할 항목: {', '.join(fields[:3])}. 다시 생성해주세요."}


def chat_payload(request: GenerateRequest, *, stream: bool, settings=None):
    settings = settings or load_settings()
    payload = {
        "model": settings.model,
        "messages": [
            {"role": "system", "content": settings.system_prompt},
            {"role": "user", "content": request.input_data},
        ],
        "stream": stream,
        "think": stream,
        "options": settings.options,
        "keep_alive": settings.keep_alive,
        "format": report_format(request.input_data),
    }
    # Ollama emits native thinking separately; constrain the final answer while
    # keeping that live trace. A prompt alone cannot enforce one JSON report.
    return payload


async def prepare_chat_payload(client, request, settings, *, stream):
    payload = chat_payload(request, stream=stream, settings=settings)
    if stream and settings.model != FOUNDATION_MODEL:
        # General models may reject think=true. Discover capabilities without
        # loading a model or introducing any messages from previous reports.
        try:
            info = await client.post(f"{settings.ollama_url}/api/show", json={"model": settings.model}, timeout=5)
            info.raise_for_status()
            capabilities = info.json().get("capabilities")
            if isinstance(capabilities, list):
                payload["think"] = "thinking" in capabilities
            else:
                payload.pop("think", None)
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            payload.pop("think", None)
    return payload


def validate_output(content: str, user_input: str):
    output = ModelOutput.model_validate_json(content, context={"derive_summary": True})
    if any(excerpt not in user_input for finding in output.findings for excerpt in finding.evidence):
        raise HTTPException(502, "모델이 입력에 없는 근거를 반환했습니다. 요청·응답 근거를 명확히 입력한 뒤 다시 시도해주세요.")
    count = explicit_case_count(user_input)
    if count > 1 and len(output.findings) < count:
        raise HTTPException(502, f"모델이 입력의 {count}개 사례 중 일부만 분석했습니다. 반환된 항목은 {len(output.findings)}개입니다. 다시 생성해주세요.")
    return output


def build_report(request: GenerateRequest, output: ModelOutput, start: float, settings=None):
    settings = settings or load_settings()
    targets = list(dict.fromkeys(finding.target for finding in output.findings if finding.target))
    return {
        "id": f"RPT-{uuid4().hex[:12].upper()}",
        "title": request.title, "target": ", ".join(targets) or None,
        "input_data": request.input_data, "status": "완료",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "model": settings.model, "duration_seconds": round(time.monotonic() - start, 2),
        **output.model_dump(),
    }


def stream_event(name: str, data: dict):
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.get("/api/health", tags=["System"])
async def health():
    settings = load_settings()
    result = {
        "status": "ok", "mode": "ollama", "model": settings.model,
        "ollama_url": settings.ollama_url, "ollama_available": False,
        "model_connected": False, "generating": generation_lock.locked(),
    }
    try:
        async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
            response = await client.get(f"{settings.ollama_url}/api/tags")
            response.raise_for_status()
            models = response.json().get("models", [])
            result["ollama_available"] = True
            result["model_connected"] = any(isinstance(m, dict) and isinstance(m.get("name"), str) and model_matches(m["name"], settings.model) for m in models)
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        pass
    return result


@app.get("/api/settings/ollama", tags=["Settings"])
async def get_ollama_settings():
    return load_settings().public()


@app.put("/api/settings/ollama", tags=["Settings"])
async def save_ollama_settings(request: SaveOllamaSettings):
    if generation_lock.locked():
        raise HTTPException(409, "보고서 생성 중에는 설정을 저장할 수 없습니다. 생성이 끝난 뒤 다시 저장해주세요.")
    async with generation_lock:
        try:
            return settings_store.save(**request.model_dump()).public()
        except SettingsConflict as error:
            raise HTTPException(409, str(error)) from error
        except SettingsError as error:
            raise HTTPException(422, str(error)) from error
        except (OSError, ValueError, TypeError, KeyError) as error:
            raise HTTPException(503, "설정을 저장하지 못했습니다. 파일 쓰기 권한과 저장된 설정을 확인해주세요.") from error


async def list_ollama_models(url: str):
    result = {"ollama_url": url, "ollama_available": False, "models": [], "message": "로컬 Ollama에 연결할 수 없습니다. 서버 주소와 실행 상태를 확인해주세요."}
    try:
        async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
            response = await client.get(f"{url}/api/tags")
            response.raise_for_status()
            models = response.json().get("models")
            if not isinstance(models, list) or any(not isinstance(m, dict) or not isinstance(m.get("name"), str) for m in models):
                raise ValueError("Invalid model list")
            result.update(ollama_available=True, models=models, message=f"설치된 모델 {len(models)}개를 확인했습니다.")
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        pass
    return result


@app.get("/api/ollama/models", tags=["Settings"])
async def ollama_models(ollama_url: str | None = None):
    try:
        url = validate_ollama_url(ollama_url if ollama_url is not None else load_settings().ollama_url)
    except SettingsError as error:
        raise HTTPException(422, str(error)) from error
    return await list_ollama_models(url)


@app.post("/api/ollama/check", tags=["Settings"])
async def check_ollama(request: CheckOllama):
    try:
        url = validate_ollama_url(request.ollama_url)
        model = validate_model_name(request.model)
    except SettingsError as error:
        raise HTTPException(422, str(error)) from error
    listed = await list_ollama_models(url)
    connected = any(model_matches(item["name"], model) for item in listed["models"])
    result = {"ollama_url": url, "model": model, "ollama_available": listed["ollama_available"], "model_connected": connected, "capabilities": [], "message": listed["message"]}
    if connected:
        result["message"] = "선택한 모델의 연결을 확인했습니다."
        try:
            async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
                response = await client.post(f"{url}/api/show", json={"model": model})
                response.raise_for_status()
                capabilities = response.json().get("capabilities", [])
                if isinstance(capabilities, list):
                    result["capabilities"] = [value for value in capabilities if isinstance(value, str)]
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            result["message"] = "모델 연결을 확인했지만 지원 기능 정보를 읽지 못했습니다."
    elif listed["ollama_available"]:
        result["message"] = "Ollama는 연결되었지만 선택한 모델이 설치되어 있지 않습니다."
    return result


@app.post("/api/reports/generate", tags=["Reports"])
async def generate_report(request: GenerateRequest):
    if generation_lock.locked():
        raise HTTPException(409, "다른 보고서를 분석 중입니다. 완료 후 다시 시도해주세요.")
    user_input = request.input_data
    settings = load_settings()
    start = time.monotonic()
    async with generation_lock:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=5), trust_env=False) as client:
                response = await client.post(f"{settings.ollama_url}/api/chat", json=chat_payload(request, stream=False, settings=settings))
                if response.status_code == 404:
                    raise HTTPException(503, "지정한 Ollama 모델을 찾을 수 없습니다. 설치된 모델을 확인해주세요.")
                response.raise_for_status()
                message = response.json().get("message", {})
                output = validate_output(message.get("content", ""), user_input)
        except httpx.TimeoutException as error:
            raise HTTPException(504, "모델 응답 시간이 초과되었습니다. 입력을 줄이거나 Ollama 실행 상태를 확인해주세요.") from error
        except httpx.ConnectError as error:
            raise HTTPException(503, "로컬 Ollama에 연결할 수 없습니다. Ollama를 실행해주세요.") from error
        except httpx.HTTPError as error:
            raise HTTPException(502, "Ollama 요청을 처리하지 못했습니다. 모델 실행 상태를 확인해주세요.") from error
        except ValidationError as error:
            raise HTTPException(502, output_validation_error(error)["message"]) from error
        except (ValueError, TypeError, AttributeError) as error:
            raise HTTPException(502, "Ollama의 보고서 응답을 해석하지 못했습니다. 모델 실행 상태를 확인해주세요.") from error
    return build_report(request, output, start, settings=settings)


@app.post("/api/reports/generate/stream", tags=["Reports"])
async def generate_report_stream(request: GenerateRequest):
    if generation_lock.locked():
        raise HTTPException(409, "다른 보고서를 분석 중입니다. 완료 후 다시 시도해주세요.")
    settings = load_settings()
    # Acquire before sending headers so a concurrent request receives HTTP 409.
    await generation_lock.acquire()
    owned_lock = generation_lock
    released = False

    def release_lock():
        nonlocal released
        if not released:
            released = True
            owned_lock.release()

    async def events():
        start = time.monotonic()
        thinking_parts = []
        content_parts = []
        splitter = ThinkingSplitter()
        native_thinking = False
        received_done = False
        response = None
        try:
            yield stream_event("status", {"stage": "connecting", "message": "로컬 Ollama에 분석을 요청하고 있습니다."})
            async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=5), trust_env=False) as client:
                payload = await prepare_chat_payload(client, request, settings, stream=True)
                upstream_request = client.build_request("POST", f"{settings.ollama_url}/api/chat", json=payload)
                response = await asyncio.wait_for(client.send(upstream_request, stream=True), timeout=max(0.001, 300 - (time.monotonic() - start)))
                if response.status_code == 404:
                    raise HTTPException(503, "지정한 Ollama 모델을 찾을 수 없습니다. 설치된 모델을 확인해주세요.")
                response.raise_for_status()
                yield stream_event("status", {"stage": "receiving", "message": "Ollama 응답을 기다리고 있습니다."})
                lines = response.aiter_lines().__aiter__()
                while True:
                    remaining = 300 - (time.monotonic() - start)
                    if remaining <= 0:
                        raise asyncio.TimeoutError
                    try:
                        line = await asyncio.wait_for(lines.__anext__(), timeout=remaining)
                    except StopAsyncIteration:
                        break
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    if not isinstance(chunk, dict):
                        raise ValueError("Invalid Ollama stream chunk")
                    if chunk.get("error"):
                        raise HTTPException(502, "Ollama가 분석 중 오류를 반환했습니다. 모델 실행 상태를 확인해주세요.")
                    message = chunk.get("message", {})
                    if not isinstance(message, dict):
                        raise ValueError("Invalid Ollama stream message")
                    thinking = message.get("thinking", "")
                    content = message.get("content", "")
                    if not isinstance(thinking, str) or not isinstance(content, str):
                        raise ValueError("Invalid Ollama stream text")
                    deltas = []
                    if thinking:
                        if not native_thinking:
                            deltas.extend(splitter.native_thinking())
                            native_thinking = True
                        deltas.append(("thinking", thinking))
                    deltas.extend(splitter.push(content))
                    for field, text in deltas:
                        if field == "thinking":
                            thinking_parts.append(text)
                        else:
                            if not content_parts:
                                yield stream_event("status", {"stage": "writing", "message": "Ollama가 보고서 응답을 작성하고 있습니다."})
                            content_parts.append(text)
                        yield stream_event(field, {"text": text})
                    if chunk.get("done") is True:
                        if chunk.get("done_reason") == "length":
                            raise HTTPException(502, "모델의 출력 한도에 도달했습니다. 입력 데이터를 줄여 다시 시도해주세요.")
                        received_done = True
                        break
                if not received_done:
                    raise HTTPException(502, "Ollama 응답이 완료되기 전에 연결이 종료되었습니다. 다시 시도해주세요.")
                splitter.finish()
                yield stream_event("status", {"stage": "validating", "message": "보고서 형식과 입력 근거를 확인하고 있습니다."})
                output = validate_output("".join(content_parts), request.input_data)
                report = build_report(request, output, start, settings=settings)
                report["thinking"] = "".join(thinking_parts)
                yield stream_event("result", {"report": report})
        except HTTPException as error:
            yield stream_event("error", {"message": error.detail})
        except (httpx.TimeoutException, asyncio.TimeoutError):
            yield stream_event("error", {"message": "모델 응답 시간이 초과되었습니다. 입력을 줄이거나 Ollama 실행 상태를 확인해주세요."})
        except httpx.ConnectError:
            yield stream_event("error", {"message": "로컬 Ollama에 연결할 수 없습니다. Ollama를 실행해주세요."})
        except httpx.HTTPError:
            yield stream_event("error", {"message": "Ollama 요청을 처리하지 못했습니다. 모델 실행 상태를 확인해주세요."})
        except ValidationError as error:
            yield stream_event("error", output_validation_error(error))
        except (ValueError, TypeError, AttributeError):
            yield stream_event("error", {"code": "invalid_stream", "message": "Ollama 스트리밍 응답을 해석하지 못했습니다. 다시 생성해주세요."})
        finally:
            try:
                if response is not None:
                    await response.aclose()
            finally:
                release_lock()

    return StreamingResponse(
        events(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        background=BackgroundTask(release_lock),
    )
