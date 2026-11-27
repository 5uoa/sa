"""模型 / MCP 连通性探测：真实发起网络或命令探测"""
import asyncio
import json
import os
import shlex
import shutil
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from settings import settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def expand_mcp_endpoint(value: str) -> str:
    """展开 MCP 端点中的项目运行时占位符，避免写入机器绝对路径。"""
    replacements = {
        "${PROJECT_ROOT}": shlex.quote(str(PROJECT_ROOT)),
        "${SITE_DIR}": shlex.quote(str(PROJECT_ROOT / "site")),
        "${FRONT_DIR}": shlex.quote(str(PROJECT_ROOT / "front-site")),
        "${PYTHON}": shlex.quote(sys.executable),
        "${NODE}": shlex.quote(shutil.which("node") or "node"),
        "${SAFARIDRIVER}": shlex.quote(
            "/System/Cryptexes/App/usr/bin/safaridriver"
        ),
    }
    expanded = value
    for placeholder, replacement in replacements.items():
        expanded = expanded.replace(placeholder, replacement)
    return os.path.expandvars(expanded)


def _headers(endpoint: str, api_key: str) -> dict[str, str]:
    host = urlsplit(endpoint).netloc.lower()
    if "anthropic" in host:
        return {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    return {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}


def _model_ids(payload: object) -> list[str]:
    if not isinstance(payload, dict):
        return []
    ids: list[str] = []
    for item in payload.get("data") or payload.get("models") or []:
        if isinstance(item, dict):
            value = item.get("id") or item.get("name")
            if value:
                ids.append(str(value))
    return ids


def _chat_url(endpoint: str) -> tuple[str, bool]:
    url = endpoint.strip().rstrip("/")
    path = urlsplit(url).path
    is_anthropic = "anthropic" in urlsplit(url).netloc.lower()
    if is_anthropic:
        if path.endswith("/messages"):
            return url, True
        return f"{url}/v1/messages" if not path.endswith("/v1") else f"{url}/messages", True
    if path.endswith("/chat/completions"):
        return url, False
    return f"{url}/chat/completions", False


async def probe(endpoint: str, api_key: str, model_key: str = "") -> dict:
    """真实调用一次最小 completion，确认地址、密钥和目标模型均可用。"""
    started = time.perf_counter()
    model = model_key.strip()
    if not model:
        return {
            "ok": False,
            "status": "异常",
            "latencyMs": 0,
            "message": "请填写供应商模型标识。",
            "models": [],
        }
    url, is_anthropic = _chat_url(endpoint)
    if is_anthropic:
        payload = {
            "model": model,
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "Reply with ok."}],
        }
    else:
        payload = {
            "model": model,
            "max_tokens": 1,
            "temperature": 0,
            "messages": [{"role": "user", "content": "Reply with ok."}],
        }
    try:
        async with httpx.AsyncClient(timeout=settings.model_probe_timeout) as client:
            response = await client.post(url, headers=_headers(endpoint, api_key), json=payload)
    except Exception as exc:  # noqa: BLE001 - 网络异常需转为测试结果
        return {
            "ok": False,
            "status": "异常",
            "latencyMs": round((time.perf_counter() - started) * 1000),
            "message": f"连接失败：{exc.__class__.__name__}",
            "models": [],
        }

    latency = round((time.perf_counter() - started) * 1000)
    if response.status_code >= 400:
        return {
            "ok": False,
            "status": "异常",
            "latencyMs": latency,
            "message": f"HTTP {response.status_code}：{response.text[:200]}",
            "models": [],
        }
    try:
        response_payload = response.json()
    except ValueError:
        response_payload = {}
    returned_model = (
        str(response_payload.get("model") or model)
        if isinstance(response_payload, dict)
        else model
    )
    return {
        "ok": True,
        "status": "可用",
        "latencyMs": latency,
        "message": f"模型「{returned_model}」调用成功（{latency} ms）",
        "models": [returned_model],
    }


