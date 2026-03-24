"""Central static dictionary registry for backend and frontend option lists."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from stores.factory import system_config_store

_DICTIONARY_REGISTRY: dict[str, dict[str, Any]] = {
    "llm_model_types": {
        "key": "llm_model_types",
        "label": "模型类型",
        "description": "用于区分模型能力，并驱动不同的参数面板与交互逻辑。",
        "default_value": "text_generation",
        "options": [
            {
                "id": "text_generation",
                "label": "文本生成",
                "description": "适合问答、写作、代码与通用对话。",
                "chat_parameter_mode": "text",
            },
            {
                "id": "multimodal_chat",
                "label": "多模态对话",
                "description": "支持图文理解和通用对话，参数面板沿用文本模式。",
                "chat_parameter_mode": "text",
            },
            {
                "id": "image_generation",
                "label": "图片生成",
                "description": "适合根据提示词或参考图生成图片。",
                "chat_parameter_mode": "image",
            },
            {
                "id": "video_generation",
                "label": "视频生成",
                "description": "适合生成短视频或动画片段。",
                "chat_parameter_mode": "video",
            },
            {
                "id": "audio_generation",
                "label": "音频生成",
                "description": "适合语音、配音或音频内容生成。",
                "chat_parameter_mode": "text",
            },
        ],
    }
}


def has_builtin_dictionary(dictionary_key: str) -> bool:
    key = str(dictionary_key or "").strip()
    return bool(key) and key in _DICTIONARY_REGISTRY


def _normalize_dictionary_definition(
    raw: dict[str, Any],
    *,
    fallback_key: str,
    builtin: bool,
) -> dict[str, Any]:
    key = str(raw.get("key") or fallback_key).strip() or fallback_key
    options = raw.get("options") if isinstance(raw.get("options"), list) else []
    return {
        "key": key,
        "label": str(raw.get("label") or "").strip(),
        "description": str(raw.get("description") or "").strip(),
        "default_value": raw.get("default_value"),
        "options": [dict(item) for item in options if isinstance(item, dict)],
        "builtin": builtin,
    }


def get_builtin_dictionary_definition(dictionary_key: str) -> dict[str, Any] | None:
    key = str(dictionary_key or "").strip()
    raw = _DICTIONARY_REGISTRY.get(key)
    if not isinstance(raw, dict):
        return None
    return _normalize_dictionary_definition(raw, fallback_key=key, builtin=True)


def _dictionary_overrides() -> dict[str, Any]:
    try:
        config = system_config_store.get_global()
    except Exception:
        return {}
    raw = getattr(config, "dictionaries", None)
    return raw if isinstance(raw, dict) else {}


def _merge_dictionary_definition(base: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(override, dict):
        return deepcopy(base)

    merged = deepcopy(base)
    label = str(override.get("label") or "").strip()
    description = str(override.get("description") or "").strip()
    default_value = str(override.get("default_value") or "").strip()
    options = override.get("options") if isinstance(override.get("options"), list) else None
    if label:
        merged["label"] = label
    if description:
        merged["description"] = description
    if default_value:
        merged["default_value"] = default_value
    if options is not None:
        merged["options"] = [dict(item) for item in options if isinstance(item, dict)]
    return merged


def has_dictionary(dictionary_key: str) -> bool:
    return get_dictionary_definition(dictionary_key) is not None


def get_custom_dictionary_definition(dictionary_key: str) -> dict[str, Any] | None:
    key = str(dictionary_key or "").strip()
    if not key or has_builtin_dictionary(key):
        return None
    override = _dictionary_overrides().get(key)
    if not isinstance(override, dict):
        return None
    return _normalize_dictionary_definition(override, fallback_key=key, builtin=False)


def list_dictionaries() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    overrides = _dictionary_overrides()
    seen_keys: set[str] = set()
    for item in _DICTIONARY_REGISTRY.values():
        key = str(item.get("key") or "").strip()
        definition = _merge_dictionary_definition(get_builtin_dictionary_definition(key) or item, overrides.get(key))
        options = definition.get("options") if isinstance(definition.get("options"), list) else []
        seen_keys.add(str(definition.get("key") or "").strip())
        items.append(
            {
                "key": str(definition.get("key") or "").strip(),
                "label": str(definition.get("label") or "").strip(),
                "description": str(definition.get("description") or "").strip(),
                "default_value": definition.get("default_value"),
                "option_count": len(options),
                "builtin": True,
            }
        )
    for raw_key, raw in overrides.items():
        key = str(raw_key or "").strip()
        if not key or key in seen_keys or not isinstance(raw, dict):
            continue
        definition = _normalize_dictionary_definition(raw, fallback_key=key, builtin=False)
        options = definition.get("options") if isinstance(definition.get("options"), list) else []
        items.append(
            {
                "key": str(definition.get("key") or "").strip(),
                "label": str(definition.get("label") or "").strip(),
                "description": str(definition.get("description") or "").strip(),
                "default_value": definition.get("default_value"),
                "option_count": len(options),
                "builtin": False,
            }
        )
    return items


def get_dictionary_definition(dictionary_key: str) -> dict[str, Any] | None:
    key = str(dictionary_key or "").strip()
    if not key:
        return None
    base = get_builtin_dictionary_definition(key)
    if base is not None:
        override = _dictionary_overrides().get(key)
        return _merge_dictionary_definition(base, override)
    return get_custom_dictionary_definition(key)


def list_dictionary_options(dictionary_key: str) -> list[dict[str, Any]]:
    definition = get_dictionary_definition(dictionary_key) or {}
    options = definition.get("options") if isinstance(definition.get("options"), list) else []
    return [dict(item) for item in options if isinstance(item, dict)]


def get_dictionary_default_value(dictionary_key: str, fallback: Any = "") -> Any:
    definition = get_dictionary_definition(dictionary_key) or {}
    value = definition.get("default_value")
    return fallback if value in (None, "") else value
