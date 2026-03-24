"""Dictionary-backed defaults and validation for AI chat generation parameters."""

from __future__ import annotations

from typing import Any

from services.dictionary_catalog import get_dictionary_default_value, list_dictionary_options

_CHAT_PARAMETER_CONFIG: dict[str, dict[str, Any]] = {
    "image_resolution": {
        "dictionary_key": "llm_image_resolutions",
        "fallback_default": "1024x1024",
        "value_type": "str",
    },
    "image_aspect_ratio": {
        "dictionary_key": "llm_image_aspect_ratios",
        "fallback_default": "1:1",
        "value_type": "str",
    },
    "image_style": {
        "dictionary_key": "llm_image_styles",
        "fallback_default": "auto",
        "value_type": "str",
    },
    "image_quality": {
        "dictionary_key": "llm_image_qualities",
        "fallback_default": "high",
        "value_type": "str",
    },
    "video_aspect_ratio": {
        "dictionary_key": "llm_video_aspect_ratios",
        "fallback_default": "16:9",
        "value_type": "str",
    },
    "video_style": {
        "dictionary_key": "llm_video_styles",
        "fallback_default": "cinematic",
        "value_type": "str",
    },
    "video_duration_seconds": {
        "dictionary_key": "llm_video_duration_seconds",
        "fallback_default": 5,
        "value_type": "int",
    },
    "video_motion_strength": {
        "dictionary_key": "llm_video_motion_strengths",
        "fallback_default": "medium",
        "value_type": "str",
    },
}


def _get_parameter_config(setting_key: str) -> dict[str, Any]:
    key = str(setting_key or "").strip()
    config = _CHAT_PARAMETER_CONFIG.get(key)
    if not isinstance(config, dict):
        raise KeyError(f"Unsupported chat parameter setting: {setting_key}")
    return config


def _coerce_int(value: Any, fallback: int) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return fallback


def get_chat_parameter_dictionary_key(setting_key: str) -> str:
    return str(_get_parameter_config(setting_key).get("dictionary_key") or "").strip()


def list_chat_parameter_options(setting_key: str) -> list[dict[str, Any]]:
    return [dict(item) for item in list_dictionary_options(get_chat_parameter_dictionary_key(setting_key))]


def get_chat_parameter_default_value(setting_key: str) -> Any:
    config = _get_parameter_config(setting_key)
    fallback = config.get("fallback_default")
    raw_value = get_dictionary_default_value(
        str(config.get("dictionary_key") or "").strip(),
        fallback,
    )
    if config.get("value_type") == "int":
        return _coerce_int(raw_value, int(fallback))
    return str(raw_value or "").strip() or str(fallback)


def normalize_chat_parameter_value(setting_key: str, value: Any) -> Any:
    config = _get_parameter_config(setting_key)
    default_value = get_chat_parameter_default_value(setting_key)
    options = list_chat_parameter_options(setting_key)
    if config.get("value_type") == "int":
        allowed_values = {
            _coerce_int(item.get("id"), int(default_value))
            for item in options
            if str(item.get("id") or "").strip()
        }
        normalized = _coerce_int(value, int(default_value))
        if allowed_values and normalized in allowed_values:
            return normalized
        return int(default_value)

    normalized_text = str(value or "").strip()
    if not normalized_text:
        return str(default_value)

    for item in options:
        option_id = str(item.get("id") or "").strip()
        if option_id == normalized_text:
            return option_id
        if option_id.lower() == normalized_text.lower():
            return option_id
    return str(default_value)
