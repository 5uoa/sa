"""专家运行时测试：使用本地 MCP 桩和合成模型响应，不访问外部模型。"""
import asyncio
import json
import shlex
import sys
from pathlib import Path
from typing import Any, Callable

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SITE_ROOT = REPO_ROOT / "site"
if str(SITE_ROOT) not in sys.path:
    sys.path.insert(0, str(SITE_ROOT))

from experts import runtime  # noqa: E402
from llm import adapters as llm_adapters  # noqa: E402


def _mcp_item() -> dict[str, Any]:
    command = " ".join(
        [
            shlex.quote(sys.executable),
            shlex.quote(str(SITE_ROOT / "admin" / "mcp_stub.py")),
        ]
    )
    return {
        "id": "runtime-test-mcp",
        "name": "runtime-test",
        "endpoint": f"stdio: {command}",
        "config": {},
    }


def _project_mcp(name: str, script: str) -> dict[str, Any]:
    command = " ".join(
        [
            shlex.quote(sys.executable),
            shlex.quote(str(SITE_ROOT / "admin" / script)),
        ]
    )
    return {
        "id": f"project-{name}",
        "name": name,
        "endpoint": f"stdio: {command}",
        "config": {},
    }


def _install_model(
    monkeypatch: pytest.MonkeyPatch,
    responder: Callable[[dict[str, Any], int], dict[str, Any]],
) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []

    class Response:
        def __init__(self, payload: dict[str, Any]):
            self.status_code = 200
            self.text = json.dumps(payload)
            self._payload = payload

        def json(self) -> dict[str, Any]:
            return self._payload

    class Client:
        def __init__(self, *_: Any, **__: Any):
            pass

        async def __aenter__(self) -> "Client":
            return self

        async def __aexit__(self, *_: Any) -> None:
            return None

        async def post(
            self, _url: str, *, headers: dict[str, str], json: dict[str, Any]
        ) -> Response:
            requests.append(json)
            return Response(responder(json, len(requests) - 1))

    monkeypatch.setattr(llm_adapters.httpx, "AsyncClient", Client)
    return requests


def _install_anthropic_model(
    monkeypatch: pytest.MonkeyPatch,
) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []

    class Response:
        status_code = 200
        text = ""

        def __init__(self, payload: dict[str, Any]):
            self._payload = payload

        def json(self) -> dict[str, Any]:
            return self._payload

    class Client:
        def __init__(self, *_: Any, **__: Any):
            pass

        async def __aenter__(self) -> "Client":
            return self

        async def __aexit__(self, *_: Any) -> None:
            return None

        async def post(
            self, url: str, *, headers: dict[str, str], json: dict[str, Any]
        ) -> Response:
            requests.append({"url": url, "headers": headers, "payload": json})
            if len(requests) == 1:
                return Response(
                    {
                        "model": "claude-test",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "claude-call",
                                "name": next(
                                    item["name"]
                                    for item in json["tools"]
                                    if item["name"].endswith("_echo")
                                ),
                                "input": {"text": "anthropic tool"},
                            }
                        ],
                        "stop_reason": "tool_use",
                        "usage": {"input_tokens": 9, "output_tokens": 2},
                    }
                )
            return Response(
                {
                    "model": "claude-test",
                    "content": [{"type": "text", "text": "Anthropic 工具循环完成。"}],
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 12, "output_tokens": 4},
                }
            )

    monkeypatch.setattr(llm_adapters.httpx, "AsyncClient", Client)
    return requests


def _tool_name(request: dict[str, Any], suffix: str) -> str:
    return next(
        item["function"]["name"]
        for item in request.get("tools", [])
        if item["function"]["name"].endswith(suffix)
    )


def _tool_call(call_id: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(arguments, ensure_ascii=False),
        },
    }


def _completion(
    message: dict[str, Any], prompt_tokens: int = 10, completion_tokens: int = 2
) -> dict[str, Any]:
    return {
        "choices": [{"message": message}],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        },
    }


