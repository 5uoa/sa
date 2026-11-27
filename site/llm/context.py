"""模型上下文预算估算与安全裁剪。"""
import json
from typing import Any


def estimate_content_tokens(content: Any) -> int:
    if isinstance(content, str):
        return _estimate_text(content)
    if isinstance(content, list):
        total = 0
        for item in content:
            if not isinstance(item, dict):
                total += _estimate_text(str(item))
            elif item.get("type") == "image_url":
                total += 1024
            elif item.get("type") == "image":
                total += 1024
            else:
                total += _estimate_text(
                    json.dumps(item, ensure_ascii=False, default=str)
                )
        return total
    if content is None:
        return 0
    return _estimate_text(json.dumps(content, ensure_ascii=False, default=str))


def estimate_message_tokens(message: dict[str, Any]) -> int:
    total = 8 + estimate_content_tokens(message.get("content"))
    tool_calls = message.get("tool_calls")
    if tool_calls:
        total += estimate_content_tokens(tool_calls)
    return total


def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    return sum(estimate_message_tokens(message) for message in messages)


def _estimate_text(value: str) -> int:
    if not value:
        return 0
    ascii_chars = sum(1 for char in value if ord(char) < 128)
    non_ascii = len(value) - ascii_chars
    # 英文约 4 字符/token；中文约 1.5 字符/token，取保守估算。
    return max(1, round(ascii_chars / 4 + non_ascii / 1.5))


def fit_messages_to_budget(
    system_prompt: str,
    messages: list[dict[str, Any]],
    *,
    context_window: int,
    max_output_tokens: int,
    context_budget_tokens: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    safe_window = max(1024, int(context_window))
    reserved = max(1, min(int(max_output_tokens), safe_window // 2))
    if context_budget_tokens:
        budget = min(
            int(context_budget_tokens),
            max(512, safe_window - reserved - 256),
        )
    else:
        budget = max(512, safe_window - reserved - 256)
    system_message = {"role": "system", "content": system_prompt}
    system_tokens = estimate_message_tokens(system_message)
    available = max(256, budget - system_tokens)
    chunks = _message_chunks(messages)
    selected: list[dict[str, Any]] = []
    used = 0
    dropped = 0
    for chunk in reversed(chunks):
        chunk_tokens = estimate_messages_tokens(chunk)
        if used + chunk_tokens <= available:
            selected = [*chunk, *selected]
            used += chunk_tokens
            continue
        dropped += len(chunk)
        if not selected and chunk:
            fitting = _truncate_largest_message(chunk[-1], available)
            if fitting:
                selected = [fitting]
                used = estimate_message_tokens(fitting)
    return [system_message, *selected], {
        "contextWindow": safe_window,
        "budgetTokens": budget,
        "estimatedTokens": system_tokens + used,
        "maxOutputTokens": reserved,
        "droppedMessages": dropped,
        "truncated": dropped > 0,
    }


def _message_chunks(messages: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    chunks: list[list[dict[str, Any]]] = []
    index = 0
    while index < len(messages):
        message = messages[index]
        if message.get("role") == "assistant" and message.get("tool_calls"):
            chunk = [message]
            index += 1
            while index < len(messages) and messages[index].get("role") == "tool":
                chunk.append(messages[index])
                index += 1
            chunks.append(chunk)
            continue
        chunks.append([message])
        index += 1
    return chunks


def _truncate_largest_message(
    message: dict[str, Any], available_tokens: int
) -> dict[str, Any] | None:
    content = message.get("content")
    if not isinstance(content, str):
        return None
    max_chars = max(200, int(available_tokens * 2))
    if len(content) <= max_chars:
        return message
    return {
        **message,
        "content": content[:max_chars] + "\n...[context truncated]",
    }
