"""专家 Agent：模型推理、MCP/SKILL 工具发现、权限确认与工具循环。"""
import asyncio
import copy
import hashlib
import json
import os
import re
import shlex
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import (
    create_mcp_http_client,
    streamable_http_client,
)

from admin.model_probe import expand_mcp_endpoint
from chief.web_fetch import fetch_webpage
from chief.web_search import search_web
from experts.skill_runtime import (
    SkillBinding,
    discover_skill_tools,
    encode_skill_result,
    execute_skill,
)
from llm.adapters import ModelTarget, ProviderError, complete
from llm.capabilities import normalize_capabilities, normalize_provider
from llm.context import fit_messages_to_budget

SENSITIVE_KEY_PATTERN = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|authorization|cookie|"
    r"credential|private[_-]?key|session)",
    re.IGNORECASE,
)
SECRET_PATTERNS = [
    re.compile(r"(?i)(bearer\s+)[a-z0-9._~+/=-]+"),
    re.compile(r"\bsk-[a-zA-Z0-9_-]{8,}\b"),
    re.compile(r"(://[^:/@\s]+:)([^@\s]+)(@)"),
    re.compile(
        r"(?i)\b(password|passwd|token|api[_-]?key|authorization)"
        r"(\s*[:=]\s*)([^\s,;]+)"
    ),
]


@dataclass
class ToolBinding:
    alias: str
    kind: str
    mcp_id: str
    mcp_name: str
    original_name: str
    description: str
    parameters: dict[str, Any]
    read_only: bool
    risk: str
    requires_confirmation: bool
    timeout_seconds: float
    session: ClientSession | None = None
    skill: SkillBinding | None = None


def _safe_slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", value).strip("_")[:48] or "tool"


def _mask_secret(value: Any) -> str:
    raw = str(value)
    if len(raw) <= 8:
        return "*" * len(raw)
    return f"{raw[:4]}****{raw[-4:]}"


def redact_text(value: str) -> str:
    text = value
    text = SECRET_PATTERNS[0].sub(r"\1********", text)
    text = SECRET_PATTERNS[1].sub("sk-********", text)
    text = SECRET_PATTERNS[2].sub(r"\1********\3", text)
    text = SECRET_PATTERNS[3].sub(r"\1\2********", text)
    return text


