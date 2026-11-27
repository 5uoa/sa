"""总管会话、运行、Harness 与候选的数据访问。"""
import json
from typing import Any

import db
from common import json_value, text
from settings import settings


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=float)


class ChiefModel:
    async def list_sessions(self, archived: bool = False) -> list[dict[str, Any]]:
        rows = await db.fetch(
            """
            SELECT s.data_id::text AS id, s.title, s.domain, s.risk_tier AS "riskTier",
                   s.project_id::text AS "projectId",
                   p.name AS "projectName",
                   s.expert_id::text AS "expertId",
                   e.name AS "expertName",
                   e.role AS "expertRole",
                   s.create_time AS "createTime", s.update_time AS "updateTime",
                   count(m.id) FILTER (WHERE m.is_deleted = false) AS "messageCount",
                   COALESCE((
                       SELECT left(content, 100)
                         FROM chief_message lm
                        WHERE lm.session_id = s.data_id AND lm.is_deleted = false
                        ORDER BY lm.id DESC LIMIT 1
                   ), '') AS "preview"
              FROM chief_session s
              LEFT JOIN chief_project p ON p.data_id = s.project_id
              LEFT JOIN ai_expert e ON e.data_id = s.expert_id
              LEFT JOIN chief_message m ON m.session_id = s.data_id
             WHERE s.is_deleted = false
               AND s.is_archived = $1
             GROUP BY s.id, p.name, e.name, e.role
             ORDER BY s.update_time DESC, s.id DESC
            """,
            archived,
        )
        return db.to_dicts(rows)

    async def create_session(
        self,
        title: str,
        domain: str,
        risk_tier: str,
        project_id: str | None = None,
        expert_id: str | None = None,
    ) -> dict[str, Any]:
        row = await db.fetchrow(
            """
            INSERT INTO chief_session (
                title, domain, risk_tier, project_id, expert_id
            )
            VALUES ($1, $2, $3, $4::uuid, $5::uuid)
            RETURNING data_id::text AS id, title, domain, risk_tier AS "riskTier",
                      project_id::text AS "projectId",
                      expert_id::text AS "expertId"
            """,
            title,
            domain,
            risk_tier,
            project_id,
            expert_id,
        )
        return dict(row)

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        row = await db.fetchrow(
            """
            SELECT s.data_id::text AS id, s.title, s.domain,
                   s.risk_tier AS "riskTier",
                   s.project_id::text AS "projectId",
                   s.expert_id::text AS "expertId",
                   e.name AS "expertName", e.role AS "expertRole"
              FROM chief_session s
              LEFT JOIN ai_expert e ON e.data_id = s.expert_id
             WHERE s.data_id = $1::uuid AND s.is_deleted = false
             LIMIT 1
            """,
            session_id,
        )
        return db.to_dict(row)

    async def list_projects(self) -> list[dict[str, Any]]:
        rows = await db.fetch(
            """
            SELECT p.data_id::text AS id, p.name, p.description, p.status, p.context,
                   p.expert_id::text AS "expertId",
                   e.name AS "expertName", e.role AS "expertRole",
                   q.used, q.quota_limit AS "limit"
              FROM chief_project p
              LEFT JOIN ai_expert e ON e.data_id = p.expert_id
              LEFT JOIN quota_project q
                ON lower(q.name) = lower(p.name) AND q.is_deleted = false
             WHERE p.is_deleted = false AND p.is_archived = false
             ORDER BY p.sort_order ASC, p.id ASC
            """
        )
        result = db.to_dicts(rows)
        for item in result:
            item["context"] = json_value(item.get("context"), {}) or {}
            item["used"] = float(item.get("used") or 0)
            item["limit"] = float(item.get("limit") or 0)
        return result

    async def project_name_exists(self, name: str) -> bool:
        return bool(
            await db.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1 FROM chief_project
                     WHERE lower(name) = lower($1) AND is_deleted = false
                )
                """,
                name,
            )
        )

    async def get_project(self, project_id: str) -> dict[str, Any] | None:
        row = await db.fetchrow(
            """
            SELECT p.data_id::text AS id, p.name, p.description, p.status,
                   p.phase, p.context, p.is_archived AS archived,
                   p.expert_id::text AS "expertId",
                   e.name AS "expertName", e.role AS "expertRole",
                   p.requirement_html AS "requirementHtml",
                   p.requirement_text AS "requirementText",
                   p.requirement_confirmed_at AS "requirementConfirmedAt",
                   p.solution_html AS "solutionHtml",
                   p.solution_text AS "solutionText",
                   p.solution_confirmed_at AS "solutionConfirmedAt",
                   p.task_plan AS "taskPlan",
                   p.task_plan_confirmed_at AS "taskPlanConfirmedAt",
                   p.execution_status AS "executionStatus",
                   p.execution_error AS "executionError",
                   p.execution_started_at AS "executionStartedAt",
                   p.execution_finished_at AS "executionFinishedAt",
                   p.source_session_id::text AS "sourceSessionId"
              FROM chief_project p
              LEFT JOIN ai_expert e ON e.data_id = p.expert_id
             WHERE p.data_id = $1::uuid AND p.is_deleted = false
             LIMIT 1
            """,
            project_id,
        )
        result = db.to_dict(row)
        if result:
            result["context"] = json_value(result.get("context"), {}) or {}
            result["taskPlan"] = json_value(result.get("taskPlan"), {}) or {}
            documents = await self.list_project_documents([project_id])
            result["documents"] = documents.get(project_id, {})
        return result

    async def list_workspace(self, archived: bool = False) -> list[dict[str, Any]]:
        projects = db.to_dicts(
            await db.fetch(
                """
                SELECT p.data_id::text AS id, p.name, p.description, p.status,
                       p.phase, p.context, p.is_archived AS archived,
                       p.expert_id::text AS "expertId",
                       e.name AS "expertName", e.role AS "expertRole",
                       p.requirement_html AS "requirementHtml",
                       p.requirement_text AS "requirementText",
                       p.requirement_confirmed_at AS "requirementConfirmedAt",
                       p.solution_html AS "solutionHtml",
                       p.solution_text AS "solutionText",
                       p.solution_confirmed_at AS "solutionConfirmedAt",
                       p.task_plan AS "taskPlan",
                       p.task_plan_confirmed_at AS "taskPlanConfirmedAt",
                       p.execution_status AS "executionStatus",
                       p.execution_error AS "executionError",
                       p.execution_started_at AS "executionStartedAt",
                       p.execution_finished_at AS "executionFinishedAt",
                       p.source_session_id::text AS "sourceSessionId",
                       q.used, q.quota_limit AS "limit"
                  FROM chief_project p
                  LEFT JOIN ai_expert e ON e.data_id = p.expert_id
                  LEFT JOIN quota_project q
                    ON lower(q.name) = lower(p.name) AND q.is_deleted = false
                 WHERE p.is_deleted = false AND p.is_archived = $1
                 ORDER BY p.sort_order ASC, p.id ASC
                """,
                archived,
            )
        )
        if not projects:
            return []

        project_ids = [item["id"] for item in projects]
        project_documents = await self.list_project_documents(project_ids)
        milestones = db.to_dicts(
            await db.fetch(
                """
                SELECT data_id::text AS id, project_id::text AS "projectId",
                       title, status, to_char(starts_at, 'YYYY-MM-DD') AS "startsAt",
                       to_char(due_at, 'YYYY-MM-DD') AS "dueAt",
                       sort_order AS "sortOrder"
                  FROM chief_milestone
                 WHERE project_id = ANY($1::uuid[]) AND is_deleted = false
                 ORDER BY sort_order ASC, id ASC
                """,
                project_ids,
            )
        )
        tasks = db.to_dicts(
            await db.fetch(
                """
                SELECT t.data_id::text AS id, t.project_id::text AS "projectId",
                       t.milestone_id::text AS "milestoneId",
                       t.session_id::text AS "sessionId", t.title, t.priority,
                       t.status, to_char(t.due_at, 'YYYY-MM-DD') AS "dueAt",
                       t.sort_order AS "sortOrder",
                       t.task_key AS "taskKey",
                       t.description,
                       t.acceptance_criteria AS "acceptanceCriteria",
                       t.depends_on AS "dependsOn",
                       t.auto_created AS "autoCreated",
                       t.phase, t.spec_confirmed_at AS "specConfirmedAt",
                       t.spec_snapshot AS "specSnapshot",
                       t.active_deliverable_id::text AS "activeDeliverableId",
                       s.expert_id::text AS "expertId",
                       e.name AS "expertName", e.role AS "expertRole",
                       d.data_id::text AS "deliverableId",
                       d.title AS "deliverableTitle",
                       d.status AS "deliverableStatus",
                       d.latest_version_no AS "latestVersionNo",
                       d.draft_html AS "draftHtml",
                       d.draft_text AS "draftText",
                       d.draft_source_message_id::text AS "draftSourceMessageId",
                       d.draft_source_run_id::text AS "draftSourceRunId",
                       d.draft_update_time AS "draftUpdateTime"
                  FROM chief_task t
                  LEFT JOIN ai_expert_session s ON s.data_id = t.session_id
                  LEFT JOIN ai_expert e ON e.data_id = s.expert_id
                  LEFT JOIN chief_deliverable d
                    ON d.task_id = t.data_id AND d.is_deleted = false
                 WHERE t.project_id = ANY($1::uuid[]) AND t.is_deleted = false
                 ORDER BY t.sort_order ASC, t.id ASC
                """,
                project_ids,
            )
        )
        task_ids = [item["id"] for item in tasks]
        attachments = (
            db.to_dicts(
                await db.fetch(
                    """
                    SELECT data_id::text AS id, task_id::text AS "taskId",
                           file_uuid::text AS uuid, file_name AS name,
                           file_ext AS ext, file_size AS size, mime_type AS "mimeType",
                           kind, create_time AS "createTime"
                      FROM chief_task_attachment
                     WHERE task_id = ANY($1::uuid[]) AND is_deleted = false
                     ORDER BY kind DESC, sort_order ASC, id ASC
                    """,
                    task_ids,
                )
            )
            if task_ids
            else []
        )
        session_ids = [item["sessionId"] for item in tasks if item.get("sessionId")]
        messages = (
            db.to_dicts(
                await db.fetch(
                    """
                    SELECT data_id::text AS id, session_id::text AS "sessionId",
                           role, content, attachments,
                           create_time AS "createTime"
                      FROM ai_expert_message
                     WHERE session_id = ANY($1::uuid[]) AND is_deleted = false
                     ORDER BY ai_expert_message.id ASC
                    """,
                    session_ids,
                )
            )
            if session_ids
            else []
        )
        deliverable_ids = [
            item["deliverableId"] for item in tasks if item.get("deliverableId")
        ]
        versions = (
            db.to_dicts(
                await db.fetch(
                    """
                    SELECT data_id::text AS id,
                           deliverable_id::text AS "deliverableId",
                           version_no AS "versionNo",
                           content_html AS "contentHtml",
                           content_text AS "contentText",
                           content_hash AS "contentHash",
                           source_message_id::text AS "sourceMessageId",
                           source_session_id::text AS "sourceSessionId",
                           source_run_id::text AS "sourceRunId",
                           source_expert_id::text AS "sourceExpertId",
                           confirmed_at AS "confirmedAt"
                      FROM chief_deliverable_version
                     WHERE deliverable_id = ANY($1::uuid[])
                     ORDER BY version_no DESC
                    """,
                    deliverable_ids,
                )
            )
            if deliverable_ids
            else []
        )

        milestones_by_project: dict[str, list[dict[str, Any]]] = {}
        task_by_milestone: dict[str, list[dict[str, Any]]] = {}
        attachment_by_task: dict[str, list[dict[str, Any]]] = {}
        message_by_session: dict[str, list[dict[str, Any]]] = {}
        versions_by_deliverable: dict[str, list[dict[str, Any]]] = {}

        for task in tasks:
            task["attachments"] = attachment_by_task.setdefault(task["id"], [])
            task["messages"] = message_by_session.setdefault(
                task.get("sessionId") or "", []
            )
            task["specSnapshot"] = json_value(task.get("specSnapshot"), {}) or {}
            task["dependsOn"] = json_value(task.get("dependsOn"), []) or []
            if task.get("deliverableId"):
                task["deliverable"] = {
                    "id": task["deliverableId"],
                    "title": task["deliverableTitle"],
                    "status": task["deliverableStatus"],
                    "latestVersionNo": task["latestVersionNo"],
                    "draftHtml": task["draftHtml"],
                    "draftText": task["draftText"],
                    "draftSourceMessageId": task.get("draftSourceMessageId"),
                    "draftSourceRunId": task.get("draftSourceRunId"),
                    "draftUpdateTime": task.get("draftUpdateTime"),
                    "versions": versions_by_deliverable.setdefault(
                        task["deliverableId"], []
                    ),
                }
            else:
                task["deliverable"] = None

        messages.sort(
            key=lambda item: (
                str(item.get("createTime") or ""),
                str(item.get("id") or ""),
            )
        )
        for item in attachments:
            attachment_by_task.setdefault(item["taskId"], []).append(item)
        for message in messages:
            message["attachments"] = json_value(message.get("attachments"), []) or []
            message_by_session.setdefault(message["sessionId"], []).append(message)
        for version in versions:
            versions_by_deliverable.setdefault(version["deliverableId"], []).append(
                version
            )
        for milestone in milestones:
            task_list = task_by_milestone.setdefault(milestone["id"], [])
            task_list.extend(
                item for item in tasks if item["milestoneId"] == milestone["id"]
            )
            milestones_by_project.setdefault(milestone["projectId"], []).append(milestone)

        for milestone in milestones:
            milestone["tasks"] = task_by_milestone.setdefault(milestone["id"], [])
        for project in projects:
            project["context"] = json_value(project.get("context"), {}) or {}
            project["taskPlan"] = json_value(project.get("taskPlan"), {}) or {}
            project["documents"] = project_documents.get(project["id"], {})
            project["used"] = float(project.get("used") or 0)
            project["limit"] = float(project.get("limit") or 0)
            project["milestones"] = milestones_by_project.setdefault(project["id"], [])
        return projects

    async def list_project_documents(
        self, project_ids: list[str]
    ) -> dict[str, dict[str, Any]]:
        if not project_ids:
            return {}
        rows = db.to_dicts(
            await db.fetch(
                """
                SELECT data_id::text AS id, project_id::text AS "projectId",
                       kind, title, status,
                       latest_version_no AS "latestVersionNo",
                       draft_html AS "draftHtml", draft_text AS "draftText",
                       source_deliverable_id::text AS "sourceDeliverableId",
                       source_version_id::text AS "sourceVersionId",
                       source_version_no AS "sourceVersionNo",
                       draft_update_time AS "draftUpdateTime"
                  FROM chief_project_deliverable
                 WHERE project_id = ANY($1::uuid[]) AND is_deleted = false
                 ORDER BY create_time ASC, id ASC
                """,
                project_ids,
            )
        )
        deliverable_ids = [item["id"] for item in rows]
        versions = (
            db.to_dicts(
                await db.fetch(
                    """
                    SELECT data_id::text AS id,
                           deliverable_id::text AS "deliverableId",
                           version_no AS "versionNo",
                           content_html AS "contentHtml",
                           content_text AS "contentText",
                           content_hash AS "contentHash",
                           source_deliverable_id::text AS "sourceDeliverableId",
                           source_version_id::text AS "sourceVersionId",
                           source_version_no AS "sourceVersionNo",
                           confirmed_at AS "confirmedAt"
                      FROM chief_project_deliverable_version
                     WHERE deliverable_id = ANY($1::uuid[])
                     ORDER BY version_no DESC
                    """,
                    deliverable_ids,
                )
            )
            if deliverable_ids
            else []
        )
        versions_by_deliverable: dict[str, list[dict[str, Any]]] = {}
        for version in versions:
            versions_by_deliverable.setdefault(
                version["deliverableId"], []
            ).append(version)
        by_project: dict[str, dict[str, Any]] = {}
        for row in rows:
            row["versions"] = versions_by_deliverable.setdefault(row["id"], [])
            by_project.setdefault(row["projectId"], {})[row["kind"]] = row
        return by_project

    async def create_document(
        self,
        session_id: str,
        project_id: str | None,
        source_message_id: str | None,
        title: str,
        content_html: str,
        content_text: str,
    ) -> dict[str, Any]:
        row = await db.fetchrow(
            """
            INSERT INTO chief_document (
                session_id, project_id, source_message_id, title,
                content_html, content_text
            )
            VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5, $6)
            RETURNING data_id::text AS id,
                      session_id::text AS "sessionId",
                      project_id::text AS "projectId",
                      source_message_id::text AS "sourceMessageId",
                      kind, status,
                      title, content_html AS "contentHtml",
                      content_text AS "contentText",
                      create_time AS "createTime",
                      update_time AS "updateTime",
                      false AS attached
            """,
            session_id,
            project_id,
            source_message_id,
            title[:200],
            content_html,
            content_text,
        )
        return dict(row)

    async def get_document(self, document_id: str) -> dict[str, Any] | None:
        row = await db.fetchrow(
            """
            SELECT data_id::text AS id, session_id::text AS "sessionId",
                   project_id::text AS "projectId",
                   source_message_id::text AS "sourceMessageId",
                   kind, status, title, content_html AS "contentHtml",
                   content_text AS "contentText",
                   create_time AS "createTime", update_time AS "updateTime"
              FROM chief_document
             WHERE data_id = $1::uuid AND is_deleted = false
             LIMIT 1
            """,
            document_id,
        )
        return db.to_dict(row)

    async def list_documents(
        self, session_id: str, project_id: str | None = None
    ) -> list[dict[str, Any]]:
        rows = await db.fetch(
            """
            SELECT d.data_id::text AS id, d.session_id::text AS "sessionId",
                   d.project_id::text AS "projectId",
                   d.source_message_id::text AS "sourceMessageId",
                   d.kind, d.status,
                   d.title, d.content_html AS "contentHtml",
                   d.content_text AS "contentText",
                   d.create_time AS "createTime", d.update_time AS "updateTime",
                   EXISTS (
                       SELECT 1
                         FROM chief_session_document link
                        WHERE link.session_id = $1::uuid
                          AND link.document_id = d.data_id
                   ) AS attached
              FROM chief_document d
             WHERE d.is_deleted = false
               AND (
                   d.session_id = $1::uuid
                   OR ($2::uuid IS NOT NULL AND d.project_id = $2::uuid)
               )
             ORDER BY d.update_time DESC, d.id DESC
            """,
            session_id,
            project_id,
        )
        return db.to_dicts(rows)

    async def list_attached_documents(self, session_id: str) -> list[dict[str, Any]]:
        rows = await db.fetch(
            """
            SELECT d.data_id::text AS id, d.session_id::text AS "sessionId",
                   d.project_id::text AS "projectId",
                   d.title, d.content_text AS "contentText",
                   d.update_time AS "updateTime"
              FROM chief_session_document link
              JOIN chief_document d ON d.data_id = link.document_id
             WHERE link.session_id = $1::uuid
               AND d.is_deleted = false
             ORDER BY link.id ASC
            """,
            session_id,
        )
        return db.to_dicts(rows)

    async def update_document(
        self,
        document_id: str,
        title: str,
        content_html: str,
        content_text: str,
    ) -> dict[str, Any] | None:
        row = await db.fetchrow(
            """
            UPDATE chief_document
               SET title = $2, content_html = $3, content_text = $4,
                   update_time = now()
             WHERE data_id = $1::uuid AND is_deleted = false
            RETURNING data_id::text AS id,
                      session_id::text AS "sessionId",
                      project_id::text AS "projectId",
                      source_message_id::text AS "sourceMessageId",
                      kind, status, title, content_html AS "contentHtml",
                      content_text AS "contentText",
                      create_time AS "createTime",
                      update_time AS "updateTime"
            """,
            document_id,
            title[:200],
            content_html,
            content_text,
        )
        return db.to_dict(row)

    async def delete_document(self, document_id: str) -> bool:
        async with db.transaction() as conn:
            row = await conn.fetchrow(
                """
                UPDATE chief_document
                   SET is_deleted = true, update_time = now()
                 WHERE data_id = $1::uuid AND is_deleted = false
                RETURNING data_id
                """,
                document_id,
            )
            if not row:
                return False
            await conn.execute(
                "DELETE FROM chief_session_document WHERE document_id = $1::uuid",
                document_id,
            )
            await conn.execute(
                """
                UPDATE chief_message
                   SET is_deleted = true
                 WHERE is_deleted = false
                   AND meta->>'documentId' = $1
                """,
                document_id,
            )
        return True

    async def delete_project_workflow_document(
        self, project_id: str, kind: str
    ) -> bool:
        targets = {
            "requirements": ["requirements", "solution", "task_plan"],
            "solution": ["solution", "task_plan"],
            "task_plan": ["task_plan"],
        }
        kinds = targets.get(kind)
        if not kinds:
            return False
        async with db.transaction() as conn:
            rows = await conn.fetch(
                """
                UPDATE chief_document
                   SET is_deleted = true, update_time = now()
                 WHERE project_id = $1::uuid
                   AND kind = ANY($2::varchar[])
                   AND is_deleted = false
                RETURNING data_id::text AS id
                """,
                project_id,
                kinds,
            )
            document_ids = [row["id"] for row in rows]
            if not document_ids:
                return False
            await conn.execute(
                """
                DELETE FROM chief_session_document
                 WHERE document_id = ANY($1::uuid[])
                """,
                document_ids,
            )
            await conn.execute(
                """
                UPDATE chief_message
                   SET is_deleted = true
                 WHERE is_deleted = false
                   AND meta->>'documentId' = ANY($1::text[])
                """,
                document_ids,
            )
            await conn.execute(
                """
                UPDATE chief_project_deliverable
                   SET is_deleted = true, update_time = now()
                 WHERE project_id = $1::uuid
                   AND kind = ANY($2::varchar[])
                   AND is_deleted = false
                """,
                project_id,
                kinds,
            )
            if kind == "requirements":
                await conn.execute(
                    """
                    UPDATE chief_project
                       SET phase = 'requirements',
                           requirement_html = '',
                           requirement_text = '',
                           requirement_confirmed_at = NULL,
                           solution_html = '',
                           solution_text = '',
                           solution_confirmed_at = NULL,
                           task_plan = '{}'::jsonb,
                           task_plan_confirmed_at = NULL,
                           update_time = now()
                     WHERE data_id = $1::uuid AND is_deleted = false
                    """,
                    project_id,
                )
            elif kind == "solution":
                await conn.execute(
                    """
                    UPDATE chief_project
                       SET phase = 'requirements_confirmed',
                           solution_html = '',
                           solution_text = '',
                           solution_confirmed_at = NULL,
                           task_plan = '{}'::jsonb,
                           task_plan_confirmed_at = NULL,
                           update_time = now()
                     WHERE data_id = $1::uuid AND is_deleted = false
                    """,
                    project_id,
                )
            else:
                await conn.execute(
                    """
                    UPDATE chief_project
                       SET phase = 'solution_confirmed',
                           task_plan = '{}'::jsonb,
                           task_plan_confirmed_at = NULL,
                           update_time = now()
                     WHERE data_id = $1::uuid AND is_deleted = false
                    """,
                    project_id,
                )
        return True

    async def attach_document(self, session_id: str, document_id: str) -> bool:
        row = await db.fetchrow(
            """
            INSERT INTO chief_session_document (session_id, document_id)
            VALUES ($1::uuid, $2::uuid)
            ON CONFLICT (session_id, document_id) DO NOTHING
            RETURNING data_id
            """,
            session_id,
            document_id,
        )
        return bool(row)

    async def ensure_project_deliverable(
        self, project_id: str, kind: str, title: str
    ) -> dict[str, Any]:
        existing = await db.fetchrow(
            """
            SELECT data_id::text AS id, project_id::text AS "projectId",
                   kind, title, status,
                   latest_version_no AS "latestVersionNo",
                   draft_html AS "draftHtml", draft_text AS "draftText",
                   source_deliverable_id::text AS "sourceDeliverableId",
                   source_version_id::text AS "sourceVersionId",
                   source_version_no AS "sourceVersionNo"
              FROM chief_project_deliverable
             WHERE project_id = $1::uuid AND kind = $2 AND is_deleted = false
             LIMIT 1
            """,
            project_id,
            kind,
        )
        if existing:
            return dict(existing)
        row = await db.fetchrow(
            """
            INSERT INTO chief_project_deliverable (
                project_id, kind, title
            )
            VALUES ($1::uuid, $2, $3)
            RETURNING data_id::text AS id, project_id::text AS "projectId",
                      kind, title, status,
                      latest_version_no AS "latestVersionNo",
                      draft_html AS "draftHtml", draft_text AS "draftText",
                      source_deliverable_id::text AS "sourceDeliverableId",
                      source_version_id::text AS "sourceVersionId",
                      source_version_no AS "sourceVersionNo"
            """,
            project_id,
            kind,
            title[:200],
        )
        return dict(row)

    async def save_project_deliverable_draft(
        self,
        project_id: str,
        kind: str,
        title: str,
        content_html: str,
        content_text: str,
        source_deliverable_id: str | None = None,
        source_version_id: str | None = None,
        source_version_no: int | None = None,
    ) -> dict[str, Any]:
        deliverable = await self.ensure_project_deliverable(project_id, kind, title)
        row = await db.fetchrow(
            """
            UPDATE chief_project_deliverable
               SET title = $2, status = 'draft',
                   draft_html = $3, draft_text = $4,
                   source_deliverable_id = $5::uuid,
                   source_version_id = $6::uuid,
                   source_version_no = $7,
                   draft_update_time = now(), update_time = now()
             WHERE data_id = $1::uuid AND is_deleted = false
            RETURNING data_id::text AS id, project_id::text AS "projectId",
                      kind, title, status,
                      latest_version_no AS "latestVersionNo",
                      draft_html AS "draftHtml", draft_text AS "draftText",
                      source_deliverable_id::text AS "sourceDeliverableId",
                      source_version_id::text AS "sourceVersionId",
                      source_version_no AS "sourceVersionNo",
                      draft_update_time AS "draftUpdateTime"
            """,
            deliverable["id"],
            title[:200],
            content_html,
            content_text,
            source_deliverable_id,
            source_version_id,
            source_version_no,
        )
        await self.sync_project_document(
            project_id,
            kind,
            title,
            "draft",
            content_html,
            content_text,
        )
        return dict(row)

    async def sync_project_document(
        self,
        project_id: str,
        kind: str,
        title: str,
        status: str,
        content_html: str,
        content_text: str,
    ) -> None:
        await db.execute(
            """
            INSERT INTO chief_document (
                session_id, project_id, kind, status, title,
                content_html, content_text
            )
            SELECT p.source_session_id, p.data_id, $2, $3, $4, $5, $6
              FROM chief_project p
             WHERE p.data_id = $1::uuid AND p.is_deleted = false
            ON CONFLICT (project_id, kind)
              WHERE is_deleted = false
                AND kind IN ('requirements', 'solution', 'task_plan')
            DO UPDATE SET
                title = EXCLUDED.title,
                status = EXCLUDED.status,
                content_html = EXCLUDED.content_html,
                content_text = EXCLUDED.content_text,
                update_time = now()
            """,
            project_id,
            kind,
            status,
            title[:200],
            content_html,
            content_text,
        )

    async def invalidate_project_downstream(
        self, project_id: str, stage: str, *, invalidate_stage: bool = False
    ) -> None:
        if stage == "requirements":
            await db.execute(
                """
                UPDATE chief_project
                   SET phase = 'requirements',
                       requirement_confirmed_at = NULL,
                       solution_confirmed_at = NULL,
                       task_plan_confirmed_at = NULL,
                       update_time = now()
                 WHERE data_id = $1::uuid AND is_deleted = false
                """,
                project_id,
            )
            stale_kinds = ["solution", "task_plan"]
        elif stage == "solution":
            await db.execute(
                """
                UPDATE chief_project
                   SET phase = 'solution',
                       solution_confirmed_at = NULL,
                       task_plan_confirmed_at = NULL,
                       update_time = now()
                 WHERE data_id = $1::uuid AND is_deleted = false
                """,
                project_id,
            )
            stale_kinds = ["task_plan"]
        elif stage == "task_plan":
            await db.execute(
                """
                UPDATE chief_project
                   SET phase = 'task_planning',
                       task_plan_confirmed_at = NULL,
                       update_time = now()
                 WHERE data_id = $1::uuid AND is_deleted = false
                """,
                project_id,
            )
            stale_kinds = [stage] if invalidate_stage else []
        else:
            return
        if stale_kinds:
            await db.execute(
                """
                UPDATE chief_project_deliverable
                   SET status = 'stale', update_time = now()
                 WHERE project_id = $1::uuid
                   AND kind = ANY($2::varchar[])
                   AND latest_version_no > 0
                   AND is_deleted = false
                """,
                project_id,
                stale_kinds,
            )
            await db.execute(
                """
                UPDATE chief_document
                   SET status = 'stale', update_time = now()
                 WHERE project_id = $1::uuid
                   AND kind = ANY($2::varchar[])
                   AND is_deleted = false
                """,
                project_id,
                stale_kinds,
            )

    async def confirm_project_deliverable_version(
        self,
        project_id: str,
        kind: str,
        title: str,
        content_html: str,
        content_text: str,
        content_hash: str,
        confirmed_by: str | None,
    ) -> dict[str, Any]:
        deliverable = await self.ensure_project_deliverable(project_id, kind, title)
        async with db.transaction() as conn:
            current = await conn.fetchrow(
                """
                SELECT latest_version_no
                  FROM chief_project_deliverable
                 WHERE data_id = $1::uuid AND is_deleted = false
                 FOR UPDATE
                """,
                deliverable["id"],
            )
            if not current:
                raise RuntimeError("文档不存在")
            latest_version_no = int(current["latest_version_no"])
            if latest_version_no > 0:
                latest = await conn.fetchrow(
                    """
                    SELECT data_id::text AS id, version_no AS "versionNo",
                           content_hash AS "contentHash",
                           source_deliverable_id::text AS "sourceDeliverableId",
                           source_version_id::text AS "sourceVersionId",
                           source_version_no AS "sourceVersionNo",
                           confirmed_at AS "confirmedAt"
                      FROM chief_project_deliverable_version
                     WHERE deliverable_id = $1::uuid
                       AND version_no = $2
                     LIMIT 1
                    """,
                    deliverable["id"],
                    latest_version_no,
                )
                if latest and latest["contentHash"] == content_hash:
                    await conn.execute(
                        """
                        UPDATE chief_project_deliverable
                           SET status = 'confirmed', update_time = now()
                         WHERE data_id = $1::uuid
                        """,
                        deliverable["id"],
                    )
                    await conn.execute(
                        """
                        UPDATE chief_document
                           SET status = 'confirmed', update_time = now()
                         WHERE project_id = $1::uuid
                           AND kind = $2
                           AND is_deleted = false
                        """,
                        project_id,
                        kind,
                    )
                    return {**dict(latest), "unchanged": True}
            version_no = int(current["latest_version_no"]) + 1
            version = await conn.fetchrow(
                """
                INSERT INTO chief_project_deliverable_version (
                    deliverable_id, version_no, content_html, content_text,
                    content_hash, source_deliverable_id, source_version_id,
                    source_version_no, confirmed_by
                )
                VALUES (
                    $1::uuid, $2, $3, $4, $5, $6::uuid,
                    $7::uuid, $8, $9::uuid
                )
                RETURNING data_id::text AS id, version_no AS "versionNo",
                          content_hash AS "contentHash",
                          source_deliverable_id::text AS "sourceDeliverableId",
                          source_version_id::text AS "sourceVersionId",
                          source_version_no AS "sourceVersionNo",
                          confirmed_at AS "confirmedAt"
                """,
                deliverable["id"],
                version_no,
                content_html,
                content_text,
                content_hash,
                deliverable.get("sourceDeliverableId"),
                deliverable.get("sourceVersionId"),
                deliverable.get("sourceVersionNo"),
                confirmed_by,
            )
            await conn.execute(
                """
                UPDATE chief_project_deliverable
                   SET title = $2, status = 'confirmed',
                       latest_version_no = $3,
                       draft_html = $4, draft_text = $5,
                       draft_update_time = now(), update_time = now()
                 WHERE data_id = $1::uuid
                """,
                deliverable["id"],
                title[:200],
                version_no,
                content_html,
                content_text,
            )
        await self.sync_project_document(
            project_id,
            kind,
            title,
            "confirmed",
            content_html,
            content_text,
        )
        return dict(version)

    async def create_project(
        self,
        name: str,
        description: str,
        status: str,
        context: dict[str, Any],
        expert_id: str | None = None,
        source_session_id: str | None = None,
    ) -> dict[str, Any]:
        row = await db.fetchrow(
            """
            INSERT INTO chief_project (
                name, description, status, context, sort_order, expert_id,
                source_session_id
            )
            VALUES (
                $1, $2, $3, $4::jsonb,
                COALESCE((SELECT max(sort_order) + 1 FROM chief_project), 1),
                $5::uuid, $6::uuid
            )
            RETURNING data_id::text AS id, name, description, status, context,
                      is_archived AS archived, expert_id::text AS "expertId",
                      source_session_id::text AS "sourceSessionId"
            """,
            name,
            description,
            status,
            _json(context),
            expert_id,
            source_session_id,
        )
        result = dict(row)
        result["context"] = json_value(result.get("context"), {}) or {}
        return result

    async def update_project(
        self, project_id: str, fields: dict[str, Any]
    ) -> dict[str, Any] | None:
        row = await db.fetchrow(
            """
            UPDATE chief_project
               SET name = COALESCE($2, name),
                   description = COALESCE($3, description),
                   status = COALESCE($4, status),
                   context = COALESCE($5::jsonb, context),
                   expert_id = CASE
                       WHEN $6::boolean THEN $7::uuid ELSE expert_id
                   END,
                   update_time = now()
             WHERE data_id = $1::uuid AND is_deleted = false
             RETURNING data_id::text AS id, name, description, status, context,
                       is_archived AS archived, expert_id::text AS "expertId"
            """,
            project_id,
            fields.get("name"),
            fields.get("description"),
            fields.get("status"),
            _json(fields["context"]) if "context" in fields else None,
            "expertId" in fields,
            fields.get("expertId"),
        )
        result = db.to_dict(row)
        if result:
            result["context"] = json_value(result.get("context"), {}) or {}
            if "expertId" in fields:
                await db.execute(
                    """
                    UPDATE chief_session
                       SET expert_id = $2::uuid, update_time = now()
                     WHERE project_id = $1::uuid AND is_deleted = false
                    """,
                    project_id,
                    fields.get("expertId"),
                )
                await db.execute(
                    """
                    UPDATE ai_expert_session
                       SET expert_id = $2::uuid, update_time = now()
                     WHERE project_id = $1::uuid AND is_deleted = false
                    """,
                    project_id,
                    fields.get("expertId"),
                )
        return await self.get_project(project_id)

    async def set_project_archived(self, project_id: str, archived: bool) -> bool:
        result = await db.execute(
            """
            UPDATE chief_project
               SET is_archived = $2, update_time = now()
             WHERE data_id = $1::uuid AND is_deleted = false
            """,
            project_id,
            archived,
        )
        return result.startswith("UPDATE") and not result.endswith(" 0")

    async def save_project_document(
        self,
        project_id: str,
        stage: str,
        content_html: str,
        content_text: str,
    ) -> dict[str, Any] | None:
        fields = {
            "requirements": ("requirement_html", "requirement_text", "requirements"),
            "solution": ("solution_html", "solution_text", "solution"),
        }
        if stage not in fields:
            return None
        html_column, text_column, phase = fields[stage]
        row = await db.fetchrow(
            f"""
            UPDATE chief_project
               SET {html_column} = $2,
                   {text_column} = $3,
                   phase = $4,
                   update_time = now()
             WHERE data_id = $1::uuid AND is_deleted = false
            RETURNING data_id::text AS id, phase, execution_status AS "executionStatus"
            """,
            project_id,
            content_html,
            content_text,
            phase,
        )
        return db.to_dict(row)

    async def confirm_project_document(
        self, project_id: str, stage: str
    ) -> dict[str, Any] | None:
        if stage == "requirements":
            next_phase = "requirements_confirmed"
            time_column = "requirement_confirmed_at"
            text_column = "requirement_text"
        elif stage == "solution":
            next_phase = "solution_confirmed"
            time_column = "solution_confirmed_at"
            text_column = "solution_text"
        else:
            return None
        row = await db.fetchrow(
            f"""
            UPDATE chief_project
               SET phase = $2,
                   {time_column} = now(),
                   update_time = now()
             WHERE data_id = $1::uuid
               AND is_deleted = false
               AND length(trim({text_column})) > 0
            RETURNING data_id::text AS id, phase
            """,
            project_id,
            next_phase,
        )
        return db.to_dict(row)

    async def save_project_task_plan(
        self, project_id: str, plan: dict[str, Any]
    ) -> dict[str, Any] | None:
        row = await db.fetchrow(
            """
            UPDATE chief_project
               SET task_plan = $2::jsonb,
                   phase = 'task_planning',
                   task_plan_confirmed_at = NULL,
                   update_time = now()
             WHERE data_id = $1::uuid AND is_deleted = false
            RETURNING data_id::text AS id, phase, task_plan AS "taskPlan"
            """,
            project_id,
            _json(plan),
        )
        result = db.to_dict(row)
        if result:
            result["taskPlan"] = json_value(result.get("taskPlan"), {}) or {}
        return result

    async def confirm_project_task_plan(
        self, project_id: str
    ) -> dict[str, Any] | None:
        row = await db.fetchrow(
            """
            UPDATE chief_project
               SET phase = 'tasks_confirmed',
                   task_plan_confirmed_at = now(),
                   update_time = now()
             WHERE data_id = $1::uuid
               AND is_deleted = false
               AND task_plan <> '{}'::jsonb
            RETURNING data_id::text AS id, phase,
                      task_plan AS "taskPlan"
            """,
            project_id,
        )
        result = db.to_dict(row)
        if result:
            result["taskPlan"] = json_value(result.get("taskPlan"), {}) or {}
        return result

    async def materialize_project_task_plan(
        self, project_id: str
    ) -> list[dict[str, Any]]:
        async with db.transaction() as conn:
            project = await conn.fetchrow(
                """
                SELECT expert_id, task_plan
                  FROM chief_project
                 WHERE data_id = $1::uuid AND is_deleted = false
                 FOR UPDATE
                """,
                project_id,
            )
            if not project or not project["expert_id"]:
                return []
            existing = await conn.fetch(
                """
                SELECT data_id::text AS id, task_key AS "taskKey",
                       session_id::text AS "sessionId", title,
                       depends_on AS "dependsOn"
                  FROM chief_task
                 WHERE project_id = $1::uuid
                   AND auto_created = true
                   AND is_deleted = false
                 ORDER BY sort_order ASC, id ASC
                """,
                project_id,
            )
            if existing:
                result = [dict(item) for item in existing]
                for item in result:
                    item["dependsOn"] = json_value(item.get("dependsOn"), []) or []
                return result
            plan = json_value(project["task_plan"], {}) or {}
            packages = plan.get("packages") if isinstance(plan, dict) else []
            created: list[dict[str, Any]] = []
            for package_index, package in enumerate(packages or [], start=1):
                if not isinstance(package, dict):
                    continue
                package_title = text(package.get("name")) or f"任务包 {package_index}"
                milestone = await conn.fetchrow(
                    """
                    INSERT INTO chief_milestone (
                        project_id, title, status, sort_order
                    )
                    VALUES ($1::uuid, $2, '进行中', $3)
                    RETURNING data_id::text AS id
                    """,
                    project_id,
                    package_title[:200],
                    package_index,
                )
                tasks = package.get("tasks") if isinstance(package.get("tasks"), list) else []
                for task_index, task in enumerate(tasks, start=1):
                    if not isinstance(task, dict):
                        continue
                    title = text(task.get("title")) or f"任务 {task_index}"
                    task_key = text(task.get("key")) or f"T{package_index}-{task_index}"
                    task_row = await conn.fetchrow(
                        """
                        INSERT INTO chief_task (
                            project_id, milestone_id, title, priority, status,
                            phase, sort_order, task_key, description,
                            acceptance_criteria, depends_on, auto_created
                        )
                        VALUES (
                            $1::uuid, $2::uuid, $3, $4, '进行中', 'executing',
                            $5, $6, $7, $8, $9::jsonb, true
                        )
                        RETURNING data_id::text AS id
                        """,
                        project_id,
                        milestone["id"],
                        title[:200],
                        text(task.get("priority")) or "P2",
                        task_index,
                        task_key[:80],
                        text(task.get("description")),
                        text(task.get("acceptance_criteria") or task.get("acceptanceCriteria")),
                        _json(task.get("depends_on") or task.get("dependsOn") or []),
                    )
                    session = await conn.fetchrow(
                        """
                        INSERT INTO ai_expert_session (
                            title, project_id, task_id, expert_id
                        )
                        VALUES ($1, $2::uuid, $3::uuid, $4::uuid)
                        RETURNING data_id::text AS id
                        """,
                        title[:200],
                        project_id,
                        task_row["id"],
                        project["expert_id"],
                    )
                    await conn.execute(
                        """
                        UPDATE chief_task
                           SET session_id = $2::uuid,
                               spec_snapshot = $3::jsonb,
                               spec_confirmed_at = now()
                         WHERE data_id = $1::uuid
                        """,
                        task_row["id"],
                        session["id"],
                        _json(
                            {
                                "objective": text(task.get("description")) or title,
                                "scope": package_title,
                                "acceptanceCriteria": text(
                                    task.get("acceptance_criteria")
                                    or task.get("acceptanceCriteria")
                                ),
                            }
                        ),
                    )
                    created.append(
                        {
                            "id": task_row["id"],
                            "taskKey": task_key,
                            "sessionId": session["id"],
                            "title": title,
                            "dependsOn": task.get("depends_on")
                            or task.get("dependsOn")
                            or [],
                        }
                    )
        return created

    async def set_project_execution(
        self,
        project_id: str,
        status: str,
        *,
        error: str = "",
        phase: str | None = None,
    ) -> None:
        await db.execute(
            """
            UPDATE chief_project
               SET execution_status = $2::varchar,
                   execution_error = $3::text,
                   phase = COALESCE($4::varchar, phase),
                   execution_started_at = CASE
                       WHEN $2::text = 'running' THEN COALESCE(execution_started_at, now())
                       ELSE execution_started_at
                   END,
                   execution_finished_at = CASE
                       WHEN $2::text IN ('completed', 'failed') THEN now()
                       ELSE execution_finished_at
                   END,
                   update_time = now()
             WHERE data_id = $1::uuid AND is_deleted = false
            """,
            project_id,
            status,
            error,
            phase,
        )

    async def complete_project(self, project_id: str) -> bool:
        async with db.transaction() as conn:
            project = await conn.fetchrow(
                """
                SELECT 1 FROM chief_project
                 WHERE data_id = $1::uuid AND is_deleted = false
                """,
                project_id,
            )
            if not project:
                return False
            incomplete = await conn.fetchval(
                """
                SELECT count(*)
                  FROM chief_task task
                  LEFT JOIN chief_deliverable deliverable
                    ON deliverable.task_id = task.data_id
                   AND deliverable.is_deleted = false
                 WHERE task.project_id = $1::uuid
                   AND task.is_deleted = false
                   AND COALESCE(deliverable.latest_version_no, 0) = 0
                """,
                project_id,
            )
            task_count = await conn.fetchval(
                """
                SELECT count(*) FROM chief_task
                 WHERE project_id = $1::uuid AND is_deleted = false
                """,
                project_id,
            )
            if int(incomplete or 0) > 0 or int(task_count or 0) == 0:
                return False
            await conn.execute(
                """
                UPDATE chief_task
                   SET phase = 'completed', status = '已完成', update_time = now()
                 WHERE project_id = $1::uuid AND is_deleted = false
                """,
                project_id,
            )
            await conn.execute(
                """
                UPDATE chief_project
                   SET phase = 'completed',
                       status = '已完成',
                       execution_status = 'completed',
                       execution_finished_at = now(),
                       update_time = now()
                 WHERE data_id = $1::uuid
                """,
                project_id,
            )
        return True

    async def duplicate_project(
        self, project_id: str, name: str
    ) -> dict[str, Any] | None:
        async with db.transaction() as conn:
            source = await conn.fetchrow(
                """
                SELECT name, description, status, context, expert_id, phase,
                       requirement_html, requirement_text, requirement_confirmed_at,
                       solution_html, solution_text, solution_confirmed_at,
                       task_plan, task_plan_confirmed_at, execution_status,
                       execution_error, execution_started_at,
                       execution_finished_at, source_session_id
                  FROM chief_project
                 WHERE data_id = $1::uuid AND is_deleted = false
                """,
                project_id,
            )
            if not source:
                return None
            project = await conn.fetchrow(
                """
                INSERT INTO chief_project (
                    name, description, status, context, sort_order, expert_id,
                    phase, requirement_html, requirement_text,
                    requirement_confirmed_at, solution_html, solution_text,
                    solution_confirmed_at, task_plan, task_plan_confirmed_at,
                    execution_status, execution_error, execution_started_at,
                    execution_finished_at, source_session_id
                )
                VALUES (
                    $1, $2, $3, $4::jsonb,
                    COALESCE((SELECT max(sort_order) + 1 FROM chief_project), 1),
                    $5::uuid, $6, $7, $8, $9, $10, $11, $12, $13::jsonb,
                    $14, $15, $16, $17, $18, $19::uuid
                )
                RETURNING data_id::text AS id, name, description, status, context,
                          is_archived AS archived, expert_id::text AS "expertId"
                """,
                name,
                source["description"],
                source["status"],
                _json(json_value(source["context"], {}) or {}),
                source["expert_id"],
                source["phase"],
                source["requirement_html"],
                source["requirement_text"],
                source["requirement_confirmed_at"],
                source["solution_html"],
                source["solution_text"],
                source["solution_confirmed_at"],
                _json(json_value(source["task_plan"], {}) or {}),
                source["task_plan_confirmed_at"],
                source["execution_status"],
                source["execution_error"],
                source["execution_started_at"],
                source["execution_finished_at"],
                source["source_session_id"],
            )
            new_project_id = project["id"]
            milestones = await conn.fetch(
                """
                SELECT *
                  FROM chief_milestone
                 WHERE project_id = $1::uuid AND is_deleted = false
                 ORDER BY sort_order ASC, id ASC
                """,
                project_id,
            )
            for milestone in milestones:
                copied_milestone = await conn.fetchrow(
                    """
                    INSERT INTO chief_milestone (
                        project_id, title, status, starts_at, due_at, sort_order
                    )
                    VALUES ($1::uuid, $2, $3, $4, $5, $6)
                    RETURNING data_id::text AS id
                    """,
                    new_project_id,
                    milestone["title"],
                    milestone["status"],
                    milestone["starts_at"],
                    milestone["due_at"],
                    milestone["sort_order"],
                )
                tasks = await conn.fetch(
                    """
                    SELECT data_id, title, priority, status, due_at, sort_order,
                           phase, spec_confirmed_at, spec_snapshot
                      FROM chief_task
                     WHERE milestone_id = $1::uuid AND is_deleted = false
                     ORDER BY sort_order ASC, id ASC
                    """,
                    milestone["data_id"],
                )
                for task in tasks:
                    copied_task = await conn.fetchrow(
                        """
                        INSERT INTO chief_task (
                            project_id, milestone_id, title, priority, status,
                            due_at, sort_order, phase, spec_confirmed_at,
                            spec_snapshot
                        )
                        VALUES (
                            $1::uuid, $2::uuid, $3, $4, $5, $6, $7, $8, $9,
                            $10::jsonb
                        )
                        RETURNING data_id::text AS id
                        """,
                        new_project_id,
                        copied_milestone["id"],
                        task["title"],
                        task["priority"],
                        task["status"],
                        task["due_at"],
                        task["sort_order"],
                        task["phase"],
                        task["spec_confirmed_at"],
                        _json(json_value(task["spec_snapshot"], {}) or {}),
                    )
                    session = await conn.fetchrow(
                        """
                        INSERT INTO ai_expert_session (
                            title, project_id, task_id, expert_id
                        )
                        VALUES ($1, $2::uuid, $3::uuid, $4::uuid)
                        RETURNING data_id::text AS id
                        """,
                        task["title"],
                        new_project_id,
                        copied_task["id"],
                        source["expert_id"],
                    )
                    await conn.execute(
                        """
                        UPDATE chief_task
                           SET session_id = $2::uuid
                         WHERE data_id = $1::uuid
                        """,
                        copied_task["id"],
                        session["id"],
                    )
                    await conn.execute(
                        """
                        INSERT INTO chief_task_attachment (
                            project_id, task_id, file_uuid, file_name, file_ext,
                            file_size, mime_type, kind, sort_order
                        )
                        SELECT $1::uuid, $2::uuid, file_uuid, file_name, file_ext,
                               file_size, mime_type, kind, sort_order
                          FROM chief_task_attachment
                         WHERE task_id = $3::uuid AND is_deleted = false
                        """,
                        new_project_id,
                        copied_task["id"],
                        task["data_id"],
                    )
                    source_deliverable = await conn.fetchrow(
                        """
                        SELECT title, status, latest_version_no, draft_html,
                               draft_text, draft_source_message_id,
                               draft_source_session_id, draft_source_run_id,
                               draft_source_expert_id, draft_update_time
                          FROM chief_deliverable
                         WHERE task_id = $1::uuid AND is_deleted = false
                         LIMIT 1
                        """,
                        task["data_id"],
                    )
                    if source_deliverable:
                        copied_deliverable = await conn.fetchrow(
                            """
                            INSERT INTO chief_deliverable (
                                project_id, task_id, title, status,
                                latest_version_no, draft_html, draft_text,
                                draft_source_message_id, draft_source_session_id,
                                draft_source_run_id, draft_source_expert_id,
                                draft_update_time
                            )
                            VALUES (
                                $1::uuid, $2::uuid, $3, $4, $5, $6, $7,
                                NULL, $8::uuid, NULL, $9::uuid, $10
                            )
                            RETURNING data_id::text AS id
                            """,
                            new_project_id,
                            copied_task["id"],
                            source_deliverable["title"],
                            source_deliverable["status"],
                            source_deliverable["latest_version_no"],
                            source_deliverable["draft_html"],
                            source_deliverable["draft_text"],
                            session["id"],
                            source_deliverable["draft_source_expert_id"],
                            source_deliverable["draft_update_time"],
                        )
                        await conn.execute(
                            """
                            UPDATE chief_task
                               SET active_deliverable_id = $2::uuid
                             WHERE data_id = $1::uuid
                            """,
                            copied_task["id"],
                            copied_deliverable["id"],
                        )
                        await conn.execute(
                            """
                            INSERT INTO chief_deliverable_version (
                                deliverable_id, version_no, content_html,
                                content_text, content_hash, source_message_id,
                                source_session_id, source_run_id,
                                source_expert_id, confirmed_by, confirmed_at
                            )
                            SELECT $1::uuid, version.version_no,
                                   version.content_html, version.content_text,
                                   version.content_hash, NULL, $2::uuid, NULL,
                                   version.source_expert_id, version.confirmed_by,
                                   version.confirmed_at
                              FROM chief_deliverable_version version
                             WHERE version.deliverable_id = (
                                 SELECT data_id FROM chief_deliverable
                                  WHERE task_id = $3::uuid
                                    AND is_deleted = false LIMIT 1
                             )
                            """,
                            copied_deliverable["id"],
                            session["id"],
                            task["data_id"],
                        )
        result = dict(project)
        result["context"] = json_value(result.get("context"), {}) or {}
        return result

    async def delete_project(self, project_id: str) -> bool:
        async with db.transaction() as conn:
            exists = await conn.fetchval(
                """
                SELECT 1 FROM chief_project
                 WHERE data_id = $1::uuid AND is_deleted = false
                """,
                project_id,
            )
            if not exists:
                return False
            session_ids = [
                item["data_id"]
                for item in await conn.fetch(
                    """
                    SELECT data_id
                      FROM chief_session
                     WHERE project_id = $1::uuid AND is_deleted = false
                    """,
                    project_id,
                )
            ]
            if session_ids:
                await conn.execute(
                    """
                    UPDATE chief_message SET is_deleted = true
                     WHERE session_id = ANY($1::uuid[])
                    """,
                    session_ids,
                )
                await conn.execute(
                    """
                    UPDATE chief_run
                       SET is_deleted = true, update_time = now()
                     WHERE session_id = ANY($1::uuid[])
                    """,
                    session_ids,
                )
            await conn.execute(
                """
                UPDATE ai_expert_message
                   SET is_deleted = true
                 WHERE session_id IN (
                     SELECT data_id FROM ai_expert_session
                      WHERE project_id = $1::uuid
                 )
                """,
                project_id,
            )
            await conn.execute(
                """
                UPDATE ai_expert_session
                   SET is_deleted = true, update_time = now()
                 WHERE project_id = $1::uuid
                """,
                project_id,
            )
            await conn.execute(
                """
                UPDATE chief_session
                   SET is_deleted = true, update_time = now()
                 WHERE project_id = $1::uuid
                """,
                project_id,
            )
            await conn.execute(
                """
                UPDATE chief_task_attachment SET is_deleted = true
                 WHERE project_id = $1::uuid
                """,
                project_id,
            )
            await conn.execute(
                """
                UPDATE chief_deliverable
                   SET is_deleted = true, update_time = now()
                 WHERE project_id = $1::uuid
                """,
                project_id,
            )
            await conn.execute(
                """
                UPDATE chief_task
                   SET is_deleted = true, update_time = now()
                 WHERE project_id = $1::uuid
                """,
                project_id,
            )
            await conn.execute(
                """
                UPDATE chief_milestone
                   SET is_deleted = true, update_time = now()
                 WHERE project_id = $1::uuid
                """,
                project_id,
            )
            await conn.execute(
                """
                UPDATE chief_project
                   SET is_deleted = true, update_time = now()
                 WHERE data_id = $1::uuid
                """,
                project_id,
            )
        return True

    async def create_milestone(
        self,
        project_id: str,
        title: str,
        status: str,
        starts_at: str | None,
        due_at: str | None,
    ) -> dict[str, Any]:
        row = await db.fetchrow(
            """
            INSERT INTO chief_milestone (
                project_id, title, status, starts_at, due_at, sort_order
            )
            VALUES (
                $1::uuid, $2, $3, $4::text::date, $5::text::date,
                COALESCE((
                    SELECT max(sort_order) + 1 FROM chief_milestone
                     WHERE project_id = $1::uuid AND is_deleted = false
                ), 1)
            )
            RETURNING data_id::text AS id, project_id::text AS "projectId",
                      title, status, to_char(starts_at, 'YYYY-MM-DD') AS "startsAt",
                      to_char(due_at, 'YYYY-MM-DD') AS "dueAt"
            """,
            project_id,
            title,
            status,
            starts_at,
            due_at,
        )
        return {**dict(row), "tasks": []}

    async def milestone_belongs_to_project(
        self, milestone_id: str, project_id: str
    ) -> bool:
        return bool(
            await db.fetchval(
                """
                SELECT 1
                  FROM chief_milestone
                 WHERE data_id = $1::uuid
                   AND project_id = $2::uuid
                   AND is_deleted = false
                """,
                milestone_id,
                project_id,
            )
        )

    async def update_milestone(
        self, milestone_id: str, fields: dict[str, Any]
    ) -> dict[str, Any] | None:
        row = await db.fetchrow(
            """
            UPDATE chief_milestone
               SET title = COALESCE($2, title),
                   status = COALESCE($3, status),
                   starts_at = CASE WHEN $4::boolean THEN $5::text::date ELSE starts_at END,
                   due_at = CASE WHEN $6::boolean THEN $7::text::date ELSE due_at END,
                   update_time = now()
             WHERE data_id = $1::uuid AND is_deleted = false
             RETURNING data_id::text AS id, project_id::text AS "projectId",
                       title, status, to_char(starts_at, 'YYYY-MM-DD') AS "startsAt",
                       to_char(due_at, 'YYYY-MM-DD') AS "dueAt"
            """,
            milestone_id,
            fields.get("title"),
            fields.get("status"),
            "startsAt" in fields,
            fields.get("startsAt"),
            "dueAt" in fields,
            fields.get("dueAt"),
        )
        return db.to_dict(row)

    async def delete_milestone(self, milestone_id: str) -> bool:
        async with db.transaction() as conn:
            project_id = await conn.fetchval(
                """
                SELECT project_id
                  FROM chief_milestone
                 WHERE data_id = $1::uuid AND is_deleted = false
                """,
                milestone_id,
            )
            if not project_id:
                return False
            task_ids = [
                item["data_id"]
                for item in await conn.fetch(
                    """
                    SELECT data_id FROM chief_task
                     WHERE milestone_id = $1::uuid AND is_deleted = false
                    """,
                    milestone_id,
                )
            ]
            if task_ids:
                session_ids = [
                    item["session_id"]
                    for item in await conn.fetch(
                        """
                        SELECT session_id FROM chief_task
                         WHERE data_id = ANY($1::uuid[])
                           AND session_id IS NOT NULL
                        """,
                        task_ids,
                    )
                ]
                if session_ids:
                    await conn.execute(
                        "UPDATE chief_message SET is_deleted = true WHERE session_id = ANY($1::uuid[])",
                        session_ids,
                    )
                    await conn.execute(
                        "UPDATE chief_session SET is_deleted = true WHERE data_id = ANY($1::uuid[])",
                        session_ids,
                    )
                    await conn.execute(
                        "UPDATE ai_expert_message SET is_deleted = true WHERE session_id = ANY($1::uuid[])",
                        session_ids,
                    )
                    await conn.execute(
                        "UPDATE ai_expert_session SET is_deleted = true WHERE data_id = ANY($1::uuid[])",
                        session_ids,
                    )
                await conn.execute(
                    "UPDATE chief_task_attachment SET is_deleted = true WHERE task_id = ANY($1::uuid[])",
                    task_ids,
                )
                await conn.execute(
                    "UPDATE chief_deliverable SET is_deleted = true WHERE task_id = ANY($1::uuid[])",
                    task_ids,
                )
            await conn.execute(
                """
                UPDATE chief_task
                   SET is_deleted = true, update_time = now()
                 WHERE milestone_id = $1::uuid
                """,
                milestone_id,
            )
            await conn.execute(
                """
                UPDATE chief_milestone
                   SET is_deleted = true, update_time = now()
                 WHERE data_id = $1::uuid
                """,
                milestone_id,
            )
        return True

    async def create_task(
        self,
        project_id: str,
        milestone_id: str,
        title: str,
        priority: str,
        status: str,
        due_at: str | None,
    ) -> dict[str, Any]:
        async with db.transaction() as conn:
            task = await conn.fetchrow(
                """
                INSERT INTO chief_task (
                    project_id, milestone_id, title, priority, status, due_at,
                    sort_order
                )
                VALUES (
                    $1::uuid, $2::uuid, $3, $4, $5, $6::text::date,
                    COALESCE((
                        SELECT max(sort_order) + 1 FROM chief_task
                         WHERE milestone_id = $2::uuid AND is_deleted = false
                    ), 1)
                )
                RETURNING data_id::text AS id, project_id::text AS "projectId",
                          milestone_id::text AS "milestoneId", title, priority,
                          status, to_char(due_at, 'YYYY-MM-DD') AS "dueAt"
                """,
                project_id,
                milestone_id,
                title,
                priority,
                status,
                due_at,
            )
            session = await conn.fetchrow(
                """
                INSERT INTO ai_expert_session (
                    title, project_id, task_id, expert_id
                )
                VALUES (
                    $1, $2::uuid, $3::uuid,
                    (SELECT expert_id FROM chief_project WHERE data_id = $2::uuid)
                )
                RETURNING data_id::text AS id
                """,
                title,
                project_id,
                task["id"],
            )
            await conn.execute(
                "UPDATE chief_task SET session_id = $2::uuid WHERE data_id = $1::uuid",
                task["id"],
                session["id"],
            )
        return {
            **dict(task),
            "sessionId": session["id"],
            "phase": "communicating",
            "specConfirmedAt": None,
            "specSnapshot": {},
            "activeDeliverableId": None,
            "deliverable": None,
            "attachments": [],
            "messages": [],
        }

    async def confirm_task_spec(
        self, task_id: str, spec: dict[str, Any]
    ) -> dict[str, Any] | None:
        row = await db.fetchrow(
            """
            UPDATE chief_task
               SET phase = 'spec_confirmed',
                   status = '进行中',
                   spec_snapshot = $2::jsonb,
                   spec_confirmed_at = now(),
                   update_time = now()
             WHERE data_id = $1::uuid AND is_deleted = false
             RETURNING data_id::text AS id, phase,
                       spec_snapshot AS "specSnapshot",
                       spec_confirmed_at AS "specConfirmedAt"
            """,
            task_id,
            _json(spec),
        )
        result = db.to_dict(row)
        if result:
            result["specSnapshot"] = json_value(result.get("specSnapshot"), {}) or {}
        return result

    async def set_task_phase(self, task_id: str, phase: str) -> bool:
        result = await db.execute(
            """
            UPDATE chief_task
               SET phase = $2, update_time = now()
             WHERE data_id = $1::uuid AND is_deleted = false
            """,
            task_id,
            phase,
        )
        return result.startswith("UPDATE") and not result.endswith(" 0")

    async def mark_task_execution_failed(self, task_id: str) -> None:
        await db.execute(
            """
            UPDATE chief_task
               SET phase = 'executing', status = '执行失败',
                   update_time = now()
             WHERE data_id = $1::uuid AND is_deleted = false
            """,
            task_id,
        )

    async def ensure_deliverable(
        self, task_id: str, project_id: str, title: str
    ) -> dict[str, Any]:
        existing = await db.fetchrow(
            """
            SELECT data_id::text AS id, task_id::text AS "taskId",
                   title, status, latest_version_no AS "latestVersionNo",
                   draft_html AS "draftHtml", draft_text AS "draftText"
              FROM chief_deliverable
             WHERE task_id = $1::uuid AND is_deleted = false
             LIMIT 1
            """,
            task_id,
        )
        if existing:
            return dict(existing)
        row = await db.fetchrow(
            """
            INSERT INTO chief_deliverable (project_id, task_id, title)
            VALUES ($1::uuid, $2::uuid, $3)
            RETURNING data_id::text AS id, task_id::text AS "taskId",
                      title, status, latest_version_no AS "latestVersionNo",
                      draft_html AS "draftHtml", draft_text AS "draftText"
            """,
            project_id,
            task_id,
            title[:200],
        )
        await db.execute(
            """
            UPDATE chief_task
               SET active_deliverable_id = $2::uuid, phase = 'adjusting',
                   update_time = now()
             WHERE data_id = $1::uuid
            """,
            task_id,
            row["id"],
        )
        return dict(row)

    async def save_deliverable_draft(
        self,
        deliverable_id: str,
        content_html: str,
        content_text: str,
        *,
        source_message_id: str | None = None,
        source_session_id: str | None = None,
        source_run_id: str | None = None,
        source_expert_id: str | None = None,
    ) -> dict[str, Any] | None:
        row = await db.fetchrow(
            """
            UPDATE chief_deliverable
               SET draft_html = $2,
                   draft_text = $3,
                   draft_source_message_id = COALESCE($4::uuid, draft_source_message_id),
                   draft_source_session_id = COALESCE($5::uuid, draft_source_session_id),
                   draft_source_run_id = COALESCE($6::uuid, draft_source_run_id),
                   draft_source_expert_id = COALESCE($7::uuid, draft_source_expert_id),
                   draft_update_time = now(),
                   update_time = now()
             WHERE data_id = $1::uuid AND is_deleted = false
            RETURNING data_id::text AS id, task_id::text AS "taskId",
                      title, status, latest_version_no AS "latestVersionNo",
                      draft_html AS "draftHtml", draft_text AS "draftText",
                      draft_source_message_id::text AS "draftSourceMessageId",
                      draft_source_run_id::text AS "draftSourceRunId",
                      draft_update_time AS "draftUpdateTime"
            """,
            deliverable_id,
            content_html,
            content_text,
            source_message_id,
            source_session_id,
            source_run_id,
            source_expert_id,
        )
        return db.to_dict(row)

    async def confirm_deliverable_version(
        self,
        deliverable_id: str,
        content_hash: str,
        confirmed_by: str | None,
    ) -> dict[str, Any] | None:
        async with db.transaction() as conn:
            deliverable = await conn.fetchrow(
                """
                SELECT data_id::text AS id, task_id::text AS "taskId",
                       title, latest_version_no AS "latestVersionNo",
                       draft_html AS "draftHtml", draft_text AS "draftText",
                       draft_source_message_id, draft_source_session_id,
                       draft_source_run_id, draft_source_expert_id
                  FROM chief_deliverable
                 WHERE data_id = $1::uuid AND is_deleted = false
                 FOR UPDATE
                """,
                deliverable_id,
            )
            if not deliverable or not text(deliverable["draftText"]).strip():
                return None
            version_no = int(deliverable["latestVersionNo"]) + 1
            version = await conn.fetchrow(
                """
                INSERT INTO chief_deliverable_version (
                    deliverable_id, version_no, content_html, content_text,
                    content_hash, source_message_id, source_session_id,
                    source_run_id, source_expert_id, confirmed_by
                )
                VALUES (
                    $1::uuid, $2, $3, $4, $5, $6::uuid, $7::uuid,
                    $8::uuid, $9::uuid, $10::uuid
                )
                RETURNING data_id::text AS id, version_no AS "versionNo",
                          content_hash AS "contentHash",
                          confirmed_at AS "confirmedAt"
                """,
                deliverable_id,
                version_no,
                deliverable["draftHtml"],
                deliverable["draftText"],
                content_hash,
                deliverable["draft_source_message_id"],
                deliverable["draft_source_session_id"],
                deliverable["draft_source_run_id"],
                deliverable["draft_source_expert_id"],
                confirmed_by,
            )
            await conn.execute(
                """
                UPDATE chief_deliverable
                   SET status = 'confirmed',
                       latest_version_no = $2,
                       update_time = now()
                 WHERE data_id = $1::uuid
                """,
                deliverable_id,
                version_no,
            )
            await conn.execute(
                """
                UPDATE chief_task
                   SET phase = 'confirmed',
                       status = '进行中',
                       update_time = now()
                 WHERE data_id = $1::uuid
                """,
                deliverable["taskId"],
            )
        return dict(version)

    async def start_deliverable_adjustment(
        self, deliverable_id: str
    ) -> dict[str, Any] | None:
        async with db.transaction() as conn:
            deliverable = await conn.fetchrow(
                """
                SELECT data_id::text AS id, task_id::text AS "taskId",
                       latest_version_no AS "latestVersionNo"
                  FROM chief_deliverable
                 WHERE data_id = $1::uuid AND is_deleted = false
                 FOR UPDATE
                """,
                deliverable_id,
            )
            if not deliverable:
                return None
            version = await conn.fetchrow(
                """
                SELECT content_html, content_text
                  FROM chief_deliverable_version
                 WHERE deliverable_id = $1::uuid
                 ORDER BY version_no DESC
                 LIMIT 1
                """,
                deliverable_id,
            )
            if not version:
                return None
            updated = await conn.fetchrow(
                """
                UPDATE chief_deliverable
                   SET status = 'draft',
                       draft_html = $2,
                       draft_text = $3,
                       draft_update_time = now(),
                       update_time = now()
                 WHERE data_id = $1::uuid
                RETURNING data_id::text AS id, task_id::text AS "taskId",
                          latest_version_no AS "latestVersionNo",
                          draft_html AS "draftHtml", draft_text AS "draftText"
                """,
                deliverable_id,
                version["content_html"],
                version["content_text"],
            )
            await conn.execute(
                """
                UPDATE chief_task
                   SET phase = 'adjusting', update_time = now()
                 WHERE data_id = $1::uuid
                """,
                deliverable["taskId"],
            )
        return dict(updated)

    async def complete_task_delivery(self, task_id: str) -> bool:
        result = await db.execute(
            """
            UPDATE chief_task task
               SET phase = 'completed', status = '已完成', update_time = now()
              FROM chief_deliverable deliverable
             WHERE task.data_id = $1::uuid
               AND task.active_deliverable_id = deliverable.data_id
               AND deliverable.latest_version_no > 0
               AND task.is_deleted = false
            """,
            task_id,
        )
        return result.startswith("UPDATE") and not result.endswith(" 0")

    async def update_task(
        self, task_id: str, fields: dict[str, Any]
    ) -> dict[str, Any] | None:
        row = await db.fetchrow(
            """
            UPDATE chief_task
               SET title = COALESCE($2, title),
                   priority = COALESCE($3, priority),
                   status = COALESCE($4, status),
                   due_at = CASE WHEN $5::boolean THEN $6::text::date ELSE due_at END,
                   update_time = now()
             WHERE data_id = $1::uuid AND is_deleted = false
            RETURNING data_id::text AS id, project_id::text AS "projectId",
                      milestone_id::text AS "milestoneId",
                      session_id::text AS "sessionId", title, priority, status,
                      to_char(due_at, 'YYYY-MM-DD') AS "dueAt"
            """,
            task_id,
            fields.get("title"),
            fields.get("priority"),
            fields.get("status"),
            "dueAt" in fields,
            fields.get("dueAt"),
        )
        if not row:
            return None
        if fields.get("title") and row["sessionId"]:
            await db.execute(
                """
                UPDATE ai_expert_session
                   SET title = $2, update_time = now()
                 WHERE data_id = $1::uuid AND is_deleted = false
                """,
                row["sessionId"],
                row["title"],
            )
        if fields.get("title"):
            await db.execute(
                """
                UPDATE chief_deliverable
                   SET title = $2, update_time = now()
                 WHERE task_id = $1::uuid AND is_deleted = false
                """,
                task_id,
                row["title"],
            )
        return db.to_dict(row)

    async def get_task_delivery_context(
        self, task_id: str
    ) -> dict[str, Any] | None:
        row = await db.fetchrow(
            """
            SELECT task.data_id::text AS id, task.project_id::text AS "projectId",
                   task.milestone_id::text AS "milestoneId",
                   task.session_id::text AS "sessionId",
                   task.title, task.phase, task.status,
                   task.spec_snapshot AS "specSnapshot",
                   task.active_deliverable_id::text AS "activeDeliverableId",
                   deliverable.data_id::text AS "deliverableId",
                   deliverable.title AS "deliverableTitle",
                   deliverable.status AS "deliverableStatus",
                   deliverable.latest_version_no AS "latestVersionNo",
                   deliverable.draft_html AS "draftHtml",
                   deliverable.draft_text AS "draftText",
                   session.expert_id::text AS "expertId"
              FROM chief_task task
              LEFT JOIN chief_deliverable deliverable
                ON deliverable.task_id = task.data_id
               AND deliverable.is_deleted = false
              LEFT JOIN ai_expert_session session
                ON session.data_id = task.session_id
             WHERE task.data_id = $1::uuid
               AND task.is_deleted = false
             LIMIT 1
            """,
            task_id,
        )
        result = db.to_dict(row)
        if result:
            result["specSnapshot"] = json_value(result.get("specSnapshot"), {}) or {}
        return result

    async def get_expert_message_for_task(
        self, task_id: str, message_id: str
    ) -> dict[str, Any] | None:
        row = await db.fetchrow(
            """
            SELECT message.data_id::text AS id, message.role,
                   message.content, message.run_id::text AS "runId",
                   message.attachments, message.meta,
                   session.data_id::text AS "sessionId",
                   session.expert_id::text AS "expertId"
              FROM ai_expert_message message
              JOIN ai_expert_session session
                ON session.data_id = message.session_id
             WHERE message.data_id = $1::uuid
               AND session.task_id = $2::uuid
               AND message.is_deleted = false
               AND session.is_deleted = false
             LIMIT 1
            """,
            message_id,
            task_id,
        )
        return db.to_dict(row)

    async def delete_task(self, task_id: str) -> bool:
        async with db.transaction() as conn:
            task = await conn.fetchrow(
                """
                SELECT session_id
                  FROM chief_task
                 WHERE data_id = $1::uuid AND is_deleted = false
                """,
                task_id,
            )
            if not task:
                return False
            if task["session_id"]:
                await conn.execute(
                    "UPDATE chief_message SET is_deleted = true WHERE session_id = $1::uuid",
                    task["session_id"],
                )
                await conn.execute(
                    "UPDATE chief_run SET is_deleted = true WHERE session_id = $1::uuid",
                    task["session_id"],
                )
                await conn.execute(
                    """
                    UPDATE chief_session
                       SET is_deleted = true, update_time = now()
                     WHERE data_id = $1::uuid
                    """,
                    task["session_id"],
                )
                await conn.execute(
                    "UPDATE ai_expert_message SET is_deleted = true WHERE session_id = $1::uuid",
                    task["session_id"],
                )
                await conn.execute(
                    """
                    UPDATE ai_expert_session
                       SET is_deleted = true, update_time = now()
                     WHERE data_id = $1::uuid
                    """,
                    task["session_id"],
                )
            await conn.execute(
                "UPDATE chief_task_attachment SET is_deleted = true WHERE task_id = $1::uuid",
                task_id,
            )
            await conn.execute(
                "UPDATE chief_deliverable SET is_deleted = true WHERE task_id = $1::uuid",
                task_id,
            )
            await conn.execute(
                """
                UPDATE chief_task
                   SET is_deleted = true, update_time = now()
                 WHERE data_id = $1::uuid
                """,
                task_id,
            )
        return True

    async def add_task_attachment(
        self,
        task_id: str,
        file: dict[str, Any],
        kind: str,
    ) -> dict[str, Any]:
        row = await db.fetchrow(
            """
            INSERT INTO chief_task_attachment (
                project_id, task_id, file_uuid, file_name, file_ext, file_size,
                mime_type, kind, sort_order
            )
            SELECT t.project_id, t.data_id, $2::uuid, $3, $4, $5, $6, $7,
                   COALESCE((
                       SELECT max(a.sort_order) + 1
                         FROM chief_task_attachment a
                        WHERE a.task_id = t.data_id
                          AND a.kind = $7::varchar AND a.is_deleted = false
                   ), 1)
              FROM chief_task t
             WHERE t.data_id = $1::uuid AND t.is_deleted = false
            ON CONFLICT (task_id, file_uuid) WHERE is_deleted = false
            DO UPDATE SET
                file_name = EXCLUDED.file_name,
                file_ext = EXCLUDED.file_ext,
                file_size = EXCLUDED.file_size,
                mime_type = EXCLUDED.mime_type,
                kind = EXCLUDED.kind
            RETURNING data_id::text AS id, task_id::text AS "taskId",
                      file_uuid::text AS uuid, file_name AS name,
                      file_ext AS ext, file_size AS size,
                      mime_type AS "mimeType", kind,
                      create_time AS "createTime"
            """,
            task_id,
            file.get("uuid"),
            file.get("name") or file.get("original_name") or "附件",
            file.get("ext") or file.get("file_ext") or "",
            int(file.get("size") or file.get("file_size") or 0),
            file.get("mimeType") or file.get("mime_type") or "application/octet-stream",
            kind,
        )
        if not row:
            return {}
        return dict(row)

    async def delete_task_attachment(self, attachment_id: str) -> bool:
        result = await db.execute(
            """
            UPDATE chief_task_attachment
               SET is_deleted = true
             WHERE data_id = $1::uuid AND is_deleted = false
            """,
            attachment_id,
        )
        return result.startswith("UPDATE") and not result.endswith(" 0")

    async def update_session(
        self, session_id: str, domain: str, risk_tier: str
    ) -> None:
        await db.execute(
            """
            UPDATE chief_session
               SET domain = $2, risk_tier = $3, update_time = now()
             WHERE data_id = $1::uuid
            """,
            session_id,
            domain,
            risk_tier,
        )

    async def bind_session_project(
        self,
        session_id: str,
        project_id: str,
        expert_id: str,
        fallback_title: str = "",
    ) -> dict[str, Any] | None:
        """把总管会话转为项目会话，同时保留已有聊天记录。"""
        row = await db.fetchrow(
            """
            UPDATE chief_session
               SET project_id = $2::uuid,
                   expert_id = $3::uuid,
                   domain = 'project',
                   title = CASE
                       WHEN title IN ('', '新会话') AND $4 <> '' THEN $4
                       ELSE title
                   END,
                   update_time = now()
             WHERE data_id = $1::uuid AND is_deleted = false
            RETURNING data_id::text AS id, title, domain,
                      risk_tier AS "riskTier",
                      project_id::text AS "projectId",
                      expert_id::text AS "expertId"
            """,
            session_id,
            project_id,
            expert_id,
            fallback_title,
        )
        return db.to_dict(row)

    async def delete_session(self, session_id: str) -> bool:
        exists = await db.fetchval(
            """
            SELECT 1 FROM chief_session
             WHERE data_id = $1::uuid AND is_deleted = false
            """,
            session_id,
        )
        if not exists:
            return False
        async with db.transaction() as conn:
            await conn.execute(
                """
                UPDATE chief_session
                   SET is_deleted = true, update_time = now()
                 WHERE data_id = $1::uuid
                """,
                session_id,
            )
            await conn.execute(
                """
                UPDATE chief_message
                   SET is_deleted = true
                 WHERE session_id = $1::uuid
                """,
                session_id,
            )
            await conn.execute(
                """
                UPDATE chief_run
                   SET is_deleted = true, update_time = now()
                 WHERE session_id = $1::uuid
                """,
                session_id,
            )
        return True

    async def archive_session(self, session_id: str) -> bool:
        result = await db.execute(
            """
            UPDATE chief_session
               SET is_archived = true, update_time = now()
             WHERE data_id = $1::uuid AND is_deleted = false
            """,
            session_id,
        )
        return result.startswith("UPDATE") and not result.endswith(" 0")

    async def restore_session(self, session_id: str) -> bool:
        result = await db.execute(
            """
            UPDATE chief_session
               SET is_archived = false, update_time = now()
             WHERE data_id = $1::uuid AND is_deleted = false
            """,
            session_id,
        )
        return result.startswith("UPDATE") and not result.endswith(" 0")

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        run_id: str | None = None,
        meta: dict[str, Any] | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        row = await db.fetchrow(
            """
            INSERT INTO chief_message (
                session_id, run_id, role, content, meta, attachments
            ) VALUES ($1::uuid, $2::uuid, $3, $4, $5::jsonb, $6::jsonb)
            RETURNING data_id::text AS id, session_id::text AS "sessionId",
                      run_id::text AS "runId", role, content, meta, attachments,
                      create_time AS "createTime"
            """,
            session_id,
            run_id,
            role,
            content,
            _json(meta or {}),
            _json(attachments or []),
        )
        result = dict(row)
        result["meta"] = json_value(result.get("meta"), {}) or {}
        result["attachments"] = json_value(result.get("attachments"), []) or []
        return result

    async def list_messages(self, session_id: str) -> list[dict[str, Any]]:
        rows = await db.fetch(
            """
            SELECT data_id::text AS id, session_id::text AS "sessionId",
                   run_id::text AS "runId", role, content, meta, attachments,
                   create_time AS "createTime"
              FROM chief_message
             WHERE session_id = $1::uuid AND is_deleted = false
             ORDER BY chief_message.id ASC
            """,
            session_id,
        )
        result = db.to_dicts(rows)
        for item in result:
            item["meta"] = json_value(item.get("meta"), {}) or {}
            item["attachments"] = json_value(item.get("attachments"), []) or []
        return result

    async def get_message(self, message_id: str) -> dict[str, Any] | None:
        row = await db.fetchrow(
            """
            SELECT data_id::text AS id, session_id::text AS "sessionId",
                   role, content, meta, attachments
              FROM chief_message
             WHERE data_id = $1::uuid AND is_deleted = false
             LIMIT 1
            """,
            message_id,
        )
        result = db.to_dict(row)
        if result:
            result["meta"] = json_value(result.get("meta"), {}) or {}
            result["attachments"] = json_value(result.get("attachments"), []) or []
        return result

    async def create_run(
        self,
        *,
        session_id: str,
        user_message_id: str,
        domain: str,
        risk_tier: str,
        baseline_harness_id: str,
        expert_id: str | None,
        model_name: str,
        recursion_mode: str,
        recursion_k: int,
    ) -> dict[str, Any]:
        row = await db.fetchrow(
            """
            INSERT INTO chief_run (
                session_id, user_message_id, domain, risk_tier,
                baseline_harness_id, expert_id, model_name,
                recursion_mode, recursion_k
            ) VALUES ($1::uuid, $2::uuid, $3, $4, $5::uuid, $6::uuid, $7, $8, $9)
            RETURNING data_id::text AS id, status
            """,
            session_id,
            user_message_id,
            domain,
            risk_tier,
            baseline_harness_id,
            expert_id,
            model_name,
            recursion_mode,
            recursion_k,
        )
        return dict(row)

    async def update_run(self, run_id: str, fields: dict[str, Any]) -> None:
        allowed = {
            "status",
            "selected_harness_id",
            "assistant_message_id",
            "answer",
            "error",
            "requires_approval",
            "approved_by",
            "input_tokens",
            "output_tokens",
            "estimated_cost",
            "regression_passed",
            "auto_adopt_reason",
        }
        assignments: list[str] = []
        values: list[Any] = [run_id]
        for key, value in fields.items():
            if key not in allowed:
                continue
            values.append(value)
            cast = "::uuid" if key in {"selected_harness_id", "assistant_message_id", "approved_by"} else ""
            assignments.append(f"{key} = ${len(values)}{cast}")
        if not assignments:
            return
        if "approved_by" in fields:
            assignments.append("approve_time = now()")
        assignments.append("update_time = now()")
        await db.execute(
            f"UPDATE chief_run SET {', '.join(assignments)} WHERE data_id = $1::uuid",
            *values,
        )

    async def create_voice_run(
        self,
        *,
        session_id: str,
        user_message_id: str,
        domain: str,
        risk_tier: str,
        expert_id: str | None,
        model_name: str,
    ) -> dict[str, Any]:
        row = await db.fetchrow(
            """
            INSERT INTO chief_run (
                session_id, user_message_id, domain, risk_tier,
                expert_id, model_name, recursion_mode, recursion_k, run_mode
            ) VALUES (
                $1::uuid, $2::uuid, $3, $4, $5::uuid, $6, 'voice', 0, 'voice'
            )
            RETURNING data_id::text AS id, status
            """,
            session_id,
            user_message_id,
            domain,
            risk_tier,
            expert_id,
            model_name,
        )
        return dict(row)

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        row = await db.fetchrow(
            """
            SELECT data_id::text AS id, session_id::text AS "sessionId",
                   user_message_id::text AS "userMessageId",
                   assistant_message_id::text AS "assistantMessageId",
                   status, domain, risk_tier AS "riskTier",
                   baseline_harness_id::text AS "baselineHarnessId",
                   selected_harness_id::text AS "selectedHarnessId",
                   expert_id::text AS "expertId", model_name AS "modelName",
                   run_mode AS "runMode",
                   answer, error, requires_approval AS "requiresApproval",
                   recursion_mode AS "recursionMode", recursion_k AS "recursionK",
                   input_tokens AS "inputTokens", output_tokens AS "outputTokens",
                   estimated_cost AS "estimatedCost",
                   run_mode AS "runMode",
                   regression_passed AS "regressionPassed",
                   auto_adopt_reason AS "autoAdoptReason",
                   approved_by::text AS "approvedBy", approve_time AS "approveTime",
                   create_time AS "createTime", update_time AS "updateTime"
              FROM chief_run
             WHERE data_id = $1::uuid AND is_deleted = false
             LIMIT 1
            """,
            run_id,
        )
        return db.to_dict(row)

    async def list_runs(self, session_id: str) -> list[dict[str, Any]]:
        rows = await db.fetch(
            """
            SELECT data_id::text AS id, status, domain, risk_tier AS "riskTier",
                   selected_harness_id::text AS "selectedHarnessId",
                   answer, error, requires_approval AS "requiresApproval",
                   recursion_mode AS "recursionMode", recursion_k AS "recursionK",
                   input_tokens AS "inputTokens", output_tokens AS "outputTokens",
                   estimated_cost AS "estimatedCost",
                   regression_passed AS "regressionPassed",
                   auto_adopt_reason AS "autoAdoptReason",
                   create_time AS "createTime", update_time AS "updateTime"
              FROM chief_run
             WHERE session_id = $1::uuid AND is_deleted = false
             ORDER BY chief_run.id DESC
            """,
            session_id,
        )
        return db.to_dicts(rows)

    async def add_event(
        self,
        run_id: str,
        stage: str,
        status: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        seq = int(
            await db.fetchval(
                "SELECT COALESCE(max(seq), 0) + 1 FROM chief_run_event WHERE run_id = $1::uuid",
                run_id,
            )
            or 1
        )
        await db.execute(
            """
            INSERT INTO chief_run_event (run_id, seq, stage, status, message, payload)
            VALUES ($1::uuid, $2, $3, $4, $5, $6::jsonb)
            """,
            run_id,
            seq,
            stage,
            status,
            message,
            _json(payload or {}),
        )

    async def list_events(self, run_id: str) -> list[dict[str, Any]]:
        rows = await db.fetch(
            """
            SELECT seq, stage, status, message, payload, create_time AS "createTime"
              FROM chief_run_event
             WHERE run_id = $1::uuid
             ORDER BY seq ASC
            """,
            run_id,
        )
        result = db.to_dicts(rows)
        for item in result:
            item["payload"] = json_value(item.get("payload"), {}) or {}
        return result

    async def active_harness(self, domain: str) -> dict[str, Any] | None:
        row = await db.fetchrow(
            """
            SELECT data_id::text AS id, name, domain, version,
                   parent_id::text AS "parentId", components,
                   content_hash AS "contentHash", status, evidence
              FROM chief_harness
             WHERE domain = $1 AND status = 'active' AND is_deleted = false
             ORDER BY version DESC
             LIMIT 1
            """,
            domain,
        )
        result = db.to_dict(row)
        if result:
            result["components"] = json_value(result.get("components"), {}) or {}
            result["evidence"] = json_value(result.get("evidence"), {}) or {}
        return result

    async def list_harnesses(self, domain: str = "") -> list[dict[str, Any]]:
        rows = await db.fetch(
            """
            SELECT data_id::text AS id, name, domain, version,
                   parent_id::text AS "parentId", components,
                   content_hash AS "contentHash", status, evidence,
                   create_time AS "createTime"
              FROM chief_harness
             WHERE is_deleted = false
               AND ($1::text = '' OR domain = $1::text)
             ORDER BY domain ASC, version DESC
            """,
            domain,
        )
        result = db.to_dicts(rows)
        for item in result:
            item["components"] = json_value(item.get("components"), {}) or {}
            item["evidence"] = json_value(item.get("evidence"), {}) or {}
        return result

    async def create_harness(
        self,
        *,
        name: str,
        domain: str,
        components: dict[str, Any],
        hash_value: str,
        parent_id: str | None,
        status: str,
        evidence: dict[str, Any] | None = None,
        created_by: str | None = None,
    ) -> dict[str, Any]:
        version = int(
            await db.fetchval(
                "SELECT COALESCE(max(version), 0) + 1 FROM chief_harness WHERE domain = $1",
                domain,
            )
            or 1
        )
        row = await db.fetchrow(
            """
            INSERT INTO chief_harness (
                name, domain, version, parent_id, components, content_hash,
                status, evidence, create_by
            ) VALUES ($1, $2, $3, $4::uuid, $5::jsonb, $6, $7, $8::jsonb, $9::uuid)
            RETURNING data_id::text AS id, name, domain, version,
                      parent_id::text AS "parentId",
                      content_hash AS "contentHash", status, evidence
            """,
            name,
            domain,
            version,
            parent_id,
            _json(components),
            hash_value,
            status,
            _json(evidence or {}),
            created_by,
        )
        result = dict(row)
        result["components"] = components
        result["evidence"] = json_value(result.get("evidence"), {}) or {}
        return result

    async def activate_harness(self, harness_id: str, domain: str) -> None:
        await db.execute(
            """
            UPDATE chief_harness
               SET status = 'superseded', update_time = now()
             WHERE domain = $1 AND status = 'active' AND data_id <> $2::uuid
            """,
            domain,
            harness_id,
        )
        await db.execute(
            """
            UPDATE chief_harness
               SET status = 'active', update_time = now()
             WHERE data_id = $1::uuid
            """,
            harness_id,
        )

    async def add_candidate(
        self,
        *,
        run_id: str,
        label: str,
        scope: str,
        step: int,
        harness: dict[str, Any],
        harness_id: str,
        answer: str,
        score: float,
        latency_ms: int,
        input_tokens: int,
        output_tokens: int,
        estimated_cost: float,
        trace: dict[str, Any],
    ) -> dict[str, Any]:
        row = await db.fetchrow(
            """
            INSERT INTO chief_candidate (
                run_id, label, scope, step, harness, harness_id, answer,
                score, latency_ms, input_tokens, output_tokens, estimated_cost, trace
            ) VALUES (
                $1::uuid, $2, $3, $4, $5::jsonb, $6::uuid, $7,
                $8, $9, $10, $11, $12, $13::jsonb
            )
            RETURNING data_id::text AS id
            """,
            run_id,
            label,
            scope,
            step,
            _json(harness),
            harness_id,
            answer,
            score,
            latency_ms,
            input_tokens,
            output_tokens,
            estimated_cost,
            _json(trace),
        )
        return dict(row)

    async def list_candidates(self, run_id: str) -> list[dict[str, Any]]:
        rows = await db.fetch(
            """
            SELECT data_id::text AS id, label, scope, step, harness,
                   harness_id::text AS "harnessId", answer, score,
                   latency_ms AS "latencyMs", input_tokens AS "inputTokens",
                   output_tokens AS "outputTokens",
                   estimated_cost AS "estimatedCost",
                   status, trace, create_time AS "createTime"
              FROM chief_candidate
             WHERE run_id = $1::uuid
             ORDER BY chief_candidate.id ASC
            """,
            run_id,
        )
        result = db.to_dicts(rows)
        for item in result:
            item["harness"] = json_value(item.get("harness"), {}) or {}
            item["trace"] = json_value(item.get("trace"), {}) or {}
            item["score"] = float(item.get("score") or 0)
            item["estimatedCost"] = float(item.get("estimatedCost") or 0)
        return result

    async def add_reflection(
        self,
        domain: str,
        harness_id: str,
        lessons: dict[str, Any],
        score: float,
        created_by: str | None,
    ) -> None:
        await db.execute(
            """
            INSERT INTO chief_reflection (domain, harness_id, lessons, score, create_by)
            VALUES ($1, $2::uuid, $3::jsonb, $4, $5::uuid)
            """,
            domain,
            harness_id,
            _json(lessons),
            score,
            created_by,
        )

    async def recent_reflections(self, domain: str, limit: int = 3) -> list[dict[str, Any]]:
        rows = await db.fetch(
            """
            SELECT lessons, score, create_time AS "createTime"
              FROM chief_reflection
             WHERE domain = $1
             ORDER BY create_time DESC
             LIMIT $2
            """,
            domain,
            limit,
        )
        result = db.to_dicts(rows)
        for item in result:
            item["lessons"] = json_value(item.get("lessons"), {}) or {}
        return result

    async def reflection_stats(self, domain: str) -> dict[str, Any]:
        row = await db.fetchrow(
            """
            SELECT count(*) AS count, COALESCE(avg(score), 0) AS "averageScore"
              FROM chief_reflection
             WHERE domain = $1
            """,
            domain,
        )
        return {
            "count": int(row["count"] or 0),
            "averageScore": float(row["averageScore"] or 0),
        }

    async def add_regression_case(
        self,
        *,
        domain: str,
        question: str,
        source_answer: str,
        expected_score: float,
        source_run_id: str,
        harness_id: str,
    ) -> None:
        await db.execute(
            """
            INSERT INTO chief_regression_case (
                domain, question, source_answer, expected_score,
                source_run_id, harness_id
            ) VALUES ($1, $2, $3, $4, $5::uuid, $6::uuid)
            """,
            domain,
            question,
            source_answer[:12000],
            expected_score,
            source_run_id,
            harness_id,
        )

    async def regression_cases(self, domain: str, limit: int) -> list[dict[str, Any]]:
        rows = await db.fetch(
            """
            SELECT data_id::text AS id, question, source_answer,
                   expected_score AS "expectedScore",
                   source_run_id::text AS "sourceRunId",
                   harness_id::text AS "harnessId"
              FROM chief_regression_case
             WHERE domain = $1 AND enabled = true AND is_deleted = false
             ORDER BY id DESC
             LIMIT $2
            """,
            domain,
            limit,
        )
        result = db.to_dicts(rows)
        for item in result:
            item["expectedScore"] = float(item["expectedScore"] or 0)
        return result

    async def get_settings(self) -> dict[str, Any]:
        row = await db.fetchrow(
            """
            SELECT enabled, recursion_mode AS "recursionMode",
                   recursion_k AS "recursionK", recursion_max AS "recursionMax",
                   regression_enabled AS "regressionEnabled",
                   regression_cases AS "regressionCases",
                   auto_adopt_min_score AS "autoAdoptMinScore",
                   auto_adopt_min_gain AS "autoAdoptMinGain",
                   domain_experts AS "domainExperts",
                   update_by::text AS "updateBy", update_time AS "updateTime"
              FROM chief_setting
             WHERE id = 1
             LIMIT 1
            """
        )
        if not row:
            await db.execute(
                """
                INSERT INTO chief_setting (
                    id, enabled, recursion_mode, recursion_k, recursion_max,
                    regression_enabled, regression_cases,
                    auto_adopt_min_score, auto_adopt_min_gain
                ) VALUES (1, true, 'sequential', 1, $1, $2, $3, $4, $5)
                ON CONFLICT (id) DO NOTHING
                """,
                settings.chief_recursion_max,
                settings.chief_regression_enabled,
                settings.chief_regression_cases,
                settings.chief_auto_adopt_min_score,
                settings.chief_auto_adopt_min_gain,
            )
            return await self.get_settings()
        result = dict(row)
        result["autoAdoptMinScore"] = float(result["autoAdoptMinScore"] or 0)
        result["autoAdoptMinGain"] = float(result["autoAdoptMinGain"] or 0)
        result["domainExperts"] = json_value(result.get("domainExperts"), {}) or {}
        return result

    async def save_settings(
        self, payload: dict[str, Any], updated_by: str | None
    ) -> dict[str, Any]:
        await db.execute(
            """
            INSERT INTO chief_setting (
                id, enabled, recursion_mode, recursion_k, recursion_max,
                regression_enabled, regression_cases,
                auto_adopt_min_score, auto_adopt_min_gain, domain_experts,
                update_by, update_time
            ) VALUES (
                1, $1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10::uuid, now()
            )
            ON CONFLICT (id) DO UPDATE SET
                enabled = EXCLUDED.enabled,
                recursion_mode = EXCLUDED.recursion_mode,
                recursion_k = EXCLUDED.recursion_k,
                recursion_max = EXCLUDED.recursion_max,
                regression_enabled = EXCLUDED.regression_enabled,
                regression_cases = EXCLUDED.regression_cases,
                auto_adopt_min_score = EXCLUDED.auto_adopt_min_score,
                auto_adopt_min_gain = EXCLUDED.auto_adopt_min_gain,
                domain_experts = EXCLUDED.domain_experts,
                update_by = EXCLUDED.update_by,
                update_time = now()
            """,
            payload["enabled"],
            payload["recursionMode"],
            payload["recursionK"],
            payload["recursionMax"],
            payload["regressionEnabled"],
            payload["regressionCases"],
            payload["autoAdoptMinScore"],
            payload["autoAdoptMinGain"],
            _json(payload["domainExperts"]),
            updated_by,
        )
        return await self.get_settings()

    async def get_call_settings(self) -> dict[str, Any]:
        row = await db.fetchrow(
            """
            SELECT push_to_talk_key AS "pushToTalkKey",
                   asr_url AS "asrUrl", tts_url AS "ttsUrl",
                   update_by::text AS "updateBy", update_time AS "updateTime"
              FROM call_setting
             WHERE id = 1
             LIMIT 1
            """
        )
        if not row:
            await db.execute(
                """
                INSERT INTO call_setting (
                    id, push_to_talk_key, asr_url, tts_url
                ) VALUES (
                    1, 'Escape',
                    'https://api.deepseek.com/v1/tools/asr',
                    'https://api.deepseek.com/v1/tools/tts'
                )
                ON CONFLICT (id) DO NOTHING
                """
            )
            return await self.get_call_settings()
        return dict(row)

    async def save_call_settings(
        self, payload: dict[str, Any], updated_by: str | None
    ) -> dict[str, Any]:
        await db.execute(
            """
            INSERT INTO call_setting (
                id, push_to_talk_key, asr_url, tts_url,
                update_by, update_time
            ) VALUES (1, $1, $2, $3, $4::uuid, now())
            ON CONFLICT (id) DO UPDATE SET
                push_to_talk_key = EXCLUDED.push_to_talk_key,
                asr_url = EXCLUDED.asr_url,
                tts_url = EXCLUDED.tts_url,
                update_by = EXCLUDED.update_by,
                update_time = now()
            """,
            payload["pushToTalkKey"],
            payload["asrUrl"],
            payload["ttsUrl"],
            updated_by,
        )
        return await self.get_call_settings()
