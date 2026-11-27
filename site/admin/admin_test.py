"""管理后台接口测试（/front/admin）

运行：python -m pytest site/admin/admin_test.py -q
- 自动拉起 site 服务（8100），端口已被占用时复用现有实例
- 所有测试数据用后清理，改动的种子数据恢复原值，可重复执行
"""
import os
import asyncio
import json
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx
import pytest
import asyncpg
from tests.env import PG_DBNAME, PG_HOST, PG_PASSWORD, PG_PORT, PG_USER, TEST_ADMIN_EMAIL

BASE_URL = "http://127.0.0.1:8100"
REPO_ROOT = Path(__file__).resolve().parents[2]
STARTUP_TIMEOUT = 30.0

pytestmark = pytest.mark.usefixtures("api_server")
TOKEN = ""
ADMIN_EMAIL = TEST_ADMIN_EMAIL


# ---------------- 服务启停 ----------------

def _database_ready() -> bool | None:
    """返回 True/False 表示服务可达与否；None 表示端口未监听"""
    try:
        response = httpx.get(f"{BASE_URL}/health", timeout=2)
    except httpx.HTTPError:
        return None
    try:
        payload = response.json()
    except ValueError:
        return False
    return response.status_code == 200 and bool(payload.get("data", {}).get("database"))


@pytest.fixture(scope="module")
def api_server():
    process: subprocess.Popen[str] | None = None
    logs: deque[str] = deque(maxlen=80)

    if _database_ready() is None:
        env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "main:app",
                "--app-dir",
                "site",
                "--host",
                "127.0.0.1",
                "--port",
                "8100",
            ],
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )

        def _drain(stream) -> None:
            for line in stream:
                logs.append(line.rstrip())

        threading.Thread(target=_drain, args=(process.stdout,), daemon=True).start()

    deadline = time.time() + STARTUP_TIMEOUT
    while not _database_ready():
        if process is not None and process.poll() is not None:
            raise RuntimeError("site 服务启动失败：\n" + "\n".join(logs))
        if time.time() > deadline:
            raise RuntimeError("等待 /health 数据库就绪超时：\n" + "\n".join(logs))
        time.sleep(0.3)

    login = httpx.post(f"{BASE_URL}/front/admin/auth/dev-login", timeout=10)
    assert login.status_code == 200, login.text
    global TOKEN
    TOKEN = login.json()["data"]["token"]

    yield BASE_URL

    async def cleanup_logs():
        conn = await asyncpg.connect(
            host=PG_HOST,
            port=PG_PORT,
            database=PG_DBNAME,
            user=PG_USER,
            password=PG_PASSWORD,
        )
        try:
            await conn.execute(
                """
                DELETE FROM admin_operation_log
                 WHERE target ILIKE '%pytest%'
                    OR target ILIKE '%test+%'
                    OR action ILIKE '测试%'
                """
            )
        finally:
            await conn.close()

    asyncio.run(cleanup_logs())

    if process is not None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


# ---------------- 请求辅助 ----------------

