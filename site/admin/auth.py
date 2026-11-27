"""前台管理后台认证、会话与操作者上下文。"""
import hashlib
import secrets
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt
from fastapi import Request

import db
from common import ApiProblem
from settings import settings

_actor: ContextVar[dict[str, Any] | None] = ContextVar("site_admin_actor", default=None)
ADMIN_ROLES = {"拥有者", "管理员"}
INVITE_HOURS = 72


def _jwt_secret() -> str:
    if settings.admin_jwt_secret:
        return settings.admin_jwt_secret
    # 本地兼容：生产环境应在 .env 中显式配置 SITE_ADMIN_JWT_SECRET。
    seed = settings.admin_token or f"{settings.pg_password}|{settings.pg_database}"
    return hashlib.sha256(f"site-admin-jwt|{seed}".encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, stored: str) -> bool:
    if not stored:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), stored.encode("ascii"))
    except (ValueError, TypeError):
        return False


def _password_version(password_hash: str) -> str:
    return hashlib.sha256(password_hash.encode("utf-8")).hexdigest()[:16]


def create_access_token(member: dict[str, Any]) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": member["id"],
        "email": member["email"],
        "name": member["name"],
        "role": member["role"],
        "ver": _password_version(member.get("password_hash", "")),
        "iat": now,
        "exp": now + timedelta(minutes=settings.admin_jwt_ttl_minutes),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm="HS256")


def create_invitation() -> tuple[str, str, datetime]:
    token = secrets.token_urlsafe(32)
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    expires = datetime.now(timezone.utc) + timedelta(hours=INVITE_HOURS)
    return token, digest, expires


def invite_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_actor() -> dict[str, Any] | None:
    return _actor.get()


def actor_name(default: str = "系统") -> str:
    value = _actor.get()
    return str(value.get("name") or value.get("email") or default) if value else default


def actor_id() -> str | None:
    value = _actor.get()
    return str(value["id"]) if value and value.get("id") else None


async def _member_from_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise ApiProblem(401, "登录已过期，请重新登录。")
    except jwt.PyJWTError:
        raise ApiProblem(401, "登录状态无效，请重新登录。")

    member_id = str(payload.get("sub") or "")
    row = await db.fetchrow(
        """
        SELECT data_id::text AS id, name, email, role, enabled, last_active,
               password_hash, must_change_password, accepted_at
          FROM admin_member
         WHERE data_id = $1::uuid AND is_deleted = false
         LIMIT 1
        """,
        member_id,
    )
    if not row:
        raise ApiProblem(401, "账号不存在或已被移除。")
    member = dict(row)
    if not member["enabled"]:
        raise ApiProblem(403, "账号已停用。")
    if member["role"] not in ADMIN_ROLES:
        raise ApiProblem(403, "当前角色没有管理后台权限。")
    if payload.get("ver") != _password_version(member.get("password_hash", "")):
        raise ApiProblem(401, "登录状态已失效，请重新登录。")
    return member


async def require_admin_user(request: Request) -> dict[str, Any]:
    if settings.admin_auth_disabled:
        row = await db.fetchrow(
            """
            SELECT data_id::text AS id, name, email, role, enabled, last_active,
                   password_hash, must_change_password
              FROM admin_member
             WHERE role IN ('拥有者', '管理员')
               AND enabled = true
               AND is_deleted = false
             ORDER BY CASE role WHEN '拥有者' THEN 0 ELSE 1 END, id ASC
             LIMIT 1
            """
        )
        if not row:
            raise ApiProblem(503, "开发管理员账号尚未初始化。")
        member = dict(row)
        _actor.set(member)
        return member
    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer "):
        raise ApiProblem(401, "请先登录管理后台。")
    member = await _member_from_token(header[7:].strip())
    _actor.set(member)
    return member


async def login(email: str, password: str) -> dict[str, Any]:
    row = await db.fetchrow(
        """
        SELECT data_id::text AS id, name, email, role, enabled, last_active,
               password_hash, must_change_password, accepted_at
          FROM admin_member
         WHERE lower(email) = lower($1) AND is_deleted = false
         LIMIT 1
        """,
        email,
    )
    member = dict(row) if row else None
    if (
        not member
        or not member["enabled"]
        or member["role"] not in ADMIN_ROLES
        or not verify_password(password, member["password_hash"])
    ):
        raise ApiProblem(401, "邮箱或密码错误。")
    await db.execute(
        "UPDATE admin_member SET last_active = '刚刚', update_time = now() WHERE data_id = $1::uuid",
        member["id"],
    )
    return {
        "token": create_access_token(member),
        "user": {
            "id": member["id"],
            "name": member["name"],
            "email": member["email"],
            "role": member["role"],
            "mustChangePassword": member["must_change_password"],
        },
    }


async def development_login() -> dict[str, Any]:
    """开发环境自动登录：仅在 SITE_ADMIN_AUTO_LOGIN=true 且本机调用时由路由开放。"""
    row = await db.fetchrow(
        """
        SELECT data_id::text AS id, name, email, role, enabled, last_active,
               password_hash, must_change_password
          FROM admin_member
         WHERE role IN ('拥有者', '管理员')
           AND enabled = true
           AND is_deleted = false
         ORDER BY CASE role WHEN '拥有者' THEN 0 ELSE 1 END, id ASC
         LIMIT 1
        """
    )
    if not row:
        raise ApiProblem(503, "开发账号尚未初始化。")
    member = dict(row)
    return {
        "token": create_access_token(member),
        "user": {
            "id": member["id"],
            "name": member["name"],
            "email": member["email"],
            "role": member["role"],
            "mustChangePassword": False,
        },
    }


async def accept_invite(token: str, password: str, name: str = "") -> dict[str, Any]:
    digest = invite_digest(token)
    row = await db.fetchrow(
        """
        SELECT data_id::text AS id, name, email, role
          FROM admin_member
         WHERE invitation_token_hash = $1
           AND invitation_expires_at > now()
           AND enabled = true
           AND is_deleted = false
         LIMIT 1
        """,
        digest,
    )
    if not row:
        raise ApiProblem(400, "邀请链接无效或已过期。")
    member = dict(row)
    await db.execute(
        """
        UPDATE admin_member
           SET name = CASE WHEN trim($2) = '' THEN name ELSE trim($2) END,
               password_hash = $3,
               must_change_password = false,
               invitation_token_hash = NULL,
               invitation_expires_at = NULL,
               accepted_at = now(),
               last_active = '刚刚',
               update_time = now()
         WHERE data_id = $1::uuid
        """,
        member["id"],
        name,
        hash_password(password),
    )
    member["name"] = name.strip() or member["name"]
    member["password_hash"] = await db.fetchval(
        "SELECT password_hash FROM admin_member WHERE data_id = $1::uuid",
        member["id"],
    ) or ""
    return {
        "token": create_access_token(member),
        "user": {
            "id": member["id"],
            "name": member["name"],
            "email": member["email"],
            "role": member["role"],
            "mustChangePassword": False,
        },
    }
