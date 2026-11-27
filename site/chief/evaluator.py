"""无标准答案任务的轻量对比评估。"""
import re
from typing import Any


def _keywords(text: str) -> set[str]:
    return {
        item.lower()
        for item in re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9_-]{3,}", text)
        if len(item) >= 2
    }


def score_answer(question: str, answer: str, latency_ms: int) -> dict[str, Any]:
    text = answer.strip()
    reasons: list[str] = []
    score = 0.0
    if text:
        score += 30
        reasons.append("成功返回内容")
    if len(text) >= 80:
        score += 15
        reasons.append("内容具有基本完整度")
    if len(text) >= 220:
        score += 10
        reasons.append("包含较充分的说明")
    if any(token in text for token in ("1.", "1、", "- ", "###", "\n\n")):
        score += 10
        reasons.append("结构清晰")
    overlap = len(_keywords(question) & _keywords(text))
    coverage = min(20, overlap * 3)
    score += coverage
    if coverage:
        reasons.append(f"覆盖 {overlap} 个任务关键词")
    if any(token in text for token in ("下一步", "建议", "完成标准", "风险")):
        score += 10
        reasons.append("包含行动或风险信息")
    if any(token in text for token in ("无法回答", "不能提供", "不支持")):
        score -= 10
        reasons.append("存在拒绝或能力不足表述")
    latency_penalty = min(10, latency_ms / 1000)
    score -= latency_penalty
    return {
        "score": round(max(0, min(100, score)), 2),
        "reasons": reasons,
        "latencyPenalty": round(latency_penalty, 2),
    }


def choose_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    if not candidates:
        raise ValueError("没有可组合的候选")
    return max(
        candidates,
        key=lambda item: (
            float(item.get("score", 0)),
            item.get("scope") == "domain",
            -int(item.get("latency_ms", 0)),
        ),
    )
