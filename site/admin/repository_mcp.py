"""项目内置代码仓库 MCP：只读 Git 状态、日志与差异。"""
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAX_OUTPUT = 64 * 1024


def _reply(message_id: object, result: object) -> None:
    print(json.dumps({"jsonrpc": "2.0", "id": message_id, "result": result}, ensure_ascii=False), flush=True)


def _error(message_id: object, code: int, text: str) -> None:
    print(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": message_id,
                "error": {"code": code, "message": text},
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(PROJECT_ROOT), *args],
        capture_output=True,
        text=True,
        timeout=12,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(result.stderr.strip() or "Git 命令执行失败")
    output = result.stdout
    return output[:MAX_OUTPUT] + ("\n...[truncated]" if len(output) > MAX_OUTPUT else "")


def _dispatch(message: dict[str, Any]) -> tuple[object, int] | None:
    message_id = message.get("id")
    if message_id is None:
        return None
    method = message.get("method")
    params = message.get("params") or {}
    if method == "initialize":
        return (
            {
                "protocolVersion": params.get("protocolVersion") or "2025-03-26",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "xf-repository-readonly", "version": "1.0.0"},
            },
            0,
        )
    if method in {"tools/list", "list_tools"}:
        return (
            {
                "tools": [
                    {
                        "name": "git_status",
                        "description": "查看当前仓库工作区状态",
                        "inputSchema": {"type": "object", "properties": {}},
                        "annotations": {"readOnlyHint": True},
                    },
                    {
                        "name": "git_log",
                        "description": "查看最近提交记录",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "limit": {
                                    "type": "integer",
                                    "minimum": 1,
                                    "maximum": 50,
                                    "default": 10,
                                }
                            },
                        },
                        "annotations": {"readOnlyHint": True},
                    },
                    {
                        "name": "git_diff",
                        "description": "查看当前未提交差异",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "staged": {"type": "boolean", "default": False},
                                "path": {"type": "string"},
                            },
                        },
                        "annotations": {"readOnlyHint": True},
                    },
                ]
            },
            0,
        )
    if method in {"tools/call", "call_tool"}:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        try:
            if name == "git_status":
                output = _git("status", "--short", "--branch")
            elif name == "git_log":
                limit = max(1, min(50, int(arguments.get("limit") or 10)))
                output = _git("log", f"-{limit}", "--oneline", "--decorate")
            elif name == "git_diff":
                args = ["diff"]
                if arguments.get("staged"):
                    args.append("--cached")
                path = str(arguments.get("path") or "").strip()
                if path:
                    args.extend(["--", path])
                output = _git(*args)
            else:
                raise ValueError(f"未知工具：{name}")
            return (
                {
                    "content": [
                        {
                            "type": "text",
                            "text": output or "(no output)",
                        }
                    ],
                    "isError": False,
                },
                0,
            )
        except Exception as exc:  # noqa: BLE001 - 工具错误需回填给模型
            return (
                {
                    "content": [
                        {
                            "type": "text",
                            "text": f"代码仓库操作失败：{exc.__class__.__name__}: {exc}",
                        }
                    ],
                    "isError": True,
                },
                0,
            )
    return {"message": f"Method not found: {method}"}, -32601


for line in sys.stdin:
    try:
        message = json.loads(line)
    except ValueError:
        continue
    if not isinstance(message, dict):
        continue
    outcome = _dispatch(message)
    if outcome is None:
        continue
    result, error_code = outcome
    if error_code:
        _error(message.get("id"), error_code, str((result or {}).get("message", "error")))
    else:
        _reply(message.get("id"), result)
