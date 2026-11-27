"""统一模型适配器、上下文预算与能力参数测试。"""
import asyncio
import json
from typing import Any

import pytest

from llm.adapters import (
    ModelTarget,
    _deepseek_embedded_tool_calls,
    complete,
    stream_chat,
)
from llm.capabilities import normalize_capabilities, normalize_provider
from llm.capability_tests import probe_model_capabilities
from llm.context import fit_messages_to_budget


def _target(provider: str = "openai_compatible") -> ModelTarget:
    return ModelTarget(
        id="model-1",
        name="test",
        provider=provider,
        endpoint=(
            "https://api.anthropic.com"
            if provider == "anthropic"
            else "http://model.test/v1"
        ),
        model_key="test-model",
        api_key="secret-key",
        capabilities=normalize_capabilities(
            {
                "contextWindow": 8192,
                "maxOutputTokens": 1024,
                "tools": True,
                "vision": True,
                "json": True,
                "streaming": True,
            }
        ),
        config={},
    )


def test_provider_and_capabilities_are_structured():
    assert normalize_provider("", "https://api.anthropic.com") == "anthropic"
    assert normalize_provider("ollama", "") == "ollama"
    capabilities = normalize_capabilities(
        {
            "context_window": "128000",
            "max_output_tokens": "999999",
            "tools": "true",
            "vision": 1,
        }
    )
    assert capabilities["contextWindow"] == 128000
    assert capabilities["maxOutputTokens"] == 128000
    assert capabilities["tools"] is True
    assert capabilities["vision"] is True


def test_deepseek_embedded_dsml_tool_calls_are_parsed():
    content = (
        "先查询数据。\n"
        "<｜｜DSML｜｜tool_calls>\n"
        '<｜｜DSML｜｜invoke name="query_readonly">\n'
        '<｜｜DSML｜｜parameter name="sql" string="true">'
        "select current_database() as database"
        "</｜｜DSML｜｜parameter>\n"
        "</｜｜DSML｜｜invoke>\n"
        "</｜｜DSML｜｜tool_calls>"
    )
    clean, calls = _deepseek_embedded_tool_calls(content)
    assert clean == "先查询数据。"
    assert calls[0]["function"]["name"] == "query_readonly"
    assert json.loads(calls[0]["function"]["arguments"]) == {
        "sql": "select current_database() as database"
    }


def test_deepseek_dsml_is_not_executed_after_tool_budget_is_exhausted(
    monkeypatch: pytest.MonkeyPatch,
):
    dsml = (
        "根据已有结果输出。\n"
        "<｜｜DSML｜｜tool_calls>\n"
        '<｜｜DSML｜｜invoke name="query_readonly">\n'
        '<｜｜DSML｜｜parameter name="sql" string="true">select 1</｜｜DSML｜｜parameter>\n'
        "</｜｜DSML｜｜invoke>\n"
        "</｜｜DSML｜｜tool_calls>"
    )

    class Response:
        status_code = 200
        text = ""

        def json(self) -> dict[str, Any]:
            return {
                "model": "test-model",
                "choices": [
                    {
                        "message": {"content": dsml},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {},
            }

    class Client:
        def __init__(self, *_: Any, **__: Any):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_: Any) -> None:
            return None

        async def post(self, *_: Any, **__: Any):
            return Response()

    monkeypatch.setattr("llm.adapters.httpx.AsyncClient", Client)
    result = asyncio.run(
        complete(
            _target(),
            system_prompt="system",
            messages=[{"role": "user", "content": "final answer"}],
            tools=None,
            temperature=0.2,
            max_tokens=321,
        )
    )
    assert result["content"] == "根据已有结果输出。"
    assert result["toolCalls"] == []


def test_context_budget_drops_old_messages_but_keeps_latest_user():
    messages = [
        {"role": "user", "content": "old " * 1000},
        {"role": "assistant", "content": "old answer " * 1000},
        {"role": "user", "content": "latest question"},
    ]
    fitted, stats = fit_messages_to_budget(
        "system",
        messages,
        context_window=2000,
        max_output_tokens=200,
    )
    assert fitted[0]["role"] == "system"
    assert fitted[-1]["content"] == "latest question"
    assert stats["truncated"] is True


def test_openai_adapter_sends_temperature_output_json_and_vision(
    monkeypatch: pytest.MonkeyPatch,
):
    requests: list[dict[str, Any]] = []

    class Response:
        status_code = 200
        text = ""

        def json(self) -> dict[str, Any]:
            return {
                "model": "test-model",
                "choices": [
                    {
                        "message": {"content": '{"ok":true}'},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 4,
                },
            }

    class Client:
        def __init__(self, *_: Any, **__: Any):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_: Any) -> None:
            return None

        async def post(self, url: str, *, headers: dict[str, str], json: dict[str, Any]):
            requests.append({"url": url, "headers": headers, "payload": json})
            return Response()

    monkeypatch.setattr("llm.adapters.httpx.AsyncClient", Client)
    result = asyncio.run(
        complete(
            _target(),
            system_prompt="system",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "describe"},
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/png;base64,AAAA"},
                        },
                    ],
                }
            ],
            tools=None,
            temperature=0.2,
            max_tokens=321,
            response_format={"type": "json_object"},
        )
    )
    payload = requests[0]["payload"]
    assert requests[0]["url"] == "http://model.test/v1/chat/completions"
    assert payload["temperature"] == 0.2
    assert payload["max_tokens"] == 321
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["messages"][-1]["content"][1]["type"] == "image_url"
    assert result["inputTokens"] == 12
    assert result["outputTokens"] == 4


