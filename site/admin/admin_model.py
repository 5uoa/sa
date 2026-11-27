"""管理后台数据访问

表名无前缀；对外 id 统一使用 data_id::text。
"""
import json
import re
from decimal import Decimal
from typing import Any, List

import db
from common import json_value


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


class MemberModel:
    table_name = "admin_member"

    async def list(self) -> list[dict[str, Any]]:
        rows = await db.fetch(
            """
            SELECT data_id::text AS id, name, email, role, enabled,
                   last_active AS "lastActive",
                   CASE
                     WHEN password_hash = '' THEN 'invited'
                     WHEN must_change_password THEN 'password_change_required'
                     ELSE 'active'
                   END AS "accountStatus",
                   accepted_at AS "acceptedAt",
                   invitation_expires_at AS "invitationExpiresAt"
              FROM admin_member m
             WHERE is_deleted = false
             ORDER BY m.id ASC
            """
        )
        return db.to_dicts(rows)

    async def get(self, data_id: str) -> dict[str, Any] | None:
        row = await db.fetchrow(
            """
            SELECT data_id::text AS id, name, email, role, enabled,
                   last_active AS "lastActive",
                   password_hash, must_change_password,
                   invitation_token_hash, invitation_expires_at, accepted_at
              FROM admin_member
             WHERE data_id = $1::uuid AND is_deleted = false
             LIMIT 1
            """,
            data_id,
        )
        return db.to_dict(row)

    async def email_exists(self, email: str, exclude_id: str | None = None) -> bool:
        row = await db.fetchrow(
            """
            SELECT 1
              FROM admin_member
             WHERE lower(email) = lower($1) AND is_deleted = false
               AND ($2::uuid IS NULL OR data_id <> $2::uuid)
             LIMIT 1
            """,
            email,
            exclude_id,
        )
        return row is not None

    async def create(
        self,
        name: str,
        email: str,
        role: str,
        invitation_hash: str,
        invitation_expires_at: Any,
    ) -> dict[str, Any]:
        row = await db.fetchrow(
            """
            INSERT INTO admin_member (
                name, email, role, enabled, last_active,
                invitation_token_hash, invitation_expires_at
            )
            VALUES ($1, $2, $3, true, '待激活', $4, $5)
            RETURNING data_id::text AS id, invitation_expires_at
            """,
            name,
            email,
            role,
            invitation_hash,
            invitation_expires_at,
        )
        return dict(row)

    async def set_invitation(
        self, data_id: str, invitation_hash: str, invitation_expires_at: Any
    ) -> None:
        await db.execute(
            """
            UPDATE admin_member
               SET invitation_token_hash = $2,
                   invitation_expires_at = $3,
                   update_time = now()
             WHERE data_id = $1::uuid AND is_deleted = false
            """,
            data_id,
            invitation_hash,
            invitation_expires_at,
        )

    async def active_owner_count(self, exclude_id: str | None = None) -> int:
        return int(
            await db.fetchval(
                """
                SELECT count(*)
                  FROM admin_member
                 WHERE role = '拥有者'
                   AND enabled = true
                   AND is_deleted = false
                   AND ($1::uuid IS NULL OR data_id <> $1::uuid)
                """,
                exclude_id,
            )
            or 0
        )

    async def update_password(self, data_id: str, password_hash: str) -> None:
        await db.execute(
            """
            UPDATE admin_member
               SET password_hash = $2,
                   must_change_password = false,
                   accepted_at = COALESCE(accepted_at, now()),
                   update_time = now()
             WHERE data_id = $1::uuid AND is_deleted = false
            """,
            data_id,
            password_hash,
        )

    async def update(self, data_id: str, payload: dict[str, Any]) -> None:
        await db.execute(
            """
            UPDATE admin_member
               SET name = $2, email = $3, role = $4, enabled = $5, update_time = now()
             WHERE data_id = $1::uuid AND is_deleted = false
            """,
            data_id,
            payload["name"],
            payload["email"],
            payload["role"],
            payload["enabled"],
        )

    async def delete(self, data_id: str) -> None:
        await db.execute(
            """
            UPDATE admin_member
               SET is_deleted = true, update_time = now()
             WHERE data_id = $1::uuid AND is_deleted = false
            """,
            data_id,
        )


