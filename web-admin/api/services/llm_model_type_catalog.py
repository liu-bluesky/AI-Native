"""Compatibility wrapper for the shared model type dictionary."""

from __future__ import annotations

from typing import Any

from services.dictionary_catalog import (
    get_dictionary_default_value,
    list_dictionary_options,
)

MODEL_TYPE_DICTIONARY_KEY = "llm_model_types"
DEFAULT_MODEL_TYPE = str(
    get_dictionary_default_value(MODEL_TYPE_DICTIONARY_KEY, "text_generation")
).strip() or "text_generation"

_MODEL_TYPE_MAP = {
    str(item.get("id") or "").strip(): item
    for item in list_dictionary_options(MODEL_TYPE_DICTIONARY_KEY)
    if str(item.get("id") or "").strip()
}


def normalize_model_type(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in _MODEL_TYPE_MAP:
        return normalized
    return DEFAULT_MODEL_TYPE


def list_model_type_options() -> list[dict[str, str]]:
    return [dict(item) for item in list_dictionary_options(MODEL_TYPE_DICTIONARY_KEY)]


def get_model_type_meta(model_type: Any) -> dict[str, str]:
    normalized = normalize_model_type(model_type)
    return dict(_MODEL_TYPE_MAP.get(normalized) or _MODEL_TYPE_MAP[DEFAULT_MODEL_TYPE])
