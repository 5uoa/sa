"""统一 Provider Adapter：OpenAI-compatible、Anthropic、Azure、Google、Ollama。"""
import json
import re
from dataclasses import dataclass
from typing import Any, AsyncIterator
from urllib.parse import urlsplit

import httpx

from llm.capabilities import normalize_capabilities, normalize_provider


class ProviderError(Exception):
    def __init__(self, message: str, *, status_code: int = 0, retryable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


@dataclass
class ModelTarget:
    id: str
    name: str
    provider: str
    endpoint: str
    model_key: str
    api_key: str
    capabilities: dict[str, Any]
    config: dict[str, Any]


def model_target(row: dict[str, Any], api_key: str) -> ModelTarget:
    endpoint = str(row.get("endpoint") or "").strip()
    config = _json_object(row.get("config"))
    capabilities = _json_object(row.get("capabilities"))
    return ModelTarget(
        id=str(row.get("id") or ""),
        name=str(row.get("name") or row.get("model_key") or "模型"),
        provider=normalize_provider(row.get("provider"), endpoint),
        endpoint=endpoint,
        model_key=str(row.get("model_key") or ""),
        api_key=api_key,
        capabilities=normalize_capabilities(capabilities),
        config=config,
    )


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except ValueError:
            return {}
        if isinstance(parsed, dict):
            return parsed
    return {}


def _headers(target: ModelTarget) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if target.provider == "anthropic":
        headers["x-api-key"] = target.api_key
        headers["anthropic-version"] = str(
            target.config.get("anthropicVersion") or "2023-06-01"
        )
    elif target.provider == "azure_openai":
        headers["api-key"] = target.api_key
    elif target.provider == "google":
        headers["x-goog-api-key"] = target.api_key
    else:
        headers["Authorization"] = f"Bearer {target.api_key}"
    custom = target.config.get("headers")
    if isinstance(custom, dict):
        headers.update({str(key): str(value) for key, value in custom.items()})
    return headers


def _openai_url(target: ModelTarget) -> str:
    configured = str(target.config.get("chatPath") or "").strip()
    if configured:
        return configured
    url = target.endpoint.rstrip("/")
    path = urlsplit(url).path
    if path.endswith("/chat/completions"):
        return url
    if target.provider == "azure_openai":
        version = str(target.config.get("apiVersion") or "2024-10-21")
        separator = "&" if "?" in url else "?"
        return f"{url}{separator}api-version={version}"
    if path.endswith("/v1"):
        return f"{url}/chat/completions"
    return f"{url}/v1/chat/completions" if target.provider == "ollama" else (
        f"{url}/chat/completions"
    )


def _anthropic_url(target: ModelTarget) -> str:
    configured = str(target.config.get("chatPath") or "").strip()
    if configured:
        return configured
    url = target.endpoint.rstrip("/")
    path = urlsplit(url).path
    if path.endswith("/messages"):
        return url
    if path.endswith("/v1"):
        return f"{url}/messages"
    return f"{url}/v1/messages"


def _check_capabilities(
    target: ModelTarget,
    *,
    tools: list[dict[str, Any]] | None,
    messages: list[dict[str, Any]],
    response_format: dict[str, Any] | None,
) -> None:
    if tools and not target.capabilities["tools"]:
        raise ProviderError("模型未声明 Tool Calling 能力", retryable=False)
    if response_format and not target.capabilities["json"]:
        raise ProviderError("模型未声明 JSON 输出能力", retryable=False)
    if _has_image(messages) and not target.capabilities["vision"]:
        raise ProviderError("模型未声明图片理解能力", retryable=False)


def _has_image(messages: list[dict[str, Any]]) -> bool:
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for item in content:
            if isinstance(item, dict) and item.get("type") in {"image_url", "image"}:
                return True
    return False


async def complete(
    target: ModelTarget,
    *,
    system_prompt: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    temperature: float,
    max_tokens: int,
    response_format: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _check_capabilities(
        target,
        tools=tools,
        messages=messages,
        response_format=response_format,
    )
    if target.provider == "anthropic":
        return await _anthropic_complete(
            target,
            system_prompt=system_prompt,
            messages=messages,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
        )
    return await _openai_complete(
        target,
        system_prompt=system_prompt,
        messages=messages,
        tools=tools,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format=response_format,
    )


async def _openai_complete(
    target: ModelTarget,
    *,
    system_prompt: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    temperature: float,
    max_tokens: int,
    response_format: dict[str, Any] | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": target.model_key,
        "messages": [{"role": "system", "content": system_prompt}, *messages],
    }
    token_key = str(target.config.get("maxTokensField") or "max_tokens")
    payload[token_key] = max_tokens
    if not target.config.get("omitTemperature"):
        payload["temperature"] = temperature
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = str(target.config.get("toolChoice") or "auto")
    if response_format:
        payload["response_format"] = response_format
    if "deepseek" in target.model_key.lower():
        payload["thinking"] = {"type": "disabled"}
    response = await _post_json(target, _openai_url(target), payload)
    data = _response_json(response)
    choices = data.get("choices") or []
    if not choices:
        raise ProviderError("模型返回缺少 choices")
    message = (choices[0].get("message") or {}) if isinstance(choices[0], dict) else {}
    usage = data.get("usage") or {}
    content, embedded_calls = _deepseek_embedded_tool_calls(
        _openai_content(message.get("content"))
    )
    native_calls = message.get("tool_calls") or []
    if tools:
        tool_calls = native_calls or embedded_calls
    else:
        # Tool budget exhausted: keep the cleaned prose, but never execute
        # another call from either native tool calling or DeepSeek DSML text.
        tool_calls = []
    return _normalized_result(
        target,
        content=content,
        tool_calls=tool_calls,
        usage=usage,
        finish_reason=str(choices[0].get("finish_reason") or ""),
        response_model=str(data.get("model") or target.model_key),
    )


def _openai_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(item.get("text") or "")
            for item in content
            if isinstance(item, dict)
        )
    return ""


def _deepseek_embedded_tool_calls(
    content: str,
) -> tuple[str, list[dict[str, Any]]]:
    """解析 DeepSeek 在正文中返回的 DSML 工具调用。"""
    if "DSML" not in content or "tool_calls" not in content:
        return content, []
    invoke_pattern = re.compile(
        r"<[^>]*invoke\s+name=\"([^\"]+)\"[^>]*>([\s\S]*?)</[^>]*invoke>",
        re.IGNORECASE,
    )
    parameter_pattern = re.compile(
        r"<[^>]*parameter\s+name=\"([^\"]+)\"([^>]*)>([\s\S]*?)</[^>]*parameter>",
        re.IGNORECASE,
    )
    calls: list[dict[str, Any]] = []
    for index, match in enumerate(invoke_pattern.finditer(content), start=1):
        function_name = match.group(1)
        arguments: dict[str, Any] = {}
        for parameter in parameter_pattern.finditer(match.group(2)):
            name = parameter.group(1)
            attributes = parameter.group(2)
            raw_value = parameter.group(3).strip()
            value: Any = raw_value
            if 'string="true"' not in attributes.lower():
                try:
                    value = json.loads(raw_value)
                except ValueError:
                    value = raw_value
            arguments[name] = value
        calls.append(
            {
                "id": f"deepseek-dsml-{index}",
                "type": "function",
                "function": {
                    "name": function_name,
                    "arguments": json.dumps(arguments, ensure_ascii=False),
                },
            }
        )
    first = content.find("<｜｜DSML")
    if first < 0:
        first = content.find("<|DSML")
    clean_content = content[:first].strip() if first >= 0 else content
    return clean_content, calls


async def _anthropic_complete(
    target: ModelTarget,
    *,
    system_prompt: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    temperature: float,
    max_tokens: int,
    response_format: dict[str, Any] | None,
) -> dict[str, Any]:
    if response_format:
        system_prompt += "\n只返回符合要求的 JSON，不要输出 Markdown 代码围栏。"
    payload: dict[str, Any] = {
        "model": target.model_key,
        "system": system_prompt,
        "messages": _anthropic_messages(messages),
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if tools:
        payload["tools"] = [
            {
                "name": item["function"]["name"],
                "description": item["function"].get("description", ""),
                "input_schema": item["function"].get(
                    "parameters", {"type": "object", "properties": {}}
                ),
            }
            for item in tools
        ]
        payload["tool_choice"] = {"type": "auto"}
    response = await _post_json(target, _anthropic_url(target), payload)
    data = _response_json(response)
    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    for index, block in enumerate(data.get("content") or []):
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            text_parts.append(str(block.get("text") or ""))
        elif block.get("type") == "tool_use":
            tool_calls.append(
                {
                    "id": str(block.get("id") or f"anthropic-tool-{index}"),
                    "type": "function",
                    "function": {
                        "name": str(block.get("name") or ""),
                        "arguments": json.dumps(
                            block.get("input") or {}, ensure_ascii=False
                        ),
                    },
                }
            )
    usage = data.get("usage") or {}
    return _normalized_result(
        target,
        content="".join(text_parts),
        tool_calls=tool_calls,
        usage=usage,
        finish_reason=str(data.get("stop_reason") or ""),
        response_model=str(data.get("model") or target.model_key),
    )


def _anthropic_messages(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    index = 0
    while index < len(messages):
        message = messages[index]
        role = message.get("role")
        if role == "tool":
            blocks: list[dict[str, Any]] = []
            while index < len(messages) and messages[index].get("role") == "tool":
                tool_message = messages[index]
                blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": str(
                            tool_message.get("tool_call_id")
                            or tool_message.get("name")
                            or "tool"
                        ),
                        "content": str(tool_message.get("content") or ""),
                    }
                )
                index += 1
            converted.append({"role": "user", "content": blocks})
            continue
        if role == "assistant" and message.get("tool_calls"):
            blocks = []
            if message.get("content"):
                blocks.append({"type": "text", "text": str(message["content"])})
            for call in message.get("tool_calls") or []:
                function = call.get("function") or {}
                try:
                    tool_input = json.loads(function.get("arguments") or "{}")
                except ValueError:
                    tool_input = {}
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": str(call.get("id") or ""),
                        "name": str(function.get("name") or ""),
                        "input": tool_input,
                    }
                )
            converted.append({"role": "assistant", "content": blocks})
            index += 1
            continue
        converted.append(
            {
                "role": role,
                "content": _anthropic_content(message.get("content")),
            }
        )
        index += 1
    return converted


