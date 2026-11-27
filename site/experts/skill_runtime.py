"""SKILL 发现、Schema 校验与确定性执行。"""
import hashlib
import importlib
import inspect
import json
import re
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class SkillBinding:
    alias: str
    skill_id: str
    name: str
    description: str
    parameters: dict[str, Any]
    output_schema: dict[str, Any]
    handler_path: str
    handler: Callable[[dict[str, Any]], Any]
    timeout_seconds: float


def _safe_slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", value).strip("_")[:48] or "skill"


def load_handler(handler_path: str) -> Callable[[dict[str, Any]], Any]:
    module_name, separator, function_name = handler_path.partition(":")
    if not separator or not module_name or not function_name:
        raise ValueError("handler 格式应为 module:function")
    module = importlib.import_module(module_name)
    handler = getattr(module, function_name, None)
    if not callable(handler):
        raise ValueError("handler 不可调用")
    return handler


def validate_value(
    value: Any, schema: dict[str, Any], path: str = "input"
) -> list[str]:
    if not isinstance(schema, dict) or not schema:
        return []
    errors: list[str] = []
    expected = schema.get("type")
    type_map = {
        "object": dict,
        "array": list,
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
    }
    expected_type = type_map.get(str(expected))
    if expected_type and not isinstance(value, expected_type):
        return [f"{path} 类型应为 {expected}"]
    if isinstance(value, dict):
        for key in schema.get("required") or []:
            if key not in value:
                errors.append(f"{path}.{key} 必填")
        properties = schema.get("properties") or {}
        if isinstance(properties, dict):
            for key, item_schema in properties.items():
                if key in value:
                    errors.extend(
                        validate_value(value[key], item_schema, f"{path}.{key}")
                    )
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, item in enumerate(value):
            errors.extend(
                validate_value(item, schema["items"], f"{path}[{index}]")
            )
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path} 必须是 {schema['enum']} 之一")
    return errors


def discover_skill_tools(
    skill_items: list[dict[str, Any]],
) -> tuple[list[SkillBinding], list[str]]:
    bindings: list[SkillBinding] = []
    warnings: list[str] = []
    for item in skill_items:
        config = item.get("config")
        config = config if isinstance(config, dict) else {}
        name = str(item.get("name") or item.get("id") or "SKILL")
        handler_path = str(config.get("handler") or "").strip()
        if not handler_path:
            warnings.append(f"{name} 未配置可执行 handler，未作为工具加载")
            continue
        try:
            handler = load_handler(handler_path)
            parameters = config.get("input_schema")
            if not isinstance(parameters, dict) or not parameters:
                parameters = {
                    "type": "object",
                    "properties": {
                        "input": {"type": "string", "description": "技能输入"}
                    },
                    "required": ["input"],
                }
            output_schema = config.get("output_schema")
            output_schema = output_schema if isinstance(output_schema, dict) else {}
            skill_id = str(item.get("id") or name)
            prefix = hashlib.sha256(skill_id.encode("utf-8")).hexdigest()[:6]
            bindings.append(
                SkillBinding(
                    alias=f"skill_{prefix}_{_safe_slug(name)}"[:64],
                    skill_id=skill_id,
                    name=name,
                    description=str(
                        config.get("instructions")
                        or item.get("description")
                        or name
                    ),
                    parameters=parameters,
                    output_schema=output_schema,
                    handler_path=handler_path,
                    handler=handler,
                    timeout_seconds=max(
                        0.1, min(120.0, float(config.get("timeout_seconds") or 20))
                    ),
                )
            )
        except Exception as exc:  # noqa: BLE001 - 单个技能失败不应阻断专家
            warnings.append(
                f"{name} 加载失败：{exc.__class__.__name__}: {exc}"
            )
    return bindings, warnings


async def execute_skill(
    binding: SkillBinding, arguments: dict[str, Any]
) -> Any:
    errors = validate_value(arguments, binding.parameters)
    if errors:
        raise ValueError("；".join(errors))
    result = binding.handler(arguments)
    if inspect.isawaitable(result):
        result = await result
    output_errors = validate_value(result, binding.output_schema, "output")
    if output_errors:
        raise ValueError("输出不符合 Schema：" + "；".join(output_errors))
    return result


def encode_skill_result(result: Any) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False, default=str)
