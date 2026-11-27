"""总管上下文组装：专家、模型、技能、工具、历史和附件。"""
import base64
from typing import Any

from admin import secret
from admin.admin_model import ExpertModel, RegistryModel
from common import ApiProblem, json_value, text
from models import AttachmentModel
from settings import settings


DOMAIN_EXPERT_KEYWORDS = {
    "customer": ("客户", "成功"),
    "project": ("数据", "增长", "项目"),
    "content": ("品牌", "内容", "文案"),
    "operations": ("客户", "项目", "品牌"),
    "programming": ("编程", "开发", "代码", "工程", "技术"),
}


async def select_expert(
    domain: str, preferred_expert_id: str = ""
) -> dict[str, Any] | None:
    model = ExpertModel()
    experts = [item for item in await model.list() if item.get("enabled")]
    if preferred_expert_id:
        preferred = next(
            (item for item in experts if item["id"] == preferred_expert_id), None
        )
        if preferred:
            return preferred
    keywords = DOMAIN_EXPERT_KEYWORDS.get(domain, ())
    return next(
        (
            expert
            for expert in experts
            if any(keyword in f"{expert['name']} {expert['role']}" for keyword in keywords)
        ),
        experts[0] if experts else None,
    )


async def select_model(expert: dict[str, Any] | None) -> tuple[dict[str, Any], str] | None:
    registry = RegistryModel()
    candidates: list[dict[str, Any]] = []
    if expert and expert.get("modelId"):
        target = await registry.find_model_by_id(text(expert["modelId"]))
        if target:
            candidates.append(target)
    if expert and expert.get("model"):
        target = await registry.find_model_by_name(text(expert["model"]))
        if target and all(item["id"] != target["id"] for item in candidates):
            candidates.append(target)
    for item in await registry.list("model"):
        if all(existing["id"] != item["id"] for existing in candidates):
            candidates.append(item)
    for item in candidates:
        api_key = secret.decrypt(item.get("api_key_enc", ""))
        if api_key and item.get("endpoint") and item.get("model_key"):
            return item, api_key
    return None


async def selected_resources(expert: dict[str, Any] | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    registry = RegistryModel()
    if not expert:
        return [], []
    mcp_items: list[dict[str, Any]] = []
    for resource_id in json_value(expert.get("mcp_ids"), []) or []:
        item = await registry.find_mcp(resource_id)
        if item:
            item["config"] = json_value(item.get("config"), {}) or {}
            mcp_items.append(item)
    skill_items: list[dict[str, Any]] = []
    for resource_id in json_value(expert.get("skill_ids"), []) or []:
        item = await registry.find_skill(resource_id)
        if item:
            item["config"] = json_value(item.get("config"), {}) or {}
            skill_items.append(item)
    return mcp_items, skill_items


async def build_attachment_context(
    attachments: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    if not attachments:
        return "", []
    if len(attachments) > 5:
        raise ApiProblem(400, "每条消息最多 5 个附件。")
    model = AttachmentModel()
    summaries: list[str] = []
    images: list[dict[str, Any]] = []
    for item in attachments:
        if not isinstance(item, dict):
            continue
        row = await model.get_by_uuid(text(item.get("uuid")))
        if not row or row.get("form_code") != "ADMIN_CHAT":
            raise ApiProblem(400, "附件不存在或不属于当前会话。")
        path = (settings.storage_dir / text(row.get("storage_key"))).resolve()
        if not str(path).startswith(str(settings.storage_dir.resolve())) or not path.is_file():
            raise ApiProblem(400, f"附件无法读取：{row['original_name']}")
        mime_type = text(row.get("mime_type")) or "application/octet-stream"
        extension = text(row.get("file_ext")).lower()
        summaries.append(
            f"- {row['original_name']}（{extension or mime_type}，{row['file_size']} bytes）"
        )
        content = path.read_bytes()
        if mime_type.startswith("image/"):
            images.append(
                {
                    "mimeType": mime_type,
                    "base64": base64.b64encode(content).decode("ascii"),
                }
            )
        elif extension in {"txt", "md", "csv", "json"}:
            try:
                file_text = content.decode("utf-8")
            except UnicodeDecodeError:
                file_text = content.decode("utf-8", errors="replace")
            summaries.append(f"附件 {row['original_name']} 内容：\n{file_text[:16000]}")
    return "\n".join(summaries), images


def build_document_context(documents: list[dict[str, Any]]) -> str:
    """把会话已加入的文档展开为持久上下文，并限制总长度避免挤占对话预算。"""
    if not documents:
        return ""
    sections = ["以下文档已加入当前会话，可作为本轮回答的依据："]
    used = 0
    for document in documents[:10]:
        title = text(document.get("title")) or "未命名文档"
        content = text(document.get("contentText"))
        if not content:
            continue
        remaining = 32000 - used
        if remaining <= 0:
            break
        excerpt = content[: min(12000, remaining)]
        sections.append(f"## {title}\n{excerpt}")
        used += len(excerpt)
    return "\n\n".join(sections) if len(sections) > 1 else ""


def build_user_content(
    message: str, attachment_summary: str, images: list[dict[str, Any]], endpoint: str
) -> str | list[dict[str, Any]]:
    text_content = message
    if attachment_summary:
        text_content += "\n\n本轮附件：\n" + attachment_summary
    if not images:
        return text_content
    if "anthropic" in endpoint.lower():
        blocks: list[dict[str, Any]] = [{"type": "text", "text": text_content}]
        blocks.extend(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": image["mimeType"],
                    "data": image["base64"],
                },
            }
            for image in images
        )
        return blocks
    blocks = [{"type": "text", "text": text_content}]
    blocks.extend(
        {
            "type": "image_url",
            "image_url": {"url": f"data:{image['mimeType']};base64,{image['base64']}"},
        }
        for image in images
    )
    return blocks