def test_anthropic_adapter_converts_tools_and_tool_results(
    monkeypatch: pytest.MonkeyPatch,
):
    requests: list[dict[str, Any]] = []

    class Response:
        status_code = 200
        text = ""

        def json(self) -> dict[str, Any]:
            return {
                "id": "msg",
                "model": "claude-test",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tool-1",
                        "name": "echo",
                        "input": {"text": "hello"},
                    }
                ],
                "stop_reason": "tool_use",
                "usage": {"input_tokens": 10, "output_tokens": 3},
            }

    class Client:
        def __init__(self, *_: Any, **__: Any):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_: Any) -> None:
            return None

        async def post(self, url: str, *, headers: dict[str, str], json: dict[str, Any]):
            requests.append({"url": url, "headers": headers, "payload": json})
            return Response()

    monkeypatch.setattr("llm.adapters.httpx.AsyncClient", Client)
    result = asyncio.run(
        complete(
            _target("anthropic"),
            system_prompt="system",
            messages=[
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "previous-tool",
                            "function": {
                                "name": "previous",
                                "arguments": '{"value":"x"}',
                            },
                        }
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": "previous-tool",
                    "name": "previous",
                    "content": "result",
                },
                {"role": "user", "content": "continue"},
            ],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "echo",
                        "description": "Echo",
                        "parameters": {
                            "type": "object",
                            "properties": {"text": {"type": "string"}},
                        },
                    },
                }
            ],
            temperature=0.7,
            max_tokens=256,
        )
    )
    payload = requests[0]["payload"]
    assert requests[0]["url"] == "https://api.anthropic.com/v1/messages"
    assert requests[0]["headers"]["x-api-key"] == "secret-key"
    assert payload["tools"][0]["input_schema"]["type"] == "object"
    assert payload["messages"][0]["content"][0]["type"] == "tool_use"
    assert payload["messages"][1]["content"][0]["type"] == "tool_result"
    assert result["toolCalls"][0]["function"]["name"] == "echo"
    assert json.loads(result["toolCalls"][0]["function"]["arguments"]) == {
        "text": "hello"
    }


def test_openai_streaming_parser(monkeypatch: pytest.MonkeyPatch):
    lines = [
        'data: {"choices":[{"delta":{"content":"你"}}]}',
        'data: {"choices":[{"delta":{"content":"好"}}]}',
        'data: {"usage":{"prompt_tokens":5,"completion_tokens":2},'
        '"choices":[]}',
        "data: [DONE]",
    ]

    class StreamResponse:
        status_code = 200

        async def aiter_lines(self):
            for line in lines:
                yield line

    class StreamContext:
        async def __aenter__(self):
            return StreamResponse()

        async def __aexit__(self, *_: Any) -> None:
            return None

    class Client:
        def __init__(self, *_: Any, **__: Any):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_: Any) -> None:
            return None

        def stream(self, *_args: Any, **_kwargs: Any):
            return StreamContext()

    monkeypatch.setattr("llm.adapters.httpx.AsyncClient", Client)

    async def collect():
        events = []
        async for event in stream_chat(
            _target(),
            system_prompt="system",
            messages=[{"role": "user", "content": "hello"}],
            temperature=0,
            max_tokens=16,
        ):
            events.append(event)
        return events

    events = asyncio.run(collect())
    assert "".join(item.get("text", "") for item in events) == "你好"
    assert any(item.get("type") == "usage" for item in events)


def test_deep_capability_probe_covers_tools_json_vision_stream(
    monkeypatch: pytest.MonkeyPatch,
):
    posts: list[dict[str, Any]] = []

    class Response:
        status_code = 200
        text = ""

        def __init__(self, payload: dict[str, Any]):
            self._payload = payload

        def json(self) -> dict[str, Any]:
            return self._payload

    class StreamResponse:
        status_code = 200

        async def aiter_lines(self):
            yield 'data: {"choices":[{"delta":{"content":"stream-ok"}}]}'
            yield "data: [DONE]"

    class StreamContext:
        async def __aenter__(self):
            return StreamResponse()

        async def __aexit__(self, *_: Any) -> None:
            return None

    class Client:
        def __init__(self, *_: Any, **__: Any):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_: Any) -> None:
            return None

        async def post(self, _url: str, *, json: dict[str, Any], **_: Any):
            posts.append(json)
            if json.get("tools"):
                return Response(
                    {
                        "choices": [
                            {
                                "message": {
                                    "content": "",
                                    "tool_calls": [
                                        {
                                            "id": "cap-call",
                                            "type": "function",
                                            "function": {
                                                "name": "capability_echo",
                                                "arguments": '{"value":"tool-ok"}',
                                            },
                                        }
                                    ],
                                }
                            }
                        ],
                        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                    }
                )
            if json.get("response_format"):
                content = '{"ok":true,"value":1}'
            else:
                content = "white"
            return Response(
                {
                    "choices": [{"message": {"content": content}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                }
            )

        def stream(self, *_args: Any, **_kwargs: Any):
            return StreamContext()

    monkeypatch.setattr("llm.adapters.httpx.AsyncClient", Client)
    result = asyncio.run(probe_model_capabilities(_target(), deep=True))
    assert result["ok"] is True
    assert {item["name"] for item in result["checks"]} == {
        "text",
        "tools",
        "json",
        "vision",
        "streaming",
    }
    assert any(item.get("tools") for item in posts)
