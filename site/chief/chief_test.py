"""总管 Harness² 纯逻辑测试。"""
import asyncio
from typing import Any

import pytest

from chief.context_builder import build_document_context
from chief.evaluator import choose_candidate, score_answer
from chief.harness_schema import (
    build_base_harness,
    build_variants,
    classify_domain,
    classify_risk,
    component_diff,
    content_hash,
)
from chief.web_search import prepare_web_search
from chief.web_fetch import fetch_webpage, prepare_web_fetch, validate_public_url


def test_domain_and_risk_classification():
    assert classify_domain("整理客户跟进记录") == "customer"
    assert classify_domain("排查项目里程碑阻塞") == "project"
    assert classify_domain("生成品牌文案") == "content"
    assert classify_domain("修复项目前端接口报错") == "programming"
    assert classify_domain("优化数据库 SQL 性能") == "programming"
    assert classify_risk("发送通知给客户") == "T2"
    assert classify_risk("请解释项目风险") == "T3"
    assert classify_risk("提供法律意见并签署合同") == "T1"


def test_harness_variants_are_versioned_and_diffable():
    baseline = build_base_harness(
        "project",
        {"id": "expert-1", "name": "数据分析专家", "role": "增长", "prompt": "必须引用数据来源"},
        [{"id": "skill-1", "name": "数据可视化", "description": "生成图表", "config": {}}],
        [{"id": "mcp-1", "name": "数据库查询", "description": "查询数据"}],
    )
    variants = build_variants(baseline, "project")
    assert len(variants) == 2
    assert {item["scope"] for item in variants} == {"general", "domain"}
    assert content_hash(baseline) == content_hash(baseline)
    assert content_hash(variants[0]["components"]) != content_hash(baseline)
    changes = component_diff(baseline, variants[0]["components"])
    assert {item["component"] for item in changes} == {"systemPrompt", "guardrails"}


def test_candidate_score_and_composition():
    weak = {
        "scope": "general",
        "score": score_answer("项目风险", "无法回答", 2000)["score"],
        "latency_ms": 2000,
    }
    strong = {
        "scope": "domain",
        "score": score_answer(
            "项目风险",
            "项目风险如下：\n1. 依赖阻塞\n2. 验收不清\n\n下一步：明确负责人和完成标准。",
            500,
        )["score"],
        "latency_ms": 500,
    }
    assert strong["score"] > weak["score"]
    assert choose_candidate([weak, strong]) is strong


def test_document_context_includes_attached_document_content():
    context = build_document_context(
        [
            {
                "title": "竞品分析",
                "contentText": "这是加入会话的文档正文。",
            }
        ]
    )
    assert "竞品分析" in context
    assert "这是加入会话的文档正文。" in context
    assert build_document_context([]) == ""


def test_web_search_intent_and_explicit_command():
    assert prepare_web_search("请帮我搜索最新的行业新闻") == (
        True,
        "请帮我搜索最新的行业新闻",
    )
    assert prepare_web_search("#搜索# DeepSeek 网页搜索 API") == (
        True,
        "DeepSeek 网页搜索 API",
    )
    assert prepare_web_search("请解释项目风险") == (False, "")
    assert prepare_web_search("不要联网搜索，只根据附件回答") == (False, "")


def test_web_fetch_extracts_urls_and_blocks_private_targets():
    assert prepare_web_fetch(
        "请读取 https://example.com/docs 和 https://api-docs.deepseek.com/zh-cn/"
    ) == [
        "https://example.com/docs",
        "https://api-docs.deepseek.com/zh-cn/",
    ]
    assert prepare_web_fetch("#抓取# https://example.com/a。") == [
        "https://example.com/a"
    ]
    assert prepare_web_fetch("不要抓取 https://example.com") == []

    for url in (
        "http://127.0.0.1/",
        "http://localhost/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.1/",
    ):
        with pytest.raises(ValueError):
            asyncio.run(validate_public_url(url))


def test_web_fetch_uses_deepseek_api(monkeypatch: pytest.MonkeyPatch):
    requests: list[dict[str, Any]] = []

    class Response:
        status_code = 200
        text = ""

        def __init__(self, payload: dict[str, Any]):
            self._payload = payload

        def json(self) -> dict[str, Any]:
            return self._payload

    class Client:
        def __init__(self, *_: Any, **__: Any):
            pass

        async def __aenter__(self) -> "Client":
            return self

        async def __aexit__(self, *_: Any) -> None:
            return None

        async def post(
            self, url: str, *, headers: dict[str, str], json: dict[str, Any]
        ) -> Response:
            requests.append({"url": url, "headers": headers, "json": json})
            return Response(
                {
                    "title": "DeepSeek 文档",
                    "content": "# 标题\n\n抓取后的 Markdown 正文",
                }
            )

    monkeypatch.setattr("chief.web_fetch.httpx.AsyncClient", Client)
    model = {
        "name": "DeepSeek-V3",
        "endpoint": "https://api.deepseek.com",
        "model_key": "deepseek-v4-pro",
        "config": {},
    }
    result = asyncio.run(
        fetch_webpage(
            "https://1.1.1.1/example",
            preferred_model=model,
            preferred_key="sk-test",
        )
    )

    assert result["ok"] is True
    assert result["provider"] == "deepseek"
    assert result["title"] == "DeepSeek 文档"
    assert result["text"].startswith("# 标题")
    assert requests[0]["url"] == "https://api.deepseek.com/v1/tools/fetch"
    assert requests[0]["json"] == {"url": "https://1.1.1.1/example"}
    assert requests[0]["headers"]["Authorization"] == "Bearer sk-test"
