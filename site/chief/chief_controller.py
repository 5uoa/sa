"""总管 Phase 1 + Phase 2：真实会话与 Harness² 单步递归。"""
import asyncio
import hashlib
import html as html_lib
import json
import re
import time
import uuid as uuid_lib
from typing import Any, AsyncIterator
from urllib.parse import urlsplit

from admin import auth
from admin.admin_model import OperationLogModel, QuotaModel
from common import ApiProblem, fail, json_value, text, to_bool, to_int
from chief.context_builder import (
    build_attachment_context,
    build_document_context,
    build_user_content,
    select_expert,
    select_model,
    selected_resources,
)
from chief.chief_model import ChiefModel
from chief.evaluator import choose_candidate, score_answer
from chief.web_fetch import fetch_web_urls, prepare_web_fetch, web_fetch_context
from chief.harness_schema import (
    build_base_harness,
    build_variants,
    classify_domain,
    classify_risk,
    component_diff,
    content_hash,
    render_system_prompt,
)
from chief.web_search import prepare_web_search, search_context, search_web
from admin.model_probe import chat
from llm.adapters import ProviderError, model_target, stream_chat
from llm.context import fit_messages_to_budget
from settings import settings

_project_execution_tasks: set[str] = set()


def _normalize_push_to_talk_key(value: Any) -> str:
    key = text(value).strip()
    if key.lower() in {"esc", "escape"}:
        return "Escape"
    if key.lower() in {"fn", "globe"}:
        return "Fn"
    if key == " ":
        return "Space"
    return key


def _id(value: Any, field: str = "id") -> str:
    try:
        return str(uuid_lib.UUID(text(value)))
    except (ValueError, AttributeError, TypeError):
        fail("无效的记录 ID。", {field: "无效的记录 ID。"})
    return ""


def normalize_provider_error(exc: Exception) -> str:
    if isinstance(exc, ProviderError):
        return str(exc)
    return f"{exc.__class__.__name__}: {exc}"


def _plain_markdown_html(value: str) -> str:
    lines = [line.strip() for line in value.strip().splitlines() if line.strip()]
    parts: list[str] = []
    for line in lines:
        if line.startswith("### "):
            parts.append(f"<h3>{html_lib.escape(line[4:])}</h3>")
        elif line.startswith("## "):
            parts.append(f"<h2>{html_lib.escape(line[3:])}</h2>")
        elif line.startswith("# "):
            parts.append(f"<h1>{html_lib.escape(line[2:])}</h1>")
        elif line.startswith(("- ", "* ")):
            parts.append(f"<p>• {html_lib.escape(line[2:])}</p>")
        else:
            parts.append(f"<p>{html_lib.escape(line)}</p>")
    return "".join(parts)


