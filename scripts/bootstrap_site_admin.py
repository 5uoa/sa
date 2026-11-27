"""用项目根 .env 初始化框架后台与 Site 管理后台管理员密码。

SQL 种子只创建账号，不包含任何默认密码。执行完 INIT.SQL 与
site/admin/admin.sql 后运行：

    python scripts/bootstrap_site_admin.py

密码只从环境变量读取，不会出现在命令行参数或 Git 中。
脚本默认只初始化空密码账号；使用 --force 可重置现有密码。
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import asyncpg

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_env(path: Path) -> None:
    """加载简单 KEY=VALUE 配置，不覆盖进程里已显式设置的环境变量。"""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def require_env(key: str) -> str:
    value = os.getenv(key, "").strip()
    if not value:
        raise SystemExit(f"缺少环境变量 {key}，请在 .env 中配置后重试。")
    return value


def optional_env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


async def bootstrap_site_admin(conn: asyncpg.Connection, force: bool) -> None:
    email = optional_env("SITE_ADMIN_EMAIL")
    password = optional_env("SITE_ADMIN_INITIAL_PASSWORD")
    if not email or not password:
        print("未配置 SITE_ADMIN_EMAIL / SITE_ADMIN_INITIAL_PASSWORD，跳过 Site 管理员初始化。")
        return
    if len(password) < 8:
        raise SystemExit("SITE_ADMIN_INITIAL_PASSWORD 至少需要 8 个字符。")

    member = await conn.fetchrow(
        """
        SELECT data_id, password_hash
          FROM admin_member
         WHERE lower(email) = lower($1)
           AND is_deleted = false
         LIMIT 1
        """,
        email,
    )
    if not member:
        raise SystemExit(f"未找到 Site 管理员账号 {email}，请检查 SITE_ADMIN_EMAIL。")
    if member["password_hash"] and not force:
        print(f"Site 管理员 {email} 已有密码，未做修改。")
        return

    await conn.execute(
        """
        UPDATE admin_member
           SET password_hash = crypt($2, gen_salt('bf')),
               must_change_password = true,
               accepted_at = COALESCE(accepted_at, now()),
               update_time = now()
         WHERE data_id = $1
        """,
        member["data_id"],
        password,
    )
    print(f"Site 管理员 {email} 的登录密码已初始化；首次登录后必须修改密码。")


async def bootstrap_framework_admin(conn: asyncpg.Connection, force: bool) -> None:
    username = optional_env("FRAMEWORK_ADMIN_USERNAME", "admin")
    password = optional_env("FRAMEWORK_ADMIN_PASSWORD")
    email = optional_env("FRAMEWORK_ADMIN_EMAIL", "admin@example.com")
    if not password:
        print("未配置 FRAMEWORK_ADMIN_PASSWORD，跳过框架管理员初始化。")
        return
    if len(password) < 8:
        raise SystemExit("FRAMEWORK_ADMIN_PASSWORD 至少需要 8 个字符。")

    member = await conn.fetchrow(
        """
        SELECT id, password
          FROM x_user
         WHERE username = $1
           AND is_deleted = 0
         LIMIT 1
        """,
        username,
    )
    if not member:
        raise SystemExit(f"未找到框架管理员账号 {username}，请检查 INIT.SQL。")
    if member["password"] and not force:
        print(f"框架管理员 {username} 已有密码，未做修改。")
        return

    await conn.execute(
        """
        UPDATE x_user
           SET password = crypt($2, gen_salt('bf')),
               email = COALESCE(NULLIF($3, ''), email),
               token = '',
               update_time = now()
         WHERE id = $1
        """,
        member["id"],
        password,
        email,
    )
    print(f"框架管理员 {username} 的登录密码已初始化。")


async def bootstrap(force: bool = False) -> None:
    conn = await asyncpg.connect(
        host=os.getenv("PG_HOST", "127.0.0.1"),
        port=int(os.getenv("PG_PORT", "5432")),
        database=require_env("PG_DBNAME"),
        user=require_env("PG_USER"),
        password=require_env("PG_PASSWORD"),
    )
    try:
        tables = {
            row["table_name"]
            for row in await conn.fetch(
                """
                SELECT table_name
                  FROM information_schema.tables
                 WHERE table_schema = 'public'
                   AND table_name IN ('x_user', 'admin_member')
                """
            )
        }
        if "x_user" not in tables:
            raise SystemExit("x_user 表不存在，请先执行 INIT.SQL。")
        if "admin_member" not in tables:
            raise SystemExit("admin_member 表不存在，请先执行 site/admin/admin.sql。")

        await bootstrap_framework_admin(conn, force)
        await bootstrap_site_admin(conn, force)
    finally:
        await conn.close()


if __name__ == "__main__":
    load_env(PROJECT_ROOT / ".env")
    load_env(PROJECT_ROOT / "admin" / ".env")
    asyncio.run(bootstrap(force="--force" in sys.argv[1:]))
