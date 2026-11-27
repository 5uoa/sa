"""项目内置确定性 SKILL handler。

这些 handler 不依赖外部模型，输入和输出均可测试；复杂技能仍可通过
config.handler 指向其他 `module:function`。
"""
from typing import Any


def competitor_analysis(arguments: dict[str, Any]) -> dict[str, Any]:
    competitors = arguments.get("competitors") or []
    focus = arguments.get("focus") or "关键差异"
    rows: list[dict[str, Any]] = []
    for item in competitors:
        if isinstance(item, dict):
            name = str(item.get("name") or "未命名")
            strengths = item.get("strengths") or []
            weaknesses = item.get("weaknesses") or []
        else:
            name = str(item)
            strengths = []
            weaknesses = []
        rows.append(
            {
                "name": name,
                "strengths": strengths,
                "weaknesses": weaknesses,
                "focus": focus,
            }
        )
    return {
        "focus": focus,
        "competitors": rows,
        "summary": f"共分析 {len(rows)} 个竞品，维度为 {focus}。",
    }


def copywriting(arguments: dict[str, Any]) -> dict[str, Any]:
    brief = str(arguments.get("brief") or "").strip()
    tone = str(arguments.get("tone") or "专业、清晰")
    channels = arguments.get("channels") or ["通用"]
    headline = f"{brief}｜{tone}" if brief else f"待补充主题｜{tone}"
    return {
        "brief": brief,
        "tone": tone,
        "drafts": [
            {
                "channel": str(channel),
                "headline": headline,
                "body": f"{brief or '请补充传播目标'}。语气：{tone}。",
            }
            for channel in channels
        ],
    }


def data_visualization(arguments: dict[str, Any]) -> dict[str, Any]:
    rows = arguments.get("data") or []
    x_field = str(arguments.get("x") or "name")
    y_field = str(arguments.get("y") or "value")
    chart_type = str(arguments.get("chart_type") or "bar")
    categories: list[Any] = []
    values: list[Any] = []
    for item in rows:
        if isinstance(item, dict):
            categories.append(item.get(x_field))
            values.append(item.get(y_field))
    return {
        "chartType": chart_type,
        "xField": x_field,
        "yField": y_field,
        "categories": categories,
        "series": [{"name": y_field, "data": values}],
        "rowCount": len(values),
    }


def meeting_minutes(arguments: dict[str, Any]) -> dict[str, Any]:
    transcript = str(arguments.get("transcript") or "").strip()
    lines = [line.strip(" -\t") for line in transcript.splitlines() if line.strip()]
    action_markers = ("待办", "行动", "负责人", "todo", "action")
    actions = [line for line in lines if any(marker in line.lower() for marker in action_markers)]
    decisions = [line for line in lines if any(marker in line for marker in ("决定", "确认", "结论"))]
    return {
        "summary": "；".join(lines[:3]) or "未提供会议内容。",
        "decisions": decisions,
        "actionItems": actions,
        "lineCount": len(lines),
    }
