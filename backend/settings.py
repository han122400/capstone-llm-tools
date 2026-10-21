"""Validated, persistent application settings derived from the project Modelfile."""

import hashlib
import ipaddress
import json
import math
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


DEFAULT_OPTIONS = {"temperature": 0.1, "top_p": 0.95, "repeat_penalty": 1.0, "num_ctx": 16384, "num_predict": 4096}
KEEP_ALIVE_VALUES = {"0", "1m", "5m", "15m", "1h"}
# Bounds keep values representable by Ollama and catch common editing mistakes.
PARAMETERS = {
    "temperature": (float, 0, 2), "top_p": (float, 0, 1),
    "min_p": (float, 0, 1), "repeat_penalty": (float, 0, 10),
    "num_ctx": (int, 512, 131072), "num_predict": (int, 1, 32768),
    "top_k": (int, 0, 2000), "seed": (int, 0, 2147483647),
    "repeat_last_n": (int, -1, 131072), "stop": (str, None, None),
}


class SettingsError(ValueError):
    pass


class SettingsConflict(SettingsError):
    pass


def validate_ollama_url(value: str) -> str:
    try:
        parsed = urlsplit(value.strip())
        host = parsed.hostname
        port = parsed.port
        if parsed.scheme not in {"http", "https"} or not host:
            raise ValueError
        if parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment:
            raise ValueError
        if parsed.path not in {"", "/"} or (port is not None and not 1 <= port <= 65535):
            raise ValueError
        if host.lower() != "localhost" and not ipaddress.ip_address(host).is_loopback:
            raise ValueError
        host = host.lower()
        authority = f"[{host}]" if ":" in host else host
        if port is not None:
            authority += f":{port}"
        return f"{parsed.scheme}://{authority}"
    except (ValueError, AttributeError) as error:
        raise SettingsError("Ollama 주소는 http://127.0.0.1:11434처럼 로컬 주소와 포트로 입력해주세요.") from error


def validate_model_name(value: str) -> str:
    value = value.strip()
    if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/:+\-]{0,199}", value)
            or "://" in value or re.match(r"^[A-Za-z]:/", value)
            or any(part in {".", "..", ""} for part in value.split("/"))):
        raise SettingsError("FROM에는 설치된 Ollama 모델 이름을 입력해주세요. 파일 경로나 URL은 사용할 수 없습니다.")
    return value


def model_matches(installed: str, selected: str) -> bool:
    def normalized(name):
        return name if ":" in name.rsplit("/", 1)[-1] else name + ":latest"
    return normalized(installed) == normalized(selected)


def scalar_text(argument: str, line: int) -> str:
    argument = argument.strip()
    if argument.startswith('"'):
        try:
            value = json.loads(argument)
        except (ValueError, TypeError) as error:
            raise SettingsError(f"{line}행: 따옴표로 감싼 값의 형식이 올바르지 않습니다.") from error
        if not isinstance(value, str):
            raise SettingsError(f"{line}행: 문자열 값을 입력해주세요.")
        return value
    return argument


def parse_modelfile(text: str):
    if not text.strip() or len(text) > 100000 or "\x00" in text:
        raise SettingsError("Modelfile은 비어 있지 않은 100,000자 이하의 텍스트여야 합니다.")
    lines = text.splitlines(keepends=True)
    model = system = None
    options = DEFAULT_OPTIONS.copy()
    seen = set()
    index = 0
    while index < len(lines):
        line_number = index + 1
        stripped = lines[index].strip()
        index += 1
        if not stripped or stripped.startswith("#"):
            continue
        match = re.match(r"([A-Za-z]+)\s+(.*)", stripped)
        if not match:
            raise SettingsError(f"{line_number}행: FROM, SYSTEM 또는 PARAMETER 구문을 입력해주세요.")
        instruction, argument = match.group(1).upper(), match.group(2)
        if instruction == "FROM":
            if model is not None:
                raise SettingsError(f"{line_number}행: FROM은 한 번만 지정할 수 있습니다.")
            model = validate_model_name(scalar_text(argument, line_number))
        elif instruction == "SYSTEM":
            if system is not None:
                raise SettingsError(f"{line_number}행: SYSTEM은 한 번만 지정할 수 있습니다.")
            if argument.startswith('"""'):
                block = argument[3:]
                while '"""' not in block and index < len(lines):
                    block += "\n" if index == line_number else ""
                    block += lines[index]
                    index += 1
                if '"""' not in block:
                    raise SettingsError(f'{line_number}행: SYSTEM의 닫는 따옴표(""")가 없습니다.')
                system, trailing = block.split('"""', 1)
                if trailing.strip() and not trailing.lstrip().startswith("#"):
                    raise SettingsError(f"{line_number}행: SYSTEM 블록 뒤에는 다른 구문을 붙일 수 없습니다.")
            else:
                system = scalar_text(argument, line_number)
            system = system.strip()
            if not system:
                raise SettingsError(f"{line_number}행: SYSTEM 프롬프트를 입력해주세요.")
        elif instruction == "PARAMETER":
            parts = argument.split(None, 1)
            if len(parts) != 2 or parts[0].lower() not in PARAMETERS:
                raise SettingsError(f"{line_number}행: 지원하는 PARAMETER와 값을 입력해주세요. 지원: {', '.join(PARAMETERS)}")
            name, value = parts[0].lower(), scalar_text(parts[1], line_number)
            converter, minimum, maximum = PARAMETERS[name]
            if name in seen and name != "stop":
                raise SettingsError(f"{line_number}행: PARAMETER {name}이 중복되어 있습니다.")
            try:
                if converter is str:
                    if not value or len(value) > 500:
                        raise ValueError
                    options.setdefault("stop", []).append(value)
                else:
                    number = converter(value)
                    if (converter is float and not math.isfinite(number)) or not minimum <= number <= maximum:
                        raise ValueError
                    options[name] = number
            except ValueError as error:
                expected = "1~500자의 문자열" if converter is str else f"{minimum}~{maximum} 범위의 {'정수' if converter is int else '숫자'}"
                raise SettingsError(f"{line_number}행: {name}에는 {expected}를 입력해주세요.") from error
            seen.add(name)
        else:
            raise SettingsError(f"{line_number}행: 이 앱에서 지원하지 않는 구문입니다: {instruction}. FROM, SYSTEM, PARAMETER를 사용해주세요.")
    if model is None or system is None:
        raise SettingsError("Modelfile에는 FROM 모델 이름과 SYSTEM 프롬프트가 모두 필요합니다.")
    return model, system, options