def test_mcp_discovers_tools_and_blocks_write_by_default():
    async def scenario() -> None:
        stack, tools, warnings = await runtime.discover_mcp_tools(
            [_mcp_item()], timeout_seconds=3
        )
        try:
            assert {tool.original_name for tool in tools} == {"echo", "slow", "fail"}
            assert all(tool.read_only for tool in tools)
            assert any("write_value" in warning for warning in warnings)
        finally:
            await stack.aclose()

        stack, tools, warnings = await runtime.discover_mcp_tools(
            [_mcp_item()], allow_write_tools=True, timeout_seconds=3
        )
        try:
            assert {tool.original_name for tool in tools} == {
                "echo",
                "write_value",
                "slow",
                "fail",
            }
            assert not any("write_value" in warning for warning in warnings)
        finally:
            await stack.aclose()

    asyncio.run(scenario())


def test_expert_calls_read_only_tool_and_returns_trace(
    monkeypatch: pytest.MonkeyPatch,
):
    def responder(request: dict[str, Any], index: int) -> dict[str, Any]:
        if index == 0:
            name = _tool_name(request, "_echo")
            return _completion(
                {
                    "content": "",
                    "tool_calls": [
                        _tool_call(
                            "call-echo",
                            name,
                            {"text": "synthetic value"},
                        )
                    ],
                }
            )
        assert request["messages"][-1]["role"] == "tool"
        assert "ECHO: synthetic value" in request["messages"][-1]["content"]
        return _completion(
            {"content": "已根据工具结果完成。"},
            prompt_tokens=20,
            completion_tokens=3,
        )

    requests = _install_model(monkeypatch, responder)
    result = asyncio.run(
        runtime.run_expert(
            endpoint="http://model.test/v1",
            api_key="test-key",
            model_key="test-model",
            system_prompt="合成系统提示词",
            messages=[{"role": "user", "content": "请执行合成工具测试"}],
            mcp_items=[_mcp_item()],
            max_tool_steps=3,
            allow_write_tools=False,
            tool_timeout_seconds=3,
            temperature=0.2,
            max_output_tokens=123,
            context_budget_tokens=1024,
        )
    )

    assert result["ok"] is True
    assert result["content"] == "已根据工具结果完成。"
    assert result["availableTools"] == 5
    assert result["usedTools"] == 1
    assert result["toolTrace"][0]["tool"] == "echo"
    assert result["toolTrace"][0]["ok"] is True
    assert "ECHO: synthetic value" in result["toolTrace"][0]["resultPreview"]
    assert result["inputTokens"] == 30
    assert result["outputTokens"] == 5
    assert len(requests) == 2
    assert requests[0]["temperature"] == 0.2
    assert requests[0]["max_tokens"] == 123
    assert result["contextBudget"]["budgetTokens"] <= 1024
    assert requests[0]["messages"][0] == {
        "role": "system",
        "content": "合成系统提示词",
    }