class ExpertModel:
    table_name = "ai_expert"

    async def list(self) -> list[dict[str, Any]]:
        rows = await db.fetch(
            """
            SELECT data_id::text AS id, name, role, model, temperature, prompt,
                   model_id::text AS model_id, enabled, mcp_ids, skill_ids, settings
              FROM ai_expert e
             WHERE is_deleted = false
             ORDER BY e.id ASC
            """
        )
        return db.to_dicts(rows)

    async def get(self, data_id: str) -> dict[str, Any] | None:
        row = await db.fetchrow(
            """
            SELECT data_id::text AS id, name, role, model, temperature, prompt,
                   model_id::text AS model_id, enabled, mcp_ids, skill_ids, settings
              FROM ai_expert
             WHERE data_id = $1::uuid AND is_deleted = false
             LIMIT 1
            """,
            data_id,
        )
        return db.to_dict(row)

    async def first_model_name(self) -> str:
        return (
            await db.fetchval(
                """
                SELECT name
                  FROM ai_model
                 WHERE is_deleted = false
                 ORDER BY id ASC
                 LIMIT 1
                """
            )
        ) or ""

    async def first_model(self) -> dict[str, Any] | None:
        row = await db.fetchrow(
            """
            SELECT data_id::text AS id, name, model_key, endpoint, status, api_key_enc
              FROM ai_model
             WHERE is_deleted = false
             ORDER BY id ASC
             LIMIT 1
            """
        )
        return db.to_dict(row)

    async def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = await db.fetchrow(
            """
            INSERT INTO ai_expert (
                name, role, model, model_id, temperature, prompt, enabled,
                mcp_ids, skill_ids, settings
            ) VALUES ($1, $2, $3, $4::uuid, $5, $6, $7, $8::jsonb, $9::jsonb, $10::jsonb)
            RETURNING data_id::text AS id
            """,
            payload["name"],
            payload["role"],
            payload["model"],
            payload["model_id"],
            payload["temperature"],
            payload["prompt"],
            payload["enabled"],
            _json(payload["mcp_ids"]),
            _json(payload["skill_ids"]),
            _json(payload.get("settings", {})),
        )
        return dict(row)

    async def update(self, data_id: str, payload: dict[str, Any]) -> None:
        await db.execute(
            """
            UPDATE ai_expert
               SET name = $2, role = $3, model = $4, model_id = $5::uuid,
                   temperature = $6, prompt = $7, enabled = $8,
                   mcp_ids = $9::jsonb, skill_ids = $10::jsonb,
                   settings = $11::jsonb,
                   update_time = now()
             WHERE data_id = $1::uuid AND is_deleted = false
            """,
            data_id,
            payload["name"],
            payload["role"],
            payload["model"],
            payload["model_id"],
            payload["temperature"],
            payload["prompt"],
            payload["enabled"],
            _json(payload["mcp_ids"]),
            _json(payload["skill_ids"]),
            _json(payload.get("settings", {})),
        )

    async def delete(self, data_id: str) -> None:
        async with db.transaction() as conn:
            await conn.execute(
                """
                UPDATE ai_expert_message
                   SET is_deleted = true
                 WHERE session_id IN (
                     SELECT data_id FROM ai_expert_session
                      WHERE expert_id = $1::uuid
                 )
                """,
                data_id,
            )
            await conn.execute(
                """
                UPDATE ai_expert_session
                   SET is_deleted = true, update_time = now()
                 WHERE expert_id = $1::uuid
                """,
                data_id,
            )
            await conn.execute(
                """
                UPDATE ai_expert
                   SET is_deleted = true, update_time = now()
                 WHERE data_id = $1::uuid AND is_deleted = false
                """,
                data_id,
            )

    async def reference_names(self, column: str, data_id: str) -> List[str]:
        """返回引用了该注册项的专家名称（MCP / SKILL 按 jsonb 数组匹配）"""
        rows = await db.fetch(
            f"""
            SELECT name
              FROM ai_expert
             WHERE is_deleted = false AND {column} ? $1::text
             ORDER BY name ASC
            """,
            data_id,
        )
        return [row["name"] for row in rows]

    async def model_reference_names(self, model_name: str) -> List[str]:
        rows = await db.fetch(
            """
            SELECT name
              FROM ai_expert
             WHERE is_deleted = false AND model = $1
             ORDER BY name ASC
            """,
            model_name,
        )
        return [row["name"] for row in rows]

    async def model_id_reference_names(self, model_id: str) -> List[str]:
        rows = await db.fetch(
            """
            SELECT name
              FROM ai_expert
             WHERE is_deleted = false AND model_id = $1::uuid
             ORDER BY name ASC
            """,
            model_id,
        )
        return [row["name"] for row in rows]

    async def reference_summary(self, data_id: str) -> dict[str, Any]:
        project_rows = await db.fetch(
            """
            SELECT name
              FROM chief_project
             WHERE expert_id = $1::uuid AND is_deleted = false
             ORDER BY name ASC
            """,
            data_id,
        )
        session_count = int(
            await db.fetchval(
                """
                SELECT count(*)
                  FROM chief_session
                 WHERE expert_id = $1::uuid AND is_deleted = false
                """,
                data_id,
            )
            or 0
        )
        domain_rows = await db.fetch(
            """
            SELECT item.key AS domain
              FROM chief_setting setting,
                   jsonb_each_text(setting.domain_experts) AS item
             WHERE item.value = $1
             ORDER BY item.key
            """,
            data_id,
        )
        return {
            "projects": [row["name"] for row in project_rows],
            "chief_sessions": session_count,
            "domains": [row["domain"] for row in domain_rows],
        }


