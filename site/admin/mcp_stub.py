"""测试用最小 stdio MCP 服务：支持工具发现、只读调用、写入与故障模拟。"""
import json
import sys
import time


TOOLS = [
    {
        "name": "echo",
        "description": "Return the supplied text",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "write_value",
        "description": "Simulate a write operation",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False},
    },
    {
        "name": "slow",
        "description": "Sleep before returning",
        "inputSchema": {
            "type": "object",
            "properties": {"seconds": {"type": "number"}},
            "required": ["seconds"],
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "fail",
        "description": "Return a tool error",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {"readOnlyHint": True},
    },
]


def _reply(message_id: object, result: object) -> None:
    print(
        json.dumps(
            {"jsonrpc": "2.0", "id": message_id, "result": result},
            ensure_ascii=False,
        ),
        flush=True,
    )


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


for line in sys.stdin:
    try:
        message = json.loads(line)
    except (TypeError, ValueError):
        continue
    if not isinstance(message, dict) or "id" not in message:
        continue
    message_id = message.get("id")
    method = message.get("method")
    params = message.get("params") or {}
    if method == "initialize":
        _reply(
            message_id,
            {
                "protocolVersion": params.get("protocolVersion") or "2025-03-26",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "xf-test-mcp", "version": "1.1.0"},
            },
        )
    elif method in {"list_tools", "tools/list"}:
        _reply(message_id, {"tools": TOOLS})
    elif method in {"call_tool", "tools/call"}:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name == "echo":
            result = {
                "content": [
                    {"type": "text", "text": f"ECHO: {arguments.get('text', '')}"}
                ],
                "isError": False,
            }
        elif name == "write_value":
            result = {
                "content": [
                    {
                        "type": "text",
                        "text": f"WRITE: {arguments.get('text', '')}",
                    }
                ],
                "isError": False,
            }
        elif name == "slow":
            time.sleep(max(0, float(arguments.get("seconds", 1))))
            result = {
                "content": [{"type": "text", "text": "SLOW: done"}],
                "isError": False,
            }
        elif name == "fail":
            result = {
                "content": [{"type": "text", "text": "TEST FAILURE"}],
                "isError": True,
            }
        else:
            _error(message_id, -32602, f"Unknown tool: {name}")
            continue
        _reply(message_id, result)
    else:
        _error(message_id, -32601, f"Method not found: {method}")
