"""DeepSeek 网页搜索：为总管补充实时网页上下文。"""
import re
from typing import Any

import httpx

from admin import secret
from admin.admin_model import RegistryModel
from common import json_value, text
from settings import settings

EXPLICIT_SEARCH_PATTERN = re.compile(
    r"^\s*#(?:网页搜索|搜索)#\s*([\s\S]+)$", re.IGNORECASE
)
SEARCH_INTENT_PATTERN = re.compile(
    r"(最新|新闻|实时|刚刚|价格|汇率|天气|政策|法规|"
    r"官网|官方发布|发布时间|版本发布|网页|联网|搜索|搜一下|查一下|查询一下|"
    r"来源链接|引用来源)",
    re.IGNORECASE,
)
NO_SEARCH_PATTERN = re.compile(r"(不要|无需|不用|别).{0,8}(搜索|联网|查网页)")


def prepare_web_search(message: str) -> tuple[bool, str]:
    value = message.strip()
    explicit = EXPLICIT_SEARCH_PATTERN.match(value)
    if explicit:
        query = explicit.group(1).strip()
        return bool(query), query[:128]
    if NO_SEARCH_PATTERN.search(value):
        return False, ""
    should_search = bool(SEARCH_INTENT_PATTERN.search(value))
    return should_search, value[:128] if should_search else ""


def _search_endpoint(model: dict[str, Any]) -> str:
    config = json_value(model.get("config"), {}) or {}
    configured = text(config.get("searchUrl") or config.get("webSearchUrl"))
    if configured:
        return configured
    endpoint = text(model.get("endpoint")).rstrip("/")
    if "api.deepseek.com" in endpoint:
        return "https://api.deepseek.com/v1/tools/search"
    return settings.deepseek_search_url


async def _search_credentials(
    preferred_model: dict[str, Any], preferred_key: str
) -> tuple[dict[str, Any], str] | None:
    if (
        "deepseek" in text(preferred_model.get("endpoint")).lower()
        or "deepseek" in text(preferred_model.get("model_key")).lower()
        or "deepseek" in text(preferred_model.get("name")).lower()
    ) and preferred_key:
        return preferred_model, preferred_key
    for item in await RegistryModel().list("model"):
        if not (
            "deepseek" in text(item.get("endpoint")).lower()
            or "deepseek" in text(item.get("model_key")).lower()
            or "deepseek" in text(item.get("name")).lower()
        ):
            continue
        api_key = secret.decrypt(item.get("api_key_enc", ""))
        if api_key:
            return item, api_key
    return None


async def deepseek_credentials(
    preferred_model: dict[str, Any] | None = None,
    preferred_key: str = "",
) -> tuple[dict[str, Any], str] | None:
    return await _search_credentials(preferred_model or {}, preferred_key)


def deepseek_fetch_endpoint(model: dict[str, Any]) -> str:
    config = json_value(model.get("config"), {}) or {}
    configured = text(config.get("fetchUrl") or config.get("webFetchUrl"))
    if configured:
        return configured
    endpoint = text(model.get("endpoint")).rstrip("/")
    if "api.deepseek.com" in endpoint:
        return "https://api.deepseek.com/v1/tools/fetch"
    return settings.deepseek_fetch_url


async def search_web(
    query: str,
    *,
    original_question: str,
    preferred_model: dict[str, Any],
    preferred_key: str,
    count: int = 5,
) -> dict[str, Any]:
    credentials = await _search_credentials(preferred_model, preferred_key)
    if not credentials:
        return {
            "ok": False,
            "query": query,
            "results": [],
            "message": "没有可用的 DeepSeek API Key，无法执行网页搜索。",
        }
    model, api_key = credentials
    timeout = float(
        (json_value(model.get("config"), {}) or {}).get("searchTimeout")
        or settings.deepseek_search_timeout
    )
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                _search_endpoint(model),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "query": query[:128],
                    "ori_question": original_question[:128],
                    "count": max(1, min(10, count)),
                    "need_content": True,
                },
            )
    except httpx.HTTPError as exc:
        return {
            "ok": False,
            "query": query,
            "results": [],
            "message": f"网页搜索连接失败：{exc.__class__.__name__}",
        }
    if response.status_code != 200:
        message = ""
        try:
            message = text((response.json().get("error") or {}).get("message"))
        except ValueError:
            message = response.text[:200]
        return {
            "ok": False,
            "query": query,
            "results": [],
            "message": f"网页搜索失败（HTTP {response.status_code}）：{message}",
        }
    payload = response.json()
    results = payload.get("results") if isinstance(payload, dict) else []
    cleaned: list[dict[str, Any]] = []
    for item in results if isinstance(results, list) else []:
        if not isinstance(item, dict) or not text(item.get("url")):
            continue
        cleaned.append(
            {
                "title": text(item.get("title")) or text(item.get("url")),
                "url": text(item.get("url")),
                "snippet": text(item.get("snippet"))[:500],
                "summary": text(item.get("summary"))[:1800],
                "content": text(item.get("content"))[:5000],
                "siteName": text(item.get("site_name")),
                "date": text(item.get("date")),
                "authority": item.get("authority"),
            }
        )
    return {
        "ok": True,
        "query": query,
        "results": cleaned,
        "message": "网页搜索完成" if cleaned else "网页搜索无结果",
    }


def search_context(results: list[dict[str, Any]]) -> str:
    if not results:
        return ""
    blocks = [
        "以下是本轮实时网页搜索结果。回答涉及这些事实时必须结合结果，"
        "并使用 Markdown 链接 [标题](URL) 标注来源；无结果或信息冲突时明确说明。"
    ]
    for index, item in enumerate(results, start=1):
        blocks.append(
            "\n".join(
                [
                    f"[{index}] {item['title']}",
                    f"URL: {item['url']}",
                    f"站点：{item['siteName'] or '未知'}；日期：{item['date'] or '未知'}；"
                    f"权威度：{item['authority']}",
                    f"摘要：{item['summary'] or item['snippet']}",
                    f"正文节选：{item['content']}",
                ]
            )
        )
    return "\n\n".join(blocks)
