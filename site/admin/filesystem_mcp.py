"""项目内置文件系统 MCP：工作区内的只读文件访问。"""
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAX_TEXT_BYTES = 64 * 1024
MAX_ENTRIES = 200


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


def _safe_path(raw_path: str) -> Path:
    relative = raw_path.strip().lstrip("/")
    target = (PROJECT_ROOT / relative).resolve()
    try:
        target.relative_to(PROJECT_ROOT)
    except ValueError as exc:
        raise ValueError("路径必须位于项目工作区内") from exc
    return target


def _list_directory(path: str, limit: int) -> dict[str, Any]:
    target = _safe_path(path or ".")
    if not target.is_dir():
        raise ValueError(f"目录不存在：{path or '.'}")
    entries = sorted(target.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
    selected = entries[: max(1, min(MAX_ENTRIES, limit))]
    return {
        "path": str(target.relative_to(PROJECT_ROOT)),
        "entries": [
            {
                "name": item.name,
                "type": "directory" if item.is_dir() else "file",
            }
            for item in selected
        ],
        "truncated": len(entries) > len(selected),
    }


def _read_text(path: str) -> dict[str, Any]:
    target = _safe_path(path)
    if not target.is_file():
        raise ValueError(f"文件不存在：{path}")
    if target.stat().st_size > MAX_TEXT_BYTES:
        raise ValueError(f"文件超过 {MAX_TEXT_BYTES} 字节限制")
    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("只允许读取 UTF-8 文本文件") from exc
    return {
        "path": str(target.relative_to(PROJECT_ROOT)),
        "content": content,
        "bytes": target.stat().st_size,
    }


def _search_text(path: str, query: str) -> dict[str, Any]:
    target = _safe_path(path or ".")
    if not query.strip():
        raise ValueError("搜索词不能为空")
    result = subprocess.run(
        [
            "rg",
            "--line-number",
            "--no-heading",
            "--color",
            "never",
            "--max-count",
            "20",
            "--glob",
            "!node_modules/**",
            "--glob",
            "!.git/**",
            "--glob",
            "!.venv/**",
            "--glob",
            "!.output/**",
            query,
            str(target),
        ],
        capture_output=True,
        text=True,
        timeout=8,
        check=False,
    )
    lines = result.stdout.splitlines()[:100]
    return {
        "query": query,
        "matches": [line.replace(str(PROJECT_ROOT) + "/", "") for line in lines],
        "truncated": len(result.stdout.splitlines()) > len(lines),
    }


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
                "serverInfo": {"name": "xf-filesystem-readonly", "version": "1.0.0"},
            },
            0,
        )
    if method in {"tools/list", "list_tools"}:
        return (
            {
                "tools": [
                    {
                        "name": "list_directory",
                        "description": "列出项目工作区内的目录",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string", "default": "."},
                                "limit": {"type": "integer", "default": 100},
                            },
                        },
                        "annotations": {"readOnlyHint": True},
                    },
                    {
                        "name": "read_text",
                        "description": "读取项目内的 UTF-8 文本文件",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"path": {"type": "string"}},
                            "required": ["path"],
                        },
                        "annotations": {"readOnlyHint": True},
                    },
                    {
                        "name": "search_text",
                        "description": "在项目路径中使用 ripgrep 搜索文本",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string", "default": "."},
                                "query": {"type": "string"},
                            },
                            "required": ["query"],
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
            if name == "list_directory":
                result = _list_directory(
                    str(arguments.get("path") or "."),
                    int(arguments.get("limit") or 100),
                )
            elif name == "read_text":
                result = _read_text(str(arguments.get("path") or ""))
            elif name == "search_text":
                result = _search_text(
                    str(arguments.get("path") or "."),
                    str(arguments.get("query") or ""),
                )
            else:
                raise ValueError(f"未知工具：{name}")
            return (
                {
                    "content": [
                        {"type": "text", "text": json.dumps(result, ensure_ascii=False)}
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
                            "text": f"文件系统操作失败：{exc.__class__.__name__}: {exc}",
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