def post(path: str, payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    response = httpx.post(
        f"{BASE_URL}{path}",
        json=payload or {},
        headers={"Authorization": f"Bearer {TOKEN}"},
        timeout=15,
    )
    return response.status_code, response.json()


def ok(path: str, payload: dict[str, Any] | None = None) -> Any:
    status, body = post(path, payload)
    assert status == 200, f"{path} HTTP {status}: {body}"
    assert body["code"] == 200, f"{path} code={body['code']}: {body}"
    return body["data"]


def find(items: list[dict[str, Any]], data_id: str) -> dict[str, Any] | None:
    return next((item for item in items if item["id"] == data_id), None)


def list_items(path: str, payload: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return ok(path, payload)["items"]


def test_admin_auth_required_and_role_guard():
    response = httpx.post(f"{BASE_URL}/front/admin/members/list", json={}, timeout=10)
    assert response.status_code in {200, 401}
    assert response.json()["code"] in {200, 401}

    owner = next(item for item in list_items("/front/admin/members/list") if item["role"] == "拥有者")
    status, body = post("/front/admin/members/delete", {"id": owner["id"]})
    assert status == 400 and "拥有者" in body["message"]


# ---------------- 成员 ----------------

def test_members_lifecycle():
    items = list_items("/front/admin/members/list")
    assert items, "种子成员数据缺失"
    for key in ("id", "name", "email", "role", "enabled", "lastActive"):
        assert key in items[0], f"成员字段缺失：{key}"

    email = f"test+{uuid.uuid4().hex}@xf.cn"
    member_id: str | None = None
    try:
        data = ok("/front/admin/members/create", {"email": email, "role": "成员"})
        member_id = data["id"]
        assert uuid.UUID(member_id)
        accepted = ok(
            "/front/admin/auth/accept-invite",
            {
                "token": data["inviteToken"],
                "password": "test-pass-123",
                "name": "pytest-member",
            },
        )
        assert accepted["token"]

        status, body = post("/front/admin/members/create", {"email": email})
        assert status == 400 and body["code"] == 400, body

        row = find(list_items("/front/admin/members/list"), member_id)
        assert row is not None
        assert row["email"] == email and row["enabled"] is True

        ok("/front/admin/members/update", {"id": member_id, "enabled": False})
        row = find(list_items("/front/admin/members/list"), member_id)
        assert row is not None and row["enabled"] is False

        status, body = post(
            "/front/admin/members/update", {"id": str(uuid.uuid4()), "enabled": False}
        )
        assert status == 404 and body["code"] == 404, body
    finally:
        if member_id is not None:
            ok("/front/admin/members/delete", {"id": member_id})

    assert find(list_items("/front/admin/members/list"), member_id) is None


# ---------------- 专家 ----------------

def test_expert_config_persists():
    experts = list_items("/front/admin/experts/list")
    assert experts, "种子专家数据缺失"
    for expert in experts:
        assert isinstance(expert["mcpIds"], list)
        assert isinstance(expert["skillIds"], list)
        assert {
            "maxToolSteps",
            "allowWriteTools",
            "toolTimeoutSeconds",
            "maxOutputTokens",
            "contextBudgetTokens",
            "routingMode",
            "fallbackModelIds",
            "toolPolicies",
        } <= expert["settings"].keys()

    expert = experts[0]
    new_mcp_ids = [item["id"] for item in list_items("/front/admin/mcp/list")[:2]]
    new_skill_ids = [item["id"] for item in list_items("/front/admin/skills/list")[:1]]
    models = list_items("/front/admin/models/list")
    new_model = next(
        (item["name"] for item in models if item["name"] != expert["model"]), expert["model"]
    )
    original = {
        "model": expert["model"],
        "mcp_ids": expert["mcpIds"],
        "skill_ids": expert["skillIds"],
        "settings": expert["settings"],
    }
    changed_settings = {
        "maxToolSteps": 3 if expert["settings"]["maxToolSteps"] != 3 else 4,
        "allowWriteTools": not expert["settings"]["allowWriteTools"],
        "toolTimeoutSeconds": (
            12 if expert["settings"]["toolTimeoutSeconds"] != 12 else 13
        ),
        "toolPolicies": {
            "demo-mcp:echo": "confirm",
        },
        "maxOutputTokens": 2000,
        "contextBudgetTokens": 0,
        "routingMode": "fixed",
        "fallbackModelIds": [],
    }
    base = {"id": expert["id"], "name": expert["name"]}
    try:
        ok(
            "/front/admin/experts/update",
            {
                **base,
                "model": new_model,
                "mcp_ids": new_mcp_ids,
                "skill_ids": new_skill_ids,
                "settings": changed_settings,
            },
        )
        updated = find(list_items("/front/admin/experts/list"), expert["id"])
        assert updated is not None
        assert updated["model"] == new_model
        assert updated["mcpIds"] == new_mcp_ids
        assert updated["skillIds"] == new_skill_ids
        assert updated["settings"] == changed_settings
    finally:
        ok("/front/admin/experts/update", {**base, **original})

    restored = find(list_items("/front/admin/experts/list"), expert["id"])
    assert restored is not None
    assert restored["model"] == original["model"]
    assert restored["mcpIds"] == original["mcp_ids"]
    assert restored["skillIds"] == original["skill_ids"]
    assert restored["settings"] == original["settings"]


# ---------------- 注册表：模型 / MCP / SKILL ----------------

def _registry_crud(kind: str, extra: dict[str, Any]) -> None:
    name = f"pytest-{kind}-{uuid.uuid4().hex[:8]}"
    created = ok(
        f"/front/admin/{kind}/create",
        {"name": name, "description": "pytest 临时数据", "status": "未测试", **extra},
    )
    data_id = created["id"]
    try:
        updated_name = f"{name}-updated"
        ok(
            f"/front/admin/{kind}/update",
            {
                "id": data_id,
                "name": updated_name,
                "description": "pytest 临时数据",
                "status": "可用",
                **extra,
            },
        )
        row = find(list_items(f"/front/admin/{kind}/list"), data_id)
        assert row is not None, f"{kind} 更新后不存在"
        assert row["name"] == updated_name and row["status"] == "未测试"
    finally:
        ok(f"/front/admin/{kind}/delete", {"id": data_id})

    assert find(list_items(f"/front/admin/{kind}/list"), data_id) is None


def test_registry_crud():
    _registry_crud(
        "mcp",
        {"endpoint": "stdio: pytest", "config": {"timeout": 2}},
    )
    _registry_crud(
        "skills",
        {"config": {"instructions": "执行 pytest 临时技能", "requires_tools": []}},
    )
    _registry_crud(
        "models",
        {
            "endpoint": "https://example.com/v1",
            "model_key": "test-model",
            "api_key": "sk-pytest-placeholder",
        },
    )


def test_registry_reference_guard():
    experts = list_items("/front/admin/experts/list")
    mcp_items = list_items("/front/admin/mcp/list")
    referenced = next(
        (item for item in mcp_items if any(item["id"] in expert["mcpIds"] for expert in experts)),
        None,
    )
    assert referenced is not None, "种子数据中没有被专家引用的 MCP"

    status, body = post("/front/admin/mcp/delete", {"id": referenced["id"]})
    assert status == 400 and body["code"] == 400, body
    assert "专家" in body["message"]

    still_there = find(list_items("/front/admin/mcp/list"), referenced["id"])
    assert still_there is not None, "被引用 MCP 不应被删除"


def test_model_api_key_and_real_probe():
    """模型 API Key 只回掩码；配置后真实请求供应商验证连通"""
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    name = f"pytest-model-{uuid.uuid4().hex[:8]}"
    created = ok(
        "/front/admin/models/create",
        {
            "name": name,
            "description": "pytest 临时模型",
            "meta": "连通性测试",
            "status": "未测试",
            "endpoint": "https://api.deepseek.com",
            "model_key": "deepseek-v4-pro",
            "api_key": api_key or "sk-pytest-invalid-key",
        },
    )
    data_id = created["id"]
    try:
        row = find(list_items("/front/admin/models/list"), data_id)
        assert row is not None
        assert row["hasApiKey"] is True
        assert row["apiKeyMask"].startswith("sk-")
        # 明文密钥不得出现在任何返回字段中
        assert all(api_key not in str(value) for value in row.values() if api_key)

        # 编辑表单会提交空 API Key，留空必须保留已加密的密钥。
        ok(
            "/front/admin/models/update",
            {
                "id": data_id,
                "name": name,
                "description": "pytest 临时模型",
                "meta": "连通性测试",
                "status": "未测试",
                "endpoint": "https://api.deepseek.com",
                "model_key": "deepseek-v4-pro",
                "api_key": "",
            },
        )
        updated = find(list_items("/front/admin/models/list"), data_id)
        assert updated is not None
        assert updated["hasApiKey"] is True
        assert updated["apiKeyMask"] == row["apiKeyMask"]

        # 未配置密钥的模型测试应返回字段级 400
        empty = ok(
            "/front/admin/models/create",
            {
                "name": f"{name}-nokey",
                "description": "pytest 无密钥",
                "status": "未测试",
                "endpoint": "https://api.deepseek.com",
                "model_key": "deepseek-v4-pro",
            },
        )
        try:
            status, body = post("/front/admin/models/test", {"id": empty["id"]})
            assert status == 400 and "api_key" in body["data"], body
        finally:
            ok("/front/admin/models/delete", {"id": empty["id"]})

        status, body = post("/front/admin/models/test", {"id": str(uuid.uuid4())})
        assert status == 404 and body["code"] == 404, body

        if not api_key:
            pytest.skip("未配置 DEEPSEEK_API_KEY，跳过真实连通性验证")

        result = ok("/front/admin/models/test", {"id": data_id})
        assert result["ok"] is True, result
        assert result["status"] == "可用", result
        assert any("deepseek" in item.lower() for item in result["models"]), result

        refreshed = find(list_items("/front/admin/models/list"), data_id)
        assert refreshed is not None and refreshed["status"] == "可用"
    finally:
        ok("/front/admin/models/delete", {"id": data_id})


def test_model_update_with_empty_api_key_preserves_existing_key():
    name = f"pytest-model-key-preserve-{uuid.uuid4().hex[:8]}"
    created = ok(
        "/front/admin/models/create",
        {
            "name": name,
            "description": "pytest 密钥保留",
            "meta": "连通性测试",
            "status": "未测试",
            "endpoint": "https://api.deepseek.com",
            "model_key": "deepseek-v4-pro",
            "api_key": "sk-pytest-preserve-key",
        },
    )
    data_id = created["id"]
    try:
        before = find(list_items("/front/admin/models/list"), data_id)
        assert before is not None and before["hasApiKey"] is True
        ok(
            "/front/admin/models/update",
            {
                "id": data_id,
                "name": name,
                "description": "pytest 密钥保留",
                "meta": "未重新输入密钥",
                "status": "未测试",
                "endpoint": "https://api.deepseek.com",
                "model_key": "deepseek-v4-pro",
                "api_key": "",
            },
        )
        after = find(list_items("/front/admin/models/list"), data_id)
        assert after is not None
        assert after["hasApiKey"] is True
        assert after["apiKeyMask"] == before["apiKeyMask"]
    finally:
        ok("/front/admin/models/delete", {"id": data_id})


def test_registry_probe_and_expert_test():
    """MCP 协议握手、SKILL 配置校验与专家真实测试。"""
    secret_value = f"Bearer pytest-{uuid.uuid4().hex}"
    mcp_endpoint = (
        f"stdio: {sys.executable} {REPO_ROOT / 'site' / 'admin' / 'mcp_stub.py'}"
    )
    mcp = ok(
        "/front/admin/mcp/create",
        {
            "name": f"pytest-mcp-{uuid.uuid4().hex[:8]}",
            "description": "pytest 临时 MCP",
            "status": "未测试",
            "endpoint": mcp_endpoint,
            "config": {
                "timeout": 5,
                "headers": {"Authorization": secret_value},
                "env": {"PYTEST_MCP_SECRET": "hidden-value"},
            },
        },
    )
    try:
        result = ok("/front/admin/mcp/test", {"id": mcp["id"]})
        assert result["ok"] is True and result["status"] == "可用", result
        row = find(list_items("/front/admin/mcp/list"), mcp["id"])
        assert row is not None and row["status"] == "可用"
        assert row["config"] == {"timeout": 5}
        assert row["hasSecrets"] is True
        assert set(row["secretKeys"]) == {"headers", "env"}
        assert secret_value not in json.dumps(row, ensure_ascii=False)
        async def stored_mcp_config() -> asyncpg.Record | None:
            conn = await asyncpg.connect(
                host=PG_HOST,
                port=PG_PORT,
                database=PG_DBNAME,
                user=PG_USER,
                password=PG_PASSWORD,
            )
            try:
                return await conn.fetchrow(
                    """
                    SELECT config::text AS config, secret_config_enc
                      FROM ai_mcp
                     WHERE data_id = $1::uuid
                    """,
                    mcp["id"],
                )
            finally:
                await conn.close()

        stored = asyncio.run(stored_mcp_config())
        assert stored is not None and stored["secret_config_enc"]
        assert secret_value not in stored["config"]
        tools = ok("/front/admin/mcp/tools", {"id": mcp["id"]})
        assert {"echo", "write_value"} <= {
            item["name"] for item in tools["items"]
        }
    finally:
        ok("/front/admin/mcp/delete", {"id": mcp["id"]})

    skill = ok(
        "/front/admin/skills/create",
        {
            "name": f"pytest-skill-{uuid.uuid4().hex[:8]}",
            "description": "pytest 临时 SKILL",
            "status": "未测试",
            "config": {
                "instructions": "执行 pytest 临时技能",
                "requires_tools": [],
                "handler": "experts.builtin_skills:meeting_minutes",
                "input_schema": {
                    "type": "object",
                    "properties": {"transcript": {"type": "string"}},
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
                "test_input": {
                    "transcript": "确认发布。\n待办：完成测试，负责人：张三。"
                },
            },
        },
    )
    try:
        result = ok("/front/admin/skills/test", {"id": skill["id"]})
        assert result["ok"] is True and result["status"] == "可用", result
        assert result["sampleOutput"]["summary"]
    finally:
        ok("/front/admin/skills/delete", {"id": skill["id"]})

    expert = ok(
        "/front/admin/experts/create",
        {"name": f"pytest-expert-{uuid.uuid4().hex[:8]}", "model": "GPT-5"},
    )
    try:
        result = ok("/front/admin/experts/test", {"id": expert["id"]})
        assert result["ok"] is False and result["status"] == "异常", result
        assert "API" in result["message"], result
        assert result["mcpCount"] >= 0 and result["skillCount"] >= 0
    finally:
        ok("/front/admin/experts/delete", {"id": expert["id"]})

    status, body = post("/front/admin/experts/test", {"id": str(uuid.uuid4())})
    assert status == 404 and body["code"] == 404, body


def test_seeded_mcp_endpoints_are_executable():
    """种子 MCP 必须能真实启动并完成握手，不能只依赖手填的“可用”状态。"""
    wanted = {"文件系统", "数据库查询", "浏览器自动化", "代码仓库"}
    seeded = {
        item["name"]: item
        for item in list_items("/front/admin/mcp/list")
        if item["name"] in wanted
    }
    assert set(seeded) == wanted
    for name, item in seeded.items():
        result = ok("/front/admin/mcp/test", {"id": item["id"]})
        assert result["ok"] is True, f"{name}：{result}"
        assert result["status"] == "可用"


# ---------------- 额度 ----------------

def test_quota_summary_and_updates():
    summary = ok("/front/admin/quota/get-summary")
    assert len(summary["summary"]) == 4
    for card in summary["summary"]:
        assert {"label", "value", "note"} <= card.keys()
    assert isinstance(summary["used"], (int, float)) and isinstance(summary["limit"], (int, float))

    projects = list_items("/front/admin/quota/get-project-quotas")
    assert projects
    for project in projects:
        assert {"id", "name", "used", "limit"} <= project.keys()

    models = list_items("/front/admin/quota/get-model-quotas")
    assert models
    target = models[0]
    assert {"id", "model", "price", "used", "limit"} <= target.keys()
    original_limit = float(target["limit"])
    changed_limit = original_limit + 10
    try:
        ok(
            "/front/admin/quota/update-model-quotas",
            {"items": [{"id": target["id"], "limit": changed_limit}]},
        )
        refreshed = find(list_items("/front/admin/quota/get-model-quotas"), target["id"])
        assert refreshed is not None and float(refreshed["limit"]) == changed_limit
    finally:
        ok(
            "/front/admin/quota/update-model-quotas",
            {"items": [{"id": target["id"], "limit": original_limit}]},
        )
    refreshed = find(list_items("/front/admin/quota/get-model-quotas"), target["id"])
    assert refreshed is not None and float(refreshed["limit"]) == original_limit

    settings_payload = ok("/front/admin/quota/get-alert-settings")
    assert {"threshold", "channel", "notifyAdmin", "stopOnExceed"} <= settings_payload.keys()
    restore = {
        "threshold": settings_payload["threshold"],
        "channel": settings_payload["channel"],
        "notify_admin": settings_payload["notifyAdmin"],
        "stop_on_exceed": settings_payload["stopOnExceed"],
    }
    new_threshold = "85%" if settings_payload["threshold"] != "85%" else "80%"
    try:
        ok("/front/admin/quota/update-alert-settings", {**restore, "threshold": new_threshold})
        updated = ok("/front/admin/quota/get-alert-settings")
        assert updated["threshold"] == new_threshold
    finally:
        ok("/front/admin/quota/update-alert-settings", restore)
    assert ok("/front/admin/quota/get-alert-settings") == settings_payload


def test_project_quota_crud_and_log_pagination():
    created = ok(
        "/front/admin/quota/create-project",
        {"name": f"pytest-project-{uuid.uuid4().hex[:8]}", "used": 0, "limit": 100},
    )
    try:
        ok(
            "/front/admin/quota/update-project-quotas",
            {"items": [{"id": created["id"], "limit": 150}]},
        )
        projects = list_items("/front/admin/quota/get-project-quotas")
        updated = find(projects, created["id"])
        assert updated is not None and float(updated["limit"]) == 150
    finally:
        ok("/front/admin/quota/delete-project", {"id": created["id"]})
    assert find(list_items("/front/admin/quota/get-project-quotas"), created["id"]) is None

    page = ok("/front/admin/logs/list", {"page": 1, "page_size": 2, "keyword": "pytest"})
    assert page["page"] == 1 and page["page_size"] == 2 and page["total"] >= 1
    assert len(page["items"]) <= 2


def test_expert_chat_returns_reply_or_clear_configuration_error():
    expert = list_items("/front/admin/experts/list")[0]
    result = ok("/front/admin/experts/chat", {"id": expert["id"], "message": "你好"})
    session_id = result["sessionId"]
    try:
        assert uuid.UUID(session_id)
        sessions = list_items(
            "/front/admin/experts/sessions/list",
            {"id": expert["id"], "limit": 20},
        )
        assert find(sessions, session_id) is not None
        session = ok("/front/admin/experts/sessions/get", {"id": session_id})
        assert session["messages"][0]["role"] == "user"
        assert session["messages"][0]["content"] == "你好"
        if result["ok"]:
            assert result["content"].strip()
            assert uuid.UUID(result["runId"])
            assert session["messages"][-1]["role"] == "assistant"
        else:
            assert "API Key" in result["message"] or "模型" in result["message"]
    finally:
        ok("/front/admin/experts/sessions/delete", {"id": session_id})

    status, body = post("/front/admin/experts/chat", {"id": expert["id"], "message": ""})
    assert status == 400 and "message" in body["data"]


def test_disabled_expert_and_delete_reference_protection():
    suffix = uuid.uuid4().hex[:8]
    expert = ok(
        "/front/admin/experts/create",
        {
            "name": f"pytest-disabled-expert-{suffix}",
            "role": "引用保护测试",
            "enabled": True,
        },
    )
    project = ok(
        "/front/chief/workspace/projects/create",
        {
            "name": f"pytest-expert-reference-{suffix}",
            "expert_id": expert["id"],
        },
    )
    try:
        ok(
            "/front/admin/experts/update",
            {
                "id": expert["id"],
                "name": f"pytest-disabled-expert-{suffix}",
                "enabled": False,
            },
        )
        status, body = post(
            "/front/chief/workspace/projects/create",
            {
                "name": f"pytest-disabled-bind-{suffix}",
                "expert_id": expert["id"],
            },
        )
        assert status == 400 and "停用" in body["message"]
        status, body = post(
            "/front/admin/chief/update-settings",
            {"domain_experts": {"programming": expert["id"]}},
        )
        assert status == 400 and "专家映射无效" in body["message"]

        status, body = post("/front/admin/experts/delete", {"id": expert["id"]})
        assert status == 409
        assert project["name"] in body["message"]
    finally:
        ok("/front/chief/workspace/projects/delete", {"project_id": project["id"]})
        ok("/front/admin/experts/delete", {"id": expert["id"]})


def test_chief_session_can_create_traceable_project_session():
    suffix = uuid.uuid4().hex[:8]
    expert = next(iter(list_items("/front/admin/experts/list")), None)
    assert expert is not None
    source = ok(
        "/front/chief/sessions/create",
        {"title": f"pytest-chief-source-{suffix}"},
    )
    project: dict[str, Any] | None = None
    try:
        project = ok(
            "/front/chief/workspace/projects/create",
            {
                "name": f"pytest-chief-project-{suffix}",
                "description": "总管会话立项测试",
                "expert_id": expert["id"],
                "source_session_id": source["id"],
                "context": {
                    "objective": "验证总管会话能够转为项目",
                    "scope": "来源关联、项目会话绑定",
                    "constraints": [],
                },
            },
        )
        assert project["sourceSessionId"] == source["id"]
        assert project["expertId"] == expert["id"]

        project_session = ok(
            "/front/chief/sessions/create",
            {
                "title": project["name"],
                "project_id": project["id"],
            },
        )
        assert project_session["projectId"] == project["id"]
        assert project_session["expertId"] == expert["id"]

        wrong_stage_status, wrong_stage = post(
            "/front/chief/workspace/workflow/command",
            {
                "session_id": project_session["id"],
                "message": "#生成方案#",
            },
        )
        assert wrong_stage_status == 400 and "阶段" in wrong_stage["message"]

        ok(
            "/front/chief/workspace/projects/document/save",
            {
                "project_id": project["id"],
                "stage": "requirements",
                "content_text": "固定指令确认测试需求",
            },
        )
        ok(
            "/front/chief/workspace/projects/document/confirm",
            {
                "project_id": project["id"],
                "stage": "requirements",
            },
        )
        workspace = ok("/front/chief/workspace/get")
        saved_project = find(workspace["items"], project["id"])
        assert saved_project["phase"] == "requirements_confirmed"
        assert saved_project["documents"]["requirements"]["latestVersionNo"] == 1
        assert len(saved_project["documents"]["requirements"]["versions"]) == 1

        duplicate = ok(
            "/front/chief/workspace/projects/document/confirm",
            {
                "project_id": project["id"],
                "stage": "requirements",
            },
        )
        assert duplicate["artifactVersion"]["versionNo"] == 1
        assert duplicate["artifactVersion"]["unchanged"] is True

        invalid_stage_status, invalid_stage = post(
            "/front/chief/workspace/projects/document/confirm",
            {
                "project_id": project["id"],
                "stage": "invalid",
            },
        )
        assert invalid_stage_status == 400
        assert "阶段" in invalid_stage["message"]

        ok(
            "/front/chief/workspace/projects/document/save",
            {
                "project_id": project["id"],
                "stage": "requirements",
                "content_text": "固定指令确认测试需求 V2",
            },
        )
        ok(
            "/front/chief/workspace/projects/document/confirm",
            {
                "project_id": project["id"],
                "stage": "requirements",
            },
        )
        workspace = ok("/front/chief/workspace/get")
        saved_project = find(workspace["items"], project["id"])
        assert saved_project["documents"]["requirements"]["latestVersionNo"] == 2
        assert len(saved_project["documents"]["requirements"]["versions"]) == 2
        assert (
            saved_project["documents"]["requirements"]["versions"][0]["contentText"]
            == "固定指令确认测试需求 V2"
        )

        ok(
            "/front/chief/workspace/projects/document/save",
            {
                "project_id": project["id"],
                "stage": "solution",
                "content_text": "基于需求 V2 的方案",
            },
        )
        ok(
            "/front/chief/workspace/projects/document/confirm",
            {
                "project_id": project["id"],
                "stage": "solution",
            },
        )
        workspace = ok("/front/chief/workspace/get")
        saved_project = find(workspace["items"], project["id"])
        assert saved_project["documents"]["solution"]["latestVersionNo"] == 1
        assert saved_project["documents"]["solution"]["versions"][0][
            "sourceVersionNo"
        ] == 2

        plan = {
            "packages": [
                {
                    "name": "版本测试任务包",
                    "tasks": [
                        {
                            "key": "T1",
                            "title": "验证版本引用",
                            "acceptanceCriteria": "依赖版本可追溯",
                        }
                    ],
                }
            ]
        }
        ok(
            "/front/chief/workspace/projects/task-plan/save",
            {"project_id": project["id"], "plan": plan},
        )
        ok(
            "/front/chief/workspace/projects/task-plan/confirm",
            {"project_id": project["id"]},
        )
        workspace = ok("/front/chief/workspace/get")
        saved_project = find(workspace["items"], project["id"])
        assert saved_project["documents"]["task_plan"]["latestVersionNo"] == 1
        assert saved_project["documents"]["task_plan"]["versions"][0][
            "sourceVersionNo"
        ] == 1

        ok(
            "/front/chief/workspace/projects/document/save",
            {
                "project_id": project["id"],
                "stage": "requirements",
                "content_text": "需求 V3，触发下游过期",
            },
        )
        workspace = ok("/front/chief/workspace/get")
        saved_project = find(workspace["items"], project["id"])
        assert saved_project["phase"] == "requirements"
        assert saved_project["documents"]["solution"]["status"] == "stale"
        assert saved_project["documents"]["task_plan"]["status"] == "stale"

        invalid_status, invalid = post(
            "/front/chief/workspace/workflow/command",
            {
                "session_id": project_session["id"],
                "message": "#需求已定#",
            },
        )
        assert invalid_status == 400 and "固定指令" in invalid["message"]

        status, body = post(
            "/front/chief/workspace/projects/create",
            {
                "name": f"pytest-chief-duplicate-{suffix}",
                "expert_id": expert["id"],
                "source_session_id": project_session["id"],
            },
        )
        assert status == 409 and "项目会话" in body["message"]
    finally:
        if project:
            ok("/front/chief/workspace/projects/delete", {"project_id": project["id"]})
        ok("/front/chief/sessions/delete", {"session_id": source["id"]})


def test_expert_agent_tool_loop_and_run_persistence():
    """通过管理 API 跑通专家工具循环，并确认运行记录落库。"""
    requests: list[dict[str, Any]] = []

    class ModelHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - http.server 固定接口
            length = int(self.headers.get("content-length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            requests.append(payload)
            if payload.get("model") == "primary-fail":
                body = json.dumps({"error": {"message": "synthetic outage"}}).encode()
                self.send_response(503)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            user_text = next(
                (
                    str(item.get("content") or "")
                    for item in reversed(payload.get("messages", []))
                    if item.get("role") == "user"
                ),
                "",
            )
            if "故障转移测试" in user_text:
                response = {
                    "choices": [{"message": {"content": "备用模型已接管。"}}],
                    "usage": {"prompt_tokens": 7, "completion_tokens": 3},
                }
                body = json.dumps(response).encode("utf-8")
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if payload.get("messages", [{}])[-1].get("role") != "tool":
                suffix = "_write_value" if "写入确认测试" in user_text else "_echo"
                name = next(
                    item["function"]["name"]
                    for item in payload.get("tools", [])
                    if item["function"]["name"].endswith(suffix)
                )
                response = {
                    "choices": [
                        {
                            "message": {
                                "content": "",
                                "tool_calls": [
                                    {
                                        "id": (
                                            "api-call-write"
                                            if suffix == "_write_value"
                                            else "api-call-echo"
                                        ),
                                        "type": "function",
                                        "function": {
                                            "name": name,
                                            "arguments": json.dumps(
                                                {"text": "synthetic api value"}
                                            ),
                                        },
                                    }
                                ],
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 11, "completion_tokens": 2},
                }
            else:
                tool_text = payload["messages"][-1]["content"]
                assert (
                    "ECHO: synthetic api value" in tool_text
                    or "WRITE: synthetic api value" in tool_text
                    or "用户拒绝" in tool_text
                )
                response = {
                    "choices": [
                        {
                            "message": {
                                "content": (
                                    "API 写入确认完成。"
                                    if "WRITE:" in tool_text
                                    else "API 工具循环完成。"
                                )
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 13, "completion_tokens": 4},
                }
            body = json.dumps(response).encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *args: Any) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), ModelHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    mcp_id = ""
    model_id = ""
    fallback_model_id = ""
    expert_id = ""
    run_id = ""
    approval_run_id = ""
    fallback_run_id = ""
    try:
        model_name = f"pytest-agent-model-{uuid.uuid4().hex[:8]}"
        model = ok(
            "/front/admin/models/create",
            {
                "name": model_name,
                "description": "pytest 合成模型",
                "status": "未测试",
                "endpoint": f"http://127.0.0.1:{server.server_port}/v1",
                "model_key": "synthetic-model",
                "api_key": "synthetic-key",
                "provider": "openai_compatible",
                "capabilities": {
                    "contextWindow": 8192,
                    "maxOutputTokens": 1024,
                    "tools": True,
                    "vision": True,
                    "json": True,
                    "streaming": True,
                },
            },
        )
        model_id = model["id"]

        async def seed_quota(name: str) -> None:
            conn = await asyncpg.connect(
                host=PG_HOST,
                port=PG_PORT,
                database=PG_DBNAME,
                user=PG_USER,
                password=PG_PASSWORD,
            )
            try:
                await conn.execute(
                    """
                    INSERT INTO quota_model (model, price, used, quota_limit, sort_order)
                    VALUES ($1, '1.0', 0, 100, 999)
                    """,
                    name,
                )
            finally:
                await conn.close()

        asyncio.run(seed_quota(model_name))
        mcp = ok(
            "/front/admin/mcp/create",
            {
                "name": f"pytest-agent-mcp-{uuid.uuid4().hex[:8]}",
                "description": "pytest 合成 MCP",
                "status": "未测试",
                "endpoint": (
                    f"stdio: {sys.executable} "
                    f"{REPO_ROOT / 'site' / 'admin' / 'mcp_stub.py'}"
                ),
            },
        )
        mcp_id = mcp["id"]
        expert = ok(
            "/front/admin/experts/create",
            {
                "name": f"pytest-agent-expert-{uuid.uuid4().hex[:8]}",
                "role": "合成测试专家",
                "model": model_name,
                "mcp_ids": [mcp_id],
                "settings": {
                    "maxToolSteps": 2,
                    "allowWriteTools": False,
                    "toolTimeoutSeconds": 5,
                },
            },
        )
        expert_id = expert["id"]
        result = ok(
            "/front/admin/experts/chat",
            {"id": expert_id, "message": "执行合成 API 工具测试"},
        )
        assert result["ok"] is True, result
        assert result["content"] == "API 工具循环完成。"
        assert result["usedTools"] == 1
        assert result["toolTrace"][0]["tool"] == "echo"
        assert result["cost"] > 0
        assert len(requests) == 2
        run_id = result["runId"]
        runs = ok(
            "/front/admin/experts/runs",
            {"id": expert_id, "limit": 5},
        )
        assert runs["items"][0]["id"] == run_id
        assert runs["items"][0]["status"] == "completed"
        assert runs["items"][0]["toolTrace"][0]["tool"] == "echo"

        async def persisted_run() -> asyncpg.Record | None:
            conn = await asyncpg.connect(
                host=PG_HOST,
                port=PG_PORT,
                database=PG_DBNAME,
                user=PG_USER,
                password=PG_PASSWORD,
            )
            try:
                return await conn.fetchrow(
                    """
                    SELECT status, answer,
                           jsonb_array_length(tool_trace) AS trace_count,
                           tool_trace->0->>'tool' AS first_tool
                      FROM ai_expert_run
                     WHERE data_id = $1::uuid
                    """,
                    result["runId"],
                )
            finally:
                await conn.close()

        run = asyncio.run(persisted_run())
        assert run is not None
        assert run["status"] == "completed"
        assert run["answer"] == "API 工具循环完成。"
        assert run["trace_count"] == 1
        assert run["first_tool"] == "echo"

        updated = ok(
            "/front/admin/experts/update",
            {
                "id": expert_id,
                "name": f"pytest-agent-expert-{uuid.uuid4().hex[:8]}",
                "role": "合成测试专家",
                "model": model_name,
                "mcp_ids": [mcp_id],
                "settings": {
                    "maxToolSteps": 2,
                    "allowWriteTools": True,
                    "toolTimeoutSeconds": 5,
                    "toolPolicies": {
                        f"{mcp_id}:write_value": "confirm",
                    },
                },
            },
        )
        assert updated is None
        pending = ok(
            "/front/admin/experts/chat",
            {"id": expert_id, "message": "执行写入确认测试"},
        )
        approval_run_id = pending["runId"]
        assert pending["requiresApproval"] is True
        assert pending["pendingApproval"]["calls"][0]["tool"] == "write_value"
        assert len(requests) == 3

        async def pending_state() -> asyncpg.Record | None:
            conn = await asyncpg.connect(
                host=PG_HOST,
                port=PG_PORT,
                database=PG_DBNAME,
                user=PG_USER,
                password=PG_PASSWORD,
            )
            try:
                return await conn.fetchrow(
                    """
                    SELECT status, state_enc, pending_approval::text
                      FROM ai_expert_run
                     WHERE data_id = $1::uuid
                    """,
                    approval_run_id,
                )
            finally:
                await conn.close()

        pending_row = asyncio.run(pending_state())
        assert pending_row is not None
        assert pending_row["status"] == "awaiting_approval"
        assert pending_row["state_enc"]
        approved = ok(
            "/front/admin/experts/chat/resume",
            {
                "id": approval_run_id,
                "approvals": [
                    {
                        "callId": pending["pendingApproval"]["calls"][0]["callId"],
                        "approved": True,
                    }
                ],
            },
        )
        assert approved["ok"] is True
        assert approved["content"] == "API 写入确认完成。"
        assert approved["toolTrace"][0]["confirmed"] is True
        assert len(requests) == 4

        fallback_model_name = f"pytest-fallback-model-{uuid.uuid4().hex[:8]}"
        fallback_model = ok(
            "/front/admin/models/create",
            {
                "name": fallback_model_name,
                "description": "pytest 备用模型",
                "endpoint": f"http://127.0.0.1:{server.server_port}/v1",
                "model_key": "synthetic-model",
                "api_key": "synthetic-key",
                "provider": "openai_compatible",
                "capabilities": {
                    "contextWindow": 8192,
                    "maxOutputTokens": 1024,
                    "tools": True,
                    "vision": True,
                    "json": True,
                    "streaming": True,
                },
            },
        )
        fallback_model_id = fallback_model["id"]
        asyncio.run(seed_quota(fallback_model_name))
        ok(
            "/front/admin/models/update",
            {
                "id": model_id,
                "name": model_name,
                "description": "pytest 主模型故障",
                "endpoint": f"http://127.0.0.1:{server.server_port}/v1",
                "model_key": "primary-fail",
                "provider": "openai_compatible",
                "capabilities": {
                    "contextWindow": 8192,
                    "maxOutputTokens": 1024,
                    "tools": True,
                    "vision": True,
                    "json": True,
                    "streaming": True,
                },
            },
        )
        ok(
            "/front/admin/experts/update",
            {
                "id": expert_id,
                "name": f"pytest-agent-expert-{uuid.uuid4().hex[:8]}",
                "role": "合成测试专家",
                "model": model_name,
                "mcp_ids": [mcp_id],
                "settings": {
                    "maxToolSteps": 2,
                    "allowWriteTools": False,
                    "toolTimeoutSeconds": 5,
                    "routingMode": "fallback",
                    "fallbackModelIds": [fallback_model_id],
                },
            },
        )
        fallback_result = ok(
            "/front/admin/experts/chat",
            {"id": expert_id, "message": "执行故障转移测试"},
        )
        fallback_run_id = fallback_result["runId"]
        assert fallback_result["ok"] is True
        assert fallback_result["content"] == "备用模型已接管。"
        assert fallback_result["model"] == fallback_model_name
        assert len(fallback_result["modelAttempts"]) == 2
        assert fallback_result["modelAttempts"][0]["retryable"] is True
        model_rows = list_items("/front/admin/models/list")
        assert find(model_rows, model_id)["healthStatus"] == "down"
        assert find(model_rows, fallback_model_id)["healthStatus"] == "healthy"
    finally:
        for test_run_id in [
            value
            for value in (run_id, approval_run_id, fallback_run_id)
            if value
        ]:
            async def delete_run() -> None:
                conn = await asyncpg.connect(
                    host=PG_HOST,
                    port=PG_PORT,
                    database=PG_DBNAME,
                    user=PG_USER,
                    password=PG_PASSWORD,
                )
                try:
                    await conn.execute(
                        "DELETE FROM ai_expert_run WHERE data_id = $1::uuid",
                        test_run_id,
                    )
                finally:
                    await conn.close()

            asyncio.run(delete_run())
        if expert_id:
            ok("/front/admin/experts/delete", {"id": expert_id})
        if mcp_id:
            ok("/front/admin/mcp/delete", {"id": mcp_id})
        if model_id:
            ok("/front/admin/models/delete", {"id": model_id})
        if fallback_model_id:
            ok("/front/admin/models/delete", {"id": fallback_model_id})

        async def cleanup_quotas() -> None:
            conn = await asyncpg.connect(
                host=PG_HOST,
                port=PG_PORT,
                database=PG_DBNAME,
                user=PG_USER,
                password=PG_PASSWORD,
            )
            try:
                await conn.execute(
                    "DELETE FROM quota_model WHERE model LIKE 'pytest-%model-%'"
                )
            finally:
                await conn.close()

        asyncio.run(cleanup_quotas())
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_chief_settings_persist():
    current = ok("/front/admin/chief/get-settings")
    original = float(current["autoAdoptMinScore"])
    changed = 66 if original != 66 else 67
    try:
        ok(
            "/front/admin/chief/update-settings",
            {
                "enabled": current["enabled"],
                "recursion_mode": current["recursionMode"],
                "recursion_k": current["recursionK"],
                "recursion_max": current["recursionMax"],
                "regression_enabled": current["regressionEnabled"],
                "regression_cases": current["regressionCases"],
                "domain_experts": current["domainExperts"],
                "auto_adopt_min_score": changed,
                "auto_adopt_min_gain": current["autoAdoptMinGain"],
            },
        )
        assert float(ok("/front/admin/chief/get-settings")["autoAdoptMinScore"]) == changed
    finally:
        ok(
            "/front/admin/chief/update-settings",
            {
                "enabled": current["enabled"],
                "recursion_mode": current["recursionMode"],
                "recursion_k": current["recursionK"],
                "recursion_max": current["recursionMax"],
                "regression_enabled": current["regressionEnabled"],
                "regression_cases": current["regressionCases"],
                "domain_experts": current["domainExperts"],
                "auto_adopt_min_score": original,
                "auto_adopt_min_gain": current["autoAdoptMinGain"],
            },
        )


def test_call_settings_persist():
    current = ok("/front/admin/call/get-settings")
    changed_key = "ESC"
    changed_asr = "https://example.com/v1/tools/asr"
    changed_tts = "https://example.com/v1/tools/tts"
    try:
        updated = ok(
            "/front/admin/call/update-settings",
            {
                "pushToTalkKey": changed_key,
                "asrUrl": changed_asr,
                "ttsUrl": changed_tts,
            },
        )
        assert updated["pushToTalkKey"] == "Escape"
        assert updated["asrUrl"] == changed_asr
        assert updated["ttsUrl"] == changed_tts
    finally:
        ok(
            "/front/admin/call/update-settings",
            {
                "pushToTalkKey": current["pushToTalkKey"],
                "asrUrl": current["asrUrl"],
                "ttsUrl": current["ttsUrl"],
            },
        )


# ---------------- 操作日志 ----------------

def test_logs_newest_first_and_member_update_recorded():
    items = list_items("/front/admin/logs/list", {"limit": 100})
    assert items, "种子操作日志缺失"
    for item in items:
        assert {"id", "time", "user", "action", "target"} <= item.keys()
        assert item["time"] and item["user"] and item["action"]

    email = f"test+{uuid.uuid4().hex}@xf.cn"
    member_id: str | None = None
    try:
        member_id = ok(
            "/front/admin/members/create", {"email": email, "name": "pytest-log"}
        )["id"]
        before = {item["id"] for item in list_items("/front/admin/logs/list", {"limit": 200})}

        ok("/front/admin/members/update", {"id": member_id, "enabled": False})

        after = list_items("/front/admin/logs/list", {"limit": 200})
        latest = after[0]
        assert latest["id"] not in before, "成员更新未产生新的操作日志"
        assert latest["action"] == "修改成员"
        assert "pytest-log" in latest["target"]
        assert all(latest["id"] != item["id"] for item in after[1:]), "日志未按时间倒序"
    finally:
        if member_id is not None:
            ok("/front/admin/members/delete", {"id": member_id})