def redact_sensitive_data(value: Any, key: str = "") -> Any:
    if SENSITIVE_KEY_PATTERN.search(key):
        return _mask_secret(value)
    if isinstance(value, dict):
        return {
            str(item_key): redact_sensitive_data(item, str(item_key))
            for item_key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive_data(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def _tool_result_text(result: Any) -> str:
    parts: list[str] = []
    for item in getattr(result, "content", []) or []:
        text_value = getattr(item, "text", None)
        if text_value:
            parts.append(str(text_value))
            continue
        if hasattr(item, "model_dump"):
            parts.append(json.dumps(item.model_dump(), ensure_ascii=False, default=str))
        else:
            parts.append(str(item))
    if not parts and getattr(result, "structured_content", None) is not None:
        parts.append(
            json.dumps(result.structured_content, ensure_ascii=False, default=str)
        )
    content = "\n".join(parts) or "(empty result)"
    return content[:20000]


def _policy_for(
    policies: dict[str, str], resource_id: str, tool_name: str
) -> str:
    return policies.get(f"{resource_id}:{tool_name}", "default")


async def discover_mcp_tools(
    mcp_items: list[dict[str, Any]],
    *,
    allow_write_tools: bool = False,
    timeout_seconds: int = 20,
    tool_policies: dict[str, str] | None = None,
) -> tuple[AsyncExitStack, list[ToolBinding], list[str]]:
    policies = tool_policies or {}
    stack = AsyncExitStack()
    bindings: list[ToolBinding] = []
    warnings: list[str] = []
    for mcp_item in mcp_items:
        endpoint = expand_mcp_endpoint(str(mcp_item.get("endpoint") or "")).strip()
        if not endpoint:
            warnings.append(f"{mcp_item.get('name') or 'MCP'} 未配置端点")
            continue
        config = mcp_item.get("config")
        config = config if isinstance(config, dict) else {}
        try:
            if endpoint.startswith(("http://", "https://")):
                client = await stack.enter_async_context(
                    create_mcp_http_client(
                        headers=config.get("headers")
                        if isinstance(config.get("headers"), dict)
                        else None
                    )
                )
                read_stream, write_stream = await stack.enter_async_context(
                    streamable_http_client(endpoint, http_client=client)
                )
            else:
                raw = (
                    endpoint[6:].strip()
                    if endpoint.lower().startswith("stdio:")
                    else endpoint
                )
                args = shlex.split(raw)
                if not args:
                    raise ValueError("启动命令为空")
                env = {
                    **os.environ,
                    **(
                        config.get("env")
                        if isinstance(config.get("env"), dict)
                        else {}
                    ),
                }
                params = StdioServerParameters(
                    command=args[0],
                    args=args[1:],
                    env=env,
                    cwd=config.get("cwd") or None,
                )
                read_stream, write_stream = await stack.enter_async_context(
                    stdio_client(params)
                )
            session = await stack.enter_async_context(
                ClientSession(
                    read_stream,
                    write_stream,
                    read_timeout_seconds=timeout_seconds,
                )
            )
            await session.initialize()
            listed = await session.list_tools()
            mcp_name = str(mcp_item.get("name") or mcp_item.get("id") or "MCP")
            mcp_id = str(mcp_item.get("id") or mcp_name)
            prefix = hashlib.sha256(mcp_id.encode("utf-8")).hexdigest()[:6]
            configured_read_only = config.get("read_only_tools")
            for tool in listed.tools:
                annotations = getattr(tool, "annotations", None)
                read_only = bool(
                    getattr(annotations, "read_only_hint", False)
                    if annotations is not None
                    else False
                )
                if (
                    not read_only
                    and isinstance(configured_read_only, list)
                    and tool.name in configured_read_only
                ):
                    read_only = True
                destructive = bool(
                    getattr(annotations, "destructive_hint", False)
                    if annotations is not None
                    else False
                )
                policy = _policy_for(policies, mcp_id, tool.name)
                if policy == "deny":
                    warnings.append(f"{mcp_name}/{tool.name} 已被工具级策略禁用")
                    continue
                if not read_only and not allow_write_tools and policy != "allow":
                    warnings.append(
                        f"{mcp_name}/{tool.name} 是写入或未声明只读的工具，已跳过"
                    )
                    continue
                requires_confirmation = policy == "confirm" or (
                    not read_only and policy != "allow"
                )
                bindings.append(
                    ToolBinding(
                        alias=f"mcp_{prefix}_{_safe_slug(tool.name)}"[:64],
                        kind="mcp",
                        mcp_id=mcp_id,
                        mcp_name=mcp_name,
                        original_name=tool.name,
                        description=str(tool.description or ""),
                        parameters=tool.input_schema
                        or {"type": "object", "properties": {}},
                        read_only=read_only,
                        risk="destructive" if destructive else (
                            "read" if read_only else "write"
                        ),
                        requires_confirmation=requires_confirmation,
                        timeout_seconds=float(timeout_seconds),
                        session=session,
                    )
                )
        except Exception as exc:  # noqa: BLE001 - 单个 MCP 失败不应阻断专家
            warnings.append(
                f"{mcp_item.get('name') or 'MCP'} 加载失败："
                f"{exc.__class__.__name__}: {exc}"
            )
    return stack, bindings, warnings


def _skill_bindings(
    skill_items: list[dict[str, Any]],
    tool_policies: dict[str, str],
) -> tuple[list[ToolBinding], list[str]]:
    discovered, warnings = discover_skill_tools(skill_items)
    bindings: list[ToolBinding] = []
    for item in discovered:
        policy = _policy_for(tool_policies, item.skill_id, item.name)
        if policy == "deny":
            warnings.append(f"SKILL/{item.name} 已被工具级策略禁用")
            continue
        bindings.append(
            ToolBinding(
                alias=item.alias,
                kind="skill",
                mcp_id="",
                mcp_name="SKILL",
                original_name=item.name,
                description=item.description,
                parameters=item.parameters,
                read_only=True,
                risk="skill",
                requires_confirmation=policy == "confirm",
                timeout_seconds=item.timeout_seconds,
                skill=item,
            )
        )
    return bindings, warnings


def _builtin_bindings(
    tool_policies: dict[str, str], timeout_seconds: float
) -> list[ToolBinding]:
    bindings: list[ToolBinding] = []
    search_policy = _policy_for(tool_policies, "builtin", "web_search")
    if search_policy != "deny":
        bindings.append(
            ToolBinding(
                alias="web_search",
                kind="builtin",
                mcp_id="builtin",
                mcp_name="内置联网",
                original_name="search_web",
                description=(
                    "联网搜索公开网页。适合查询最新信息、新闻、价格、"
                    "政策、版本发布和需要来源链接的问题。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "简洁的搜索关键词或问题",
                        },
                        "count": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 10,
                            "description": "返回结果数量，默认 5",
                        },
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
                read_only=True,
                risk="read",
                requires_confirmation=search_policy == "confirm",
                timeout_seconds=timeout_seconds,
            )
        )
    fetch_policy = _policy_for(tool_policies, "builtin", "web_fetch")
    if fetch_policy != "deny":
        bindings.append(
            ToolBinding(
                alias="web_fetch",
                kind="builtin",
                mcp_id="builtin",
                mcp_name="内置网页",
                original_name="fetch_webpage",
                description=(
                    "抓取一个公开 HTTP/HTTPS 网页并提取正文。"
                    "适合用户提供网址后读取页面内容；不允许访问内网地址。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "完整的公开 HTTP/HTTPS 网址",
                        },
                        "maxChars": {
                            "type": "integer",
                            "minimum": 500,
                            "maximum": 30000,
                            "description": "正文最大字符数，默认 12000",
                        },
                    },
                    "required": ["url"],
                    "additionalProperties": False,
                },
                read_only=True,
                risk="read",
                requires_confirmation=fetch_policy == "confirm",
                timeout_seconds=timeout_seconds,
            )
        )
    return bindings


