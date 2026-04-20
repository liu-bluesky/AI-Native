"""系统配置路由"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from core.config import get_api_data_dir
from core.deps import (
    ensure_any_permission,
    ensure_permission,
    require_auth,
    role_store,
    system_config_store,
    user_store,
)
from models.requests import SystemConfigUpdateReq
from services.llm_provider_service import get_llm_provider_service
from services.system_mcp_discovery import list_system_mcp_skills
from stores.json.system_config_store import (
    normalize_global_assistant_guide_modules,
    normalize_voice_allowed_role_ids,
    normalize_voice_allowed_usernames,
    DEFAULT_GLOBAL_ASSISTANT_GREETING_TEXT,
    DEFAULT_GLOBAL_ASSISTANT_SYSTEM_PROMPT,
    DEFAULT_GLOBAL_ASSISTANT_TRANSCRIPTION_PROMPT,
    DEFAULT_CHAT_STYLE_HINTS,
    normalize_employee_external_skill_sites,
    normalize_public_contact_channels,
    normalize_public_changelog,
    normalize_chat_style_hints,
    normalize_query_mcp_public_base_url,
    normalize_query_mcp_clarity_confirm_threshold,
    normalize_dictionaries,
    normalize_skill_registry_sources,
    normalize_system_mcp_config,
)


def _require_system_config_permission(auth_payload: dict = Depends(require_auth)) -> None:
    ensure_permission(auth_payload, "menu.system.config")


def _require_system_config_read_permission(auth_payload: dict = Depends(require_auth)) -> None:
    ensure_any_permission(
        auth_payload,
        ["menu.system.config", "menu.ai.chat", "menu.projects", "menu.employees"],
    )


def _require_global_assistant_guide_permission(
    auth_payload: dict = Depends(require_auth),
) -> None:
    ensure_permission(auth_payload, "menu.system.assistant_guide")


router = APIRouter(prefix="/api/system-config", dependencies=[Depends(require_auth)])
public_router = APIRouter(prefix="/api/system-config")
_GLOBAL_ASSISTANT_GREETING_AUDIO_DIR = Path("global-assistant") / "greeting-audio"


def _serialize_public_contact_channels(channels: object) -> list[dict[str, object]]:
    items = [
        {
            "id": item["id"],
            "type": item["type"],
            "title": item["title"],
            "description": item["description"],
            "qq_group_number": item["qq_group_number"],
            "button_text": item["button_text"],
            "guide_text": item["guide_text"],
            "join_link": item["join_link"],
            "qr_image_url": item["qr_image_url"],
            "sort_order": item["sort_order"],
        }
        for item in normalize_public_contact_channels(channels)
        if item.get("enabled", True)
    ]
    return sorted(items, key=lambda item: (int(item["sort_order"]), item["title"], item["id"]))


def _resolve_greeting_audio_absolute_path(storage_path: object) -> Path | None:
    normalized_storage_path = str(storage_path or "").strip()
    if not normalized_storage_path:
        return None
    relative_path = Path(normalized_storage_path)
    if relative_path.is_absolute():
        return None
    data_dir = get_api_data_dir()
    absolute_path = (data_dir / relative_path).resolve()
    try:
        absolute_path.relative_to(data_dir.resolve())
    except ValueError:
        return None
    return absolute_path


def _delete_greeting_audio_file(storage_path: object) -> None:
    absolute_path = _resolve_greeting_audio_absolute_path(storage_path)
    if absolute_path is None or not absolute_path.exists():
        return
    absolute_path.unlink(missing_ok=True)
    parent = absolute_path.parent
    root = (get_api_data_dir() / _GLOBAL_ASSISTANT_GREETING_AUDIO_DIR).resolve()
    while parent != root and parent.exists():
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent


def _build_greeting_audio_signature(config_payload: dict[str, object]) -> str:
    raw_signature = json.dumps(
        {
            "voice_output_enabled": bool(config_payload.get("voice_output_enabled")),
            "voice_output_provider_id": str(config_payload.get("voice_output_provider_id") or "").strip(),
            "voice_output_model_name": str(config_payload.get("voice_output_model_name") or "").strip(),
            "voice_output_voice": str(config_payload.get("voice_output_voice") or "").strip(),
            "greeting_enabled": bool(config_payload.get("global_assistant_greeting_enabled")),
            "greeting_text": str(config_payload.get("global_assistant_greeting_text") or "").strip(),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw_signature.encode("utf-8")).hexdigest()[:32]


async def _build_greeting_audio_metadata(
    config_payload: dict[str, object],
    *,
    owner_username: str,
) -> dict[str, object]:
    greeting_enabled = bool(config_payload.get("global_assistant_greeting_enabled"))
    greeting_text = str(config_payload.get("global_assistant_greeting_text") or "").strip()
    voice_output_enabled = bool(config_payload.get("voice_output_enabled"))
    provider_id = str(config_payload.get("voice_output_provider_id") or "").strip()
    model_name = str(config_payload.get("voice_output_model_name") or "").strip()
    voice = str(config_payload.get("voice_output_voice") or "").strip()
    if not (
        greeting_enabled
        and greeting_text
        and voice_output_enabled
        and provider_id
        and model_name
        and voice
    ):
        return {}

    signature = _build_greeting_audio_signature(config_payload)
    relative_path = (_GLOBAL_ASSISTANT_GREETING_AUDIO_DIR / f"{signature}.wav").as_posix()
    absolute_path = _resolve_greeting_audio_absolute_path(relative_path)
    if absolute_path is None:
        raise HTTPException(500, "欢迎语音频缓存路径无效")

    if absolute_path.is_file():
        stat = absolute_path.stat()
        return {
            "signature": signature,
            "storage_path": relative_path,
            "content_type": "audio/wav",
            "generated_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            "file_size_bytes": stat.st_size,
        }

    payload = await get_llm_provider_service().generate_audio_speech(
        provider_id,
        model_name,
        text=greeting_text,
        voice=voice,
        response_format="wav",
        speed=1.0,
        owner_username=owner_username,
        include_all=True,
    )
    audio_bytes = payload.get("audio_bytes") or b""
    if not audio_bytes:
        raise HTTPException(502, "欢迎语音频生成结果为空")
    absolute_path.parent.mkdir(parents=True, exist_ok=True)
    absolute_path.write_bytes(audio_bytes)
    generated_at = datetime.now(timezone.utc).isoformat()
    return {
        "signature": signature,
        "storage_path": relative_path,
        "content_type": str(payload.get("content_type") or "audio/wav").strip() or "audio/wav",
        "generated_at": generated_at,
        "file_size_bytes": len(audio_bytes),
    }


def _serialize_system_config(config: object, *, include_sensitive_voice_scope: bool) -> dict[str, object]:
    payload = asdict(config)
    if include_sensitive_voice_scope:
        return payload
    payload["voice_input_allowed_usernames"] = []
    payload["voice_input_allowed_role_ids"] = []
    payload["global_assistant_guide_modules"] = []
    return payload


def _serialize_voice_provider_option(provider: dict[str, object]) -> dict[str, object] | None:
    provider_id = str(provider.get("id") or "").strip()
    if not provider_id:
        return None
    model_configs = [
        {
            "name": str(item.get("name") or item.get("model_name") or "").strip(),
            "model_type": str(item.get("model_type") or "").strip().lower(),
        }
        for item in (provider.get("model_configs") or [])
        if isinstance(item, dict)
    ]
    transcription_models = [
        {
            "name": str(item.get("name") or "").strip(),
            "model_type": "audio_transcription",
        }
        for item in model_configs
        if str(item.get("name") or "").strip()
        and str(item.get("model_type") or "").strip().lower() == "audio_transcription"
    ]
    if not transcription_models:
        return None
    default_model = str(provider.get("default_model") or "").strip()
    if not any(str(item.get("name") or "").strip() == default_model for item in transcription_models):
        default_model = str(transcription_models[0].get("name") or "").strip()
    return {
        "id": provider_id,
        "name": str(provider.get("name") or provider_id).strip(),
        "default_model": default_model,
        "model_configs": transcription_models,
    }


def _serialize_global_assistant_chat_provider_option(
    provider: dict[str, object],
) -> dict[str, object] | None:
    provider_id = str(provider.get("id") or "").strip()
    if not provider_id:
        return None
    chat_model_types = {"text_generation", "multimodal_chat"}
    model_configs = [
        {
            "name": str(item.get("name") or item.get("model_name") or "").strip(),
            "model_type": str(item.get("model_type") or "").strip().lower() or "text_generation",
        }
        for item in (provider.get("model_configs") or [])
        if isinstance(item, dict)
    ]
    chat_models = [
        {
            "name": str(item.get("name") or "").strip(),
            "model_type": str(item.get("model_type") or "").strip().lower() or "text_generation",
        }
        for item in model_configs
        if str(item.get("name") or "").strip()
        and str(item.get("model_type") or "").strip().lower() in chat_model_types
    ]
    if not chat_models:
        return None
    default_model = str(provider.get("default_model") or "").strip()
    if not any(str(item.get("name") or "").strip() == default_model for item in chat_models):
        default_model = str(chat_models[0].get("name") or "").strip()
    return {
        "id": provider_id,
        "name": str(provider.get("name") or provider_id).strip(),
        "default_model": default_model,
        "model_configs": chat_models,
    }
 

def _serialize_voice_output_provider_option(provider: dict[str, object]) -> dict[str, object] | None:
    provider_id = str(provider.get("id") or "").strip()
    if not provider_id:
        return None
    model_configs = [
        {
            "name": str(item.get("name") or item.get("model_name") or "").strip(),
            "model_type": str(item.get("model_type") or "").strip().lower(),
        }
        for item in (provider.get("model_configs") or [])
        if isinstance(item, dict)
    ]
    audio_models = [
        {
            "name": str(item.get("name") or "").strip(),
            "model_type": "audio_generation",
        }
        for item in model_configs
        if str(item.get("name") or "").strip()
        and str(item.get("model_type") or "").strip().lower() == "audio_generation"
    ]
    if not audio_models:
        return None
    default_model = str(provider.get("default_model") or "").strip()
    if not any(str(item.get("name") or "").strip() == default_model for item in audio_models):
        default_model = str(audio_models[0].get("name") or "").strip()
    return {
        "id": provider_id,
        "name": str(provider.get("name") or provider_id).strip(),
        "default_model": default_model,
        "model_configs": audio_models,
    }


def _can_manage_system_config(auth_payload: dict) -> bool:
    try:
        ensure_permission(auth_payload, "menu.system.config")
    except HTTPException:
        return False
    return True


@router.get("")
async def get_system_config(
    auth_payload: dict = Depends(require_auth),
):
    _require_system_config_read_permission(auth_payload)
    cfg = system_config_store.get_global()
    return {
        "config": _serialize_system_config(
            cfg,
            include_sensitive_voice_scope=_can_manage_system_config(auth_payload),
        )
    }


@router.get("/global-assistant-guide-modules")
async def get_global_assistant_guide_modules(
    _: None = Depends(_require_global_assistant_guide_permission),
):
    cfg = system_config_store.get_global()
    return {
        "items": list(getattr(cfg, "global_assistant_guide_modules", []) or []),
    }


@router.patch("/global-assistant-guide-modules")
async def patch_global_assistant_guide_modules(
    req: SystemConfigUpdateReq,
    _: None = Depends(_require_global_assistant_guide_permission),
):
    updates = req.model_dump(exclude_none=True)
    if set(updates.keys()) - {"global_assistant_guide_modules"}:
        raise HTTPException(400, "Only global_assistant_guide_modules can be updated here")
    if "global_assistant_guide_modules" not in updates:
        cfg = system_config_store.get_global()
        return {
            "status": "no_change",
            "items": list(getattr(cfg, "global_assistant_guide_modules", []) or []),
        }
    normalized_items = normalize_global_assistant_guide_modules(
        updates["global_assistant_guide_modules"]
    )
    updated = system_config_store.patch_global(
        {"global_assistant_guide_modules": normalized_items}
    )
    return {
        "status": "updated",
        "items": list(getattr(updated, "global_assistant_guide_modules", []) or []),
    }


@public_router.get("/public-contact-channels")
async def get_public_contact_channels():
    cfg = system_config_store.get_global()
    return {"items": _serialize_public_contact_channels(getattr(cfg, "public_contact_channels", []))}


@public_router.get("/public-changelog")
async def get_public_changelog():
    cfg = system_config_store.get_global()
    return {"content": normalize_public_changelog(getattr(cfg, "public_changelog", ""))}


@router.get("/mcp-skills")
async def get_system_mcp_skills(
    _: None = Depends(_require_system_config_permission),
):
    cfg = system_config_store.get_global()
    servers = list_system_mcp_skills(getattr(cfg, "mcp_config", {}))
    return {"servers": servers, "total": len(servers)}


@router.get("/voice-input/options")
async def get_system_voice_input_options(
    auth_payload: dict = Depends(require_auth),
):
    _require_system_config_permission(auth_payload)
    llm_service = get_llm_provider_service()
    providers = llm_service.list_providers(
        enabled_only=True,
        owner_username=str(auth_payload.get("sub") or "").strip(),
        include_all=True,
        include_shared=True,
    )
    provider_options = [
        item
        for item in (
            _serialize_voice_provider_option(provider)
            for provider in providers
        )
        if item is not None
    ]
    user_options = [
        {
            "username": item.username,
            "role": item.role,
            "role_ids": list(item.role_ids or []),
            "created_at": item.created_at,
        }
        for item in user_store.list_all()
        if str(item.username or "").strip()
    ]
    role_options = [
        {
            "id": item.id,
            "name": item.name,
            "description": item.description,
        }
        for item in role_store.list_all()
    ]
    return {
        "providers": provider_options,
        "users": user_options,
        "roles": role_options,
    }


@router.get("/voice-output/options")
async def get_system_voice_output_options(
    auth_payload: dict = Depends(require_auth),
):
    _require_system_config_permission(auth_payload)
    llm_service = get_llm_provider_service()
    providers = llm_service.list_providers(
        enabled_only=True,
        owner_username=str(auth_payload.get("sub") or "").strip(),
        include_all=True,
        include_shared=True,
    )
    provider_options = [
        item
        for item in (
            _serialize_voice_output_provider_option(provider)
            for provider in providers
        )
        if item is not None
    ]
    return {"providers": provider_options}


@router.get("/global-assistant-chat/options")
async def get_system_global_assistant_chat_options(
    auth_payload: dict = Depends(require_auth),
):
    _require_system_config_permission(auth_payload)
    llm_service = get_llm_provider_service()
    providers = llm_service.list_providers(
        enabled_only=True,
        owner_username=str(auth_payload.get("sub") or "").strip(),
        include_all=True,
        include_shared=True,
    )
    provider_options = [
        item
        for item in (
            _serialize_global_assistant_chat_provider_option(provider)
            for provider in providers
        )
        if item is not None
    ]
    return {"providers": provider_options}


@router.get("/voice-output/voices")
async def get_system_voice_output_voices(
    provider_id: str = "",
    auth_payload: dict = Depends(require_auth),
):
    _require_system_config_permission(auth_payload)
    normalized_provider_id = str(provider_id or "").strip()
    if not normalized_provider_id:
        return {"items": [], "message": "", "catalog_available": False}
    llm_service = get_llm_provider_service()
    try:
        items = await llm_service.list_audio_voices(
            normalized_provider_id,
            owner_username=str(auth_payload.get("sub") or "").strip(),
            include_all=True,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        return {
            "items": [],
            "message": str(exc),
            "catalog_available": False,
        }
    return {
        "items": items,
        "message": "" if items else "当前供应商没有返回可用音色，可直接手动填写 voice id。",
        "catalog_available": True,
    }


@router.patch("")
async def patch_system_config(
    req: SystemConfigUpdateReq,
    auth_payload: dict = Depends(require_auth),
):
    _require_system_config_permission(auth_payload)
    updates = req.model_dump(exclude_none=True)
    if not updates:
        cfg = system_config_store.get_global()
        return {"status": "no_change", "config": asdict(cfg)}
    current_config = system_config_store.get_global()

    allowed = {
        "enable_project_manual_generation",
        "enable_employee_manual_generation",
        "enable_user_register",
        "chat_upload_max_limit",
        "chat_max_tokens",
        "default_chat_system_prompt",
        "public_changelog",
        "employee_auto_rule_generation_enabled",
        "employee_auto_rule_generation_source_filters",
        "employee_auto_rule_generation_max_count",
        "employee_auto_rule_generation_prompt",
        "employee_external_skill_sites",
        "global_assistant_guide_modules",
            "voice_input_enabled",
            "voice_input_provider_id",
            "voice_input_model_name",
        "voice_input_allowed_usernames",
        "voice_input_allowed_role_ids",
        "voice_output_enabled",
        "voice_output_provider_id",
        "voice_output_model_name",
        "voice_output_voice",
        "global_assistant_greeting_enabled",
        "global_assistant_greeting_text",
        "global_assistant_chat_provider_id",
        "global_assistant_chat_model_name",
        "global_assistant_system_prompt",
        "global_assistant_transcription_prompt",
        "global_assistant_wake_phrase",
        "global_assistant_idle_timeout_sec",
        "public_contact_channels",
        "query_mcp_public_base_url",
        "query_mcp_clarity_confirm_threshold",
        "query_mcp_bootstrap_prompt_template",
        "query_mcp_usage_guide_template",
        "query_mcp_client_profile_template",
        "chat_style_hints",
        "skill_registry_sources",
        "dictionaries",
        "mcp_config",
    }
    invalid = [key for key in updates.keys() if key not in allowed]
    if invalid:
        raise HTTPException(400, f"Invalid system config keys: {invalid}")

    if "chat_upload_max_limit" in updates:
        try:
            value = int(updates["chat_upload_max_limit"])
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, "chat_upload_max_limit must be an integer") from exc
        if value < 1 or value > 20:
            raise HTTPException(400, "chat_upload_max_limit must be between 1 and 20")
        updates["chat_upload_max_limit"] = value

    if "chat_max_tokens" in updates:
        try:
            value = int(updates["chat_max_tokens"])
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, "chat_max_tokens must be an integer") from exc
        if value < 128 or value > 8192:
            raise HTTPException(400, "chat_max_tokens must be between 128 and 8192")
        updates["chat_max_tokens"] = value

    if "default_chat_system_prompt" in updates:
        updates["default_chat_system_prompt"] = str(updates["default_chat_system_prompt"] or "").strip()[:8000]

    if "public_changelog" in updates:
        updates["public_changelog"] = normalize_public_changelog(updates["public_changelog"])

    if "employee_auto_rule_generation_source_filters" in updates:
        raw_filters = updates["employee_auto_rule_generation_source_filters"]
        if raw_filters is None:
            normalized_filters = ["prompts_chat_curated"]
        elif not isinstance(raw_filters, list):
            raise HTTPException(400, "employee_auto_rule_generation_source_filters must be an array")
        else:
            normalized_filters = []
            seen: set[str] = set()
            for item in raw_filters:
                value = str(item or "").strip()
                if not value or value in seen:
                    continue
                seen.add(value)
                normalized_filters.append(value)
            if not normalized_filters:
                normalized_filters = ["prompts_chat_curated"]
        allowed_filters = {"prompts_chat_curated"}
        invalid_filters = [value for value in normalized_filters if value not in allowed_filters]
        if invalid_filters:
            raise HTTPException(400, f"Invalid employee auto rule sources: {invalid_filters}")
        updates["employee_auto_rule_generation_source_filters"] = normalized_filters

    if "employee_auto_rule_generation_max_count" in updates:
        try:
            value = int(updates["employee_auto_rule_generation_max_count"])
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, "employee_auto_rule_generation_max_count must be an integer") from exc
        if value < 1 or value > 6:
            raise HTTPException(400, "employee_auto_rule_generation_max_count must be between 1 and 6")
        updates["employee_auto_rule_generation_max_count"] = value

    if "employee_auto_rule_generation_prompt" in updates:
        updates["employee_auto_rule_generation_prompt"] = (
            str(updates["employee_auto_rule_generation_prompt"] or "").strip()[:8000]
        )

    if "employee_external_skill_sites" in updates:
        updates["employee_external_skill_sites"] = normalize_employee_external_skill_sites(
            updates["employee_external_skill_sites"]
        )

    if "global_assistant_guide_modules" in updates:
        ensure_permission(auth_payload, "menu.system.assistant_guide")
        updates["global_assistant_guide_modules"] = normalize_global_assistant_guide_modules(
            updates["global_assistant_guide_modules"]
        )

    if "voice_input_provider_id" in updates:
        updates["voice_input_provider_id"] = str(updates["voice_input_provider_id"] or "").strip()[:120]

    if "voice_input_model_name" in updates:
        updates["voice_input_model_name"] = str(updates["voice_input_model_name"] or "").strip()[:160]

    if "voice_input_allowed_usernames" in updates:
        updates["voice_input_allowed_usernames"] = normalize_voice_allowed_usernames(
            updates["voice_input_allowed_usernames"]
        )

    if "voice_input_allowed_role_ids" in updates:
        normalized_role_ids = normalize_voice_allowed_role_ids(updates["voice_input_allowed_role_ids"])
        known_role_ids = {str(item.id or "").strip().lower() for item in role_store.list_all()}
        invalid_role_ids = [item for item in normalized_role_ids if item not in known_role_ids]
        if invalid_role_ids:
            raise HTTPException(400, f"Invalid voice_input_allowed_role_ids: {invalid_role_ids}")
        updates["voice_input_allowed_role_ids"] = normalized_role_ids

    if "voice_output_provider_id" in updates:
        updates["voice_output_provider_id"] = str(updates["voice_output_provider_id"] or "").strip()[:120]

    if "voice_output_model_name" in updates:
        updates["voice_output_model_name"] = str(updates["voice_output_model_name"] or "").strip()[:160]

    if "voice_output_voice" in updates:
        updates["voice_output_voice"] = str(updates["voice_output_voice"] or "").strip()[:200]

    if "global_assistant_greeting_text" in updates:
        updates["global_assistant_greeting_text"] = (
            str(updates["global_assistant_greeting_text"] or "").strip()[:1000]
            or DEFAULT_GLOBAL_ASSISTANT_GREETING_TEXT
        )

    if "global_assistant_chat_provider_id" in updates:
        updates["global_assistant_chat_provider_id"] = (
            str(updates["global_assistant_chat_provider_id"] or "").strip()[:120]
        )

    if "global_assistant_chat_model_name" in updates:
        updates["global_assistant_chat_model_name"] = (
            str(updates["global_assistant_chat_model_name"] or "").strip()[:160]
        )

    if "global_assistant_system_prompt" in updates:
        updates["global_assistant_system_prompt"] = (
            str(updates["global_assistant_system_prompt"] or "").strip()[:8000]
            or DEFAULT_GLOBAL_ASSISTANT_SYSTEM_PROMPT
        )

    if "global_assistant_transcription_prompt" in updates:
        updates["global_assistant_transcription_prompt"] = (
            str(updates["global_assistant_transcription_prompt"] or "").strip()[:1000]
            or DEFAULT_GLOBAL_ASSISTANT_TRANSCRIPTION_PROMPT
        )

    voice_enabled = bool(
        updates.get(
            "voice_input_enabled",
            getattr(current_config, "voice_input_enabled", False),
        )
    )
    voice_provider_id = str(
        updates.get(
            "voice_input_provider_id",
            getattr(current_config, "voice_input_provider_id", ""),
        )
        or ""
    ).strip()
    voice_model_name = str(
        updates.get(
            "voice_input_model_name",
            getattr(current_config, "voice_input_model_name", ""),
        )
        or ""
    ).strip()
    if voice_enabled:
        if not voice_provider_id:
            raise HTTPException(400, "voice_input_provider_id is required when voice_input_enabled is true")
        if not voice_model_name:
            raise HTTPException(400, "voice_input_model_name is required when voice_input_enabled is true")
        provider = get_llm_provider_service().get_provider_raw(
            voice_provider_id,
            owner_username=str(auth_payload.get("sub") or "").strip(),
            include_all=True,
            include_shared=True,
        )
        if provider is None or not bool(provider.get("enabled", True)):
            raise HTTPException(400, "voice_input_provider_id is invalid or disabled")
        provider_option = _serialize_voice_provider_option(provider)
        if provider_option is None:
            raise HTTPException(400, "voice_input_provider_id has no audio transcription model")
        valid_model_names = {
            str(item.get("name") or "").strip()
            for item in provider_option.get("model_configs") or []
            if str(item.get("name") or "").strip()
        }
        if voice_model_name not in valid_model_names:
            raise HTTPException(400, "voice_input_model_name is invalid for the selected provider")

    voice_output_enabled = bool(
        updates.get(
            "voice_output_enabled",
            getattr(current_config, "voice_output_enabled", False),
        )
    )
    voice_output_provider_id = str(
        updates.get(
            "voice_output_provider_id",
            getattr(current_config, "voice_output_provider_id", ""),
        )
        or ""
    ).strip()
    voice_output_model_name = str(
        updates.get(
            "voice_output_model_name",
            getattr(current_config, "voice_output_model_name", ""),
        )
        or ""
    ).strip()
    voice_output_voice = str(
        updates.get(
            "voice_output_voice",
            getattr(current_config, "voice_output_voice", ""),
        )
        or ""
    ).strip()
    if voice_output_enabled:
        if not voice_output_provider_id:
            raise HTTPException(400, "voice_output_provider_id is required when voice_output_enabled is true")
        if not voice_output_model_name:
            raise HTTPException(400, "voice_output_model_name is required when voice_output_enabled is true")
        if not voice_output_voice:
            raise HTTPException(400, "voice_output_voice is required when voice_output_enabled is true")
        provider = get_llm_provider_service().get_provider_raw(
            voice_output_provider_id,
            owner_username=str(auth_payload.get("sub") or "").strip(),
            include_all=True,
            include_shared=True,
        )
        if provider is None or not bool(provider.get("enabled", True)):
            raise HTTPException(400, "voice_output_provider_id is invalid or disabled")
        provider_option = _serialize_voice_output_provider_option(provider)
        if provider_option is None:
            raise HTTPException(400, "voice_output_provider_id has no audio generation model")
        valid_model_names = {
            str(item.get("name") or "").strip()
            for item in provider_option.get("model_configs") or []
            if str(item.get("name") or "").strip()
        }
        if voice_output_model_name not in valid_model_names:
            raise HTTPException(400, "voice_output_model_name is invalid for the selected provider")

    global_assistant_chat_provider_id = str(
        updates.get(
            "global_assistant_chat_provider_id",
            getattr(current_config, "global_assistant_chat_provider_id", ""),
        )
        or ""
    ).strip()
    global_assistant_chat_model_name = str(
        updates.get(
            "global_assistant_chat_model_name",
            getattr(current_config, "global_assistant_chat_model_name", ""),
        )
        or ""
    ).strip()
    if global_assistant_chat_provider_id or global_assistant_chat_model_name:
        if not global_assistant_chat_provider_id:
            raise HTTPException(400, "global_assistant_chat_provider_id is required when chat model is configured")
        if not global_assistant_chat_model_name:
            raise HTTPException(400, "global_assistant_chat_model_name is required when chat provider is configured")
        provider = get_llm_provider_service().get_provider_raw(
            global_assistant_chat_provider_id,
            owner_username=str(auth_payload.get("sub") or "").strip(),
            include_all=True,
            include_shared=True,
        )
        if provider is None or not bool(provider.get("enabled", True)):
            raise HTTPException(400, "global_assistant_chat_provider_id is invalid or disabled")
        provider_option = _serialize_global_assistant_chat_provider_option(provider)
        if provider_option is None:
            raise HTTPException(400, "global_assistant_chat_provider_id has no chat model")
        valid_model_names = {
            str(item.get("name") or "").strip()
            for item in provider_option.get("model_configs") or []
            if str(item.get("name") or "").strip()
        }
        if global_assistant_chat_model_name not in valid_model_names:
            raise HTTPException(400, "global_assistant_chat_model_name is invalid for the selected provider")

    if "public_contact_channels" in updates:
        updates["public_contact_channels"] = normalize_public_contact_channels(
            updates["public_contact_channels"]
        )

    if "query_mcp_public_base_url" in updates:
        normalized_base_url = normalize_query_mcp_public_base_url(
            updates["query_mcp_public_base_url"]
        )
        if str(updates["query_mcp_public_base_url"] or "").strip() and not normalized_base_url:
            raise HTTPException(
                400,
                "query_mcp_public_base_url must be an absolute http(s) URL without query or fragment",
            )
        updates["query_mcp_public_base_url"] = normalized_base_url

    if "query_mcp_clarity_confirm_threshold" in updates:
        updates["query_mcp_clarity_confirm_threshold"] = (
            normalize_query_mcp_clarity_confirm_threshold(
                updates["query_mcp_clarity_confirm_threshold"]
            )
        )

    if "query_mcp_bootstrap_prompt_template" in updates:
        updates["query_mcp_bootstrap_prompt_template"] = (
            str(updates["query_mcp_bootstrap_prompt_template"] or "").strip()[:24000]
        )

    if "query_mcp_usage_guide_template" in updates:
        updates["query_mcp_usage_guide_template"] = (
            str(updates["query_mcp_usage_guide_template"] or "").strip()[:32000]
        )

    if "query_mcp_client_profile_template" in updates:
        updates["query_mcp_client_profile_template"] = (
            str(updates["query_mcp_client_profile_template"] or "").strip()[:12000]
        )

    if "chat_style_hints" in updates:
        if not isinstance(updates["chat_style_hints"], dict):
            raise HTTPException(400, "chat_style_hints must be a JSON object")
        updates["chat_style_hints"] = normalize_chat_style_hints(updates["chat_style_hints"])

    if "skill_registry_sources" in updates:
        updates["skill_registry_sources"] = normalize_skill_registry_sources(
            updates["skill_registry_sources"]
        )

    if "dictionaries" in updates:
        if not isinstance(updates["dictionaries"], dict):
            raise HTTPException(400, "dictionaries must be a JSON object")
        updates["dictionaries"] = normalize_dictionaries(updates["dictionaries"])

    if "mcp_config" in updates:
        if not isinstance(updates["mcp_config"], dict):
            raise HTTPException(400, "mcp_config must be a JSON object")
        updates["mcp_config"] = normalize_system_mcp_config(updates["mcp_config"])

    greeting_related_keys = {
        "voice_output_enabled",
        "voice_output_provider_id",
        "voice_output_model_name",
        "voice_output_voice",
        "global_assistant_greeting_enabled",
        "global_assistant_greeting_text",
        "global_assistant_system_prompt",
        "global_assistant_transcription_prompt",
    }
    previous_greeting_audio = dict(getattr(current_config, "global_assistant_greeting_audio", {}) or {})
    if greeting_related_keys.intersection(updates.keys()):
        effective_config = asdict(current_config)
        effective_config.update(updates)
        updates["global_assistant_greeting_audio"] = await _build_greeting_audio_metadata(
            effective_config,
            owner_username=str(auth_payload.get("sub") or "").strip(),
        )

    updated = system_config_store.patch_global(updates)
    previous_storage_path = str(previous_greeting_audio.get("storage_path") or "").strip()
    current_storage_path = str(getattr(updated, "global_assistant_greeting_audio", {}).get("storage_path") or "").strip()
    if previous_storage_path and previous_storage_path != current_storage_path:
        _delete_greeting_audio_file(previous_storage_path)
    return {"status": "updated", "config": asdict(updated)}
