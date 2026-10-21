import asyncio
import json

import httpx
import pytest

from app.adapters import JevAdapter, OllamaAdapter, make_adapter
from app.core import common_input_limit, model_input
from app.settings import load_settings, public_settings
from app.telemetry import ResourceMonitor


def settings():
    return {"ollama_url": "http://localhost:11434", "foundation_sec_model": "foundation-sec:test", "qwen_model": "qwen3.5:9b", "jev_model": "typesafe/jev-1.13", "openrouter_api_key": "test-secret", "context_length": 4096, "temperature": 0, "seed": 42, "max_output_tokens": 64, "timeout_seconds": 1, "max_attempts": 3, "retry_delay_seconds": 0, "explanation": False}


def run(coro):
    return asyncio.run(coro)


def client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_public_settings_never_expose_key_and_load_from_environment(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret-value")
    loaded = load_settings()
    public = public_settings(loaded)
    assert loaded["openrouter_api_key"] == "secret-value"
    assert public["openrouter_key_configured"] is True
    assert "secret-value" not in json.dumps(public)


def test_environment_aliases_and_numeric_options_are_honored(monkeypatch):
    monkeypatch.setenv("OLLAMA_URL", "http://127.0.0.1:12345")
    monkeypatch.setenv("FOUNDATION_SEC_MODEL", "my-installed:Q4_K_M")
    monkeypatch.setenv("QWEN_MODEL", "qwen3.5:9b")
    monkeypatch.setenv("MAX_OUTPUT_TOKENS", "128")
    loaded = load_settings()
    assert loaded["ollama_url"] == "http://127.0.0.1:12345"
    assert loaded["foundation_sec_model"] == "my-installed:Q4_K_M"
    assert loaded["max_output_tokens"] == 128


def test_telemetry_only_reads_memory_for_model_processes(monkeypatch):
    class Unrelated:
        info = {"pid": 123, "name": "browser.exe"}
        def memory_info(self):
            raise AssertionError("unrelated memory must not be scanned")
    def processes(attrs):
        assert attrs == ["pid", "name"]
        return [Unrelated()]
    monkeypatch.setattr("app.telemetry.psutil.process_iter", processes)
    report = ResourceMonitor(interval_seconds=0.01).start().stop()
    assert report["backend_rss_peak_bytes"] > 0 and report["ollama_rss_peak_bytes"] is None


def test_mock_is_deterministic_and_identified_without_network():
    result = run(make_adapter("qwen", settings(), mock=True).predict(model_input({"subject": "hello", "body": "업무 보고"})))
    assert result["status"] == "SUCCESS" and result["decision"] in {"NORMAL", "INJECTION", "REVIEW"}
    assert result["is_mock"] is True and result["cost"] is None


def test_ollama_missing_model_does_not_pull_or_substitute():
    paths = []
    def handler(request):
        paths.append(request.url.path)
        return httpx.Response(200, json={"models": []})
    adapter = OllamaAdapter("qwen", settings(), client(handler))
    result = run(adapter.prepare())
    assert result["ready"] is False and result["error"]["type"] == "MODEL_NOT_INSTALLED"
    assert paths == ["/api/tags"]


def test_ollama_rejects_wrong_quantization():
    def handler(request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen3.5:9b", "digest": "abc"}]})
        return httpx.Response(200, json={"details": {"quantization_level": "Q8_0"}, "model_info": {"qwen3.context_length": 32768}})
    result = run(OllamaAdapter("qwen", settings(), client(handler)).prepare())
    assert result["ready"] is False and result["error"]["type"] == "QUANTIZATION_MISMATCH"


def test_ollama_does_not_accept_qwen_2b_as_required_9b():
    def handler(request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen3.5:9b", "digest": "abc"}]})
        return httpx.Response(200, json={"details": {"quantization_level": "Q4_K_M", "parameter_size": "2.0B"}, "model_info": {"qwen35.context_length": 32768, "general.name": "Qwen3.5 2B"}})
    result = run(OllamaAdapter("qwen", settings(), client(handler)).inspect())
    assert result["ready"] is False and result["error"]["type"] == "MODEL_SIZE_MISMATCH"


@pytest.mark.parametrize("wrong_name", ["Foundation-Sec-8B-Instruct", "Foundation-Sec-8B-Base", "Qwen3.5-9B"])
def test_foundation_config_rejects_obviously_different_installed_model(wrong_name):
    def handler(request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "foundation-sec:test", "digest": "abc"}]})
        return httpx.Response(200, json={"details": {"quantization_level": "Q4_K_M", "parameter_size": "8.03B"}, "model_info": {"llama.context_length": 32768, "general.name": wrong_name}})
    result = run(OllamaAdapter("foundation_sec", settings(), client(handler)).inspect())
    assert result["ready"] is False and result["error"]["type"] == "MODEL_IDENTITY_MISMATCH"