def test_expert_can_use_builtin_web_fetch_tool(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[tuple[str, int]] = []

    async def fake_fetch(url: str, *, max_chars: int = 12000) -> dict[str, Any]:
        calls.append((url, max_chars))
        return {
            "ok": True,
            "url": url,
            "finalUrl": url,
            "title": "抓取测试页",
            "text": "页面正文内容",
            "provider": "deepseek",
            "truncated": False,
        }

    monkeypatch.setattr(runtime, "fetch_webpage", fake_fetch)

    def responder(request: dict[str, Any], index: int) -> dict[str, Any]:
        if index == 0:
            name = _tool_name(request, "web_fetch")
            return _completion(
                {
                    "content": "",
                    "tool_calls": [
                        _tool_call(
                            "call-web-fetch",
                            name,
                            {
                                "url": "https://example.com/page",
                                "maxChars": 4000,
                            },
                        )
                    ],
                }
            )
        assert request["messages"][-1]["role"] == "tool"
        assert "页面正文内容" in request["messages"][-1]["content"]
        return _completion({"content": "已读取网页并完成总结。"})

    _install_model(monkeypatch, responder)
    result = asyncio.run(
        runtime.run_expert(
            endpoint="http://model.test/v1",
            api_key="test-key",
            model_key="test-model",
            system_prompt="合成系统提示词",
            messages=[{"role": "user", "content": "请读取网页"}],
            mcp_items=[],
            max_tool_steps=2,
            tool_timeout_seconds=3,
        )
    )

    assert result["ok"] is True
    assert result["content"] == "已读取网页并完成总结。"
    assert result["availableTools"] == 2
    assert result["toolTrace"][0]["kind"] == "builtin"
    assert result["toolTrace"][0]["tool"] == "fetch_webpage"
    assert result["toolTrace"][0]["ok"] is True
    assert calls == [("https://example.com/page", 4000)]


def test_expert_can_use_builtin_web_search_tool(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[tuple[str, int]] = []

    async def fake_search(
        query: str,
        *,
        original_question: str,
        preferred_model: dict[str, Any],
        preferred_key: str,
        count: int = 5,
    ) -> dict[str, Any]:
        calls.append((query, count))
        return {
            "ok": True,
            "query": query,
            "message": "网页搜索完成",
            "results": [
                {
                    "title": "测试结果",
                    "url": "https://example.com/result",
                    "summary": "最新公开信息",
                }
            ],
        }

    monkeypatch.setattr(runtime, "search_web", fake_search)

    def responder(request: dict[str, Any], index: int) -> dict[str, Any]:
        if index == 0:
            name = _tool_name(request, "web_search")
            return _completion(
                {
                    "content": "",
                    "tool_calls": [
                        _tool_call(
                            "call-web-search",
                            name,
                            {"query": "最新公告", "count": 3},
                        )
                    ],
                }
            )
        assert request["messages"][-1]["role"] == "tool"
        assert "测试结果" in request["messages"][-1]["content"]
        return _completion({"content": "已获取最新搜索结果。"})

    _install_model(monkeypatch, responder)
    result = asyncio.run(
        runtime.run_expert(
            endpoint="http://model.test/v1",
            api_key="test-key",
            model_key="test-model",
            system_prompt="合成系统提示词",
            messages=[{"role": "user", "content": "搜索最新公告"}],
            mcp_items=[],
            max_tool_steps=2,
            tool_timeout_seconds=3,
        )
    )

    assert result["ok"] is True
    assert result["availableTools"] == 2
    assert result["toolTrace"][0]["kind"] == "builtin"
    assert result["toolTrace"][0]["tool"] == "search_web"
    assert result["toolTrace"][0]["ok"] is True
    assert calls == [("最新公告", 3)]


def test_expert_calls_write_tool_only_after_explicit_authorization(
    monkeypatch: pytest.MonkeyPatch,
):
    def responder(request: dict[str, Any], index: int) -> dict[str, Any]:
        if index == 0:
            name = _tool_name(request, "_write_value")
            return _completion(
                {
                    "content": "",
                    "tool_calls": [
                        _tool_call(
                            "call-write",
                            name,
                            {"text": "synthetic value"},
                        )
                    ],
                }
            )
        return _completion({"content": "写入工具已按授权执行。"})

    _install_model(monkeypatch, responder)
    approval_result = asyncio.run(
        runtime.run_expert(
            endpoint="http://model.test/v1",
            api_key="test-key",
            model_key="test-model",
            system_prompt="合成系统提示词",
            messages=[{"role": "user", "content": "执行合成写入测试"}],
            mcp_items=[_mcp_item()],
            max_tool_steps=2,
            allow_write_tools=True,
            tool_timeout_seconds=3,
        )
    )

    assert approval_result["requiresApproval"] is True
    assert approval_result["availableTools"] == 6
    assert approval_result["pendingApproval"]["calls"][0]["tool"] == "write_value"
    assert approval_result["toolTrace"] == []

    result = asyncio.run(
        runtime.run_expert(
            endpoint="http://model.test/v1",
            api_key="test-key",
            model_key="test-model",
            system_prompt="合成系统提示词",
            messages=[],
            mcp_items=[_mcp_item()],
            max_tool_steps=2,
            allow_write_tools=True,
            tool_timeout_seconds=3,
            resume_state=approval_result["_state"],
            approvals={"call-write": True},
        )
    )
    assert result["ok"] is True
    assert result["toolTrace"][0]["tool"] == "write_value"
    assert result["toolTrace"][0]["ok"] is True
    assert result["toolTrace"][0]["confirmed"] is True


def test_anthropic_expert_executes_mcp_tool_loop(
    monkeypatch: pytest.MonkeyPatch,
):
    requests = _install_anthropic_model(monkeypatch)
    result = asyncio.run(
        runtime.run_expert(
            endpoint="https://api.anthropic.com",
            api_key="anthropic-key",
            model_key="claude-test",
            provider="anthropic",
            model_capabilities={
                "tools": True,
                "vision": True,
                "json": True,
                "streaming": True,
            },
            system_prompt="合成系统提示词",
            messages=[{"role": "user", "content": "执行 Anthropic 工具测试"}],
            mcp_items=[_mcp_item()],
            max_tool_steps=2,
            tool_timeout_seconds=3,
        )
    )
    assert result["ok"] is True
    assert result["content"] == "Anthropic 工具循环完成。"
    assert result["provider"] == "anthropic"
    assert result["toolTrace"][0]["tool"] == "echo"
    assert requests[0]["url"] == "https://api.anthropic.com/v1/messages"
    assert requests[0]["payload"]["tools"]
    all_blocks = [
        block
        for message in requests[1]["payload"]["messages"]
        if isinstance(message.get("content"), list)
        for block in message["content"]
    ]
    assert any(block.get("type") == "tool_result" for block in all_blocks)


def test_tool_timeout_is_reported_and_model_can_degrade(
    monkeypatch: pytest.MonkeyPatch,
):
    def responder(request: dict[str, Any], index: int) -> dict[str, Any]:
        if index == 0:
            name = _tool_name(request, "_slow")
            return _completion(
                {
                    "content": "",
                    "tool_calls": [
                        _tool_call("call-slow", name, {"seconds": 0.5})
                    ],
                }
            )
        assert "Timeout" in request["messages"][-1]["content"]
        return _completion({"content": "工具超时，已提供降级结论。"})

    _install_model(monkeypatch, responder)
    result = asyncio.run(
        runtime.run_expert(
            endpoint="http://model.test/v1",
            api_key="test-key",
            model_key="test-model",
            system_prompt="合成系统提示词",
            messages=[{"role": "user", "content": "执行合成超时测试"}],
            mcp_items=[_mcp_item()],
            max_tool_steps=2,
            allow_write_tools=False,
            tool_timeout_seconds=0.05,
        )
    )

    assert result["ok"] is True
    assert result["content"] == "工具超时，已提供降级结论。"
    assert result["toolTrace"][0]["ok"] is False
    assert "Timeout" in result["toolTrace"][0]["resultPreview"]
    assert any("执行失败" in warning for warning in result["warnings"])


def test_mcp_load_failure_does_not_block_expert_reply(
    monkeypatch: pytest.MonkeyPatch,
):
    requests = _install_model(
        monkeypatch,
        lambda _request, _index: _completion({"content": "已降级回答。"}),
    )
    result = asyncio.run(
        runtime.run_expert(
            endpoint="http://model.test/v1",
            api_key="test-key",
            model_key="test-model",
            system_prompt="合成系统提示词",
            messages=[{"role": "user", "content": "合成 MCP 故障测试"}],
            mcp_items=[
                {
                    "id": "missing",
                    "name": "缺失 MCP",
                    "endpoint": "stdio: /definitely/missing/mcp-command",
                    "config": {},
                }
            ],
        )
    )

    assert result["ok"] is True
    assert result["content"] == "已降级回答。"
    assert result["availableTools"] == 2
    assert {
        item["function"]["name"] for item in requests[0]["tools"]
    } == {"web_fetch", "web_search"}
    assert any("加载失败" in warning for warning in result["warnings"])


def test_zero_tool_steps_skips_tool_schema(
    monkeypatch: pytest.MonkeyPatch,
):
    requests = _install_model(
        monkeypatch,
        lambda _request, _index: _completion({"content": "直接回答。"}),
    )
    result = asyncio.run(
        runtime.run_expert(
            endpoint="http://model.test/v1",
            api_key="test-key",
            model_key="test-model",
            system_prompt="合成系统提示词",
            messages=[{"role": "user", "content": "不需要工具"}],
            mcp_items=[_mcp_item()],
            max_tool_steps=0,
            tool_timeout_seconds=3,
        )
    )

    assert result["ok"] is True
    assert result["availableTools"] == 5
    assert "tools" not in requests[0]


def test_exhausted_tool_budget_forces_a_final_text_answer(
    monkeypatch: pytest.MonkeyPatch,
):
    def responder(request: dict[str, Any], index: int) -> dict[str, Any]:
        if index == 0:
            name = _tool_name(request, "_echo")
            return _completion(
                {
                    "content": "",
                    "tool_calls": [
                        _tool_call("call-echo", name, {"text": "partial result"})
                    ],
                }
            )
        assert "tools" not in request
        assert request["messages"][-1]["role"] == "user"
        assert "工具调用预算已用完" in request["messages"][-1]["content"]
        return _completion({"content": "已停止调用工具并完成成果。"})

    requests = _install_model(monkeypatch, responder)
    result = asyncio.run(
        runtime.run_expert(
            endpoint="http://model.test/v1",
            api_key="test-key",
            model_key="test-model",
            system_prompt="合成系统提示词",
            messages=[{"role": "user", "content": "执行任务"}],
            mcp_items=[_mcp_item()],
            max_tool_steps=1,
            tool_timeout_seconds=3,
        )
    )

    assert result["ok"] is True
    assert result["content"] == "已停止调用工具并完成成果。"
    assert result["usedTools"] == 1
    assert len(requests) == 2


def test_skill_handler_executes_as_agent_tool(
    monkeypatch: pytest.MonkeyPatch,
):
    def responder(request: dict[str, Any], index: int) -> dict[str, Any]:
        if index == 0:
            name = next(
                item["function"]["name"]
                for item in request["tools"]
                if item["function"]["name"] not in {"web_fetch", "web_search"}
            )
            return _completion(
                {
                    "content": "",
                    "tool_calls": [
                        _tool_call(
                            "call-skill",
                            name,
                            {
                                "transcript": (
                                    "确认本周上线。\n"
                                    "待办：完成回归测试，负责人：张三。"
                                )
                            },
                        )
                    ],
                }
            )
        assert "完成回归测试" in request["messages"][-1]["content"]
        return _completion({"content": "会议纪要技能已执行。"})

    _install_model(monkeypatch, responder)
    result = asyncio.run(
        runtime.run_expert(
            endpoint="http://model.test/v1",
            api_key="test-key",
            model_key="test-model",
            system_prompt="合成系统提示词",
            messages=[{"role": "user", "content": "整理会议纪要"}],
            mcp_items=[],
            skill_items=[
                {
                    "id": "skill-minutes",
                    "name": "会议纪要",
                    "description": "整理会议纪要",
                    "config": {
                        "handler": "experts.builtin_skills:meeting_minutes",
                        "instructions": "整理会议纪要与待办",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "transcript": {"type": "string"}
                            },
                            "required": ["transcript"],
                        },
                        "output_schema": {
                            "type": "object",
                            "properties": {
                                "summary": {"type": "string"},
                                "actionItems": {"type": "array"},
                            },
                            "required": ["summary", "actionItems"],
                        },
                    },
                }
            ],
            max_tool_steps=2,
        )
    )

    assert result["ok"] is True
    assert result["content"] == "会议纪要技能已执行。"
    assert result["toolTrace"][0]["kind"] == "skill"
    assert result["toolTrace"][0]["tool"] == "会议纪要"
    assert result["toolTrace"][0]["ok"] is True


