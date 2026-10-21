"""Backend-only environment settings. Never persist or expose credentials."""
import os
from pathlib import Path

from dotenv import load_dotenv

from .core import MAX_INPUT_BYTES

ROOT = Path(__file__).resolve().parents[2]


def _numeric(name, default, cast, minimum, maximum):
    value = cast(os.getenv(name, str(default)))
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def load_settings():
    load_dotenv(ROOT / ".env", override=False)
    return {
        "ollama_url": os.getenv("OLLAMA_URL", os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip("/"),
        "foundation_sec_model": os.getenv("FOUNDATION_SEC_MODEL", os.getenv("OLLAMA_FOUNDATION_SEC_MODEL", "hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q4_K_M-GGUF:Q4_K_M")),
        "qwen_model": os.getenv("QWEN_MODEL", os.getenv("OLLAMA_QWEN_MODEL", "qwen3.5:9b")),
        "qwen_thinking": False,
        "jev_model": os.getenv("OPENROUTER_JEV_MODEL", "typesafe/jev-1.13"),
        "openrouter_api_key": os.getenv("OPENROUTER_API_KEY", ""),
        "context_length": _numeric("CONTEXT_LENGTH", 4096, int, 512, 65536),
        "temperature": _numeric("TEMPERATURE", 0, float, 0, 2),
        "seed": _numeric("SEED", 42, int, 0, 2147483647),
        "max_output_tokens": _numeric("MAX_OUTPUT_TOKENS", 64, int, 8, 8192),
        "timeout_seconds": _numeric("TIMEOUT_SECONDS", 120, float, 1, 600),
        "max_attempts": _numeric("MAX_ATTEMPTS", 3, int, 1, 3),
        "retry_delay_seconds": 0.5,
        "thinking": None,
        "explanations": False,
        "warmup": False,
        "local_concurrency": 1,
        "max_input_bytes": MAX_INPUT_BYTES,
        "memory_interval_seconds": 0.25,
    }


def public_settings(settings):
    public = {key: value for key, value in settings.items() if key != "openrouter_api_key" and "api_key" not in key.lower() and "authorization" not in key.lower()}
    public["openrouter_key_configured"] = bool(settings.get("openrouter_api_key"))
    return public