def test_foundation_custom_alias_without_identity_metadata_warns_instead_of_claiming_verified():
    def handler(request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "foundation-sec:test", "digest": "abc"}]})
        return httpx.Response(200, json={"details": {"quantization_level": "Q4_K_M", "parameter_size": "8.03B"}, "model_info": {"llama.context_length": 32768, "general.basename": "Llama"}})
    result = run(OllamaAdapter("foundation_sec", settings(), client(handler)).inspect())
    assert result["ready"] is True and result["identity_verified"] is False
    assert result["identity_unverified"] is True and result["warnings"]
    assert result["metadata"]["model_identity"]["status"] == "UNVERIFIED"


def test_official_looking_tag_never_overrides_contradictory_foundation_metadata():
    configured = settings() | {"foundation_sec_model": "hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q4_K_M-GGUF:Q4_K_M"}
    def handler(request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": configured["foundation_sec_model"], "digest": "abc"}]})
        return httpx.Response(200, json={"details": {"quantization_level": "Q4_K_M", "parameter_size": "8.03B"}, "model_info": {"llama.context_length": 32768, "general.name": "Foundation-Sec-8B-Instruct"}})
    result = run(OllamaAdapter("foundation_sec", configured, client(handler)).inspect())
    assert result["ready"] is False and result["error"]["type"] == "MODEL_IDENTITY_MISMATCH"


def test_prepare_snapshots_actual_ollama_server_version():
    def handler(request):
        path = request.url.path
        if path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen3.5:9b", "digest": "abc"}]})
        if path == "/api/show":
            return httpx.Response(200, json={"details": {"quantization_level": "Q4_K_M", "parameter_size": "9.0B"}, "model_info": {"qwen35.context_length": 32768, "general.name": "Qwen3.5-9B"}})
        if path == "/api/version":
            return httpx.Response(200, json={"version": "0.35.1-test"})
        if path == "/api/ps":
            return httpx.Response(200, json={"models": [{"name": "qwen3.5:9b"}]})
        if path == "/api/generate":
            return httpx.Response(200, json={"done": True})
        pytest.fail(f"Unexpected request {path}")
    result = run(OllamaAdapter("qwen", settings(), client(handler)).prepare())
    assert result["ready"] is True and result["metadata"]["ollama_version"] == "0.35.1-test"


def test_ollama_context_overflow_is_explicit_without_any_request():
    def no_request(request):
        raise AssertionError("over-budget input must not reach Ollama")
    result = run(OllamaAdapter("qwen", settings(), client(no_request)).predict("x" * 5000))
    assert result["status"] == "ERROR" and result["decision"] is None
    assert result["error"]["type"] == "INPUT_LIMIT" and result["attempts"] == []


def test_ollama_existing_system_contributes_to_budget_without_mutating_email():
    adapter = OllamaAdapter("qwen", settings(), client(lambda _: pytest.fail("must not request")))
    adapter.metadata = {"show": {"system": "x" * 4000}}
    result = run(adapter.predict("original email"))
    assert result["error"]["type"] == "INPUT_LIMIT" and result["input_budget"]["existing_system_bytes"] == 4000


def test_ollama_unload_is_verified_and_left_loaded_is_error():
    def handler(request):
        if request.url.path == "/api/generate":
            assert json.loads(request.content)["keep_alive"] == 0
            return httpx.Response(200, json={"done": True})
        return httpx.Response(200, json={"models": [{"name": "qwen3.5:9b"}]})
    result = run(OllamaAdapter("qwen", settings(), client(handler)).release())
    assert result["status"] == "ERROR" and result["unloaded"] is False


def test_ollama_sends_canonical_input_independently_and_does_not_invent_probability():
    payloads = []
    def handler(request):
        payloads.append(json.loads(request.content))
        return httpx.Response(200, json={"model": "qwen3.5:9b", "message": {"role": "assistant", "content": '{"decision":"NORMAL"}'}, "done": True, "total_duration": 100000000, "load_duration": 1000, "prompt_eval_count": 10, "eval_count": 5})
    text = model_input({"subject": "test", "body": "email", "label": "NORMAL"})
    result = run(OllamaAdapter("qwen", settings(), client(handler)).predict(text))
    assert result["decision"] == "NORMAL" and result["status"] == "SUCCESS"
    assert result["probabilities"] is None and result["confidence"] is None
    assert payloads[0]["messages"][1]["content"] == text
    assert payloads[0]["options"]["num_ctx"] == 4096
    assert "keep_alive" in payloads[0] and len(payloads[0]["messages"]) == 2


def test_ollama_parse_failure_never_becomes_normal_or_review():
    adapter = OllamaAdapter("qwen", settings(), client(lambda _: httpx.Response(200, json={"message": {"content": "probably fine"}})))
    result = run(adapter.predict("email"))
    assert result["status"] == "ERROR" and result["decision"] is None
    assert result["error"]["type"] == "PARSE_ERROR"


@pytest.mark.parametrize("status,error_type,attempts", [(401, "AUTHENTICATION", 1), (429, "RATE_LIMIT", 3), (500, "SERVER_ERROR", 3), (404, "UNSUPPORTED_ENDPOINT_OR_MODEL", 1)])
def test_jev_http_failures_have_limited_attempts_and_no_decision(status, error_type, attempts):
    adapter = JevAdapter(settings(), client(lambda _: httpx.Response(status, json={"error": {"message": "failure"}})))
    result = run(adapter.predict("email"))
    assert result["status"] == "ERROR" and result["decision"] is None
    assert result["error"]["type"] == error_type
    assert len(result["attempts"]) == attempts
    assert result["latency_ms"] >= sum(a["latency_ms"] for a in result["attempts"])


def test_jev_timeout_retry_and_missing_key_are_explicit():
    def timeout(request):
        raise httpx.ReadTimeout("timeout", request=request)
    result = run(JevAdapter(settings(), client(timeout)).predict("email"))
    assert result["error"]["type"] == "TIMEOUT" and len(result["attempts"]) == 3
    no_key = settings() | {"openrouter_api_key": ""}
    result = run(JevAdapter(no_key, client(timeout)).predict("email"))
    assert result["error"]["type"] == "API_KEY_MISSING" and result["attempts"] == []


def test_jev_malformed_schema_is_failure_not_fallback():
    result = run(JevAdapter(settings(), client(lambda _: httpx.Response(200, json={"choices": []}))).predict("email"))
    assert result["status"] == "ERROR" and result["decision"] is None
    assert result["error"]["type"] == "INVALID_RESPONSE_SCHEMA"


def test_jev_official_decisions_schema_and_unknown_fields_remain_null():
    payloads = []
    def handler(request):
        assert request.url.path == "/api/alpha/decisions"
        payloads.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "dec-test", "model": "typesafe/jev-1.13-20260917", "provider": "TypeSafe", "answers": {"decision": {"type": "choice", "choice": "REVIEW", "probabilities": {"NORMAL": 0.2, "INJECTION": 0.3, "REVIEW": 0.5}}}, "usage": {"input_tokens": 10, "output_tokens": 1, "cost": 0.000001}})
    text = model_input({"subject": "same", "body": "same email", "label": "INJECTION"})
    result = run(JevAdapter(settings(), client(handler)).predict(text))
    assert result["status"] == "SUCCESS" and result["decision"] == "REVIEW"
    assert payloads[0]["state"] == text
    assert set(payloads[0]["questions"]["decision"]["criteria"]) == {"NORMAL", "INJECTION", "REVIEW"}
    assert "messages" not in payloads[0] and "temperature" not in payloads[0]
    assert result["actual_model"] == "typesafe/jev-1.13-20260917" and result["request_id"] == "dec-test"
    assert result["confidence"] is None and result["reasoning"] is None
    assert result["cost"] == 0.000001 and result["unknown_cost_attempt_count"] == 0


