"""Load local test configuration without committing credentials."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_env(path: Path) -> None:
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


_load_env(PROJECT_ROOT / ".env")
_load_env(PROJECT_ROOT / "admin" / ".env")

TEST_API_URL = os.getenv("TEST_API_URL", "http://localhost:8000")
TEST_ADMIN_USERNAME = os.getenv("TEST_ADMIN_USERNAME", "admin")
TEST_ADMIN_PASSWORD = os.getenv("TEST_ADMIN_PASSWORD", "")
TEST_USER_USERNAME = os.getenv("TEST_USER_USERNAME", "deptuser")
TEST_USER_PASSWORD = os.getenv("TEST_USER_PASSWORD", "")
TEST_ADMIN_EMAIL = os.getenv("TEST_ADMIN_EMAIL", os.getenv("SITE_ADMIN_EMAIL", ""))

PG_HOST = os.getenv("PG_HOST", "127.0.0.1")
PG_PORT = int(os.getenv("PG_PORT", "5432"))
PG_DBNAME = os.getenv("PG_DBNAME", "xf")
PG_USER = os.getenv("PG_USER", "postgres")
PG_PASSWORD = os.getenv("PG_PASSWORD", "")
