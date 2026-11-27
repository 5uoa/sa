"""MCP 配置拆分、密钥加密与接口脱敏。"""
import json
from typing import Any

import db
from admin import secret

SENSITIVE_CONFIG_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "credentials",
    "env",
    "headers",
    "password",
    "private_key",
    "secret",
    "secrets",
    "token",
}


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


def split_mcp_config(config: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    public: dict[str, Any] = {}
    sensitive: dict[str, Any] = {}
    for key, value in config.items():
        if str(key).lower() in SENSITIVE_CONFIG_KEYS:
            sensitive[key] = value
        else:
            public[key] = value
    return public, sensitive


def _mask(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _mask(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_mask(item) for item in value]
    text = str(value)
    if len(text) <= 8:
        return "*" * len(text)
    return f"{text[:4]}****{text[-4:]}"


def mask_public_config(config: dict[str, Any]) -> dict[str, Any]:
    masked: dict[str, Any] = {}
    for key, value in config.items():
        if str(key).lower() in SENSITIVE_CONFIG_KEYS:
            masked[key] = _mask(value)
        elif isinstance(value, dict):
            masked[key] = mask_public_config(value)
        else:
            masked[key] = value
    return masked


def decrypt_secret_config(value: str) -> dict[str, Any]:
    plain = secret.decrypt(value)
    return _json_object(plain)


def encrypt_secret_config(value: dict[str, Any]) -> str:
    return secret.encrypt(json.dumps(value, ensure_ascii=False)) if value else ""


def mcp_runtime_config(row: dict[str, Any]) -> dict[str, Any]:
    public = _json_object(row.get("config"))
    sensitive = decrypt_secret_config(str(row.get("secret_config_enc") or ""))
    return {**public, **sensitive}


async def migrate_plaintext_mcp_secrets() -> int:
    """把历史 MCP config 中的 headers/env 等字段迁移到加密列。"""
    rows = await db.fetch(
        """
        SELECT data_id::text AS id, config, secret_config_enc
          FROM ai_mcp
         WHERE is_deleted = false
        """
    )
    migrated = 0
    for row in rows:
        config = _json_object(row["config"])
        public, sensitive = split_mcp_config(config)
        if not sensitive:
            continue
        existing = decrypt_secret_config(str(row["secret_config_enc"] or ""))
        merged = {**existing, **sensitive}
        await db.execute(
            """
            UPDATE ai_mcp
               SET config = $2::jsonb,
                   secret_config_enc = $3,
                   update_time = now()
             WHERE data_id = $1::uuid
            """,
            row["id"],
            json.dumps(public, ensure_ascii=False),
            encrypt_secret_config(merged),
        )
        migrated += 1
    return migrated