def test_cost_preserves_charged_retries_and_unknown_attempts():
    responses = iter([
        httpx.Response(429, json={"error": {"message": "limit"}, "usage": {"cost": 0.1}}),
        httpx.Response(500, json={"error": {"message": "failed"}}),
        httpx.Response(200, json={"answers": {"decision": {"type": "choice", "choice": "NORMAL"}}, "usage": {"cost": 0.2}}),
    ])
    result = run(JevAdapter(settings(), client(lambda _: next(responses))).predict("email"))
    assert result["status"] == "SUCCESS" and len(result["attempts"]) == 3
    assert result["cost"] == pytest.approx(0.3) and result["unknown_cost_attempt_count"] == 1
    assert result["cost_complete"] is False


def test_request_cancellation_retains_prior_charges_and_current_uncertain_attempt():
    async def scenario():
        second_started = asyncio.Event()
        never = asyncio.Event()
        calls = 0
        async def handler(request):
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(429, json={"id": "charged-first", "usage": {"cost": 0.1}, "error": {"message": "limited"}})
            second_started.set()
            await never.wait()
        adapter = JevAdapter(settings(), client(handler))
        task = asyncio.create_task(adapter.predict("email"))
        await second_started.wait()
        task.cancel()
        result = await task
        assert result["status"] == "CANCELLED" and result["decision"] is None
        assert result["cost"] == 0.1 and result["unknown_cost_attempt_count"] == 1
        assert len(result["attempts"]) == 2 and result["attempts"][1]["status"] == "CANCELLED"
        assert result["attempts"][0]["raw_response"]["id"] == "charged-first"
        assert result["cancellation_phase"] == "request"
    run(scenario())