async def chat(
    endpoint: str,
    api_key: str,
    model_key: str,
    system_prompt: str,
    messages: list[dict[str, object]],
    max_tokens: int = 1200,
) -> dict:
    """调用专家所选模型并返回纯文本回复。"""
    started = time.perf_counter()
    if not model_key.strip():
        return {
            "ok": False,
            "content": "",
            "latencyMs": 0,
            "model": "",
            "message": "专家所选模型未配置供应商模型标识。",
            "inputTokens": 0,
            "outputTokens": 0,
        }
    url, is_anthropic = _chat_url(endpoint)
    clean_messages: list[dict[str, object]] = []
    for item in messages[-20:]:
        if item.get("role") not in {"user", "assistant"}:
            continue
        content = item.get("content")
        if isinstance(content, str):
            content = content[:12000]
            if not content.strip():
                continue
        elif not isinstance(content, list) or not content:
            continue
        clean_messages.append({"role": item["role"], "content": content})
    if is_anthropic:
        payload = {
            "model": model_key,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": clean_messages,
        }
    else:
        payload = {
            "model": model_key,
            "max_tokens": max_tokens,
            "temperature": 0.7,
            "messages": [{"role": "system", "content": system_prompt}, *clean_messages],
        }
        if "deepseek" in model_key.lower():
            payload["thinking"] = {"type": "disabled"}
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(url, headers=_headers(endpoint, api_key), json=payload)
    except Exception as exc:  # noqa: BLE001 - 返回可读外部服务错误
        return {
            "ok": False,
            "content": "",
            "latencyMs": round((time.perf_counter() - started) * 1000),
            "model": model_key,
            "message": f"模型连接失败：{exc.__class__.__name__}",
            "inputTokens": 0,
            "outputTokens": 0,
        }
    latency = round((time.perf_counter() - started) * 1000)
    if response.status_code >= 400:
        return {
            "ok": False,
            "content": "",
            "latencyMs": latency,
            "model": model_key,
            "message": f"模型 HTTP {response.status_code}：{response.text[:180]}",
            "inputTokens": 0,
            "outputTokens": 0,
        }
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    content = ""
    if is_anthropic:
        content = "".join(
            str(item.get("text") or "")
            for item in (payload.get("content") or [])
            if isinstance(item, dict)
        )
    else:
        choices = payload.get("choices") or []
        if choices and isinstance(choices[0], dict):
            content = str((choices[0].get("message") or {}).get("content") or "")
    usage = payload.get("usage") if isinstance(payload, dict) else {}
    return {
        "ok": bool(content.strip()),
        "content": content.strip(),
        "latencyMs": latency,
        "model": str(payload.get("model") or model_key),
        "message": "回复生成成功" if content.strip() else "模型返回了空内容。",
        "inputTokens": int((usage or {}).get("prompt_tokens") or (usage or {}).get("input_tokens") or 0),
        "outputTokens": int((usage or {}).get("completion_tokens") or (usage or {}).get("output_tokens") or 0),
    }


async def probe_http(url: str, config: dict | None = None) -> dict:
    """执行 MCP initialize JSON-RPC 握手。"""
    started = time.perf_counter()
    config = config or {}
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        **(config.get("headers") if isinstance(config.get("headers"), dict) else {}),
    }
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": config.get("protocol_version", "2025-03-26"),
            "capabilities": {},
            "clientInfo": {"name": "xf-admin", "version": "1.0.0"},
        },
    }
    try:
        async with httpx.AsyncClient(timeout=config.get("timeout", settings.model_probe_timeout)) as client:
            response = await client.post(url, headers=headers, json=payload)
    except Exception as exc:  # noqa: BLE001 - 网络异常需转为测试结果
        return {
            "ok": False,
            "status": "异常",
            "latencyMs": round((time.perf_counter() - started) * 1000),
            "message": f"连接失败：{exc.__class__.__name__}",
            "models": [],
        }
    latency = round((time.perf_counter() - started) * 1000)
    if response.status_code >= 400:
        return {
            "ok": False,
            "status": "异常",
            "latencyMs": latency,
            "message": f"MCP HTTP {response.status_code}：{response.text[:180]}",
            "models": [],
        }
    body_text = response.text.strip()
    if body_text.startswith("event:") or "\ndata:" in body_text:
        body_text = next(
            (line[5:].strip() for line in body_text.splitlines() if line.startswith("data:")),
            "",
        )
    try:
        body = json.loads(body_text)
    except ValueError:
        body = {}
    server_info = (body.get("result") or {}).get("serverInfo") if isinstance(body, dict) else None
    ok = isinstance(body, dict) and "result" in body and not body.get("error")
    return {
        "ok": ok,
        "status": "可用" if ok else "异常",
        "latencyMs": latency,
        "message": (
            f"MCP 握手成功（{latency} ms，{server_info.get('name', 'unknown')}）"
            if ok
            else f"MCP 握手失败（{latency} ms）：{body_text[:180]}"
        ),
        "models": [],
    }