def _openai_tool_schema(binding: ToolBinding) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": binding.alias,
            "description": f"[{binding.mcp_name}] {binding.description}".strip(),
            "parameters": binding.parameters,
        },
    }


def _public_calls(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "callId": item["callId"],
            "kind": item["kind"],
            "mcp": item["mcp"],
            "tool": item["tool"],
            "risk": item["risk"],
            "requiresConfirmation": item["requiresConfirmation"],
            "arguments": redact_sensitive_data(item["arguments"]),
        }
        for item in calls
    ]


async def _execute_binding(
    binding: ToolBinding,
    arguments: dict[str, Any],
    fallback_timeout: float,
) -> tuple[str, bool]:
    try:
        if binding.kind == "builtin":
            if binding.original_name == "fetch_webpage":
                result = await asyncio.wait_for(
                    fetch_webpage(
                        str(arguments.get("url") or ""),
                        max_chars=int(arguments.get("maxChars") or 12_000),
                    ),
                    timeout=binding.timeout_seconds or fallback_timeout,
                )
            elif binding.original_name == "search_web":
                query = str(arguments.get("query") or "").strip()
                result = await asyncio.wait_for(
                    search_web(
                        query,
                        original_question=query,
                        preferred_model={},
                        preferred_key="",
                        count=int(arguments.get("count") or 5),
                    ),
                    timeout=binding.timeout_seconds or fallback_timeout,
                )
            else:
                return f"未知内置工具：{binding.original_name}", True
            return json.dumps(result, ensure_ascii=False)[:20000], not bool(result.get("ok"))
        if binding.kind == "skill":
            if not binding.skill:
                return "SKILL 绑定无效", True
            result = await asyncio.wait_for(
                execute_skill(binding.skill, arguments),
                timeout=binding.timeout_seconds or fallback_timeout,
            )
            return encode_skill_result(result)[:20000], False
        if not binding.session:
            return "MCP 会话不存在", True
        tool_result = await asyncio.wait_for(
            binding.session.call_tool(binding.original_name, arguments),
            timeout=binding.timeout_seconds or fallback_timeout,
        )
        return _tool_result_text(tool_result), bool(
            getattr(tool_result, "is_error", False)
        )
    except Exception as exc:  # noqa: BLE001 - 工具失败回填给模型
        return (
            f"工具执行失败：{exc.__class__.__name__}: {exc}。"
            "请使用已有信息给出降级方案。",
            True,
        )