def test_tool_trace_and_pending_arguments_are_redacted(
    monkeypatch: pytest.MonkeyPatch,
):
    secret = "sk-syntheticsupersecret"

    def responder(request: dict[str, Any], index: int) -> dict[str, Any]:
        if index == 0:
            name = _tool_name(request, "_echo")
            return _completion(
                {
                    "content": "",
                    "tool_calls": [
                        _tool_call("call-secret", name, {"text": secret})
                    ],
                }
            )
        return _completion({"content": "脱敏测试完成。"})

    _install_model(monkeypatch, responder)
    result = asyncio.run(
        runtime.run_expert(
            endpoint="http://model.test/v1",
            api_key="test-key",
            model_key="test-model",
            system_prompt="合成系统提示词",
            messages=[{"role": "user", "content": "测试脱敏"}],
            mcp_items=[_mcp_item()],
            max_tool_steps=2,
            tool_timeout_seconds=3,
        )
    )

    trace = result["toolTrace"][0]
    assert secret not in json.dumps(trace, ensure_ascii=False)
    assert "sk-********" in trace["arguments"]["text"]
    assert "sk-********" in trace["resultPreview"]


def test_tool_policy_can_deny_or_require_confirmation():
    async def scenario() -> None:
        stack, tools, warnings = await runtime.discover_mcp_tools(
            [_mcp_item()],
            timeout_seconds=3,
            tool_policies={
                "runtime-test-mcp:echo": "deny",
                "runtime-test-mcp:fail": "confirm",
            },
        )
        try:
            names = {tool.original_name for tool in tools}
            assert "echo" not in names
            confirm_tool = next(tool for tool in tools if tool.original_name == "fail")
            assert confirm_tool.requires_confirmation is True
            assert any("工具级策略禁用" in warning for warning in warnings)
        finally:
            await stack.aclose()

    asyncio.run(scenario())