def _anthropic_content(content: Any) -> Any:
    if not isinstance(content, list):
        return content or ""
    blocks: list[dict[str, Any]] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text":
            blocks.append({"type": "text", "text": str(item.get("text") or "")})
        elif item.get("type") == "image":
            blocks.append(item)
        elif item.get("type") == "image_url":
            url = str((item.get("image_url") or {}).get("url") or "")
            if url.startswith("data:") and ";base64," in url:
                header, data = url.split(";base64,", 1)
                blocks.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": header[5:],
                            "data": data,
                        },
                    }
                )
    return blocks


def _normalized_result(
    target: ModelTarget,
    *,
    content: str,
    tool_calls: list[dict[str, Any]],
    usage: dict[str, Any],
    finish_reason: str,
    response_model: str,
) -> dict[str, Any]:
    return {
        "provider": target.provider,
        "model": response_model,
        "content": content,
        "toolCalls": tool_calls,
        "finishReason": finish_reason,
        "inputTokens": int(
            usage.get("prompt_tokens") or usage.get("input_tokens") or 0
        ),
        "outputTokens": int(
            usage.get("completion_tokens") or usage.get("output_tokens") or 0
        ),
        "cachedInputTokens": int(
            usage.get("cached_tokens")
            or (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
            or (usage.get("input_tokens_details") or {}).get("cached_tokens")
            or 0
        ),
    }


async def _post_json(
    target: ModelTarget, url: str, payload: dict[str, Any]
) -> httpx.Response:
    timeout = float(target.config.get("timeout") or 90)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=_headers(target), json=payload)
    except httpx.HTTPError as exc:
        raise ProviderError(
            f"模型连接失败：{exc.__class__.__name__}", retryable=True
        ) from exc
    if response.status_code >= 400:
        retryable = response.status_code in {408, 409, 425, 429} or response.status_code >= 500
        raise ProviderError(
            f"模型 HTTP {response.status_code}：{response.text[:240]}",
            status_code=response.status_code,
            retryable=retryable,
        )
    return response