def _document_content(body: dict[str, Any]) -> tuple[str, str]:
    content_text = text(body.get("content_text") or body.get("contentText"))
    content_html = text(body.get("content_html") or body.get("contentHtml"))
    if not content_text and content_html:
        content_text = html_lib.unescape(re.sub(r"<[^>]+>", " ", content_html))
        content_text = re.sub(r"\s+", " ", content_text).strip()
    if not content_text:
        fail("文档内容不能为空。", {"content": "文档内容不能为空。"})
    content_html = content_html or _plain_markdown_html(content_text)
    content_html = re.sub(
        r"<(script|style)[^>]*>.*?</\1>",
        "",
        content_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    content_html = re.sub(
        r"\s+on[a-z]+\s*=\s*(['\"]).*?\1",
        "",
        content_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return content_html, content_text


def _project_document_title(project_name: str, kind: str) -> str:
    labels = {
        "requirements": "需求文档",
        "solution": "方案文档",
        "task_plan": "计划清单",
    }
    return f"{project_name} · {labels.get(kind, kind)}"


def _task_plan_markdown(plan: dict[str, Any]) -> str:
    lines = ["# 计划清单"]
    packages = plan.get("packages") if isinstance(plan, dict) else []
    for package in packages if isinstance(packages, list) else []:
        if not isinstance(package, dict):
            continue
        lines.extend(["", f"## {text(package.get('name')) or '任务包'}"])
        tasks = package.get("tasks") if isinstance(package.get("tasks"), list) else []
        for task in tasks:
            if not isinstance(task, dict):
                continue
            key = text(task.get("key"))
            title = text(task.get("title")) or "任务"
            lines.append(f"- {f'[{key}] ' if key else ''}{title}")
            description = text(task.get("description"))
            if description:
                lines.append(f"  - 目标：{description}")
            acceptance = text(
                task.get("acceptance_criteria") or task.get("acceptanceCriteria")
            )
            if acceptance:
                lines.append(f"  - 验收：{acceptance}")
    return "\n".join(lines).strip()


def _append_user_context(
    content: str | list[dict[str, Any]], context: str
) -> str | list[dict[str, Any]]:
    if not context:
        return content
    if isinstance(content, str):
        return f"{content}\n\n{context}"
    blocks = [dict(item) for item in content]
    for block in blocks:
        if block.get("type") == "text":
            block["text"] = f"{block.get('text', '')}\n\n{context}"
            return blocks
    return [{"type": "text", "text": context}, *blocks]


def _document_source(
    project: dict[str, Any], stage: str
) -> tuple[str | None, str | None, int | None]:
    upstream_kind = {
        "solution": "requirements",
        "task_plan": "solution",
    }.get(stage)
    if not upstream_kind:
        return None, None, None
    document = (project.get("documents") or {}).get(upstream_kind)
    if not document or int(document.get("latestVersionNo") or 0) <= 0:
        return None, None, None
    versions = document.get("versions") or []
    latest = next(
        (
            item
            for item in versions
            if int(item.get("versionNo") or 0)
            == int(document.get("latestVersionNo") or 0)
        ),
        versions[0] if versions else None,
    )
    if not latest:
        return document.get("id"), None, int(document.get("latestVersionNo") or 0)
    return (
        document.get("id"),
        latest.get("id"),
        int(latest.get("versionNo") or document.get("latestVersionNo") or 0),
    )


class ChiefController:
    def __init__(self) -> None:
        self.store = ChiefModel()
        self.log = OperationLogModel()

    async def _audit(self, action: str, target: str) -> None:
        await self.log.add(
            auth.actor_id(), auth.actor_name(), action, target
        )

    async def _scoped_document(
        self, body: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        session_id = _id(body.get("session_id") or body.get("sessionId"), "session_id")
        document_id = _id(
            body.get("document_id") or body.get("documentId"), "document_id"
        )
        session = await self.store.get_session(session_id)
        if not session:
            raise ApiProblem(404, "会话不存在。")
        document = await self.store.get_document(document_id)
        if not document:
            raise ApiProblem(404, "文档不存在。")
        same_project = bool(
            session.get("projectId")
            and document.get("projectId") == session.get("projectId")
        )
        if document.get("sessionId") != session_id and not same_project:
            raise ApiProblem(404, "文档不属于当前会话或项目。")
        return session, document

    async def list_sessions(self, body: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "items": await self.store.list_sessions(bool((body or {}).get("archived")))
        }

    async def create_session(self, body: dict[str, Any]) -> dict[str, Any]:
        project_id = text(body.get("project_id") or body.get("projectId"))
        project = None
        if project_id:
            project_id = _id(project_id, "project_id")
            project = await self.store.get_project(project_id)
            if not project:
                raise ApiProblem(404, "项目不存在。")
        title = text(body.get("title")) or (project["name"] if project else "新会话")
        session = await self.store.create_session(
            title,
            "project" if project else "general",
            "T2",
            project_id if project else None,
            project.get("expertId") if project else None,
        )
        await self._audit("新建总管会话", session["title"])
        return {
            **session,
            "projectName": project["name"] if project else "",
            "messages": [],
            "runs": [],
            "documents": [],
        }

    async def list_projects(self) -> dict[str, Any]:
        return {"items": await self.store.list_projects()}

    async def _web_search_context(
        self,
        run_id: str,
        message: str,
        model: dict[str, Any],
        api_key: str,
    ) -> str:
        should_search, query = prepare_web_search(message)
        if not should_search:
            return ""
        result = await search_web(
            query,
            original_question=message,
            preferred_model=model,
            preferred_key=api_key,
        )
        results = result.get("results") or []
        await self.store.add_event(
            run_id,
            "search",
            "completed" if result.get("ok") else "failed",
            (
                f"网页搜索完成，找到 {len(results)} 条结果"
                if result.get("ok") and results
                else text(result.get("message"))
            ),
            {
                "query": query,
                "results": [
                    {
                        "title": item.get("title"),
                        "url": item.get("url"),
                        "siteName": item.get("siteName"),
                        "date": item.get("date"),
                        "authority": item.get("authority"),
                    }
                    for item in results
                ],
            },
        )
        if results:
            return search_context(results)
        if result.get("ok"):
            return (
                "本轮网页搜索没有找到结果。涉及实时事实时不得编造，"
                "应明确告知用户未检索到可靠来源。"
            )
        return (
            f"本轮网页搜索失败：{text(result.get('message'))}。"
            "涉及实时事实时必须明确说明无法联网核实，不得编造。"
        )

    async def _web_fetch_context(
        self,
        run_id: str,
        message: str,
        model: dict[str, Any],
        api_key: str,
    ) -> str:
        urls = prepare_web_fetch(message)
        if not urls:
            return ""
        results = await fetch_web_urls(
            urls,
            preferred_model=model,
            preferred_key=api_key,
        )
        successful = [item for item in results if item.get("ok")]
        await self.store.add_event(
            run_id,
            "fetch",
            "completed" if successful else "failed",
            (
                f"网页抓取完成，成功 {len(successful)}/{len(results)} 个页面"
                if successful
                else "网页抓取失败"
            ),
            {
                "pages": [
                    {
                        "url": item.get("url"),
                        "finalUrl": item.get("finalUrl"),
                        "title": item.get("title"),
                        "ok": bool(item.get("ok")),
                        "message": item.get("message", ""),
                        "chars": len(text(item.get("text"))),
                    }
                    for item in results
                ]
            },
        )
        return web_fetch_context(results)

    async def list_experts(self) -> dict[str, Any]:
        return {
            "items": [
                {
                    "id": item["id"],
                    "name": item["name"],
                    "role": item["role"],
                    "model": item["model"],
                    "enabled": item["enabled"],
                }
                for item in await self._list_experts()
            ]
        }

    async def _project_expert_id(self, value: Any) -> str | None:
        expert_id = text(value)
        if not expert_id:
            return None
        expert_id = _id(expert_id, "expert_id")
        expert = next(
            (item for item in await self._list_experts() if item["id"] == expert_id),
            None,
        )
        if not expert or not expert.get("enabled"):
            fail("绑定的专家不存在或已停用。", {"expertId": "请选择启用中的专家 Agent。"})
        return expert_id

    async def get_workspace(self, body: dict[str, Any]) -> dict[str, Any]:
        return {
            "items": await self.store.list_workspace(
                bool(body.get("archived") or body.get("showArchived"))
            )
        }

    async def create_project(self, body: dict[str, Any]) -> dict[str, Any]:
        name = text(body.get("name") or body.get("title"))
        if not name:
            fail("请输入项目名称。", {"name": "项目名称不能为空。"})
        source_session_id = text(
            body.get("source_session_id") or body.get("sourceSessionId")
        )
        if source_session_id:
            source_session_id = _id(source_session_id, "source_session_id")
            source_session = await self.store.get_session(source_session_id)
            if not source_session:
                raise ApiProblem(404, "来源总管会话不存在。")
            if source_session.get("projectId"):
                raise ApiProblem(409, "项目会话不能重复立项。")
        context = body.get("context")
        if not isinstance(context, dict):
            context = {
                "objective": text(body.get("objective")),
                "scope": text(body.get("scope")),
                "constraints": [],
            }
        project = await self.store.create_project(
            name[:200],
            text(body.get("description")),
            text(body.get("status")) or "进行中",
            context,
            await self._project_expert_id(
                body.get("expert_id") or body.get("expertId")
            ),
            source_session_id or None,
        )
        await self._audit("新建项目", project["name"])
        return project

    async def update_project(self, body: dict[str, Any]) -> dict[str, Any]:
        project_id = _id(body.get("project_id") or body.get("projectId"), "project_id")
        current = await self.store.get_project(project_id)
        if not current:
            raise ApiProblem(404, "项目不存在。")
        fields: dict[str, Any] = {}
        if "name" in body or "title" in body:
            name = text(body.get("name") or body.get("title"))
            if not name:
                fail("项目名称不能为空。", {"name": "项目名称不能为空。"})
            fields["name"] = name[:200]
        if "description" in body:
            fields["description"] = text(body.get("description"))
        if "status" in body:
            fields["status"] = text(body.get("status")) or current["status"]
        if "context" in body:
            context = body.get("context")
            if not isinstance(context, dict):
                fail("项目背景必须是对象。", {"context": "项目背景格式不正确。"})
            fields["context"] = context
        if "expertId" in body or "expert_id" in body:
            fields["expertId"] = await self._project_expert_id(
                body.get("expertId") or body.get("expert_id")
            )
        project = await self.store.update_project(project_id, fields)
        if not project:
            raise ApiProblem(404, "项目不存在。")
        await self._audit("修改项目", project["name"])
        return project

    async def set_project_archived(
        self, body: dict[str, Any], archived: bool
    ) -> None:
        project_id = _id(body.get("project_id") or body.get("projectId"), "project_id")
        project = await self.store.get_project(project_id)
        if not project:
            raise ApiProblem(404, "项目不存在。")
        if not await self.store.set_project_archived(project_id, archived):
            raise ApiProblem(404, "项目不存在。")
        await self._audit("归档项目" if archived else "恢复项目", project["name"])

    async def duplicate_project(self, body: dict[str, Any]) -> dict[str, Any]:
        project_id = _id(body.get("project_id") or body.get("projectId"), "project_id")
        project = await self.store.get_project(project_id)
        if not project:
            raise ApiProblem(404, "项目不存在。")
        requested_name = text(body.get("name"))
        copy = await self.store.duplicate_project(
            project_id, requested_name[:200] or f"{project['name']} 副本"
        )
        if not copy:
            raise ApiProblem(404, "项目不存在。")
        await self._audit("复制项目", copy["name"])
        return copy

    async def delete_project(self, body: dict[str, Any]) -> None:
        project_id = _id(body.get("project_id") or body.get("projectId"), "project_id")
        project = await self.store.get_project(project_id)
        if not project:
            raise ApiProblem(404, "项目不存在。")
        if not await self.store.delete_project(project_id):
            raise ApiProblem(404, "项目不存在。")
        await self._audit("删除项目", project["name"])

    async def create_document(self, body: dict[str, Any]) -> dict[str, Any]:
        session_id = _id(body.get("session_id") or body.get("sessionId"), "session_id")
        session = await self.store.get_session(session_id)
        if not session:
            raise ApiProblem(404, "会话不存在。")
        content_html, content_text = _document_content(body)
        if len(content_text) > 500000:
            fail("文档内容过长。", {"content": "单个文档不能超过 50 万字符。"})
        source_message_id = text(
            body.get("source_message_id") or body.get("sourceMessageId")
        )
        if source_message_id:
            source_message_id = _id(source_message_id, "source_message_id")
            source_message = await self.store.get_message(source_message_id)
            if not source_message or source_message.get("sessionId") != session_id:
                raise ApiProblem(404, "来源消息不属于当前会话。")
        else:
            source_message_id = None
        existing = await self.store.list_documents(session_id, session.get("projectId"))
        custom_count = sum(1 for item in existing if item.get("kind") == "custom")
        title = text(body.get("title")) or (
            f"{session['title']} · 文档 {custom_count + 1}"
        )
        document = await self.store.create_document(
            session_id,
            session.get("projectId"),
            source_message_id,
            title[:200],
            content_html,
            content_text,
        )
        await self._audit("生成会话文档", document["title"])
        return document

    async def update_document(self, body: dict[str, Any]) -> dict[str, Any]:
        _, document = await self._scoped_document(body)
        if document.get("kind") != "custom":
            raise ApiProblem(409, "项目流程文档请在对应阶段中编辑。")
        content_html, content_text = _document_content(body)
        if len(content_text) > 500000:
            fail("文档内容过长。", {"content": "单个文档不能超过 50 万字符。"})
        title = text(body.get("title")) or document["title"]
        updated = await self.store.update_document(
            document["id"], title[:200], content_html, content_text
        )
        if not updated:
            raise ApiProblem(404, "文档不存在。")
        await self._audit("修改会话文档", updated["title"])
        return updated

    async def delete_document(self, body: dict[str, Any]) -> None:
        _, document = await self._scoped_document(body)
        kind = text(document.get("kind")) or "custom"
        if kind == "custom":
            if not await self.store.delete_document(document["id"]):
                raise ApiProblem(404, "文档不存在。")
            await self._audit("删除会话文档", document["title"])
            return
        project_id = text(document.get("projectId"))
        project = (
            await self.store.get_project(project_id)
            if project_id
            else None
        )
        if not project:
            raise ApiProblem(404, "项目不存在。")
        if project.get("phase") in {
            "tasks_confirmed",
            "executing",
            "reviewing",
            "completed",
        }:
            raise ApiProblem(409, "项目已生成任务，请先进入调整状态后再删除流程文档。")
        if not await self.store.delete_project_workflow_document(project_id, kind):
            raise ApiProblem(404, "文档不存在。")
        await self._audit("删除项目流程文档", document["title"])

    async def attach_document_to_session(
        self, body: dict[str, Any]
    ) -> dict[str, Any]:
        session, document = await self._scoped_document(body)
        inserted = await self.store.attach_document(session["id"], document["id"])
        message = None
        if inserted:
            message = await self.store.add_message(
                session["id"],
                "user",
                f"已将文档《{document['title']}》加入当前会话。",
                meta={
                    "documentAdded": True,
                    "documentId": document["id"],
                    "documentTitle": document["title"],
                },
                attachments=[
                    {
                        "uuid": document["id"],
                        "documentId": document["id"],
                        "name": document["title"],
                        "ext": "doc",
                        "mimeType": "text/html",
                        "size": len(text(document.get("contentText")).encode("utf-8")),
                        "kind": "document",
                    }
                ],
            )
            await self._audit("文档加入会话", document["title"])
        return {
            "document": {**document, "attached": True},
            "message": message,
            "alreadyAttached": not inserted,
        }

    async def save_project_document(self, body: dict[str, Any]) -> dict[str, Any]:
        project_id = _id(body.get("project_id") or body.get("projectId"), "project_id")
        stage = text(body.get("stage"))
        if stage not in {"requirements", "solution"}:
            fail("项目文档阶段不合法。", {"stage": "仅支持需求或方案。"})
        project = await self.store.get_project(project_id)
        if not project:
            raise ApiProblem(404, "项目不存在。")
        content_text = text(body.get("content_text") or body.get("contentText"))
        content_html = text(body.get("content_html") or body.get("contentHtml"))
        if not content_text and content_html:
            content_text = html_lib.unescape(re.sub(r"<[^>]+>", " ", content_html))
            content_text = re.sub(r"\s+", " ", content_text).strip()
        if not content_text:
            fail("内容不能为空。", {"content": "请先填写或生成内容。"})
        content_html = content_html or _plain_markdown_html(content_text)
        source_deliverable_id, source_version_id, source_version_no = _document_source(
            project, stage
        )
        await self.store.invalidate_project_downstream(project_id, stage)
        result = await self.store.save_project_document(
            project_id,
            stage,
            content_html,
            content_text,
        )
        await self.store.save_project_deliverable_draft(
            project_id,
            stage,
            _project_document_title(project["name"], stage),
            content_html,
            content_text,
            source_deliverable_id,
            source_version_id,
            source_version_no,
        )
        await self._audit(
            "保存项目需求" if stage == "requirements" else "保存项目方案",
            project["name"],
        )
        return result or {}

    async def generate_project_document(
        self, body: dict[str, Any]
    ) -> dict[str, Any]:
        project_id = _id(body.get("project_id") or body.get("projectId"), "project_id")
        stage = text(body.get("stage"))
        if stage not in {"requirements", "solution"}:
            fail("项目文档阶段不合法。", {"stage": "仅支持需求或方案。"})
        project = await self.store.get_project(project_id)
        if not project:
            raise ApiProblem(404, "项目不存在。")
        project = await self._ensure_project_generation_expert(project)
        if not project.get("expertId"):
            raise ApiProblem(409, "请先为项目绑定专家 Agent。")
        if stage == "requirements":
            prompt = (
                f"请为项目「{project['name']}」生成一份简洁、可确认的需求文档。"
                f"项目说明：{project.get('description', '')}。"
                f"项目背景：{json_value(project.get('context'), {})}。"
                "必须包含：目标、范围、不包含事项、交付标准、时间要求。"
                "只输出可以直接确认的正式内容，不要寒暄。"
            )
        elif stage == "solution":
            if not project.get("requirementConfirmedAt"):
                raise ApiProblem(409, "请先确认项目需求。")
            prompt = (
                f"请根据项目「{project['name']}」已确认的需求生成项目方案。\n"
                f"需求：{project.get('requirementText', '')}\n"
                "必须包含：整体思路、阶段、关键路径、风险、依赖、验收方式。"
                "只输出方案正文，不要寒暄。"
            )
        else:
            fail("项目文档阶段不合法。", {"stage": "仅支持需求或方案。"})
        from admin.admin_controller import ExpertController

        response = await ExpertController().chat(
            {
                "id": project["expertId"],
                "project_id": project_id,
                "message": prompt,
            }
        )
        if not response.get("ok") or not text(response.get("content")):
            raise ApiProblem(502, text(response.get("message")) or "专家生成失败。")
        content = text(response["content"])
        saved = await self.save_project_document(
            {
                "projectId": project_id,
                "stage": stage,
                "contentText": content,
                "contentHtml": _plain_markdown_html(content),
            }
        )
        await self._audit(
            "生成项目需求" if stage == "requirements" else "生成项目方案",
            project["name"],
        )
        return {
            **(saved or {}),
            "contentHtml": _plain_markdown_html(content),
            "contentText": content,
            "sessionId": response.get("sessionId"),
        }

    async def confirm_project_document(
        self, body: dict[str, Any]
    ) -> dict[str, Any]:
        project_id = _id(body.get("project_id") or body.get("projectId"), "project_id")
        stage = text(body.get("stage"))
        if stage not in {"requirements", "solution"}:
            fail("项目文档阶段不合法。", {"stage": "仅支持需求或方案。"})
        project = await self.store.get_project(project_id)
        if not project:
            raise ApiProblem(404, "项目不存在。")
        result = await self.store.confirm_project_document(project_id, stage)
        if not result:
            fail("内容不能为空。", {"content": "请先生成或填写内容。"})
        content_text = text(
            project.get("requirementText")
            if stage == "requirements"
            else project.get("solutionText")
        )
        content_html = text(
            project.get("requirementHtml")
            if stage == "requirements"
            else project.get("solutionHtml")
        )
        content_html = content_html or _plain_markdown_html(content_text)
        if not content_text:
            fail("内容不能为空。", {"content": "请先生成或填写内容。"})
        version = await self.store.confirm_project_deliverable_version(
            project_id,
            stage,
            _project_document_title(project["name"], stage),
            content_html,
            content_text,
            hashlib.sha256(content_text.encode("utf-8")).hexdigest(),
            auth.actor_id(),
        )
        action = "确认项目需求" if stage == "requirements" else "确认项目方案"
        if version.get("unchanged"):
            action += "（内容无变化）"
        await self._audit(action, f"{project['name']} · V{version['versionNo']}")
        return {**result, "artifactVersion": version}

    async def save_project_task_plan(
        self, body: dict[str, Any]
    ) -> dict[str, Any]:
        project_id = _id(body.get("project_id") or body.get("projectId"), "project_id")
        project = await self.store.get_project(project_id)
        if not project:
            raise ApiProblem(404, "项目不存在。")
        project = await self._ensure_project_generation_expert(project)
        if not project.get("solutionConfirmedAt"):
            raise ApiProblem(409, "请先确认项目方案。")
        plan = body.get("plan")
        if not isinstance(plan, dict):
            fail("任务计划格式不正确。", {"plan": "任务计划必须是对象。"})
        packages = plan.get("packages")
        if not isinstance(packages, list) or not packages:
            fail("任务计划不能为空。", {"plan": "至少需要一个任务包。"})
        source_deliverable_id, source_version_id, source_version_no = _document_source(
            project, "task_plan"
        )
        await self.store.invalidate_project_downstream(project_id, "task_plan")
        result = await self.store.save_project_task_plan(project_id, plan)
        plan_text = _task_plan_markdown(plan)
        await self.store.save_project_deliverable_draft(
            project_id,
            "task_plan",
            _project_document_title(project["name"], "task_plan"),
            _plain_markdown_html(plan_text),
            plan_text,
            source_deliverable_id,
            source_version_id,
            source_version_no,
        )
        await self._audit("保存项目任务分解", project["name"])
        return result or {}

    async def generate_project_task_plan(
        self, body: dict[str, Any]
    ) -> dict[str, Any]:
        project_id = _id(body.get("project_id") or body.get("projectId"), "project_id")
        project = await self.store.get_project(project_id)
        if not project:
            raise ApiProblem(404, "项目不存在。")
        if not project.get("solutionConfirmedAt"):
            raise ApiProblem(409, "请先确认项目方案。")
        if not project.get("expertId"):
            raise ApiProblem(409, "请先为项目绑定专家 Agent。")
        prompt = (
            f"项目：{project['name']}\n"
            f"已确认需求：{project.get('requirementText', '')}\n"
            f"已确认方案：{project.get('solutionText', '')}\n"
            "请按项目→任务包→任务三层结构分解。只返回合法 JSON，不要 Markdown 代码块。"
            '格式：{"packages":[{"name":"任务包名","tasks":[{"key":"T1",'
            '"title":"任务标题","description":"任务目标","acceptanceCriteria":"验收标准",'
            '"priority":"P1","dependsOn":[]}]}]}'
        )
        from admin.admin_controller import ExpertController

        response = await ExpertController().chat(
            {
                "id": project["expertId"],
                "project_id": project_id,
                "message": prompt,
            }
        )
        content = text(response.get("content"))
        if not response.get("ok") or not content:
            raise ApiProblem(502, text(response.get("message")) or "任务分解生成失败。")
        match = re.search(r"\{[\s\S]*\}", content)
        if not match:
            raise ApiProblem(502, "专家未返回有效任务计划。")
        try:
            plan = json.loads(match.group(0))
        except ValueError:
            raise ApiProblem(502, "专家返回的任务计划不是合法 JSON，请重试。")
        if not isinstance(plan.get("packages"), list) or not plan["packages"]:
            raise ApiProblem(502, "任务计划缺少任务包。")
        saved = await self.save_project_task_plan(
            {
                "projectId": project_id,
                "plan": plan,
            }
        )
        await self._audit("生成项目任务分解", project["name"])
        return {
            **(saved or {}),
            "plan": plan,
            "sessionId": response.get("sessionId"),
        }

    async def confirm_project_task_plan(
        self, body: dict[str, Any]
    ) -> dict[str, Any]:
        project_id = _id(body.get("project_id") or body.get("projectId"), "project_id")
        project = await self.store.get_project(project_id)
        if not project:
            raise ApiProblem(404, "项目不存在。")
        result = await self.store.confirm_project_task_plan(project_id)
        if not result:
            fail("任务计划不能为空。", {"plan": "请先生成或保存任务计划。"})
        plan = project.get("taskPlan") or {}
        plan_text = _task_plan_markdown(plan)
        version = await self.store.confirm_project_deliverable_version(
            project_id,
            "task_plan",
            _project_document_title(project["name"], "task_plan"),
            _plain_markdown_html(plan_text),
            plan_text,
            hashlib.sha256(plan_text.encode("utf-8")).hexdigest(),
            auth.actor_id(),
        )
        await self._audit("确认项目任务", project["name"])
        return {**result, "artifactVersion": version}

    async def execute_project(self, body: dict[str, Any]) -> dict[str, Any]:
        project_id = _id(body.get("project_id") or body.get("projectId"), "project_id")
        project = await self.store.get_project(project_id)
        if not project:
            raise ApiProblem(404, "项目不存在。")
        can_retry = (
            project["phase"] == "executing"
            and project.get("executionStatus") == "failed"
        )
        if project["phase"] != "tasks_confirmed" and not can_retry:
            raise ApiProblem(409, "请先确认任务分解。")
        tasks = await self.store.materialize_project_task_plan(project_id)
        if not tasks:
            raise ApiProblem(409, "任务计划为空或项目未绑定专家。")
        await self.store.set_project_execution(
            project_id, "running", phase="executing"
        )
        if project_id not in _project_execution_tasks:
            _project_execution_tasks.add(project_id)
            asyncio.create_task(self._run_project_execution(project_id, tasks))
        await self._audit("启动项目自动执行", project["name"])
        return {
            "projectId": project_id,
            "status": "running",
            "taskCount": len(tasks),
        }

    async def complete_project(self, body: dict[str, Any]) -> dict[str, Any]:
        project_id = _id(body.get("project_id") or body.get("projectId"), "project_id")
        project = await self.store.get_project(project_id)
        if not project:
            raise ApiProblem(404, "项目不存在。")
        if not await self.store.complete_project(project_id):
            raise ApiProblem(409, "仍有任务没有确认成果版本，项目不能完成。")
        await self._audit("完成项目", project["name"])
        return {"projectId": project_id, "phase": "completed", "status": "已完成"}

    async def _resolve_generation_expert(
        self, preferred_ids: list[str]
    ) -> dict[str, Any] | None:
        """选择首个模型已配置 API Key 的启用专家。"""
        from admin import secret
        from admin.admin_model import RegistryModel

        registry = RegistryModel()
        experts = await self._list_experts()
        preferred_ids.extend(
            item["id"]
            for item in experts
            if "项目" in f"{item.get('name', '')} {item.get('role', '')}"
        )
        preferred_ids.extend(item["id"] for item in experts)
        checked: set[str] = set()
        for expert_id in preferred_ids:
            if not expert_id or expert_id in checked:
                continue
            checked.add(expert_id)
            candidate = next(
                (item for item in experts if item["id"] == expert_id), None
            )
            if not candidate or not candidate.get("enabled"):
                continue
            model_id = text(candidate.get("modelId") or candidate.get("model_id"))
            target = await registry.find_model_by_id(model_id) if model_id else None
            if not target:
                target = await registry.find_model_by_name(text(candidate.get("model")))
            if target and secret.decrypt(target.get("api_key_enc", "")):
                return candidate
        return None

    async def _ensure_project_generation_expert(
        self, project: dict[str, Any]
    ) -> dict[str, Any]:
        current_expert_id = text(project.get("expertId"))
        expert = await self._resolve_generation_expert([current_expert_id])
        if not expert:
            fail(
                "没有配置可用模型 API Key 的专家 Agent。",
                {"expert": "请先在管理后台为至少一个启用专家配置可用模型。"},
            )
        if current_expert_id == expert["id"]:
            return project
        updated = await self.store.update_project(
            project["id"], {"expertId": expert["id"]}
        )
        await self._audit(
            "自动绑定项目专家",
            f"{project['name']} · {expert['name']}",
        )
        return updated or project

    async def _create_project_from_chief_session(
        self, session: dict[str, Any]
    ) -> dict[str, Any]:
        """首次需求指令自动立项，并把当前总管会话原地转为项目会话。"""
        session_id = text(session.get("id"))
        messages = await self.store.list_messages(session_id)
        fixed_command = re.compile(
            r"^#(?:生成需求|需求沟通|需求文档|生成方案|方案沟通|方案文档|"
            r"生成计划|任务计划|计划清单|开始执行)#$"
        )
        conversation = [
            text(item.get("content")).strip()
            for item in messages
            if item.get("role") == "user"
            and text(item.get("content")).strip()
            and not fixed_command.fullmatch(text(item.get("content")).strip())
        ]
        title = text(session.get("title")).strip()
        if title in {"", "新会话"}:
            title = (
                conversation[0][:60]
                if conversation
                else f"未命名项目 {time.strftime('%m-%d %H:%M', time.localtime())}"
            )
        base_name = title[:180] or "未命名项目"
        project_name = base_name
        suffix = 2
        while await self.store.project_name_exists(project_name):
            project_name = f"{base_name} {suffix}"
            suffix += 1

        description = "\n".join(conversation[-8:])[:8000] or "从总管会话创建的项目"
        context = {
            "objective": (conversation[0] if conversation else base_name)[:2000],
            "scope": "",
            "constraints": [],
            "source": "chief_session",
        }
        runtime_settings = await self.store.get_settings()
        session_expert_id = text(session.get("expertId"))
        mapped_expert_id = text(
            (runtime_settings.get("domainExperts") or {}).get("project")
        )
        expert = await self._resolve_generation_expert(
            [session_expert_id, mapped_expert_id]
        )
        if not expert:
            fail(
                "没有配置可用模型 API Key 的专家 Agent。",
                {"expert": "请先在管理后台为至少一个启用专家配置可用模型。"},
            )

        project = await self.store.create_project(
            project_name,
            description,
            "进行中",
            context,
            expert["id"],
            session_id,
        )
        bound = await self.store.bind_session_project(
            session_id,
            project["id"],
            expert["id"],
            project_name,
        )
        if not bound:
            raise ApiProblem(404, "会话不存在。")
        await self._audit("从总管会话自动立项", project_name)
        return await self.store.get_project(project["id"]) or project

    async def project_workflow_command(self, body: dict[str, Any]) -> dict[str, Any]:
        """用完全匹配的固定会话内容推进项目流程。"""
        session_id = _id(
            body.get("session_id") or body.get("sessionId"), "session_id"
        )
        session = await self.store.get_session(session_id)
        if not session:
            raise ApiProblem(404, "会话不存在。")
        message = text(body.get("message") or body.get("command")).strip()
        aliases = {
            "#生成需求#": "requirements_draft",
            "#生成方案#": "solution_draft",
            "#生成计划#": "plan_list_draft",
            "#开始执行#": "execute",
            "#需求沟通#": "requirements_draft",
            "#需求文档#": "requirements_draft",
            "#方案沟通#": "solution_draft",
            "#方案文档#": "solution_draft",
            "#计划清单#": "plan_list_draft",
            "#任务计划#": "plan_list_draft",
        }
        command = aliases.get(message)
        if not command:
            fail(
                "固定指令不合法。",
                {
                    "message": (
                        "支持：#生成需求#、#生成方案#、#生成计划#、"
                        "#开始执行#。旧指令仍作为兼容别名。"
                    )
                },
            )

        project_id = text(session.get("projectId"))
        created_project = False
        if not project_id:
            if command != "requirements_draft":
                fail(
                    "当前会话尚未建立项目。",
                    {
                        "message": (
                            "请先发送 #生成需求# 或 #需求文档#，"
                            "系统会自动立项并生成需求草稿。"
                        )
                    },
                )
            project = await self._create_project_from_chief_session(session)
            project_id = project["id"]
            created_project = True
            session = await self.store.get_session(session_id) or session
        else:
            project = await self.store.get_project(project_id)
            if not project:
                raise ApiProblem(404, "项目不存在。")

        phase = text(project.get("phase"))
        execution_status = text(project.get("executionStatus"))
        allowed = {
            "requirements": {"requirements_draft"},
            "requirements_confirmed": {"solution_draft"},
            "solution": {"solution_draft"},
            "solution_confirmed": {"plan_list_draft"},
            "task_planning": {"plan_list_draft"},
            "tasks_confirmed": {"execute"},
            "executing": set(),
            "reviewing": set(),
            "completed": set(),
        }
        can_retry_execution = (
            command == "execute"
            and phase == "executing"
            and execution_status == "failed"
        )
        if command not in allowed.get(phase, {"status"}) and not can_retry_execution:
            fail(
                "当前项目阶段不能执行该指令。",
                {
                    "message": (
                        f"当前阶段为 {phase or '未知'}。"
                        "请按需求、方案、任务分解、执行、完成的顺序推进。"
                    )
                },
            )

        result: dict[str, Any] = {}
        if command == "requirements_draft":
            result = await self.generate_project_document(
                {"projectId": project_id, "stage": "requirements"}
            )
            answer = "需求文档草稿已生成，请在右侧“文档”中调整并确认需求 V1。"
        elif command == "solution_draft":
            result = await self.generate_project_document(
                {"projectId": project_id, "stage": "solution"}
            )
            answer = "方案文档草稿已生成，请在右侧“文档”中调整并确认方案 V1。"
        elif command == "plan_list_draft":
            result = await self.generate_project_task_plan({"projectId": project_id})
            answer = "计划清单草稿已生成，请在右侧“文档”中调整并确认计划 V1。"
        elif command == "execute":
            result = await self.execute_project({"projectId": project_id})
            answer = (
                f"执行已启动，共 {result['taskCount']} 个任务。"
                "正在进入项目工作台，全部任务生成草稿后会进入待确认。"
            )

        updated = await self.store.get_project(project_id)
        await self.store.add_message(
            session_id,
            "user",
            message,
            meta={"workflowCommand": command, "projectId": project_id},
        )
        assistant = await self.store.add_message(
            session_id,
            "assistant",
            answer,
            meta={
                "workflowCommand": command,
                "projectId": project_id,
                "phase": updated.get("phase") if updated else phase,
            },
        )
        await self._audit("项目流程固定指令", f"{project['name']} · {message}")
        return {
            "sessionId": session_id,
            "projectId": project_id,
            "command": message,
            "message": answer,
            "assistantMessageId": assistant["id"],
            "project": updated or result,
            "projectCreated": created_project,
        }

    async def _run_project_execution(
        self, project_id: str, tasks: list[dict[str, Any]]
    ) -> None:
        try:
            from admin.admin_controller import ExpertController, ExpertSessionModel

            expert = ExpertController()
            session_store = ExpertSessionModel()
            project = await self.store.get_project(project_id)
            if not project or not project.get("expertId"):
                raise RuntimeError("项目专家不存在")
            pending = {text(item.get("taskKey")): item for item in tasks}
            completed: set[str] = set()
            failed: dict[str, str] = {}
            while pending:
                ready = [
                    item
                    for item in pending.values()
                    if all(dep in completed for dep in item.get("dependsOn", []))
                ]
                if not ready:
                    break
                semaphore = asyncio.Semaphore(3)

                async def run_task(task: dict[str, Any]) -> None:
                    async with semaphore:
                        result = await expert.chat(
                            {
                                "id": project["expertId"],
                                "session_id": task["sessionId"],
                                "task_id": task["id"],
                                "message": (
                                    f"请执行任务「{task['title']}」。"
                                    "基于已确认的项目需求、方案和任务验收标准，"
                                    "直接产出可提交确认的成果草稿。"
                                ),
                            }
                        )
                        if result.get("requiresApproval"):
                            raise RuntimeError(
                                f"任务「{task['title']}」等待工具调用确认"
                            )
                        if not result.get("ok"):
                            raise RuntimeError(
                                result.get("message") or f"任务「{task['title']}」执行失败"
                            )
                        messages = await session_store.list_messages(task["sessionId"])
                        assistant = next(
                            (
                                item
                                for item in reversed(messages)
                                if item.get("role") == "assistant"
                            ),
                            None,
                        )
                        if not assistant:
                            raise RuntimeError(f"任务「{task['title']}」没有生成成果")
                        deliverable = await self.store.ensure_deliverable(
                            task["id"], project_id, task["title"]
                        )
                        await self.store.save_deliverable_draft(
                            deliverable["id"],
                            _plain_markdown_html(text(assistant["content"])),
                            text(assistant["content"]),
                            source_message_id=assistant["id"],
                            source_session_id=task["sessionId"],
                            source_run_id=text(assistant.get("runId")) or None,
                            source_expert_id=project["expertId"],
                        )
                        await self.store.set_task_phase(task["id"], "adjusting")

                results = await asyncio.gather(
                    *(run_task(task) for task in ready), return_exceptions=True
                )
                for task, result in zip(ready, results, strict=True):
                    task_key = text(task.get("taskKey"))
                    pending.pop(task_key, None)
                    if isinstance(result, Exception):
                        failed[task_key] = (
                            f"{task['title']}：{result.__class__.__name__}: {result}"
                        )
                        await self.store.mark_task_execution_failed(task["id"])
                    else:
                        completed.add(task_key)
            blocked = [text(item.get("title")) for item in pending.values()]
            if failed or blocked:
                problems = list(failed.values())
                if blocked:
                    problems.append(f"依赖阻塞：{'、'.join(blocked)}")
                await self.store.set_project_execution(
                    project_id,
                    "failed",
                    error="；".join(problems),
                    phase="executing",
                )
                return
            await self.store.set_project_execution(
                project_id, "completed", phase="reviewing"
            )
        except Exception as exc:  # noqa: BLE001 - 后台执行需写回可读错误
            await self.store.set_project_execution(
                project_id,
                "failed",
                error=f"{exc.__class__.__name__}: {exc}",
                phase="executing",
            )
        finally:
            _project_execution_tasks.discard(project_id)

    async def create_milestone(self, body: dict[str, Any]) -> dict[str, Any]:
        project_id = _id(body.get("project_id") or body.get("projectId"), "project_id")
        if not await self.store.get_project(project_id):
            raise ApiProblem(404, "项目不存在。")
        title = text(body.get("title") or body.get("name"))
        if not title:
            fail("请输入任务包名称。", {"title": "任务包名称不能为空。"})
        milestone = await self.store.create_milestone(
            project_id,
            title[:200],
            text(body.get("status")) or "未开始",
            text(body.get("starts_at") or body.get("startsAt")) or None,
            text(body.get("due_at") or body.get("dueAt")) or None,
        )
        await self._audit("新建任务包", milestone["title"])
        return milestone

    async def update_milestone(self, body: dict[str, Any]) -> dict[str, Any]:
        milestone_id = _id(
            body.get("milestone_id") or body.get("milestoneId"), "milestone_id"
        )
        fields: dict[str, Any] = {}
        for source, target in (("title", "title"), ("name", "title"), ("status", "status")):
            if source in body:
                fields[target] = text(body.get(source))
        if "startsAt" in body or "starts_at" in body:
            fields["startsAt"] = text(body.get("startsAt") or body.get("starts_at")) or None
        if "dueAt" in body or "due_at" in body:
            fields["dueAt"] = text(body.get("dueAt") or body.get("due_at")) or None
        if fields.get("title") == "":
            fail("任务包名称不能为空。", {"title": "任务包名称不能为空。"})
        milestone = await self.store.update_milestone(milestone_id, fields)
        if not milestone:
            raise ApiProblem(404, "任务包不存在。")
        await self._audit("修改任务包", milestone["title"])
        return milestone

    async def delete_milestone(self, body: dict[str, Any]) -> None:
        milestone_id = _id(
            body.get("milestone_id") or body.get("milestoneId"), "milestone_id"
        )
        if not await self.store.delete_milestone(milestone_id):
            raise ApiProblem(404, "任务包不存在。")
        await self._audit("删除任务包", milestone_id)

    async def create_task(self, body: dict[str, Any]) -> dict[str, Any]:
        project_id = _id(body.get("project_id") or body.get("projectId"), "project_id")
        milestone_id = _id(
            body.get("milestone_id") or body.get("milestoneId"), "milestone_id"
        )
        project = await self.store.get_project(project_id)
        if not project:
            raise ApiProblem(404, "项目不存在。")
        if not text(project.get("expertId")):
            raise ApiProblem(409, "请先为项目绑定专家 Agent，再创建任务会话。")
        await self._resolve_expert(
            "project",
            requested_expert_id=text(project["expertId"]),
        )
        if not await self.store.milestone_belongs_to_project(milestone_id, project_id):
            raise ApiProblem(404, "任务包不存在或不属于当前项目。")
        title = text(body.get("title") or body.get("name"))
        if not title:
            fail("请输入任务名称。", {"title": "任务名称不能为空。"})
        task = await self.store.create_task(
            project_id,
            milestone_id,
            title[:200],
            text(body.get("priority")) or "P2",
            text(body.get("status")) or "未开始",
            text(body.get("due_at") or body.get("dueAt")) or None,
        )
        await self._audit("新建任务", task["title"])
        return task

    async def update_task(self, body: dict[str, Any]) -> dict[str, Any]:
        task_id = _id(body.get("task_id") or body.get("taskId"), "task_id")
        fields: dict[str, Any] = {}
        for source, target in (
            ("title", "title"),
            ("name", "title"),
            ("priority", "priority"),
            ("status", "status"),
        ):
            if source in body:
                fields[target] = text(body.get(source))
        if "dueAt" in body or "due_at" in body:
            fields["dueAt"] = text(body.get("dueAt") or body.get("due_at")) or None
        if fields.get("title") == "":
            fail("任务名称不能为空。", {"title": "任务名称不能为空。"})
        if fields.get("status") == "已完成":
            fail(
                "任务只能通过成果确认流程完成。",
                {"status": "请先确认至少一个成果版本，再点击完成任务。"},
            )
        task = await self.store.update_task(task_id, fields)
        if not task:
            raise ApiProblem(404, "任务不存在。")
        await self._audit("修改任务", task["title"])
        return task

    async def delete_task(self, body: dict[str, Any]) -> None:
        task_id = _id(body.get("task_id") or body.get("taskId"), "task_id")
        if not await self.store.delete_task(task_id):
            raise ApiProblem(404, "任务不存在。")
        await self._audit("删除任务", task_id)

    async def confirm_task_spec(self, body: dict[str, Any]) -> dict[str, Any]:
        task_id = _id(body.get("task_id") or body.get("taskId"), "task_id")
        task = await self.store.get_task_delivery_context(task_id)
        if not task:
            raise ApiProblem(404, "任务不存在。")
        if task["phase"] != "communicating":
            raise ApiProblem(409, "当前任务已经确认需求，不能重复确认。")
        objective = text(body.get("objective"))
        scope = text(body.get("scope"))
        acceptance = text(body.get("acceptance_criteria") or body.get("acceptanceCriteria"))
        if not objective:
            fail("请输入任务目标。", {"objective": "任务目标不能为空。"})
        result = await self.store.confirm_task_spec(
            task_id,
            {"objective": objective, "scope": scope, "acceptanceCriteria": acceptance},
        )
        await self._audit("确认任务需求", task["title"])
        return result or {}

    async def start_task_execution(self, body: dict[str, Any]) -> dict[str, Any]:
        task_id = _id(body.get("task_id") or body.get("taskId"), "task_id")
        task = await self.store.get_task_delivery_context(task_id)
        if not task:
            raise ApiProblem(404, "任务不存在。")
        if task["phase"] != "spec_confirmed":
            raise ApiProblem(409, "任务需求尚未确认。")
        await self.store.set_task_phase(task_id, "executing")
        await self._audit("任务开始执行", task["title"])
        return {"taskId": task_id, "phase": "executing"}

    async def set_deliverable_draft(self, body: dict[str, Any]) -> dict[str, Any]:
        task_id = _id(body.get("task_id") or body.get("taskId"), "task_id")
        message_id = _id(
            body.get("message_id") or body.get("messageId"), "message_id"
        )
        task = await self.store.get_task_delivery_context(task_id)
        if not task:
            raise ApiProblem(404, "任务不存在。")
        if task["phase"] not in {"executing", "adjusting", "confirmed"}:
            raise ApiProblem(409, "请先确认需求并开始执行。")
        message = await self.store.get_expert_message_for_task(task_id, message_id)
        if not message or message["role"] != "assistant":
            raise ApiProblem(404, "专家回复不存在或不属于当前任务。")
        content_text = text(body.get("content_text") or body.get("contentText")) or text(
            message["content"]
        )
        content_html = text(body.get("content_html") or body.get("contentHtml"))
        if not content_html:
            escaped = html_lib.escape(content_text).replace("\n", "<br>")
            content_html = f"<p>{escaped}</p>"
        content_html = re.sub(
            r"<(script|style)[^>]*>.*?</\1>",
            "",
            content_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        content_html = re.sub(
            r"\s+on[a-z]+\s*=\s*(['\"]).*?\1",
            "",
            content_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        deliverable = await self.store.ensure_deliverable(
            task_id, task["projectId"], task["title"]
        )
        draft = await self.store.save_deliverable_draft(
            deliverable["id"],
            content_html,
            content_text,
            source_message_id=message["id"],
            source_session_id=message["sessionId"],
            source_run_id=message.get("runId"),
            source_expert_id=message.get("expertId"),
        )
        await self.store.set_task_phase(task_id, "adjusting")
        await self._audit("专家回复设为成果草稿", task["title"])
        return draft or {}

    async def save_deliverable_draft(self, body: dict[str, Any]) -> dict[str, Any]:
        deliverable_id = _id(
            body.get("deliverable_id") or body.get("deliverableId"),
            "deliverable_id",
        )
        task_id = _id(body.get("task_id") or body.get("taskId"), "task_id")
        task = await self.store.get_task_delivery_context(task_id)
        if not task or task.get("deliverableId") != deliverable_id:
            raise ApiProblem(404, "成果物不存在或不属于当前任务。")
        content_text = text(body.get("content_text") or body.get("contentText"))
        content_html = text(body.get("content_html") or body.get("contentHtml"))
        if not content_text and content_html:
            content_text = html_lib.unescape(re.sub(r"<[^>]+>", " ", content_html))
            content_text = re.sub(r"\s+", " ", content_text).strip()
        if not content_text:
            fail("成果物内容不能为空。", {"content": "成果物内容不能为空。"})
        draft = await self.store.save_deliverable_draft(
            deliverable_id, content_html, content_text
        )
        await self._audit("保存成果草稿", task["title"])
        return draft or {}

    async def confirm_deliverable(self, body: dict[str, Any]) -> dict[str, Any]:
        deliverable_id = _id(
            body.get("deliverable_id") or body.get("deliverableId"),
            "deliverable_id",
        )
        task_id = _id(body.get("task_id") or body.get("taskId"), "task_id")
        task = await self.store.get_task_delivery_context(task_id)
        if not task or task.get("deliverableId") != deliverable_id:
            raise ApiProblem(404, "成果物不存在或不属于当前任务。")
        if task["phase"] not in {"executing", "adjusting"}:
            raise ApiProblem(409, "当前阶段不能确认版本。")
        draft_text = text(task.get("draftText"))
        if not draft_text:
            fail("成果物内容不能为空。", {"content": "请先生成或保存成果草稿。"})
        version = await self.store.confirm_deliverable_version(
            deliverable_id,
            hashlib.sha256(draft_text.encode("utf-8")).hexdigest(),
            auth.actor_id(),
        )
        if not version:
            fail("成果物版本确认失败。", {"content": "请检查成果草稿。"})
        await self._audit(
            "确认成果版本",
            f"{task['title']} · V{version['versionNo']}",
        )
        return version

    async def start_deliverable_adjustment(
        self, body: dict[str, Any]
    ) -> dict[str, Any]:
        deliverable_id = _id(
            body.get("deliverable_id") or body.get("deliverableId"),
            "deliverable_id",
        )
        result = await self.store.start_deliverable_adjustment(deliverable_id)
        if not result:
            raise ApiProblem(404, "成果物不存在或没有可调整版本。")
        await self._audit("开始调整成果", f"V{result['latestVersionNo']}")
        return result

    async def complete_task_delivery(self, body: dict[str, Any]) -> dict[str, Any]:
        task_id = _id(body.get("task_id") or body.get("taskId"), "task_id")
        if not await self.store.complete_task_delivery(task_id):
            raise ApiProblem(409, "至少需要确认一个成果版本后才能完成。")
        await self._audit("完成任务", task_id)
        return {"taskId": task_id, "phase": "completed"}

    async def add_task_attachment(self, body: dict[str, Any]) -> dict[str, Any]:
        task_id = _id(body.get("task_id") or body.get("taskId"), "task_id")
        file = body.get("file")
        if not isinstance(file, dict) or not text(file.get("uuid")):
            fail("附件信息不完整。", {"file": "请先上传附件。"})
        kind = text(body.get("kind")) or "输入"
        if kind not in {"输入", "产出"}:
            fail("附件类型不合法。", {"kind": "仅支持输入或产出。"})
        attachment = await self.store.add_task_attachment(task_id, file, kind)
        if not attachment:
            raise ApiProblem(404, "任务不存在。")
        await self._audit("添加任务附件", attachment["name"])
        return attachment

    async def delete_task_attachment(self, body: dict[str, Any]) -> None:
        attachment_id = _id(
            body.get("attachment_id") or body.get("attachmentId"), "attachment_id"
        )
        if not await self.store.delete_task_attachment(attachment_id):
            raise ApiProblem(404, "附件不存在。")
        await self._audit("删除任务附件", attachment_id)

    async def get_session(self, body: dict[str, Any]) -> dict[str, Any]:
        session_id = _id(body.get("session_id") or body.get("sessionId"), "session_id")
        session = await self.store.get_session(session_id)
        if not session:
            raise ApiProblem(404, "会话不存在。")
        return {
            **session,
            "messages": await self.store.list_messages(session_id),
            "runs": await self.store.list_runs(session_id),
            "documents": await self.store.list_documents(
                session_id, session.get("projectId")
            ),
        }

    async def delete_session(self, body: dict[str, Any]) -> None:
        session_id = _id(body.get("session_id") or body.get("sessionId"), "session_id")
        session = await self.store.get_session(session_id)
        if not session:
            raise ApiProblem(404, "会话不存在。")
        if not await self.store.delete_session(session_id):
            raise ApiProblem(404, "会话不存在。")
        await self._audit("删除总管会话", session["title"])

    async def archive_session(self, body: dict[str, Any]) -> None:
        session_id = _id(body.get("session_id") or body.get("sessionId"), "session_id")
        session = await self.store.get_session(session_id)
        if not session:
            raise ApiProblem(404, "会话不存在。")
        if not await self.store.archive_session(session_id):
            raise ApiProblem(404, "会话不存在。")
        await self._audit("归档总管会话", session["title"])

    async def restore_session(self, body: dict[str, Any]) -> None:
        session_id = _id(body.get("session_id") or body.get("sessionId"), "session_id")
        session = await self.store.get_session(session_id)
        if not session:
            raise ApiProblem(404, "会话不存在。")
        if not await self.store.restore_session(session_id):
            raise ApiProblem(404, "会话不存在。")
        await self._audit("恢复归档会话", session["title"])

    async def list_harnesses(self, body: dict[str, Any]) -> dict[str, Any]:
        domain = text(body.get("domain"))
        rows = await self.store.list_harnesses(domain) if hasattr(self.store, "list_harnesses") else []
        return {"items": rows}

    async def get_settings(self) -> dict[str, Any]:
        return await self.store.get_settings()

    async def update_settings(self, body: dict[str, Any]) -> dict[str, Any]:
        current = await self.store.get_settings()
        mode = text(body.get("recursion_mode") or body.get("recursionMode")) or current[
            "recursionMode"
        ]
        if mode not in {"sequential", "parallel"}:
            fail("递归模式不合法。", {"recursionMode": "仅支持顺序或并行递归。"})
        recursion_max = min(
            4,
            max(
                1,
                to_int(
                    body.get("recursion_max") or body.get("recursionMax"),
                    current["recursionMax"],
                ),
            ),
        )
        recursion_k = min(
            recursion_max,
            max(
                1,
                to_int(
                    body.get("recursion_k") or body.get("recursionK"),
                    current["recursionK"],
                ),
            ),
        )
        regression_cases = min(
            10,
            max(
                0,
                to_int(
                    body.get("regression_cases") or body.get("regressionCases"),
                    current["regressionCases"],
                ),
            ),
        )
        try:
            min_score = min(
                100.0,
                max(
                    0.0,
                    float(
                        body.get("auto_adopt_min_score")
                        or body.get("autoAdoptMinScore")
                        or current["autoAdoptMinScore"]
                    ),
                ),
            )
            min_gain = min(
                100.0,
                max(
                    0.0,
                    float(
                        body.get("auto_adopt_min_gain")
                        or body.get("autoAdoptMinGain")
                        or current["autoAdoptMinGain"]
                    ),
                ),
            )
        except (TypeError, ValueError):
            fail("自动采纳阈值必须是数字。", {"threshold": "请输入合法数字。"})
        raw_domains = body.get("domain_experts") or body.get("domainExperts")
        domain_experts = raw_domains if isinstance(raw_domains, dict) else current["domainExperts"]
        allowed_domains = {
            "customer",
            "project",
            "content",
            "operations",
            "programming",
            "general",
        }
        expert_ids = {
            item["id"] for item in await self._list_experts() if item.get("enabled")
        }
        cleaned_domains: dict[str, str] = {}
        for domain, expert_id in domain_experts.items():
            if domain not in allowed_domains:
                continue
            expert_id = text(expert_id)
            if expert_id and expert_id not in expert_ids:
                fail(
                    "总管专家映射无效。",
                    {"domainExperts": f"{domain} 绑定的专家不存在。"},
                )
            cleaned_domains[domain] = expert_id
        payload = {
            "enabled": to_bool(
                body.get("enabled") if "enabled" in body else current["enabled"]
            ),
            "recursionMode": mode,
            "recursionK": recursion_k,
            "recursionMax": recursion_max,
            "regressionEnabled": to_bool(
                body.get("regression_enabled")
                if "regression_enabled" in body
                else body.get("regressionEnabled", current["regressionEnabled"])
            ),
            "regressionCases": regression_cases,
            "autoAdoptMinScore": min_score,
            "autoAdoptMinGain": min_gain,
            "domainExperts": cleaned_domains,
        }
        result = await self.store.save_settings(payload, auth.actor_id())
        await self._audit(
            "修改总管设置",
            f"{mode} · K={recursion_k}/{recursion_max} · 回归 {regression_cases}",
        )
        return result

    async def get_call_settings(self) -> dict[str, Any]:
        return await self.store.get_call_settings()

    async def update_call_settings(self, body: dict[str, Any]) -> dict[str, Any]:
        current = await self.store.get_call_settings()
        push_to_talk_key = (
            text(body.get("push_to_talk_key") or body.get("pushToTalkKey"))
            or current["pushToTalkKey"]
        )
        push_to_talk_key = _normalize_push_to_talk_key(push_to_talk_key)
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,29}", push_to_talk_key):
            fail(
                "通话快捷键不合法。",
                {
                    "pushToTalkKey": "请使用键盘事件 code，例如 Escape、Space、Fn、KeyV 或 F8。"
                },
            )

        def checked_http_url(value: Any, field: str, label: str) -> str:
            url = text(value).strip()
            parsed = urlsplit(url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                fail(f"{label}地址不合法。", {field: "请输入完整的 HTTP(S) 地址。"})
            return url

        result = await self.store.save_call_settings(
            {
                "pushToTalkKey": push_to_talk_key,
                "asrUrl": checked_http_url(
                    body.get("asr_url") or body.get("asrUrl") or current["asrUrl"],
                    "asrUrl",
                    "ASR ",
                ),
                "ttsUrl": checked_http_url(
                    body.get("tts_url") or body.get("ttsUrl") or current["ttsUrl"],
                    "ttsUrl",
                    "TTS ",
                ),
            },
            auth.actor_id(),
        )
        await self._audit(
            "修改通话设置",
            f"{result['pushToTalkKey']} · ASR/TTS",
        )
        return result

    async def send_message(self, body: dict[str, Any]) -> dict[str, Any]:
        message = text(body.get("message"))
        attachments = body.get("attachments")
        attachments = attachments if isinstance(attachments, list) else []
        if not message and not attachments:
            fail("请输入消息或添加附件。", {"message": "消息不能为空。"})

        session_id = text(body.get("session_id") or body.get("sessionId"))
        if session_id:
            session_id = _id(session_id, "session_id")
            session = await self.store.get_session(session_id)
            if not session:
                raise ApiProblem(404, "会话不存在。")
        else:
            project_id = text(body.get("project_id") or body.get("projectId"))
            project = (
                await self.store.get_project(_id(project_id, "project_id"))
                if project_id
                else None
            )
            session = await self.store.create_session(
                text(body.get("title"))
                or (project["name"] if project else "")
                or message[:40]
                or "附件会话",
                "project" if project else "general",
                "T3",
                project["id"] if project else None,
                project.get("expertId") if project else None,
            )
            session_id = session["id"]

        domain = classify_domain(message)
        project = None
        if session.get("projectId"):
            project = await self.store.get_project(session["projectId"])
            if project:
                domain = "project"
        risk_tier = classify_risk(message)
        runtime_settings = await self.store.get_settings()
        if not runtime_settings["enabled"]:
            raise ApiProblem(503, "总管当前已在管理后台停用。")
        recursion_mode = (
            text(body.get("recursion_mode") or body.get("recursionMode"))
            or runtime_settings["recursionMode"]
        )
        if recursion_mode not in {"sequential", "parallel"}:
            recursion_mode = "sequential"
        recursion_k = min(
            max(
                1,
                to_int(
                    body.get("recursion_k") or body.get("recursionK"),
                    runtime_settings["recursionK"],
                ),
            ),
            max(1, runtime_settings["recursionMax"]),
        )
        await self.store.update_session(session_id, domain, risk_tier)
        prior_messages = await self.store.list_messages(session_id)

        session_expert_id = text(session.get("expertId"))
        expert_id = session_expert_id or text(
            body.get("expert_id") or body.get("expertId")
        )
        mapped_expert_id = text(
            session_expert_id
            or (runtime_settings.get("domainExperts") or {}).get(domain)
        )
        expert = await self._resolve_expert(
            domain,
            session_expert_id=session_expert_id,
            requested_expert_id="" if session_expert_id else expert_id,
            mapped_expert_id="" if session_expert_id or expert_id else mapped_expert_id,
        )
        selected = await select_model(expert)
        if not selected:
            raise ApiProblem(503, "没有可用模型，请先在模型管理中配置 API Key。")
        model, api_key = selected
        mcp_items, skill_items = await selected_resources(expert)
        attachment_summary, images = await build_attachment_context(attachments)

        attachment_meta = [
            {
                "uuid": text(item.get("uuid")),
                "name": text(item.get("name")),
                "mimeType": text(item.get("mime_type") or item.get("mimeType")),
            }
            for item in attachments
            if isinstance(item, dict)
        ]
        user_message = await self.store.add_message(
            session_id,
            "user",
            message or "请查看附件",
            meta={
                "domain": domain,
                "riskTier": risk_tier,
                "expertName": expert.get("name") if expert else "",
                "projectId": project.get("id") if project else None,
                "projectName": project.get("name") if project else None,
            },
            attachments=attachment_meta,
        )

        baseline = await self.store.active_harness(domain)
        if not baseline:
            base_components = build_base_harness(domain, expert, skill_items, mcp_items)
            baseline = await self.store.create_harness(
                name=f"{domain}-base",
                domain=domain,
                components=base_components,
                hash_value=content_hash(base_components),
                parent_id=None,
                status="active",
                evidence={"source": "initial_base"},
                created_by=auth.actor_id(),
            )

        run = await self.store.create_run(
            session_id=session_id,
            user_message_id=user_message["id"],
            domain=domain,
            risk_tier=risk_tier,
            baseline_harness_id=baseline["id"],
            expert_id=expert.get("id") if expert else None,
            model_name=model["name"],
            recursion_mode=recursion_mode,
            recursion_k=recursion_k,
        )
        run_id = run["id"]
        await self.store.add_event(
            run_id,
            "intent",
            "completed",
            f"识别为{domain}域，风险等级 {risk_tier}",
            {"domain": domain, "riskTier": risk_tier},
        )
        await self.store.add_event(
            run_id,
            "baseline",
            "completed",
            f"使用 Harness v{baseline['version']}",
            {"harnessId": baseline["id"], "version": baseline["version"]},
        )
        web_context = await self._web_search_context(
            run_id,
            message,
            model,
            api_key,
        )
        web_fetch = await self._web_fetch_context(
            run_id,
            message,
            model,
            api_key,
        )
        if web_fetch:
            web_context = "\n\n".join(
                item for item in (web_context, web_fetch) if item
            )
        history = [
            {"role": item["role"], "content": item["content"]}
            for item in prior_messages[-12:]
        ]
        user_content = build_user_content(
            message or "请分析附件", attachment_summary, images, text(model["endpoint"])
        )
        document_context = build_document_context(
            await self.store.list_attached_documents(session_id)
        )
        user_content = _append_user_context(user_content, document_context)
        user_content = _append_user_context(user_content, web_context)
        reflections = await self.store.recent_reflections(domain)
        reflection_text = "\n".join(
            f"- {json_value(item.get('lessons'), {})}" for item in reflections
        )
        project_prompt = ""
        if project:
            project_context = json_value(project.get("context"), {}) or {}
            project_prompt = (
                f"\n当前项目：{project['name']}。\n"
                f"项目目标：{project_context.get('objective', '')}\n"
                f"项目范围：{project_context.get('scope', '')}\n"
                "沟通必须严格限定在当前项目背景下。"
                "不要讨论、引用或假设其他项目的信息；"
                "信息不足时明确说明需要当前项目的哪些补充材料。"
            )
        quota = QuotaModel()
        total_input_tokens = 0
        total_output_tokens = 0
        total_cost = 0.0

        async def probe_candidate(
            variant: dict[str, Any],
            *,
            parent_harness_id: str,
            parent_components: dict[str, Any],
            step: int,
            group: int = 1,
        ) -> dict[str, Any]:
            components = variant["components"]
            system_prompt = render_system_prompt(components)
            if project_prompt:
                system_prompt += project_prompt
            if reflection_text:
                system_prompt += f"\n已验证的领域经验：\n{reflection_text}"
            result = await chat(
                text(model["endpoint"]),
                api_key,
                text(model.get("model_key")),
                system_prompt,
                [*history, {"role": "user", "content": user_content}],
            )
            assessment = score_answer(
                message or "附件分析",
                text(result.get("content")),
                int(result.get("latencyMs", 0)),
            )
            input_tokens = int(result.get("inputTokens", 0))
            output_tokens = int(result.get("outputTokens", 0))
            estimated_cost = await quota.consume_usage(
                model["name"], input_tokens + output_tokens
            )
            harness = await self.store.create_harness(
                name=(
                    f"{domain}-{variant['scope']}-s{step}-g{group}-run-{run_id[:8]}"
                ),
                domain=domain,
                components=components,
                hash_value=content_hash(components),
                parent_id=parent_harness_id,
                status="proposed",
                evidence={
                    "runId": run_id,
                    "probeScore": assessment,
                    "model": model["name"],
                    "step": step,
                    "group": group,
                    "usage": {
                        "inputTokens": input_tokens,
                        "outputTokens": output_tokens,
                        "estimatedCost": estimated_cost,
                    },
                },
                created_by=auth.actor_id(),
            )
            candidate = await self.store.add_candidate(
                run_id=run_id,
                label=(
                    variant["label"]
                    if recursion_k == 1 and recursion_mode == "sequential"
                    else (
                        f"{variant['label']} · 第 {group} 组"
                        if recursion_mode == "parallel"
                        else f"{variant['label']} · 第 {step} 步"
                    )
                ),
                scope=variant["scope"],
                step=step,
                harness=components,
                harness_id=harness["id"],
                answer=text(result.get("content")),
                score=float(assessment["score"]),
                latency_ms=int(result.get("latencyMs", 0)),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                estimated_cost=estimated_cost,
                trace={
                    "ok": bool(result.get("ok")),
                    "message": result.get("message", ""),
                    "assessment": assessment,
                    "diff": component_diff(parent_components, components),
                    "usage": {
                        "inputTokens": input_tokens,
                        "outputTokens": output_tokens,
                        "estimatedCost": estimated_cost,
                    },
                    "step": step,
                    "group": group,
                },
            )
            return {
                **candidate,
                "label": variant["label"],
                "scope": variant["scope"],
                "harness": components,
                "harnessId": harness["id"],
                "answer": text(result.get("content")),
                "score": float(assessment["score"]),
                "latencyMs": int(result.get("latencyMs", 0)),
                "inputTokens": input_tokens,
                "outputTokens": output_tokens,
                "estimatedCost": estimated_cost,
                "trace": {
                    "ok": bool(result.get("ok")),
                    "message": result.get("message", ""),
                    "assessment": assessment,
                    "diff": component_diff(parent_components, components),
                    "usage": {
                        "inputTokens": input_tokens,
                        "outputTokens": output_tokens,
                        "estimatedCost": estimated_cost,
                    },
                    "step": step,
                    "group": group,
                },
            }

        candidates: list[dict[str, Any]] = []
        base_components = baseline["components"]
        parent_harness_id = baseline["id"]
        selected_candidate = None
        if recursion_mode == "parallel":
            await self.store.add_event(
                run_id,
                "propose",
                "completed",
                f"并行生成 {recursion_k * 2} 个候选 Harness",
                {"mode": recursion_mode, "k": recursion_k},
            )
            tasks = []
            for group in range(1, recursion_k + 1):
                for variant in build_variants(base_components, domain):
                    tasks.append(
                        probe_candidate(
                            variant,
                            parent_harness_id=baseline["id"],
                            parent_components=baseline["components"],
                            step=1,
                            group=group,
                        )
                    )
            candidates = await asyncio.gather(*tasks)
            valid = [item for item in candidates if item["trace"].get("ok") and item["answer"]]
            if valid:
                selected_candidate = choose_candidate(valid)
        else:
            for step in range(1, recursion_k + 1):
                variants = build_variants(base_components, domain)
                await self.store.add_event(
                    run_id,
                    "propose",
                    "completed",
                    f"第 {step} 步生成 {len(variants)} 个候选 Harness",
                    {"mode": recursion_mode, "step": step, "k": recursion_k},
                )
                step_candidates = await asyncio.gather(
                    *(
                        probe_candidate(
                            item,
                            parent_harness_id=parent_harness_id,
                            parent_components=base_components,
                            step=step,
                        )
                        for item in variants
                    )
                )
                candidates.extend(step_candidates)
                await self.store.add_event(
                    run_id,
                    "probe",
                    "completed",
                    f"第 {step} 步候选执行完成",
                    {
                        "step": step,
                        "candidates": [
                            {
                                "label": item["label"],
                                "score": item["score"],
                                "latencyMs": item["latencyMs"],
                            }
                            for item in step_candidates
                        ],
                    },
                )
                valid_step = [
                    item
                    for item in step_candidates
                    if item["trace"].get("ok") and item["answer"]
                ]
                if not valid_step:
                    break
                selected_candidate = choose_candidate(valid_step)
                base_components = selected_candidate["harness"]
                parent_harness_id = selected_candidate["harnessId"]

        total_input_tokens = sum(item.get("inputTokens", 0) for item in candidates)
        total_output_tokens = sum(item.get("outputTokens", 0) for item in candidates)
        total_cost = round(sum(item.get("estimatedCost", 0) for item in candidates), 6)
        valid = [item for item in candidates if item["trace"].get("ok") and item["answer"]]
        if not valid:
            await self.store.update_run(
                run_id,
                {
                    "status": "failed",
                    "error": "全部候选执行失败",
                    "requires_approval": False,
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                    "estimated_cost": total_cost,
                },
            )
            await self.store.add_event(run_id, "compose", "failed", "没有可用候选")
            return await self.get_run({"run_id": run_id})

        selected_candidate = selected_candidate or choose_candidate(valid)
        regression_passed, regression_detail, regression_tokens, regression_cost = (
            await self._run_regression(
                run_id,
                domain,
                selected_candidate,
                model,
                api_key,
                quota,
                runtime_settings,
            )
        )
        total_input_tokens += regression_tokens[0]
        total_output_tokens += regression_tokens[1]
        total_cost = round(total_cost + regression_cost, 6)
        reflection_stats = await self.store.reflection_stats(domain)
        score = float(selected_candidate["score"])
        enough_quality = score >= runtime_settings["autoAdoptMinScore"]
        if reflection_stats["count"] >= 2:
            required_score = reflection_stats["averageScore"] * (
                1 + runtime_settings["autoAdoptMinGain"] / 100
            )
            improved_enough = score >= required_score
        else:
            required_score = 0.0
            improved_enough = True
        risk_allows_auto = risk_tier in {"T3", "T4"}
        requires_approval = not (
            risk_allows_auto and regression_passed and enough_quality and improved_enough
        )
        reasons: list[str] = []
        if not risk_allows_auto:
            reasons.append(f"{risk_tier} 任务需要人工确认")
        if not regression_passed:
            reasons.append("历史回归未通过")
        if not enough_quality:
            reasons.append(
                f"得分 {score:.2f} 低于自动采纳阈值 {runtime_settings['autoAdoptMinScore']}"
            )
        if not improved_enough:
            reasons.append(
                f"得分未达到历史均值的 {100 + runtime_settings['autoAdoptMinGain']}% "
                f"（要求 {required_score:.2f}）"
            )
        auto_reason = "满足自动采纳条件" if not requires_approval else "；".join(reasons)
        status = "awaiting_approval" if requires_approval else "completed"
        await self.store.add_event(
            run_id,
            "compose",
            "completed",
            f"采用「{selected_candidate['label']}」，得分 {selected_candidate['score']}",
            {
                "selectedCandidateId": selected_candidate["id"],
                "requiresApproval": requires_approval,
                "regression": regression_detail,
                "reason": auto_reason,
            },
        )
        update_fields: dict[str, Any] = {
            "status": status,
            "selected_harness_id": selected_candidate["harnessId"],
            "answer": selected_candidate["answer"],
            "requires_approval": requires_approval,
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
            "estimated_cost": total_cost,
            "regression_passed": regression_passed,
            "auto_adopt_reason": auto_reason,
        }
        if not requires_approval:
            await self.store.activate_harness(selected_candidate["harnessId"], domain)
            assistant = await self.store.add_message(
                session_id,
                "assistant",
                selected_candidate["answer"],
                run_id=run_id,
                meta={
                    "runId": run_id,
                    "domain": domain,
                    "riskTier": risk_tier,
                    "harnessId": selected_candidate["harnessId"],
                    "score": selected_candidate["score"],
                },
            )
            update_fields["assistant_message_id"] = assistant["id"]
            update_fields["approved_by"] = auth.actor_id()
            await self._record_reflection(domain, selected_candidate, run_id)
            await self._add_regression_case(run_id, domain, selected_candidate)
            await self.store.add_event(run_id, "complete", "completed", "自动采纳并生成回复")
        else:
            await self.store.add_event(
                run_id,
                "approval",
                "waiting",
                f"{risk_tier} 任务等待人工确认：{auto_reason}",
            )
        await self.store.update_run(run_id, update_fields)
        await self._audit("总管任务", f"{domain} · {risk_tier} · {run_id}")
        return await self.get_run({"run_id": run_id})

    async def _list_experts(self) -> list[dict[str, Any]]:
        from admin.admin_model import ExpertModel

        return await ExpertModel().list()

    async def _resolve_expert(
        self,
        domain: str,
        *,
        session_expert_id: str = "",
        requested_expert_id: str = "",
        mapped_expert_id: str = "",
    ) -> dict[str, Any] | None:
        experts = await self._list_experts()

        def find(expert_id: str) -> dict[str, Any] | None:
            return next((item for item in experts if item["id"] == expert_id), None)

        if session_expert_id:
            expert = find(session_expert_id)
            if not expert or not expert.get("enabled"):
                raise ApiProblem(
                    409,
                    "会话绑定的专家已被删除或停用，请重新绑定专家。",
                )
            return expert
        if requested_expert_id:
            expert = find(requested_expert_id)
            if not expert:
                raise ApiProblem(404, "所选专家不存在。")
            if not expert.get("enabled"):
                raise ApiProblem(409, "所选专家已停用，请使用启用中的专家。")
            return expert
        if mapped_expert_id:
            expert = find(mapped_expert_id)
            if not expert or not expert.get("enabled"):
                raise ApiProblem(
                    409,
                    f"业务域 {domain} 绑定的专家已停用或不存在，请在总管设置中重新选择。",
                )
            return expert
        return await select_expert(domain)

    async def _run_regression(
        self,
        run_id: str,
        domain: str,
        candidate: dict[str, Any],
        model: dict[str, Any],
        api_key: str,
        quota: QuotaModel,
        runtime_settings: dict[str, Any],
    ) -> tuple[bool, dict[str, Any], tuple[int, int], float]:
        if (
            not runtime_settings["regressionEnabled"]
            or runtime_settings["regressionCases"] <= 0
        ):
            detail = {"enabled": False, "passed": True, "cases": []}
            await self.store.add_event(
                run_id, "regression", "skipped", "历史回归门禁未启用", detail
            )
            return True, detail, (0, 0), 0.0
        cases = await self.store.regression_cases(
            domain, runtime_settings["regressionCases"]
        )
        if not cases:
            detail = {"enabled": True, "passed": True, "cases": [], "reason": "无历史案例"}
            await self.store.add_event(
                run_id, "regression", "completed", "暂无历史案例，回归门禁通过", detail
            )
            return True, detail, (0, 0), 0.0

        system_prompt = render_system_prompt(candidate["harness"])
        results: list[dict[str, Any]] = []
        input_tokens = 0
        output_tokens = 0
        total_cost = 0.0
        for case in cases:
            response = await chat(
                text(model["endpoint"]),
                api_key,
                text(model.get("model_key")),
                system_prompt,
                [{"role": "user", "content": case["question"]}],
            )
            assessment = score_answer(
                case["question"],
                text(response.get("content")),
                int(response.get("latencyMs", 0)),
            )
            case_input = int(response.get("inputTokens", 0))
            case_output = int(response.get("outputTokens", 0))
            case_cost = await quota.consume_usage(
                model["name"], case_input + case_output
            )
            input_tokens += case_input
            output_tokens += case_output
            total_cost += case_cost
            required = float(case["expectedScore"]) * 0.9
            passed = bool(response.get("ok")) and float(assessment["score"]) >= required
            results.append(
                {
                    "caseId": case["id"],
                    "question": case["question"][:200],
                    "score": assessment["score"],
                    "requiredScore": round(required, 2),
                    "passed": passed,
                    "message": response.get("message", ""),
                }
            )
        passed = all(item["passed"] for item in results)
        detail = {"enabled": True, "passed": passed, "cases": results}
        await self.store.add_event(
            run_id,
            "regression",
            "completed" if passed else "failed",
            f"{len(results)} 个历史案例回归{'通过' if passed else '未通过'}",
            detail,
        )
        return passed, detail, (input_tokens, output_tokens), round(total_cost, 6)

    async def _add_regression_case(
        self, run_id: str, domain: str, candidate: dict[str, Any]
    ) -> None:
        run = await self.store.get_run(run_id)
        if not run or not run.get("userMessageId"):
            return
        message = await self.store.get_message(run["userMessageId"])
        if not message or not text(message.get("content")):
            return
        assessment = score_answer(
            text(message["content"]),
            text(candidate["answer"]),
            int(candidate.get("latencyMs", 0)),
        )
        await self.store.add_regression_case(
            domain=domain,
            question=text(message["content"]),
            source_answer=text(candidate["answer"]),
            expected_score=float(assessment["score"]),
            source_run_id=run_id,
            harness_id=candidate["harnessId"],
        )

    async def _record_reflection(
        self, domain: str, candidate: dict[str, Any], run_id: str
    ) -> None:
        lessons = {
            "runId": run_id,
            "adoptedCandidate": candidate["label"],
            "scope": candidate["scope"],
            "reasons": candidate.get("trace", {}).get("assessment", {}).get("reasons", []),
            "diffComponents": [
                item["component"] for item in candidate.get("trace", {}).get("diff", [])
            ],
        }
        await self.store.add_reflection(
            domain,
            candidate["harnessId"],
            lessons,
            float(candidate["score"]),
            auth.actor_id(),
        )

    async def get_run(self, body: dict[str, Any]) -> dict[str, Any]:
        run_id = _id(body.get("run_id") or body.get("runId"), "run_id")
        run = await self.store.get_run(run_id)
        if not run:
            raise ApiProblem(404, "运行不存在。")
        return {
            **run,
            "candidates": await self.store.list_candidates(run_id),
            "events": await self.store.list_events(run_id),
        }

    async def send_voice_events(
        self, body: dict[str, Any]
    ) -> AsyncIterator[dict[str, Any]]:
        """总管语音快速通道：单次模型流式回答，不创建 Harness 候选。"""
        message = text(body.get("message"))
        if not message:
            fail("请输入语音内容。", {"message": "消息不能为空。"})
        session_id = text(body.get("session_id") or body.get("sessionId"))
        if session_id:
            session_id = _id(session_id, "session_id")
            session = await self.store.get_session(session_id)
            if not session:
                raise ApiProblem(404, "会话不存在。")
        else:
            project_id = text(body.get("project_id") or body.get("projectId"))
            project = (
                await self.store.get_project(_id(project_id, "project_id"))
                if project_id
                else None
            )
            session = await self.store.create_session(
                text(body.get("title"))
                or (project["name"] if project else "")
                or message[:40],
                "project" if project else "general",
                "T3",
                project["id"] if project else None,
                project.get("expertId") if project else None,
            )
            session_id = session["id"]

        runtime_settings = await self.store.get_settings()
        if not runtime_settings["enabled"]:
            raise ApiProblem(503, "总管当前已在管理后台停用。")
        domain = classify_domain(message)
        project = None
        if session.get("projectId"):
            project = await self.store.get_project(session["projectId"])
            if project:
                domain = "project"
        risk_tier = classify_risk(message)
        await self.store.update_session(session_id, domain, risk_tier)
        prior_messages = await self.store.list_messages(session_id)

        session_expert_id = text(session.get("expertId"))
        expert_id = session_expert_id or text(
            body.get("expert_id") or body.get("expertId")
        )
        mapped_expert_id = text(
            session_expert_id
            or (runtime_settings.get("domainExperts") or {}).get(domain)
        )
        expert = await self._resolve_expert(
            domain,
            session_expert_id=session_expert_id,
            requested_expert_id="" if session_expert_id else expert_id,
            mapped_expert_id="" if session_expert_id or expert_id else mapped_expert_id,
        )
        selected = await select_model(expert)
        if not selected:
            raise ApiProblem(503, "没有可用模型，请先在模型管理中配置 API Key。")
        model, api_key = selected
        target = model_target(model, api_key)
        quota = QuotaModel()
        budget = await quota.model_budget(text(model.get("name")))
        if not budget["available"]:
            raise ApiProblem(402, "当前模型额度已用尽。")

        attachments = body.get("attachments")
        attachments = attachments if isinstance(attachments, list) else []
        attachment_summary, images = await build_attachment_context(attachments)
        attachment_meta = [
            {
                "uuid": text(item.get("uuid")),
                "name": text(item.get("name")),
                "mimeType": text(item.get("mime_type") or item.get("mimeType")),
            }
            for item in attachments
            if isinstance(item, dict)
        ]
        user_message = await self.store.add_message(
            session_id,
            "user",
            message,
            meta={
                "domain": domain,
                "riskTier": risk_tier,
                "mode": "voice",
                "expertName": expert.get("name") if expert else "",
                "projectId": project.get("id") if project else None,
                "projectName": project.get("name") if project else None,
            },
            attachments=attachment_meta,
        )
        run = await self.store.create_voice_run(
            session_id=session_id,
            user_message_id=user_message["id"],
            domain=domain,
            risk_tier=risk_tier,
            expert_id=expert.get("id") if expert else None,
            model_name=text(model["name"]),
        )
        run_id = run["id"]
        await self.store.add_event(
            run_id,
            "voice",
            "started",
            "语音快速通道已启动",
            {"mode": "voice", "model": model["name"]},
        )
        yield {
            "type": "meta",
            "runId": run_id,
            "sessionId": session_id,
            "domain": domain,
            "riskTier": risk_tier,
            "model": model["name"],
            "mode": "voice",
        }
        web_context = await self._web_search_context(
            run_id,
            message,
            model,
            api_key,
        )
        web_fetch = await self._web_fetch_context(
            run_id,
            message,
            model,
            api_key,
        )
        if web_fetch:
            web_context = "\n\n".join(
                item for item in (web_context, web_fetch) if item
            )

        project_prompt = ""
        if project:
            context = json_value(project.get("context"), {}) or {}
            project_prompt = (
                f"\n当前项目：{project['name']}。"
                f"\n项目目标：{context.get('objective', '')}"
                f"\n项目范围：{context.get('scope', '')}"
                "\n回答必须严格限定在当前项目背景内。"
            )
        expert_prompt = text(expert.get("prompt")) if expert else ""
        system_prompt = (
            "你是总管语音快速通道。直接回答用户，不要生成 Harness 候选，"
            "不要声称已执行工具、修改数据或完成外部操作。"
            "表达应适合口语朗读：先给结论，再给一到三个短段，避免复杂表格。"
            "可以使用系统提供的联网搜索和网页正文材料；若使用网页信息，"
            "口播时简短说明来源，并在回答中保留可点击的 Markdown 链接。"
            "如果用户要求执行工具或高风险操作，请提示用户结束通话并改用文字执行模式。"
            f"\n当前域：{domain}，风险等级：{risk_tier}。"
            f"\n{expert_prompt}{project_prompt}"
        )
        history = [
            {"role": item["role"], "content": item["content"]}
            for item in prior_messages[-12:]
            if item.get("role") in {"user", "assistant"}
        ]
        user_content = build_user_content(
            message, attachment_summary, images, text(model.get("endpoint"))
        )
        document_context = build_document_context(
            await self.store.list_attached_documents(session_id)
        )
        user_content = _append_user_context(user_content, document_context)
        user_content = _append_user_context(user_content, web_context)
        fitted, context_stats = fit_messages_to_budget(
            system_prompt,
            [*history, {"role": "user", "content": user_content}],
            context_window=int(target.capabilities["contextWindow"]),
            max_output_tokens=min(
                800, int(target.capabilities["maxOutputTokens"])
            ),
        )
        started = time.perf_counter()
        answer_parts: list[str] = []
        input_tokens = 0
        output_tokens = 0
        try:
            async for event in stream_chat(
                target,
                system_prompt=str(fitted[0].get("content") or ""),
                messages=fitted[1:],
                temperature=0.5,
                max_tokens=min(800, int(target.capabilities["maxOutputTokens"])),
            ):
                if event.get("type") == "delta":
                    delta = str(event.get("text") or "")
                    if delta:
                        answer_parts.append(delta)
                        yield {
                            "type": "delta",
                            "runId": run_id,
                            "text": delta,
                        }
                elif event.get("type") == "usage":
                    input_tokens = max(
                        input_tokens, int(event.get("inputTokens") or 0)
                    )
                    output_tokens = max(
                        output_tokens, int(event.get("outputTokens") or 0)
                    )
            answer = "".join(answer_parts).strip()
            if not answer:
                raise ProviderError("语音模型返回空内容", retryable=True)
            latency_ms = round((time.perf_counter() - started) * 1000)
            cost = await quota.consume_usage(
                text(model["name"]), input_tokens + output_tokens
            )
            assistant = await self.store.add_message(
                session_id,
                "assistant",
                answer,
                run_id=run_id,
                meta={
                    "domain": domain,
                    "riskTier": risk_tier,
                    "mode": "voice",
                    "model": model["name"],
                    "inputTokens": input_tokens,
                    "outputTokens": output_tokens,
                    "estimatedCost": cost,
                    "contextBudget": context_stats,
                },
            )
            await self.store.update_run(
                run_id,
                {
                    "status": "completed",
                    "assistant_message_id": assistant["id"],
                    "answer": answer,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "estimated_cost": cost,
                },
            )
            await self.store.add_event(
                run_id,
                "voice",
                "completed",
                f"语音回答完成，{latency_ms} ms",
                {"mode": "voice", "estimatedCost": cost},
            )
            await self._audit("总管语音通话", f"{domain} · {risk_tier}")
            yield {
                "type": "final",
                "runId": run_id,
                "sessionId": session_id,
                "answer": answer,
                "modelName": model["name"],
                "domain": domain,
                "riskTier": risk_tier,
                "mode": "voice",
                "inputTokens": input_tokens,
                "outputTokens": output_tokens,
                "estimatedCost": cost,
                "latencyMs": latency_ms,
                "contextBudget": context_stats,
                "assistantMessage": assistant,
            }
        except Exception as exc:  # noqa: BLE001 - SSE 需返回可读错误
            error_text = normalize_provider_error(exc)
            await self.store.update_run(
                run_id,
                {"status": "failed", "answer": "", "error": error_text},
            )
            await self.store.add_event(
                run_id, "voice", "failed", error_text
            )
            yield {
                "type": "error",
                "runId": run_id,
                "message": error_text,
            }

    async def approve_run(self, body: dict[str, Any]) -> dict[str, Any]:
        run = await self.get_run(body)
        if run["status"] != "awaiting_approval":
            raise ApiProblem(400, "当前运行不在待审批状态。")
        candidates = run["candidates"]
        selected = next(
            (item for item in candidates if item["harnessId"] == run["selectedHarnessId"]),
            choose_candidate([item for item in candidates if item["answer"]]) if candidates else None,
        )
        if not selected:
            raise ApiProblem(400, "没有可采纳的候选。")
        await self.store.activate_harness(selected["harnessId"], run["domain"])
        assistant = await self.store.add_message(
            run["sessionId"],
            "assistant",
            selected["answer"],
            run_id=run["id"],
            meta={
                "runId": run["id"],
                "domain": run["domain"],
                "riskTier": run["riskTier"],
                "harnessId": selected["harnessId"],
                "score": selected["score"],
                "approved": True,
            },
        )
        await self.store.update_run(
            run["id"],
            {
                "status": "completed",
                "answer": selected["answer"],
                "assistant_message_id": assistant["id"],
                "requires_approval": False,
                "approved_by": auth.actor_id(),
            },
        )
        await self.store.add_event(run["id"], "approval", "approved", "人工采纳候选 Harness")
        await self.store.add_event(run["id"], "complete", "completed", "生成最终回复")
        await self._record_reflection(run["domain"], selected, run["id"])
        await self._add_regression_case(run["id"], run["domain"], selected)
        await self._audit("采纳总管 Harness", f"{run['domain']} · {selected['label']}")
        return await self.get_run({"run_id": run["id"]})

    async def reject_run(self, body: dict[str, Any]) -> dict[str, Any]:
        run = await self.get_run(body)
        if run["status"] != "awaiting_approval":
            raise ApiProblem(400, "当前运行不在待审批状态。")
        await self.store.update_run(
            run["id"], {"status": "rejected", "requires_approval": False}
        )
        await self.store.add_event(
            run["id"], "approval", "rejected", "人工拒绝候选变更"
        )
        await self._audit("拒绝总管 Harness", f"{run['domain']} · {run['id']}")
        return await self.get_run({"run_id": run["id"]})