@dataclass(frozen=True)
class OllamaSettings:
    ollama_url: str
    model: str
    system_prompt: str
    modelfile: str
    options: dict
    keep_alive: str
    revision: str

    def public(self):
        return {
            "ollama_url": self.ollama_url, "model": self.model,
            "modelfile": self.modelfile, "options": self.options.copy(),
            "keep_alive": self.keep_alive, "revision": self.revision,
            "supported_parameters": list(PARAMETERS), "generation_timeout_seconds": 300,
        }


class SettingsStore:
    def __init__(self, modelfile: Path, runtime_file: Path, default_url: str):
        self.modelfile = modelfile
        self.runtime_file = runtime_file
        self.default_url = default_url

    def load(self) -> OllamaSettings:
        raw = self.modelfile.read_bytes()
        text = raw.decode("utf-8-sig")
        runtime = {"ollama_url": self.default_url, "keep_alive": "5m"}
        if self.runtime_file.exists():
            saved = json.loads(self.runtime_file.read_text(encoding="utf-8"))
            if not isinstance(saved, dict):
                raise SettingsError("저장된 Ollama 설정 파일의 형식이 올바르지 않습니다.")
            runtime.update(saved)
        url = validate_ollama_url(runtime["ollama_url"])
        keep_alive = runtime["keep_alive"]
        if keep_alive not in KEEP_ALIVE_VALUES:
            raise SettingsError("모델 메모리 유지 시간 설정이 올바르지 않습니다.")
        model, system, options = parse_modelfile(text)
        identity = json.dumps({"ollama_url": url, "keep_alive": keep_alive}, sort_keys=True).encode()
        revision = hashlib.sha256(raw + b"\0" + identity).hexdigest()
        return OllamaSettings(url, model, system, text, options, keep_alive, revision)

    @staticmethod
    def replace_file(path: Path, content: bytes):
        # Stage in the same directory so os.replace stays on the same volume.
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(descriptor, "wb") as file:
                file.write(content)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def save(self, *, ollama_url: str, modelfile: str, keep_alive: str, revision: str):
        url = validate_ollama_url(ollama_url)
        parse_modelfile(modelfile)
        if keep_alive not in KEEP_ALIVE_VALUES:
            raise SettingsError("메모리 유지 시간은 0, 1m, 5m, 15m, 1h 중에서 선택해주세요.")
        current = self.load()
        if revision != current.revision:
            raise SettingsConflict("설정이 다른 화면이나 파일에서 변경되었습니다. 저장된 설정을 다시 불러온 뒤 수정해주세요.")
        previous_model = self.modelfile.read_bytes()
        previous_runtime = self.runtime_file.read_bytes() if self.runtime_file.exists() else None
        runtime = json.dumps({"ollama_url": url, "keep_alive": keep_alive}, ensure_ascii=False, indent=2).encode()
        model_replaced = False
        try:
            self.replace_file(self.modelfile, modelfile.encode("utf-8"))
            model_replaced = True
            self.replace_file(self.runtime_file, runtime)
        except OSError:
            if model_replaced:
                self.replace_file(self.modelfile, previous_model)
                if previous_runtime is not None:
                    self.replace_file(self.runtime_file, previous_runtime)
                elif self.runtime_file.exists():
                    self.runtime_file.unlink()
            raise
        return self.load()
