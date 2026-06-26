"""Compatibility wrapper for the shared model type dictionary."""

from __future__ import annotations

from typing import Any

from services.catalogs.dictionary_catalog import (
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

_MODEL_TYPE_ALIASES = {
    "chat": "text_generation",
    "chat_completion": "text_generation",
    "chat_completions": "text_generation",
    "completion": "text_generation",
    "text": "text_generation",
    "text_generation": "text_generation",
    "vision": "multimodal_chat",
    "vision_chat": "multimodal_chat",
    "multimodal": "multimodal_chat",
    "multimodal_chat": "multimodal_chat",
    "image": "image_generation",
    "images": "image_generation",
    "image_generation": "image_generation",
    "video": "video_generation",
    "videos": "video_generation",
    "video_generation": "video_generation",
    "speech": "audio_generation",
    "tts": "audio_generation",
    "text_to_speech": "audio_generation",
    "audio": "audio_generation",
    "audio_generation": "audio_generation",
    "transcription": "audio_transcription",
    "transcriptions": "audio_transcription",
    "speech_to_text": "audio_transcription",
    "stt": "audio_transcription",
    "asr": "audio_transcription",
    "audio_transcription": "audio_transcription",
}


def normalize_model_type(value: Any) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in _MODEL_TYPE_MAP:
        return normalized
    aliased = _MODEL_TYPE_ALIASES.get(normalized)
    if aliased in _MODEL_TYPE_MAP:
        return aliased
    return DEFAULT_MODEL_TYPE


def list_model_type_options() -> list[dict[str, str]]:
    return [dict(item) for item in list_dictionary_options(MODEL_TYPE_DICTIONARY_KEY)]


def get_model_type_meta(model_type: Any) -> dict[str, str]:
    normalized = normalize_model_type(model_type)
    return dict(_MODEL_TYPE_MAP.get(normalized) or _MODEL_TYPE_MAP[DEFAULT_MODEL_TYPE])
