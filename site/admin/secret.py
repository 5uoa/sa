"""模型 API Key 加密与掩码

- 数据库只保存 AES-GCM 密文，接口永不返回明文
- 加密密钥优先读取 SITE_SECRET_KEY；未配置时由数据库凭据派生（仅本地开发兜底）
"""
import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from settings import settings

NONCE_BYTES = 12


def _derive_key() -> bytes:
    seed = settings.api_key_secret or f"{settings.pg_password}|{settings.pg_database}"
    return hashlib.sha256(f"site-api-key|{seed}".encode("utf-8")).digest()


def encrypt(plain: str) -> str:
    raw = plain.encode("utf-8")
    nonce = os.urandom(NONCE_BYTES)
    sealed = AESGCM(_derive_key()).encrypt(nonce, raw, None)
    return base64.urlsafe_b64encode(nonce + sealed).decode("ascii")


def decrypt(token: str) -> str:
    if not token:
        return ""
    try:
        payload = base64.urlsafe_b64decode(token.encode("ascii"))
        nonce, sealed = payload[:NONCE_BYTES], payload[NONCE_BYTES:]
        return AESGCM(_derive_key()).decrypt(nonce, sealed, None).decode("utf-8")
    except Exception:  # noqa: BLE001 - 脏数据或密钥变更时按未配置处理
        return ""


def mask(plain: str) -> str:
    """掩码展示：保留前 4 位与后 4 位"""
    if not plain:
        return ""
    if len(plain) <= 8:
        return "*" * len(plain)
    return f"{plain[:4]}****{plain[-4:]}"