def test_project_filesystem_repository_and_safari_mcp_are_discoverable():
    safari_read_only = [
        "browser_console_messages",
        "get_network_request",
        "get_page_content",
        "list_network_requests",
        "list_tabs",
        "page_info",
        "wait_for_navigation",
    ]

    async def discover_project_tools():
        return await runtime.discover_mcp_tools(
            [
                _project_mcp("filesystem", "filesystem_mcp.py"),
                _project_mcp("repository", "repository_mcp.py"),
                {
                    "id": "safari-test",
                    "name": "safari",
                    "endpoint": "stdio: ${SAFARIDRIVER} --mcp",
                    "config": {"read_only_tools": safari_read_only},
                },
            ],
            allow_write_tools=True,
            timeout_seconds=10,
        )

    async def scenario() -> None:
        stack, tools, warnings = await discover_project_tools()
        try:
            by_mcp: dict[str, list[Any]] = {}
            for tool in tools:
                by_mcp.setdefault(tool.mcp_name, []).append(tool)
            assert "list_directory" in {
                tool.original_name for tool in by_mcp["filesystem"]
            }
            assert "git_status" in {
                tool.original_name for tool in by_mcp["repository"]
            }
            assert "page_info" in {
                tool.original_name for tool in by_mcp["safari"]
            }
            assert "create_tab" in {
                tool.original_name for tool in by_mcp["safari"]
            }
            assert not any("加载失败" in warning for warning in warnings)

            filesystem = next(
                tool for tool in tools if tool.original_name == "list_directory"
            )
            listed = await filesystem.session.call_tool(
                "list_directory", {"path": ".", "limit": 5}
            )
            assert listed.is_error is False
            assert "entries" in _tool_text(listed)

            repository = next(
                tool for tool in tools if tool.original_name == "git_status"
            )
            status = await repository.session.call_tool("git_status", {})
            assert status.is_error is False
        finally:
            await stack.aclose()

    asyncio.run(scenario())


def test_postgres_mcp_only_allows_read_queries():
    async def scenario() -> None:
        stack, tools, warnings = await runtime.discover_mcp_tools(
            [_project_mcp("database", "postgres_mcp.py")],
            timeout_seconds=10,
        )
        try:
            assert not warnings
            assert len(tools) == 1
            assert tools[0].read_only is True
            query = await tools[0].session.call_tool(
                "query_readonly",
                {"sql": "select current_database() as database, 1 as ok"},
            )
            assert query.is_error is False
            assert '"database": "xf"' in _tool_text(query)

            rejected = await tools[0].session.call_tool(
                "query_readonly",
                {"sql": "delete from admin_member"},
            )
            assert rejected.is_error is True
        finally:
            await stack.aclose()

    asyncio.run(scenario())


def _tool_text(result: Any) -> str:
    return "\n".join(
        str(getattr(item, "text", "") or "")
        for item in (getattr(result, "content", None) or [])
    )