def _response_json(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise ProviderError("模型返回非 JSON 响应", retryable=True) from exc
    if not isinstance(payload, dict):
        raise ProviderError("模型响应格式不正确", retryable=True)
    if payload.get("error"):
        raise ProviderError(str(payload["error"]), retryable=False)
    return payload


async def stream_chat(
    target: ModelTarget,
    *,
    system_prompt: str,
    messages: list[dict[str, Any]],
    temperature: float,
    max_tokens: int,
) -> AsyncIterator[dict[str, Any]]:
    if not target.capabilities["streaming"]:
        raise ProviderError("模型未声明流式输出能力", retryable=False)
    if target.provider == "anthropic":
        iterator = _anthropic_stream(target, system_prompt, messages, temperature, max_tokens)
    else:
        iterator = _openai_stream(target, system_prompt, messages, temperature, max_tokens)
    async for event in iterator:
        yield event


async def _openai_stream(
    target: ModelTarget,
    system_prompt: str,
    messages: list[dict[str, Any]],
    temperature: float,
    max_tokens: int,
) -> AsyncIterator[dict[str, Any]]:
    payload: dict[str, Any] = {
        "model": target.model_key,
        "messages": [{"role": "system", "content": system_prompt}, *messages],
        (str(target.config.get("maxTokensField") or "max_tokens")): max_tokens,
        "temperature": temperature,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if "deepseek" in target.model_key.lower():
        payload["thinking"] = {"type": "disabled"}
    async with httpx.AsyncClient(timeout=float(target.config.get("timeout") or 90)) as client:
        async with client.stream(
            "POST",
            _openai_url(target),
            headers=_headers(target),
            json=payload,
        ) as response:
            if response.status_code >= 400:
                body = (await response.aread()).decode("utf-8", errors="replace")
                raise ProviderError(
                    f"模型 HTTP {response.status_code}：{body[:240]}",
                    status_code=response.status_code,
                    retryable=response.status_code in {408, 429} or response.status_code >= 500,
                )
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data_text = line[5:].strip()
                if data_text == "[DONE]":
                    break
                try:
                    data = json.loads(data_text)
                except ValueError:
                    continue
                choices = data.get("choices") or []
                if choices:
                    delta = (choices[0].get("delta") or {}).get("content")
                    if delta:
                        yield {"type": "delta", "text": str(delta)}
                if data.get("usage"):
                    usage = data["usage"]
                    yield {
                        "type": "usage",
                        "inputTokens": int(usage.get("prompt_tokens") or 0),
                        "outputTokens": int(usage.get("completion_tokens") or 0),
                    }
    yield {"type": "done"}


async def _anthropic_stream(
    target: ModelTarget,
    system_prompt: str,
    messages: list[dict[str, Any]],
    temperature: float,
    max_tokens: int,
) -> AsyncIterator[dict[str, Any]]:
    payload = {
        "model": target.model_key,
        "system": system_prompt,
        "messages": _anthropic_messages(messages),
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
    }
    async with httpx.AsyncClient(timeout=float(target.config.get("timeout") or 90)) as client:
        async with client.stream(
            "POST",
            _anthropic_url(target),
            headers=_headers(target),
            json=payload,
        ) as response:
            if response.status_code >= 400:
                body = (await response.aread()).decode("utf-8", errors="replace")
                raise ProviderError(
                    f"模型 HTTP {response.status_code}：{body[:240]}",
                    status_code=response.status_code,
                    retryable=response.status_code in {408, 429} or response.status_code >= 500,
                )
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                try:
                    data = json.loads(line[5:].strip())
                except ValueError:
                    continue
                if data.get("type") == "content_block_delta":
                    delta = data.get("delta") or {}
                    if delta.get("type") == "text_delta" and delta.get("text"):
                        yield {"type": "delta", "text": str(delta["text"])}
                elif data.get("type") == "message_delta":
                    usage = data.get("usage") or {}
                    if usage:
                        yield {
                            "type": "usage",
                            "inputTokens": int(usage.get("input_tokens") or 0),
                            "outputTokens": int(usage.get("output_tokens") or 0),
                        }
    yield {"type": "done"}