def test_backoff_cancellation_preserves_charge_without_inventing_another_api_call():
    async def scenario():
        responded = asyncio.Event()
        calls = 0
        async def handler(request):
            nonlocal calls
            calls += 1
            responded.set()
            return httpx.Response(429, json={"id": "charged-first", "usage": {"cost": 0.1}})
        adapter = JevAdapter(settings() | {"retry_delay_seconds": 10}, client(handler))
        task = asyncio.create_task(adapter.predict("email"))
        await responded.wait()
        await asyncio.sleep(0)
        task.cancel()
        result = await task
        assert result["status"] == "CANCELLED" and result["decision"] is None
        assert result["cost"] == 0.1 and result["unknown_cost_attempt_count"] == 0
        assert len(result["attempts"]) == 1 and calls == 1
        assert result["cancellation_phase"] == "retry_backoff"
    run(scenario())


def test_optional_local_explanation_is_separately_timed_and_never_changes_decision():
    payloads = []
    def handler(request):
        payload = json.loads(request.content)
        payloads.append(payload)
        content = '{"decision":"NORMAL"}' if len(payloads) == 1 else '{"explanation":"업무 요청으로 판단했습니다."}'
        return httpx.Response(200, json={"model": "qwen3.5:9b", "message": {"content": content}, "done": True})
    adapter = OllamaAdapter("qwen", settings() | {"explanations": True}, client(handler))
    result = run(adapter.predict('original email'))
    assert result["decision"] == "NORMAL" and result["explanation_generated"] is True
    assert result["explanation"] == "업무 요청으로 판단했습니다."
    assert result["explanation_latency_ms"] >= 0 and result["total_request_latency_ms"] >= result["latency_ms"]
    assert len(payloads) == 2 and payloads[1]["messages"][1]["content"] == "original email"


def test_explanation_overflow_skips_second_call_preserving_classification_and_budget():
    payloads = []
    def handler(request):
        payloads.append(json.loads(request.content))
        return httpx.Response(200, json={"model": "qwen3.5:9b", "message": {"content": '{"decision":"NORMAL"}'}, "done": True})
    adapter = OllamaAdapter("qwen", settings() | {"explanations": True}, client(handler))
    adapter.metadata = {"show": {"system": "s" * 50, "messages": [{"role": "user", "content": "m" * 25}]}}
    # Classification fits by one byte after the 75-byte Modelfile additions;
    # the separate explanation's longer prompt/output reservation must not fit.
    text = "x" * (common_input_limit(settings()) - 75 - 1)
    result = run(adapter.predict(text))
    assert result["status"] == "SUCCESS" and result["decision"] == "NORMAL"
    assert len(payloads) == 1 and result["explanation_generated"] is False
    assert result["explanation_error"]["type"] == "INPUT_LIMIT"
    assert result["explanation_attempts"] == []
    assert result["input_budget"]["existing_system_bytes"] == 50
    assert result["input_budget"]["existing_messages_bytes"] == 25
    explanation_budget = result["explanation_input_budget"]
    assert explanation_budget["output_reserved_tokens"] == 256
    assert explanation_budget["existing_system_bytes"] == 50 and explanation_budget["existing_messages_bytes"] == 25
    assert explanation_budget["estimated_total_tokens_upper_bound"] >= 4096


def test_response_secret_is_redacted_before_local_storage():
    response = {"answers": {"decision": {"type": "choice", "choice": "NORMAL"}}, "echo": "test-secret"}
    result = run(JevAdapter(settings(), client(lambda _: httpx.Response(200, json=response))).predict("email"))
    assert "test-secret" not in json.dumps(result)


def test_resource_monitor_separates_backend_and_gpu_unknown():
    monitor = ResourceMonitor(interval_seconds=0.01)
    monitor.start()
    report = monitor.stop()
    assert report["backend_rss_peak_bytes"] > 0
    assert report["system_ram_used_peak_bytes"] > 0
    assert report["gpu_memory_peak_bytes"] is None
    assert report["collection_interval_seconds"] == 0.01
