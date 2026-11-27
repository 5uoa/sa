"""模型基础与能力矩阵测试。"""
import json
import time
from dataclasses import replace
from typing import Any

from llm.adapters import ModelTarget, ProviderError, complete, stream_chat

PIXEL_PNG = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Zq7sAAAAASUVORK5CYII="
)


async def probe_model_capabilities(
    target: ModelTarget, *, deep: bool = False
) -> dict[str, Any]:
    started = time.perf_counter()
    checks: list[dict[str, Any]] = []
    try:
        basic = await complete(
            target,
            system_prompt="You are a connectivity tester.",
            messages=[{"role": "user", "content": "Reply with OK."}],
            tools=None,
            temperature=0,
            max_tokens=8,
        )
        checks.append(
            {
                "name": "text",
                "ok": bool(basic["content"].strip()),
                "message": "文本生成通过" if basic["content"].strip() else "返回空内容",
                "latencyMs": round((time.perf_counter() - started) * 1000),
            }
        )
        if not checks[0]["ok"]:
            return _result(target, checks, started)
        if not deep:
            return _result(target, checks, started)
        capabilities = target.capabilities
        if capabilities["tools"]:
            checks.append(await _test_tools(target))
        if capabilities["json"]:
            checks.append(await _test_json(target))
        if capabilities["vision"]:
            checks.append(await _test_vision(target))
        if capabilities["streaming"]:
            checks.append(await _test_streaming(target))
        return _result(target, checks, started)
    except ProviderError as exc:
        checks.append(
            {
                "name": "text",
                "ok": False,
                "message": str(exc),
                "retryable": exc.retryable,
            }
        )
        return _result(target, checks, started)
    except Exception as exc:  # noqa: BLE001 - 能力测试需转成结果
        checks.append(
            {
                "name": "text",
                "ok": False,
                "message": f"{exc.__class__.__name__}: {exc}",
            }
        )
        return _result(target, checks, started)


async def _test_tools(target: ModelTarget) -> dict[str, Any]:
    started = time.perf_counter()
    probe_target = replace(
        target,
        config={**target.config, "toolChoice": "required"},
    )
    try:
        result = await complete(
            probe_target,
            system_prompt="Use the provided tool and do not answer directly.",
            messages=[
                {
                    "role": "user",
                    "content": "Call capability_echo with value 'tool-ok'.",
                }
            ],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "capability_echo",
                        "description": "Echo a value",
                        "parameters": {
                            "type": "object",
                            "properties": {"value": {"type": "string"}},
                            "required": ["value"],
                        },
                    },
                }
            ],
            temperature=0,
            max_tokens=128,
        )
        calls = result.get("toolCalls") or []
        ok = any(
            (item.get("function") or {}).get("name") == "capability_echo"
            for item in calls
        )
        return {
            "name": "tools",
            "ok": ok,
            "message": "Tool Calling 通过" if ok else "未返回预期工具调用",
            "latencyMs": round((time.perf_counter() - started) * 1000),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "name": "tools",
            "ok": False,
            "message": str(exc),
            "latencyMs": round((time.perf_counter() - started) * 1000),
        }


async def _test_json(target: ModelTarget) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = await complete(
            target,
            system_prompt="Return only valid JSON.",
            messages=[
                {
                    "role": "user",
                    "content": 'Return {"ok": true, "value": 1} as JSON.',
                }
            ],
            tools=None,
            temperature=0,
            max_tokens=80,
            response_format={"type": "json_object"},
        )
        parsed = json.loads(_strip_code_fence(result["content"]))
        ok = isinstance(parsed, dict)
        return {
            "name": "json",
            "ok": ok,
            "message": "JSON 输出通过" if ok else "JSON 顶层不是对象",
            "latencyMs": round((time.perf_counter() - started) * 1000),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "name": "json",
            "ok": False,
            "message": f"JSON 输出失败：{exc}",
            "latencyMs": round((time.perf_counter() - started) * 1000),
        }


async def _test_vision(target: ModelTarget) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = await complete(
            target,
            system_prompt="Describe images briefly.",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Describe the dominant color."},
                        {
                            "type": "image_url",
                            "image_url": {"url": PIXEL_PNG},
                        },
                    ],
                }
            ],
            tools=None,
            temperature=0,
            max_tokens=32,
        )
        ok = bool(result["content"].strip())
        return {
            "name": "vision",
            "ok": ok,
            "message": "图片理解通过" if ok else "图片理解返回空内容",
            "latencyMs": round((time.perf_counter() - started) * 1000),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "name": "vision",
            "ok": False,
            "message": f"图片理解失败：{exc}",
            "latencyMs": round((time.perf_counter() - started) * 1000),
        }


async def _test_streaming(target: ModelTarget) -> dict[str, Any]:
    started = time.perf_counter()
    text = ""
    try:
        async for event in stream_chat(
            target,
            system_prompt="Reply briefly.",
            messages=[{"role": "user", "content": "Count from 1 to 3."}],
            temperature=0,
            max_tokens=32,
        ):
            if event.get("type") == "delta":
                text += str(event.get("text") or "")
                if text:
                    break
        return {
            "name": "streaming",
            "ok": bool(text),
            "message": "流式输出通过" if text else "未收到流式增量",
            "latencyMs": round((time.perf_counter() - started) * 1000),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "name": "streaming",
            "ok": False,
            "message": f"流式输出失败：{exc}",
            "latencyMs": round((time.perf_counter() - started) * 1000),
        }


def _strip_code_fence(value: str) -> str:
    text = value.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


def _result(
    target: ModelTarget, checks: list[dict[str, Any]], started: float
) -> dict[str, Any]:
    ok = bool(checks) and all(item["ok"] for item in checks)
    failures = [f"{item['name']}：{item['message']}" for item in checks if not item["ok"]]
    return {
        "ok": ok,
        "status": "可用" if ok else "异常",
        "healthStatus": "healthy" if ok else "down",
        "latencyMs": round((time.perf_counter() - started) * 1000),
        "message": (
            "模型基础与声明能力全部通过"
            if ok
            else "；".join(failures) or "能力测试失败"
        ),
        "models": [target.model_key],
        "provider": target.provider,
        "checks": checks,
    }
