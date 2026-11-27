"""项目内置 PostgreSQL MCP：只读 SQL 查询。"""
import asyncio
import json
import re
import sys
from datetime import date, datetime, time as datetime_time
from decimal import Decimal
from pathlib import Path
from typing import Any

import asyncpg

SITE_DIR = Path(__file__).resolve().parents[1]
if str(SITE_DIR) not in sys.path:
    sys.path.insert(0, str(SITE_DIR))

from settings import settings  # noqa: E402

READ_ONLY_PREFIX = re.compile(r"^\s*(select|with|explain|show|values)\b", re.IGNORECASE)
MAX_ROWS = 200
MAX_SQL_LENGTH = 20000


def _json_default(value: Any) -> Any:
    if isinstance(value, (date, datetime, datetime_time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (bytes, bytearray)):
        return f"<{len(value)} bytes>"
    return str(value)


def _reply(message_id: object, result: object) -> None:
    print(
        json.dumps(
            {"jsonrpc": "2.0", "id": message_id, "result": result},
            ensure_ascii=False,
            default=_json_default,
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


def _validate_sql(sql: str) -> str:
    clean = sql.strip()
    if not clean:
        raise ValueError("SQL 不能为空")
    if len(clean) > MAX_SQL_LENGTH:
        raise ValueError(f"SQL 超过 {MAX_SQL_LENGTH} 字符限制")
    if not READ_ONLY_PREFIX.match(clean):
        raise ValueError("只允许 SELECT、WITH、EXPLAIN、SHOW 或 VALUES 查询")
    if ";" in clean.rstrip().rstrip(";"):
        raise ValueError("只允许执行单条 SQL")
    return clean.rstrip().rstrip(";")


async def _query(sql: str, limit: int) -> dict[str, Any]:
    statement = _validate_sql(sql)
    connection = await asyncpg.connect(
        host=settings.pg_host,
        port=settings.pg_port,
        database=settings.pg_database,
        user=settings.pg_user,
        password=settings.pg_password,
        timeout=5,
    )
    try:
        async with connection.transaction(readonly=True):
            await connection.execute("SET LOCAL statement_timeout = '8s'")
            rows = await connection.fetch(statement)
    finally:
        await connection.close()
    capped = max(1, min(MAX_ROWS, limit))
    selected = rows[:capped]
    return {
        "rowCount": len(rows),
        "returned": len(selected),
        "truncated": len(rows) > len(selected),
        "rows": [dict(row) for row in selected],
    }


async def _dispatch(message: dict[str, Any]) -> tuple[object, int] | None:
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
                "serverInfo": {"name": "xf-postgres-readonly", "version": "1.0.0"},
            },
            0,
        )
    if method in {"tools/list", "list_tools"}:
        return (
            {
                "tools": [
                    {
                        "name": "query_readonly",
                        "description": "在只读事务中执行单条 PostgreSQL 查询",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "sql": {
                                    "type": "string",
                                    "description": "SELECT、WITH、EXPLAIN、SHOW 或 VALUES 查询",
                                },
                                "limit": {
                                    "type": "integer",
                                    "minimum": 1,
                                    "maximum": MAX_ROWS,
                                    "default": 50,
                                },
                            },
                            "required": ["sql"],
                        },
                        "annotations": {"readOnlyHint": True},
                    }
                ]
            },
            0,
        )
    if method in {"tools/call", "call_tool"}:
        arguments = params.get("arguments") or {}
        try:
            result = await asyncio.wait_for(
                _query(str(arguments.get("sql") or ""), int(arguments.get("limit") or 50)),
                timeout=10,
            )
            return (
                {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                result, ensure_ascii=False, default=_json_default
                            ),
                        }
                    ],
                    "isError": False,
                },
                0,
            )
        except Exception as exc:  # noqa: BLE001 - 查询错误需回填给模型
            return (
                {
                    "content": [
                        {
                            "type": "text",
                            "text": f"数据库查询失败：{exc.__class__.__name__}: {exc}",
                        }
                    ],
                    "isError": True,
                },
                0,
            )
    return {"message": f"Method not found: {method}"}, -32601


async def main() -> None:
    while True:
        line = await asyncio.to_thread(sys.stdin.readline)
        if not line:
            break
        try:
            message = json.loads(line)
        except ValueError:
            continue
        if not isinstance(message, dict):
            continue
        outcome = await _dispatch(message)
        if outcome is None:
            continue
        result, error_code = outcome
        if error_code:
            _error(message.get("id"), error_code, str((result or {}).get("message", "error")))
        else:
            _reply(message.get("id"), result)


if __name__ == "__main__":
    asyncio.run(main())