async def probe_command(command: str, config: dict | None = None) -> dict:
    """启动 stdio MCP，执行 initialize 握手后立即终止。"""
    started = time.perf_counter()
    config = config or {}
    raw = expand_mcp_endpoint(command).strip()
    if raw.lower().startswith("stdio:"):
        raw = raw[6:].strip()
    args = shlex.split(raw)
    if not args:
        return {
            "ok": False,
            "status": "异常",
            "latencyMs": 0,
            "message": "MCP 启动命令为空。",
            "models": [],
        }
    binary = shutil.which(args[0])
    if not binary:
        return {
            "ok": False,
            "status": "异常",
            "latencyMs": 0,
            "message": f"运行环境未找到命令：{args[0]}",
            "models": [],
        }
    args[0] = binary
    env = {**os.environ, **(config.get("env") if isinstance(config.get("env"), dict) else {})}
    cwd = config.get("cwd") or None
    process = None
    try:
        process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
        )
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": config.get("protocol_version", "2025-03-26"),
                "capabilities": {},
                "clientInfo": {"name": "xf-admin", "version": "1.0.0"},
            },
        }
        process.stdin.write((json.dumps(request) + "\n").encode("utf-8"))
        await process.stdin.drain()
        line = await asyncio.wait_for(
            process.stdout.readline(), timeout=float(config.get("timeout", 10))
        )
        body = json.loads(line.decode("utf-8"))
        server_info = (body.get("result") or {}).get("serverInfo") or {}
        latency = round((time.perf_counter() - started) * 1000)
        return {
            "ok": "result" in body and not body.get("error"),
            "status": "可用" if "result" in body and not body.get("error") else "异常",
            "latencyMs": latency,
            "message": f"MCP stdio 握手成功（{latency} ms，{server_info.get('name', 'unknown')}）",
            "models": [],
        }
    except Exception as exc:  # noqa: BLE001 - 外部进程错误需转为测试结果
        latency = round((time.perf_counter() - started) * 1000)
        return {
            "ok": False,
            "status": "异常",
            "latencyMs": latency,
            "message": f"MCP stdio 握手失败：{exc.__class__.__name__}",
            "models": [],
        }
    finally:
        if process is not None and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=2)
            except asyncio.TimeoutError:
                process.kill()


async def probe_mcp(endpoint: str, config: dict | None = None) -> dict:
    expanded = expand_mcp_endpoint(endpoint)
    if expanded.startswith(("http://", "https://")):
        return await probe_http(expanded, config)
    return await probe_command(expanded, config)


async def validate_skill(description: str, config: dict | None = None) -> dict:
    """加载并实际执行 SKILL handler，同时校验输入输出 Schema。"""
    started = time.perf_counter()
    config = config or {}
    errors: list[str] = []
    if not description.strip():
        errors.append("缺少描述")
    instructions = str(config.get("instructions") or "").strip()
    if not instructions:
        errors.append("缺少执行指令")
    requires_tools = config.get("requires_tools", [])
    if requires_tools and not isinstance(requires_tools, list):
        errors.append("requires_tools 必须是数组")
    handler = str(config.get("handler") or "").strip()
    input_schema = config.get("input_schema")
    output_schema = config.get("output_schema")
    sample_output: Any = None
    if not isinstance(input_schema, dict) or not input_schema:
        errors.append("缺少 input_schema")
    if not isinstance(output_schema, dict) or not output_schema:
        errors.append("缺少 output_schema")
    if not handler:
        errors.append("缺少可执行 handler")
    else:
        try:
            from experts.skill_runtime import load_handler, validate_value
            import inspect

            function = load_handler(handler)
            test_input = config.get("test_input") or {}
            if not isinstance(test_input, dict):
                raise ValueError("test_input 必须是对象")
            input_errors = (
                validate_value(test_input, input_schema)
                if isinstance(input_schema, dict)
                else []
            )
            if input_errors:
                raise ValueError("；".join(input_errors))
            sample_output = function(test_input)
            if inspect.isawaitable(sample_output):
                sample_output = await sample_output
            output_errors = (
                validate_value(sample_output, output_schema, "output")
                if isinstance(output_schema, dict)
                else []
            )
            if output_errors:
                raise ValueError("；".join(output_errors))
        except Exception as exc:  # noqa: BLE001 - 返回可读校验结果
            errors.append(f"handler 执行失败：{exc}")
    latency = round((time.perf_counter() - started) * 1000)
    ok = not errors
    return {
        "ok": ok,
        "status": "可用" if ok else "异常",
        "latencyMs": latency,
        "message": "SKILL handler 执行与输入输出校验通过" if ok else "；".join(errors),
        "models": [],
        "sampleOutput": jsonable_output(sample_output),
    }


def jsonable_output(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool, list, dict)):
        return value
    return str(value)