class ExpertSessionModel:
    async def create(
        self,
        expert_id: str,
        title: str,
        create_by: str | None,
        project_id: str | None = None,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        row = await db.fetchrow(
            """
            INSERT INTO ai_expert_session (
                expert_id, title, create_by, project_id, task_id
            )
            VALUES ($1::uuid, $2, $3::uuid, $4::uuid, $5::uuid)
            RETURNING data_id::text AS id, expert_id::text AS "expertId",
                      project_id::text AS "projectId",
                      task_id::text AS "taskId",
                      title, create_time AS "createTime",
                      update_time AS "updateTime"
            """,
            expert_id,
            title[:200] or "新会话",
            create_by,
            project_id,
            task_id,
        )
        return dict(row)

    async def get(
        self,
        session_id: str,
        create_by: str | None = None,
    ) -> dict[str, Any] | None:
        row = await db.fetchrow(
            """
            SELECT s.data_id::text AS id, s.expert_id::text AS "expertId",
                   s.project_id::text AS "projectId",
                   s.task_id::text AS "taskId",
                   s.title, s.create_by::text AS "createBy",
                   s.create_time AS "createTime", s.update_time AS "updateTime"
              FROM ai_expert_session s
             WHERE s.data_id = $1::uuid
               AND s.is_deleted = false
               AND (
                   s.create_by IS NULL
                   OR $2::uuid IS NULL
                   OR s.create_by = $2::uuid
               )
             LIMIT 1
            """,
            session_id,
            create_by,
        )
        return db.to_dict(row)

    async def list(
        self,
        expert_id: str,
        create_by: str | None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        rows = await db.fetch(
            """
            SELECT s.data_id::text AS id, s.expert_id::text AS "expertId",
                   s.title, s.create_time AS "createTime",
                   s.update_time AS "updateTime",
                   count(m.id) FILTER (WHERE m.is_deleted = false) AS "messageCount",
                   COALESCE((
                       SELECT left(message.content, 120)
                         FROM ai_expert_message message
                        WHERE message.session_id = s.data_id
                          AND message.is_deleted = false
                        ORDER BY message.id DESC
                        LIMIT 1
                   ), '') AS preview
              FROM ai_expert_session s
              LEFT JOIN ai_expert_message m ON m.session_id = s.data_id
             WHERE s.expert_id = $1::uuid
               AND s.is_deleted = false
               AND s.is_archived = false
               AND s.project_id IS NULL
               AND ($2::uuid IS NULL OR s.create_by = $2::uuid)
             GROUP BY s.id
             ORDER BY s.update_time DESC, s.id DESC
             LIMIT $3
            """,
            expert_id,
            create_by,
            max(1, min(100, limit)),
        )
        return db.to_dicts(rows)

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        run_id: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        row = await db.fetchrow(
            """
            INSERT INTO ai_expert_message (
                session_id, run_id, role, content, attachments, meta
            ) VALUES ($1::uuid, $2::uuid, $3, $4, $5::jsonb, $6::jsonb)
            RETURNING data_id::text AS id, session_id::text AS "sessionId",
                      run_id::text AS "runId", role, content, attachments, meta,
                      create_time AS "createTime"
            """,
            session_id,
            run_id,
            role,
            content,
            _json(attachments or []),
            _json(meta or {}),
        )
        await db.execute(
            """
            UPDATE ai_expert_session
               SET update_time = now()
             WHERE data_id = $1::uuid
            """,
            session_id,
        )
        result = dict(row)
        result["attachments"] = json_value(result.get("attachments"), []) or []
        result["meta"] = json_value(result.get("meta"), {}) or {}
        return result

    async def list_messages(self, session_id: str) -> list[dict[str, Any]]:
        rows = await db.fetch(
            """
            SELECT data_id::text AS id, session_id::text AS "sessionId",
                   run_id::text AS "runId", role, content, attachments, meta,
                   create_time AS "createTime"
              FROM ai_expert_message
             WHERE session_id = $1::uuid AND is_deleted = false
             ORDER BY ai_expert_message.id ASC
            """,
            session_id,
        )
        result = db.to_dicts(rows)
        for item in result:
            item["attachments"] = json_value(item.get("attachments"), []) or []
            item["meta"] = json_value(item.get("meta"), {}) or {}
        return result

    async def delete(
        self,
        session_id: str,
        create_by: str | None,
    ) -> bool:
        async with db.transaction() as conn:
            row = await conn.fetchrow(
                """
                SELECT 1
                  FROM ai_expert_session
                 WHERE data_id = $1::uuid
                   AND is_deleted = false
                   AND ($2::uuid IS NULL OR create_by = $2::uuid)
                """,
                session_id,
                create_by,
            )
            if not row:
                return False
            await conn.execute(
                """
                UPDATE ai_expert_message
                   SET is_deleted = true
                 WHERE session_id = $1::uuid
                """,
                session_id,
            )
            await conn.execute(
                """
                UPDATE ai_expert_session
                   SET is_deleted = true, update_time = now()
                 WHERE data_id = $1::uuid
                """,
                session_id,
            )
        return True


class ExpertRunModel:
    async def add(
        self,
        *,
        expert_id: str,
        session_id: str | None = None,
        model_name: str,
        question: str,
        answer: str,
        status: str,
        tool_trace: list[dict[str, Any]],
        warnings: list[str],
        input_tokens: int,
        output_tokens: int,
        latency_ms: int,
        create_by: str | None,
        state_enc: str = "",
        pending_approval: dict[str, Any] | None = None,
        cost: float = 0.0,
        model_attempts: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        row = await db.fetchrow(
            """
            INSERT INTO ai_expert_run (
                expert_id, session_id, model_name, question, answer, status,
                tool_trace, warnings, input_tokens, output_tokens,
                latency_ms, state_enc, pending_approval, create_by,
                cost, model_attempts
            ) VALUES (
                $1::uuid, $2::uuid, $3, $4, $5, $6, $7::jsonb,
                $8::jsonb, $9, $10, $11, $12, $13::jsonb, $14::uuid,
                $15, $16::jsonb
            )
            RETURNING data_id::text AS id
            """,
            expert_id,
            session_id,
            model_name,
            question,
            answer,
            status,
            _json(tool_trace),
            _json(warnings),
            input_tokens,
            output_tokens,
            latency_ms,
            state_enc,
            _json(pending_approval or {}),
            create_by,
            Decimal(str(cost)),
            _json(model_attempts or []),
        )
        return dict(row)

    async def get(self, data_id: str) -> dict[str, Any] | None:
        row = await db.fetchrow(
            """
            SELECT data_id::text AS id, expert_id::text AS expert_id,
                   session_id::text AS session_id,
                   model_name, question, answer, status, tool_trace, warnings,
                   input_tokens, output_tokens, latency_ms, state_enc,
                   pending_approval, create_by::text AS create_by, create_time,
                   cost, model_attempts
              FROM ai_expert_run
             WHERE data_id = $1::uuid
            """,
            data_id,
        )
        return db.to_dict(row)

    async def update(self, data_id: str, fields: dict[str, Any]) -> None:
        await db.execute(
            """
            UPDATE ai_expert_run
               SET answer = $2, status = $3, tool_trace = $4::jsonb,
                   warnings = $5::jsonb, input_tokens = $6, output_tokens = $7,
                   latency_ms = $8, state_enc = $9, pending_approval = $10::jsonb,
                   cost = $11, model_attempts = $12::jsonb
             WHERE data_id = $1::uuid
            """,
            data_id,
            fields.get("answer", ""),
            fields.get("status", "completed"),
            _json(fields.get("tool_trace", [])),
            _json(fields.get("warnings", [])),
            int(fields.get("input_tokens", 0)),
            int(fields.get("output_tokens", 0)),
            int(fields.get("latency_ms", 0)),
            fields.get("state_enc", ""),
            _json(fields.get("pending_approval", {})),
            Decimal(str(fields.get("cost", 0))),
            _json(fields.get("model_attempts", [])),
        )

    async def list_recent(
        self, expert_id: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        rows = await db.fetch(
            """
            SELECT data_id::text AS id, session_id::text AS session_id,
                   model_name, question, answer, status,
                   tool_trace, warnings, input_tokens, output_tokens,
                   latency_ms, pending_approval, cost, model_attempts, create_time
              FROM ai_expert_run
             WHERE expert_id = $1::uuid
             ORDER BY create_time DESC, id DESC
             LIMIT $2
            """,
            expert_id,
            limit,
        )
        return db.to_dicts(rows)


class RegistryModel:
    """模型 / MCP / SKILL 共用一套注册表读写"""

    tables = {"model": "ai_model", "mcp": "ai_mcp", "skill": "ai_skill"}

    def table(self, kind: str) -> str:
        if kind not in self.tables:
            raise ValueError(f"unknown registry kind: {kind}")
        return self.tables[kind]

    async def list(self, kind: str) -> list[dict[str, Any]]:
        if kind == "model":
            extra = (
                ", model_key, api_key_enc, provider, capabilities, config, "
                "enabled, priority, health_status, last_checked_at, last_error"
            )
        elif kind == "mcp":
            extra = ", config, secret_config_enc"
        else:
            extra = ", config"
        rows = await db.fetch(
            f"""
            SELECT data_id::text AS id, name, description, meta, status, endpoint{extra}
              FROM {self.table(kind)} r
             WHERE is_deleted = false
             ORDER BY r.id ASC
            """
        )
        return db.to_dicts(rows)

    async def get(self, kind: str, data_id: str) -> dict[str, Any] | None:
        if kind == "model":
            extra = (
                ", model_key, api_key_enc, provider, capabilities, config, "
                "enabled, priority, health_status, last_checked_at, last_error"
            )
        elif kind == "mcp":
            extra = ", config, secret_config_enc"
        else:
            extra = ", config"
        row = await db.fetchrow(
            f"""
            SELECT data_id::text AS id, name, description, meta, status, endpoint{extra}
              FROM {self.table(kind)}
             WHERE data_id = $1::uuid AND is_deleted = false
             LIMIT 1
            """,
            data_id,
        )
        return db.to_dict(row)

    async def find_model_by_name(self, name: str) -> dict[str, Any] | None:
        """按名称取模型，用于专家连通性测试"""
        row = await db.fetchrow(
            """
            SELECT data_id::text AS id, name, model_key, endpoint, status,
                   api_key_enc, provider, capabilities, config, enabled,
                   priority, health_status, last_checked_at, last_error
              FROM ai_model
             WHERE name = $1 AND is_deleted = false
             ORDER BY id ASC
             LIMIT 1
            """,
            name,
        )
        return db.to_dict(row)

    async def find_model_by_id(self, data_id: str) -> dict[str, Any] | None:
        row = await db.fetchrow(
            """
            SELECT data_id::text AS id, name, model_key, endpoint, status,
                   api_key_enc, provider, capabilities, config, enabled,
                   priority, health_status, last_checked_at, last_error
              FROM ai_model
             WHERE data_id = $1::uuid AND is_deleted = false
             LIMIT 1
            """,
            data_id,
        )
        return db.to_dict(row)

    async def find_mcp(self, data_id: str) -> dict[str, Any] | None:
        return await self.get("mcp", data_id)

    async def find_skill(self, data_id: str) -> dict[str, Any] | None:
        return await self.get("skill", data_id)

    async def name_exists(self, kind: str, name: str, exclude_id: str | None = None) -> bool:
        row = await db.fetchrow(
            f"""
            SELECT 1
              FROM {self.table(kind)}
             WHERE lower(name) = lower($1)
               AND is_deleted = false
               AND ($2::uuid IS NULL OR data_id <> $2::uuid)
             LIMIT 1
            """,
            name,
            exclude_id,
        )
        return row is not None

    async def create(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        if kind == "model":
            row = await db.fetchrow(
                """
                INSERT INTO ai_model (
                    name, description, meta, status, endpoint, model_key, api_key_enc,
                    provider, capabilities, config, enabled, priority
                )
                VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10::jsonb, $11, $12
                )
                RETURNING data_id::text AS id
                """,
                payload["name"],
                payload["description"],
                payload["meta"],
                payload["status"],
                payload["endpoint"],
                payload.get("model_key", ""),
                payload.get("api_key_enc", ""),
                payload.get("provider", "openai_compatible"),
                _json(payload.get("capabilities", {})),
                _json(payload.get("config", {})),
                payload.get("enabled", True),
                int(payload.get("priority", 100)),
            )
            return dict(row)
        if kind == "mcp":
            row = await db.fetchrow(
                """
                INSERT INTO ai_mcp (
                    name, description, meta, status, endpoint, config,
                    secret_config_enc
                )
                VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)
                RETURNING data_id::text AS id
                """,
                payload["name"],
                payload["description"],
                payload["meta"],
                payload["status"],
                payload["endpoint"],
                _json(payload.get("config", {})),
                payload.get("secret_config_enc", ""),
            )
        else:
            row = await db.fetchrow(
                f"""
                INSERT INTO {self.table(kind)} (
                    name, description, meta, status, endpoint, config
                )
                VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                RETURNING data_id::text AS id
                """,
                payload["name"],
                payload["description"],
                payload["meta"],
                payload["status"],
                payload["endpoint"],
                _json(payload.get("config", {})),
            )
        return dict(row)

    async def update(self, kind: str, data_id: str, payload: dict[str, Any]) -> None:
        if kind == "model":
            await db.execute(
                """
                UPDATE ai_model
                   SET name = $2, description = $3, meta = $4, status = $5,
                       endpoint = $6, model_key = $7, api_key_enc = $8,
                       provider = $9, capabilities = $10::jsonb,
                       config = $11::jsonb, enabled = $12, priority = $13,
                       update_time = now()
                 WHERE data_id = $1::uuid AND is_deleted = false
                """,
                data_id,
                payload["name"],
                payload["description"],
                payload["meta"],
                payload["status"],
                payload["endpoint"],
                payload.get("model_key", ""),
                payload.get("api_key_enc", ""),
                payload.get("provider", "openai_compatible"),
                _json(payload.get("capabilities", {})),
                _json(payload.get("config", {})),
                payload.get("enabled", True),
                int(payload.get("priority", 100)),
            )
            return
        if kind == "mcp":
            await db.execute(
                """
                UPDATE ai_mcp
                   SET name = $2, description = $3, meta = $4, status = $5,
                       endpoint = $6, config = $7::jsonb,
                       secret_config_enc = $8, update_time = now()
                 WHERE data_id = $1::uuid AND is_deleted = false
                """,
                data_id,
                payload["name"],
                payload["description"],
                payload["meta"],
                payload["status"],
                payload["endpoint"],
                _json(payload.get("config", {})),
                payload.get("secret_config_enc", ""),
            )
        else:
            await db.execute(
                f"""
                UPDATE {self.table(kind)}
                   SET name = $2, description = $3, meta = $4, status = $5,
                       endpoint = $6, config = $7::jsonb, update_time = now()
                 WHERE data_id = $1::uuid AND is_deleted = false
                """,
                data_id,
                payload["name"],
                payload["description"],
                payload["meta"],
                payload["status"],
                payload["endpoint"],
                _json(payload.get("config", {})),
            )

    async def set_status(self, kind: str, data_id: str, status: str) -> None:
        await db.execute(
            f"""
            UPDATE {self.table(kind)}
               SET status = $2, update_time = now()
             WHERE data_id = $1::uuid AND is_deleted = false
            """,
            data_id,
            status,
        )

    async def update_model_health(
        self,
        data_id: str,
        *,
        health_status: str,
        error: str = "",
        status: str | None = None,
    ) -> None:
        await db.execute(
            """
            UPDATE ai_model
               SET health_status = $2,
                   last_error = $3,
                   last_checked_at = now(),
                   status = COALESCE($4, status),
                   update_time = now()
             WHERE data_id = $1::uuid AND is_deleted = false
            """,
            data_id,
            health_status,
            error[:1000],
            status,
        )

    async def model_candidates(self) -> list[dict[str, Any]]:
        rows = await db.fetch(
            """
            SELECT data_id::text AS id, name, model_key, endpoint, status,
                   api_key_enc, provider, capabilities, config, enabled,
                   priority, health_status, last_checked_at, last_error
              FROM ai_model
             WHERE is_deleted = false AND enabled = true
             ORDER BY
                   CASE health_status
                       WHEN 'healthy' THEN 0
                       WHEN 'unknown' THEN 1
                       WHEN 'degraded' THEN 2
                       ELSE 3
                   END ASC,
                   priority ASC,
                   id ASC
            """
        )
        return db.to_dicts(rows)

    async def delete(self, kind: str, data_id: str) -> None:
        await db.execute(
            f"""
            UPDATE {self.table(kind)}
               SET is_deleted = true, update_time = now()
             WHERE data_id = $1::uuid AND is_deleted = false
            """,
            data_id,
        )


class QuotaModel:
    async def totals(self) -> dict[str, Decimal]:
        row = await db.fetchrow(
            """
            SELECT COALESCE(SUM(used), 0) AS used,
                   COALESCE(SUM(quota_limit), 0) AS total
              FROM quota_model
             WHERE is_deleted = false
            """
        )
        return {"used": row["used"], "total": row["total"]}

    async def projects(self) -> list[dict[str, Any]]:
        rows = await db.fetch(
            """
            SELECT data_id::text AS id, name, used, quota_limit AS "limit"
              FROM quota_project p
             WHERE is_deleted = false
             ORDER BY p.sort_order ASC, p.id ASC
            """
        )
        return db.to_dicts(rows)

    async def models(self) -> list[dict[str, Any]]:
        rows = await db.fetch(
            """
            SELECT data_id::text AS id, model, price, used, quota_limit AS "limit"
              FROM quota_model q
             WHERE is_deleted = false
             ORDER BY q.sort_order ASC, q.id ASC
            """
        )
        return db.to_dicts(rows)

    async def update_model_limit(self, data_id: str, limit: Decimal) -> None:
        await db.execute(
            """
            UPDATE quota_model
               SET quota_limit = $2, update_time = now()
             WHERE data_id = $1::uuid AND is_deleted = false
            """,
            data_id,
            limit,
        )

    async def consume_usage(self, model_name: str, total_tokens: int) -> float:
        row = await db.fetchrow(
            """
            SELECT data_id, price
              FROM quota_model
             WHERE is_deleted = false
               AND (
                   lower(model) = lower($1)
                   OR $1 ILIKE '%' || model || '%'
                   OR model ILIKE '%' || $1 || '%'
               )
             ORDER BY id ASC
             LIMIT 1
            """,
            model_name,
        )
        if not row:
            return 0.0
        match = re.search(r"([0-9]+(?:\.[0-9]+)?)", str(row["price"] or ""))
        unit_price = float(match.group(1)) if match else 0.0
        cost = round(max(0, total_tokens) / 1000 * unit_price, 6)
        if cost:
            await db.execute(
                """
                UPDATE quota_model
                   SET used = used + $2, update_time = now()
                 WHERE data_id = $1::uuid
                """,
                row["data_id"],
                Decimal(str(cost)),
            )
        return cost

    async def model_budget(self, model_name: str) -> dict[str, Any]:
        row = await db.fetchrow(
            """
            SELECT data_id::text AS id, model, price, used, quota_limit,
                   COALESCE((
                       SELECT stop_on_exceed
                         FROM quota_setting
                        WHERE id = 1
                        LIMIT 1
                   ), false) AS stop_on_exceed
              FROM quota_model
             WHERE is_deleted = false
               AND (
                   lower(model) = lower($1)
                   OR $1 ILIKE '%' || model || '%'
                   OR model ILIKE '%' || $1 || '%'
               )
             ORDER BY id ASC
             LIMIT 1
            """,
            model_name,
        )
        if not row:
            return {
                "configured": False,
                "used": 0.0,
                "limit": 0.0,
                "price": 0.0,
                "stopOnExceed": False,
                "available": True,
            }
        used = float(row["used"] or 0)
        limit = float(row["quota_limit"] or 0)
        match = re.search(r"([0-9]+(?:\.[0-9]+)?)", str(row["price"] or ""))
        return {
            "configured": True,
            "id": row["id"],
            "used": used,
            "limit": limit,
            "price": float(match.group(1)) if match else 0.0,
            "stopOnExceed": bool(row["stop_on_exceed"]),
            "available": not (
                bool(row["stop_on_exceed"]) and limit > 0 and used >= limit
            ),
        }

    async def create_project(self, name: str, used: Decimal, limit: Decimal) -> dict[str, Any]:
        row = await db.fetchrow(
            """
            INSERT INTO quota_project (name, used, quota_limit, sort_order)
            VALUES ($1, $2, $3, COALESCE((SELECT max(sort_order) + 1 FROM quota_project), 1))
            RETURNING data_id::text AS id
            """,
            name,
            used,
            limit,
        )
        return dict(row)

    async def update_project_limit(self, data_id: str, limit: Decimal) -> None:
        await db.execute(
            """
            UPDATE quota_project
               SET quota_limit = $2, update_time = now()
             WHERE data_id = $1::uuid AND is_deleted = false
            """,
            data_id,
            limit,
        )

    async def get_project(self, data_id: str) -> dict[str, Any] | None:
        row = await db.fetchrow(
            """
            SELECT data_id::text AS id, name, used, quota_limit AS "limit"
              FROM quota_project
             WHERE data_id = $1::uuid AND is_deleted = false
             LIMIT 1
            """,
            data_id,
        )
        return db.to_dict(row)

    async def delete_project(self, data_id: str) -> None:
        await db.execute(
            """
            UPDATE quota_project
               SET is_deleted = true, update_time = now()
             WHERE data_id = $1::uuid AND is_deleted = false
            """,
            data_id,
        )

    async def setting(self) -> dict[str, Any] | None:
        row = await db.fetchrow(
            """
            SELECT threshold, channel, notify_admin, stop_on_exceed
              FROM quota_setting
             WHERE id = 1 AND is_deleted = false
             LIMIT 1
            """
        )
        return db.to_dict(row)

    async def save_setting(self, payload: dict[str, Any]) -> None:
        await db.execute(
            """
            INSERT INTO quota_setting (id, threshold, channel, notify_admin, stop_on_exceed)
            VALUES (1, $1, $2, $3, $4)
            ON CONFLICT (id) DO UPDATE
               SET threshold = EXCLUDED.threshold,
                   channel = EXCLUDED.channel,
                   notify_admin = EXCLUDED.notify_admin,
                   stop_on_exceed = EXCLUDED.stop_on_exceed,
                   is_deleted = false,
                   update_time = now()
            """,
            payload["threshold"],
            payload["channel"],
            payload["notify_admin"],
            payload["stop_on_exceed"],
        )


class OperationLogModel:
    async def list(
        self,
        limit: int,
        offset: int = 0,
        keyword: str = "",
        action: str = "",
        start_time: Any = None,
        end_time: Any = None,
    ) -> tuple[list[dict[str, Any]], int]:
        keyword_like = f"%{keyword}%"
        rows = await db.fetch(
            """
            WITH filtered AS (
                SELECT data_id::text AS id, user_name, action, target, create_time
                  FROM admin_operation_log l
                 WHERE is_deleted = false
                   AND ($1::text = '' OR user_name ILIKE $1::text OR target ILIKE $1::text)
                   AND ($2::text = '' OR action = $2::text)
                   AND ($3::timestamptz IS NULL OR create_time >= $3::timestamptz)
                   AND ($4::timestamptz IS NULL OR create_time <= $4::timestamptz)
            )
            SELECT *, count(*) OVER() AS total
              FROM filtered
             ORDER BY create_time DESC, id DESC
             LIMIT $5 OFFSET $6
            """,
            keyword_like if keyword else "",
            action,
            start_time,
            end_time,
            limit,
            offset,
        )
        if not rows:
            total = int(
                await db.fetchval(
                    """
                    SELECT count(*)
                      FROM admin_operation_log l
                     WHERE is_deleted = false
                       AND ($1::text = '' OR user_name ILIKE $1::text OR target ILIKE $1::text)
                       AND ($2::text = '' OR action = $2::text)
                       AND ($3::timestamptz IS NULL OR create_time >= $3::timestamptz)
                       AND ($4::timestamptz IS NULL OR create_time <= $4::timestamptz)
                    """,
                    keyword_like if keyword else "",
                    action,
                    start_time,
                    end_time,
                )
                or 0
            )
            return [], total
        total = int(rows[0]["total"])
        return [{key: value for key, value in row.items() if key != "total"} for row in rows], total

    async def add(
        self, user_id: str | None, user_name: str, action: str, target: str
    ) -> None:
        await db.execute(
            """
            INSERT INTO admin_operation_log (user_id, user_name, action, target)
            VALUES ($1::uuid, $2, $3, $4)
            """,
            user_id,
            user_name,
            action,
            target,
        )
