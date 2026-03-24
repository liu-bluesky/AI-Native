"""Shared dictionary routes."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException

from core.deps import ensure_any_permission, ensure_permission, require_auth, system_config_store
from models.requests import DictionaryCreateReq, DictionaryUpdateReq
from services.dictionary_catalog import (
    get_dictionary_definition,
    has_dictionary,
    has_builtin_dictionary,
    list_dictionaries,
)

router = APIRouter(prefix="/api/dictionaries", dependencies=[Depends(require_auth)])
_DICTIONARY_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _ensure_dictionary_read_permission(auth_payload: dict = Depends(require_auth)) -> None:
    ensure_any_permission(
        auth_payload,
        [
            "menu.system.dictionaries",
            "menu.system.config",
            "menu.llm.providers",
            "menu.ai.chat",
        ],
    )


def _ensure_dictionary_write_permission(auth_payload: dict = Depends(require_auth)) -> None:
    ensure_any_permission(
        auth_payload,
        ["menu.system.dictionaries", "menu.system.config"],
    )


def _normalize_dictionary_key(value: str) -> str:
    return str(value or "").strip()


def _build_dictionary_payload(
    dictionary_key: str,
    req: DictionaryUpdateReq,
) -> dict[str, object]:
    normalized_key = _normalize_dictionary_key(dictionary_key)
    if not normalized_key:
        raise HTTPException(400, "Dictionary key is required")
    if not _DICTIONARY_KEY_RE.fullmatch(normalized_key):
        raise HTTPException(400, "Dictionary key only supports letters, numbers, dot, underscore and hyphen")

    raw_options = req.model_dump().get("options", [])
    options: list[dict[str, str]] = []
    seen_option_ids: set[str] = set()
    for index, raw in enumerate(raw_options):
        option_id = str((raw or {}).get("id") or "").strip()
        if not option_id:
            raise HTTPException(400, f"Dictionary option #{index + 1} is missing id")
        if option_id in seen_option_ids:
            raise HTTPException(400, f"Duplicate dictionary option id: {option_id}")
        seen_option_ids.add(option_id)

        option = {
            "id": option_id,
            "label": str((raw or {}).get("label") or "").strip(),
            "description": str((raw or {}).get("description") or "").strip(),
        }
        chat_parameter_mode = str((raw or {}).get("chat_parameter_mode") or "").strip()
        if chat_parameter_mode:
            option["chat_parameter_mode"] = chat_parameter_mode
        options.append(option)

    if not options:
        raise HTTPException(400, "Dictionary must contain at least one option")

    default_value = str(req.default_value or "").strip()
    if default_value not in seen_option_ids:
        default_value = options[0]["id"]

    return {
        "key": normalized_key,
        "label": str(req.label or "").strip(),
        "description": str(req.description or "").strip(),
        "default_value": default_value,
        "options": options,
    }


@router.get("")
async def list_shared_dictionaries(
    _: None = Depends(_ensure_dictionary_read_permission),
):
    return {"items": list_dictionaries()}


@router.get("/{dictionary_key}")
async def get_shared_dictionary(
    dictionary_key: str,
    _: None = Depends(_ensure_dictionary_read_permission),
):
    definition = get_dictionary_definition(dictionary_key)
    if definition is None:
        raise HTTPException(404, f"Dictionary not found: {dictionary_key}")
    return definition


@router.post("")
async def create_shared_dictionary(
    req: DictionaryCreateReq,
    _: None = Depends(_ensure_dictionary_write_permission),
):
    normalized_key = _normalize_dictionary_key(req.key)
    if has_dictionary(normalized_key):
        raise HTTPException(409, f"Dictionary already exists: {normalized_key}")

    current = system_config_store.get_global()
    dictionaries = dict(getattr(current, "dictionaries", {}) or {})
    dictionaries[normalized_key] = _build_dictionary_payload(normalized_key, req)
    system_config_store.patch_global({"dictionaries": dictionaries})
    definition = get_dictionary_definition(normalized_key)
    if definition is None:
        raise HTTPException(500, f"Failed to create dictionary: {normalized_key}")
    return {"status": "created", "dictionary": definition}


@router.put("/{dictionary_key}")
async def update_shared_dictionary(
    dictionary_key: str,
    req: DictionaryUpdateReq,
    _: None = Depends(_ensure_dictionary_write_permission),
):
    normalized_key = _normalize_dictionary_key(dictionary_key)
    if not has_dictionary(normalized_key):
        raise HTTPException(404, f"Dictionary not found: {dictionary_key}")

    current = system_config_store.get_global()
    dictionaries = dict(getattr(current, "dictionaries", {}) or {})
    dictionaries[normalized_key] = _build_dictionary_payload(normalized_key, req)
    system_config_store.patch_global({"dictionaries": dictionaries})
    definition = get_dictionary_definition(normalized_key)
    if definition is None:
        raise HTTPException(500, f"Failed to update dictionary: {dictionary_key}")
    return {"status": "updated", "dictionary": definition}


@router.delete("/{dictionary_key}")
async def reset_shared_dictionary(
    dictionary_key: str,
    _: None = Depends(_ensure_dictionary_write_permission),
):
    normalized_key = _normalize_dictionary_key(dictionary_key)
    if not has_dictionary(normalized_key):
        raise HTTPException(404, f"Dictionary not found: {dictionary_key}")

    current = system_config_store.get_global()
    dictionaries = dict(getattr(current, "dictionaries", {}) or {})
    dictionaries.pop(normalized_key, None)
    system_config_store.patch_global({"dictionaries": dictionaries})
    if not has_builtin_dictionary(normalized_key):
        return {"status": "deleted", "dictionary_key": normalized_key}

    definition = get_dictionary_definition(normalized_key)
    if definition is None:
        raise HTTPException(500, f"Failed to reset dictionary: {dictionary_key}")
    return {"status": "reset", "dictionary": definition}