async def run_expert(
    *,
    endpoint: str,
    api_key: str,
    model_key: str,
    provider: str = "",
    model_capabilities: dict[str, Any] | None = None,
    model_config: dict[str, Any] | None = None,
    system_prompt: str,
    messages: list[dict[str, Any]],
    mcp_items: list[dict[str, Any]],
    skill_items: list[dict[str, Any]] | None = None,
    max_tool_steps: int = 6,
    allow_write_tools: bool = False,
    tool_timeout_seconds: int = 20,
    tool_policies: dict[str, str] | None = None,
    temperature: float = 0.7,
    max_output_tokens: int = 2000,
    context_budget_tokens: int | None = None,
    response_format: dict[str, Any] | None = None,
    resume_state: dict[str, Any] | None = None,
    approvals: dict[str, bool] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    if not model_key.strip():
        return {
            "ok": False,
            "content": "",
            "message": "专家所选模型未配置供应商模型标识。",
            "toolTrace": [],
            "warnings": [],
            "availableTools": 0,
            "usedTools": 0,
            "latencyMs": 0,
            "inputTokens": 0,
            "outputTokens": 0,
        }
    effective_capabilities = model_capabilities or {
        "tools": True,
        "vision": True,
        "json": True,
        "streaming": True,
    }
    target = ModelTarget(
        id="",
        name=model_key,
        provider=normalize_provider(provider, endpoint),
        endpoint=endpoint,
        model_key=model_key,
        api_key=api_key,
        capabilities=normalize_capabilities(effective_capabilities),
        config=model_config or {},
    )
    max_tool_steps = max(0, min(12, int(max_tool_steps)))
    tool_timeout_seconds = max(0.05, float(tool_timeout_seconds))
    max_output_tokens = max(
        1,
        min(int(max_output_tokens), int(target.capabilities["maxOutputTokens"])),
    )
    temperature = max(0.0, min(2.0, float(temperature)))
    policies = tool_policies or {}
    stack, bindings, warnings = await discover_mcp_tools(
        mcp_items,
        allow_write_tools=allow_write_tools,
        timeout_seconds=tool_timeout_seconds,
        tool_policies=policies,
    )
    skill_bindings, skill_warnings = _skill_bindings(skill_items or [], policies)
    bindings.extend(skill_bindings)
    warnings.extend(skill_warnings)
    if target.capabilities["tools"]:
        bindings = [
            *_builtin_bindings(policies, tool_timeout_seconds),
            *bindings,
        ]
    tool_map = {binding.alias: binding for binding in bindings}
    tools = [_openai_tool_schema(binding) for binding in bindings]
    context_stats: dict[str, Any] = {}
    if resume_state:
        conversation = copy.deepcopy(resume_state["conversation"])
        step = int(resume_state.get("step") or 0)
        traces = copy.deepcopy(resume_state.get("traces") or [])
        warnings = [*resume_state.get("warnings", []), *warnings]
        input_tokens = int(resume_state.get("inputTokens") or 0)
        output_tokens = int(resume_state.get("outputTokens") or 0)
        pending_calls = resume_state.get("pendingCalls") or []
    else:
        conversation, context_stats = fit_messages_to_budget(
            system_prompt,
            messages,
            context_window=int(target.capabilities["contextWindow"]),
            max_output_tokens=max_output_tokens,
            context_budget_tokens=context_budget_tokens,
        )
        if context_stats["truncated"]:
            warnings.append(
                f"历史上下文已裁剪 {context_stats['droppedMessages']} 条消息"
            )
        step = 0
        traces = []
        input_tokens = 0
        output_tokens = 0
        pending_calls = []

    def result_payload(
        *,
        ok: bool,
        content: str = "",
        message: str,
        state: dict[str, Any] | None = None,
        requires_approval: bool = False,
        pending: list[dict[str, Any]] | None = None,
        retryable: bool = False,
    ) -> dict[str, Any]:
        return {
            "ok": ok,
            "content": content,
            "message": message,
            "toolTrace": traces,
            "warnings": [redact_text(str(item)) for item in warnings],
            "availableTools": len(bindings),
            "usedTools": len(traces),
            "latencyMs": round((time.perf_counter() - started) * 1000),
            "inputTokens": input_tokens,
            "outputTokens": output_tokens,
            "provider": target.provider,
            "model": target.model_key,
            "contextBudget": context_stats,
            "retryable": retryable,
            "requiresApproval": requires_approval,
            "pendingApproval": {"calls": _public_calls(pending or [])}
            if requires_approval
            else None,
            "_state": state,
        }

    try:
        async def execute_calls(calls: list[dict[str, Any]]) -> None:
            for call in calls:
                call_id = str(call.get("callId") or "")
                alias = str(call.get("alias") or "")
                binding = tool_map.get(alias)
                arguments = (
                    call.get("arguments") if isinstance(call.get("arguments"), dict) else {}
                )
                started_tool = time.perf_counter()
                approved = (
                    approvals.get(call_id, not bool(call.get("requiresConfirmation")))
                    if approvals is not None
                    else True
                )
                if call.get("argumentError"):
                    result_text = f"工具参数不是合法 JSON 对象：{alias}"
                    is_error = True
                elif not binding:
                    result_text = f"工具不存在或未授权：{alias}"
                    is_error = True
                elif not approved:
                    result_text = "用户拒绝执行该工具调用。"
                    is_error = True
                else:
                    result_text, is_error = await _execute_binding(
                        binding, arguments, tool_timeout_seconds
                    )
                trace = {
                    "step": step + 1,
                    "kind": binding.kind if binding else call.get("kind", "mcp"),
                    "alias": alias,
                    "mcp": binding.mcp_name if binding else call.get("mcp", ""),
                    "tool": (
                        binding.original_name if binding else call.get("tool", alias)
                    ),
                    "risk": binding.risk if binding else call.get("risk", "unknown"),
                    "arguments": redact_sensitive_data(arguments),
                    "ok": not is_error,
                    "confirmed": bool(
                        call.get("requiresConfirmation") and approved
                    ),
                    "resultPreview": redact_text(result_text[:3000]),
                    "durationMs": round(
                        (time.perf_counter() - started_tool) * 1000
                    ),
                }
                traces.append(trace)
                if is_error:
                    warnings.append(
                        f"{trace['mcp']}/{trace['tool']} 执行失败："
                        f"{redact_text(result_text[:180])}"
                    )
                conversation.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": alias,
                        "content": result_text[:20000],
                    }
                )

        if pending_calls:
            await execute_calls(pending_calls)
            pending_calls = []
            step += 1
            approvals = None

        while step < max_tool_steps + 1:
                system_message = conversation[0]
                fitted, request_context = fit_messages_to_budget(
                    str(system_message.get("content") or ""),
                    conversation[1:],
                    context_window=int(target.capabilities["contextWindow"]),
                    max_output_tokens=max_output_tokens,
                    context_budget_tokens=context_budget_tokens,
                )
                context_stats.update(request_context)
                request_messages = fitted[1:]
                if tools and step >= max_tool_steps:
                    request_messages = [
                        *request_messages,
                        {
                            "role": "user",
                            "content": (
                                "工具调用预算已用完。请立即停止调用工具，"
                                "基于已经获得的工具结果和上下文输出最终成果。"
                                "不要再输出 DSML、tool_calls 或任何工具调用标记。"
                            ),
                        },
                    ]
                model_result = await complete(
                    target,
                    system_prompt=str(fitted[0].get("content") or ""),
                    messages=request_messages,
                    tools=tools if tools and step < max_tool_steps else None,
                    temperature=temperature,
                    max_tokens=max_output_tokens,
                    response_format=response_format,
                )
                input_tokens += int(model_result.get("inputTokens") or 0)
                output_tokens += int(model_result.get("outputTokens") or 0)
                tool_calls = model_result.get("toolCalls") or []
                content = str(model_result.get("content") or "")
                if not tool_calls:
                    return result_payload(
                        ok=bool(content.strip()),
                        content=content.strip(),
                        message=(
                            "专家执行完成"
                            if content.strip()
                            else "专家返回空内容"
                        ),
                    )
                conversation.append(
                    {
                        "role": "assistant",
                        "content": content,
                        "tool_calls": tool_calls,
                    }
                )
                calls: list[dict[str, Any]] = []
                for call in tool_calls:
                    call_id = str(call.get("id") or "")
                    function = call.get("function") or {}
                    alias = str(function.get("name") or "")
                    binding = tool_map.get(alias)
                    try:
                        arguments = json.loads(function.get("arguments") or "{}")
                        if not isinstance(arguments, dict):
                            raise ValueError("参数必须是 JSON 对象")
                        argument_error = False
                    except ValueError:
                        arguments = {}
                        argument_error = True
                    calls.append(
                        {
                            "callId": call_id,
                            "alias": alias,
                            "kind": binding.kind if binding else "mcp",
                            "mcp": binding.mcp_name if binding else "",
                            "tool": binding.original_name if binding else alias,
                            "risk": binding.risk if binding else "unknown",
                            "arguments": arguments,
                            "argumentError": argument_error,
                            "requiresConfirmation": bool(
                                binding and binding.requires_confirmation
                            ),
                        }
                    )
                if approvals is None and any(
                    call["requiresConfirmation"] for call in calls
                ):
                    state = {
                        "conversation": conversation,
                        "step": step,
                        "traces": traces,
                        "warnings": warnings,
                        "inputTokens": input_tokens,
                        "outputTokens": output_tokens,
                        "pendingCalls": calls,
                    }
                    return result_payload(
                        ok=False,
                        message="工具调用需要人工确认后才能继续。",
                        state=state,
                        requires_approval=True,
                        pending=calls,
                    )
                await execute_calls(calls)
                step += 1
        warnings.append(f"工具调用达到最大步数 {max_tool_steps}")
        return result_payload(
            ok=False,
            message="工具调用达到最大步数，未生成最终回答。",
        )
    except ProviderError as exc:
        return result_payload(
            ok=False,
            message=redact_text(str(exc)),
            retryable=exc.retryable,
        )
    except Exception as exc:  # noqa: BLE001 - 运行时错误返回可读降级信息
        return result_payload(
            ok=False,
            message=f"专家运行失败：{exc.__class__.__name__}: {exc}",
        )
    finally:
        await stack.aclose()
