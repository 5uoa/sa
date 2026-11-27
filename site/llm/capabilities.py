"""供应商与模型能力规范化。"""
from typing import Any

PROVIDERS = {
    "openai_compatible",
    "anthropic",
    "azure_openai",
    "google",
    "ollama",
}

CAPABILITY_DEFAULTS: dict[str, Any] = {
    "contextWindow": 32768,
    "maxOutputTokens": 2048,
    "tools": False,
    "vision": False,
    "json": False,
    "streaming": False,
    "embeddings": False,
    "audio": False,
}

BOOLEAN_CAPABILITIES = {
    "tools",
    "vision",
    "json",
    "streaming",
    "embeddings",
    "audio",
}


def normalize_provider(value: Any, endpoint: str = "") -> str:
    provider = str(value or "").strip().lower()
    if provider in PROVIDERS:
        return provider
    lower_endpoint = endpoint.lower()
    if "anthropic" in lower_endpoint:
        return "anthropic"
    if "openai.azure.com" in lower_endpoint:
        return "azure_openai"
    if "generativelanguage.googleapis.com" in lower_endpoint:
        return "google"
    if "localhost:11434" in lower_endpoint or "ollama" in lower_endpoint:
        return "ollama"
    return "openai_compatible"


def normalize_capabilities(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    context_window = _bounded_int(
        raw.get("contextWindow", raw.get("context_window")),
        int(CAPABILITY_DEFAULTS["contextWindow"]),
        1024,
        2_000_000,
    )
    max_output = _bounded_int(
        raw.get("maxOutputTokens", raw.get("max_output_tokens")),
        int(CAPABILITY_DEFAULTS["maxOutputTokens"]),
        1,
        min(context_window, 200_000),
    )
    result: dict[str, Any] = {
        "contextWindow": context_window,
        "maxOutputTokens": max_output,
    }
    for key in BOOLEAN_CAPABILITIES:
        result[key] = _to_bool(raw.get(key, CAPABILITY_DEFAULTS[key]))
    return result


def _bounded_int(value: Any, default: int, low: int, high: int) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return max(low, min(high, parsed))


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def capability_enabled(capabilities: dict[str, Any], name: str) -> bool:
    return bool(normalize_capabilities(capabilities).get(name))
