"""项目管理路由"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import mimetypes
import re
import shutil
import subprocess
import sys
import time
import uuid
import wave
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import asdict, replace
from collections.abc import AsyncIterator
from tempfile import NamedTemporaryFile
from typing import Any
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool
import asyncio
from services.agent_orchestrator import AgentOrchestrator
from services.conversation_manager import ConversationManager
from core.redis_client import get_redis_client

# from ai_decision import ai_decide_action, execute_db_query, recommend_better_project  # 已废弃
from core.auth import decode_token
from core.config import get_api_data_dir, get_project_root, get_settings
from core.redis_client import get_redis_client
from core.deps import employee_store, external_mcp_store, get_auth_role_ids, is_admin_like, local_connector_store, project_chat_store, project_chat_task_store, project_material_store, project_studio_export_store, project_store, require_auth, resolve_role_ids_permissions, role_store, system_config_store, user_store, work_session_store
from services.feedback_service import get_feedback_service
from services.global_assistant_service import (
    build_global_assistant_builtin_tools,
    build_global_assistant_visibility_context,
)
from services.local_connector_service import (
    build_local_connector_file_tools,
    chat_completion_via_connector,
    parse_local_connector_provider_id,
)
from services.llm_chat_parameter_catalog import (
    get_chat_parameter_default_value,
    normalize_chat_parameter_value,
)
from services.llm_model_type_catalog import DEFAULT_MODEL_TYPE
from services.project_voice_service import get_project_voice_service
from services.project_chat_task_tree import (
    audit_task_tree_round,
    archive_task_tree,
    ensure_task_tree,
    get_latest_task_tree_for_user,
    get_task_tree_by_session_id,
    get_task_tree,
    get_task_tree_for_chat_session,
    list_project_task_tree_summaries,
    serialize_task_tree,
    update_task_node,
)
from services.runtime.provider_resolver import (
    ResolvedProviderRuntime,
    finalize_resolved_provider_runtime,
    list_visible_chat_providers,
    pick_provider_from_candidates,
    resolve_provider_runtime,
    resolve_runtime_llm_service,
)
from services.runtime.prompt_assembler import (
    assemble_chat_messages,
    join_prompt_sections,
    resolve_chat_style_hints,
)
from services.runtime.orchestrator_factory import build_agent_orchestrator
from services.runtime.run_request_factory import build_orchestrator_run_kwargs
from services.runtime.tool_registry import (
    collect_project_runtime_tools as collect_project_runtime_tools_via_registry,
    filter_tools_by_employee_ids as filter_tools_by_employee_ids_via_registry,
    filter_tools_by_names as filter_tools_by_names_via_registry,
    resolve_chat_workspace_path as resolve_chat_workspace_path_via_registry,
    resolve_local_connector_runtime_tools as resolve_local_connector_runtime_tools_via_registry,
    sort_tools_by_priority as sort_tools_by_priority_via_registry,
    summarize_effective_tools as summarize_effective_tools_via_registry,
)
from services.runtime.runtime_resolver import build_chat_runtime_context
from services.task_tree_guard.task_tree_evolution import build_task_tree_evolution_summary
from models.requests import (
    ProjectAiEntryFileUpdateReq,
    ProjectExperienceRuleConsolidateReq,
    ProjectExperienceRuleUpdateReq,
    ProjectExperienceRuleResolveReq,
    ProjectExperienceSummaryReq,
    ProjectRequirementRecordBatchDeleteReq,
    ProjectChatHistoryTruncateReq,
    ProjectChatReq,
    ProjectChatSettingsUpdateReq,
    ProjectChatTaskNodeUpdateReq,
    ProjectChatTaskTreeGenerateReq,
    ProjectCreateReq,
    ProjectMaterialAssetCreateReq,
    ProjectMaterialAssetUpdateReq,
    StudioAudioPayloadReq,
    StudioAudioTrackReq,
    StudioClipReq,
    StudioClipTransformReq,
    StudioTimelinePayloadReq,
    ProjectStudioDraftSaveReq,
    ProjectStudioCharacterReferenceGenerateReq,
    ProjectStudioExtractionRunReq,
    ProjectStudioExportCreateReq,
    ProjectStudioExportUpdateReq,
    ProjectStudioStoryboardGenerateReq,
    ProjectStudioVoiceGenerateReq,
    ProjectStudioVoiceUpdateReq,
    ProjectMemberAddReq,
    ProjectUserAddReq,
    ProjectUpdateReq,
    GlobalAssistantSpeechReq,
    WorkspaceDirectoryPickReq,
    WorkspaceFilePickReq,
)
from stores.json.project_chat_store import ProjectChatMessage
from stores.json.project_material_store import ProjectMaterialAsset
from stores.json.project_studio_export_store import ProjectStudioExportJob
from stores.json.project_store import ProjectConfig, ProjectMember, ProjectUserMember, _now_iso
from stores.json.system_config_store import (
    DEFAULT_GLOBAL_ASSISTANT_GREETING_TEXT,
    DEFAULT_GLOBAL_ASSISTANT_SYSTEM_PROMPT,
    DEFAULT_GLOBAL_ASSISTANT_TRANSCRIPTION_PROMPT,
    normalize_voice_allowed_role_ids,
    normalize_voice_allowed_usernames,
)
from core.role_permissions import has_permission, resolve_role_permissions
from stores.mcp_bridge import (
    Classification,
    Memory,
    MemoryScope,
    MemoryType,
    RiskDomain,
    Rule,
    Severity,
    memory_store,
    rule_store,
    rules_now_iso,
    serialize_memory,
    skill_store,
)

router = APIRouter(prefix="/api/projects", dependencies=[Depends(require_auth)])

_PROJECT_USERNAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{1,63}")
_PROJECT_EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
_GLOBAL_ASSISTANT_STORE_PROJECT_ID = "__global-assistant__"
_GLOBAL_VOICE_STREAM_SAMPLE_RATE = 16000
_GLOBAL_VOICE_STREAM_PCM_BYTES_PER_SAMPLE = 2
_GLOBAL_VOICE_STREAM_MIN_CHUNK_MS = 240
_GLOBAL_VOICE_STREAM_MAX_BUFFER_SECONDS = 20
_GLOBAL_VOICE_STREAM_FINAL_MAX_BUFFER_SECONDS = 180
_PROJECT_REQUIREMENT_RECORDS_CACHE_PREFIX = "project:req-records:item:"
_PROJECT_REQUIREMENT_RECORDS_CACHE_SET_PREFIX = "project:req-records:project:"
_PROJECT_REQUIREMENT_RECORDS_CACHE_TTL_SECONDS = 15
_project_requirement_records_local_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_PROJECT_EXPERIENCE_SUMMARY_RECORD_LIMIT = 300
_PROJECT_EXPERIENCE_RULE_DOMAIN = "项目经验"
_PROJECT_EXPERIENCE_RULE_TITLE_PREFIX = "经验卡片 · "
_DEVELOPMENT_EXPERIENCE_RULE_DOMAIN = "开发经验"
_DEVELOPMENT_EXPERIENCE_RULE_TITLE_PREFIX = "开发经验 · "
_EXPERIENCE_SCOPE_PROJECT = "project"
_EXPERIENCE_SCOPE_DEVELOPMENT = "development"
_EXPERIENCE_QUERY_STOPWORDS = {
    "一个",
    "开发",
    "处理",
    "页面",
    "需求",
    "问题",
    "项目",
    "当前",
    "功能",
}

_PROJECT_CHAT_SETTINGS_DEFAULTS: dict[str, Any] = {
    "chat_mode": "system",
    "local_connector_id": "",
    "connector_workspace_path": "",
    "connector_sandbox_mode": "workspace-write",
    "connector_sandbox_mode_explicit": False,
    "selected_employee_id": "",
    "selected_employee_ids": [],
    "employee_coordination_mode": "auto",
    "provider_id": "",
    "model_name": "",
    "temperature": 0.1,
    "max_tokens": 512,
    "system_prompt": "",
    "auto_use_tools": True,
    "enabled_project_tool_names": [],
    "tool_priority": [],
    "max_tool_calls_per_round": 6,
    "max_loop_rounds": 20,
    "max_tool_rounds": 6,
    "repeated_tool_call_threshold": 2,
    "tool_only_threshold": 3,
    "tool_budget_strategy": "finalize",
    "history_limit": 20,
    "upload_file_limit": 6,
    "max_file_size_mb": 15,
    "doc_max_chars_per_file": 1200,
    "doc_max_chars_total": 3000,
    "allowed_file_types": [
        "image/*",
        ".wps",
        ".doc",
        ".docx",
        ".pdf",
        ".txt",
        ".csv",
        ".xlsx",
        ".xls",
    ],
    "high_risk_tool_confirm": True,
    "tool_timeout_sec": 60,
    "tool_retry_count": 0,
    "answer_style": "concise",
    "prefer_conclusion_first": True,
    "task_tree_enabled": True,
    "task_tree_auto_generate": True,
    "image_resolution": "1080x1080",
    "image_aspect_ratio": "1:1",
    "image_generate_four_views": False,
    "image_style": "auto",
    "image_quality": "high",
    "video_aspect_ratio": "16:9",
    "video_style": "cinematic",
    "video_duration_seconds": 5,
    "video_motion_strength": "medium",
}

_PROJECT_TYPE_VALUES = {"image", "storyboard_video", "mixed"}
_PROJECT_TYPE_LABELS = {
    "image": "图片项目",
    "storyboard_video": "分镜视频项目",
    "mixed": "综合项目",
}
_PROJECT_MATERIAL_ASSET_TYPES = {"image", "storyboard", "video", "audio"}
_PROJECT_MATERIAL_GROUP_LABELS = {
    "image": "图片",
    "storyboard_video": "分镜 / 视频 / 音频",
}
_PROJECT_MATERIAL_ASSET_LABELS = {
    "image": "图片",
    "storyboard": "分镜",
    "video": "视频",
    "audio": "音频",
}
_PROJECT_MATERIAL_STATUS_VALUES = {"draft", "ready", "archived"}
_PROJECT_MATERIAL_STATUS_LABELS = {
    "draft": "草稿",
    "ready": "可用",
    "archived": "归档",
}
_PROJECT_MATERIAL_UPLOAD_ROOT = "project-material-files"
_PROJECT_MATERIAL_UPLOAD_MAX_BYTES = 200 * 1024 * 1024
_PROJECT_MATERIAL_UPLOAD_CHUNK_SIZE = 1024 * 1024
_PROJECT_STUDIO_EXPORT_STATUS_VALUES = {
    "draft",
    "queued",
    "processing",
    "succeeded",
    "failed",
    "canceled",
}
_PROJECT_STUDIO_EXPORT_STATUS_LABELS = {
    "draft": "草稿",
    "queued": "排队中",
    "processing": "处理中",
    "succeeded": "已完成",
    "failed": "失败",
    "canceled": "已取消",
}
_PROJECT_STUDIO_EXPORT_SOURCE_TYPE_LABELS = {
    "studio_export": "正式导出",
    "studio_draft": "制作草稿",
}
_PROJECT_STUDIO_EXPORT_FORMAT_LABELS = {
    "mp4-h264": "MP4 (H.264)",
    "mp4-h265": "MP4 (H.265)",
}
_PROJECT_STUDIO_EXPORT_RESOLUTION_VALUES = {"720p", "1080p", "4K"}
_PROJECT_CHAT_IMAGE_RESOLUTION_LONG_EDGE = {
    "720p": 1280,
    "1080p": 1920,
    "4K": 3840,
    "720x720": 720,
    "1080x1080": 1080,
    "2160x2160": 2160,
}
_PROJECT_STUDIO_CHARACTER_VIEWS = ("front", "back", "left", "right")
_PROJECT_STUDIO_CHARACTER_VIEW_LABELS = {
    "front": "正面",
    "back": "背面",
    "left": "左侧",
    "right": "右侧",
}


def _project_creator_username(project_id: str, project: ProjectConfig | None = None) -> str:
    resolved_project = project or project_store.get(project_id)
    created_by = str(getattr(resolved_project, "created_by", "") or "").strip()
    if created_by:
        return created_by
    owner_members = [
        item
        for item in project_store.list_user_members(project_id)
        if bool(getattr(item, "enabled", True))
        and str(getattr(item, "role", "") or "").strip().lower() == "owner"
        and str(getattr(item, "username", "") or "").strip()
    ]
    owner_members.sort(key=lambda item: str(getattr(item, "joined_at", "") or ""))
    return str(getattr(owner_members[0], "username", "") or "").strip() if owner_members else ""


def _can_manage_project(
    project_id: str,
    auth_payload: dict,
    project: ProjectConfig | None = None,
    *,
    creator_username: str = "",
) -> bool:
    if _is_admin_like(auth_payload):
        return True
    username = _current_username(auth_payload)
    resolved_creator_username = str(creator_username or "").strip() or _project_creator_username(project_id, project)
    return bool(username and resolved_creator_username and username == resolved_creator_username)


def _serialize_project(
    project: ProjectConfig,
    auth_payload: dict | None = None,
    *,
    member_count: int | None = None,
    user_count: int | None = None,
    creator_username: str = "",
    current_member: ProjectUserMember | None = None,
) -> dict:
    data = asdict(project)
    data.pop("chat_settings", None)
    normalized_type = _normalize_project_type(getattr(project, "type", "mixed"))
    resolved_creator_username = str(creator_username or "").strip() or _project_creator_username(project.id, project)
    data["type"] = normalized_type
    data["type_label"] = _PROJECT_TYPE_LABELS.get(normalized_type, _PROJECT_TYPE_LABELS["mixed"])
    data["member_count"] = int(member_count) if member_count is not None else len(project_store.list_members(project.id))
    data["user_count"] = int(user_count) if user_count is not None else len(project_store.list_user_members(project.id))
    data["created_by"] = resolved_creator_username
    data["ui_rule_ids"] = _normalize_project_ui_rule_ids(getattr(project, "ui_rule_ids", []) or [])
    data["ui_rule_bindings"] = _resolve_project_ui_rule_bindings(project)
    data["experience_rule_ids"] = _normalize_project_experience_rule_ids(
        getattr(project, "experience_rule_ids", []) or []
    )
    data["experience_rule_bindings"] = _resolve_project_experience_rule_bindings(project)
    data["has_mcp_instruction"] = bool(str(getattr(project, "mcp_instruction", "") or "").strip())
    data["has_workspace_path"] = bool(str(getattr(project, "workspace_path", "") or "").strip())
    data["has_ai_entry_file"] = bool(str(getattr(project, "ai_entry_file", "") or "").strip())
    if auth_payload is not None:
        current_username = _current_username(auth_payload)
        resolved_member = current_member
        if resolved_member is None and current_username:
            resolved_member = _get_project_user_member(project.id, current_username)
        data["current_user_role"] = str(getattr(resolved_member, "role", "") or "").strip().lower()
        data["can_manage"] = _can_manage_project(
            project.id,
            auth_payload,
            project,
            creator_username=resolved_creator_username,
        )
    return data


def _serialize_project_list_item(
    project: ProjectConfig,
    auth_payload: dict | None = None,
    *,
    member_count: int | None = None,
    user_count: int | None = None,
    creator_username: str = "",
    current_member: ProjectUserMember | None = None,
) -> dict[str, Any]:
    normalized_type = _normalize_project_type(getattr(project, "type", "mixed"))
    resolved_creator_username = str(creator_username or "").strip() or _project_creator_username(project.id, project)
    data: dict[str, Any] = {
        "id": str(getattr(project, "id", "") or "").strip(),
        "name": str(getattr(project, "name", "") or "").strip(),
        "description": str(getattr(project, "description", "") or "").strip(),
        "created_by": resolved_creator_username,
        "type": normalized_type,
        "type_label": _PROJECT_TYPE_LABELS.get(normalized_type, _PROJECT_TYPE_LABELS["mixed"]),
        "member_count": int(member_count) if member_count is not None else len(project_store.list_members(project.id)),
        "user_count": int(user_count) if user_count is not None else len(project_store.list_user_members(project.id)),
        "mcp_enabled": bool(getattr(project, "mcp_enabled", True)),
        "feedback_upgrade_enabled": bool(getattr(project, "feedback_upgrade_enabled", True)),
        "created_at": str(getattr(project, "created_at", "") or ""),
        "updated_at": str(getattr(project, "updated_at", "") or ""),
        "ui_rule_count": len(_normalize_project_ui_rule_ids(getattr(project, "ui_rule_ids", []) or [])),
        "has_mcp_instruction": bool(str(getattr(project, "mcp_instruction", "") or "").strip()),
        "has_workspace_path": bool(str(getattr(project, "workspace_path", "") or "").strip()),
        "has_ai_entry_file": bool(str(getattr(project, "ai_entry_file", "") or "").strip()),
    }
    if auth_payload is None:
        return data
    current_username = _current_username(auth_payload)
    resolved_member = current_member
    if resolved_member is None and current_username and not _is_admin_like(auth_payload):
        resolved_member = _get_project_user_member(project.id, current_username)
    data["current_user_role"] = str(getattr(resolved_member, "role", "") or "").strip().lower()
    data["can_manage"] = _can_manage_project(
        project.id,
        auth_payload,
        project,
        creator_username=resolved_creator_username,
    )
    return data


def _infer_material_group_type(asset_type: str) -> str:
    return "image" if asset_type == "image" else "storyboard_video"


def _normalize_material_asset_type(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in _PROJECT_MATERIAL_ASSET_TYPES:
        return normalized
    raise HTTPException(400, f"asset_type must be one of {sorted(_PROJECT_MATERIAL_ASSET_TYPES)}")


def _normalize_material_status(value: Any) -> str:
    normalized = str(value or "").strip().lower() or "ready"
    if normalized in _PROJECT_MATERIAL_STATUS_VALUES:
        return normalized
    raise HTTPException(400, f"status must be one of {sorted(_PROJECT_MATERIAL_STATUS_VALUES)}")


def _normalize_material_text(value: Any, *, limit: int = 500) -> str:
    return str(value or "").strip()[:limit]


def _normalize_studio_export_status(value: Any) -> str:
    normalized = str(value or "").strip().lower() or "queued"
    if normalized in _PROJECT_STUDIO_EXPORT_STATUS_VALUES:
        return normalized
    raise HTTPException(
        400,
        f"studio export status must be one of {sorted(_PROJECT_STUDIO_EXPORT_STATUS_VALUES)}",
    )


def _normalize_studio_export_format(value: Any) -> str:
    normalized = str(value or "").strip().lower() or "mp4-h264"
    if normalized in _PROJECT_STUDIO_EXPORT_FORMAT_LABELS:
        return normalized
    raise HTTPException(
        400,
        f"export_format must be one of {sorted(_PROJECT_STUDIO_EXPORT_FORMAT_LABELS)}",
    )


def _normalize_studio_export_resolution(value: Any) -> str:
    normalized = str(value or "").strip() or "1080p"
    if normalized in _PROJECT_STUDIO_EXPORT_RESOLUTION_VALUES:
        return normalized
    raise HTTPException(
        400,
        f"export_resolution must be one of {sorted(_PROJECT_STUDIO_EXPORT_RESOLUTION_VALUES)}",
    )


def _normalize_studio_export_payload(value: Any, field_name: str) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump()
    if isinstance(value, dict):
        return value
    if value in (None, ""):
        return {}
    raise HTTPException(400, f"{field_name} must be object")


def _normalize_studio_export_duration_seconds(value: Any, field_name: str) -> float:
    try:
        duration_seconds = float(value or 0)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, f"{field_name} must be number") from exc
    if duration_seconds <= 0:
        raise HTTPException(400, f"{field_name} must be > 0")
    return duration_seconds


def _normalize_studio_export_nonnegative_seconds(value: Any, field_name: str) -> float:
    try:
        seconds = float(value or 0)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, f"{field_name} must be number") from exc
    if seconds < 0:
        raise HTTPException(400, f"{field_name} must be >= 0")
    return seconds


def _normalize_studio_audio_volume(value: Any, field_name: str, *, default: float = 1.0) -> float:
    if value in (None, ""):
        return default
    try:
        normalized_volume = float(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, f"{field_name} must be number") from exc
    return max(0.0, min(1.5, normalized_volume))


def _resolve_project_chat_image_size(image_resolution: Any, image_aspect_ratio: Any) -> str:
    normalized_resolution = str(image_resolution or "").strip()
    normalized_resolution_key = normalized_resolution.lower()
    explicit_size_match = re.fullmatch(r"(\d{2,5})\s*(?:x|\*)\s*(\d{2,5})", normalized_resolution_key)
    if explicit_size_match:
        explicit_width = max(1, int(explicit_size_match.group(1)))
        explicit_height = max(1, int(explicit_size_match.group(2)))
        if explicit_width != explicit_height:
            if explicit_width % 2:
                explicit_width += 1
            if explicit_height % 2:
                explicit_height += 1
            return f"{explicit_width}x{explicit_height}"
        long_edge = max(explicit_width, explicit_height)
    else:
        long_edge = _PROJECT_CHAT_IMAGE_RESOLUTION_LONG_EDGE.get(normalized_resolution)
        if long_edge is None:
            long_edge = _PROJECT_CHAT_IMAGE_RESOLUTION_LONG_EDGE.get(normalized_resolution.upper())
        if long_edge is None:
            shorthand_map = {
                "hd": 1280,
                "fhd": 1920,
                "fullhd": 1920,
                "uhd": 3840,
                "4k": 3840,
            }
            long_edge = shorthand_map.get(normalized_resolution_key)
        if long_edge is None:
            match = re.fullmatch(r"(\d{3,4})\s*p", normalized_resolution_key)
            if match:
                short_edge = max(1, int(match.group(1)))
                long_edge = max(2, round((short_edge * 16) / 9))
    if not long_edge:
        return normalized_resolution
    normalized_ratio = str(image_aspect_ratio or "").strip() or "1:1"
    raw_width, _, raw_height = normalized_ratio.partition(":")
    try:
        ratio_width = max(1, int(raw_width))
    except (TypeError, ValueError):
        ratio_width = 1
    try:
        ratio_height = max(1, int(raw_height))
    except (TypeError, ValueError):
        ratio_height = 1
    if ratio_width >= ratio_height:
        width = long_edge
        height = max(1, round((long_edge * ratio_height) / ratio_width))
    else:
        width = max(1, round((long_edge * ratio_width) / ratio_height))
        height = long_edge
    if width % 2:
        width += 1
    if height % 2:
        height += 1
    return f"{width}x{height}"


def _pick_studio_audio_mixer_value(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload and payload.get(key) not in (None, ""):
            return payload.get(key)
    return None


def _list_studio_model_providers(auth_payload: dict) -> list[dict[str, Any]]:
    from services.llm_provider_service import get_llm_provider_service

    llm_service = get_llm_provider_service()
    providers = llm_service.list_providers(
        enabled_only=True,
        owner_username=str(auth_payload.get("sub") or "").strip(),
        include_all=is_admin_like(auth_payload),
        include_shared=True,
    )
    return list(providers or [])


def _serialize_studio_model_provider(provider: dict[str, Any]) -> dict[str, Any]:
    provider_id = _normalize_material_text(provider.get("id"), limit=120)
    provider_name = _normalize_material_text(provider.get("name"), limit=120) or provider_id
    raw_model_configs = provider.get("model_configs")
    model_configs = []
    if isinstance(raw_model_configs, list):
        for item in raw_model_configs:
            if not isinstance(item, dict):
                continue
            name = _normalize_material_text(item.get("name") or item.get("model_name"), limit=160)
            if not name:
                continue
            model_configs.append(
                {
                    "name": name,
                    "model_type": _normalize_material_text(item.get("model_type"), limit=80) or DEFAULT_MODEL_TYPE,
                }
            )
    raw_models = provider.get("models")
    models = []
    if isinstance(raw_models, list):
        models = [
            _normalize_material_text(item, limit=160)
            for item in raw_models
            if _normalize_material_text(item, limit=160)
        ]
    if not models and model_configs:
        models = [str(item.get("name") or "").strip() for item in model_configs if str(item.get("name") or "").strip()]
    default_model = _normalize_material_text(provider.get("default_model"), limit=160)
    if default_model and default_model not in models:
        models = [default_model, *models]
    if default_model and not any(str(item.get("name") or "").strip() == default_model for item in model_configs):
        model_configs = [
            {"name": default_model, "model_type": DEFAULT_MODEL_TYPE},
            *model_configs,
        ]
    return {
        "id": provider_id,
        "name": provider_name,
        "models": models,
        "model_configs": model_configs,
        "default_model": default_model or (models[0] if models else ""),
        "is_default": bool(provider.get("is_default")),
    }


def _resolve_studio_model_target(
    auth_payload: dict,
    *,
    preferred_provider_id: str = "",
    preferred_model_name: str = "",
) -> tuple[dict[str, Any], str]:
    from services.llm_provider_service import get_llm_provider_service

    providers = _list_studio_model_providers(auth_payload)
    if not providers:
        raise HTTPException(400, "当前没有可用模型，请先配置启用中的模型供应商")
    llm_service = get_llm_provider_service()
    normalized_provider_id = _normalize_material_text(preferred_provider_id, limit=120)
    provider = None
    if normalized_provider_id:
        provider = next(
            (item for item in providers if _normalize_material_text(item.get("id"), limit=120) == normalized_provider_id),
            None,
        )
        if provider is None:
            raise HTTPException(400, f"provider_id is invalid: {normalized_provider_id}")
    else:
        provider = next((item for item in providers if bool(item.get("is_default"))), None) or providers[0]
    if provider is None:
        raise HTTPException(400, "没有匹配的模型供应商")
    model_name = _normalize_material_text(preferred_model_name, limit=160) or _normalize_material_text(
        provider.get("default_model"),
        limit=160,
    )
    if not model_name:
        raw_models = provider.get("models")
        if isinstance(raw_models, list):
            model_name = next(
                (
                    _normalize_material_text(item, limit=160)
                    for item in raw_models
                    if _normalize_material_text(item, limit=160)
                ),
                "",
            )
    if not model_name:
        raise HTTPException(400, "model_name is required")
    try:
        provider_raw = llm_service.get_provider_raw(
            _normalize_material_text(provider.get("id"), limit=120),
            owner_username=str(auth_payload.get("sub") or "").strip(),
            include_all=is_admin_like(auth_payload),
            include_shared=True,
        )
    except TypeError:
        provider_raw = llm_service.get_provider_raw(_normalize_material_text(provider.get("id"), limit=120))
    if provider_raw is None:
        raise HTTPException(404, f"LLM provider {_normalize_material_text(provider.get('id'), limit=120)} not found")
    return provider_raw, model_name


def _parse_studio_llm_json(content: Any) -> dict[str, Any] | list[Any]:
    raw_text = str(content or "").strip()
    if not raw_text:
        raise HTTPException(502, "模型返回为空")
    candidates = [raw_text]
    if "```" in raw_text:
        fenced_blocks = re.findall(r"```(?:json)?\s*(.*?)```", raw_text, flags=re.IGNORECASE | re.DOTALL)
        candidates = [*fenced_blocks, raw_text]
    for candidate in candidates:
        text = str(candidate or "").strip()
        if not text:
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            pass
        else:
            if isinstance(parsed, (dict, list)):
                return parsed
        if "{" in text and "}" in text:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                try:
                    parsed = json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    pass
                else:
                    if isinstance(parsed, dict):
                        return parsed
        if "[" in text and "]" in text:
            start = text.find("[")
            end = text.rfind("]")
            if start >= 0 and end > start:
                try:
                    parsed = json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    pass
                else:
                    if isinstance(parsed, list):
                        return parsed
    raise HTTPException(502, f"模型返回不是合法 JSON：{raw_text[:300]}")


def _build_studio_extraction_prompt(req: ProjectStudioExtractionRunReq) -> list[dict[str, str]]:
    chapters = []
    for index, chapter in enumerate(req.chapters or [], start=1):
        if not isinstance(chapter, dict):
            continue
        title = _normalize_material_text(chapter.get("title"), limit=120) or f"章节 {index}"
        content = _normalize_material_text(chapter.get("content"), limit=2000)
        chapters.append({"title": title, "content": content})
    payload = {
        "focus_kind": req.focus_kind,
        "duration": _normalize_material_text(req.duration, limit=40),
        "quality": _normalize_material_text(req.quality, limit=40),
        "styles": [_normalize_material_text(item, limit=80) for item in req.styles if _normalize_material_text(item, limit=80)],
        "script_content": _normalize_material_text(req.script_content, limit=6000),
        "chapters": chapters,
    }
    return [
        {
            "role": "system",
            "content": (
                "你是短片制作中的美术设定助手。"
                "你必须只输出 JSON，不要输出 markdown。"
                "返回结构必须是对象，且仅包含 roles、scenes、props 三个数组字段。"
                "每个数组项字段仅允许: name, status, summary。"
                "status 只允许 detected 或 pending。"
                "结合剧本与风格提取角色、场景、道具，避免重复和空泛描述。"
            ),
        },
        {
            "role": "user",
            "content": (
                "请为短片工作台生成基础元素提取结果。\n"
                f"输入数据: {json.dumps(payload, ensure_ascii=False)}\n"
                "要求：每类返回 2~6 条；name 简洁可落地；summary 一句话描述；只返回 JSON 对象。"
            ),
        },
    ]


def _normalize_studio_extraction_items(
    payload: dict[str, Any] | list[Any],
    *,
    provider_id: str,
    model_name: str,
) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        payload = {"roles": payload, "scenes": [], "props": []}
    if not isinstance(payload, dict):
        raise HTTPException(502, "提取结果格式错误")
    key_mapping = {
        "role": ("roles", "role"),
        "scene": ("scenes", "scene"),
        "prop": ("props", "prop"),
    }
    normalized_items: list[dict[str, Any]] = []
    timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
    for kind, keys in key_mapping.items():
        raw_items = []
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                raw_items = value
                break
        for index, item in enumerate(raw_items, start=1):
            if isinstance(item, str):
                item = {"name": item}
            if not isinstance(item, dict):
                continue
            name = _normalize_material_text(item.get("name"), limit=120)
            if not name:
                continue
            status = _normalize_material_text(item.get("status"), limit=20).lower()
            normalized_items.append(
                {
                    "id": f"{kind}-{timestamp}-{index}",
                    "kind": kind,
                    "name": name,
                    "status": status if status in {"detected", "pending"} else "detected",
                    "metadata": {
                        "summary": _normalize_material_text(item.get("summary"), limit=240),
                        "provider_id": provider_id,
                        "model_name": model_name,
                    },
                }
            )
    if not normalized_items:
        raise HTTPException(502, "模型没有返回可用的提取结果")
    return normalized_items


def _build_studio_storyboard_prompt(req: ProjectStudioStoryboardGenerateReq) -> list[dict[str, str]]:
    normalized_elements = []
    for item in req.elements or []:
        if not isinstance(item, dict):
            continue
        kind = _normalize_material_text(item.get("kind"), limit=40)
        name = _normalize_material_text(item.get("name"), limit=120)
        if not kind or not name:
            continue
        normalized_elements.append({"kind": kind, "name": name})
    payload = {
        "chapter_id": _normalize_material_text(req.chapter_id, limit=120),
        "chapter_title": _normalize_material_text(req.chapter_title, limit=120),
        "chapter_content": _normalize_material_text(req.chapter_content, limit=4000),
        "duration": _normalize_material_text(req.duration, limit=40),
        "quality": _normalize_material_text(req.quality, limit=40),
        "sfx": bool(req.sfx),
        "styles": [_normalize_material_text(item, limit=80) for item in req.styles if _normalize_material_text(item, limit=80)],
        "elements": normalized_elements[:24],
    }
    return [
        {
            "role": "system",
            "content": (
                "你是短片分镜设计助手。"
                "你必须只输出 JSON，不要输出 markdown。"
                "返回结构必须是对象，且仅包含 storyboards 数组字段。"
                "每个数组项字段仅允许: title, duration_seconds, summary。"
                "title 要像镜头标题；duration_seconds 为数字；summary 一句话说明镜头内容。"
            ),
        },
        {
            "role": "user",
            "content": (
                "请根据章节内容生成可直接用于短片工作台的分镜草案。\n"
                f"输入数据: {json.dumps(payload, ensure_ascii=False)}\n"
                "要求：返回 3~6 条 storyboards；时长通常围绕给定时长上下浮动 1~2 秒；只返回 JSON 对象。"
            ),
        },
    ]


def _parse_duration_label_seconds(value: Any, default: int = 8) -> int:
    text = _normalize_material_text(value, limit=40)
    match = re.search(r"(\d+)", text)
    if not match:
        return default
    try:
        return max(3, min(30, int(match.group(1))))
    except (TypeError, ValueError):
        return default


def _normalize_studio_storyboards(
    payload: dict[str, Any] | list[Any],
    *,
    chapter_id: str,
    provider_id: str,
    model_name: str,
    preferred_duration_seconds: int,
) -> list[dict[str, Any]]:
    raw_items = payload
    if isinstance(payload, dict):
        raw_items = payload.get("storyboards")
    if not isinstance(raw_items, list):
        raise HTTPException(502, "分镜结果格式错误")
    normalized_items: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)
    timestamp = int(now.timestamp() * 1000)
    for index, item in enumerate(raw_items, start=1):
        if isinstance(item, str):
            item = {"title": item}
        if not isinstance(item, dict):
            continue
        title = _normalize_material_text(item.get("title"), limit=160)
        if not title:
            continue
        try:
            duration_seconds = int(round(float(item.get("duration_seconds", preferred_duration_seconds))))
        except (TypeError, ValueError):
            duration_seconds = preferred_duration_seconds
        duration_seconds = max(3, min(30, duration_seconds))
        normalized_items.append(
            {
                "id": f"storyboard-{chapter_id or 'chapter'}-{timestamp}-{index}",
                "chapterId": chapter_id,
                "title": title,
                "summary": _normalize_material_text(item.get("summary"), limit=240),
                "durationSeconds": duration_seconds,
                "generatedDurationSeconds": duration_seconds,
                "durationLocked": True,
                "hasVoice": False,
                "selected": False,
                "status": "draft",
                "updatedAt": now.isoformat(),
                "metadata": {
                    "provider_id": provider_id,
                    "model_name": model_name,
                },
            }
        )
    if not normalized_items:
        raise HTTPException(502, "模型没有返回可用分镜")
    return normalized_items


def _infer_studio_clip_type(source: dict[str, Any]) -> str:
    mime_type = _normalize_material_text(
        source.get("mime_type") or source.get("mimeType"),
        limit=120,
    ).lower()
    if mime_type.startswith("image/"):
        return "image"
    if mime_type.startswith("video/"):
        return "video"
    locator = " ".join(
        [
            _normalize_material_text(source.get("content_url") or source.get("contentUrl"), limit=500).lower(),
            _normalize_material_text(source.get("preview_url") or source.get("previewUrl"), limit=500).lower(),
            _normalize_material_text(source.get("storage_path") or source.get("storagePath"), limit=500).lower(),
            _normalize_material_text(source.get("original_filename") or source.get("originalFilename"), limit=240).lower(),
        ]
    )
    if any(ext in locator for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")):
        return "image"
    return "video"


def _normalize_studio_clip_transform(value: Any) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        value = value.model_dump()
    raw = value if isinstance(value, dict) else {}
    normalized = StudioClipTransformReq(
        fit=_normalize_material_text(raw.get("fit"), limit=20) or "cover",
        align=_normalize_material_text(raw.get("align"), limit=20) or "center",
        background=_normalize_material_text(raw.get("background"), limit=20) or "#000000",
    )
    return normalized.model_dump()


def _normalize_studio_timeline_payload(value: Any) -> dict[str, Any]:
    payload = _normalize_studio_export_payload(value, "timeline_payload")
    version = _normalize_material_text(payload.get("version"), limit=40) or "studio-export-legacy"
    raw_summary = payload.get("summary")
    if isinstance(raw_summary, BaseModel):
        raw_summary = raw_summary.model_dump()
    summary = raw_summary if isinstance(raw_summary, dict) else {}
    raw_clips = payload.get("clips")
    if not isinstance(raw_clips, list) or not raw_clips:
        raise HTTPException(400, "timeline_payload.clips is required")

    normalized_clips: list[dict[str, Any]] = []
    seen_clip_ids: set[str] = set()
    total_duration_seconds = 0.0
    for index, raw_clip in enumerate(raw_clips, start=1):
        if isinstance(raw_clip, BaseModel):
            raw_clip = raw_clip.model_dump()
        if not isinstance(raw_clip, dict):
            raise HTTPException(400, f"timeline_payload.clips[{index - 1}] must be object")
        normalized_clip_id = _normalize_material_text(raw_clip.get("id"), limit=120) or f"clip-{index}"
        if normalized_clip_id in seen_clip_ids:
            raise HTTPException(400, f"timeline_payload.clips contains duplicated id: {normalized_clip_id}")
        seen_clip_ids.add(normalized_clip_id)
        duration_seconds = _normalize_studio_export_duration_seconds(
            raw_clip.get("durationSeconds", raw_clip.get("duration_seconds")),
            f"timeline_payload.clips[{index - 1}].durationSeconds",
        )
        start_seconds = _normalize_studio_export_nonnegative_seconds(
            raw_clip.get("startSeconds", raw_clip.get("start_seconds")),
            f"timeline_payload.clips[{index - 1}].startSeconds",
        )
        source_id = _normalize_material_text(
            raw_clip.get("asset_id") or raw_clip.get("assetId") or raw_clip.get("sourceId") or raw_clip.get("source_id"),
            limit=120,
        )
        source_type = _normalize_material_text(
            raw_clip.get("source_type") or raw_clip.get("sourceType"),
            limit=40,
        ) or ("material" if source_id else "storyboard")
        content_url = _normalize_material_url(raw_clip.get("content_url") or raw_clip.get("contentUrl"))
        preview_url = _normalize_material_url(raw_clip.get("preview_url") or raw_clip.get("previewUrl"))
        storage_path = _normalize_material_text(
            raw_clip.get("storage_path") or raw_clip.get("storagePath"),
            limit=500,
        )
        mime_type = _normalize_material_text(
            raw_clip.get("mime_type") or raw_clip.get("mimeType"),
            limit=120,
        )
        original_filename = _normalize_material_text(
            raw_clip.get("original_filename") or raw_clip.get("originalFilename"),
            limit=240,
        )
        normalized_type = _normalize_material_text(raw_clip.get("type"), limit=20).lower() or _infer_studio_clip_type(raw_clip)
        clip_model = StudioClipReq(
            id=normalized_clip_id,
            type="image" if normalized_type == "image" else "video",
            title=_normalize_material_text(raw_clip.get("title"), limit=120) or f"片段 {index}",
            durationSeconds=duration_seconds,
            startSeconds=start_seconds,
            asset_id=source_id,
            storage_path=storage_path,
            content_url=content_url,
            preview_url=preview_url,
            mime_type=mime_type,
            original_filename=original_filename,
            source_type=(
                source_type
                if source_type in {"project_material", "studio_draft", "external_url", "ai_generated"}
                else ("project_material" if source_id else "external_url" if content_url.startswith(("http://", "https://", "data:")) else "studio_draft")
            ),
            transform=StudioClipTransformReq(**_normalize_studio_clip_transform(raw_clip.get("transform"))),
            meta=_normalize_material_mapping(raw_clip.get("meta")),
        )
        normalized_clip = clip_model.model_dump()
        normalized_clip["source_id"] = source_id
        normalized_clip["source_type"] = clip_model.source_type
        normalized_clip["duration_seconds"] = duration_seconds
        normalized_clip["start_seconds"] = start_seconds
        normalized_clips.append(normalized_clip)
        total_duration_seconds += duration_seconds

    summary_duration_seconds = (
        _normalize_studio_export_nonnegative_seconds(
            summary.get("timelineDurationSeconds", summary.get("timeline_duration_seconds")),
            "timeline_payload.summary.timelineDurationSeconds",
        )
        if summary.get("timelineDurationSeconds", summary.get("timeline_duration_seconds")) not in (None, "")
        else total_duration_seconds
    )
    return {
        "version": "studio-export-v2",
        "summary": {
            "title": _normalize_material_text(summary.get("title") or payload.get("title"), limit=120),
            "timelineDurationSeconds": max(total_duration_seconds, summary_duration_seconds),
            "clipCount": len(normalized_clips),
        },
        "clips": normalized_clips,
    }


def _normalize_studio_audio_payload(value: Any, timeline_payload: dict[str, Any]) -> dict[str, Any]:
    payload = _normalize_studio_export_payload(value, "audio_payload")
    raw_mixer = payload.get("mixer")
    mixer_payload = raw_mixer if isinstance(raw_mixer, dict) else {}
    normalized_mixer: dict[str, float] = {}
    mixer_volume_specs = (
        ("video_volume", "videoVolume", 1.0),
        ("voice_volume", "voiceVolume", 1.0),
        ("bgm_volume", "bgmVolume", 0.56),
    )
    for snake_key, camel_key, default_volume in mixer_volume_specs:
        mixer_value = _pick_studio_audio_mixer_value(mixer_payload, snake_key, camel_key)
        if mixer_value in (None, ""):
            continue
        normalized_mixer[snake_key] = _normalize_studio_audio_volume(
            mixer_value,
            f"audio_payload.mixer.{snake_key}",
            default=default_volume,
        )
    raw_tracks = payload.get("tracks")
    if raw_tracks in (None, ""):
        raw_tracks = []
    if not isinstance(raw_tracks, list):
        raise HTTPException(400, "audio_payload.tracks must be array")
    known_clip_ids = {
        _normalize_material_text(item.get("id"), limit=120)
        for item in timeline_payload.get("clips") or []
        if isinstance(item, dict)
    }
    normalized_tracks: list[dict[str, Any]] = []
    for track_index, raw_track in enumerate(raw_tracks, start=1):
        if isinstance(raw_track, BaseModel):
            raw_track = raw_track.model_dump()
        if not isinstance(raw_track, dict):
            raise HTTPException(400, f"audio_payload.tracks[{track_index - 1}] must be object")
        kind = _normalize_material_text(raw_track.get("kind"), limit=20).lower() or "bgm"
        if kind not in {"voice", "bgm", "sfx"}:
            raise HTTPException(400, f"audio_payload.tracks[{track_index - 1}].kind is invalid")
        track_id = _normalize_material_text(raw_track.get("id"), limit=120) or f"audio-track-{track_index}"
        title = _normalize_material_text(raw_track.get("title") or raw_track.get("label"), limit=120) or f"音轨 {track_index}"
        storage_path = _normalize_material_text(
            raw_track.get("storage_path") or raw_track.get("storagePath"),
            limit=500,
        )
        source_url = _normalize_material_url(
            raw_track.get("content_url") or raw_track.get("contentUrl") or raw_track.get("source_url") or raw_track.get("sourceUrl")
        )
        mime_type = _normalize_material_text(
            raw_track.get("mime_type") or raw_track.get("mimeType"),
            limit=120,
        )
        original_filename = _normalize_material_text(
            raw_track.get("original_filename") or raw_track.get("originalFilename"),
            limit=240,
        )
        bind_clip_id = _normalize_material_text(
            raw_track.get("bind_clip_id") or raw_track.get("bindClipId"),
            limit=120,
        )
        if bind_clip_id and bind_clip_id not in known_clip_ids:
            raise HTTPException(400, f"audio_payload.tracks[{track_index - 1}].bind_clip_id not found: {bind_clip_id}")
        required = bool(raw_track.get("required"))
        base_volume = raw_track.get("volume")
        default_volume = normalized_mixer.get(f"{kind}_volume", 1.0)
        normalized_volume = _normalize_studio_audio_volume(
            base_volume,
            f"audio_payload.tracks[{track_index - 1}].volume",
            default=default_volume,
        )
        raw_segments = raw_track.get("segments")
        segments: list[dict[str, Any]] = []
        if isinstance(raw_segments, list):
            for segment_index, raw_segment in enumerate(raw_segments, start=1):
                if not isinstance(raw_segment, dict):
                    raise HTTPException(
                        400,
                        f"audio_payload.tracks[{track_index - 1}].segments[{segment_index - 1}] must be object",
                    )
                duration_seconds = _normalize_studio_export_duration_seconds(
                    raw_segment.get("durationSeconds", raw_segment.get("duration_seconds")),
                    f"audio_payload.tracks[{track_index - 1}].segments[{segment_index - 1}].durationSeconds",
                )
                start_seconds = _normalize_studio_export_nonnegative_seconds(
                    raw_segment.get("startSeconds", raw_segment.get("start_seconds")),
                    f"audio_payload.tracks[{track_index - 1}].segments[{segment_index - 1}].startSeconds",
                )
                segment_volume = _normalize_studio_audio_volume(
                    raw_segment.get("volume"),
                    f"audio_payload.tracks[{track_index - 1}].segments[{segment_index - 1}].volume",
                    default=normalized_volume,
                )
                segments.append(
                    {
                        "id": _normalize_material_text(raw_segment.get("id"), limit=120) or f"{track_id}-segment-{segment_index}",
                        "label": _normalize_material_text(raw_segment.get("label"), limit=120) or f"{title} 片段 {segment_index}",
                        "start_seconds": start_seconds,
                        "duration_seconds": duration_seconds,
                        "source_url": _normalize_material_url(
                            raw_segment.get("source_url") or raw_segment.get("sourceUrl")
                        ),
                        "storage_path": _normalize_material_text(
                            raw_segment.get("storage_path") or raw_segment.get("storagePath"),
                            limit=500,
                        ),
                        "mime_type": _normalize_material_text(
                            raw_segment.get("mime_type") or raw_segment.get("mimeType"),
                            limit=120,
                        ),
                        "original_filename": _normalize_material_text(
                            raw_segment.get("original_filename") or raw_segment.get("originalFilename"),
                            limit=240,
                        ),
                        "volume": segment_volume,
                        "required": required,
                        "bind_clip_id": bind_clip_id,
                    }
                )
        else:
            duration_seconds = raw_track.get("durationSeconds", raw_track.get("duration_seconds"))
            if duration_seconds not in (None, ""):
                track_model = StudioAudioTrackReq(
                    id=track_id,
                    kind=kind,
                    title=title,
                    startSeconds=_normalize_studio_export_nonnegative_seconds(
                        raw_track.get("startSeconds", raw_track.get("start_seconds")),
                        f"audio_payload.tracks[{track_index - 1}].startSeconds",
                    ),
                    durationSeconds=_normalize_studio_export_duration_seconds(
                        duration_seconds,
                        f"audio_payload.tracks[{track_index - 1}].durationSeconds",
                    ),
                    volume=normalized_volume,
                    asset_id=_normalize_material_text(
                        raw_track.get("asset_id") or raw_track.get("assetId"),
                        limit=120,
                    ),
                    storage_path=storage_path,
                    content_url=source_url,
                    mime_type=mime_type,
                    original_filename=original_filename,
                    required=required,
                    bind_clip_id=bind_clip_id,
                )
                track_payload = track_model.model_dump()
                segments = [
                    {
                        "id": track_payload["id"],
                        "label": track_payload["title"] or title,
                        "start_seconds": track_payload["startSeconds"],
                        "duration_seconds": track_payload["durationSeconds"],
                        "source_url": track_payload["content_url"],
                        "storage_path": track_payload["storage_path"],
                        "mime_type": track_payload["mime_type"],
                        "original_filename": track_payload["original_filename"],
                        "volume": track_payload["volume"],
                        "required": track_payload["required"],
                        "bind_clip_id": track_payload["bind_clip_id"],
                    }
                ]
        if not segments:
            continue
        normalized_tracks.append(
            {
                "id": track_id,
                "kind": kind,
                "label": title,
                "source_url": source_url,
                "storage_path": storage_path,
                "mime_type": mime_type,
                "original_filename": original_filename,
                "volume": normalized_volume,
                "required": required,
                "bind_clip_id": bind_clip_id,
                "segments": segments,
            }
        )
    normalized_payload = StudioAudioPayloadReq(
        version="studio-audio-v2",
        tracks=[
            StudioAudioTrackReq(
                id=item["id"],
                kind=item["kind"],
                title=item["label"],
                startSeconds=float(item["segments"][0]["start_seconds"]),
                durationSeconds=float(item["segments"][0]["duration_seconds"]),
                volume=float(item["volume"]),
                storage_path=item["storage_path"],
                content_url=item["source_url"],
                mime_type=item["mime_type"],
                original_filename=item["original_filename"],
                required=bool(item["required"]),
                bind_clip_id=item["bind_clip_id"],
            )
            for item in normalized_tracks
        ],
    )
    payload_data = normalized_payload.model_dump()
    if normalized_mixer:
        payload_data["mixer"] = normalized_mixer
    payload_data["tracks"] = normalized_tracks
    return payload_data


def _normalize_studio_export_progress(value: Any) -> int:
    try:
        progress = int(round(float(value or 0)))
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "progress must be number") from exc
    return max(0, min(100, progress))


def _extract_studio_export_clip_count(timeline_payload: dict[str, Any]) -> int:
    clips = timeline_payload.get("clips")
    if isinstance(clips, list):
        return len(clips)
    return 0


def _extract_studio_export_timeline_duration_seconds(timeline_payload: dict[str, Any]) -> int:
    summary = timeline_payload.get("summary")
    if isinstance(summary, dict):
        for key in ("timelineDurationSeconds", "timeline_duration_seconds"):
            try:
                duration = int(round(float(summary.get(key) or 0)))
            except (TypeError, ValueError):
                duration = 0
            if duration > 0:
                return duration
    duration_seconds = 0
    clips = timeline_payload.get("clips")
    if isinstance(clips, list):
        for item in clips:
            if not isinstance(item, dict):
                continue
            try:
                duration_seconds += max(
                    0,
                    int(round(float(item.get("durationSeconds") or item.get("duration_seconds") or 0))),
                )
            except (TypeError, ValueError):
                continue
    return duration_seconds


def _derive_studio_export_title(
    requested_title: Any,
    export_format: str,
    export_resolution: str,
    timeline_payload: dict[str, Any],
) -> str:
    normalized_title = _normalize_material_text(requested_title, limit=120)
    if normalized_title:
        return normalized_title
    summary = timeline_payload.get("summary")
    if isinstance(summary, dict):
        draft_title = _normalize_material_text(
            summary.get("title") or summary.get("draftTitle"),
            limit=120,
        )
        if draft_title:
            return draft_title
    return f"正式导出 {export_resolution} / {_PROJECT_STUDIO_EXPORT_FORMAT_LABELS.get(export_format, export_format)}"


def _normalize_material_url(value: Any, *, limit: int = 20000) -> str:
    normalized = str(value or "").strip()[:limit]
    if not normalized:
        return ""
    lowered = normalized.lower()
    if lowered.startswith("file://"):
        raise HTTPException(400, "素材地址不支持 file:// 本地路径，请改用 http(s) 地址或先上传到服务器")
    if lowered.startswith(("http://", "https://", "data:")) or normalized.startswith("/"):
        return normalized
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", normalized):
        raise HTTPException(400, "素材地址仅支持 http(s)、data URL 或站内相对路径")
    return normalized


def _normalize_material_url_list(value: Any, *, item_limit: int = 8) -> list[str]:
    if not isinstance(value, list):
        return []
    urls: list[str] = []
    seen: set[str] = set()
    for item in value:
        normalized = _normalize_material_url(item)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        urls.append(normalized)
        if len(urls) >= item_limit:
            break
    return urls


def _normalize_material_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _parse_material_json_text(value: Any, field_name: str) -> dict[str, Any]:
    source = str(value or "").strip()
    if not source:
        return {}
    try:
        parsed = json.loads(source)
    except json.JSONDecodeError as exc:
        raise HTTPException(400, f"{field_name} must be valid JSON object text") from exc
    if isinstance(parsed, dict):
        return parsed
    raise HTTPException(400, f"{field_name} must be valid JSON object text")


def _normalize_material_video_duration_seconds(value: Any) -> int:
    try:
        duration = round(float(value or 0))
    except (TypeError, ValueError):
        return 0
    if duration <= 0:
        return 0
    return max(1, int(duration))


def _extract_material_video_duration_seconds(metadata: dict[str, Any] | None) -> int:
    if not isinstance(metadata, dict):
        return 0
    for key in (
        "duration_seconds",
        "durationSeconds",
        "video_duration_seconds",
        "videoDurationSeconds",
    ):
        normalized_duration = _normalize_material_video_duration_seconds(metadata.get(key))
        if normalized_duration > 0:
            return normalized_duration
    return 0


def _require_material_video_duration_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    normalized_metadata = dict(metadata or {})
    duration_seconds = _extract_material_video_duration_seconds(normalized_metadata)
    if duration_seconds <= 0:
        raise HTTPException(400, "视频素材缺少有效时长，无法上传")
    normalized_metadata["duration_seconds"] = duration_seconds
    normalized_metadata["durationSeconds"] = duration_seconds
    normalized_metadata["video_duration_seconds"] = duration_seconds
    normalized_metadata["videoDurationSeconds"] = duration_seconds
    return normalized_metadata


def _project_material_file_root() -> Path:
    root = get_api_data_dir() / _PROJECT_MATERIAL_UPLOAD_ROOT
    root.mkdir(parents=True, exist_ok=True)
    return root


def _sanitize_material_filename(filename: str, fallback_name: str) -> str:
    raw_name = Path(str(filename or "").strip()).name or fallback_name
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "-", raw_name).strip(".-")
    if not sanitized:
        sanitized = fallback_name
    return sanitized[:180]


def _build_inline_content_disposition(filename: str, fallback_name: str) -> str:
    raw_name = Path(str(filename or "").strip()).name or fallback_name
    normalized_name = raw_name.replace("\r", "").replace("\n", "").replace('"', "")
    safe_fallback = _sanitize_material_filename(normalized_name, fallback_name)
    encoded_name = quote(normalized_name, safe="")
    return f"inline; filename={safe_fallback}; filename*=UTF-8''{encoded_name}"


def _infer_material_upload_mime_type(upload: UploadFile, fallback: str = "") -> str:
    explicit = str(fallback or "").strip()
    if explicit:
        return explicit
    content_type = str(getattr(upload, "content_type", "") or "").strip()
    if content_type:
        return content_type[:120]
    guessed, _ = mimetypes.guess_type(str(getattr(upload, "filename", "") or ""))
    return str(guessed or "").strip()[:120]


def _validate_material_upload_type(asset_type: str, mime_type: str) -> None:
    normalized_mime = str(mime_type or "").strip().lower()
    if asset_type == "image" and not normalized_mime.startswith("image/"):
        raise HTTPException(400, "图片素材请上传图片文件")
    if asset_type == "video" and not normalized_mime.startswith("video/"):
        raise HTTPException(400, "视频素材请上传视频文件")
    if asset_type == "audio" and not normalized_mime.startswith("audio/"):
        raise HTTPException(400, "音频素材请上传音频文件")


def _validate_material_cover_upload_type(mime_type: str) -> None:
    normalized_mime = str(mime_type or "").strip().lower()
    if not normalized_mime.startswith("image/"):
        raise HTTPException(400, "视频封面请上传图片文件")


def _validate_studio_audio_upload_type(mime_type: str) -> None:
    normalized_mime = str(mime_type or "").strip().lower()
    if not normalized_mime.startswith("audio/"):
        raise HTTPException(400, "背景音乐请上传音频文件")


async def _write_material_upload_file(upload: UploadFile, destination: Path) -> int:
    destination.parent.mkdir(parents=True, exist_ok=True)
    total_size = 0
    try:
        with destination.open("wb") as handle:
            while True:
                chunk = await upload.read(_PROJECT_MATERIAL_UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > _PROJECT_MATERIAL_UPLOAD_MAX_BYTES:
                    raise HTTPException(400, "上传文件过大，当前上限为 200MB")
                handle.write(chunk)
    except Exception:
        if destination.exists():
            destination.unlink(missing_ok=True)
        raise
    if total_size <= 0:
        destination.unlink(missing_ok=True)
        raise HTTPException(400, "Uploaded file is empty")
    return total_size


def _build_material_file_url(project_id: str, asset_id: str) -> str:
    normalized_project_id = str(project_id or "").strip()
    normalized_asset_id = str(asset_id or "").strip()
    return f"/api/projects/{normalized_project_id}/materials/{normalized_asset_id}/file"


def _build_material_cover_url(project_id: str, asset_id: str) -> str:
    normalized_project_id = str(project_id or "").strip()
    normalized_asset_id = str(asset_id or "").strip()
    return f"/api/projects/{normalized_project_id}/materials/{normalized_asset_id}/cover"


def _build_studio_audio_file_url(project_id: str, audio_id: str) -> str:
    normalized_project_id = str(project_id or "").strip()
    normalized_audio_id = str(audio_id or "").strip()
    return f"/api/projects/{normalized_project_id}/studio/audio/{normalized_audio_id}/file"


def _build_studio_voice_sample_file_url(project_id: str, voice_id: str) -> str:
    normalized_project_id = str(project_id or "").strip()
    normalized_voice_id = str(voice_id or "").strip()
    return f"/api/projects/{normalized_project_id}/studio/voices/{normalized_voice_id}/sample/file"


def _normalize_studio_character_view(value: Any) -> str:
    normalized = _normalize_material_text(value, limit=40).lower() or "front"
    if normalized in _PROJECT_STUDIO_CHARACTER_VIEWS:
        return normalized
    raise HTTPException(
        400,
        f"target_view must be one of {list(_PROJECT_STUDIO_CHARACTER_VIEWS)}",
    )


def _studio_character_view_label(view: str) -> str:
    return _PROJECT_STUDIO_CHARACTER_VIEW_LABELS.get(view, "参考图")


def _build_studio_character_reference_prompt(
    *,
    prompt: str,
    character_name: str,
    view: str,
    image_style: str,
    image_quality: str,
    has_reference_images: bool,
) -> str:
    view_label = _studio_character_view_label(view)
    normalized_prompt = _normalize_material_text(prompt, limit=6000)
    normalized_name = _normalize_material_text(character_name, limit=120) or "角色"
    normalized_style = _normalize_material_text(image_style, limit=80) or "auto"
    normalized_quality = _normalize_material_text(image_quality, limit=80) or "high"
    return (
        f"{normalized_prompt}\n\n"
        "补充要求：\n"
        f"- 当前角色名称：{normalized_name}\n"
        f"- 只生成单张{view_label}视角角色参考图，不要四宫格，不要多视图拼接。\n"
        f"- {'已提供角色参考图，请严格延续同一人物形象与服装细节。' if has_reference_images else '当前没有可用参考图，请仅基于提示词生成。'}\n"
        "- 画面里只保留同一个角色，不要多人，不要多头，不要肢体错位。\n"
        "- 保持角色服装、发型、年龄感、五官和整体设定一致。\n"
        "- 不要文字、水印、边框、logo。\n"
        f"- 风格偏好：{normalized_style}\n"
        f"- 质量要求：{normalized_quality}\n"
    ).strip()


def _save_studio_generated_image_asset(
    *,
    project_id: str,
    auth_payload: dict,
    artifact: dict[str, Any],
    title: str,
    summary: str,
    structured_content: dict[str, Any],
    metadata: dict[str, Any],
) -> ProjectMaterialAsset:
    preview_url = _normalize_material_url(artifact.get("preview_url"))
    content_url = _normalize_material_url(artifact.get("content_url")) or preview_url
    asset = ProjectMaterialAsset(
        id=project_material_store.new_id(),
        project_id=project_id,
        asset_type="image",
        group_type=_infer_material_group_type("image"),
        title=_normalize_material_text(title, limit=120) or "AI 角色参考图",
        summary=_normalize_material_text(summary, limit=1000),
        source_type="ai_generated",
        source_username=_normalize_material_text(auth_payload.get("sub"), limit=120),
        created_by=_normalize_material_text(auth_payload.get("sub"), limit=120),
        preview_url=preview_url or content_url,
        content_url=content_url or preview_url,
        mime_type=_normalize_material_text(
            artifact.get("mime_type")
            or _guess_material_artifact_mime_type(content_url or preview_url, asset_type="image"),
            limit=120,
        ),
        status="ready",
        structured_content=_normalize_material_mapping(structured_content),
        metadata=_normalize_material_mapping(metadata),
    )
    project_material_store.save(asset)
    return asset


def _resolve_studio_audio_storage_path(project_id: str, audio_id: str, file_name: str) -> Path | None:
    normalized_project_id = str(project_id or "").strip()
    normalized_audio_id = str(audio_id or "").strip()
    safe_file_name = _sanitize_material_filename(file_name, f"{normalized_audio_id}.bin")
    if not normalized_project_id or not normalized_audio_id or not safe_file_name:
        return None
    relative_path = Path(normalized_project_id) / "studio-audio" / normalized_audio_id / safe_file_name
    return (_project_material_file_root() / relative_path).resolve()


def _resolve_material_storage_path(storage_path: str) -> Path | None:
    if not storage_path:
        return None
    relative_path = Path(storage_path)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        return None
    return (_project_material_file_root() / relative_path).resolve()


def _resolve_material_file_path(asset: ProjectMaterialAsset) -> Path | None:
    storage_path = str((asset.metadata or {}).get("storage_path") or "").strip()
    return _resolve_material_storage_path(storage_path)


def _resolve_material_cover_path(asset: ProjectMaterialAsset) -> Path | None:
    storage_path = str((asset.metadata or {}).get("cover_storage_path") or "").strip()
    return _resolve_material_storage_path(storage_path)


def _delete_material_storage_path(storage_path: str) -> None:
    target_path = _resolve_material_storage_path(storage_path)
    if target_path is None or not target_path.exists():
        return
    root = _project_material_file_root().resolve()
    if root not in target_path.parents:
        return
    if target_path.is_file():
        target_path.unlink(missing_ok=True)
    parent = target_path.parent
    while parent != root and parent.exists():
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent


def _delete_material_file(asset: ProjectMaterialAsset) -> None:
    paths = {
        str((asset.metadata or {}).get("storage_path") or "").strip(),
        str((asset.metadata or {}).get("cover_storage_path") or "").strip(),
    }
    for storage_path in paths:
        if storage_path:
            _delete_material_storage_path(storage_path)


def _serialize_project_material_asset(asset: ProjectMaterialAsset) -> dict[str, Any]:
    payload = asdict(asset)
    payload["asset_type_label"] = _PROJECT_MATERIAL_ASSET_LABELS.get(asset.asset_type, asset.asset_type)
    payload["group_type_label"] = _PROJECT_MATERIAL_GROUP_LABELS.get(asset.group_type, asset.group_type)
    payload["status_label"] = _PROJECT_MATERIAL_STATUS_LABELS.get(asset.status, asset.status)
    return payload


def _serialize_project_studio_export_job(job: ProjectStudioExportJob) -> dict[str, Any]:
    payload = asdict(job)
    payload["status_label"] = _PROJECT_STUDIO_EXPORT_STATUS_LABELS.get(job.status, job.status)
    payload["export_format_label"] = _PROJECT_STUDIO_EXPORT_FORMAT_LABELS.get(
        job.export_format,
        job.export_format,
    )
    payload["source_type_label"] = _PROJECT_STUDIO_EXPORT_SOURCE_TYPE_LABELS.get(
        job.source_type,
        job.source_type or "作品记录",
    )
    payload["can_retry"] = job.status == "failed"
    payload["can_cancel"] = job.status in {"queued", "processing"}
    payload["can_resume"] = job.status == "draft" and job.source_type == "studio_draft"
    payload["can_delete"] = job.status not in {"queued", "processing"}
    return payload


def _filter_project_material_assets(
    items: list[ProjectMaterialAsset],
    *,
    group_type: str = "",
    asset_type: str = "",
    query: str = "",
) -> list[ProjectMaterialAsset]:
    normalized_group_type = str(group_type or "").strip().lower()
    normalized_asset_type = str(asset_type or "").strip().lower()
    normalized_query = str(query or "").strip().lower()
    result: list[ProjectMaterialAsset] = []
    for item in items:
        if normalized_group_type and item.group_type != normalized_group_type:
            continue
        if normalized_asset_type and item.asset_type != normalized_asset_type:
            continue
        if normalized_query:
            haystacks = [
                item.title,
                item.summary,
                item.source_message_id,
                item.source_chat_session_id,
                item.source_username,
                item.created_by,
            ]
            if not any(normalized_query in str(text or "").lower() for text in haystacks):
                continue
        result.append(item)
    return result


def _normalize_studio_draft_snapshot(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value in (None, ""):
        return {}
    raise HTTPException(400, "snapshot must be object")


def _extract_studio_draft_timeline_clips(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    clips = snapshot.get("timelineClips")
    if not isinstance(clips, list):
        return []
    return [item for item in clips if isinstance(item, dict)]


def _extract_studio_draft_timeline_duration_seconds(snapshot: dict[str, Any]) -> int:
    total = 0
    for clip in _extract_studio_draft_timeline_clips(snapshot):
        if clip.get("visible") is False:
            continue
        try:
            duration = int(round(float(clip.get("durationSeconds") or 0)))
        except (TypeError, ValueError):
            duration = 0
        if duration > 0:
            total += duration
    return max(0, total)


def _derive_studio_draft_title(value: Any, snapshot: dict[str, Any]) -> str:
    explicit = _normalize_material_text(value, limit=120)
    if explicit:
        return explicit
    script_draft = snapshot.get("scriptDraft")
    script_content = ""
    if isinstance(script_draft, dict):
        script_content = _normalize_material_text(script_draft.get("content"), limit=40)
    if script_content:
        return f"制作草稿 · {script_content[:24]}"
    return "短片制作草稿"


def _to_unique_string_list(values: Any, *, max_items: int = 100, max_item_len: int = 120) -> list[str]:
    if not isinstance(values, list):
        return []
    seen: set[str] = set()
    result: list[str] = []
    for item in values:
        text = str(item or "").strip()
        if not text:
            continue
        if len(text) > max_item_len:
            text = text[:max_item_len]
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
        if len(result) >= max_items:
            break
    return result


def _guess_material_image_mime_type(url: str, fallback: Any = "") -> str:
    preferred = str(fallback or "").strip().lower()
    if preferred.startswith("image/"):
        return preferred[:120]
    lower = str(url or "").lower()
    if lower.startswith("data:image/"):
        return lower.split(";", 1)[0].replace("data:", "", 1)[:120]
    if ".png" in lower:
        return "image/png"
    if ".jpg" in lower or ".jpeg" in lower:
        return "image/jpeg"
    if ".gif" in lower:
        return "image/gif"
    if ".webp" in lower:
        return "image/webp"
    if ".bmp" in lower:
        return "image/bmp"
    if ".svg" in lower:
        return "image/svg+xml"
    return "image/png"


def _guess_material_video_mime_type(url: str, fallback: Any = "") -> str:
    preferred = str(fallback or "").strip().lower()
    if preferred.startswith("video/"):
        return preferred[:120]
    lower = str(url or "").lower()
    if lower.startswith("data:video/"):
        return lower.split(";", 1)[0].replace("data:", "", 1)[:120]
    if ".mp4" in lower:
        return "video/mp4"
    if ".mov" in lower:
        return "video/quicktime"
    if ".m4v" in lower:
        return "video/x-m4v"
    if ".webm" in lower:
        return "video/webm"
    if ".avi" in lower:
        return "video/x-msvideo"
    if ".mkv" in lower:
        return "video/x-matroska"
    return "video/mp4"


def _guess_material_audio_mime_type(url: str, fallback: Any = "") -> str:
    preferred = str(fallback or "").strip().lower()
    if preferred.startswith("audio/"):
        return preferred[:120]
    lower = str(url or "").lower()
    if lower.startswith("data:audio/"):
        return lower.split(";", 1)[0].replace("data:", "", 1)[:120]
    if ".mp3" in lower:
        return "audio/mpeg"
    if ".wav" in lower:
        return "audio/wav"
    if ".m4a" in lower:
        return "audio/mp4"
    if ".aac" in lower:
        return "audio/aac"
    if ".ogg" in lower:
        return "audio/ogg"
    if ".flac" in lower:
        return "audio/flac"
    return "audio/mpeg"


def _guess_material_artifact_mime_type(url: str, fallback: Any = "", asset_type: str = "") -> str:
    hinted_asset_type = str(asset_type or "").strip().lower()
    preferred = str(fallback or "").strip().lower()
    if preferred.startswith(("image/", "video/", "audio/")):
        return preferred[:120]
    if hinted_asset_type == "video":
        return _guess_material_video_mime_type(url, fallback)
    if hinted_asset_type == "audio":
        return _guess_material_audio_mime_type(url, fallback)
    if hinted_asset_type == "image":
        return _guess_material_image_mime_type(url, fallback)
    lower = str(url or "").lower()
    if any(ext in lower for ext in (".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv")):
        return _guess_material_video_mime_type(url, fallback)
    if any(ext in lower for ext in (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac")):
        return _guess_material_audio_mime_type(url, fallback)
    return _guess_material_image_mime_type(url, fallback)


def _infer_material_artifact_asset_type(
    *,
    content_url: str,
    preview_url: str,
    mime_type: str = "",
    hinted_asset_type: str = "",
) -> str:
    hinted = str(hinted_asset_type or "").strip().lower()
    if hinted in _PROJECT_MATERIAL_ASSET_TYPES:
        return hinted
    normalized_mime = str(mime_type or "").strip().lower()
    if normalized_mime.startswith("video/"):
        return "video"
    if normalized_mime.startswith("audio/"):
        return "audio"
    if normalized_mime.startswith("image/"):
        return "image"
    combined = " ".join([str(content_url or "").lower(), str(preview_url or "").lower()])
    if any(ext in combined for ext in (".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv")):
        return "video"
    if any(ext in combined for ext in (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac")):
        return "audio"
    return "image"


def _normalize_chat_media_artifacts(values: Any) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        return []
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for index, item in enumerate(values, start=1):
        if not isinstance(item, dict):
            continue
        hinted_asset_type = _normalize_material_text(
            item.get("asset_type") or item.get("assetType") or item.get("type") or item.get("kind"),
            limit=20,
        ).lower()
        mime_type = _normalize_material_text(
            item.get("mime_type")
            or item.get("mimeType")
            or item.get("content_type")
            or item.get("contentType")
            or item.get("media_type")
            or item.get("mediaType"),
            limit=120,
        )
        preview_url = _normalize_material_url(
            item.get("preview_url")
            or item.get("previewUrl")
            or item.get("thumbnail_url")
            or item.get("thumbnailUrl")
            or item.get("poster_url")
            or item.get("posterUrl")
            or item.get("cover_url")
            or item.get("coverUrl"),
        )
        content_url = _normalize_material_url(
            item.get("content_url")
            or item.get("contentUrl")
            or item.get("image_url")
            or item.get("imageUrl")
            or item.get("video_url")
            or item.get("videoUrl")
            or item.get("url"),
        )
        asset_type = _infer_material_artifact_asset_type(
            content_url=content_url,
            preview_url=preview_url,
            mime_type=mime_type,
            hinted_asset_type=hinted_asset_type,
        )
        if asset_type == "video":
            if not content_url:
                content_url = preview_url
            if not preview_url:
                preview_url = content_url
        else:
            if not preview_url:
                preview_url = content_url
            if not content_url:
                content_url = preview_url
        if not preview_url:
            preview_url = content_url
        if not content_url:
            content_url = preview_url
        if not preview_url and not content_url:
            continue
        artifact_key = f"{asset_type}||{preview_url}||{content_url}"
        if artifact_key in seen:
            continue
        seen.add(artifact_key)
        metadata = _normalize_material_mapping(item.get("metadata"))
        title_fallback = "AI 生成视频" if asset_type == "video" else f"AI 生成图片 #{index}"
        result.append(
            {
                "asset_type": asset_type,
                "title": _normalize_material_text(
                    item.get("title") or title_fallback,
                    limit=120,
                ) or title_fallback,
                "summary": _normalize_material_text(item.get("summary"), limit=1000),
                "preview_url": preview_url,
                "content_url": content_url,
                "mime_type": _guess_material_artifact_mime_type(
                    content_url or preview_url,
                    mime_type,
                    asset_type,
                ),
                "metadata": metadata,
            }
        )
    return result


def _merge_chat_media_artifacts(
    current: list[dict[str, Any]] | None,
    incoming: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    return _normalize_chat_media_artifacts([*(current or []), *(incoming or [])])


def _collect_chat_artifact_urls(
    values: list[dict[str, Any]] | None,
    *,
    asset_type: str,
) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for item in values or []:
        if str((item or {}).get("asset_type") or "").strip().lower() != asset_type:
            continue
        candidates = (
            [str((item or {}).get("content_url") or "").strip()]
            if asset_type == "video"
            else [
                str((item or {}).get("preview_url") or "").strip(),
                str((item or {}).get("content_url") or "").strip(),
            ]
        )
        for candidate in candidates:
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            urls.append(candidate)
    return urls


def _build_generated_media_answer(artifacts: list[dict[str, Any]] | None) -> str:
    normalized_artifacts = _normalize_chat_media_artifacts(artifacts)
    image_count = sum(
        1 for item in normalized_artifacts if str(item.get("asset_type") or "").strip().lower() == "image"
    )
    video_count = sum(
        1 for item in normalized_artifacts if str(item.get("asset_type") or "").strip().lower() == "video"
    )
    if image_count and video_count:
        return f"已生成 {image_count} 张图片和 {video_count} 个视频，请查看下方结果。"
    if image_count:
        return f"已生成 {image_count} 张图片，请查看下方结果。"
    if video_count:
        return f"已生成 {video_count} 个视频，请查看下方结果。"
    return "模型未返回有效媒体结果。"


def _resolve_provider_model_parameter_mode(
    llm_service: Any,
    *,
    provider_mode: str,
    selected_provider: dict[str, Any],
    model_name: str,
) -> str:
    if str(provider_mode or "").strip().lower() != "provider":
        return "text"
    model_config = llm_service.get_model_config(selected_provider, model_name) or {}
    parameter_mode = str(model_config.get("chat_parameter_mode") or "text").strip().lower()
    return parameter_mode if parameter_mode in {"image", "video"} else "text"


async def _generate_project_chat_media_done_payload(
    *,
    llm_service: Any,
    auth_payload: dict,
    project_id: str,
    username: str,
    chat_session_id: str,
    assistant_message_id: str,
    effective_user_message: str,
    selected_employee_ids: list[str],
    provider_id: str,
    model_name: str,
    runtime_settings: dict[str, Any],
    memory_source: str,
    allow_requirement_record: bool = True,
) -> dict[str, Any]:
    artifacts = _normalize_chat_media_artifacts(
        await llm_service.generate_media_artifacts(
            provider_id,
            model_name,
            effective_user_message,
            owner_username=username,
            include_all=is_admin_like(auth_payload),
            image_size=_resolve_project_chat_image_size(
                runtime_settings.get("image_resolution"),
                runtime_settings.get("image_aspect_ratio"),
            ),
            video_aspect_ratio=str(runtime_settings.get("video_aspect_ratio") or "").strip(),
            video_duration_seconds=int(runtime_settings.get("video_duration_seconds") or 0) or None,
        )
    )
    if not artifacts:
        raise RuntimeError("模型未返回有效媒体结果")
    _save_chat_media_artifacts_to_materials(
        project_id=project_id,
        username=username,
        chat_session_id=chat_session_id,
        source_message_id=assistant_message_id,
        artifacts=artifacts,
    )
    images = _collect_chat_artifact_urls(artifacts, asset_type="image")
    videos = _collect_chat_artifact_urls(artifacts, asset_type="video")
    content = _build_generated_media_answer(artifacts)
    _append_chat_record(
        project_id=project_id,
        username=username,
        role="assistant",
        content=content,
        message_id=assistant_message_id,
        chat_session_id=chat_session_id,
        images=images,
        videos=videos,
    )
    done_payload = _build_project_chat_done_payload(
        content=content,
        project_id=project_id,
        username=username,
        chat_session_id=chat_session_id,
        provider_id=provider_id,
        model_name=model_name,
        artifacts=artifacts,
        successful_tool_names=["generate_media_artifacts"],
    )
    _save_project_chat_memory_snapshot(
        project_id=project_id,
        user_message=effective_user_message,
        answer=content,
        chat_session_id=chat_session_id,
        task_tree_payload=done_payload.get("history_task_tree") or done_payload.get("task_tree"),
        selected_employee_ids=selected_employee_ids,
        source=memory_source,
        allow_requirement_record=allow_requirement_record,
    )
    return done_payload


def _save_chat_media_artifacts_to_materials(
    *,
    project_id: str,
    username: str,
    chat_session_id: str,
    source_message_id: str,
    artifacts: list[dict[str, Any]] | None,
    tool_name: str = "",
) -> list[ProjectMaterialAsset]:
    normalized_artifacts = _normalize_chat_media_artifacts(artifacts)
    if not normalized_artifacts:
        return []
    existing_items = project_material_store.list_by_project(project_id)
    existing_keys: set[str] = set()
    for item in existing_items:
        metadata = item.metadata if isinstance(item.metadata, dict) else {}
        artifact_key = str(metadata.get("artifact_key") or "").strip()
        if artifact_key:
            existing_keys.add(artifact_key)
    saved: list[ProjectMaterialAsset] = []
    for artifact in normalized_artifacts:
        asset_type = _normalize_material_asset_type(artifact.get("asset_type") or "image")
        preview_url = str(artifact.get("preview_url") or "").strip()
        content_url = str(artifact.get("content_url") or "").strip()
        artifact_key = "||".join(
            [
                asset_type,
                str(source_message_id or "").strip(),
                str(chat_session_id or "").strip(),
                preview_url,
                content_url,
            ]
        )
        if artifact_key in existing_keys:
            continue
        metadata = {
            **_normalize_material_mapping(artifact.get("metadata")),
            "artifact_key": artifact_key,
            "artifact_source": "project-chat-auto-artifact",
            "tool_name": str(tool_name or "").strip(),
        }
        asset = ProjectMaterialAsset(
            id=project_material_store.new_id(),
            project_id=project_id,
            asset_type=asset_type,
            group_type=_infer_material_group_type(asset_type),
            title=_normalize_material_text(
                artifact.get("title") or ("AI 生成视频" if asset_type == "video" else "AI 生成图片"),
                limit=120,
            ) or ("AI 生成视频" if asset_type == "video" else "AI 生成图片"),
            summary=_normalize_material_text(artifact.get("summary"), limit=1000),
            source_type="ai_generated",
            source_message_id=_normalize_material_text(source_message_id, limit=120),
            source_chat_session_id=_normalize_material_text(chat_session_id, limit=120),
            source_username=_normalize_material_text(username, limit=120),
            created_by=_normalize_material_text(username, limit=120),
            preview_url=_normalize_material_url(preview_url),
            content_url=_normalize_material_url(content_url),
            mime_type=_normalize_material_text(
                artifact.get("mime_type")
                or _guess_material_artifact_mime_type(content_url or preview_url, asset_type=asset_type),
                limit=120,
            ),
            status="ready",
            structured_content={},
            metadata=metadata,
        )
        project_material_store.save(asset)
        existing_keys.add(artifact_key)
        saved.append(asset)
    return saved


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


def _coerce_int(value: Any, default: int, *, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(min_value, min(max_value, parsed))


def _coerce_float(value: Any, default: float, *, min_value: float, max_value: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(min_value, min(max_value, parsed))


def _normalize_project_chat_settings(raw: dict[str, Any] | None) -> dict[str, Any]:
    source = raw if isinstance(raw, dict) else {}
    settings = dict(_PROJECT_CHAT_SETTINGS_DEFAULTS)
    settings["image_resolution"] = get_chat_parameter_default_value("image_resolution")
    settings["image_aspect_ratio"] = get_chat_parameter_default_value("image_aspect_ratio")
    settings["image_style"] = get_chat_parameter_default_value("image_style")
    settings["image_quality"] = get_chat_parameter_default_value("image_quality")
    settings["video_aspect_ratio"] = get_chat_parameter_default_value("video_aspect_ratio")
    settings["video_style"] = get_chat_parameter_default_value("video_style")
    settings["video_duration_seconds"] = get_chat_parameter_default_value("video_duration_seconds")
    settings["video_motion_strength"] = get_chat_parameter_default_value("video_motion_strength")
    settings["chat_mode"] = "system"
    sandbox_mode_explicit = _coerce_bool(
        source.get(
            "connector_sandbox_mode_explicit",
            source.get(
                "external_agent_sandbox_mode_explicit",
                settings["connector_sandbox_mode_explicit"],
            ),
        ),
        settings["connector_sandbox_mode_explicit"],
    )
    sandbox_mode = str(
        source.get(
            "connector_sandbox_mode",
            source.get(
                "external_agent_sandbox_mode",
                settings["connector_sandbox_mode"],
            ),
        )
        or ""
    ).strip().lower()
    normalized_sandbox_mode = sandbox_mode if sandbox_mode in {"read-only", "workspace-write"} else settings["connector_sandbox_mode"]
    if normalized_sandbox_mode == "read-only" and not sandbox_mode_explicit:
        normalized_sandbox_mode = settings["connector_sandbox_mode"]
    settings["connector_sandbox_mode"] = normalized_sandbox_mode
    settings["connector_sandbox_mode_explicit"] = sandbox_mode_explicit
    settings["local_connector_id"] = str(source.get("local_connector_id", settings["local_connector_id"]) or "").strip()
    settings["connector_workspace_path"] = str(source.get("connector_workspace_path", settings["connector_workspace_path"]) or "").strip()
    settings["selected_employee_id"] = str(source.get("selected_employee_id", settings["selected_employee_id"]) or "").strip()
    settings["selected_employee_ids"] = _to_unique_string_list(source.get("selected_employee_ids"), max_items=200, max_item_len=120)
    if not settings["selected_employee_ids"] and settings["selected_employee_id"]:
        settings["selected_employee_ids"] = [settings["selected_employee_id"]]
    coordination_mode = str(
        source.get(
            "employee_coordination_mode",
            settings["employee_coordination_mode"],
        )
        or ""
    ).strip().lower()
    settings["employee_coordination_mode"] = (
        coordination_mode
        if coordination_mode in {"auto", "manual"}
        else settings["employee_coordination_mode"]
    )
    settings["provider_id"] = str(source.get("provider_id", settings["provider_id"]) or "").strip()
    settings["model_name"] = str(source.get("model_name", settings["model_name"]) or "").strip()
    settings["temperature"] = _coerce_float(source.get("temperature"), settings["temperature"], min_value=0.0, max_value=2.0)
    settings["max_tokens"] = _coerce_int(source.get("max_tokens"), settings["max_tokens"], min_value=128, max_value=8192)
    settings["system_prompt"] = str(source.get("system_prompt", settings["system_prompt"]) or "").strip()[:4000]
    settings["auto_use_tools"] = _coerce_bool(source.get("auto_use_tools"), settings["auto_use_tools"])
    settings["enabled_project_tool_names"] = _to_unique_string_list(source.get("enabled_project_tool_names"), max_items=200, max_item_len=160)
    settings["tool_priority"] = _to_unique_string_list(source.get("tool_priority"), max_items=200, max_item_len=160)
    settings["max_tool_calls_per_round"] = _coerce_int(source.get("max_tool_calls_per_round"), settings["max_tool_calls_per_round"], min_value=1, max_value=30)
    settings["max_loop_rounds"] = _coerce_int(source.get("max_loop_rounds"), settings["max_loop_rounds"], min_value=1, max_value=60)
    settings["max_tool_rounds"] = _coerce_int(source.get("max_tool_rounds"), settings["max_tool_rounds"], min_value=1, max_value=30)
    settings["repeated_tool_call_threshold"] = _coerce_int(source.get("repeated_tool_call_threshold"), settings["repeated_tool_call_threshold"], min_value=1, max_value=10)
    settings["tool_only_threshold"] = _coerce_int(source.get("tool_only_threshold"), settings["tool_only_threshold"], min_value=1, max_value=10)
    strategy = str(source.get("tool_budget_strategy", settings["tool_budget_strategy"]) or "").strip().lower()
    settings["tool_budget_strategy"] = strategy if strategy in {"stop", "finalize"} else settings["tool_budget_strategy"]
    settings["history_limit"] = _coerce_int(source.get("history_limit"), settings["history_limit"], min_value=1, max_value=50)
    settings["upload_file_limit"] = _coerce_int(source.get("upload_file_limit"), settings["upload_file_limit"], min_value=1, max_value=20)
    settings["max_file_size_mb"] = _coerce_int(source.get("max_file_size_mb"), settings["max_file_size_mb"], min_value=1, max_value=100)
    settings["doc_max_chars_per_file"] = _coerce_int(source.get("doc_max_chars_per_file"), settings["doc_max_chars_per_file"], min_value=100, max_value=20000)
    settings["doc_max_chars_total"] = _coerce_int(source.get("doc_max_chars_total"), settings["doc_max_chars_total"], min_value=500, max_value=100000)
    settings["allowed_file_types"] = _to_unique_string_list(source.get("allowed_file_types"), max_items=40, max_item_len=20)
    settings["high_risk_tool_confirm"] = _coerce_bool(source.get("high_risk_tool_confirm"), settings["high_risk_tool_confirm"])
    settings["tool_timeout_sec"] = _coerce_int(source.get("tool_timeout_sec"), settings["tool_timeout_sec"], min_value=1, max_value=600)
    settings["tool_retry_count"] = _coerce_int(source.get("tool_retry_count"), settings["tool_retry_count"], min_value=0, max_value=5)
    style = str(source.get("answer_style", settings["answer_style"]) or "").strip().lower()
    settings["answer_style"] = style if style in {"concise", "balanced", "detailed"} else settings["answer_style"]
    settings["prefer_conclusion_first"] = _coerce_bool(source.get("prefer_conclusion_first"), settings["prefer_conclusion_first"])
    settings["task_tree_enabled"] = _coerce_bool(source.get("task_tree_enabled"), settings["task_tree_enabled"])
    settings["task_tree_auto_generate"] = _coerce_bool(
        source.get("task_tree_auto_generate"),
        settings["task_tree_auto_generate"],
    )
    settings["image_resolution"] = normalize_chat_parameter_value(
        "image_resolution",
        source.get("image_resolution", settings["image_resolution"]),
    )
    settings["image_aspect_ratio"] = normalize_chat_parameter_value(
        "image_aspect_ratio",
        source.get("image_aspect_ratio", settings["image_aspect_ratio"]),
    )
    settings["image_generate_four_views"] = _coerce_bool(
        source.get("image_generate_four_views"),
        settings["image_generate_four_views"],
    )
    settings["image_style"] = normalize_chat_parameter_value(
        "image_style",
        source.get("image_style", settings["image_style"]),
    )
    settings["image_quality"] = normalize_chat_parameter_value(
        "image_quality",
        source.get("image_quality", settings["image_quality"]),
    )
    settings["video_aspect_ratio"] = normalize_chat_parameter_value(
        "video_aspect_ratio",
        source.get("video_aspect_ratio", settings["video_aspect_ratio"]),
    )
    settings["video_style"] = normalize_chat_parameter_value(
        "video_style",
        source.get("video_style", settings["video_style"]),
    )
    settings["video_duration_seconds"] = normalize_chat_parameter_value(
        "video_duration_seconds",
        source.get("video_duration_seconds", settings["video_duration_seconds"]),
    )
    settings["video_motion_strength"] = normalize_chat_parameter_value(
        "video_motion_strength",
        source.get("video_motion_strength", settings["video_motion_strength"]),
    )
    return settings


def _public_project_chat_settings(raw: dict[str, Any] | None) -> dict[str, Any]:
    return _normalize_project_chat_settings(raw)


def _merge_project_chat_settings_overrides(
    persisted_settings: dict[str, Any] | None,
    *,
    local_connector_id: str = "",
    connector_workspace_path: str = "",
) -> dict[str, Any]:
    merged = dict(_normalize_project_chat_settings(persisted_settings))
    normalized_connector_id = str(local_connector_id or "").strip()
    normalized_workspace_path = str(connector_workspace_path or "").strip()
    if normalized_connector_id:
        merged["local_connector_id"] = normalized_connector_id
    if normalized_workspace_path:
        merged["connector_workspace_path"] = normalized_workspace_path
    return _normalize_project_chat_settings(merged)


def _sync_feedback_project_flag(project_id: str, enabled: bool) -> None:
    try:
        get_feedback_service().update_project_config(project_id, enabled=enabled)
    except Exception:
        # 反馈升级能力在非 PG/禁用场景可能不可用；项目主流程不阻断。
        return


def _normalize_domain(value: str) -> str:
    return str(value or "").strip().lower()


def _resolve_employee_rule_bindings(employee: Any) -> list[dict[str, str]]:
    bindings: list[dict[str, str]] = []
    rule_ids = [str(item or "").strip() for item in (getattr(employee, "rule_ids", []) or []) if str(item or "").strip()]
    if rule_ids:
        seen_ids: set[str] = set()
        for rule_id in rule_ids:
            if rule_id in seen_ids:
                continue
            seen_ids.add(rule_id)
            rule = rule_store.get(rule_id)
            if rule is None:
                bindings.append({"id": rule_id, "title": f"{rule_id}（规则不存在）", "domain": ""})
                continue
            bindings.append(
                {
                    "id": str(getattr(rule, "id", "") or ""),
                    "title": str(getattr(rule, "title", "") or ""),
                    "domain": str(getattr(rule, "domain", "") or ""),
                }
            )
        return bindings

    domains = {_normalize_domain(item) for item in (getattr(employee, "rule_domains", []) or []) if str(item or "").strip()}
    if not domains:
        return bindings
    seen_ids: set[str] = set()
    for rule in rule_store.list_all():
        domain = _normalize_domain(getattr(rule, "domain", ""))
        if not domain or domain not in domains:
            continue
        rule_id = str(getattr(rule, "id", "") or "").strip()
        if not rule_id or rule_id in seen_ids:
            continue
        seen_ids.add(rule_id)
        bindings.append(
            {
                "id": rule_id,
                "title": str(getattr(rule, "title", "") or ""),
                "domain": str(getattr(rule, "domain", "") or ""),
            }
        )
    return bindings


def _resolve_project_ui_rule_bindings(
    project: ProjectConfig | None,
    *,
    include_content: bool = False,
) -> list[dict[str, str]]:
    if project is None:
        return []
    bindings: list[dict[str, str]] = []
    for rule_id in _normalize_project_ui_rule_ids(getattr(project, "ui_rule_ids", []) or []):
        rule = rule_store.get(rule_id)
        if rule is None:
            payload = {
                "id": rule_id,
                "title": f"{rule_id}（规则不存在）",
                "domain": "",
            }
            if include_content:
                payload["content"] = ""
            bindings.append(payload)
            continue
        payload = {
            "id": str(getattr(rule, "id", "") or ""),
            "title": str(getattr(rule, "title", "") or ""),
            "domain": str(getattr(rule, "domain", "") or ""),
        }
        if include_content:
            payload["content"] = str(getattr(rule, "content", "") or "")
        bindings.append(payload)
    return bindings


def _normalize_project_experience_rule_ids(values: Any) -> list[str]:
    return _normalize_project_ui_rule_ids(values)


def _normalize_experience_rule_scope(value: Any) -> str:
    normalized = _normalize_project_record_token(value, limit=40).lower()
    if normalized == _EXPERIENCE_SCOPE_PROJECT:
        return _EXPERIENCE_SCOPE_PROJECT
    return _EXPERIENCE_SCOPE_DEVELOPMENT


def _experience_rule_domain_for_scope(scope: str) -> str:
    return (
        _PROJECT_EXPERIENCE_RULE_DOMAIN
        if _normalize_experience_rule_scope(scope) == _EXPERIENCE_SCOPE_PROJECT
        else _DEVELOPMENT_EXPERIENCE_RULE_DOMAIN
    )


def _experience_rule_title_prefix_for_scope(scope: str) -> str:
    return (
        _PROJECT_EXPERIENCE_RULE_TITLE_PREFIX
        if _normalize_experience_rule_scope(scope) == _EXPERIENCE_SCOPE_PROJECT
        else _DEVELOPMENT_EXPERIENCE_RULE_TITLE_PREFIX
    )


def _normalize_experience_rule_title(title: str, scope: str) -> str:
    raw = str(title or "").strip()
    for prefix in (
        _PROJECT_EXPERIENCE_RULE_TITLE_PREFIX,
        _DEVELOPMENT_EXPERIENCE_RULE_TITLE_PREFIX,
    ):
        if raw.startswith(prefix):
            raw = raw[len(prefix) :].strip()
            break
    raw = raw or (
        "项目经验"
        if _normalize_experience_rule_scope(scope) == _EXPERIENCE_SCOPE_PROJECT
        else "开发经验"
    )
    return f"{_experience_rule_title_prefix_for_scope(scope)}{raw}"


def _strip_experience_rule_title_prefix(title: str) -> str:
    raw = str(title or "").strip()
    for prefix in (
        _PROJECT_EXPERIENCE_RULE_TITLE_PREFIX,
        _DEVELOPMENT_EXPERIENCE_RULE_TITLE_PREFIX,
    ):
        if raw.startswith(prefix):
            return raw[len(prefix) :].strip() or raw
    return raw


def _extract_experience_rule_preview(content: str, *, limit: int = 140) -> str:
    lines = [
        str(line or "").strip()
        for line in str(content or "").splitlines()
        if str(line or "").strip()
    ]
    for line in lines:
        if line.startswith("#") or line.startswith("- 主题键:") or line.startswith("- 关键词:"):
            continue
        if line.startswith("- "):
            text = line[2:].strip()
            if text:
                return text[:limit]
        return line[:limit]
    return ""


def _resolve_project_experience_rule_bindings(
    project: ProjectConfig | None,
    *,
    include_content: bool = False,
) -> list[dict[str, str]]:
    if project is None:
        return []
    bindings: list[dict[str, str]] = []
    for rule_id in _normalize_project_experience_rule_ids(
        getattr(project, "experience_rule_ids", []) or []
    ):
        rule = rule_store.get(rule_id)
        if rule is None:
            payload = {
                "id": rule_id,
                "title": f"{rule_id}（规则不存在）",
                "domain": _PROJECT_EXPERIENCE_RULE_DOMAIN,
                "preview": "",
            }
            if include_content:
                payload["content"] = ""
            bindings.append(payload)
            continue
        content = str(getattr(rule, "content", "") or "")
        experience_scope = _infer_experience_rule_scope(rule)
        payload = {
            "id": str(getattr(rule, "id", "") or ""),
            "title": str(getattr(rule, "title", "") or ""),
            "domain": str(getattr(rule, "domain", "") or "") or _experience_rule_domain_for_scope(experience_scope),
            "preview": _extract_experience_rule_preview(content),
            "experience_scope": experience_scope,
            "system_source": (
                "project_experience"
                if experience_scope == _EXPERIENCE_SCOPE_PROJECT
                else "development_experience"
            ),
        }
        if include_content:
            payload["content"] = content
        bindings.append(payload)
    return bindings


def _collect_rule_domains(rule_bindings: list[dict[str, str]]) -> list[str]:
    seen: set[str] = set()
    domains: list[str] = []
    for item in rule_bindings:
        domain = str(item.get("domain", "") or "").strip()
        key = _normalize_domain(domain)
        if not key or key in seen:
            continue
        seen.add(key)
        domains.append(domain)
    return domains


def _project_member_details(project_id: str) -> list[dict]:
    items: list[dict] = []
    for member in project_store.list_members(project_id):
        employee = employee_store.get(member.employee_id)
        if employee is None:
            continue
        skill_items = []
        for skill_id in employee.skills or []:
            skill = skill_store.get(skill_id)
            entry_count, sample_entries = _scan_skill_entries(skill) if skill else (0, [])
            skill_items.append(
                {
                    "id": skill_id,
                    "name": getattr(skill, "name", "") or skill_id,
                    "description": getattr(skill, "description", "") if skill else "",
                    "entry_count": entry_count,
                    "sample_entries": sample_entries,
                }
            )
        rule_bindings = _resolve_employee_rule_bindings(employee)
        items.append(
            {
                "member": member,
                "employee": employee,
                "skills": skill_items,
                "rule_bindings": rule_bindings,
            }
        )
    return items


def _scan_skill_entries(skill) -> tuple[int, list[str]]:
    package_dir = str(getattr(skill, "package_dir", "") or "").strip() if skill else ""
    if not package_dir:
        return 0, []
    package_path = Path(package_dir)
    if not package_path.is_absolute():
        package_path = get_project_root() / package_path
    package_path = package_path.resolve()
    if not package_path.exists() or not package_path.is_dir():
        return 0, []

    entries: list[str] = []
    for base_dir in ("tools", "scripts"):
        root = package_path / base_dir
        if not root.exists():
            continue
        for file in sorted(root.rglob("*")):
            if not file.is_file() or file.suffix.lower() not in {".py", ".js"}:
                continue
            entries.append(file.relative_to(package_path).as_posix())
    return len(entries), entries[:8]


def _format_manual_skill_item(
    skill_id: str,
    name: str,
    description: str,
    *,
    entry_count: int = 0,
    sample_entries: list[str] | None = None,
    list_tool_name: str,
    invoke_tool_name: str,
    employee_id: str = "",
) -> str:
    normalized_skill_id = str(skill_id or "").strip() or str(name or "").strip() or "unknown-skill"
    normalized_name = str(name or "").strip() or normalized_skill_id
    normalized_description = str(description or "").strip() or "未提供描述"
    entry_examples = "、".join(f"`{item}`" for item in (sample_entries or []) if str(item or "").strip()) or "无"
    match_parts = []
    if employee_id:
        match_parts.append(f'`employee_id="{employee_id}"`')
    match_parts.append(f'`skill_id="{normalized_skill_id}"`')
    invoke_args = [f'"tool_name": "<从 {list_tool_name} 返回结果里选出的 tool_name>"']
    if employee_id:
        invoke_args.append(f'"employee_id": "{employee_id}"')
    invoke_args.append('"args": { "...": "..." }')
    invoke_example = ", ".join(invoke_args)
    return (
        f"#### {normalized_name} (`{normalized_skill_id}`)\n"
        f"- 描述：{normalized_description}\n"
        f"- 可执行入口数量：{entry_count}\n"
        f"- 可执行入口示例：{entry_examples}\n"
        f"- MCP 查看详情：先调用 `{list_tool_name}`，在返回结果中按 {' + '.join(match_parts)} 匹配该技能对应的 `tool_name`、`entry_name`、`description`\n"
        f"- MCP 调用示例：`{invoke_tool_name}({{{invoke_example}}})`\n"
        "- 手册写作要求：必须补出“何时使用这个技能”的触发条件，并基于上面的 MCP 查询/调用路径给出至少 1 个最小使用案例"
    )


def _format_manual_rule_index(
    rule_bindings: list[dict[str, str]],
    *,
    query_tool_name: str,
    employee_id: str = "",
) -> str:
    grouped: dict[str, list[dict[str, str]]] = {}
    for item in rule_bindings:
        domain = str(item.get("domain", "") or "").strip() or "未分类"
        grouped.setdefault(domain, []).append(item)
    if not grouped:
        return "无"

    sections: list[str] = []
    for domain in sorted(grouped):
        items = grouped[domain]
        lines = [
            f"- {str(rule.get('title', '') or '').strip() or str(rule.get('id', '') or '').strip() or '未命名规则'} (`{str(rule.get('id', '') or '').strip() or 'unknown-rule'}`)"
            for rule in items
        ]
        query_parts = ['keyword="<规则标题关键词>"']
        if employee_id:
            query_parts.append(f'employee_id="{employee_id}"')
        sections.append(
            "\n".join(
                [
                    f"#### {domain}",
                    *lines,
                    (
                        f"- MCP 获取详情：调用 `{query_tool_name}({', '.join(query_parts)})`，"
                        "再以返回结果中的 `id`、`title`、`content` 作为最终依据"
                    ),
                ]
            )
        )
    return "\n\n".join(sections)


def _format_rule_domain_summary(rule_bindings: list[dict[str, str]]) -> str:
    grouped: dict[str, list[dict[str, str]]] = {}
    for item in rule_bindings:
        domain = str(item.get("domain", "") or "").strip() or "未分类"
        grouped.setdefault(domain, []).append(item)
    if not grouped:
        return "无"

    lines: list[str] = []
    for domain in sorted(grouped):
        items = grouped[domain]
        labels = [
            f"{str(rule.get('title', '') or '').strip() or str(rule.get('id', '') or '').strip() or '未命名规则'} (`{str(rule.get('id', '') or '').strip() or 'unknown-rule'}`)"
            for rule in items
        ]
        lines.append(f"- {domain}：{'；'.join(labels)}")
    return "\n".join(lines)


def _ensure_permission(auth_payload: dict, permission_key: str) -> None:
    role_ids = get_auth_role_ids(auth_payload)
    role_id = role_ids[0] if role_ids else ""
    permissions = resolve_role_ids_permissions(role_ids)
    if not has_permission(permissions, permission_key, role_id=role_id):
        raise HTTPException(403, f"Permission denied: {permission_key}")


def _has_permission(auth_payload: dict, permission_key: str) -> bool:
    role_ids = get_auth_role_ids(auth_payload)
    role_id = role_ids[0] if role_ids else ""
    permissions = resolve_role_ids_permissions(role_ids)
    return has_permission(permissions, permission_key, role_id=role_id)


def _ensure_any_permission(auth_payload: dict, permission_keys: list[str]) -> None:
    role_ids = get_auth_role_ids(auth_payload)
    role_id = role_ids[0] if role_ids else ""
    permissions = resolve_role_ids_permissions(role_ids)
    if any(has_permission(permissions, key, role_id=role_id) for key in permission_keys):
        return
    raise HTTPException(403, f"Permission denied: {permission_keys}")


def _project_chat_employee_candidates(project_id: str) -> list[dict[str, Any]]:
    from services.dynamic_mcp_runtime import list_project_member_profiles_runtime

    profiles = list_project_member_profiles_runtime(
        project_id,
        include_disabled=False,
        include_missing=False,
        rule_limit=30,
    )
    candidates: list[dict[str, Any]] = []
    for item in profiles:
        candidates.append(
            {
                "id": str(item.get("id") or item.get("employee_id") or ""),
                "name": str(item.get("name") or item.get("employee_name") or ""),
                "description": str(item.get("description") or ""),
                "role": str(item.get("role") or "member"),
                "enabled": bool(item.get("enabled", True)),
                "skills": list(item.get("skills") or []),
                "skill_names": list(item.get("skill_names") or []),
                "rule_bindings": list(item.get("rule_bindings") or []),
                "tone": str(item.get("tone") or ""),
                "verbosity": str(item.get("verbosity") or ""),
                "language": str(item.get("language") or ""),
                "mcp_enabled": bool(item.get("mcp_enabled", False)),
                "feedback_upgrade_enabled": bool(item.get("feedback_upgrade_enabled", False)),
            }
        )
    return candidates


def _resolve_project_chat_employee(project_id: str, expected_employee_id: str = "") -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    candidates = _project_chat_employee_candidates(project_id)
    if not candidates:
        return None, []
    expected = str(expected_employee_id or "").strip()
    if expected:
        matched = next((item for item in candidates if item["id"] == expected), None)
        if matched is not None:
            return matched, candidates
        # 项目聊天设置是项目级共享配置。多人协作时，某个用户删除/禁用成员后，
        # 其他用户本地或项目设置里残留的 selected_employee_id 不应直接打断整轮对话。
        return None, candidates
    # 未显式指定执行员工时，不做后端“智能默认选人”。
    # 由模型在项目可用工具/员工能力范围内自行决策。
    return None, candidates


def _resolve_project_chat_employees(
    project_id: str,
    expected_employee_ids: list[str] | None = None,
    expected_employee_id: str = "",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates = _project_chat_employee_candidates(project_id)
    if not candidates:
        return [], []
    by_id = {str(item.get("id") or ""): item for item in candidates if str(item.get("id") or "")}
    expected_list = [str(item or "").strip() for item in (expected_employee_ids or []) if str(item or "").strip()]
    if not expected_list:
        single = str(expected_employee_id or "").strip()
        if single:
            expected_list = [single]
    if not expected_list:
        return [], candidates
    selected: list[dict[str, Any]] = []
    missing: list[str] = []
    seen: set[str] = set()
    for employee_id in expected_list:
        if employee_id in seen:
            continue
        seen.add(employee_id)
        item = by_id.get(employee_id)
        if item is not None:
            selected.append(item)
            continue
        missing.append(employee_id)
    # 对于多人共享的项目聊天配置，失效成员自动忽略并回退。
    # 这样不会因为某个残留 employee_id 直接让整个聊天入口不可用。
    return selected, candidates


def _cleanup_project_chat_employee_selection(project_id: str, employee_id: str) -> bool:
    pid = str(project_id or "").strip()
    eid = str(employee_id or "").strip()
    if not pid or not eid:
        return False
    project = project_store.get(pid)
    if project is None:
        return False
    chat_settings = dict(getattr(project, "chat_settings", {}) or {})
    selected_ids = [
        str(item or "").strip()
        for item in (chat_settings.get("selected_employee_ids") or [])
        if str(item or "").strip()
    ]
    selected_id = str(chat_settings.get("selected_employee_id") or "").strip()
    next_selected_ids = [item for item in selected_ids if item != eid]
    next_selected_id = "" if selected_id == eid else selected_id
    if next_selected_id and next_selected_id not in next_selected_ids:
        next_selected_ids.append(next_selected_id)
    if next_selected_ids == selected_ids and next_selected_id == selected_id:
        return False
    chat_settings["selected_employee_ids"] = next_selected_ids
    chat_settings["selected_employee_id"] = next_selected_id
    project.chat_settings = chat_settings
    project.updated_at = _now_iso()
    project_store.save(project)
    return True


def _pick_chat_provider(
    provider_id: str,
    auth_payload: dict,
    *,
    include_all_providers: bool = False,
) -> tuple[dict, list[dict]]:
    providers = list_visible_chat_providers(
        auth_payload,
        include_all_providers=include_all_providers,
    )
    selected_provider, providers, _ = pick_provider_from_candidates(provider_id, providers)
    return selected_provider, providers


async def _resolve_provider_runtime_target(
    provider_id: str,
    auth_payload: dict,
    *,
    include_all_providers: bool = False,
) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    runtime = await resolve_provider_runtime(
        provider_id,
        auth_payload,
        resolve_local_connector=lambda connector_id: _resolve_accessible_local_connector_for_llm(
            connector_id,
            auth_payload,
        ),
        include_all_providers=include_all_providers,
    )
    return runtime.provider_mode, runtime.provider, runtime.providers


async def _resolve_global_assistant_provider_runtime_target(
    provider_id: str,
    auth_payload: dict,
) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    try:
        return await _resolve_provider_runtime_target(
            provider_id,
            auth_payload,
            include_all_providers=True,
        )
    except TypeError:
        return await _resolve_provider_runtime_target(provider_id, auth_payload)


def _resolve_global_assistant_chat_model_defaults() -> tuple[str, str]:
    config = system_config_store.get_global()
    provider_id = str(
        getattr(config, "global_assistant_chat_provider_id", "") or ""
    ).strip()
    model_name = str(
        getattr(config, "global_assistant_chat_model_name", "") or ""
    ).strip()
    return provider_id, model_name


def _finalize_resolved_provider_runtime(
    provider_mode: str,
    selected_provider: dict[str, Any],
    providers: list[dict[str, Any]] | None,
    *,
    requested_model_name: str = "",
    fallback_model_name: str = "",
    missing_model_message: str,
) -> ResolvedProviderRuntime:
    runtime = ResolvedProviderRuntime(
        provider_mode=provider_mode,
        provider=dict(selected_provider or {}),
        providers=list(providers or []),
        provider_id=str((selected_provider or {}).get("id") or "").strip(),
        connector_id=(
            parse_local_connector_provider_id(str((selected_provider or {}).get("id") or ""))
            if provider_mode == "local_connector"
            else ""
        ),
    )
    return finalize_resolved_provider_runtime(
        runtime,
        requested_model_name,
        fallback_model_name,
        missing_model_message=missing_model_message,
    )


async def _resolve_global_assistant_chat_runtime(
    runtime_settings: dict[str, Any],
    auth_payload: dict,
) -> ResolvedProviderRuntime:
    configured_provider_id, configured_model_name = (
        _resolve_global_assistant_chat_model_defaults()
    )
    requested_provider_id = str(runtime_settings.get("provider_id") or "").strip()
    requested_model_name = str(runtime_settings.get("model_name") or "").strip()
    provider_mode, selected_provider, providers = (
        await _resolve_global_assistant_provider_runtime_target(
            requested_provider_id or configured_provider_id,
            auth_payload,
        )
    )
    return _finalize_resolved_provider_runtime(
        provider_mode,
        selected_provider,
        providers,
        requested_model_name=requested_model_name,
        fallback_model_name=configured_model_name,
        missing_model_message="未找到可用模型",
    )


async def _resolve_global_assistant_chat_runtime_target(
    runtime_settings: dict[str, Any],
    auth_payload: dict,
) -> tuple[str, dict[str, Any], str]:
    runtime = await _resolve_global_assistant_chat_runtime(runtime_settings, auth_payload)
    return runtime.provider_mode, runtime.provider, runtime.model_name


async def _resolve_project_chat_runtime(
    runtime_settings: dict[str, Any],
    auth_payload: dict,
) -> ResolvedProviderRuntime:
    provider_mode, selected_provider, providers = await _resolve_provider_runtime_target(
        str(runtime_settings.get("provider_id") or ""),
        auth_payload,
    )
    return _finalize_resolved_provider_runtime(
        provider_mode,
        selected_provider,
        providers,
        requested_model_name=str(runtime_settings.get("model_name") or "").strip(),
        missing_model_message="model_name is required",
    )


def _resolve_chat_llm_service_runtime(
    base_llm_service: Any,
    resolved_runtime: ResolvedProviderRuntime,
    auth_payload: dict,
) -> Any:
    return resolve_runtime_llm_service(
        base_llm_service,
        resolved_runtime,
        resolve_local_connector=lambda connector_id: _resolve_accessible_local_connector_for_llm(
            connector_id,
            auth_payload,
        ),
    )


def _project_tool_display_name(tool_name: str) -> str:
    normalized = str(tool_name or "").strip()
    if normalized == "query_project_rules":
        return "查询项目规则"
    if normalized == "query_project_members":
        return "查询项目成员"
    if normalized == "search_project_context":
        return "搜索项目上下文"
    if normalized == "get_project_detail":
        return "获取项目完整详情"
    if normalized == "get_project_employee_detail":
        return "获取员工完整详情"
    if normalized == "get_current_task_tree":
        return "读取当前任务树"
    if normalized == "update_task_node_status":
        return "更新任务节点状态"
    if normalized == "complete_task_node_with_verification":
        return "完成任务节点并写入验证"
    return normalized


def _build_project_related_mcp_modules(project_id: str) -> list[dict[str, Any]]:
    from services.dynamic_mcp_runtime import list_project_proxy_tools_runtime

    candidates = _project_chat_employee_candidates(project_id)
    employee_name_map = {
        str(item.get("id") or ""): str(item.get("name") or item.get("id") or "")
        for item in candidates
        if str(item.get("id") or "")
    }
    modules: list[dict[str, Any]] = []
    for tool in list_project_proxy_tools_runtime(project_id, ""):
        tool_name = str(tool.get("tool_name") or "").strip()
        if not tool_name:
            continue
        employee_id = str(tool.get("employee_id") or "").strip()
        builtin = bool(tool.get("builtin", False))
        modules.append(
            {
                "id": f"project-tool:{tool_name}",
                "name": _project_tool_display_name(tool_name),
                "provider": "system",
                "scope": "project_related",
                "module_type": "builtin_tool" if builtin else "project_skill_tool",
                "description": str(tool.get("description") or "").strip(),
                "tool_name": tool_name,
                "employee_id": employee_id,
                "employee_name": employee_name_map.get(employee_id, ""),
                "skill_id": str(tool.get("skill_id") or "").strip(),
                "entry_name": str(tool.get("entry_name") or "").strip(),
                "script_type": str(tool.get("script_type") or "").strip(),
            }
        )
    modules.sort(key=lambda item: (str(item.get("module_type") or ""), str(item.get("name") or "")))
    return modules


def _build_system_global_mcp_modules(current_project_id: str) -> list[dict[str, Any]]:
    modules: list[dict[str, Any]] = []

    for project in project_store.list_all():
        if not bool(getattr(project, "mcp_enabled", True)):
            continue
        modules.append(
            {
                "id": f"project-service:{project.id}",
                "name": str(getattr(project, "name", "") or project.id),
                "provider": "system",
                "scope": "system_global",
                "module_type": "project_mcp_service",
                "description": str(getattr(project, "description", "") or ""),
                "resource_id": str(project.id),
                "resource_kind": "project",
                "endpoint_http": f"/mcp/projects/{project.id}/mcp?key=YOUR_API_KEY",
                "endpoint_sse": f"/mcp/projects/{project.id}/sse?key=YOUR_API_KEY",
                "is_current_project": str(project.id) == current_project_id,
            }
        )

    for employee in employee_store.list_all():
        if not bool(getattr(employee, "mcp_enabled", True)):
            continue
        modules.append(
            {
                "id": f"employee-service:{employee.id}",
                "name": str(getattr(employee, "name", "") or employee.id),
                "provider": "system",
                "scope": "system_global",
                "module_type": "employee_mcp_service",
                "description": str(getattr(employee, "description", "") or ""),
                "resource_id": str(employee.id),
                "resource_kind": "employee",
                "endpoint_http": f"/mcp/employees/{employee.id}/mcp?key=YOUR_API_KEY&project_id={current_project_id}",
                "endpoint_sse": f"/mcp/employees/{employee.id}/sse?key=YOUR_API_KEY&project_id={current_project_id}",
            }
        )

    for skill in skill_store.list_all():
        if not bool(getattr(skill, "mcp_enabled", False)):
            continue
        modules.append(
            {
                "id": f"skill-service:{skill.id}",
                "name": str(getattr(skill, "name", "") or skill.id),
                "provider": "system",
                "scope": "system_global",
                "module_type": "skill_mcp_service",
                "description": str(getattr(skill, "description", "") or ""),
                "resource_id": str(skill.id),
                "resource_kind": "skill",
                "endpoint_http": f"/mcp/skills/{skill.id}/mcp",
                "endpoint_sse": f"/mcp/skills/{skill.id}/sse",
            }
        )

    for rule in rule_store.list_all():
        if not bool(getattr(rule, "mcp_enabled", False)):
            continue
        modules.append(
            {
                "id": f"rule-service:{rule.id}",
                "name": str(getattr(rule, "title", "") or rule.id),
                "provider": "system",
                "scope": "system_global",
                "module_type": "rule_mcp_service",
                "description": str(getattr(rule, "domain", "") or ""),
                "resource_id": str(rule.id),
                "resource_kind": "rule",
                "endpoint_http": f"/mcp/rules/{rule.id}/mcp",
                "endpoint_sse": f"/mcp/rules/{rule.id}/sse",
            }
        )

    modules.sort(
        key=lambda item: (
            0 if bool(item.get("is_current_project")) else 1,
            str(item.get("module_type") or ""),
            str(item.get("name") or ""),
        )
    )
    return modules


def _build_chat_mcp_modules(project_id: str) -> dict[str, Any]:
    system_project_related = _build_project_related_mcp_modules(project_id)
    system_global = _build_system_global_mcp_modules(project_id)
    external_modules: list[dict[str, Any]] = []
    for module in external_mcp_store.list_all():
        if not bool(getattr(module, "enabled", True)):
            continue
        module_project_id = str(getattr(module, "project_id", "") or "").strip()
        if module_project_id and module_project_id != project_id:
            continue
        external_modules.append(
            {
                "id": str(getattr(module, "id", "") or ""),
                "name": str(getattr(module, "name", "") or ""),
                "provider": "external",
                "scope": "external",
                "module_type": "external_mcp_service",
                "description": str(getattr(module, "description", "") or ""),
                "endpoint_http": str(getattr(module, "endpoint_http", "") or ""),
                "endpoint_sse": str(getattr(module, "endpoint_sse", "") or ""),
                "auth_type": str(getattr(module, "auth_type", "") or ""),
                "project_id": module_project_id,
                "enabled": bool(getattr(module, "enabled", True)),
            }
        )
    external_modules.sort(key=lambda item: (0 if item.get("project_id") == project_id else 1, str(item.get("name") or ""), str(item.get("id") or "")))
    return {
        "system": {
            "project_related": system_project_related,
            "system_global": system_global,
        },
        "external": {
            "modules": external_modules,
        },
        "summary": {
            "system_project_related_total": len(system_project_related),
            "system_global_total": len(system_global),
            "external_total": len(external_modules),
        },
    }


def _normalize_chat_history(history: list[dict] | None, *, limit: int = 20) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for item in history or []:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        if role not in {"user", "assistant"}:
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        normalized.append({"role": role, "content": content})
    safe_limit = max(1, min(int(limit or 20), 100))
    return normalized[-safe_limit:]


def _filter_project_tools_by_names(
    tools: list[dict[str, Any]],
    enabled_tool_names: list[str] | None,
    *,
    explicit_filter: bool,
) -> list[dict[str, Any]]:
    _ = explicit_filter
    return filter_tools_by_names_via_registry(tools, enabled_tool_names)


def _sort_tools_by_priority(tools: list[dict[str, Any]], tool_priority: list[str] | None) -> list[dict[str, Any]]:
    return sort_tools_by_priority_via_registry(tools, tool_priority)


def _collect_runtime_tools(
    project_id: str,
    *,
    selected_employee_ids: list[str] | None,
    enabled_tool_names: list[str] | None,
    explicit_tool_filter: bool,
    tool_priority: list[str] | None,
) -> list[dict[str, Any]]:
    from services.dynamic_mcp_runtime import list_project_external_tools_runtime, list_project_proxy_tools_runtime

    _ = explicit_tool_filter
    return collect_project_runtime_tools_via_registry(
        project_id,
        selected_employee_ids=selected_employee_ids,
        enabled_tool_names=enabled_tool_names,
        tool_priority=tool_priority,
        list_internal_tools=lambda current_project_id: list_project_proxy_tools_runtime(
            current_project_id,
            "",
        ),
        list_external_tools=list_project_external_tools_runtime,
    )


def _summarize_effective_tools(
    tools: list[dict[str, Any]] | None,
    *,
    max_items: int = 24,
) -> tuple[list[dict[str, str]], int]:
    return summarize_effective_tools_via_registry(tools, max_items=max_items)


def _resolve_chat_runtime_settings(req: ProjectChatReq, project: ProjectConfig) -> dict[str, Any]:
    base = _normalize_project_chat_settings(getattr(project, "chat_settings", {}) or {})
    merged = dict(base)
    override = {
        "chat_mode": req.chat_mode,
        "local_connector_id": req.local_connector_id,
        "connector_workspace_path": req.connector_workspace_path,
        "connector_sandbox_mode": req.connector_sandbox_mode,
        "connector_sandbox_mode_explicit": req.connector_sandbox_mode_explicit,
        "selected_employee_id": req.employee_id,
        "selected_employee_ids": req.employee_ids,
        "employee_coordination_mode": req.employee_coordination_mode,
        "provider_id": req.provider_id,
        "model_name": req.model_name,
        "temperature": req.temperature,
        "max_tokens": req.max_tokens,
        "system_prompt": req.system_prompt,
        "enabled_project_tool_names": req.enabled_project_tool_names,
        "auto_use_tools": req.auto_use_tools,
        "tool_priority": req.tool_priority,
        "max_tool_calls_per_round": req.max_tool_calls_per_round,
        "max_loop_rounds": req.max_loop_rounds,
        "max_tool_rounds": req.max_tool_rounds,
        "repeated_tool_call_threshold": req.repeated_tool_call_threshold,
        "tool_only_threshold": req.tool_only_threshold,
        "tool_budget_strategy": req.tool_budget_strategy,
        "history_limit": req.history_limit,
        "tool_timeout_sec": req.tool_timeout_sec,
        "tool_retry_count": req.tool_retry_count,
        "answer_style": req.answer_style,
        "prefer_conclusion_first": req.prefer_conclusion_first,
        "task_tree_enabled": getattr(req, "task_tree_enabled", None),
        "task_tree_auto_generate": getattr(req, "task_tree_auto_generate", None),
    }
    for key, value in override.items():
        if key in req.model_fields_set and value is not None:
            merged[key] = value
    return _normalize_project_chat_settings(merged)


def _filter_project_tools_by_employee_ids(
    tools: list[dict[str, Any]],
    employee_ids: list[str] | None,
) -> list[dict[str, Any]]:
    return filter_tools_by_employee_ids_via_registry(tools, employee_ids)


def _normalize_image_inputs(images: list[str] | None) -> list[str]:
    normalized: list[str] = []
    for item in images or []:
        value = str(item or "").strip()
        if not value:
            continue
        lower = value.lower()
        if re.match(r"^data:image/[a-z0-9.+-]+;base64,", lower):
            normalized.append(value)
            continue
        if lower.startswith("http://") or lower.startswith("https://"):
            normalized.append(value)
    return normalized


def _normalize_skill_resource_directory(value: Any) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    return normalized[:1000]


def _build_skill_resource_prompt_block(skill_resource_directory: str) -> str:
    normalized = _normalize_skill_resource_directory(skill_resource_directory)
    if not normalized:
        return ""
    return (
        f"\n\n当前已为本轮对话指定本地技能目录: {normalized}\n"
        "当用户提到缺少技能、查找技能模板、下载技能、安装技能或复用本地 skill 时，优先把这个目录视为当前可参考的本地技能来源。"
        "\n如果当前模式或工具链能够访问该目录，请优先读取其中的 SKILL.md、模板和脚本后再回答或执行。"
        "\n如果当前模式无法直接访问该目录，请先明确说明限制，再给出下一步操作建议。"
        "\n除非用户明确要求，不要把该目录中的技能自动导入系统。"
    )


def _summarize_prompt_values(
    values: list[Any] | tuple[Any, ...] | set[Any] | None,
    *,
    limit: int = 8,
) -> str:
    normalized = [str(item or "").strip() for item in (values or []) if str(item or "").strip()]
    if not normalized:
        return "-"
    if len(normalized) <= limit:
        return ", ".join(normalized)
    return f"{', '.join(normalized[:limit])} 等{len(normalized)}项"


def _summarize_prompt_text(value: Any, *, limit: int = 600) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    compact = re.sub(r"\s+", " ", text)
    if len(compact) <= limit:
        return compact
    return f"{compact[:limit].rstrip()}..."


def _build_multi_employee_collaboration_prompt(
    selected_employees: list[dict[str, Any]] | None,
    tools: list[dict[str, Any]] | None,
) -> str:
    employees = [
        item
        for item in (selected_employees or [])
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    ]
    if len(employees) <= 1:
        return ""

    employee_name_map = {
        str(item.get("id") or "").strip(): str(item.get("name") or item.get("id") or "").strip()
        for item in employees
        if str(item.get("id") or "").strip()
    }
    tool_groups: dict[str, list[str]] = {}
    for item in tools or []:
        if not isinstance(item, dict):
            continue
        tool_name = str(item.get("tool_name") or "").strip()
        if not tool_name:
            continue
        employee_id = str(item.get("employee_id") or "").strip() or "__shared__"
        tool_groups.setdefault(employee_id, []).append(tool_name)

    lines = [
        f"当前启用多员工自动协作，共 {len(employees)} 名执行员工。",
        "协作要求：先结合当前项目手册、员工手册、规则和工具判断是否需要多人协作，再决定拆分方式；不要预设固定行业分工模板。",
        "协作要求：若单个员工已足以完成任务，可保持单人主责；仅在确有必要时引入其他员工辅助，避免多人对同一子任务重复调用工具。",
        "协作要求：调用工具时优先选择最匹配员工名下的工具；跨员工串联时先明确负责人、输入和输出，再复用上一步结果继续。",
        "协作要求：最终只输出一份汇总结论；仅在有帮助时简要说明为何这样协作、关键依据和剩余风险。",
        "已选员工清单：",
    ]
    for employee in employees:
        employee_id = str(employee.get("id") or "").strip()
        employee_name = str(employee.get("name") or employee_id).strip() or employee_id
        rule_bindings = list(employee.get("rule_bindings") or [])
        workflow = [
            str(item or "").strip()
            for item in (employee.get("default_workflow") or [])
            if str(item or "").strip()
        ]
        lines.append(
            f"- {employee_name} ({employee_id}): "
            f"goal={str(employee.get('goal') or '-').strip() or '-'}; "
            f"skills={_summarize_prompt_values(employee.get('skill_names') or [])}; "
            f"rule_titles={_summarize_prompt_values([item.get('title') or item.get('id') for item in rule_bindings])}; "
            f"rule_domains={_summarize_prompt_values(_collect_rule_domains(rule_bindings))}; "
            f"workflow={_summarize_prompt_values(workflow)}"
        )
        tool_usage_policy = str(employee.get("tool_usage_policy") or "").strip()
        if tool_usage_policy:
            lines.append(f"  tool_policy={tool_usage_policy}")

    if tool_groups:
        lines.append("按员工分组的可用工具：")
        for employee in employees:
            employee_id = str(employee.get("id") or "").strip()
            employee_name = employee_name_map.get(employee_id) or employee_id
            lines.append(
                f"- {employee_name} ({employee_id}): "
                f"{_summarize_prompt_values(tool_groups.get(employee_id, []), limit=10)}"
            )
        if tool_groups.get("__shared__"):
            lines.append(
                f"- 共享/全局工具: {_summarize_prompt_values(tool_groups.get('__shared__'), limit=10)}"
            )
    return "\n" + "\n".join(lines)


def _build_project_chat_messages(
    project: ProjectConfig,
    user_message: str,
    history: list[dict] | None,
    images: list[str] | None = None,
    selected_employee: dict[str, Any] | None = None,
    selected_employees: list[dict[str, Any]] | None = None,
    tools: list[dict] | None = None,
    custom_system_prompt: str | None = None,
    history_limit: int = 20,
    answer_style: str = "concise",
    prefer_conclusion_first: bool = True,
    workspace_path: str = "",
    skill_resource_directory: str = "",
    employee_coordination_mode: str = "auto",
    task_tree_prompt: str = "",
) -> list[dict[str, Any]]:
    workspace_info = ""
    effective_workspace_path = str(workspace_path or project.workspace_path or "").strip()
    if effective_workspace_path:
        workspace_info = (
            f"当前项目工作区路径: {effective_workspace_path}\n"
            "请在此目录下进行代码开发和文件操作。"
        )
    ai_entry_info = ""
    ai_entry_file = str(project.ai_entry_file or "").strip()
    if ai_entry_file:
        ai_entry_path = Path(ai_entry_file).expanduser()
        if effective_workspace_path and not ai_entry_path.is_absolute():
            resolved_entry_hint = str(Path(effective_workspace_path) / ai_entry_file)
            ai_entry_info = (
                f"当前项目 AI 入口文件: {ai_entry_file}"
                f"\n该入口文件相对于项目工作区，对应路径: {resolved_entry_hint}"
                "\n在开始分析、编码、调用工具或回答项目前，优先读取这个入口文件，并按其中约定理解项目规则、目录结构、实现约束和执行顺序。"
                "\n仅当该入口文件不存在、无法访问或信息不足时，再自行补充读取项目内其他相关规则文件。"
            )
        else:
            ai_entry_info = (
                f"当前项目 AI 入口文件: {ai_entry_file}"
                "\n在开始分析、编码、调用工具或回答项目前，优先读取这个入口文件，并按其中约定理解项目规则、目录结构、实现约束和执行顺序。"
                "\n仅当该入口文件不存在、无法访问或信息不足时，再自行补充读取项目内其他相关规则文件。"
            )

    tool_names = [t.get("tool_name", "") for t in (tools or [])] if tools else []
    tool_list_text = f"可用工具({len(tool_names)}个): {', '.join(tool_names)}" if tool_names else "当前无可用工具"

    base_prompt = (custom_system_prompt or "").strip()
    if not base_prompt:
        base_prompt = "你是项目开发助手。"
        base_prompt += "\n可按需调用工具检索最新项目上下文并完成用户请求。"
        base_prompt += "\n解决问题时，优先使用当前项目已绑定的员工、规则和技能；先判断项目内现成能力是否足够，再决定是否补充你自己的通用能力。"
        base_prompt += "\n每次收到项目请求，进入分析、实现或排查前，先读取项目手册，并按需调用 get_project_manual、query_project_rules、list_project_proxy_tools，重新获取与当前问题直接相关的规则正文和技能能力。"
        base_prompt += "\n若项目绑定员工或技能已经可以闭环，就优先复用项目员工对应的工具或协作链路；只有项目内能力不足、工具缺失或上下文仍不够时，才允许你自行补足实现。"
        base_prompt += "\n项目规则只使用与当前问题直接相关的部分；不要只看规则标题，也不要把无关项目规则机械套用到所有请求。"
        base_prompt += "\n当用户询问项目信息、员工信息、规则、MCP 服务时，优先调用 search_project_context 再回答。"
        base_prompt += "\n当用户询问当前项目有哪些员工、成员、规则、工具或 MCP 能力时，不要先说无法获取；先调用 query_project_members、query_project_rules 或 search_project_context。"
        base_prompt += "\n当用户明确要完整项目配置、聊天配置、成员原始关系或单员工完整档案时，优先调用 get_project_detail 或 get_project_employee_detail。"

    style_hint, order_hint = resolve_chat_style_hints(
        answer_style,
        prefer_conclusion_first=prefer_conclusion_first,
    )
    skill_resource_prompt = _build_skill_resource_prompt_block(skill_resource_directory)
    coordination_mode = str(employee_coordination_mode or "auto").strip().lower()
    multi_employee_prompt = (
        _build_multi_employee_collaboration_prompt(selected_employees, tools)
        if coordination_mode == "auto"
        else ""
    )
    system_prompt = join_prompt_sections(
        base_prompt,
        workspace_info,
        ai_entry_info,
        tool_list_text,
        order_hint,
        style_hint,
        skill_resource_prompt,
        multi_employee_prompt,
        task_tree_prompt,
    )
    project_ui_rule_bindings = _resolve_project_ui_rule_bindings(project, include_content=True)
    if project_ui_rule_bindings:
        project_ui_rule_titles = [
            str(item.get("title") or item.get("id") or "").strip()
            for item in project_ui_rule_bindings
            if str(item.get("title") or item.get("id") or "").strip()
        ]
        project_ui_rule_domains = _collect_rule_domains(project_ui_rule_bindings)
        project_ui_rule_lines: list[str] = []
        for item in project_ui_rule_bindings:
            title = str(item.get("title") or item.get("id") or "").strip() or "未命名规则"
            rule_id = str(item.get("id") or "").strip()
            domain = str(item.get("domain") or "").strip() or "-"
            content = _summarize_prompt_text(item.get("content"), limit=600)
            if content:
                project_ui_rule_lines.append(
                    f"- {title} ({rule_id}) [domain={domain}]: {content}"
                )
            else:
                project_ui_rule_lines.append(
                    f"- {title} ({rule_id}) [domain={domain}]"
                )
        system_prompt = join_prompt_sections(
            system_prompt,
            (
                "当前项目已绑定 UI 规则，这些规则优先级高于员工个人规则；涉及页面、交互、视觉表达时必须先遵循项目 UI 规则。"
            f"\nproject_ui_rule_titles={', '.join(project_ui_rule_titles) or '-'}。"
            f"\nproject_ui_rule_domains={', '.join(project_ui_rule_domains) or '-'}。"
            "\n项目 UI 规则正文：\n"
            + "\n".join(project_ui_rule_lines)
        )
        )
    if selected_employee:
        rule_bindings = list(selected_employee.get("rule_bindings") or [])
        rule_titles = [str(item.get("title") or item.get("id") or "").strip() for item in rule_bindings]
        rule_titles = [item for item in rule_titles if item]
        rule_domains = _collect_rule_domains(rule_bindings)
        workflow = [str(item or "").strip() for item in (selected_employee.get("default_workflow") or []) if str(item or "").strip()]
        employee_section = (
            f"当前执行员工：{selected_employee.get('name') or selected_employee.get('id')} "
            f"({selected_employee.get('id')})，"
            f"goal={str(selected_employee.get('goal') or '-').strip() or '-'}，"
            f"skills={', '.join(selected_employee.get('skill_names') or []) or '-'}，"
            f"rule_titles={', '.join(rule_titles) or '-'}，"
            f"rule_domains={', '.join(rule_domains) or '-'}。"
        )
        if workflow:
            employee_section += f"\n默认工作流：{' -> '.join(workflow)}。"
        tool_usage_policy = str(selected_employee.get("tool_usage_policy") or "").strip()
        if tool_usage_policy:
            employee_section += f"\n工具使用策略：{tool_usage_policy}"
        system_prompt = join_prompt_sections(system_prompt, employee_section)
    return assemble_chat_messages(
        system_messages=[
            system_prompt,
            f"当前项目: id={project.id}, name={project.name}, description={project.description or '-'}",
        ],
        history=history,
        user_message=user_message,
        images=images,
        history_limit=history_limit,
        normalize_history=_normalize_chat_history,
        normalize_images=_normalize_image_inputs,
    )


def _resolve_project_chat_task_tree_context(
    project_id: str,
    username: str,
    chat_session_id: str,
    runtime_settings: dict[str, Any],
    effective_user_message: str,
) -> dict[str, Any] | None:
    normalized_chat_session_id = _require_project_chat_session_id(chat_session_id)
    if not bool(runtime_settings.get("task_tree_enabled", True)):
        payload = serialize_task_tree(
            get_task_tree_for_chat_session(
                project_id,
                username,
                normalized_chat_session_id,
            )
        )
    elif bool(runtime_settings.get("task_tree_auto_generate", True)) and str(
        effective_user_message or ""
    ).strip():
        session = ensure_task_tree(
            project_id=project_id,
            username=username,
            chat_session_id=normalized_chat_session_id,
            root_goal=effective_user_message,
        )
        payload = serialize_task_tree(session)
    else:
        session = get_task_tree(project_id, username, normalized_chat_session_id)
        payload = serialize_task_tree(session)
    if payload is None:
        raise ValueError("task tree must be available before answering")
    return payload


def _require_project_chat_session_id(chat_session_id: str) -> str:
    normalized_chat_session_id = str(chat_session_id or "").strip()
    if not normalized_chat_session_id:
        raise ValueError("chat_session_id is required for project chat")
    return normalized_chat_session_id


def _attach_task_tree_audit_to_done_payload(
    payload: dict[str, Any],
    *,
    project_id: str,
    username: str,
    chat_session_id: str,
    content: str,
    successful_tool_names: list[str] | None = None,
    task_tree_tool_used: bool = False,
) -> dict[str, Any]:
    task_tree_audit = audit_task_tree_round(
        project_id=project_id,
        username=username,
        chat_session_id=chat_session_id,
        assistant_content=content,
        successful_tool_names=successful_tool_names,
        task_tree_tool_used=task_tree_tool_used,
    )
    if isinstance(task_tree_audit, dict):
        payload["task_tree_audit"] = task_tree_audit
        if "task_tree" in task_tree_audit:
            payload["task_tree"] = task_tree_audit.get("task_tree")
        history_task_tree_payload = task_tree_audit.get("history_task_tree")
        if isinstance(history_task_tree_payload, dict):
            payload["history_task_tree"] = history_task_tree_payload
    return payload


def _resolve_project_chat_work_session_payload(
    *,
    project_id: str,
    task_tree_payload: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(task_tree_payload, dict):
        return None
    normalized_project_id = str(project_id or "").strip()
    if not normalized_project_id:
        return None
    task_tree_session_id = str(task_tree_payload.get("id") or "").strip()
    task_tree_chat_session_id = str(
        task_tree_payload.get("source_chat_session_id")
        or task_tree_payload.get("chat_session_id")
        or ""
    ).strip()
    source_session_id = str(task_tree_payload.get("source_session_id") or "").strip()
    grouped: dict[str, list[Any]] = {}
    if task_tree_session_id:
        try:
            events = work_session_store.list_events(
                project_id=normalized_project_id,
                task_tree_session_id=task_tree_session_id,
                task_tree_chat_session_id=task_tree_chat_session_id,
                limit=200,
            )
        except Exception:
            events = []
        for item in events:
            session_id = str(getattr(item, "session_id", "") or "").strip()
            if not session_id:
                continue
            grouped.setdefault(session_id, []).append(item)
    if grouped:
        summaries = [
            _summarize_project_work_session(items)
            for items in grouped.values()
            if items
        ]
        summaries = [item for item in summaries if item.get("session_id")]
        summaries.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
        if summaries:
            selected = summaries[0]
            return {
                "session_id": str(selected.get("session_id") or "").strip(),
                "project_id": normalized_project_id,
                "task_tree_session_id": str(
                    selected.get("task_tree_session_id") or task_tree_session_id or ""
                ).strip(),
                "task_tree_chat_session_id": str(
                    selected.get("task_tree_chat_session_id")
                    or task_tree_chat_session_id
                    or ""
                ).strip(),
                "task_node_id": str(selected.get("task_node_id") or "").strip(),
                "task_node_title": str(selected.get("task_node_title") or "").strip(),
                "goal": str(selected.get("goal") or "").strip(),
                "latest_status": str(selected.get("latest_status") or "").strip(),
                "updated_at": str(selected.get("updated_at") or "").strip(),
                "created_at": str(selected.get("created_at") or "").strip(),
            }
    if not source_session_id and not task_tree_session_id:
        return None
    current_node = (
        task_tree_payload.get("current_node")
        if isinstance(task_tree_payload.get("current_node"), dict)
        else {}
    )
    return {
        "session_id": source_session_id,
        "project_id": normalized_project_id,
        "task_tree_session_id": task_tree_session_id,
        "task_tree_chat_session_id": task_tree_chat_session_id,
        "task_node_id": str(current_node.get("id") or "").strip(),
        "task_node_title": str(current_node.get("title") or "").strip(),
        "goal": str(task_tree_payload.get("root_goal") or task_tree_payload.get("title") or "").strip(),
        "latest_status": str(task_tree_payload.get("status") or "").strip(),
        "updated_at": str(task_tree_payload.get("updated_at") or "").strip(),
        "created_at": str(task_tree_payload.get("created_at") or "").strip(),
    }


def _attach_project_chat_work_session_payload(
    payload: dict[str, Any],
    *,
    project_id: str,
    task_tree_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    work_session_payload = _resolve_project_chat_work_session_payload(
        project_id=project_id,
        task_tree_payload=task_tree_payload,
    )
    if isinstance(work_session_payload, dict) and work_session_payload.get("session_id"):
        payload["work_session"] = work_session_payload
    return payload


def _build_project_chat_start_payload(
    *,
    project_id: str,
    request_id: str = "",
    provider_id: str = "",
    model_name: str = "",
    chat_mode: str = "system",
    employee_id: str = "",
    employee_name: str = "",
    employee_ids: list[str] | None = None,
    tools_enabled: bool = False,
    effective_tools: list[dict[str, Any]] | None = None,
    effective_tool_total: int | None = None,
    task_tree_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": "start",
        "project_id": project_id,
        "provider_id": provider_id,
        "model_name": model_name,
        "chat_mode": chat_mode,
        "employee_id": employee_id,
        "employee_name": employee_name,
        "tools_enabled": bool(tools_enabled),
        "task_tree": task_tree_payload,
    }
    if request_id:
        payload["request_id"] = request_id
    if employee_ids is not None:
        payload["employee_ids"] = employee_ids
    if effective_tools is not None:
        payload["effective_tools"] = effective_tools
    if effective_tool_total is not None:
        payload["effective_tool_total"] = int(effective_tool_total or 0)
    return _attach_project_chat_work_session_payload(
        payload,
        project_id=project_id,
        task_tree_payload=task_tree_payload,
    )


def _build_project_chat_done_payload(
    *,
    content: str,
    project_id: str,
    username: str,
    chat_session_id: str,
    provider_id: str = "",
    model_name: str = "",
    artifacts: list[dict[str, Any]] | None = None,
    successful_tool_names: list[str] | None = None,
    task_tree_tool_used: bool = False,
) -> dict[str, Any]:
    normalized_artifacts = _normalize_chat_media_artifacts(artifacts)
    payload: dict[str, Any] = {
        "type": "done",
        "content": content,
        "provider_id": provider_id,
        "model_name": model_name,
    }
    if normalized_artifacts:
        payload["artifacts"] = normalized_artifacts
        payload["images"] = _collect_chat_artifact_urls(normalized_artifacts, asset_type="image")
        payload["videos"] = _collect_chat_artifact_urls(normalized_artifacts, asset_type="video")
    payload = _attach_task_tree_audit_to_done_payload(
        payload,
        project_id=project_id,
        username=username,
        chat_session_id=chat_session_id,
        content=content,
        successful_tool_names=successful_tool_names,
        task_tree_tool_used=task_tree_tool_used,
    )
    task_tree_payload = None
    history_task_tree_payload = payload.get("history_task_tree")
    if isinstance(history_task_tree_payload, dict):
        task_tree_payload = history_task_tree_payload
    elif isinstance(payload.get("task_tree"), dict):
        task_tree_payload = payload.get("task_tree")
    return _attach_project_chat_work_session_payload(
        payload,
        project_id=project_id,
        task_tree_payload=task_tree_payload,
    )


def _build_global_chat_messages(
    user_message: str,
    history: list[dict] | None,
    images: list[str] | None = None,
    *,
    custom_system_prompt: str | None = None,
    history_limit: int = 20,
    answer_style: str = "concise",
    prefer_conclusion_first: bool = True,
    skill_resource_directory: str = "",
    chat_surface: str = "main-chat",
    runtime_snapshot: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    base_prompt = (custom_system_prompt or "").strip()
    if not base_prompt:
        if _normalize_project_chat_surface(chat_surface) == "global-assistant":
            cfg = system_config_store.get_global()
            base_prompt = str(
                getattr(cfg, "global_assistant_system_prompt", "") or DEFAULT_GLOBAL_ASSISTANT_SYSTEM_PROMPT
            ).strip() or DEFAULT_GLOBAL_ASSISTANT_SYSTEM_PROMPT
        else:
            base_prompt = "你是通用 AI 助手。"
            base_prompt += "\n当前没有选中项目，请基于通用知识直接回答。"
            base_prompt += "\n如果用户问题依赖项目、代码库、员工、MCP 或规则配置，请明确提示需要先选择项目后再继续。"

    style_hint, order_hint = resolve_chat_style_hints(
        answer_style,
        prefer_conclusion_first=prefer_conclusion_first,
    )
    skill_resource_prompt = _build_skill_resource_prompt_block(skill_resource_directory)
    system_prompt = join_prompt_sections(
        base_prompt,
        "当前模式：通用对话（未选择项目）。",
        order_hint,
        style_hint,
        skill_resource_prompt,
    )
    runtime_lines: list[str] = []
    snapshot = runtime_snapshot or {}
    route_title = str(snapshot.get("route_title") or "").strip()
    route_path = str(snapshot.get("route_path") or "").strip()
    current_user = str(snapshot.get("username") or "").strip()
    current_role = str(snapshot.get("role") or "").strip()
    current_project_id = str(snapshot.get("current_project_id") or "").strip()
    current_project_name = str(snapshot.get("current_project_name") or "").strip()
    if route_title or route_path:
        runtime_lines.append(
            f"当前页面：{route_title or route_path} ({route_path or route_title})"
        )
    if current_project_id or current_project_name:
        runtime_lines.append(
            f"当前项目：{current_project_name or current_project_id} ({current_project_id or current_project_name})"
        )
    if current_user:
        runtime_lines.append(
            f"当前登录用户：{current_user}，角色：{current_role or 'unknown'}"
        )
    metric_map = {
        "visible_project_count": "可访问项目数",
        "employee_count": "员工数",
        "user_count": "用户数",
        "online_user_count": "在线用户数",
        "project_mcp_count": "项目 MCP 数",
        "global_mcp_count": "全局 MCP 数",
    }
    metric_lines = [
        f"{label}：{snapshot[key]}"
        for key, label in metric_map.items()
        if snapshot.get(key) is not None
    ]
    if metric_lines:
        runtime_lines.append("实时系统快照：" + "；".join(metric_lines))
    system_messages = [system_prompt]
    if runtime_lines:
        system_messages.append(
            "以下是本轮回答必须参考的真实运行数据快照：\n" + "\n".join(runtime_lines)
        )
    return assemble_chat_messages(
        system_messages=system_messages,
        history=history,
        user_message=user_message,
        images=images,
        history_limit=history_limit,
        normalize_history=_normalize_chat_history,
        normalize_images=_normalize_image_inputs,
    )


async def _build_global_assistant_runtime_snapshot(
    auth_payload: dict,
    *,
    route_path: str = "",
    route_title: str = "",
) -> dict[str, Any]:
    username = _current_username(auth_payload)
    role = _current_role_id(auth_payload) or "user"
    visibility = build_global_assistant_visibility_context(
        username=username,
        role_ids=_current_role_ids(auth_payload),
    )
    visible_project_ids = {
        str(item or "").strip()
        for item in (visibility.get("visible_project_ids") or [])
        if str(item or "").strip()
    }
    visible_employee_count = int(visibility.get("visible_employee_count") or 0)

    project_mcp_count = 0
    global_mcp_count = 0
    try:
        for module in external_mcp_store.list_all():
            if not bool(getattr(module, "enabled", True)):
                continue
            module_project_id = str(getattr(module, "project_id", "") or "").strip()
            if module_project_id:
                if module_project_id in visible_project_ids:
                    project_mcp_count += 1
            else:
                global_mcp_count += 1
    except Exception:
        pass

    online_user_count: int | None = None
    try:
        redis_client = await get_redis_client()
        online_user_count = len(
            await redis_client.smembers("online-users:members") or set()
        )
    except Exception:
        online_user_count = None

    snapshot: dict[str, Any] = {
        "username": username,
        "role": role,
        "route_path": str(route_path or "").strip(),
        "route_title": str(route_title or "").strip(),
        "visible_project_count": len(visible_project_ids),
        "employee_count": visible_employee_count,
        "project_mcp_count": project_mcp_count,
        "global_mcp_count": global_mcp_count,
    }
    route_project_match = re.search(
        r"(proj-[A-Za-z0-9]+)",
        str(route_path or "").strip(),
    )
    if route_project_match:
        route_project_id = route_project_match.group(1)
        route_project = project_store.get(route_project_id)
        if route_project is not None:
            route_project_visible = _is_admin_like(auth_payload)
            if not route_project_visible:
                member = _get_project_user_member(route_project_id, username)
                route_project_visible = member is not None and bool(
                    getattr(member, "enabled", True)
                )
            if route_project_visible:
                snapshot["current_project_id"] = route_project_id
                snapshot["current_project_name"] = str(
                    getattr(route_project, "name", "") or route_project_id
                ).strip()
    if _is_admin_like(auth_payload):
        snapshot["user_count"] = len(user_store.list_all())
        snapshot["online_user_count"] = online_user_count
    return snapshot


def _resolve_default_chat_system_prompt(custom_system_prompt: Any = None) -> str | None:
    custom_prompt = str(custom_system_prompt or "").strip()
    if custom_prompt:
        return custom_prompt
    cfg = system_config_store.get_global()
    default_prompt = str(getattr(cfg, "default_chat_system_prompt", "") or "").strip()
    return default_prompt or None


def _resolve_chat_max_tokens(request_max_tokens: int | None) -> int:
    cfg = system_config_store.get_global()
    configured = int(getattr(cfg, "chat_max_tokens", 512) or 512)
    configured = max(128, min(configured, 8192))
    if request_max_tokens is None:
        return configured
    try:
        request_value = int(request_max_tokens)
    except (TypeError, ValueError):
        return configured
    if request_value <= 0:
        return configured
    return max(128, min(request_value, 8192))


def _normalize_project_username(value: Any) -> str:
    username = str(value or "").strip()
    if not username:
        raise HTTPException(400, "username is required")
    if not (
        _PROJECT_USERNAME_PATTERN.fullmatch(username)
        or _PROJECT_EMAIL_PATTERN.fullmatch(username)
    ):
        raise HTTPException(400, "Invalid username format")
    return username


def _current_username(auth_payload: dict) -> str:
    username = str(auth_payload.get("sub") or "").strip()
    return username or "unknown"


def _current_role_id(auth_payload: dict) -> str:
    role_ids = get_auth_role_ids(auth_payload)
    return role_ids[0] if role_ids else ""


def _current_role_ids(auth_payload: dict) -> list[str]:
    return get_auth_role_ids(auth_payload)


def _is_admin_like(auth_payload: dict) -> bool:
    return "*" in set(resolve_role_ids_permissions(_current_role_ids(auth_payload)))


def _normalize_text_list(value: Any, *, limit: int = 80) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_item in value:
        item = str(raw_item or "").strip()[:limit]
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(item)
    return normalized


def _connector_llm_shared_with_usernames(item: Any) -> list[str]:
    return _normalize_text_list(getattr(item, "llm_shared_with_usernames", []), limit=64)


def _connector_llm_shared_with_roles(item: Any) -> list[str]:
    return [item.lower() for item in _normalize_text_list(getattr(item, "llm_shared_with_roles", []), limit=64)]


def _connector_llm_accessible(item: Any, auth_payload: dict) -> bool:
    if _is_admin_like(auth_payload):
        return True
    username = _current_username(auth_payload)
    if str(getattr(item, "owner_username", "") or "").strip() == username:
        return True
    if username in _connector_llm_shared_with_usernames(item):
        return True
    shared_roles = set(_connector_llm_shared_with_roles(item))
    return any(role_id in shared_roles for role_id in _current_role_ids(auth_payload))


def _connector_workspace_accessible(item: Any, auth_payload: dict) -> bool:
    if _is_admin_like(auth_payload):
        return True
    return str(getattr(item, "owner_username", "") or "").strip() == _current_username(auth_payload)


def _list_accessible_local_connectors(auth_payload: dict) -> list[Any]:
    return [
        item
        for item in local_connector_store.list_connectors()
        if _connector_workspace_accessible(item, auth_payload)
    ]


def _resolve_accessible_local_connector(
    connector_id: str,
    auth_payload: dict,
) -> Any | None:
    normalized = str(connector_id or "").strip()
    if not normalized:
        return None
    item = local_connector_store.get_connector(normalized)
    if item is None:
        return None
    return item if _connector_workspace_accessible(item, auth_payload) else None


def _list_accessible_local_connectors_for_llm(auth_payload: dict) -> list[Any]:
    return [
        item
        for item in local_connector_store.list_connectors()
        if _connector_llm_accessible(item, auth_payload)
    ]


def _resolve_accessible_local_connector_for_llm(
    connector_id: str,
    auth_payload: dict,
) -> Any | None:
    normalized = str(connector_id or "").strip()
    if not normalized:
        return None
    item = local_connector_store.get_connector(normalized)
    if item is None:
        return None
    return item if _connector_llm_accessible(item, auth_payload) else None


def _serialize_chat_connector(item: Any) -> dict[str, Any]:
    payload = {
        "id": str(getattr(item, "id", "") or "").strip(),
        "connector_name": str(getattr(item, "connector_name", "") or "").strip(),
        "owner_username": str(getattr(item, "owner_username", "") or "").strip(),
        "platform": str(getattr(item, "platform", "") or "").strip(),
        "app_version": str(getattr(item, "app_version", "") or "").strip(),
        "advertised_url": str(getattr(item, "advertised_url", "") or "").strip(),
        "status": str(getattr(item, "status", "") or "").strip(),
        "last_error": str(getattr(item, "last_error", "") or "").strip(),
        "last_seen_at": str(getattr(item, "last_seen_at", "") or "").strip(),
        "capabilities": getattr(item, "capabilities", {}) if isinstance(getattr(item, "capabilities", {}), dict) else {},
        "health": getattr(item, "health", {}) if isinstance(getattr(item, "health", {}), dict) else {},
        "manifest": getattr(item, "manifest", {}) if isinstance(getattr(item, "manifest", {}), dict) else {},
        "online": False,
    }
    last_seen_raw = payload["last_seen_at"]
    if last_seen_raw:
        try:
            last_seen = datetime.fromisoformat(last_seen_raw.replace("Z", "+00:00"))
            payload["online"] = (datetime.now(timezone.utc) - last_seen).total_seconds() <= 90
        except ValueError:
            payload["online"] = False
    return payload


def _resolve_project_workspace_for_chat(
    project: ProjectConfig,
    settings: dict[str, Any],
) -> str:
    return resolve_chat_workspace_path_via_registry(
        str(project.workspace_path or "").strip(),
        settings,
    )


def _resolve_local_connector_coding_tools(
    auth_payload: dict,
    settings: dict[str, Any],
    workspace_path: str,
) -> tuple[list[dict[str, Any]], Any | None, str]:
    return resolve_local_connector_runtime_tools_via_registry(
        settings,
        workspace_path,
        resolve_local_connector=lambda connector_id: _resolve_accessible_local_connector(
            connector_id,
            auth_payload,
        ),
        build_connector_tools=build_local_connector_file_tools,
    )


def _get_project_user_member(project_id: str, username: str) -> ProjectUserMember | None:
    normalized_project_id = str(project_id or "").strip()
    normalized_username = str(username or "").strip()
    if not normalized_project_id or not normalized_username:
        return None
    try:
        return project_store.get_user_member(normalized_project_id, normalized_username)
    except Exception:
        return None


def _ensure_project_access(project_id: str, auth_payload: dict) -> ProjectConfig:
    project = project_store.get(project_id)
    if project is None:
        raise HTTPException(404, f"Project {project_id} not found")
    if _is_admin_like(auth_payload):
        return project
    username = _current_username(auth_payload)
    member = _get_project_user_member(project_id, username)
    if member is None or not bool(getattr(member, "enabled", True)):
        raise HTTPException(403, f"Project access denied: {project_id}")
    return project


def _ensure_project_manage_access(project_id: str, auth_payload: dict) -> ProjectConfig:
    project = _ensure_project_access(project_id, auth_payload)
    if _can_manage_project(project_id, auth_payload, project):
        return project
    raise HTTPException(403, f"Project manage access denied: {project_id}")


def _normalize_project_record_token(value: Any, *, limit: int = 4000) -> str:
    return str(value or "").strip()[:limit]


def _normalize_project_record_tags(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(
        str(item or "").strip().lower()
        for item in value
        if str(item or "").strip()
    )


def _project_requirement_records_cache_set_key(project_id: str) -> str:
    normalized_project_id = _normalize_project_record_token(project_id, limit=120)
    return f"{_PROJECT_REQUIREMENT_RECORDS_CACHE_SET_PREFIX}{normalized_project_id}:keys"


def _project_requirement_records_cache_key(
    project_id: str,
    *,
    employee_id: str = "",
    query: str = "",
    memory_type: str = "",
    limit: int = 200,
) -> str:
    payload = json.dumps(
        {
            "project_id": _normalize_project_record_token(project_id, limit=120),
            "employee_id": _normalize_project_record_token(employee_id, limit=80),
            "query": _normalize_project_record_token(query, limit=200),
            "memory_type": _normalize_project_record_token(memory_type, limit=80),
            "limit": max(1, min(int(limit or 200), 500)),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:20]
    return f"{_PROJECT_REQUIREMENT_RECORDS_CACHE_PREFIX}{digest}"


async def _load_project_requirement_records_cache(cache_key: str) -> dict[str, Any] | None:
    now = time.monotonic()
    cached_local = _project_requirement_records_local_cache.get(cache_key)
    if cached_local and cached_local[0] > now:
        return dict(cached_local[1])
    if cached_local:
        _project_requirement_records_local_cache.pop(cache_key, None)

    try:
        redis_client = await get_redis_client()
        raw = await redis_client.get(cache_key)
    except Exception:
        return None
    if not raw:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    _project_requirement_records_local_cache[cache_key] = (
        now + _PROJECT_REQUIREMENT_RECORDS_CACHE_TTL_SECONDS,
        payload,
    )
    return dict(payload)


async def _save_project_requirement_records_cache(
    project_id: str,
    cache_key: str,
    payload: dict[str, Any],
) -> None:
    _project_requirement_records_local_cache[cache_key] = (
        time.monotonic() + _PROJECT_REQUIREMENT_RECORDS_CACHE_TTL_SECONDS,
        dict(payload),
    )
    try:
        redis_client = await get_redis_client()
        await redis_client.set(
            cache_key,
            json.dumps(payload, ensure_ascii=False),
            ex=_PROJECT_REQUIREMENT_RECORDS_CACHE_TTL_SECONDS,
        )
        project_set_key = _project_requirement_records_cache_set_key(project_id)
        await redis_client.sadd(project_set_key, cache_key)
        await redis_client.expire(project_set_key, _PROJECT_REQUIREMENT_RECORDS_CACHE_TTL_SECONDS)
    except Exception:
        return


async def _invalidate_project_requirement_records_cache(project_id: str) -> None:
    normalized_project_id = _normalize_project_record_token(project_id, limit=120)
    if not normalized_project_id:
        return
    local_keys = [
        key
        for key in _project_requirement_records_local_cache.keys()
        if key.startswith(_PROJECT_REQUIREMENT_RECORDS_CACHE_PREFIX)
    ]
    for key in local_keys:
        _project_requirement_records_local_cache.pop(key, None)
    project_set_key = _project_requirement_records_cache_set_key(normalized_project_id)
    try:
        redis_client = await get_redis_client()
        cache_keys = await redis_client.smembers(project_set_key) or set()
        normalized_keys = [
            _normalize_project_record_token(item, limit=240)
            for item in cache_keys
            if _normalize_project_record_token(item, limit=240)
        ]
        if normalized_keys:
            await redis_client.delete(*normalized_keys)
        await redis_client.delete(project_set_key)
    except Exception:
        return


def _project_memory_matches_project(memory: Any, project: ProjectConfig) -> bool:
    project_id = _normalize_project_record_token(getattr(project, "id", ""), limit=120)
    project_tokens = {
        project_id.lower(),
        _normalize_project_record_token(getattr(project, "name", ""), limit=160).lower(),
    }
    binding = _parse_project_memory_binding(
        getattr(memory, "content", ""),
        getattr(memory, "purpose_tags", ()),
    )
    bound_project_id = _normalize_project_record_token(binding.get("project_id"), limit=120)
    if bound_project_id:
        return bound_project_id == project_id
    memory_project_name = _normalize_project_record_token(getattr(memory, "project_name", ""), limit=160).lower()
    return bool(memory_project_name) and memory_project_name in project_tokens


def _is_project_trajectory_memory(memory: Any) -> bool:
    purpose_tags = set(_normalize_project_record_tags(getattr(memory, "purpose_tags", ())))
    if "work-facts" in purpose_tags or "session-event" in purpose_tags:
        return True
    content = _normalize_project_record_token(getattr(memory, "content", ""), limit=200).lstrip()
    return content.startswith("[工作事实]") or content.startswith("[会话事件]")


def _project_memory_sort_key(memory: Any, *, query: str = "") -> tuple[Any, ...]:
    created_at = _normalize_project_record_token(getattr(memory, "created_at", ""), limit=40)
    if str(query or "").strip():
        return (float(getattr(memory, "importance", 0.0) or 0.0), created_at)
    return (created_at,)


def _project_active_member_ids(project_id: str) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for member in project_store.list_members(project_id):
        if not bool(getattr(member, "enabled", True)):
            continue
        employee_id = _normalize_project_record_token(getattr(member, "employee_id", ""), limit=80)
        if not employee_id or employee_id in seen:
            continue
        seen.add(employee_id)
        result.append(employee_id)
    return result


def _collect_project_related_memories(
    project: ProjectConfig,
    *,
    employee_id: str = "",
    query: str = "",
) -> tuple[list[Any], list[Any]]:
    normalized_employee_id = _normalize_project_record_token(employee_id, limit=80)
    query_text = _normalize_project_record_token(query, limit=200).lower()
    target_employee_ids = _project_active_member_ids(project.id)
    if normalized_employee_id:
        if normalized_employee_id not in target_employee_ids:
            return [], []
        target_employee_ids = [normalized_employee_id]

    deduped: dict[str, Any] = {}
    for current_employee_id in target_employee_ids:
        for memory in memory_store.list_by_employee(current_employee_id) or []:
            if not _project_memory_matches_project(memory, project):
                continue
            content = _normalize_project_record_token(getattr(memory, "content", ""))
            if query_text and query_text not in content.lower():
                continue
            memory_id = _normalize_project_record_token(getattr(memory, "id", ""), limit=80)
            dedupe_key = memory_id or json.dumps(
                [
                    current_employee_id,
                    _normalize_project_record_token(getattr(memory, "project_name", ""), limit=160),
                    _normalize_project_record_token(getattr(memory, "created_at", ""), limit=40),
                    content,
                ],
                ensure_ascii=False,
            )
            if dedupe_key not in deduped:
                deduped[dedupe_key] = memory

    items = list(deduped.values())
    items.sort(key=lambda item: _project_memory_sort_key(item, query=query_text), reverse=True)
    memories = [item for item in items if not _is_project_trajectory_memory(item)]
    trajectories = [item for item in items if _is_project_trajectory_memory(item)]
    return memories, trajectories


def _project_employee_name_map(project_id: str) -> dict[str, str]:
    employee_names: dict[str, str] = {}
    for member in project_store.list_members(project_id):
        if not bool(getattr(member, "enabled", True)):
            continue
        employee_id = _normalize_project_record_token(getattr(member, "employee_id", ""), limit=80)
        if not employee_id:
            continue
        employee = employee_store.get(employee_id)
        employee_names[employee_id] = _normalize_project_record_token(
            getattr(employee, "name", ""),
            limit=120,
        ) or employee_id
    return employee_names


def _summarize_project_work_session(events: list[Any]) -> dict[str, Any]:
    if not events:
        return {}
    ordered = sorted(
        events,
        key=lambda item: (
            _normalize_project_record_token(getattr(item, "created_at", ""), limit=40),
            _normalize_project_record_token(getattr(item, "id", ""), limit=80),
        ),
        reverse=True,
    )
    latest = ordered[0]
    phases: list[str] = []
    steps: list[str] = []
    changed_files: list[str] = []
    verification: list[str] = []
    risks: list[str] = []
    next_steps: list[str] = []
    event_types: list[str] = []
    task_tree_session_ids: list[str] = []
    task_node_titles: list[str] = []
    for item in ordered:
        phase = _normalize_project_record_token(getattr(item, "phase", ""), limit=120)
        step = _normalize_project_record_token(getattr(item, "step", ""), limit=200)
        event_type = _normalize_project_record_token(getattr(item, "event_type", ""), limit=80)
        task_tree_session_id = _normalize_project_record_token(
            getattr(item, "task_tree_session_id", ""),
            limit=80,
        )
        task_node_title = _normalize_project_record_token(
            getattr(item, "task_node_title", ""),
            limit=200,
        )
        if phase and phase not in phases:
            phases.append(phase)
        if step and step not in steps:
            steps.append(step)
        if event_type and event_type not in event_types:
            event_types.append(event_type)
        if task_tree_session_id and task_tree_session_id not in task_tree_session_ids:
            task_tree_session_ids.append(task_tree_session_id)
        if task_node_title and task_node_title not in task_node_titles:
            task_node_titles.append(task_node_title)
        for source, target in (
            (getattr(item, "changed_files", []) or [], changed_files),
            (getattr(item, "verification", []) or [], verification),
            (getattr(item, "risks", []) or [], risks),
            (getattr(item, "next_steps", []) or [], next_steps),
        ):
            for value in source:
                normalized = _normalize_project_record_token(value, limit=500)
                if normalized and normalized not in target:
                    target.append(normalized)
    return {
        "session_id": _normalize_project_record_token(getattr(latest, "session_id", ""), limit=120),
        "project_id": _normalize_project_record_token(getattr(latest, "project_id", ""), limit=80),
        "project_name": _normalize_project_record_token(getattr(latest, "project_name", ""), limit=120),
        "employee_id": _normalize_project_record_token(getattr(latest, "employee_id", ""), limit=80),
        "latest_status": _normalize_project_record_token(getattr(latest, "status", ""), limit=80),
        "latest_event_type": _normalize_project_record_token(getattr(latest, "event_type", ""), limit=80),
        "goal": _normalize_project_record_token(getattr(latest, "goal", ""), limit=400),
        "task_tree_session_id": _normalize_project_record_token(
            getattr(latest, "task_tree_session_id", ""),
            limit=80,
        ),
        "task_tree_chat_session_id": _normalize_project_record_token(
            getattr(latest, "task_tree_chat_session_id", ""),
            limit=80,
        ),
        "task_node_id": _normalize_project_record_token(getattr(latest, "task_node_id", ""), limit=80),
        "task_node_title": _normalize_project_record_token(
            getattr(latest, "task_node_title", ""),
            limit=200,
        ),
        "phases": phases,
        "steps": steps,
        "event_types": event_types,
        "task_tree_session_ids": task_tree_session_ids,
        "task_node_titles": task_node_titles,
        "changed_files": changed_files,
        "verification": verification,
        "risks": risks,
        "next_steps": next_steps,
        "event_count": len(ordered),
        "updated_at": _normalize_project_record_token(getattr(latest, "updated_at", ""), limit=40),
        "created_at": _normalize_project_record_token(getattr(ordered[-1], "created_at", ""), limit=40),
    }


def _serialize_project_work_session_summary(summary: dict[str, Any], employee_names: dict[str, str]) -> dict[str, Any]:
    payload = dict(summary or {})
    employee_id = _normalize_project_record_token(payload.get("employee_id"), limit=80)
    payload["employee_id"] = employee_id
    payload["employee_name"] = employee_names.get(employee_id, employee_id) if employee_id else "团队协作"
    return payload


def _serialize_project_work_session_event(item: Any, employee_names: dict[str, str]) -> dict[str, Any]:
    employee_id = _normalize_project_record_token(getattr(item, "employee_id", ""), limit=80)
    return {
        **asdict(item),
        "employee_name": employee_names.get(employee_id, employee_id) if employee_id else "团队协作",
    }


def _extract_project_memory_section(content: Any, label: str) -> str:
    text = _normalize_project_record_token(content)
    if not text or not label:
        return ""
    pattern = rf"\[{re.escape(str(label).strip())}\]\s*([^\n]+)"
    matched = re.search(pattern, text)
    if not matched:
        return ""
    return _normalize_project_record_token(matched.group(1), limit=400)


def _extract_project_memory_inline_binding(content: Any, key: str, *, limit: int = 120) -> str:
    text = _normalize_project_record_token(content)
    normalized_key = str(key or "").strip()
    if not text or not normalized_key:
        return ""
    patterns = (
        rf"(?:^|[\s,;]){re.escape(normalized_key)}=([A-Za-z0-9_.:-]+)",
        rf'"{re.escape(normalized_key)}"\s*:\s*"([^"]+)"',
    )
    for pattern in patterns:
        matched = re.search(pattern, text)
        if matched:
            return _normalize_project_record_token(matched.group(1), limit=limit)
    return ""


def _extract_project_memory_tag_binding(purpose_tags: Any, prefix: str, *, limit: int = 120) -> str:
    normalized_prefix = str(prefix or "").strip().lower()
    if not normalized_prefix:
        return ""
    for item in purpose_tags or ():
        tag = str(item or "").strip()
        if not tag:
            continue
        if tag.lower().startswith(normalized_prefix):
            return _normalize_project_record_token(tag[len(prefix):], limit=limit)
    return ""


def _parse_project_memory_binding(content: Any, purpose_tags: Any = ()) -> dict[str, str]:
    text = _normalize_project_record_token(content)
    result = {
        "project_id": _extract_project_memory_section(text, "项目ID")
        or _extract_project_memory_tag_binding(purpose_tags, "project-id:", limit=120)
        or _extract_project_memory_inline_binding(text, "project_id", limit=120),
        "project_name": _extract_project_memory_section(text, "项目名称")
        or _extract_project_memory_inline_binding(text, "project_name", limit=160),
        "chat_session_id": _extract_project_memory_section(text, "关联会话")
        or _extract_project_memory_tag_binding(purpose_tags, "chat-session:", limit=120)
        or _extract_project_memory_inline_binding(text, "chat_session_id", limit=120),
        "task_tree_session_id": _extract_project_memory_inline_binding(text, "task_tree_session_id", limit=80),
        "task_tree_chat_session_id": _extract_project_memory_inline_binding(text, "task_tree_chat_session_id", limit=80),
        "task_node_id": _extract_project_memory_inline_binding(text, "task_node_id", limit=80),
        "task_node_title": _extract_project_memory_inline_binding(text, "task_node_title", limit=200),
        "root_goal": _extract_project_memory_inline_binding(text, "root_goal", limit=400),
        "session_id": _extract_project_memory_inline_binding(text, "session_id", limit=120),
    }
    if not text:
        return {key: value for key, value in result.items() if value}
    matched = re.search(r"\[执行轨迹JSON\]\s*([^\n]+)", text)
    if matched:
        try:
            payload = json.loads(str(matched.group(1) or "").strip())
        except json.JSONDecodeError:
            payload = {}
        if isinstance(payload, dict):
            current_node = payload.get("current_node") if isinstance(payload.get("current_node"), dict) else {}
            result.update(
                {
                    "project_id": _normalize_project_record_token(
                        payload.get("project_id") or result.get("project_id"),
                        limit=120,
                    ),
                    "project_name": _normalize_project_record_token(
                        payload.get("project_name") or result.get("project_name"),
                        limit=160,
                    ),
                    "chat_session_id": _normalize_project_record_token(
                        payload.get("chat_session_id") or result.get("chat_session_id"),
                        limit=120,
                    ),
                    "task_tree_session_id": _normalize_project_record_token(
                        payload.get("task_tree_session_id") or payload.get("id"),
                        limit=80,
                    ),
                    "task_tree_chat_session_id": _normalize_project_record_token(
                        payload.get("task_tree_chat_session_id")
                        or payload.get("source_chat_session_id")
                        or payload.get("chat_session_id"),
                        limit=80,
                    ),
                    "task_node_id": _normalize_project_record_token(
                        payload.get("task_node_id") or current_node.get("id"),
                        limit=80,
                    ),
                    "task_node_title": _normalize_project_record_token(
                        payload.get("task_node_title") or current_node.get("title") or result.get("task_node_title"),
                        limit=200,
                    ),
                    "root_goal": _normalize_project_record_token(
                        payload.get("root_goal") or payload.get("title") or result.get("root_goal"),
                        limit=400,
                    ),
                    "session_id": _normalize_project_record_token(
                        payload.get("session_id") or result.get("session_id"),
                        limit=120,
                    ),
                }
            )
    return {key: value for key, value in result.items() if value}


def _serialize_project_memory_record(item: Any) -> dict[str, Any]:
    payload = serialize_memory(item)
    payload.update(
        _parse_project_memory_binding(
            getattr(item, "content", ""),
            getattr(item, "purpose_tags", ()),
        )
    )
    return payload


def _project_memory_candidate_records(employee_id: str, *, limit: int = 200) -> list[Any]:
    recent = getattr(memory_store, "recent", None)
    list_by_employee = getattr(memory_store, "list_by_employee", None)
    if callable(recent):
        try:
            return list(recent(employee_id, limit) or [])
        except Exception:
            return []
    if callable(list_by_employee):
        try:
            return list(list_by_employee(employee_id) or [])[:limit]
        except Exception:
            return []
    return []


def _project_memory_fingerprint_tag(*parts: Any) -> str:
    normalized_parts = [
        re.sub(r"\s+", " ", str(part or "").strip())[:4000]
        for part in parts
        if str(part or "").strip()
    ]
    if not normalized_parts:
        return ""
    digest = hashlib.sha1("|".join(normalized_parts).encode("utf-8")).hexdigest()[:20]
    return f"fp:{digest}"


def _normalize_project_requirement_goal_key(value: Any) -> str:
    return re.sub(r"\s+", " ", _normalize_project_record_token(value, limit=1000)).strip().lower()


def _is_query_cli_chat_session_id(value: Any) -> bool:
    return _normalize_project_record_token(value, limit=120).lower().startswith("query-cli.")


def _parse_project_record_datetime(value: Any) -> float | None:
    normalized = _normalize_project_record_token(value, limit=40)
    if not normalized:
        return None
    candidate = normalized[:-1] + "+00:00" if normalized.endswith("Z") else normalized
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _project_requirement_record_usernames(record: dict[str, Any]) -> set[str]:
    usernames: set[str] = set()
    for round_item in record.get("rounds") or []:
        if not isinstance(round_item, dict):
            continue
        task_tree = round_item.get("taskTree") if isinstance(round_item.get("taskTree"), dict) else {}
        username = _normalize_project_record_token(task_tree.get("username"), limit=80)
        if username:
            usernames.add(username)
    return usernames


def _project_requirement_record_chat_session_id(record: dict[str, Any]) -> str:
    for key in ("detailRound", "currentRound", "latestRound"):
        round_item = record.get(key)
        if not isinstance(round_item, dict):
            continue
        chat_session_id = _normalize_project_record_token(round_item.get("chatSessionId"), limit=120)
        if chat_session_id:
            return chat_session_id
    for round_item in record.get("rounds") or []:
        if not isinstance(round_item, dict):
            continue
        chat_session_id = _normalize_project_record_token(round_item.get("chatSessionId"), limit=120)
        if chat_session_id:
            return chat_session_id
    return ""


def _project_requirement_record_timestamp(record: dict[str, Any]) -> float | None:
    for key in ("createdAt", "updatedAt"):
        parsed = _parse_project_record_datetime(record.get(key))
        if parsed is not None:
            return parsed
    return None


def _dedupe_query_cli_requirement_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(records) < 2:
        return records

    duplicate_window_seconds = 15 * 60
    grouped_by_goal: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        goal_key = _normalize_project_requirement_goal_key(record.get("rootGoal"))
        if not goal_key:
            continue
        grouped_by_goal.setdefault(goal_key, []).append(record)

    dropped_ids: set[str] = set()
    for grouped_records in grouped_by_goal.values():
        if len(grouped_records) < 2:
            continue
        query_cli_records = [
            record
            for record in grouped_records
            if _is_query_cli_chat_session_id(_project_requirement_record_chat_session_id(record))
        ]
        formal_records = [
            record
            for record in grouped_records
            if not _is_query_cli_chat_session_id(_project_requirement_record_chat_session_id(record))
        ]
        if not query_cli_records or not formal_records:
            continue
        for query_cli_record in query_cli_records:
            query_cli_id = _normalize_project_record_token(query_cli_record.get("id"), limit=80)
            if not query_cli_id:
                continue
            query_cli_timestamp = _project_requirement_record_timestamp(query_cli_record)
            query_cli_usernames = _project_requirement_record_usernames(query_cli_record)
            if query_cli_timestamp is None:
                continue
            for formal_record in formal_records:
                formal_timestamp = _project_requirement_record_timestamp(formal_record)
                if formal_timestamp is None:
                    continue
                formal_usernames = _project_requirement_record_usernames(formal_record)
                if (
                    query_cli_usernames
                    and formal_usernames
                    and not query_cli_usernames.intersection(formal_usernames)
                ):
                    continue
                if abs(formal_timestamp - query_cli_timestamp) <= duplicate_window_seconds:
                    dropped_ids.add(query_cli_id)
                    break

    if not dropped_ids:
        return records
    return [
        record
        for record in records
        if _normalize_project_record_token(record.get("id"), limit=80) not in dropped_ids
    ]


def _collect_all_project_related_memories(project: ProjectConfig) -> list[Any]:
    memories, trajectory_memories = _collect_project_related_memories(project)
    return [*memories, *trajectory_memories]


def _build_project_requirement_record_delete_index(project: ProjectConfig) -> dict[str, dict[str, Any]]:
    sessions = project_chat_task_store.list_by_project(project.id, limit=500) or []
    chain_index: dict[str, dict[str, Any]] = {}
    session_id_to_chain: dict[str, str] = {}
    chat_session_id_to_chain: dict[str, str] = {}

    for session in sessions:
        session_id = _normalize_project_record_token(getattr(session, "id", ""), limit=80)
        if not session_id:
            continue
        source_session_id = _normalize_project_record_token(
            getattr(session, "source_session_id", ""),
            limit=80,
        )
        chain_id = source_session_id or session_id
        entry = chain_index.setdefault(
            chain_id,
            {
                "chain_id": chain_id,
                "task_sessions": [],
                "task_session_ids": set(),
                "task_chat_session_ids": set(),
                "memory_ids": set(),
                "work_session_ids": set(),
            },
        )
        entry["task_sessions"].append(session)
        entry["task_session_ids"].add(session_id)
        session_id_to_chain[session_id] = chain_id
        for chat_session_id in (
            _normalize_project_record_token(getattr(session, "chat_session_id", ""), limit=80),
            _normalize_project_record_token(getattr(session, "source_chat_session_id", ""), limit=80),
        ):
            if not chat_session_id:
                continue
            entry["task_chat_session_ids"].add(chat_session_id)
            chat_session_id_to_chain.setdefault(chat_session_id, chain_id)

    for memory in _collect_all_project_related_memories(project):
        memory_id = _normalize_project_record_token(getattr(memory, "id", ""), limit=80)
        if not memory_id:
            continue
        binding = _parse_project_memory_binding(
            getattr(memory, "content", ""),
            getattr(memory, "purpose_tags", ()),
        )
        chain_id = session_id_to_chain.get(
            _normalize_project_record_token(binding.get("task_tree_session_id"), limit=80),
            "",
        )
        if not chain_id:
            for chat_session_id in (
                binding.get("task_tree_chat_session_id"),
                binding.get("chat_session_id"),
            ):
                normalized_chat_session_id = _normalize_project_record_token(chat_session_id, limit=80)
                if normalized_chat_session_id and normalized_chat_session_id in chat_session_id_to_chain:
                    chain_id = chat_session_id_to_chain[normalized_chat_session_id]
                    break
        if not chain_id:
            normalized_session_id = _normalize_project_record_token(binding.get("session_id"), limit=120)
            if normalized_session_id and normalized_session_id in chain_index:
                chain_id = normalized_session_id
        if not chain_id:
            continue
        chain_index[chain_id]["memory_ids"].add(memory_id)

    list_all_work_events = getattr(work_session_store, "list_all", None)
    if callable(list_all_work_events):
        work_events = list_all_work_events() or []
    else:
        work_events = work_session_store.list_events(project_id=project.id, limit=500)
    for item in work_events:
        if _normalize_project_record_token(getattr(item, "project_id", ""), limit=80) != project.id:
            continue
        work_session_id = _normalize_project_record_token(getattr(item, "session_id", ""), limit=120)
        if not work_session_id:
            continue
        chain_id = session_id_to_chain.get(
            _normalize_project_record_token(getattr(item, "task_tree_session_id", ""), limit=80),
            "",
        )
        if not chain_id:
            chain_id = chat_session_id_to_chain.get(
                _normalize_project_record_token(getattr(item, "task_tree_chat_session_id", ""), limit=80),
                "",
            )
        if not chain_id and work_session_id in chain_index:
            chain_id = work_session_id
        if not chain_id:
            continue
        chain_index[chain_id]["work_session_ids"].add(work_session_id)

    return chain_index


def _is_completed_like_project_status(value: Any) -> bool:
    normalized = _normalize_project_record_token(value, limit=40).lower()
    return normalized in {"completed", "done"}


def _get_project_task_session_status_tag_type(value: Any) -> str:
    normalized = _normalize_project_record_token(value, limit=40).lower()
    if normalized == "done":
        return "success"
    if normalized == "blocked":
        return "danger"
    if normalized == "verifying":
        return "warning"
    if normalized == "paused":
        return "info"
    if normalized == "in_progress":
        return ""
    return "info"


def _get_project_task_session_status_label(value: Any) -> str:
    normalized = _normalize_project_record_token(value, limit=40).lower()
    if normalized == "done":
        return "已完成"
    if normalized == "blocked":
        return "阻塞"
    if normalized == "verifying":
        return "验证中"
    if normalized == "paused":
        return "已暂停"
    if normalized == "in_progress":
        return "进行中"
    if normalized == "pending":
        return "待开始"
    return _normalize_project_record_token(value, limit=80) or "待开始"


def _is_project_task_tree_finalized(task_tree: dict[str, Any] | None) -> bool:
    if not isinstance(task_tree, dict):
        return False
    status = _normalize_project_record_token(task_tree.get("status"), limit=40).lower()
    progress_percent = int(task_tree.get("progress_percent") or 0)
    stats = task_tree.get("stats") if isinstance(task_tree.get("stats"), dict) else {}
    leaf_total = int(task_tree.get("leaf_total") or stats.get("leaf_total") or 0)
    done_leaf_total = int(task_tree.get("done_leaf_total") or stats.get("done_leaf_total") or 0)
    if bool(task_tree.get("is_archived")) and status == "done":
        return True
    if status != "done":
        return False
    if progress_percent >= 100:
        return True
    return leaf_total > 0 and done_leaf_total >= leaf_total


def _resolve_project_task_tree_progress_percent(task_tree: dict[str, Any] | None) -> int:
    if not isinstance(task_tree, dict):
        return 0
    explicit_progress = int(task_tree.get("progress_percent") or 0)
    if explicit_progress > 0:
        return explicit_progress
    if _is_project_task_tree_finalized(task_tree):
        return 100
    stats = task_tree.get("stats") if isinstance(task_tree.get("stats"), dict) else {}
    leaf_total = int(task_tree.get("leaf_total") or stats.get("leaf_total") or 0)
    done_leaf_total = int(task_tree.get("done_leaf_total") or stats.get("done_leaf_total") or 0)
    if leaf_total > 0 and done_leaf_total > 0:
        return round((done_leaf_total / leaf_total) * 100)
    return 0


def _resolve_project_requirement_round_display_status(round_payload: dict[str, Any]) -> str:
    if not isinstance(round_payload, dict):
        return "pending"
    raw_status = _normalize_project_record_token(round_payload.get("status"), limit=40).lower()
    if bool(round_payload.get("isFinalized")) or raw_status == "done":
        return "done"
    if raw_status == "blocked":
        return "blocked"
    primary_work_session = (
        round_payload.get("primaryWorkSession")
        if isinstance(round_payload.get("primaryWorkSession"), dict)
        else {}
    )
    work_session_status = _normalize_project_record_token(primary_work_session.get("latest_status"), limit=40).lower()
    if raw_status in {"pending", "in_progress", "verifying"} and _is_completed_like_project_status(work_session_status):
        return "paused"
    return raw_status or "pending"


def _is_project_requirement_round_placeholder(round_payload: dict[str, Any]) -> bool:
    if not isinstance(round_payload, dict) or bool(round_payload.get("isFinalized")):
        return False
    raw_status = _normalize_project_record_token(round_payload.get("status"), limit=40).lower()
    if raw_status != "pending":
        return False
    if int(round_payload.get("progressPercent") or 0) > 0:
        return False
    if isinstance(round_payload.get("primaryMemory"), dict) and round_payload["primaryMemory"]:
        return False
    work_sessions = round_payload.get("workSessions")
    return not (isinstance(work_sessions, list) and work_sessions)


def _build_project_requirement_records(
    project: ProjectConfig,
    *,
    employee_id: str = "",
    query: str = "",
    memory_type: str = "",
    limit: int = 200,
) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 200), 500))
    normalized_employee_id = _normalize_project_record_token(employee_id, limit=80)
    query_text = _normalize_project_record_token(query, limit=200).lower()
    normalized_memory_type = _normalize_project_record_token(memory_type, limit=80)

    task_sessions = list_project_task_tree_summaries(project.id, safe_limit)
    employee_names = _project_employee_name_map(project.id)

    summary_limit = max(safe_limit * 8, safe_limit)
    work_events = work_session_store.list_events(
        project_id=project.id,
        employee_id=normalized_employee_id,
        query=query_text,
        limit=summary_limit,
    )
    grouped_work_events: dict[str, list[Any]] = {}
    for item in work_events:
        session_id = _normalize_project_record_token(getattr(item, "session_id", ""), limit=120)
        if not session_id:
            continue
        grouped_work_events.setdefault(session_id, []).append(item)

    work_session_summaries = [
        _serialize_project_work_session_summary(_summarize_project_work_session(items), employee_names)
        for items in grouped_work_events.values()
        if items
    ]
    work_session_summaries.sort(
        key=lambda item: _normalize_project_record_token(item.get("updated_at"), limit=40),
        reverse=True,
    )

    work_sessions_by_task_session: dict[str, list[dict[str, Any]]] = {}
    work_sessions_by_chat_session: dict[str, list[dict[str, Any]]] = {}
    for item in work_session_summaries:
        task_session_id = _normalize_project_record_token(item.get("task_tree_session_id"), limit=80)
        task_chat_session_id = _normalize_project_record_token(item.get("task_tree_chat_session_id"), limit=80)
        if task_session_id:
            work_sessions_by_task_session.setdefault(task_session_id, []).append(item)
        if task_chat_session_id:
            work_sessions_by_chat_session.setdefault(task_chat_session_id, []).append(item)

    serialized_memories: list[dict[str, Any]] = []
    if normalized_employee_id or query_text or normalized_memory_type:
        memories, _trajectory_memories = _collect_project_related_memories(
            project,
            employee_id=normalized_employee_id,
            query=query_text,
        )
        serialized_memories = [
            _serialize_project_memory_record(item)
            for item in memories
            if not normalized_memory_type
            or _normalize_project_record_token(getattr(item, "type", ""), limit=80) == normalized_memory_type
        ]

    memories_by_task_session: dict[str, list[dict[str, Any]]] = {}
    memories_by_chat_session: dict[str, list[dict[str, Any]]] = {}
    for item in serialized_memories:
        task_session_id = _normalize_project_record_token(item.get("task_tree_session_id"), limit=80)
        chat_session_id = _normalize_project_record_token(
            item.get("task_tree_chat_session_id") or item.get("chat_session_id"),
            limit=80,
        )
        if task_session_id:
            memories_by_task_session.setdefault(task_session_id, []).append(item)
        if chat_session_id:
            memories_by_chat_session.setdefault(chat_session_id, []).append(item)

    grouped_records: dict[str, list[dict[str, Any]]] = {}
    for summary in task_sessions:
        if not isinstance(summary, dict):
            continue
        session_id = _normalize_project_record_token(summary.get("id"), limit=80)
        if not session_id:
            continue
        source_session_id = _normalize_project_record_token(summary.get("source_session_id"), limit=80)
        chat_session_id = _normalize_project_record_token(
            summary.get("source_chat_session_id") or summary.get("chat_session_id"),
            limit=80,
        )
        memory_matches = list(memories_by_task_session.get(session_id, []))
        if chat_session_id:
            for item in memories_by_chat_session.get(chat_session_id, []):
                if item not in memory_matches:
                    memory_matches.append(item)
        work_sessions = list(work_sessions_by_task_session.get(session_id, []))
        if chat_session_id:
            for item in work_sessions_by_chat_session.get(chat_session_id, []):
                if item not in work_sessions:
                    work_sessions.append(item)
        primary_memory = (
            sorted(
                memory_matches,
                key=lambda item: _normalize_project_record_token(item.get("created_at"), limit=40),
                reverse=True,
            )[0]
            if memory_matches
            else None
        )
        task_tree = dict(summary)
        round_payload = {
            "id": session_id,
            "sessionId": session_id,
            "sourceSessionId": source_session_id,
            "chatSessionId": chat_session_id,
            "taskTree": task_tree,
            "rootNode": None,
            "rootGoal": _normalize_project_record_token(summary.get("root_goal") or summary.get("title"), limit=1000),
            "title": _normalize_project_record_token(summary.get("title"), limit=200),
            "recordKind": _normalize_project_record_token(summary.get("record_kind"), limit=40) or "requirement",
            "roundIndex": max(1, int(summary.get("round_index") or 1)),
            "status": _normalize_project_record_token(summary.get("status"), limit=40) or "pending",
            "progressPercent": _resolve_project_task_tree_progress_percent(task_tree),
            "currentNodeId": _normalize_project_record_token(summary.get("current_node_id"), limit=80),
            "currentNodeTitle": _normalize_project_record_token(summary.get("current_node_title"), limit=200),
            "leafTotal": int(summary.get("leaf_total") or 0),
            "doneLeafTotal": int(summary.get("done_leaf_total") or 0),
            "nodeTotal": int(summary.get("node_total") or 0),
            "isArchived": bool(summary.get("is_archived")),
            "createdAt": _normalize_project_record_token(summary.get("created_at"), limit=40),
            "updatedAt": _normalize_project_record_token(summary.get("updated_at"), limit=40),
            "primaryMemory": primary_memory,
            "workSessions": work_sessions,
            "primaryWorkSession": work_sessions[0] if work_sessions else None,
            "isFinalized": _is_project_task_tree_finalized(task_tree),
        }
        round_payload["displayStatus"] = _resolve_project_requirement_round_display_status(round_payload)
        if round_payload["isFinalized"]:
            summary_text = (
                _normalize_project_record_token(
                    (primary_memory or {}).get("latest_outcome")
                    or task_tree.get("current_node_title"),
                    limit=1000,
                )
                or "全部计划节点已完成并写入验证结果。"
            )
        else:
            summary_text = (
                _normalize_project_record_token(
                    (primary_memory or {}).get("display_preview")
                    or round_payload["currentNodeTitle"],
                    limit=1000,
                )
                or "计划已入树，当前按节点推进并逐项验证。"
            )
        round_payload["summaryText"] = summary_text
        chain_key = source_session_id or session_id
        grouped_records.setdefault(chain_key, []).append(round_payload)

    records: list[dict[str, Any]] = []
    for chain_id, rounds in grouped_records.items():
        sorted_rounds = sorted(
            rounds,
            key=lambda item: (
                int(item.get("roundIndex") or 1),
                _normalize_project_record_token(item.get("createdAt"), limit=40),
            ),
        )
        latest_round = sorted_rounds[-1] if sorted_rounds else None
        current_round = latest_round
        for item in reversed(sorted_rounds):
            if not bool(item.get("isFinalized")):
                current_round = item
                break
        if _is_project_requirement_round_placeholder(current_round or {}):
            active_round_with_progress = next(
                (
                    item
                    for item in reversed(sorted_rounds)
                    if not bool(item.get("isFinalized")) and not _is_project_requirement_round_placeholder(item)
                ),
                None,
            )
            finalized_round = next((item for item in reversed(sorted_rounds) if bool(item.get("isFinalized"))), None)
            current_round = active_round_with_progress or finalized_round or current_round

        actor_names: list[str] = []
        for item in sorted_rounds:
            primary_memory = item.get("primaryMemory") if isinstance(item.get("primaryMemory"), dict) else {}
            primary_work_session = item.get("workSessions") if isinstance(item.get("workSessions"), list) else []
            for actor in [
                _normalize_project_record_token(primary_memory.get("employee_name") or primary_memory.get("employee_id"), limit=120),
                *[
                    _normalize_project_record_token(
                        entry.get("employee_name") or entry.get("employee_id"),
                        limit=120,
                    )
                    for entry in primary_work_session
                    if isinstance(entry, dict)
                ],
            ]:
                if actor and actor not in actor_names:
                    actor_names.append(actor)

        memory_types = [
            item
            for item in {
                _normalize_project_record_token(
                    ((round_item.get("primaryMemory") or {}).get("type") if isinstance(round_item.get("primaryMemory"), dict) else ""),
                    limit=80,
                )
                for round_item in sorted_rounds
            }
            if item
        ]

        current_or_latest = current_round or latest_round or {}
        record_payload = {
            "id": chain_id,
            "rootGoal": _normalize_project_record_token(
                (current_round or {}).get("rootGoal") or (latest_round or {}).get("rootGoal"),
                limit=1000,
            ),
            "actorNames": actor_names,
            "actorLabel": " / ".join(actor_names) if actor_names else "未绑定执行人",
            "latestRound": latest_round,
            "currentRound": current_round,
            "detailRound": current_or_latest,
            "rounds": sorted_rounds,
            "repairRoundCount": sum(1 for item in sorted_rounds if item.get("recordKind") == "repair"),
            "activeRoundCount": sum(
                1
                for item in sorted_rounds
                if not bool(item.get("isFinalized")) and not _is_project_requirement_round_placeholder(item)
            ),
            "memoryTypes": memory_types,
            "status": _normalize_project_record_token(current_or_latest.get("displayStatus"), limit=40) or "pending",
            "statusLabel": _get_project_task_session_status_label(current_or_latest.get("displayStatus")),
            "statusTagType": _get_project_task_session_status_tag_type(current_or_latest.get("displayStatus")),
            "progressPercent": int(current_or_latest.get("progressPercent") or 0),
            "currentFocus": _normalize_project_record_token(
                current_or_latest.get("currentNodeTitle") or (latest_round or {}).get("currentNodeTitle"),
                limit=200,
            ) or "等待进入计划节点",
            "completionGate": (
                "全部计划节点已完成并通过验证，本轮可视为结束。"
                if bool(current_or_latest.get("isFinalized"))
                else "只有所有计划节点完成并写入验证结果，需求才算真正结束。"
            ),
            "summaryText": _normalize_project_record_token(
                current_or_latest.get("summaryText") or (latest_round or {}).get("summaryText"),
                limit=1000,
            ),
            "roundDigest": (
                f"{'最近' if bool(current_or_latest.get('isFinalized')) else '当前'}第 {max(1, int(current_or_latest.get('roundIndex') or len(sorted_rounds) or 1))} 轮，共 {len(sorted_rounds)} 轮"
                if len(sorted_rounds) > 1
                else "单轮处理"
            ),
            "progressDigest": (
                f"{max(0, int(current_or_latest.get('doneLeafTotal') or 0))}/"
                f"{max(0, int(current_or_latest.get('leafTotal') or current_or_latest.get('nodeTotal') or 0))} 已完成"
            ),
            "detailWorkSessionCount": len(current_or_latest.get("workSessions") or []),
            "updatedAt": _normalize_project_record_token(
                current_or_latest.get("updatedAt") or (latest_round or {}).get("updatedAt"),
                limit=40,
            ),
            "createdAt": _normalize_project_record_token((sorted_rounds[0] or {}).get("createdAt"), limit=40),
        }

        if normalized_memory_type and normalized_memory_type not in memory_types:
            continue
        if normalized_employee_id:
            has_employee = False
            for round_item in sorted_rounds:
                primary_memory = round_item.get("primaryMemory") if isinstance(round_item.get("primaryMemory"), dict) else {}
                if _normalize_project_record_token(primary_memory.get("employee_id"), limit=80) == normalized_employee_id:
                    has_employee = True
                    break
                for entry in round_item.get("workSessions") or []:
                    if not isinstance(entry, dict):
                        continue
                    if _normalize_project_record_token(entry.get("employee_id"), limit=80) == normalized_employee_id:
                        has_employee = True
                        break
                if has_employee:
                    break
            if not has_employee:
                continue
        if query_text:
            search_values = [
                record_payload["rootGoal"],
                record_payload["summaryText"],
                record_payload["currentFocus"],
                record_payload["actorLabel"],
            ]
            for round_item in sorted_rounds:
                primary_memory = round_item.get("primaryMemory") if isinstance(round_item.get("primaryMemory"), dict) else {}
                search_values.extend(
                    [
                        _normalize_project_record_token(round_item.get("rootGoal"), limit=1000),
                        _normalize_project_record_token(round_item.get("title"), limit=200),
                        _normalize_project_record_token(round_item.get("currentNodeTitle"), limit=200),
                        _normalize_project_record_token(round_item.get("summaryText"), limit=1000),
                        _normalize_project_record_token(primary_memory.get("content"), limit=4000),
                    ]
                )
                for entry in round_item.get("workSessions") or []:
                    if not isinstance(entry, dict):
                        continue
                    search_values.extend(
                        [
                            _normalize_project_record_token(entry.get("goal"), limit=400),
                            *[
                                _normalize_project_record_token(value, limit=400)
                                for value in entry.get("steps") or []
                            ],
                            *[
                                _normalize_project_record_token(value, limit=400)
                                for value in entry.get("verification") or []
                            ],
                            *[
                                _normalize_project_record_token(value, limit=400)
                                for value in entry.get("next_steps") or []
                            ],
                        ]
                    )
            normalized_values = [item.lower() for item in search_values if item]
            if not any(query_text in item for item in normalized_values):
                continue
        records.append(record_payload)

    records.sort(
        key=lambda item: (
            _normalize_project_record_token(item.get("updatedAt") or item.get("createdAt"), limit=40),
            _normalize_project_record_token(item.get("id"), limit=80),
        ),
        reverse=True,
    )
    records = _dedupe_query_cli_requirement_records(records)
    visible_task_session_ids = {
        _normalize_project_record_token(round_item.get("sessionId") or round_item.get("id"), limit=80)
        for record in records
        for round_item in (record.get("rounds") or [])
        if isinstance(round_item, dict)
    }
    return {
        "items": records[:safe_limit],
        "task_sessions": [
            item
            for item in task_sessions
            if _normalize_project_record_token(item.get("id"), limit=80) in visible_task_session_ids
        ],
    }


def _serialize_project_user_member(member: ProjectUserMember) -> dict[str, Any]:
    user = user_store.get(member.username)
    return {
        **asdict(member),
        "user_exists": user is not None,
        "user_role": str(getattr(user, "role", "") or ""),
    }


def _append_chat_record(
    *,
    project_id: str,
    username: str,
    role: str,
    content: str,
    message_id: str = "",
    chat_session_id: str = "",
    display_mode: str = "",
    attachments: list[str] | None = None,
    images: list[str] | None = None,
    videos: list[str] | None = None,
) -> None:
    text = str(content or "").strip()
    if not text:
        return
    try:
        project_chat_store.append_message(
            ProjectChatMessage(
                id=str(message_id or "").strip(),
                project_id=project_id,
                username=username,
                role=role,
                content=text,
                chat_session_id=str(chat_session_id or "").strip(),
                display_mode=str(display_mode or "").strip(),
                attachments=attachments or [],
                images=images or [],
                videos=videos or [],
            )
        )
    except Exception:
        pass


def _resolve_project_memory_target_employee_ids(
    project_id: str,
    selected_employee_ids: list[str] | None = None,
) -> tuple[list[str], MemoryScope]:
    active_member_ids: list[str] = []
    active_member_seen: set[str] = set()
    for member in project_store.list_members(project_id):
        if not bool(getattr(member, "enabled", True)):
            continue
        employee_id = str(getattr(member, "employee_id", "") or "").strip()
        if not employee_id or employee_id in active_member_seen:
            continue
        if employee_store.get(employee_id) is None:
            continue
        active_member_seen.add(employee_id)
        active_member_ids.append(employee_id)

    preferred = [
        str(item or "").strip()
        for item in (selected_employee_ids or [])
        if str(item or "").strip()
    ]
    result: list[str] = []
    seen: set[str] = set()
    for employee_id in preferred:
        if not employee_id or employee_id in seen:
            continue
        if employee_store.get(employee_id) is None:
            continue
        seen.add(employee_id)
        result.append(employee_id)
    if result:
        if len(result) == 1:
            return result, MemoryScope.EMPLOYEE_PRIVATE
        return [result[0]], MemoryScope.TEAM_SHARED

    if active_member_ids:
        return [active_member_ids[0]], MemoryScope.TEAM_SHARED
    return [], MemoryScope.TEAM_SHARED


def _normalize_project_chat_surface(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == "global-assistant":
        return "global-assistant"
    return "main-chat"


def _compose_project_chat_memory_source(base_source: str, chat_surface: str) -> str:
    normalized_base_source = str(base_source or "").strip() or "project-chat"
    normalized_surface = _normalize_project_chat_surface(chat_surface)
    if normalized_surface == "global-assistant":
        return f"{normalized_base_source}-global-assistant"
    return normalized_base_source


def _allow_project_chat_requirement_record(chat_surface: str) -> bool:
    return _normalize_project_chat_surface(chat_surface) == "global-assistant"


_PROJECT_CHAT_COMPLETION_SIGNAL_TERMS = (
    "已完成",
    "已经完成",
    "完成了",
    "处理完成",
    "已处理",
    "已实现",
    "实现完成",
    "已修复",
    "修复完成",
    "已解决",
    "解决了",
    "done",
    "fixed",
)
_PROJECT_CHAT_COMPLETION_NEGATION_TERMS = (
    "未完成",
    "没有完成",
    "尚未完成",
    "还没完成",
    "未实现",
    "没有实现",
    "未修复",
    "没有修复",
    "未解决",
    "没有解决",
)
_PROJECT_CHAT_VERIFICATION_SIGNAL_TERMS = (
    "已验证",
    "验证通过",
    "测试通过",
    "构建通过",
    "回归通过",
    "联调通过",
    "人工验证",
    "人工确认",
    "截图确认",
    "日志确认",
    "验证完成",
)
_PROJECT_CHAT_VERIFICATION_NEGATION_TERMS = (
    "未验证",
    "没有验证",
    "尚未验证",
    "还没验证",
    "待验证",
    "需要验证",
)


def _project_chat_answer_has_term(text: str, terms: tuple[str, ...]) -> bool:
    normalized = str(text or "").strip().lower()
    return bool(normalized) and any(term in normalized for term in terms)


def _project_chat_answer_implies_completed_summary(
    answer: str,
    task_tree_payload: dict[str, Any] | None,
) -> bool:
    normalized_answer = str(answer or "").strip().lower()
    if not normalized_answer:
        return False
    if _project_chat_answer_has_term(normalized_answer, _PROJECT_CHAT_COMPLETION_NEGATION_TERMS):
        return False
    if _project_chat_answer_has_term(normalized_answer, _PROJECT_CHAT_VERIFICATION_NEGATION_TERMS):
        return False
    if not _project_chat_answer_has_term(normalized_answer, _PROJECT_CHAT_COMPLETION_SIGNAL_TERMS):
        return False
    if not _project_chat_answer_has_term(normalized_answer, _PROJECT_CHAT_VERIFICATION_SIGNAL_TERMS):
        return False
    if not isinstance(task_tree_payload, dict):
        return True
    payload_status = str(task_tree_payload.get("status") or "").strip().lower()
    if payload_status in {"blocked", "failed"}:
        return False
    current_node = task_tree_payload.get("current_node")
    if isinstance(current_node, dict):
        current_status = str(current_node.get("status") or "").strip().lower()
        if current_status in {"blocked", "failed"}:
            return False
    return True


def _save_project_chat_memory_snapshot(
    *,
    project_id: str,
    user_message: str,
    answer: str,
    chat_session_id: str = "",
    task_tree_payload: dict[str, Any] | None = None,
    selected_employee_ids: list[str] | None = None,
    source: str = "project-chat",
    allow_requirement_record: bool = True,
) -> None:
    project = project_store.get(project_id)
    if project is None:
        return
    question = str(user_message or "").strip()
    conclusion = str(answer or "").strip()
    if not question or not conclusion:
        return
    if conclusion in {"[已停止]", "模型未返回有效内容。"}:
        return
    if conclusion.startswith("对话失败："):
        return

    normalized_chat_session_id = str(chat_session_id or "").strip()
    target_ids, memory_scope = _resolve_project_memory_target_employee_ids(project_id, selected_employee_ids)
    if not target_ids:
        return

    def _normalize_task_tree_status(payload: dict[str, Any] | None) -> str:
        if not isinstance(payload, dict):
            return ""
        session_status = str(payload.get("status") or "").strip().lower()
        current_node = payload.get("current_node") if isinstance(payload.get("current_node"), dict) else {}
        current_status = str(current_node.get("status") or "").strip().lower()
        return current_status or session_status

    def _is_task_tree_completed(payload: dict[str, Any] | None) -> bool:
        if not isinstance(payload, dict):
            return True
        status = str(payload.get("status") or "").strip().lower()
        if not status:
            return True
        if bool(payload.get("is_archived")) and status == "done":
            return True
        if status == "done":
            try:
                progress_percent = int(payload.get("progress_percent", 0) or 0)
            except (TypeError, ValueError):
                progress_percent = 0
            return progress_percent >= 100
        return False

    def _project_chat_stage_label(payload: dict[str, Any] | None) -> str:
        status = _normalize_task_tree_status(payload)
        if status == "pending":
            return "计划中"
        if status in {"in_progress", "started"}:
            return "执行中"
        if status == "verifying":
            return "待验证"
        if status in {"blocked", "failed"}:
            return "已阻塞"
        if _is_task_tree_completed(payload):
            return "已完成"
        return "执行中"

    def _render_task_tree_plan_outline(payload: dict[str, Any] | None) -> str:
        if not isinstance(payload, dict):
            return ""
        nodes = payload.get("nodes") if isinstance(payload.get("nodes"), list) else []
        lines: list[str] = []
        for node in nodes:
            if int(node.get("level", 0) or 0) <= 0:
                continue
            title = str(node.get("title") or "").strip()
            if not title:
                continue
            status = str(node.get("status") or "pending").strip() or "pending"
            verification_result = str(node.get("verification_result") or "").strip()
            line = f"- [{status}] {title}"
            if verification_result:
                line = f"{line} | 验证: {verification_result}"
            lines.append(line)
        return "\n".join(lines[:12])

    def _render_task_tree_verification_summary(payload: dict[str, Any] | None) -> str:
        if not isinstance(payload, dict):
            return ""
        nodes = payload.get("nodes") if isinstance(payload.get("nodes"), list) else []
        items: list[str] = []
        for node in nodes:
            verification_result = str(node.get("verification_result") or "").strip()
            if not verification_result:
                continue
            title = str(node.get("title") or "").strip() or "任务节点"
            items.append(f"{title}: {verification_result}")
        return "\n".join(items[:12])

    def _memory_record_exists(
        employee_id: str,
        *,
        project_id: str,
        project_name: str,
        chat_session_id: str,
        workflow_tag: str,
        task_tree_session_id: str = "",
        question: str = "",
        content: str = "",
        fingerprint_tag: str = "",
    ) -> bool:
        candidates = _project_memory_candidate_records(employee_id, limit=200)
        normalized_project_id = str(project_id or "").strip()
        normalized_project_name = str(project_name or "").strip()
        normalized_chat_tag = f"chat-session:{chat_session_id}" if chat_session_id else ""
        normalized_task_tree_session_id = str(task_tree_session_id or "").strip()
        normalized_question = str(question or "").strip()
        normalized_content = str(content or "").strip()
        for memory in candidates:
            if str(getattr(memory, "project_name", "") or "").strip() != normalized_project_name:
                continue
            tags = {
                str(item or "").strip()
                for item in (getattr(memory, "purpose_tags", ()) or [])
                if str(item or "").strip()
            }
            if fingerprint_tag and fingerprint_tag in tags:
                return True
            binding = _parse_project_memory_binding(
                getattr(memory, "content", ""),
                getattr(memory, "purpose_tags", ()),
            )
            memory_project_id = str(binding.get("project_id") or "").strip()
            if normalized_project_id:
                if memory_project_id and memory_project_id != normalized_project_id:
                    continue
                if not memory_project_id and str(getattr(memory, "project_name", "") or "").strip() != normalized_project_name:
                    continue
            elif str(getattr(memory, "project_name", "") or "").strip() != normalized_project_name:
                continue
            if workflow_tag not in tags:
                continue
            if normalized_content and normalized_content == str(getattr(memory, "content", "") or "").strip():
                return True
            memory_task_tree_session_id = str(binding.get("task_tree_session_id") or "").strip()
            if normalized_task_tree_session_id:
                if (
                    memory_task_tree_session_id == normalized_task_tree_session_id
                    or f"task-tree-session:{normalized_task_tree_session_id}" in tags
                ):
                    return True
                continue
            if normalized_question:
                memory_question = _extract_project_memory_section(getattr(memory, "content", ""), "用户问题")
                memory_root_goal = str(binding.get("root_goal") or "").strip()
                if normalized_chat_tag and normalized_chat_tag not in tags:
                    continue
                if memory_question == normalized_question or memory_root_goal == normalized_question:
                    return True
                continue
            if normalized_chat_tag and normalized_chat_tag not in tags:
                continue
            return True
        return False

    def _extract_task_tree_binding(payload: dict[str, Any] | None) -> dict[str, str]:
        if not isinstance(payload, dict):
            return {}
        current_node = payload.get("current_node") if isinstance(payload.get("current_node"), dict) else {}
        result = {
            "chat_session_id": normalized_chat_session_id,
            "task_tree_session_id": str(payload.get("id") or "").strip(),
            "task_tree_chat_session_id": str(
                payload.get("source_chat_session_id") or payload.get("chat_session_id") or ""
            ).strip(),
            "task_node_id": str(current_node.get("id") or "").strip(),
            "task_node_title": str(current_node.get("title") or "").strip(),
            "root_goal": str(payload.get("root_goal") or payload.get("title") or "").strip(),
        }
        return {key: value for key, value in result.items() if value}

    project_name = str(getattr(project, "name", "") or project_id).strip() or "default"
    task_tree_completed = _is_task_tree_completed(task_tree_payload)
    inferred_completed_summary = (
        not task_tree_completed
        and _project_chat_answer_implies_completed_summary(conclusion, task_tree_payload)
    )
    snapshot_completed = task_tree_completed or inferred_completed_summary
    if not snapshot_completed and not allow_requirement_record:
        return
    workflow_tag = "workflow:final-summary" if snapshot_completed else "workflow:requirement-record"
    stage_label = "已完成" if snapshot_completed else _project_chat_stage_label(task_tree_payload)
    plan_outline = _render_task_tree_plan_outline(task_tree_payload)
    verification_summary = _render_task_tree_verification_summary(task_tree_payload)
    if snapshot_completed:
        content_lines = [
            f"[用户问题] {question[:1200]}",
            f"[处理过程] {_build_project_chat_memory_process_summary(conclusion)}",
            f"[解决方案] {conclusion[:1600]}",
            f"[最终结论] {conclusion[:2800]}",
            f"[解决状态] {_derive_project_chat_memory_solve_status(conclusion)}",
        ]
        if verification_summary:
            content_lines.append(f"[验证结果] {verification_summary[:2400]}")
    else:
        content_lines = [
            f"[用户问题] {question[:1200]}",
            (
                "[处理过程] 已生成执行计划，当前只记录需求与计划状态。"
                f" 当前阶段：{stage_label}；必须按任务树逐项执行、逐项验证，全部完成前不生成最终结论。"
            ),
            f"[解决状态] {stage_label}",
            "[完成条件] 只有所有计划项完成并写入验证结果后，当前需求才算结束。",
        ]
        if plan_outline:
            content_lines.append(f"[任务计划]\n{plan_outline}")
    content_lines.append(f"[项目ID] {project_id}")
    content_lines.append(f"[项目名称] {project_name}")
    if normalized_chat_session_id:
        content_lines.append(f"[关联会话] {normalized_chat_session_id}")
    task_tree_binding = _extract_task_tree_binding(task_tree_payload)
    if task_tree_binding:
        content_lines.append(
            "[执行轨迹JSON] " + json.dumps(task_tree_binding, ensure_ascii=False, sort_keys=True)
        )
    content = "\n".join(content_lines)
    purpose_tags = ["auto-capture", "project-chat", source, workflow_tag, f"project-id:{project_id}"]
    if normalized_chat_session_id:
        purpose_tags.append(f"chat-session:{normalized_chat_session_id}")
    if task_tree_binding.get("task_tree_session_id"):
        purpose_tags.append(f"task-tree-session:{task_tree_binding['task_tree_session_id']}")
    fingerprint_tag = _project_memory_fingerprint_tag(
        project_name,
        workflow_tag,
        normalized_chat_session_id,
        task_tree_binding.get("task_tree_session_id", ""),
        content,
    )
    if fingerprint_tag:
        purpose_tags.append(fingerprint_tag)
    for employee_id in target_ids:
        if _memory_record_exists(
            employee_id,
            project_id=project_id,
            project_name=project_name,
            chat_session_id=normalized_chat_session_id,
            workflow_tag=workflow_tag,
            task_tree_session_id=task_tree_binding.get("task_tree_session_id", ""),
            question=question,
            content=content,
            fingerprint_tag=fingerprint_tag,
        ):
            continue
        try:
            memory_store.save(
                Memory(
                    id=memory_store.new_id(),
                    employee_id=employee_id,
                    type=MemoryType.PROJECT_CONTEXT,
                    content=content,
                    project_name=project_name,
                    importance=0.6,
                    scope=memory_scope,
                    classification=Classification.INTERNAL,
                    purpose_tags=tuple(purpose_tags),
                )
            )
        except Exception:
            continue


def _build_project_chat_memory_process_summary(answer: str) -> str:
    normalized_answer = str(answer or "").strip()
    if not normalized_answer:
        return "已在当前会话完成处理，可结合关联任务树查看执行节点与验证结果。"
    if len(normalized_answer) <= 160:
        return "已在当前会话完成问题处理并给出结论，可结合关联任务树回看执行节点与验证结果。"
    return "已在当前会话完成分析并给出处理建议，可结合关联任务树回看执行节点与验证结果。"


def _derive_project_chat_memory_solve_status(answer: str) -> str:
    normalized_answer = str(answer or "").strip()
    if not normalized_answer:
        return "待确认"
    unresolved_markers = ("未解决", "无法解决", "无法完成", "当前无法", "处理失败", "已阻塞", "阻塞")
    if any(marker in normalized_answer for marker in unresolved_markers):
        return "未解决"
    pending_markers = (
        "待确认",
        "待补充",
        "需要补充",
        "请补充",
        "请提供",
        "需提供",
        "需要进一步",
        "需要确认",
        "需确认",
    )
    if any(marker in normalized_answer for marker in pending_markers):
        return "待确认"
    return "已给出方案"


def _build_global_voice_runtime(auth_payload: dict) -> dict[str, Any]:
    config = system_config_store.get_global()
    greeting_enabled = bool(getattr(config, "global_assistant_greeting_enabled", True))
    greeting_text = str(
        getattr(config, "global_assistant_greeting_text", "") or DEFAULT_GLOBAL_ASSISTANT_GREETING_TEXT
    ).strip() or DEFAULT_GLOBAL_ASSISTANT_GREETING_TEXT
    transcription_prompt = str(
        getattr(config, "global_assistant_transcription_prompt", "") or DEFAULT_GLOBAL_ASSISTANT_TRANSCRIPTION_PROMPT
    ).strip() or DEFAULT_GLOBAL_ASSISTANT_TRANSCRIPTION_PROMPT
    wake_phrase = str(
        getattr(config, "global_assistant_wake_phrase", "") or "你好助手"
    ).strip() or "你好助手"
    idle_timeout_sec = int(
        getattr(config, "global_assistant_idle_timeout_sec", 5) or 5
    )
    if not bool(getattr(config, "voice_input_enabled", False)):
        return {
            "enabled": False,
            "available": False,
            "mode": "",
            "reason": "系统未开启语音输入",
            "greeting_enabled": greeting_enabled,
            "greeting_text": greeting_text,
            "transcription_prompt": transcription_prompt,
            "wake_phrase": wake_phrase,
            "idle_timeout_sec": idle_timeout_sec,
        }

    provider_id = str(getattr(config, "voice_input_provider_id", "") or "").strip()
    model_name = str(getattr(config, "voice_input_model_name", "") or "").strip()
    if not provider_id or not model_name:
        return {
            "enabled": True,
            "available": False,
            "mode": "",
            "reason": "系统语音模型未配置完整",
            "greeting_enabled": greeting_enabled,
            "greeting_text": greeting_text,
            "transcription_prompt": transcription_prompt,
            "wake_phrase": wake_phrase,
            "idle_timeout_sec": idle_timeout_sec,
        }

    username = _current_username(auth_payload)
    allowed_usernames = normalize_voice_allowed_usernames(
        getattr(config, "voice_input_allowed_usernames", [])
    )
    allowed_roles = set(
        normalize_voice_allowed_role_ids(getattr(config, "voice_input_allowed_role_ids", []))
    )
    current_role_ids = _current_role_ids(auth_payload)
    scope_open = not allowed_usernames and not allowed_roles
    username_allowed = username.lower() in {
        str(item or "").strip().lower()
        for item in allowed_usernames
    }
    role_allowed = any(role_id in allowed_roles for role_id in current_role_ids)
    if not scope_open and not username_allowed and not role_allowed:
        return {
            "enabled": True,
            "available": False,
            "mode": "",
            "reason": "当前账号未开通全局助手语音",
            "greeting_enabled": greeting_enabled,
            "greeting_text": greeting_text,
            "transcription_prompt": transcription_prompt,
            "wake_phrase": wake_phrase,
            "idle_timeout_sec": idle_timeout_sec,
        }

    from services.llm_provider_service import get_llm_provider_service

    llm_service = get_llm_provider_service()
    provider = llm_service.get_provider_raw(
        provider_id,
        owner_username=username,
        include_all=True,
        include_shared=True,
    )
    if provider is None or not bool(provider.get("enabled", True)):
        return {
            "enabled": True,
            "available": False,
            "mode": "",
            "reason": "系统语音模型供应商不可用",
            "greeting_enabled": greeting_enabled,
            "greeting_text": greeting_text,
            "transcription_prompt": transcription_prompt,
            "wake_phrase": wake_phrase,
            "idle_timeout_sec": idle_timeout_sec,
        }
    model_config = llm_service.get_model_config(provider, model_name) or {}
    if str(model_config.get("model_type") or "").strip().lower() != "audio_transcription":
        return {
            "enabled": True,
            "available": False,
            "mode": "",
            "reason": "系统语音模型类型不是音频转写",
            "greeting_enabled": greeting_enabled,
            "greeting_text": greeting_text,
            "transcription_prompt": transcription_prompt,
            "wake_phrase": wake_phrase,
            "idle_timeout_sec": idle_timeout_sec,
        }
    return {
        "enabled": True,
        "available": True,
        "mode": "backend",
        "reason": "",
        "provider_id": provider_id,
        "provider_name": str(provider.get("name") or provider_id).strip(),
        "model_name": model_name,
        "greeting_enabled": greeting_enabled,
        "greeting_text": greeting_text,
        "transcription_prompt": transcription_prompt,
        "wake_phrase": wake_phrase,
        "idle_timeout_sec": idle_timeout_sec,
    }


def _require_global_voice_runtime(auth_payload: dict) -> dict[str, Any]:
    runtime = _build_global_voice_runtime(auth_payload)
    if not bool(runtime.get("available")):
        raise HTTPException(403, str(runtime.get("reason") or "当前不可使用语音输入"))
    return runtime


def _resolve_global_assistant_greeting_audio_asset() -> dict[str, Any] | None:
    config = system_config_store.get_global()
    greeting_audio = (
        getattr(config, "global_assistant_greeting_audio", {})
        if isinstance(getattr(config, "global_assistant_greeting_audio", {}), dict)
        else {}
    )
    storage_path = str(greeting_audio.get("storage_path") or "").strip()
    if not storage_path:
        return None
    relative_path = Path(storage_path)
    if relative_path.is_absolute():
        return None
    data_dir = get_api_data_dir()
    absolute_path = (data_dir / relative_path).resolve()
    try:
        absolute_path.relative_to(data_dir.resolve())
    except ValueError:
        return None
    if not absolute_path.is_file():
        return None
    return {
        "path": absolute_path,
        "signature": str(greeting_audio.get("signature") or "").strip(),
        "content_type": str(greeting_audio.get("content_type") or "audio/wav").strip() or "audio/wav",
    }


def _build_global_speech_runtime(auth_payload: dict) -> dict[str, Any]:
    config = system_config_store.get_global()
    if not bool(getattr(config, "voice_output_enabled", False)):
        return {
            "enabled": False,
            "available": False,
            "mode": "",
            "reason": "系统未开启语音播报",
        }

    provider_id = str(getattr(config, "voice_output_provider_id", "") or "").strip()
    model_name = str(getattr(config, "voice_output_model_name", "") or "").strip()
    voice = str(getattr(config, "voice_output_voice", "") or "").strip()
    if not provider_id or not model_name or not voice:
        return {
            "enabled": True,
            "available": False,
            "mode": "",
            "reason": "系统语音播报配置不完整",
        }

    username = _current_username(auth_payload)
    allowed_usernames = normalize_voice_allowed_usernames(
        getattr(config, "voice_input_allowed_usernames", [])
    )
    allowed_roles = set(
        normalize_voice_allowed_role_ids(getattr(config, "voice_input_allowed_role_ids", []))
    )
    current_role_ids = _current_role_ids(auth_payload)
    scope_open = not allowed_usernames and not allowed_roles
    username_allowed = username.lower() in {
        str(item or "").strip().lower()
        for item in allowed_usernames
    }
    role_allowed = any(role_id in allowed_roles for role_id in current_role_ids)
    if not scope_open and not username_allowed and not role_allowed:
        return {
            "enabled": True,
            "available": False,
            "mode": "",
            "reason": "当前账号未开通全局助手语音",
        }

    from services.llm_provider_service import get_llm_provider_service

    llm_service = get_llm_provider_service()
    provider = llm_service.get_provider_raw(
        provider_id,
        owner_username=username,
        include_all=True,
        include_shared=True,
    )
    if provider is None or not bool(provider.get("enabled", True)):
        return {
            "enabled": True,
            "available": False,
            "mode": "",
            "reason": "系统语音播报供应商不可用",
        }
    model_config = llm_service.get_model_config(provider, model_name) or {}
    if str(model_config.get("model_type") or "").strip().lower() != "audio_generation":
        return {
            "enabled": True,
            "available": False,
            "mode": "",
            "reason": "系统语音播报模型类型不是音频生成",
        }
    greeting_audio = _resolve_global_assistant_greeting_audio_asset()
    return {
        "enabled": True,
        "available": True,
        "mode": "backend",
        "reason": "",
        "provider_id": provider_id,
        "provider_name": str(provider.get("name") or provider_id).strip(),
        "model_name": model_name,
        "voice": voice,
        "greeting_audio_available": greeting_audio is not None,
        "greeting_audio_signature": str((greeting_audio or {}).get("signature") or "").strip(),
    }


def _require_global_speech_runtime(auth_payload: dict) -> dict[str, Any]:
    runtime = _build_global_speech_runtime(auth_payload)
    if not bool(runtime.get("available")):
        raise HTTPException(403, str(runtime.get("reason") or "当前不可使用语音播报"))
    return runtime


def _resolve_request_origin(request: Request) -> str:
    forwarded_proto = str(request.headers.get("x-forwarded-proto") or "").split(",")[0].strip()
    forwarded_host = str(request.headers.get("x-forwarded-host") or "").split(",")[0].strip()
    forwarded_port = str(request.headers.get("x-forwarded-port") or "").split(",")[0].strip()
    scheme = forwarded_proto or str(request.url.scheme or "").strip() or "http"
    host = (
        forwarded_host
        or str(request.headers.get("host") or "").split(",")[0].strip()
        or str(request.url.netloc or "").strip()
    )
    if forwarded_port and host and ":" not in host and not host.endswith("]"):
        host = f"{host}:{forwarded_port}"
    if not host:
        return str(request.base_url).rstrip("/")
    return f"{scheme}://{host}".rstrip("/")


def _build_absolute_runtime_url(origin: str, path: str) -> str:
    normalized_origin = str(origin or "").strip().rstrip("/")
    normalized_path = str(path or "").strip()
    if not normalized_path.startswith("/"):
        normalized_path = f"/{normalized_path}"
    return f"{normalized_origin}{normalized_path}"


def _normalize_global_voice_transcription_error(exc: Exception) -> tuple[int, str]:
    message = str(exc or "").strip()
    lowered = message.lower()
    if "语音转写结果为空" in message or "no audio segment found" in lowered:
        return 200, ""
    if "transcriptions不支持当前文件格式" in message or '"code":"1214"' in lowered:
        return 400, "当前录音格式暂不支持，请重新录音后再试"
    return 502, "语音转写暂时不可用，请稍后重试"


def _sanitize_global_voice_transcript_text(value: Any) -> str:
    normalized = (
        str(value or "")
        .replace("#", "")
        .replace("＃", "")
        .strip()
    )
    normalized = re.sub(r"\s*\n+\s*", "", normalized)
    normalized = re.sub(r"\s{2,}", " ", normalized).strip()
    previous = ""
    while normalized and normalized != previous:
        previous = normalized
        normalized = re.sub(r"(.{3,}?)\1+", r"\1", normalized).strip()
    return normalized


def _canonicalize_global_voice_transcript_text(value: Any) -> str:
    return re.sub(
        r"[，。！？、,.!?\s]+",
        "",
        _sanitize_global_voice_transcript_text(value),
    ).strip()


def _should_skip_partial_voice_transcript(
    current_text: str,
    previous_text: str,
) -> bool:
    current_canonical = _canonicalize_global_voice_transcript_text(current_text)
    if len(current_canonical) < 2:
        return True
    previous_canonical = _canonicalize_global_voice_transcript_text(previous_text)
    if not previous_canonical:
        return False
    if current_canonical == previous_canonical:
        return True
    if (
        len(current_canonical) < len(previous_canonical)
        and current_canonical in previous_canonical
    ):
        return True
    return False


def _coerce_global_voice_stream_sample_rate(value: Any) -> int:
    try:
        sample_rate = int(value)
    except (TypeError, ValueError):
        sample_rate = _GLOBAL_VOICE_STREAM_SAMPLE_RATE
    if sample_rate <= 0:
        return _GLOBAL_VOICE_STREAM_SAMPLE_RATE
    return sample_rate


def _global_voice_stream_min_buffer_bytes(sample_rate: int) -> int:
    return max(
        3200,
        int(
            max(1, sample_rate)
            * _GLOBAL_VOICE_STREAM_PCM_BYTES_PER_SAMPLE
            * _GLOBAL_VOICE_STREAM_MIN_CHUNK_MS
            / 1000
        ),
    )


def _global_voice_stream_max_buffer_bytes(sample_rate: int) -> int:
    return max(
        _global_voice_stream_min_buffer_bytes(sample_rate) * 2,
        max(1, sample_rate)
        * _GLOBAL_VOICE_STREAM_PCM_BYTES_PER_SAMPLE
        * _GLOBAL_VOICE_STREAM_MAX_BUFFER_SECONDS,
    )


def _global_voice_stream_final_buffer_bytes(sample_rate: int) -> int:
    return max(
        _global_voice_stream_max_buffer_bytes(sample_rate),
        max(1, sample_rate)
        * _GLOBAL_VOICE_STREAM_PCM_BYTES_PER_SAMPLE
        * _GLOBAL_VOICE_STREAM_FINAL_MAX_BUFFER_SECONDS,
    )


def _global_voice_stream_has_min_duration(pcm_bytes: bytes, sample_rate: int) -> bool:
    if not pcm_bytes:
        return False
    return len(pcm_bytes) >= _global_voice_stream_min_buffer_bytes(sample_rate)


def _decode_global_voice_stream_chunk(value: Any) -> bytes:
    encoded = str(value or "").strip()
    if not encoded:
        return b""
    padding = "=" * (-len(encoded) % 4)
    try:
        return base64.b64decode(f"{encoded}{padding}", validate=False)
    except Exception as exc:
        raise ValueError("音频分片解析失败") from exc


def _build_global_voice_stream_wave_bytes(pcm_bytes: bytes, sample_rate: int) -> bytes:
    if not pcm_bytes:
        return b""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(_GLOBAL_VOICE_STREAM_PCM_BYTES_PER_SAMPLE)
        wav_file.setframerate(max(1, int(sample_rate)))
        wav_file.writeframes(pcm_bytes)
    return buffer.getvalue()


async def _transcribe_global_voice_stream_chunk(
    runtime: dict[str, Any],
    *,
    pcm_bytes: bytes,
    sample_rate: int,
    language: str,
    prompt: str,
    chunk_index: int,
    owner_username: str,
) -> str:
    if not pcm_bytes:
        return ""
    wav_bytes = _build_global_voice_stream_wave_bytes(pcm_bytes, sample_rate)
    temp_path = ""
    try:
        with NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
            temp_file.write(wav_bytes)
            temp_path = temp_file.name
        from services.llm_provider_service import get_llm_provider_service

        llm_service = get_llm_provider_service()
        result = await llm_service.transcribe_audio(
            str(runtime.get("provider_id") or "").strip(),
            str(runtime.get("model_name") or "").strip(),
            file_path=temp_path,
            filename=f"global-assistant-stream-{chunk_index}.wav",
            mime_type="audio/wav",
            language=str(language or "").strip(),
            prompt=str(prompt or "").strip(),
            owner_username=str(owner_username or "").strip(),
            include_all=True,
        )
        return str(result.get("text") or "").strip()
    finally:
        if temp_path:
            Path(temp_path).unlink(missing_ok=True)


@router.get("/chat/global/history")
async def list_global_assistant_chat_history(
    limit: int = 200,
    offset: int = 0,
    chat_session_id: str = "",
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.ai.chat")
    return {"messages": []}


@router.get("/chat/global/sessions")
async def list_global_assistant_chat_sessions(
    limit: int = 50,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.ai.chat")
    return {"sessions": []}


@router.post("/chat/global/sessions")
async def create_global_assistant_chat_session(
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.ai.chat")
    now = _now_iso()
    return {
        "session": {
            "id": f"chat-session-{uuid.uuid4().hex[:12]}",
            "title": "新对话",
            "preview": "",
            "message_count": 0,
            "created_at": now,
            "updated_at": now,
            "last_message_at": now,
        }
    }


@router.get("/chat/global/voice-input/runtime")
async def get_global_assistant_voice_runtime(
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.ai.chat")
    return {"runtime": _build_global_voice_runtime(auth_payload)}


@router.get("/chat/global/voice-output/runtime")
async def get_global_assistant_speech_runtime(
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.ai.chat")
    return {"runtime": _build_global_speech_runtime(auth_payload)}


@router.get("/query-mcp/runtime")
async def get_query_mcp_runtime(
    request: Request,
    project_id: str = Query("", description="项目 ID"),
):
    params = {"key": "YOUR_API_KEY"}
    normalized_project_id = str(project_id or "").strip()
    if normalized_project_id:
        params["project_id"] = normalized_project_id
    query_string = urlencode(params)
    config = system_config_store.get_global()
    origin = (
        str(getattr(config, "query_mcp_public_base_url", "") or "").strip().rstrip("/")
        or _resolve_request_origin(request)
    )
    return {
        "runtime": {
            "origin": origin,
            "server_name": "query-center",
            "sse_url": _build_absolute_runtime_url(origin, f"/mcp/query/sse?{query_string}"),
            "http_url": _build_absolute_runtime_url(origin, f"/mcp/query/mcp?{query_string}"),
        }
    }


@router.post("/chat/global/voice-output/speech")
async def generate_global_assistant_speech(
    req: GlobalAssistantSpeechReq,
    auth_payload: dict = Depends(require_auth),
):
    from services.llm_provider_service import get_llm_provider_service

    _ensure_permission(auth_payload, "menu.ai.chat")
    runtime = _require_global_speech_runtime(auth_payload)
    text = str(req.text or "").strip()[:4000]
    if not text:
        raise HTTPException(400, "text is required")
    try:
        payload = await get_llm_provider_service().generate_audio_speech(
            str(runtime.get("provider_id") or ""),
            str(runtime.get("model_name") or ""),
            text=text,
            voice=str(runtime.get("voice") or ""),
            response_format="wav",
            speed=1.0,
            owner_username=_current_username(auth_payload),
            include_all=True,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(502, str(exc) or "语音播报暂时不可用") from exc
    audio_bytes = payload.get("audio_bytes") or b""
    if not audio_bytes:
        raise HTTPException(502, "语音播报结果为空")
    content_type = str(payload.get("content_type") or "audio/wav").strip() or "audio/wav"
    return StreamingResponse(
        io.BytesIO(audio_bytes),
        media_type=content_type,
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": 'inline; filename="assistant-speech.wav"',
        },
    )


@router.get("/chat/global/voice-output/greeting-audio")
async def get_global_assistant_greeting_audio(
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.ai.chat")
    _require_global_speech_runtime(auth_payload)
    asset = _resolve_global_assistant_greeting_audio_asset()
    if asset is None:
        raise HTTPException(404, "欢迎语音频不存在")
    return FileResponse(
        asset["path"],
        media_type=str(asset.get("content_type") or "audio/wav"),
        filename="assistant-greeting.wav",
        headers={"Cache-Control": "no-store"},
    )


@router.post("/chat/global/voice-input/transcriptions")
async def transcribe_global_assistant_voice(
    audio: UploadFile = File(...),
    language: str = Form("zh"),
    prompt: str = Form(""),
    is_final: bool = Form(False),
    auth_payload: dict = Depends(require_auth),
):
    from services.llm_provider_service import get_llm_provider_service

    _ensure_permission(auth_payload, "menu.ai.chat")
    runtime = _require_global_voice_runtime(auth_payload)
    normalized_prompt = str(prompt or "").strip() or str(runtime.get("transcription_prompt") or "").strip()
    original_filename = str(audio.filename or "").strip() or "voice-input.webm"
    content_type = str(audio.content_type or "").strip()
    suffix = Path(original_filename).suffix or ".webm"
    raw_audio = await audio.read()
    if not raw_audio:
        raise HTTPException(400, "audio file is required")
    if len(raw_audio) > 12 * 1024 * 1024:
        raise HTTPException(400, "audio file is too large")

    temp_path = ""
    try:
        with NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(raw_audio)
            temp_path = temp_file.name
        result = await get_llm_provider_service().transcribe_audio(
            str(runtime.get("provider_id") or ""),
            str(runtime.get("model_name") or ""),
            file_path=temp_path,
            filename=original_filename,
            mime_type=content_type,
            language=str(language or "").strip(),
            prompt=normalized_prompt,
            owner_username=_current_username(auth_payload),
            include_all=True,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        status_code, detail = _normalize_global_voice_transcription_error(exc)
        if status_code == 200:
            return {
                "text": "",
                "is_final": bool(is_final),
                "runtime": runtime,
            }
        raise HTTPException(status_code, detail) from exc
    finally:
        if temp_path:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except Exception:
                pass

    return {
        "text": str(result.get("text") or "").strip(),
        "is_final": bool(is_final),
        "runtime": runtime,
    }


@router.websocket("/chat/global/ws")
async def ws_global_assistant_chat(websocket: WebSocket):
    auth_payload = _extract_ws_auth_payload(websocket)
    if auth_payload is None:
        await websocket.close(code=4401, reason="Missing or invalid token")
        return
    try:
        _ensure_permission(auth_payload, "menu.ai.chat")
    except HTTPException:
        await websocket.close(code=4403, reason="Permission denied")
        return

    await websocket.accept()
    username = _current_username(auth_payload)
    await websocket.send_json(
        {
            "type": "ready",
            "message": "connected",
        }
    )

    active_tasks: dict[str, asyncio.Task] = {}
    cancel_events: dict[str, asyncio.Event] = {}
    voice_sessions: dict[str, dict[str, Any]] = {}
    browser_tool_futures: dict[str, asyncio.Future] = {}

    async def call_browser_tool(
        tool_name: str,
        args: dict[str, Any],
        *,
        request_id: str = "",
    ) -> dict[str, Any]:
        call_id = f"ga-browser-{uuid.uuid4().hex[:12]}"
        future = asyncio.get_running_loop().create_future()
        browser_tool_futures[call_id] = future
        try:
            await websocket.send_json(
                {
                    "type": "browser_tool_call",
                    "request_id": request_id,
                    "call_id": call_id,
                    "tool_name": str(tool_name or "").strip(),
                    "args": dict(args or {}),
                }
            )
            result = await asyncio.wait_for(future, timeout=20)
            if isinstance(result, dict):
                return result
            return {"result": result}
        except asyncio.TimeoutError:
            return {"error": "Browser tool execution timeout"}
        finally:
            browser_tool_futures.pop(call_id, None)

    async def handle_browser_tool_result(payload: dict[str, Any]) -> None:
        call_id = str(payload.get("call_id") or "").strip()
        if not call_id:
            return
        future = browser_tool_futures.get(call_id)
        if future is None or future.done():
            return
        if bool(payload.get("ok")):
            result = payload.get("result")
            future.set_result(result if isinstance(result, dict) else {"result": result})
            return
        future.set_result(
            {
                "error": str(payload.get("error") or "Browser tool execution failed").strip()
                or "Browser tool execution failed"
            }
        )

    async def emit_voice_transcript(
        request_id: str,
        session: dict[str, Any],
        *,
        chunk_index: int,
        text: str,
        is_final: bool,
    ) -> None:
        normalized_text = _sanitize_global_voice_transcript_text(text)
        if not normalized_text:
            return
        previous_partial_text = str(session.get("last_partial_transcript") or "").strip()
        if not is_final and _should_skip_partial_voice_transcript(
            normalized_text,
            previous_partial_text,
        ):
            return
        if is_final:
            session["last_partial_transcript"] = ""
        else:
            session["last_partial_transcript"] = normalized_text
        session["last_transcript"] = normalized_text
        await websocket.send_json(
            {
                "type": "voice_transcript",
                "request_id": request_id,
                "chunk_index": chunk_index,
                "is_final": bool(is_final),
                "text": normalized_text,
            }
        )

    async def close_voice_session(request_id: str):
        session = voice_sessions.get(request_id)
        if session is None:
            return
        if not bool(session.get("closed_emitted")):
            session["closed_emitted"] = True
            await websocket.send_json(
                {
                    "type": "voice_stopped",
                    "request_id": request_id,
                    "text": str(session.get("last_transcript") or "").strip(),
                }
            )
        if session.get("processing_task") is None:
            voice_sessions.pop(request_id, None)

    async def finalize_voice_session(request_id: str):
        session = voice_sessions.get(request_id)
        if session is None:
            return
        if session.get("processing_task") is not None or bool(session.get("finalizing")):
            return
        if bool(session.get("finalized")):
            await close_voice_session(request_id)
            return
        full_pcm_buffer = session.get("full_pcm_buffer")
        full_pcm_bytes = (
            bytes(full_pcm_buffer)
            if isinstance(full_pcm_buffer, (bytearray, bytes))
            else b""
        )
        sample_rate = int(session.get("sample_rate") or _GLOBAL_VOICE_STREAM_SAMPLE_RATE)
        if not full_pcm_bytes:
            session["finalized"] = True
            await close_voice_session(request_id)
            return
        if not _global_voice_stream_has_min_duration(full_pcm_bytes, sample_rate):
            session["last_transcript"] = ""
            session["last_partial_transcript"] = ""
            session["finalized"] = True
            await close_voice_session(request_id)
            return

        chunk_index = max(1, int(session.get("chunk_index") or 0))

        async def run_final_transcription():
            current = voice_sessions.get(request_id)
            if current is not session:
                return
            try:
                await websocket.send_json(
                    {
                        "type": "voice_status",
                        "request_id": request_id,
                        "message": "正在整理完整语音...",
                    }
                )
                text = await _transcribe_global_voice_stream_chunk(
                    dict(session.get("runtime") or {}),
                    pcm_bytes=full_pcm_bytes,
                    sample_rate=sample_rate,
                    language=str(session.get("language") or "zh").strip(),
                    prompt=str(session.get("prompt") or "").strip(),
                    chunk_index=chunk_index,
                    owner_username=username,
                )
                await emit_voice_transcript(
                    request_id,
                    session,
                    chunk_index=chunk_index,
                    text=text,
                    is_final=True,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                status_code, detail = _normalize_global_voice_transcription_error(exc)
                if status_code != 200 and detail:
                    session["failed"] = True
                    session["pending_stop"] = True
                    await websocket.send_json(
                        {
                            "type": "voice_error",
                            "request_id": request_id,
                            "message": detail,
                        }
                    )
            finally:
                current_session = voice_sessions.get(request_id)
                if current_session is not session:
                    return
                session["processing_task"] = None
                session["finalizing"] = False
                session["finalized"] = True
                await close_voice_session(request_id)

        session["finalizing"] = True
        session["processing_task"] = asyncio.create_task(run_final_transcription())

    async def maybe_flush_voice_session(request_id: str, *, force: bool = False):
        session = voice_sessions.get(request_id)
        if (
            session is None
            or session.get("processing_task") is not None
            or bool(session.get("finalizing"))
        ):
            return
        pcm_buffer = session.get("pcm_buffer")
        if not isinstance(pcm_buffer, bytearray):
            pcm_buffer = bytearray()
            session["pcm_buffer"] = pcm_buffer
        if not pcm_buffer:
            if force or bool(session.get("pending_stop")):
                await finalize_voice_session(request_id)
            return
        if force and bool(session.get("pending_stop")):
            session["pcm_buffer"] = bytearray()
            await finalize_voice_session(request_id)
            return
        min_buffer_bytes = int(session.get("min_buffer_bytes") or 0)
        if not force and len(pcm_buffer) < min_buffer_bytes:
            return

        pcm_bytes = bytes(pcm_buffer)
        session["pcm_buffer"] = bytearray()
        chunk_index = int(session.get("chunk_index") or 0) + 1
        session["chunk_index"] = chunk_index

        async def run_transcription():
            current = voice_sessions.get(request_id)
            if current is not session:
                return
            try:
                await websocket.send_json(
                    {
                        "type": "voice_status",
                        "request_id": request_id,
                        "message": "正在识别语音...",
                    }
                )
                text = await _transcribe_global_voice_stream_chunk(
                    dict(session.get("runtime") or {}),
                    pcm_bytes=pcm_bytes,
                    sample_rate=int(session.get("sample_rate") or _GLOBAL_VOICE_STREAM_SAMPLE_RATE),
                    language=str(session.get("language") or "zh").strip(),
                    prompt=str(session.get("prompt") or "").strip(),
                    chunk_index=chunk_index,
                    owner_username=username,
                )
                await emit_voice_transcript(
                    request_id,
                    session,
                    chunk_index=chunk_index,
                    text=text,
                    is_final=False,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                status_code, detail = _normalize_global_voice_transcription_error(exc)
                if status_code != 200 and detail:
                    session["failed"] = True
                    session["pending_stop"] = True
                    await websocket.send_json(
                        {
                            "type": "voice_error",
                            "request_id": request_id,
                            "message": detail,
                        }
                    )
            finally:
                current_session = voice_sessions.get(request_id)
                if current_session is not session:
                    return
                session["processing_task"] = None
                if session.get("failed"):
                    await close_voice_session(request_id)
                    return
                if session.get("pcm_buffer"):
                    await maybe_flush_voice_session(
                        request_id,
                        force=bool(session.get("pending_stop")),
                    )
                    return
                if session.get("pending_stop"):
                    await finalize_voice_session(request_id)

        session["processing_task"] = asyncio.create_task(run_transcription())

    async def handle_voice_payload(payload: dict[str, Any]):
        request_id = str(payload.get("request_id") or "").strip()
        payload_type = str(payload.get("type") or "").strip().lower()
        if not request_id:
            await websocket.send_json(
                {
                    "type": "voice_error",
                    "message": "request_id is required",
                }
            )
            return

        if payload_type == "voice_start":
            previous_session = voice_sessions.pop(request_id, None)
            previous_task = previous_session.get("processing_task") if isinstance(previous_session, dict) else None
            if previous_task is not None and not previous_task.done():
                previous_task.cancel()
            try:
                runtime = _require_global_voice_runtime(auth_payload)
            except HTTPException as exc:
                await websocket.send_json(
                    {
                        "type": "voice_error",
                        "request_id": request_id,
                        "message": str(exc.detail or "当前不可使用语音输入"),
                    }
                )
                return
            sample_rate = _coerce_global_voice_stream_sample_rate(payload.get("sample_rate"))
            voice_sessions[request_id] = {
                "runtime": runtime,
                "sample_rate": sample_rate,
                "language": str(payload.get("language") or "zh").strip() or "zh",
                "prompt": str(payload.get("prompt") or "").strip()
                or str(runtime.get("transcription_prompt") or "").strip(),
                "pcm_buffer": bytearray(),
                "full_pcm_buffer": bytearray(),
                "min_buffer_bytes": _global_voice_stream_min_buffer_bytes(sample_rate),
                "max_buffer_bytes": _global_voice_stream_max_buffer_bytes(sample_rate),
                "full_max_buffer_bytes": _global_voice_stream_final_buffer_bytes(sample_rate),
                "processing_task": None,
                "pending_stop": False,
                "closed_emitted": False,
                "failed": False,
                "finalized": False,
                "finalizing": False,
                "chunk_index": 0,
                "last_transcript": "",
                "last_partial_transcript": "",
            }
            await websocket.send_json(
                {
                    "type": "voice_ready",
                    "request_id": request_id,
                    "sample_rate": sample_rate,
                    "mode": "buffered_ws",
                }
            )
            return

        session = voice_sessions.get(request_id)
        if session is None:
            await websocket.send_json(
                {
                    "type": "voice_error",
                    "request_id": request_id,
                    "message": "语音会话不存在，请重新录音",
                }
            )
            return

        if payload_type == "voice_cancel":
            processing_task = session.get("processing_task")
            if processing_task is not None and not processing_task.done():
                processing_task.cancel()
            voice_sessions.pop(request_id, None)
            return

        if payload_type == "voice_chunk":
            try:
                chunk_bytes = _decode_global_voice_stream_chunk(payload.get("audio_base64"))
            except ValueError as exc:
                await websocket.send_json(
                    {
                        "type": "voice_error",
                        "request_id": request_id,
                        "message": str(exc),
                    }
                )
                return
            if chunk_bytes:
                pcm_buffer = session.get("pcm_buffer")
                if not isinstance(pcm_buffer, bytearray):
                    pcm_buffer = bytearray()
                    session["pcm_buffer"] = pcm_buffer
                pcm_buffer.extend(chunk_bytes)
                max_buffer_bytes = int(session.get("max_buffer_bytes") or 0)
                if max_buffer_bytes > 0 and len(pcm_buffer) > max_buffer_bytes:
                    session["pcm_buffer"] = bytearray(pcm_buffer[-max_buffer_bytes:])
                full_pcm_buffer = session.get("full_pcm_buffer")
                if not isinstance(full_pcm_buffer, bytearray):
                    full_pcm_buffer = bytearray()
                    session["full_pcm_buffer"] = full_pcm_buffer
                full_pcm_buffer.extend(chunk_bytes)
                full_max_buffer_bytes = int(session.get("full_max_buffer_bytes") or 0)
                if (
                    full_max_buffer_bytes > 0
                    and len(full_pcm_buffer) > full_max_buffer_bytes
                ):
                    session["full_pcm_buffer"] = bytearray(
                        full_pcm_buffer[-full_max_buffer_bytes:]
                    )
            if bool(payload.get("is_final")):
                session["pending_stop"] = True
            await maybe_flush_voice_session(
                request_id,
                force=bool(payload.get("is_final")),
            )
            return

        if payload_type == "voice_stop":
            session["pending_stop"] = True
            await maybe_flush_voice_session(request_id, force=True)
            return

        await websocket.send_json(
            {
                "type": "voice_error",
                "request_id": request_id,
                "message": "不支持的语音消息类型",
            }
        )

    async def handle_request(payload: dict):
        nonlocal active_tasks, cancel_events
        request_id = str(payload.get("request_id") or "").strip()
        if str(payload.get("type") or "").strip().lower() == "ping":
            await websocket.send_json({"type": "pong", "request_id": request_id})
            return

        if str(payload.get("type") or "").strip().lower() == "cancel":
            if request_id in cancel_events:
                cancel_events[request_id].set()
            return

        try:
            req = ProjectChatReq.model_validate(payload)
        except Exception as exc:
            await websocket.send_json(
                {
                    "type": "error",
                    "request_id": request_id,
                    "message": f"Invalid payload: {str(exc)}",
                }
            )
            return

        user_message = str(req.message or "").strip()
        normalized_images = _normalize_image_inputs(req.images)
        attachment_names = [
            str(name or "").strip()
            for name in (req.attachment_names or [])
            if str(name or "").strip()
        ]
        if not user_message and not normalized_images and not attachment_names:
            await websocket.send_json(
                {
                    "type": "error",
                    "request_id": request_id,
                    "message": "message is required",
                }
            )
            return

        try:
            chat_session_id = _require_project_chat_session_id(req.chat_session_id)
        except ValueError as exc:
            await websocket.send_json(
                {
                    "type": "error",
                    "request_id": request_id,
                    "message": str(exc),
                }
            )
            return

        effective_user_message = user_message
        if not effective_user_message and attachment_names:
            effective_user_message = f"我上传了附件：{'、'.join(attachment_names)}。请先给我处理建议。"
        elif not effective_user_message and normalized_images:
            effective_user_message = "请基于我上传的图片给建议。"
        cancel_event = asyncio.Event()
        cancel_events[request_id] = cancel_event

        try:
            runtime_snapshot = await _build_global_assistant_runtime_snapshot(
                auth_payload,
                route_path=req.route_path,
                route_title=req.route_title,
            )
            runtime_settings = _normalize_project_chat_settings(
                {
                    "provider_id": req.provider_id,
                    "model_name": req.model_name,
                    "temperature": req.temperature,
                    "max_tokens": req.max_tokens,
                    "system_prompt": req.system_prompt,
                    "history_limit": req.history_limit,
                    "answer_style": req.answer_style,
                    "prefer_conclusion_first": req.prefer_conclusion_first,
                    "max_loop_rounds": req.max_loop_rounds,
                    "max_tool_rounds": req.max_tool_rounds,
                    "repeated_tool_call_threshold": req.repeated_tool_call_threshold,
                    "tool_only_threshold": req.tool_only_threshold,
                    "tool_budget_strategy": req.tool_budget_strategy,
                    "max_tool_calls_per_round": req.max_tool_calls_per_round,
                    "tool_timeout_sec": req.tool_timeout_sec,
                    "tool_retry_count": req.tool_retry_count,
                }
            )
            resolved_runtime = await _resolve_global_assistant_chat_runtime(
                runtime_settings,
                auth_payload,
            )
            provider_mode = resolved_runtime.provider_mode
            selected_provider = resolved_runtime.provider
            provider_id = resolved_runtime.provider_id
            model_name = resolved_runtime.model_name
            global_assistant_tools = build_global_assistant_builtin_tools()
            messages = _build_global_chat_messages(
                effective_user_message,
                req.history,
                normalized_images,
                custom_system_prompt=_resolve_default_chat_system_prompt(
                    runtime_settings.get("system_prompt")
                ),
                history_limit=int(runtime_settings.get("history_limit") or 20),
                answer_style=str(runtime_settings.get("answer_style") or "concise"),
                prefer_conclusion_first=bool(
                    runtime_settings.get("prefer_conclusion_first", True)
                ),
                skill_resource_directory=req.skill_resource_directory,
                chat_surface=req.chat_surface,
                runtime_snapshot=runtime_snapshot,
            )
            runtime_context = build_chat_runtime_context(
                project_id=_GLOBAL_ASSISTANT_STORE_PROJECT_ID,
                username=username,
                chat_session_id=chat_session_id,
                skill_resource_directory=req.skill_resource_directory,
                chat_surface=req.chat_surface,
                history=req.history,
                images=normalized_images,
                chat_settings=runtime_settings,
                resolved_provider=resolved_runtime,
                tools=global_assistant_tools,
                messages=messages,
                runtime_snapshot=runtime_snapshot,
            )
        except Exception as exc:
            await websocket.send_json(
                {
                    "type": "error",
                    "request_id": request_id,
                    "message": str(exc),
                }
            )
            return

        await websocket.send_json(
            {
                "type": "start",
                "request_id": request_id,
                "provider_id": provider_id,
                "model_name": model_name,
                "chat_mode": "system",
                "tools_enabled": bool(global_assistant_tools),
            }
        )

        try:
            from services.llm_provider_service import get_llm_provider_service

            llm_service = get_llm_provider_service()
            llm_service_runtime = _resolve_chat_llm_service_runtime(
                llm_service,
                resolved_runtime,
                auth_payload,
            )

            redis_client = await get_redis_client()
            conv_manager = ConversationManager(redis_client)
            session_id = await conv_manager.create_session(
                _GLOBAL_ASSISTANT_STORE_PROJECT_ID,
                "",
            )
            orchestrator = build_agent_orchestrator(
                llm_service_runtime,
                conv_manager,
                runtime_settings,
                orchestrator_cls=AgentOrchestrator,
            )

            final_answer = ""
            stream_error = ""
            async for chunk_data in orchestrator.run(
                **build_orchestrator_run_kwargs(
                    session_id=session_id,
                    user_message=effective_user_message,
                    runtime_context=runtime_context,
                    temperature=float(runtime_settings.get("temperature") or 0.1),
                    max_tokens=_resolve_chat_max_tokens(runtime_settings.get("max_tokens")),
                    cancel_event=cancel_event,
                    role_ids=_current_role_ids(auth_payload),
                    global_assistant_bridge_handler=lambda tool_name, args: call_browser_tool(
                        tool_name,
                        args,
                        request_id=request_id,
                    ),
                )
            ):
                outgoing = dict(chunk_data)
                event_type = str(outgoing.get("type") or "").strip().lower()
                if event_type == "done":
                    final_answer = str(outgoing.get("content") or "").strip()
                    if not final_answer:
                        final_answer = "模型未返回有效内容。"
                        outgoing["content"] = final_answer
                if event_type == "error":
                    stream_error = str(outgoing.get("message") or "未知错误").strip()
                outgoing["request_id"] = request_id
                await websocket.send_json(outgoing)

            if stream_error:
                return
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            await websocket.send_json(
                {
                    "type": "error",
                    "request_id": request_id,
                    "message": str(exc),
                }
            )
        finally:
            if "conv_manager" in locals() and "session_id" in locals():
                try:
                    await conv_manager.delete_session(session_id)
                except Exception:
                    pass
            cancel_events.pop(request_id, None)
            active_tasks.pop(request_id, None)

    while True:
        try:
            payload = await websocket.receive_json()
            if not isinstance(payload, dict):
                await websocket.send_json({"type": "error", "message": "Invalid payload type"})
                continue

            request_id = str(payload.get("request_id") or "").strip()
            payload_type = str(payload.get("type") or "").strip().lower()
            if payload_type == "cancel":
                if request_id in cancel_events:
                    cancel_events[request_id].set()
                continue
            if payload_type == "browser_tool_result":
                await handle_browser_tool_result(payload)
                continue
            if payload_type.startswith("voice_"):
                await handle_voice_payload(payload)
                continue

            task = asyncio.create_task(handle_request(payload))
            if request_id:
                active_tasks[request_id] = task
        except WebSocketDisconnect:
            for ev in cancel_events.values():
                ev.set()
            for task in active_tasks.values():
                task.cancel()
            for session in voice_sessions.values():
                processing_task = session.get("processing_task")
                if processing_task is not None and not processing_task.done():
                    processing_task.cancel()
            for future in browser_tool_futures.values():
                if not future.done():
                    future.set_result({"error": "Browser websocket disconnected"})
            browser_tool_futures.clear()
            voice_sessions.clear()
            break
        except Exception:
            await websocket.send_json({"type": "error", "message": "Invalid JSON payload"})
            continue


@router.post("/chat/global")
async def chat_without_project(
    req: ProjectChatReq,
    auth_payload: dict = Depends(require_auth),
):
    from services.llm_provider_service import get_llm_provider_service

    _ensure_permission(auth_payload, "menu.ai.chat")

    user_message = str(req.message or "").strip()
    normalized_images = _normalize_image_inputs(req.images)
    attachment_names = [
        str(name or "").strip()
        for name in (req.attachment_names or [])
        if str(name or "").strip()
    ]
    if not user_message and not normalized_images and not attachment_names:
        raise HTTPException(400, "message is required")

    runtime_settings = _normalize_project_chat_settings(
        {
            "provider_id": req.provider_id,
            "model_name": req.model_name,
            "temperature": req.temperature,
            "max_tokens": req.max_tokens,
            "system_prompt": req.system_prompt,
            "history_limit": req.history_limit,
            "answer_style": req.answer_style,
            "prefer_conclusion_first": req.prefer_conclusion_first,
        }
    )
    resolved_runtime = await _resolve_global_assistant_chat_runtime(
        runtime_settings,
        auth_payload,
    )
    provider_mode = resolved_runtime.provider_mode
    selected_provider = resolved_runtime.provider
    provider_id = resolved_runtime.provider_id
    model_name = resolved_runtime.model_name

    effective_user_message = user_message
    if not effective_user_message and attachment_names:
        effective_user_message = (
            f"我上传了附件：{'、'.join(attachment_names)}。请先给我处理建议。"
        )
    runtime_snapshot = await _build_global_assistant_runtime_snapshot(
        auth_payload,
        route_path=req.route_path,
        route_title=req.route_title,
    )
    global_assistant_tools = build_global_assistant_builtin_tools()
    messages = _build_global_chat_messages(
        effective_user_message,
        req.history,
        normalized_images,
        custom_system_prompt=_resolve_default_chat_system_prompt(
            runtime_settings.get("system_prompt")
        ),
        history_limit=int(runtime_settings.get("history_limit") or 20),
        answer_style=str(runtime_settings.get("answer_style") or "concise"),
        prefer_conclusion_first=bool(
            runtime_settings.get("prefer_conclusion_first", True)
        ),
        skill_resource_directory=req.skill_resource_directory,
        chat_surface=req.chat_surface,
        runtime_snapshot=runtime_snapshot,
    )
    runtime_context = build_chat_runtime_context(
        project_id=_GLOBAL_ASSISTANT_STORE_PROJECT_ID,
        username=_current_username(auth_payload),
        chat_session_id=str(req.chat_session_id or "").strip(),
        skill_resource_directory=req.skill_resource_directory,
        chat_surface=req.chat_surface,
        history=req.history,
        images=normalized_images,
        chat_settings=runtime_settings,
        resolved_provider=resolved_runtime,
        tools=global_assistant_tools,
        messages=messages,
        runtime_snapshot=runtime_snapshot,
    )
    try:
        llm_service = get_llm_provider_service()
        llm_service_runtime = _resolve_chat_llm_service_runtime(
            llm_service,
            resolved_runtime,
            auth_payload,
        )

        redis_client = await get_redis_client()
        conv_manager = ConversationManager(redis_client)
        session_id = await conv_manager.create_session(
            _GLOBAL_ASSISTANT_STORE_PROJECT_ID,
            "",
        )
        orchestrator = build_agent_orchestrator(
            llm_service_runtime,
            conv_manager,
            runtime_settings,
            orchestrator_cls=AgentOrchestrator,
        )

        answer = ""
        stream_error = ""
        async for chunk_data in orchestrator.run(
            **build_orchestrator_run_kwargs(
                session_id=session_id,
                user_message=effective_user_message,
                runtime_context=runtime_context,
                temperature=float(runtime_settings.get("temperature") or 0.1),
                max_tokens=_resolve_chat_max_tokens(runtime_settings.get("max_tokens")),
                cancel_event=asyncio.Event(),
                role_ids=_current_role_ids(auth_payload),
            )
        ):
            event_type = str(chunk_data.get("type") or "").strip().lower()
            if event_type == "done":
                answer = str(chunk_data.get("content") or "").strip() or "模型未返回有效内容。"
            elif event_type == "error":
                stream_error = str(chunk_data.get("message") or "Global chat failed").strip()
        if stream_error:
            raise HTTPException(500, stream_error)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"Global chat failed: {exc}") from exc
    finally:
        if "conv_manager" in locals() and "session_id" in locals():
            try:
                await conv_manager.delete_session(session_id)
            except Exception:
                pass

    return {
        "content": answer,
        "provider_id": provider_id,
        "model_name": model_name,
    }


def _extract_ws_auth_payload(websocket: WebSocket) -> dict | None:
    token = str(websocket.query_params.get("token") or "").strip()
    if token:
        payload = decode_token(token)
        if payload is not None:
            return payload
    auth_header = str(websocket.headers.get("authorization") or "").strip()
    if auth_header.startswith("Bearer "):
        return decode_token(auth_header[7:])
    return None


def _pick_directory_via_native_dialog(
    initial_path: str = "",
    title: str = "选择工作区目录",
) -> str:
    normalized_title = str(title or "选择工作区目录").strip() or "选择工作区目录"
    initial = Path(str(initial_path or "").strip()).expanduser()
    initial_dir = initial if initial.is_dir() else (initial.parent if str(initial_path or "").strip() else None)

    if sys.platform == "darwin":
        osa_args = ["osascript"]
        if initial_dir and initial_dir.exists():
            osa_args.extend(
                [
                    "-e",
                    f'set chosenFolder to choose folder with prompt "{normalized_title.replace(chr(34), chr(92) + chr(34))}" default location POSIX file "{str(initial_dir).replace(chr(34), chr(92) + chr(34))}"',
                ]
            )
        else:
            osa_args.extend(
                [
                    "-e",
                    f'set chosenFolder to choose folder with prompt "{normalized_title.replace(chr(34), chr(92) + chr(34))}"',
                ]
            )
        osa_args.extend(["-e", "POSIX path of chosenFolder"])
        result = subprocess.run(osa_args, capture_output=True, text=True)
        if result.returncode != 0:
            message = str(result.stderr or result.stdout or "").strip()
            if "User canceled" in message or "(-128)" in message:
                return ""
            raise RuntimeError(message or "macOS 原生目录选择失败")
        return str(result.stdout or "").strip().rstrip("/") or ""

    if sys.platform.startswith("win"):
        ps_command = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$dialog = New-Object System.Windows.Forms.FolderBrowserDialog; "
            f'$dialog.Description = "{normalized_title.replace(chr(34), chr(92) + chr(34))}"; '
        )
        if initial_dir and initial_dir.exists():
            ps_command += (
                f'$dialog.SelectedPath = "{str(initial_dir).replace(chr(34), chr(92) + chr(34))}"; '
            )
        ps_command += (
            'if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) '
            '{ [Console]::Write($dialog.SelectedPath) }'
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_command],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            message = str(result.stderr or result.stdout or "").strip()
            raise RuntimeError(message or "Windows 原生目录选择失败")
        return str(result.stdout or "").strip()

    if shutil.which("zenity"):
        result = subprocess.run(
            [
                "zenity",
                "--file-selection",
                "--directory",
                f"--title={normalized_title}",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 1:
            return ""
        if result.returncode != 0:
            raise RuntimeError(str(result.stderr or result.stdout or "").strip() or "zenity 目录选择失败")
        return str(result.stdout or "").strip()

    if shutil.which("kdialog"):
        args = ["kdialog", "--getexistingdirectory"]
        if initial_dir and initial_dir.exists():
            args.append(str(initial_dir))
        args.extend(["--title", normalized_title])
        result = subprocess.run(args, capture_output=True, text=True)
        if result.returncode == 1:
            return ""
        if result.returncode != 0:
            raise RuntimeError(str(result.stderr or result.stdout or "").strip() or "kdialog 目录选择失败")
        return str(result.stdout or "").strip()

    raise RuntimeError("当前服务端环境不支持原生目录选择器，或运行在无桌面界面的 headless 模式")


def _pick_file_via_native_dialog(
    initial_path: str = "",
    title: str = "选择文件",
) -> str:
    normalized_title = str(title or "选择文件").strip() or "选择文件"
    initial = Path(str(initial_path or "").strip()).expanduser()
    initial_dir = initial.parent if initial.is_file() else (initial if initial.is_dir() else (initial.parent if str(initial_path or "").strip() else None))

    if sys.platform == "darwin":
        osa_args = ["osascript"]
        if initial_dir and initial_dir.exists():
            osa_args.extend(
                [
                    "-e",
                    f'set chosenFile to choose file with prompt "{normalized_title.replace(chr(34), chr(92) + chr(34))}" default location POSIX file "{str(initial_dir).replace(chr(34), chr(92) + chr(34))}"',
                ]
            )
        else:
            osa_args.extend(
                [
                    "-e",
                    f'set chosenFile to choose file with prompt "{normalized_title.replace(chr(34), chr(92) + chr(34))}"',
                ]
            )
        osa_args.extend(["-e", "POSIX path of chosenFile"])
        result = subprocess.run(osa_args, capture_output=True, text=True)
        if result.returncode != 0:
            message = str(result.stderr or result.stdout or "").strip()
            if "User canceled" in message or "(-128)" in message:
                return ""
            raise RuntimeError(message or "macOS 原生文件选择失败")
        return str(result.stdout or "").strip()

    if sys.platform.startswith("win"):
        ps_command = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$dialog = New-Object System.Windows.Forms.OpenFileDialog; "
            f'$dialog.Title = "{normalized_title.replace(chr(34), chr(92) + chr(34))}"; '
        )
        if initial_dir and initial_dir.exists():
            ps_command += (
                f'$dialog.InitialDirectory = "{str(initial_dir).replace(chr(34), chr(92) + chr(34))}"; '
            )
        ps_command += (
            'if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) '
            '{ [Console]::Write($dialog.FileName) }'
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_command],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            message = str(result.stderr or result.stdout or "").strip()
            raise RuntimeError(message or "Windows 原生文件选择失败")
        return str(result.stdout or "").strip()

    if shutil.which("zenity"):
        result = subprocess.run(
            [
                "zenity",
                "--file-selection",
                f"--title={normalized_title}",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 1:
            return ""
        if result.returncode != 0:
            raise RuntimeError(str(result.stderr or result.stdout or "").strip() or "zenity 文件选择失败")
        return str(result.stdout or "").strip()

    if shutil.which("kdialog"):
        args = ["kdialog", "--getopenfilename"]
        if initial_dir and initial_dir.exists():
            args.append(str(initial_dir))
        args.extend(["--title", normalized_title])
        result = subprocess.run(args, capture_output=True, text=True)
        if result.returncode == 1:
            return ""
        if result.returncode != 0:
            raise RuntimeError(str(result.stderr or result.stdout or "").strip() or "kdialog 文件选择失败")
        return str(result.stdout or "").strip()

    raise RuntimeError("当前服务端环境不支持原生文件选择器，或运行在无桌面界面的 headless 模式")


def _chunk_text(content: str, chunk_size: int = 42) -> list[str]:
    text = str(content or "")
    if not text:
        return []
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]


def _sse_payload(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _is_project_meta_query(message: str) -> bool:
    # 关闭固定模板直出，统一走模型+工具决策。
    _ = message
    return False


def _is_mcp_modules_query(message: str) -> bool:
    # 关闭固定模板直出，统一走模型+工具决策。
    _ = message
    return False


def _extract_tool_probe_name(message: str) -> str:
    # 关闭固定模板直出，统一走模型+工具决策。
    _ = message
    return ""


def _build_tool_probe_reply(
    project_id: str,
    employee_id: str,
    tool_name: str,
    enabled_project_tool_names: list[str] | None,
    *,
    explicit_filter: bool,
) -> str:
    from services.dynamic_mcp_runtime import list_project_proxy_tools_runtime

    tools = list_project_proxy_tools_runtime(project_id, employee_id)
    tools = _filter_project_tools_by_names(
        tools,
        enabled_project_tool_names,
        explicit_filter=explicit_filter,
    )
    available_names = [
        str(item.get("tool_name") or "").strip()
        for item in tools
        if str(item.get("tool_name") or "").strip()
    ]
    available_set = set(available_names)
    can_use = tool_name in available_set
    status = "可以使用" if can_use else "当前不可用"
    preview = "、".join(available_names[:12]) if available_names else "无"
    return (
        f"`{tool_name}` {status}。\n"
        f"- 本轮可用工具数：{len(available_names)}\n"
        f"- 本轮可用工具：{preview}"
    )


def _build_mcp_modules_reply(project_id: str) -> str:
    payload = _build_chat_mcp_modules(project_id)
    project_related = list(payload.get("system", {}).get("project_related") or [])
    system_global = list(payload.get("system", {}).get("system_global") or [])
    external_modules = list(payload.get("external", {}).get("modules") or [])

    def _names(items: list[dict[str, Any]], limit: int = 12) -> str:
        values: list[str] = []
        for item in items[:limit]:
            name = str(item.get("name") or item.get("tool_name") or item.get("id") or "").strip()
            if name:
                values.append(name)
        return "、".join(values) if values else "无"

    lines = [
        f"当前项目 `{project_id}` 的 MCP 模块清单：",
        f"1. 系统提供-项目关联：{len(project_related)} 个",
        f"   { _names(project_related) }",
        f"2. 系统提供-系统全局：{len(system_global)} 个",
        f"   { _names(system_global) }",
        f"3. 外部模块：{len(external_modules)} 个",
        f"   { _names(external_modules) }",
    ]
    return "\n".join(lines)


def _should_enable_chat_tools(message: str, attachment_names: list[str], images: list[str]) -> bool:
    text = str(message or "").strip()
    if not text and not attachment_names and not images:
        return False
    return True


def _build_project_meta_reply(project: ProjectConfig, selected_employee: dict[str, Any] | None, candidates: list[dict[str, Any]]) -> str:
    lines = [
        f"- 当前绑定项目：`{project.name}`",
        f"- 项目 ID：`{project.id}`",
        f"- 项目描述：`{project.description or '-'}`",
    ]
    if project.workspace_path:
        lines.append(f"- 工作区路径：`{project.workspace_path}`")
    lines.append(f"- 成员数：`{len(candidates)}`")
    if selected_employee:
        lines.append(
            f"- 当前执行员工：`{selected_employee.get('name') or selected_employee.get('id')}` "
            f"(`{selected_employee.get('id')}`)"
        )
    if candidates:
        preview = "、".join(
            f"{item.get('name') or item.get('id')}({item.get('role') or 'member'})" for item in candidates[:5]
        )
        lines.append(f"- 项目成员：{preview}")
    lines.append("（以上为系统绑定的项目元数据，不是目录扫描结果）")
    return "\n".join(lines)


@router.get("")
async def list_projects(auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "menu.projects")
    projects = project_store.list_all()
    project_ids = [str(getattr(item, "id", "") or "").strip() for item in projects if str(getattr(item, "id", "") or "").strip()]
    current_username = _current_username(auth_payload)
    admin_like = _is_admin_like(auth_payload)
    membership_map = (
        {}
        if admin_like or not current_username
        else project_store.list_user_memberships(current_username, project_ids)
    )
    if admin_like:
        visible_projects = projects
    else:
        visible_projects = [
            item
            for item in projects
            if bool(getattr(membership_map.get(str(getattr(item, "id", "") or "").strip()), "enabled", False))
        ]
    visible_project_ids = [
        str(getattr(item, "id", "") or "").strip()
        for item in visible_projects
        if str(getattr(item, "id", "") or "").strip()
    ]
    member_counts = project_store.list_member_counts(visible_project_ids)
    user_counts = project_store.list_user_member_counts(visible_project_ids)
    creator_usernames = {
        str(getattr(item, "id", "") or "").strip(): str(getattr(item, "created_by", "") or "").strip()
        for item in visible_projects
        if str(getattr(item, "id", "") or "").strip() and str(getattr(item, "created_by", "") or "").strip()
    }
    unresolved_creator_project_ids = [
        project_id for project_id in visible_project_ids if project_id not in creator_usernames
    ]
    if unresolved_creator_project_ids:
        creator_usernames.update(project_store.list_owner_usernames(unresolved_creator_project_ids))
    return {
        "projects": [
            _serialize_project_list_item(
                item,
                auth_payload,
                member_count=member_counts.get(item.id, 0),
                user_count=user_counts.get(item.id, 0),
                creator_username=creator_usernames.get(item.id, ""),
                current_member=membership_map.get(item.id),
            )
            for item in visible_projects
        ]
    }


@router.post("/workspace-directory/pick")
async def pick_workspace_directory(
    req: WorkspaceDirectoryPickReq,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_any_permission(auth_payload, ["menu.projects", "menu.ai.chat"])
    try:
        selected = await run_in_threadpool(
            _pick_directory_via_native_dialog,
            str(req.initial_path or "").strip(),
            str(req.title or "选择工作区目录").strip() or "选择工作区目录",
        )
    except RuntimeError as exc:
        raise HTTPException(501, str(exc)) from exc
    if not selected:
        return {"path": "", "cancelled": True, "source": "native_dialog"}
    return {"path": selected, "cancelled": False, "source": "native_dialog"}


@router.post("/workspace-file/pick")
async def pick_workspace_file(
    req: WorkspaceFilePickReq,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_any_permission(auth_payload, ["menu.projects", "menu.ai.chat"])
    try:
        selected = await run_in_threadpool(
            _pick_file_via_native_dialog,
            str(req.initial_path or "").strip(),
            str(req.title or "选择文件").strip() or "选择文件",
        )
    except RuntimeError as exc:
        raise HTTPException(501, str(exc)) from exc
    if not selected:
        return {"path": "", "cancelled": True, "source": "native_dialog"}
    return {"path": selected, "cancelled": False, "source": "native_dialog"}


@router.post("")
async def create_project(req: ProjectCreateReq, auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "menu.projects")
    creator_username = _normalize_project_username(_current_username(auth_payload))
    project = ProjectConfig(
        id=project_store.new_id(),
        name=str(req.name or "").strip(),
        description=req.description,
        created_by=creator_username,
        type=_normalize_project_type(req.type),
        ui_rule_ids=_normalize_project_ui_rule_ids(req.ui_rule_ids),
        experience_rule_ids=_normalize_project_experience_rule_ids(req.experience_rule_ids),
        mcp_instruction=_normalize_project_mcp_instruction_for_save(req.mcp_instruction),
        workspace_path=_normalize_workspace_path_for_save(req.workspace_path),
        ai_entry_file=_normalize_ai_entry_file_for_save(req.ai_entry_file),
        mcp_enabled=req.mcp_enabled,
        feedback_upgrade_enabled=req.feedback_upgrade_enabled,
    )
    if not project.name:
        raise HTTPException(400, "name is required")
    project_store.save(project)
    project_store.upsert_user_member(
        ProjectUserMember(
            project_id=project.id,
            username=creator_username,
            role="owner",
            enabled=True,
            joined_at=_now_iso(),
        )
    )
    _sync_feedback_project_flag(project.id, project.feedback_upgrade_enabled)
    return {"status": "created", "project": _serialize_project(project, auth_payload)}


@router.get("/{project_id}")
async def get_project(project_id: str, auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "menu.projects")
    project = _ensure_project_access(project_id, auth_payload)
    return {"project": _serialize_project(project, auth_payload)}


@router.get("/{project_id}/materials")
async def list_project_materials(
    project_id: str,
    group_type: str = Query(""),
    asset_type: str = Query(""),
    query: str = Query(""),
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_access(project_id, auth_payload)
    items = _filter_project_material_assets(
        project_material_store.list_by_project(project_id),
        group_type=group_type,
        asset_type=asset_type,
        query=query,
    )
    return {
        "items": [_serialize_project_material_asset(item) for item in items],
        "summary": {
            "total": len(items),
            "image_count": sum(1 for item in items if item.asset_type == "image"),
            "storyboard_count": sum(1 for item in items if item.asset_type == "storyboard"),
            "video_count": sum(1 for item in items if item.asset_type == "video"),
            "audio_count": sum(1 for item in items if item.asset_type == "audio"),
        },
    }


@router.post("/{project_id}/materials")
async def create_project_material(
    project_id: str,
    req: ProjectMaterialAssetCreateReq,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_manage_access(project_id, auth_payload)
    asset_type = _normalize_material_asset_type(req.asset_type)
    asset = ProjectMaterialAsset(
        id=project_material_store.new_id(),
        project_id=project_id,
        asset_type=asset_type,
        group_type=_infer_material_group_type(asset_type),
        title=_normalize_material_text(req.title, limit=120),
        summary=_normalize_material_text(req.summary, limit=1000),
        source_type="manual_collect",
        source_message_id=_normalize_material_text(req.source_message_id, limit=120),
        source_chat_session_id=_normalize_material_text(req.source_chat_session_id, limit=120),
        source_username=_normalize_material_text(req.source_username, limit=120),
        created_by=_normalize_material_text(auth_payload.get("sub"), limit=120),
        preview_url=_normalize_material_url(req.preview_url),
        content_url=_normalize_material_url(req.content_url),
        mime_type=_normalize_material_text(req.mime_type, limit=120),
        status=_normalize_material_status(req.status),
        structured_content=_normalize_material_mapping(req.structured_content),
        metadata=_normalize_material_mapping(req.metadata),
    )
    if not asset.title:
        raise HTTPException(400, "title is required")
    project_material_store.save(asset)
    return {"status": "created", "item": _serialize_project_material_asset(asset)}


@router.post("/{project_id}/materials/upload")
async def upload_project_material(
    project_id: str,
    file: UploadFile = File(...),
    cover_file: UploadFile | None = File(None),
    asset_type: str = Form("image"),
    title: str = Form(""),
    summary: str = Form(""),
    mime_type: str = Form(""),
    cover_mime_type: str = Form(""),
    cover_source: str = Form(""),
    structured_content: str = Form(""),
    metadata: str = Form(""),
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_manage_access(project_id, auth_payload)
    normalized_asset_type = _normalize_material_asset_type(asset_type)
    structured_content_payload = _parse_material_json_text(structured_content, "structured_content")
    uploaded_metadata = _parse_material_json_text(metadata, "metadata")
    normalized_title = _normalize_material_text(
        title or Path(str(file.filename or "").strip()).stem,
        limit=120,
    )
    if not normalized_title:
        raise HTTPException(400, "title is required")
    normalized_mime_type = _normalize_material_text(
        _infer_material_upload_mime_type(file, mime_type),
        limit=120,
    )
    if not normalized_mime_type:
        raise HTTPException(400, "mime_type is required")
    _validate_material_upload_type(normalized_asset_type, normalized_mime_type)
    if normalized_asset_type == "video":
        uploaded_metadata = _require_material_video_duration_metadata(uploaded_metadata)
    if normalized_asset_type != "video" and cover_file is not None:
        await cover_file.close()
        raise HTTPException(400, "只有视频素材支持单独上传封面")
    asset_id = project_material_store.new_id()
    original_filename = Path(str(file.filename or "").strip()).name
    safe_filename = _sanitize_material_filename(original_filename, f"{asset_id}.bin")
    relative_path = Path(project_id) / asset_id / safe_filename
    absolute_path = _project_material_file_root() / relative_path
    cover_relative_path = Path()
    cover_file_size_bytes = 0
    cover_original_filename = ""
    cover_file_url = ""
    cover_mime_type_value = ""
    try:
        file_size_bytes = await _write_material_upload_file(file, absolute_path)
        if normalized_asset_type == "video" and cover_file is not None:
            cover_original_filename = Path(str(cover_file.filename or "").strip()).name
            safe_cover_filename = _sanitize_material_filename(
                cover_original_filename,
                f"{asset_id}-cover.bin",
            )
            cover_relative_path = Path(project_id) / asset_id / f"cover-{safe_cover_filename}"
            cover_absolute_path = _project_material_file_root() / cover_relative_path
            cover_mime_type_value = _normalize_material_text(
                _infer_material_upload_mime_type(cover_file, cover_mime_type),
                limit=120,
            )
            _validate_material_cover_upload_type(cover_mime_type_value)
            cover_file_size_bytes = await _write_material_upload_file(cover_file, cover_absolute_path)
            cover_file_url = _build_material_cover_url(project_id, asset_id)
    finally:
        await file.close()
        if cover_file is not None:
            await cover_file.close()
    uploaded_metadata = {
        **uploaded_metadata,
        "storage_kind": "local_file",
        "storage_path": relative_path.as_posix(),
    }
    if cover_file_url and cover_relative_path.as_posix():
        uploaded_metadata = {
            **uploaded_metadata,
            "cover_storage_path": cover_relative_path.as_posix(),
            "cover_original_filename": _normalize_material_text(cover_original_filename, limit=240),
            "cover_mime_type": cover_mime_type_value,
            "cover_file_size_bytes": cover_file_size_bytes,
            "cover_source": _normalize_material_text(cover_source, limit=120) or "manual_upload",
        }
    file_url = _build_material_file_url(project_id, asset_id)
    preview_url = ""
    if normalized_asset_type == "image":
        preview_url = file_url
    elif normalized_asset_type == "video":
        preview_url = cover_file_url or file_url
    asset = ProjectMaterialAsset(
        id=asset_id,
        project_id=project_id,
        asset_type=normalized_asset_type,
        group_type=_infer_material_group_type(normalized_asset_type),
        title=normalized_title,
        summary=_normalize_material_text(summary, limit=1000),
        source_type="manual_upload",
        created_by=_normalize_material_text(auth_payload.get("sub"), limit=120),
        original_filename=_normalize_material_text(original_filename, limit=240),
        file_size_bytes=file_size_bytes,
        preview_url=preview_url,
        content_url=file_url,
        mime_type=normalized_mime_type,
        status="ready",
        structured_content=structured_content_payload,
        metadata=uploaded_metadata,
    )
    project_material_store.save(asset)
    return {"status": "created", "item": _serialize_project_material_asset(asset)}


@router.post("/{project_id}/studio/audio/upload")
async def upload_project_studio_audio(
    project_id: str,
    file: UploadFile = File(...),
    title: str = Form(""),
    mime_type: str = Form(""),
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_manage_access(project_id, auth_payload)
    audio_id = project_studio_export_store.new_id().replace("studio-export-", "studio-audio-", 1)
    original_filename = Path(str(file.filename or "").strip()).name
    safe_filename = _sanitize_material_filename(original_filename, f"{audio_id}.bin")
    normalized_mime_type = _normalize_material_text(
        _infer_material_upload_mime_type(file, mime_type),
        limit=120,
    )
    _validate_studio_audio_upload_type(normalized_mime_type)
    relative_path = Path(project_id) / "studio-audio" / audio_id / safe_filename
    absolute_path = _project_material_file_root() / relative_path
    try:
        file_size_bytes = await _write_material_upload_file(file, absolute_path)
    finally:
        await file.close()
    normalized_title = _normalize_material_text(
        title or Path(original_filename).stem or "背景音乐",
        limit=120,
    ) or "背景音乐"
    return {
        "status": "created",
        "item": {
            "id": audio_id,
            "title": normalized_title,
            "content_url": _build_studio_audio_file_url(project_id, audio_id),
            "mime_type": normalized_mime_type,
            "original_filename": _normalize_material_text(original_filename, limit=240),
            "file_size_bytes": file_size_bytes,
            "storage_path": relative_path.as_posix(),
            "source_type": "manual_upload",
        },
    }


@router.get("/{project_id}/studio/audio/{audio_id}/file")
async def get_project_studio_audio_file(
    project_id: str,
    audio_id: str,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_access(project_id, auth_payload)
    normalized_project_id = _normalize_material_text(project_id, limit=120)
    normalized_audio_id = _normalize_material_text(audio_id, limit=120)
    if (
        not normalized_project_id
        or not normalized_audio_id
        or "/" in normalized_audio_id
        or "\\" in normalized_audio_id
        or ".." in normalized_audio_id
    ):
        raise HTTPException(404, "Studio audio not found")
    audio_root = _project_material_file_root() / normalized_project_id / "studio-audio" / normalized_audio_id
    if not audio_root.exists() or not audio_root.is_dir():
        raise HTTPException(404, "Studio audio not found")
    candidates = sorted(path for path in audio_root.iterdir() if path.is_file())
    if not candidates:
        raise HTTPException(404, "Studio audio not found")
    file_path = candidates[0]
    mime_type, _ = mimetypes.guess_type(file_path.name)
    return FileResponse(
        path=file_path,
        media_type=_normalize_material_text(mime_type, limit=120) or None,
        headers={
            "Content-Disposition": _build_inline_content_disposition(file_path.name, file_path.name)
        },
    )


@router.get("/{project_id}/studio/voices")
async def list_project_studio_voices(
    project_id: str,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_access(project_id, auth_payload)
    voice_service = get_project_voice_service()
    return {
        "project_id": project_id,
        "items": voice_service.list_project_voices(project_id),
    }


@router.post("/{project_id}/studio/voices")
async def create_project_studio_voice(
    project_id: str,
    mode: str = Form("clone"),
    provider_id: str = Form(""),
    model_name: str = Form(""),
    name: str = Form(""),
    voice_id: str = Form(""),
    transcript_text: str = Form(""),
    preview_text: str = Form(""),
    description: str = Form(""),
    sample_file: UploadFile | None = File(None),
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_manage_access(project_id, auth_payload)
    normalized_project_id = _normalize_material_text(project_id, limit=120)
    normalized_provider_id = _normalize_material_text(provider_id, limit=120)
    normalized_model_name = _normalize_material_text(model_name, limit=160)
    normalized_name = _normalize_material_text(name, limit=120)
    normalized_mode = _normalize_material_text(mode, limit=40).lower() or "clone"
    normalized_voice_id = _normalize_material_text(voice_id, limit=200)
    normalized_transcript = _normalize_material_text(transcript_text, limit=4000)
    normalized_preview = _normalize_material_text(preview_text, limit=500) or "你好，这是一段用于校准音色的试听文本。"
    normalized_description = _normalize_material_text(description, limit=500)
    if not normalized_provider_id:
        raise HTTPException(400, "provider_id is required")
    if not normalized_model_name:
        raise HTTPException(400, "model_name is required")
    if not normalized_name:
        raise HTTPException(400, "name is required")
    voice_service = get_project_voice_service()
    voice_id = voice_service.new_voice_id()
    clone_payload = {}
    sample_audio = {}
    if normalized_mode == "manual":
        if not normalized_voice_id:
            raise HTTPException(400, "voice_id is required for manual mode")
    else:
        if sample_file is None:
            raise HTTPException(400, "sample_file is required for clone mode")
        if not normalized_transcript:
            raise HTTPException(400, "transcript_text is required")
        original_filename = Path(str(sample_file.filename or "").strip()).name
        normalized_mime_type = _normalize_material_text(
            _infer_material_upload_mime_type(sample_file),
            limit=120,
        )
        _validate_studio_audio_upload_type(normalized_mime_type)
        safe_filename = _sanitize_material_filename(original_filename, f"{voice_id}.bin")
        relative_path = Path(normalized_project_id) / "studio-voice-samples" / voice_id / safe_filename
        absolute_path = _project_material_file_root() / relative_path
        try:
            file_size_bytes = await _write_material_upload_file(sample_file, absolute_path)
        finally:
            await sample_file.close()
        from services.llm_provider_service import get_llm_provider_service

        llm_service = get_llm_provider_service()
        try:
            clone_payload = await llm_service.create_audio_voice_clone(
                normalized_provider_id,
                normalized_model_name,
                voice_name=normalized_name,
                input_text=normalized_preview,
                transcript_text=normalized_transcript,
                sample_file_path=str(absolute_path),
                sample_filename=safe_filename,
                sample_mime_type=normalized_mime_type,
                owner_username=str(auth_payload.get("sub") or "").strip(),
                include_all=is_admin_like(auth_payload),
            )
        except Exception:
            absolute_path.unlink(missing_ok=True)
            raise
        normalized_voice_id = _normalize_material_text(clone_payload.get("voice"), limit=200)
        sample_audio = {
            "title": normalized_name,
            "content_url": _build_studio_voice_sample_file_url(project_id, voice_id),
            "mime_type": normalized_mime_type,
            "original_filename": _normalize_material_text(original_filename, limit=240),
            "storage_path": relative_path.as_posix(),
            "source_type": "upload",
            "file_size_bytes": file_size_bytes,
        }
    item = voice_service.create_project_voice(
        {
            "id": voice_id,
            "project_id": normalized_project_id,
            "provider_id": normalized_provider_id,
            "model_name": normalized_model_name,
            "voice_id": normalized_voice_id,
            "name": normalized_name,
            "description": normalized_description,
            "preview_text": normalized_preview,
            "transcript_text": normalized_transcript,
            "provider_voice_name": normalized_name,
            "provider_payload": clone_payload,
            "source_type": "manual_binding" if normalized_mode == "manual" else "custom_clone",
            "sample_audio": sample_audio,
            "created_by": _normalize_material_text(auth_payload.get("sub"), limit=120),
        }
    )
    return {"status": "created", "item": item}


@router.get("/{project_id}/studio/voices/{voice_id}/sample/file")
async def get_project_studio_voice_sample_file(
    project_id: str,
    voice_id: str,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_access(project_id, auth_payload)
    voice_service = get_project_voice_service()
    voice = voice_service.get_project_voice(project_id, voice_id)
    if voice is None:
        raise HTTPException(404, "Studio voice not found")
    sample_audio = voice.get("sample_audio") if isinstance(voice.get("sample_audio"), dict) else {}
    storage_path = _normalize_material_text(sample_audio.get("storage_path"), limit=500)
    absolute_path = _resolve_material_storage_path(storage_path)
    if absolute_path is None or not absolute_path.exists() or not absolute_path.is_file():
        raise HTTPException(404, "Studio voice sample not found")
    filename = _normalize_material_text(sample_audio.get("original_filename"), limit=240) or absolute_path.name
    mime_type = _normalize_material_text(sample_audio.get("mime_type"), limit=120)
    return FileResponse(
        absolute_path,
        media_type=mime_type or None,
        filename=filename,
        headers={"Content-Disposition": _build_inline_content_disposition(filename, filename)},
    )


@router.patch("/{project_id}/studio/voices/{voice_id}")
async def update_project_studio_voice(
    project_id: str,
    voice_id: str,
    req: ProjectStudioVoiceUpdateReq,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_manage_access(project_id, auth_payload)
    voice_service = get_project_voice_service()
    try:
        item = voice_service.update_project_voice(
            project_id,
            voice_id,
            req.model_dump(exclude_unset=True),
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"status": "updated", "item": item}


@router.delete("/{project_id}/studio/voices/{voice_id}")
async def delete_project_studio_voice(
    project_id: str,
    voice_id: str,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_manage_access(project_id, auth_payload)
    voice_service = get_project_voice_service()
    voice = voice_service.get_project_voice(project_id, voice_id)
    if voice is None:
        raise HTTPException(404, "Studio voice not found")
    provider_delete_error = ""
    source_type = _normalize_material_text(voice.get("source_type"), limit=40)
    provider_id = _normalize_material_text(voice.get("provider_id"), limit=120)
    provider_voice_id = _normalize_material_text(voice.get("voice_id"), limit=200)
    if source_type != "manual_binding" and provider_id and provider_voice_id:
        from services.llm_provider_service import get_llm_provider_service

        llm_service = get_llm_provider_service()
        try:
            await llm_service.delete_audio_voice(
                provider_id,
                provider_voice_id,
                owner_username=str(auth_payload.get("sub") or "").strip(),
                include_all=is_admin_like(auth_payload),
            )
        except Exception as exc:
            provider_delete_error = str(exc)
    removed = voice_service.delete_project_voice(project_id, voice_id)
    sample_audio = removed.get("sample_audio") if isinstance(removed.get("sample_audio"), dict) else {}
    sample_storage_path = _normalize_material_text(sample_audio.get("storage_path"), limit=500)
    sample_absolute_path = _resolve_material_storage_path(sample_storage_path)
    preview_audio = removed.get("preview_audio") if isinstance(removed.get("preview_audio"), dict) else {}
    preview_storage_path = _normalize_material_text(preview_audio.get("storage_path"), limit=500)
    _delete_material_storage_path(preview_storage_path)
    if sample_absolute_path is not None:
        parent = sample_absolute_path.parent
        if parent.exists() and parent.is_dir():
            shutil.rmtree(parent, ignore_errors=True)
    return {
        "status": "deleted",
        "voice_id": voice_id,
        "provider_delete_error": provider_delete_error,
    }


@router.post("/{project_id}/studio/voiceovers/generate")
async def generate_project_studio_voiceover(
    project_id: str,
    req: ProjectStudioVoiceGenerateReq,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_manage_access(project_id, auth_payload)
    normalized_provider_id = _normalize_material_text(req.provider_id, limit=120)
    normalized_model_name = _normalize_material_text(req.model_name, limit=160)
    normalized_voice = _normalize_material_text(req.voice, limit=200)
    normalized_text = _normalize_material_text(req.text, limit=4000)
    normalized_title = _normalize_material_text(req.title, limit=120) or "旁白"
    normalized_voice_record_id = _normalize_material_text(req.voice_record_id, limit=120)
    if not normalized_provider_id:
        raise HTTPException(400, "provider_id is required")
    if not normalized_model_name:
        raise HTTPException(400, "model_name is required")
    if not normalized_voice:
        raise HTTPException(400, "voice is required")
    if not normalized_text:
        raise HTTPException(400, "text is required")
    voice_service = get_project_voice_service()
    current_voice = None
    if normalized_voice_record_id:
        current_voice = voice_service.get_project_voice(project_id, normalized_voice_record_id)
        if current_voice is None:
            raise HTTPException(404, "project voice not found")
        existing_preview = (
            current_voice.get("preview_audio")
            if isinstance(current_voice.get("preview_audio"), dict)
            else {}
        )
        existing_preview_storage_path = _normalize_material_text(
            existing_preview.get("storage_path"),
            limit=500,
        )
        if existing_preview_storage_path:
            _delete_material_storage_path(existing_preview_storage_path)
    from services.llm_provider_service import get_llm_provider_service

    llm_service = get_llm_provider_service()
    payload = await llm_service.generate_audio_speech(
        normalized_provider_id,
        normalized_model_name,
        text=normalized_text,
        voice=normalized_voice,
        response_format=_normalize_material_text(req.response_format, limit=20) or "wav",
        speed=req.speed,
        owner_username=str(auth_payload.get("sub") or "").strip(),
        include_all=is_admin_like(auth_payload),
    )
    audio_id = project_studio_export_store.new_id().replace("studio-export-", "studio-audio-", 1)
    extension = "wav" if str(req.response_format or "wav").strip().lower() == "wav" else "pcm"
    safe_filename = _sanitize_material_filename(f"{audio_id}.{extension}", f"{audio_id}.{extension}")
    relative_path = Path(project_id) / "studio-audio" / audio_id / safe_filename
    absolute_path = _project_material_file_root() / relative_path
    absolute_path.parent.mkdir(parents=True, exist_ok=True)
    absolute_path.write_bytes(payload.get("audio_bytes") or b"")
    item = {
        "id": audio_id,
        "title": normalized_title,
        "content_url": _build_studio_audio_file_url(project_id, audio_id),
        "mime_type": _normalize_material_text(payload.get("content_type"), limit=120)
        or ("audio/wav" if extension == "wav" else "audio/pcm"),
        "original_filename": safe_filename,
        "storage_path": relative_path.as_posix(),
        "source_type": "tts_generation",
        "provider_id": normalized_provider_id,
        "model_name": normalized_model_name,
        "voice": normalized_voice,
        "text": normalized_text,
    }
    voice_item = None
    if current_voice is not None:
        voice_item = voice_service.update_project_voice(
            project_id,
            normalized_voice_record_id,
            {"preview_audio": item},
        )
    return {"status": "created", "item": item, "voice_item": voice_item}


@router.get("/{project_id}/studio/model-sources")
async def list_project_studio_model_sources(
    project_id: str,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_access(project_id, auth_payload)
    providers = [
        _serialize_studio_model_provider(item)
        for item in _list_studio_model_providers(auth_payload)
    ]
    default_provider = next((item for item in providers if bool(item.get("is_default"))), None) or (
        providers[0] if providers else None
    )
    return {
        "project_id": project_id,
        "providers": providers,
        "default_provider_id": _normalize_material_text((default_provider or {}).get("id"), limit=120),
        "default_model_name": _normalize_material_text((default_provider or {}).get("default_model"), limit=160),
    }


@router.post("/{project_id}/studio/character-references/generate")
async def generate_project_studio_character_references(
    project_id: str,
    req: ProjectStudioCharacterReferenceGenerateReq,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_manage_access(project_id, auth_payload)
    normalized_provider_id = _normalize_material_text(req.provider_id, limit=120)
    normalized_model_name = _normalize_material_text(req.model_name, limit=160)
    normalized_prompt = _normalize_material_text(req.prompt, limit=6000)
    normalized_character_id = _normalize_material_text(req.character_id, limit=120)
    normalized_character_name = _normalize_material_text(req.character_name, limit=120) or "角色"
    normalized_reference_image_urls = _normalize_material_url_list(
        req.reference_image_urls,
        item_limit=len(_PROJECT_STUDIO_CHARACTER_VIEWS),
    )
    normalized_image_size = _normalize_material_text(req.image_size, limit=40) or "1024x1024"
    normalized_image_style = _normalize_material_text(req.image_style, limit=80) or "auto"
    normalized_image_quality = _normalize_material_text(req.image_quality, limit=80) or "high"
    if not normalized_provider_id or not normalized_model_name:
        raise HTTPException(400, "provider_id and model_name are required")
    if not normalized_prompt:
        raise HTTPException(400, "prompt is required")
    if not normalized_reference_image_urls:
        raise HTTPException(400, "请先提供至少一张角色参考图")
    target_view = _normalize_studio_character_view(req.target_view)
    requested_views = list(_PROJECT_STUDIO_CHARACTER_VIEWS if req.generate_all_views else (target_view,))

    from services.llm_provider_service import get_llm_provider_service

    llm_service = get_llm_provider_service()
    items: list[dict[str, Any]] = []
    for view in requested_views:
        prompt = _build_studio_character_reference_prompt(
            prompt=normalized_prompt,
            character_name=normalized_character_name,
            view=view,
            image_style=normalized_image_style,
            image_quality=normalized_image_quality,
            has_reference_images=bool(normalized_reference_image_urls),
        )
        try:
            artifacts = _normalize_chat_media_artifacts(
                await llm_service.generate_media_artifacts(
                    normalized_provider_id,
                    normalized_model_name,
                    prompt,
                    owner_username=str(auth_payload.get("sub") or "").strip(),
                    include_all=is_admin_like(auth_payload),
                    image_size=normalized_image_size,
                    image_urls=normalized_reference_image_urls,
                )
            )
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(502, f"生成角色参考图失败: {exc}") from exc
        image_artifacts = [
            item for item in artifacts if _normalize_material_asset_type(item.get("asset_type") or "image") == "image"
        ]
        if not image_artifacts:
            raise HTTPException(502, f"{_studio_character_view_label(view)}视图未返回有效图片")
        primary_artifact = image_artifacts[0]
        asset = _save_studio_generated_image_asset(
            project_id=project_id,
            auth_payload=auth_payload,
            artifact=primary_artifact,
            title=f"{normalized_character_name}-{_studio_character_view_label(view)}参考图",
            summary=f"{normalized_character_name}{_studio_character_view_label(view)}统一角色形象参考",
            structured_content={
                "character_id": normalized_character_id,
                "character_name": normalized_character_name,
                "view": view,
                "view_label": _studio_character_view_label(view),
                "reference_image_count": len(normalized_reference_image_urls),
            },
            metadata={
                **_normalize_material_mapping(primary_artifact.get("metadata")),
                "source": "studio-character-reference-generate",
                "character_id": normalized_character_id,
                "character_name": normalized_character_name,
                "view": view,
                "view_label": _studio_character_view_label(view),
                "prompt": normalized_prompt,
                "image_size": normalized_image_size,
                "image_style": normalized_image_style,
                "image_quality": normalized_image_quality,
                "reference_image_urls": normalized_reference_image_urls,
            },
        )
        items.append(
            {
                "view": view,
                "view_label": _studio_character_view_label(view),
                "item": _serialize_project_material_asset(asset),
            }
        )
    return {
        "project_id": project_id,
        "character_id": normalized_character_id,
        "character_name": normalized_character_name,
        "items": items,
    }


@router.post("/{project_id}/studio/extractions")
async def run_project_studio_extraction(
    project_id: str,
    req: ProjectStudioExtractionRunReq,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_manage_access(project_id, auth_payload)
    provider, model_name = _resolve_studio_model_target(
        auth_payload,
        preferred_provider_id=req.provider_id,
        preferred_model_name=req.model_name,
    )
    from services.llm_provider_service import get_llm_provider_service

    llm_service = get_llm_provider_service()
    try:
        completion = await llm_service.chat_completion(
            provider_id=_normalize_material_text(provider.get("id"), limit=120),
            model_name=model_name,
            messages=_build_studio_extraction_prompt(req),
            temperature=0.3,
            max_tokens=1800,
            timeout=120,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"调用模型失败: {exc}") from exc
    parsed = _parse_studio_llm_json(completion.get("content"))
    provider_id = _normalize_material_text(provider.get("id"), limit=120)
    items = _normalize_studio_extraction_items(
        parsed,
        provider_id=provider_id,
        model_name=model_name,
    )
    return {
        "project_id": project_id,
        "provider_id": provider_id,
        "model_name": model_name,
        "items": items,
    }


@router.post("/{project_id}/studio/storyboards/generate")
async def generate_project_studio_storyboards(
    project_id: str,
    req: ProjectStudioStoryboardGenerateReq,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_manage_access(project_id, auth_payload)
    provider, model_name = _resolve_studio_model_target(
        auth_payload,
        preferred_provider_id=req.provider_id,
        preferred_model_name=req.model_name,
    )
    from services.llm_provider_service import get_llm_provider_service

    llm_service = get_llm_provider_service()
    try:
        completion = await llm_service.chat_completion(
            provider_id=_normalize_material_text(provider.get("id"), limit=120),
            model_name=model_name,
            messages=_build_studio_storyboard_prompt(req),
            temperature=0.35,
            max_tokens=2200,
            timeout=120,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"调用模型失败: {exc}") from exc
    parsed = _parse_studio_llm_json(completion.get("content"))
    provider_id = _normalize_material_text(provider.get("id"), limit=120)
    items = _normalize_studio_storyboards(
        parsed,
        chapter_id=_normalize_material_text(req.chapter_id, limit=120),
        provider_id=provider_id,
        model_name=model_name,
        preferred_duration_seconds=_parse_duration_label_seconds(req.duration, default=8),
    )
    return {
        "project_id": project_id,
        "provider_id": provider_id,
        "model_name": model_name,
        "items": items,
    }


@router.get("/{project_id}/materials/{asset_id}/file")
async def get_project_material_file(
    project_id: str,
    asset_id: str,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_access(project_id, auth_payload)
    asset = project_material_store.get(project_id, asset_id)
    if asset is None:
        raise HTTPException(404, f"Material asset {asset_id} not found")
    file_path = _resolve_material_file_path(asset)
    if file_path is None or not file_path.is_file():
        raise HTTPException(404, "Material file not found")
    return FileResponse(
        path=file_path,
        media_type=str(asset.mime_type or "").strip() or None,
        headers={
            "Content-Disposition": _build_inline_content_disposition(
                str(asset.original_filename or file_path.name),
                file_path.name,
            )
        },
    )


@router.get("/{project_id}/materials/{asset_id}/cover")
async def get_project_material_cover(
    project_id: str,
    asset_id: str,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_access(project_id, auth_payload)
    asset = project_material_store.get(project_id, asset_id)
    if asset is None:
        raise HTTPException(404, f"Material asset {asset_id} not found")
    file_path = _resolve_material_cover_path(asset)
    if file_path is None or not file_path.is_file():
        raise HTTPException(404, "Material cover not found")
    cover_mime_type = _normalize_material_text(
        (asset.metadata or {}).get("cover_mime_type"),
        limit=120,
    )
    cover_filename = _normalize_material_text(
        (asset.metadata or {}).get("cover_original_filename"),
        limit=240,
    )
    return FileResponse(
        path=file_path,
        media_type=cover_mime_type or None,
        headers={
            "Content-Disposition": _build_inline_content_disposition(
                str(cover_filename or file_path.name),
                file_path.name,
            )
        },
    )


@router.post("/{project_id}/materials/{asset_id}/cover")
async def replace_project_material_cover(
    project_id: str,
    asset_id: str,
    cover_file: UploadFile = File(...),
    cover_mime_type: str = Form(""),
    cover_source: str = Form(""),
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_manage_access(project_id, auth_payload)
    current = project_material_store.get(project_id, asset_id)
    if current is None:
        raise HTTPException(404, f"Material asset {asset_id} not found")
    if current.asset_type != "video":
        raise HTTPException(400, "只有视频素材支持替换封面")
    cover_original_filename = Path(str(cover_file.filename or "").strip()).name
    safe_cover_filename = _sanitize_material_filename(
        cover_original_filename,
        f"{asset_id}-cover.bin",
    )
    cover_relative_path = Path(project_id) / asset_id / f"cover-{safe_cover_filename}"
    cover_absolute_path = _project_material_file_root() / cover_relative_path
    old_cover_storage_path = str((current.metadata or {}).get("cover_storage_path") or "").strip()
    try:
        cover_mime_type_value = _normalize_material_text(
            _infer_material_upload_mime_type(cover_file, cover_mime_type),
            limit=120,
        )
        _validate_material_cover_upload_type(cover_mime_type_value)
        cover_file_size_bytes = await _write_material_upload_file(cover_file, cover_absolute_path)
    finally:
        await cover_file.close()
    metadata = {
        **_normalize_material_mapping(current.metadata),
        "cover_storage_path": cover_relative_path.as_posix(),
        "cover_original_filename": _normalize_material_text(cover_original_filename, limit=240),
        "cover_mime_type": cover_mime_type_value,
        "cover_file_size_bytes": cover_file_size_bytes,
        "cover_source": _normalize_material_text(cover_source, limit=120) or "manual_upload",
    }
    updated = replace(
        current,
        preview_url=_build_material_cover_url(project_id, asset_id),
        metadata=metadata,
        updated_at=_now_iso(),
    )
    project_material_store.save(updated)
    if old_cover_storage_path and old_cover_storage_path != cover_relative_path.as_posix():
        _delete_material_storage_path(old_cover_storage_path)
    return {"status": "updated", "item": _serialize_project_material_asset(updated)}


@router.patch("/{project_id}/materials/{asset_id}")
async def update_project_material(
    project_id: str,
    asset_id: str,
    req: ProjectMaterialAssetUpdateReq,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_manage_access(project_id, auth_payload)
    current = project_material_store.get(project_id, asset_id)
    if current is None:
        raise HTTPException(404, f"Material asset {asset_id} not found")
    updates = req.model_dump(exclude_none=True)
    if not updates:
        return {"status": "no_change", "item": _serialize_project_material_asset(current)}
    if "title" in updates:
        updates["title"] = _normalize_material_text(updates["title"], limit=120)
        if not updates["title"]:
            raise HTTPException(400, "title cannot be empty")
    if "summary" in updates:
        updates["summary"] = _normalize_material_text(updates["summary"], limit=1000)
    if "preview_url" in updates:
        updates["preview_url"] = _normalize_material_url(updates["preview_url"])
    if "content_url" in updates:
        updates["content_url"] = _normalize_material_url(updates["content_url"])
    if "mime_type" in updates:
        updates["mime_type"] = _normalize_material_text(updates["mime_type"], limit=120)
    if "status" in updates:
        updates["status"] = _normalize_material_status(updates["status"])
    if "structured_content" in updates:
        updates["structured_content"] = _normalize_material_mapping(updates["structured_content"])
    if "metadata" in updates:
        updates["metadata"] = _normalize_material_mapping(updates["metadata"])
    updates["updated_at"] = _now_iso()
    updated = replace(current, **updates)
    project_material_store.save(updated)
    return {"status": "updated", "item": _serialize_project_material_asset(updated)}


@router.delete("/{project_id}/materials/{asset_id}")
async def delete_project_material(
    project_id: str,
    asset_id: str,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_manage_access(project_id, auth_payload)
    asset = project_material_store.get(project_id, asset_id)
    if asset is None:
        raise HTTPException(404, f"Material asset {asset_id} not found")
    if not project_material_store.delete(project_id, asset_id):
        raise HTTPException(404, f"Material asset {asset_id} not found")
    _delete_material_file(asset)
    return {"status": "deleted", "asset_id": asset_id}


@router.get("/{project_id}/studio/exports")
async def list_project_studio_exports(
    project_id: str,
    status: str = Query(""),
    source_type: str = Query(""),
    limit: int = Query(20, ge=1, le=100),
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_access(project_id, auth_payload)
    normalized_status = ""
    if str(status or "").strip():
        normalized_status = _normalize_studio_export_status(status)
    normalized_source_type = _normalize_material_text(source_type, limit=40)
    if normalized_source_type and normalized_source_type not in {"studio_export", "studio_draft"}:
        raise HTTPException(400, "source_type 仅支持 studio_export 或 studio_draft")
    items = project_studio_export_store.list_by_project(
        project_id,
        status=normalized_status,
        source_type=normalized_source_type,
        limit=limit,
    )
    return {
        "items": [_serialize_project_studio_export_job(item) for item in items],
        "summary": {
            "total": len(items),
            "draft_count": sum(1 for item in items if item.status == "draft"),
            "queued_count": sum(1 for item in items if item.status == "queued"),
            "processing_count": sum(1 for item in items if item.status == "processing"),
            "succeeded_count": sum(1 for item in items if item.status == "succeeded"),
            "failed_count": sum(1 for item in items if item.status == "failed"),
            "canceled_count": sum(1 for item in items if item.status == "canceled"),
        },
    }


@router.post("/{project_id}/studio/exports")
async def create_project_studio_export(
    project_id: str,
    req: ProjectStudioExportCreateReq,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_manage_access(project_id, auth_payload)
    timeline_payload = _normalize_studio_timeline_payload(req.timeline_payload)
    clips = timeline_payload.get("clips") or []
    audio_payload = _normalize_studio_audio_payload(req.audio_payload, timeline_payload)
    export_format = _normalize_studio_export_format(req.export_format)
    export_resolution = _normalize_studio_export_resolution(req.export_resolution)
    aspect_ratio = _normalize_material_text(req.aspect_ratio, limit=20) or "16:9"
    clip_count = _extract_studio_export_clip_count(timeline_payload)
    timeline_duration_seconds = _extract_studio_export_timeline_duration_seconds(timeline_payload)
    title = _derive_studio_export_title(
        req.title,
        export_format,
        export_resolution,
        timeline_payload,
    )
    now = _now_iso()
    job = ProjectStudioExportJob(
        id=project_studio_export_store.new_id(),
        project_id=project_id,
        title=title,
        status="queued",
        progress=0,
        export_format=export_format,
        export_resolution=export_resolution,
        aspect_ratio=aspect_ratio,
        timeline_duration_seconds=timeline_duration_seconds,
        clip_count=clip_count,
        timeline_payload=timeline_payload,
        audio_payload=audio_payload,
        source_type="studio_export",
        attempt_count=0,
        error_details={},
        created_by=_normalize_material_text(auth_payload.get("sub"), limit=120),
        created_at=now,
        updated_at=now,
    )
    project_studio_export_store.save(job)
    return {"status": "created", "job": _serialize_project_studio_export_job(job)}


@router.post("/{project_id}/studio/drafts")
async def save_project_studio_draft(
    project_id: str,
    req: ProjectStudioDraftSaveReq,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_manage_access(project_id, auth_payload)
    snapshot = _normalize_studio_draft_snapshot(req.snapshot)
    clip_items = _extract_studio_draft_timeline_clips(snapshot)
    timeline_duration_seconds = _extract_studio_draft_timeline_duration_seconds(snapshot)
    export_config = snapshot.get("exportConfig") if isinstance(snapshot.get("exportConfig"), dict) else {}
    script_draft = snapshot.get("scriptDraft") if isinstance(snapshot.get("scriptDraft"), dict) else {}
    export_format = _normalize_studio_export_format(export_config.get("format"))
    export_resolution = _normalize_studio_export_resolution(export_config.get("resolution"))
    aspect_ratio = _normalize_material_text(script_draft.get("aspectRatio"), limit=20) or "16:9"
    requested_job_id = _normalize_material_text(req.job_id, limit=120)
    current = project_studio_export_store.get(project_id, requested_job_id) if requested_job_id else None
    if current is not None and current.source_type != "studio_draft":
        raise HTTPException(400, "只能覆盖制作草稿记录")
    now = _now_iso()
    job = ProjectStudioExportJob(
        id=current.id if current is not None else project_studio_export_store.new_id(),
        project_id=project_id,
        title=_derive_studio_draft_title(req.title, snapshot),
        status="draft",
        progress=0,
        export_format=export_format,
        export_resolution=export_resolution,
        aspect_ratio=aspect_ratio,
        timeline_duration_seconds=timeline_duration_seconds,
        clip_count=len(clip_items),
        timeline_payload={
            "clips": clip_items,
            "summary": {
                "timelineDurationSeconds": timeline_duration_seconds,
                "timeline_duration_seconds": timeline_duration_seconds,
                "clipCount": len(clip_items),
                "clip_count": len(clip_items),
                "activeStep": _normalize_material_text(snapshot.get("activeStep"), limit=40) or "script",
            },
            "draft_snapshot": snapshot,
        },
        audio_payload={
            "active_step": _normalize_material_text(snapshot.get("activeStep"), limit=40) or "script",
        },
        source_type="studio_draft",
        result_asset_id="",
        result_work_id=current.result_work_id if current is not None else "",
        cover_asset_id="",
        attempt_count=0,
        retry_of_job_id="",
        error_code="",
        error_message="",
        error_details={},
        created_by=_normalize_material_text(auth_payload.get("sub"), limit=120),
        created_at=current.created_at if current is not None else now,
        updated_at=now,
        started_at="",
        finished_at="",
    )
    project_studio_export_store.save(job)
    return {
        "status": "updated" if current is not None else "created",
        "job": _serialize_project_studio_export_job(job),
    }


@router.get("/{project_id}/studio/exports/{job_id}")
async def get_project_studio_export(
    project_id: str,
    job_id: str,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_access(project_id, auth_payload)
    job = project_studio_export_store.get(project_id, job_id)
    if job is None:
        raise HTTPException(404, f"Studio export job {job_id} not found")
    return {"job": _serialize_project_studio_export_job(job)}


@router.patch("/{project_id}/studio/exports/{job_id}")
async def update_project_studio_export(
    project_id: str,
    job_id: str,
    req: ProjectStudioExportUpdateReq,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_manage_access(project_id, auth_payload)
    current = project_studio_export_store.get(project_id, job_id)
    if current is None:
        raise HTTPException(404, f"Studio export job {job_id} not found")
    updates = req.model_dump(exclude_none=True)
    if not updates:
        return {"status": "no_change", "job": _serialize_project_studio_export_job(current)}
    if "status" in updates:
        updates["status"] = _normalize_studio_export_status(updates["status"])
    if "progress" in updates:
        updates["progress"] = _normalize_studio_export_progress(updates["progress"])
    for key in (
        "result_asset_id",
        "result_work_id",
        "cover_asset_id",
        "error_code",
        "started_at",
        "finished_at",
    ):
        if key in updates:
            updates[key] = _normalize_material_text(updates[key], limit=120)
    if "error_message" in updates:
        updates["error_message"] = _normalize_material_text(
            updates["error_message"],
            limit=1000,
        )
    if "error_details" in updates:
        updates["error_details"] = _normalize_material_mapping(updates["error_details"])
    if updates.get("status") == "processing" and "started_at" not in updates:
        updates["started_at"] = current.started_at or _now_iso()
    if updates.get("status") in {"succeeded", "failed", "canceled"} and "finished_at" not in updates:
        updates["finished_at"] = _now_iso()
    updates["updated_at"] = _now_iso()
    updated = replace(current, **updates)
    project_studio_export_store.save(updated)
    return {"status": "updated", "job": _serialize_project_studio_export_job(updated)}


@router.post("/{project_id}/studio/exports/{job_id}/cancel")
async def cancel_project_studio_export(
    project_id: str,
    job_id: str,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_manage_access(project_id, auth_payload)
    current = project_studio_export_store.get(project_id, job_id)
    if current is None:
        raise HTTPException(404, f"Studio export job {job_id} not found")
    if current.status == "canceled":
        return {"status": "no_change", "job": _serialize_project_studio_export_job(current)}
    if current.status not in {"queued", "processing"}:
        raise HTTPException(400, "只有排队中或处理中任务可以取消")
    updated = replace(
        current,
        status="canceled",
        updated_at=_now_iso(),
        finished_at=_now_iso(),
    )
    project_studio_export_store.save(updated)
    return {"status": "updated", "job": _serialize_project_studio_export_job(updated)}


@router.delete("/{project_id}/studio/exports/{job_id}")
async def delete_project_studio_export(
    project_id: str,
    job_id: str,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_manage_access(project_id, auth_payload)
    current = project_studio_export_store.get(project_id, job_id)
    if current is None:
        raise HTTPException(404, f"Studio export job {job_id} not found")
    if current.status in {"queued", "processing"}:
        raise HTTPException(400, "排队中或处理中任务不能直接删除，请先取消任务")
    if not project_studio_export_store.delete(project_id, job_id):
        raise HTTPException(404, f"Studio export job {job_id} not found")
    return {
        "status": "deleted",
        "job_id": job_id,
        "result_asset_id": current.result_asset_id,
    }


@router.post("/{project_id}/studio/exports/{job_id}/retry")
async def retry_project_studio_export(
    project_id: str,
    job_id: str,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_manage_access(project_id, auth_payload)
    current = project_studio_export_store.get(project_id, job_id)
    if current is None:
        raise HTTPException(404, f"Studio export job {job_id} not found")
    if current.status != "failed":
        raise HTTPException(400, "只有失败任务支持重试")
    now = _now_iso()
    retried = ProjectStudioExportJob(
        id=project_studio_export_store.new_id(),
        project_id=current.project_id,
        title=current.title,
        status="queued",
        progress=0,
        export_format=current.export_format,
        export_resolution=current.export_resolution,
        aspect_ratio=current.aspect_ratio,
        timeline_duration_seconds=current.timeline_duration_seconds,
        clip_count=current.clip_count,
        timeline_payload=dict(current.timeline_payload or {}),
        audio_payload=dict(current.audio_payload or {}),
        source_type=current.source_type,
        attempt_count=current.attempt_count + 1,
        retry_of_job_id=current.id,
        error_details={},
        created_by=_normalize_material_text(auth_payload.get("sub"), limit=120),
        created_at=now,
        updated_at=now,
    )
    project_studio_export_store.save(retried)
    return {"status": "created", "job": _serialize_project_studio_export_job(retried)}


@router.post("/{project_id}/smart-query")
async def smart_query_project(project_id: str, request: dict, auth_payload: dict = Depends(require_auth)):
    """AI 智能查询端点：自动决策调用数据库或工具"""
    from services.dynamic_mcp_runtime import list_project_proxy_tools_runtime
    from services.llm_provider_service import get_llm_provider_service
    from starlette.concurrency import run_in_threadpool
    import json

    _ensure_permission(auth_payload, "menu.ai.chat")
    project = _ensure_project_access(project_id, auth_payload)

    user_message = request.get("message", "")
    if not user_message:
        raise HTTPException(400, "message is required")

    llm_service = get_llm_provider_service()
    providers = llm_service.list_providers(
        enabled_only=True,
        owner_username=str(auth_payload.get("sub") or "").strip(),
        include_all=is_admin_like(auth_payload),
        include_shared=True,
    )
    if not providers:
        raise HTTPException(400, "No LLM provider configured")

    provider = providers[0]
    provider_id = provider.get("id", "")
    model_name = provider.get("default_model", "")

    from services.dynamic_mcp_runtime import invoke_project_tool_runtime, list_project_external_tools_runtime, list_project_proxy_tools_runtime

    tools = list_project_proxy_tools_runtime(project_id, "") + list_project_external_tools_runtime(project_id)
    decision = await ai_decide_action(llm_service, provider_id, model_name, user_message, project_id, tools)

    if not decision or decision.get("action") == "chat":
        return {"status": "no_action", "message": "请使用普通对话"}

    action = decision.get("action")

    if action == "query_db":
        result = await run_in_threadpool(execute_db_query, decision.get("query", ""))
        return {"status": "ok", "action": "query_db", "result": result, "reason": decision.get("reason")}

    if action == "call_tool":
        tool_result = await run_in_threadpool(
            invoke_project_tool_runtime, project_id, decision.get("tool", ""), "", decision.get("args", {}), "{}", 60
        )
        return {"status": "ok", "action": "call_tool", "result": tool_result, "reason": decision.get("reason")}

    if action == "recommend_project":
        recommendation = recommend_better_project(user_message, project_id)
        return {"status": "ok", "action": "recommend_project", "result": recommendation}

    return {"status": "unknown_action"}


def _normalize_workspace_path_for_save(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        raise HTTPException(400, "workspace_path 必须是绝对路径，例如 /Users/name/project")
    if not candidate.exists() or not candidate.is_dir():
        raise HTTPException(400, f"workspace_path 不存在或不是目录：{candidate}")
    return str(candidate.resolve())


def _normalize_ai_entry_file_for_save(value: Any) -> str:
    return str(value or "").strip()[:500]


def _normalize_project_mcp_instruction_for_save(value: Any) -> str:
    return str(value or "").strip()[:4000]


def _normalize_project_type(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in _PROJECT_TYPE_VALUES:
        return normalized
    return "mixed"


def _normalize_project_ui_rule_ids(values: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in values or []:
        rule_id = str(item or "").strip()
        if not rule_id or rule_id in seen:
            continue
        seen.add(rule_id)
        result.append(rule_id)
    return result


def _apply_project_update(project_id: str, req: ProjectUpdateReq, auth_payload: dict) -> dict:
    project = project_store.get(project_id)
    if project is None:
        raise HTTPException(404, f"Project {project_id} not found")
    updates = req.model_dump(exclude_none=True)
    if not updates:
        return {"status": "no_change", "project": _serialize_project(project, auth_payload)}
    if "name" in updates:
        updates["name"] = str(updates["name"] or "").strip()
        if not updates["name"]:
            raise HTTPException(400, "name cannot be empty")
    if "workspace_path" in updates:
        updates["workspace_path"] = _normalize_workspace_path_for_save(updates.get("workspace_path"))
    if "ai_entry_file" in updates:
        updates["ai_entry_file"] = _normalize_ai_entry_file_for_save(updates.get("ai_entry_file"))
    if "mcp_instruction" in updates:
        updates["mcp_instruction"] = _normalize_project_mcp_instruction_for_save(
            updates.get("mcp_instruction")
        )
    if "type" in updates:
        updates["type"] = _normalize_project_type(updates.get("type"))
    if "ui_rule_ids" in updates:
        updates["ui_rule_ids"] = _normalize_project_ui_rule_ids(updates.get("ui_rule_ids"))
    if "experience_rule_ids" in updates:
        updates["experience_rule_ids"] = _normalize_project_experience_rule_ids(
            updates.get("experience_rule_ids")
        )
    updates["updated_at"] = _now_iso()
    updated = replace(project, **updates)
    project_store.save(updated)
    if "feedback_upgrade_enabled" in updates:
        _sync_feedback_project_flag(updated.id, bool(updated.feedback_upgrade_enabled))
    return {"status": "updated", "project": _serialize_project(updated, auth_payload)}


@router.put("/{project_id}")
async def update_project(project_id: str, req: ProjectUpdateReq, auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_manage_access(project_id, auth_payload)
    return _apply_project_update(project_id, req, auth_payload)


@router.patch("/{project_id}")
async def patch_project(project_id: str, req: ProjectUpdateReq, auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_manage_access(project_id, auth_payload)
    return _apply_project_update(project_id, req, auth_payload)


@router.delete("/{project_id}")
async def delete_project(project_id: str, auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_manage_access(project_id, auth_payload)
    if not project_store.delete(project_id):
        raise HTTPException(404, f"Project {project_id} not found")
    try:
        project_chat_store.clear_project(project_id)
    except Exception:
        pass
    return {"status": "deleted", "project_id": project_id}


@router.get("/{project_id}/users")
async def list_project_users(project_id: str, auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_access(project_id, auth_payload)
    roles = {item.id: item for item in role_store.list_all()}
    project_user_members = project_store.list_user_members(project_id)
    can_manage = _can_manage_project(project_id, auth_payload)
    member_map = {
        str(item.username or "").strip(): item
        for item in project_user_members
        if str(item.username or "").strip()
    }
    all_users = []
    if can_manage:
        for user in user_store.list_all():
            member = member_map.get(user.username)
            all_users.append(
                {
                    "username": user.username,
                    "role": user.role,
                    "role_name": getattr(roles.get(user.role), "name", user.role),
                    "assigned": member is not None,
                    "enabled_in_project": bool(getattr(member, "enabled", False)),
                }
            )
    return {
        "members": [_serialize_project_user_member(item) for item in project_user_members],
        "all_users": all_users,
        "can_manage": can_manage,
    }


@router.post("/{project_id}/users")
async def add_project_user(project_id: str, req: ProjectUserAddReq, auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_manage_access(project_id, auth_payload)
    username = _normalize_project_username(req.username)
    user = user_store.get(username)
    if user is None:
        raise HTTPException(404, f"User {username} not found")
    existing = project_store.get_user_member(project_id, username)
    if existing is not None:
        return {
            "status": "exists",
            "message": f"User {username} already exists in project {project_id}",
            "member": _serialize_project_user_member(existing),
        }
    member = ProjectUserMember(
        project_id=project_id,
        username=username,
        role=str(req.role or "member").strip() or "member",
        enabled=bool(req.enabled),
        joined_at=_now_iso(),
    )
    project_store.upsert_user_member(member)
    return {"status": "created", "member": _serialize_project_user_member(member)}


@router.delete("/{project_id}/users/{username}")
async def remove_project_user(project_id: str, username: str, auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_manage_access(project_id, auth_payload)
    normalized_username = _normalize_project_username(username)
    creator_username = _project_creator_username(project_id)
    if creator_username and normalized_username == creator_username:
        raise HTTPException(400, "Cannot remove the project creator")
    member = project_store.get_user_member(project_id, normalized_username)
    if member is None:
        raise HTTPException(404, f"User {normalized_username} is not a member of project {project_id}")
    owner_count = sum(
        1
        for item in project_store.list_user_members(project_id)
        if bool(getattr(item, "enabled", True))
        and str(getattr(item, "role", "") or "").strip().lower() == "owner"
    )
    if str(getattr(member, "role", "") or "").strip().lower() == "owner" and owner_count <= 1:
        raise HTTPException(400, "Cannot remove the last project owner")
    if not project_store.remove_user_member(project_id, normalized_username):
        raise HTTPException(404, f"User {normalized_username} is not a member of project {project_id}")
    return {
        "status": "deleted",
        "project_id": project_id,
        "username": normalized_username,
    }


@router.get("/{project_id}/members")
async def list_project_members(project_id: str, auth_payload: dict = Depends(require_auth)):
    from services.dynamic_mcp_runtime import list_project_member_profiles_runtime

    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_access(project_id, auth_payload)

    profiles = list_project_member_profiles_runtime(
        project_id,
        include_disabled=True,
        include_missing=True,
        rule_limit=30,
    )
    by_employee_id = {
        str(item.get("employee_id") or ""): item
        for item in profiles
        if str(item.get("employee_id") or "")
    }
    members: list[dict[str, Any]] = []
    for member in project_store.list_members(project_id):
        profile = by_employee_id.get(member.employee_id, {})
        members.append(
            {
                **asdict(member),
                "employee_exists": bool(profile.get("employee_exists", False)),
                "employee_name": str(profile.get("employee_name") or ""),
                "employee_mcp_enabled": bool(profile.get("mcp_enabled", False)),
                "skills": list(profile.get("skills") or []),
                "skill_names": list(profile.get("skill_names") or []),
                "rule_bindings": list(profile.get("rule_bindings") or []),
            }
        )
    return {"members": members}


@router.post("/{project_id}/members")
async def add_project_member(project_id: str, req: ProjectMemberAddReq, auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_manage_access(project_id, auth_payload)

    employee_id = str(req.employee_id or "").strip()
    if not employee_id:
        raise HTTPException(400, "employee_id is required")
    employee = employee_store.get(employee_id)
    if employee is None:
        raise HTTPException(404, f"Employee {employee_id} not found")

    existing = project_store.get_member(project_id, employee_id)
    if existing is not None:
        return {
            "status": "exists",
            "message": f"Employee {employee_id} already exists in project {project_id}",
            "member": asdict(existing),
        }
    member = ProjectMember(
        project_id=project_id,
        employee_id=employee_id,
        role=str(req.role or "member").strip() or "member",
        enabled=bool(req.enabled),
        joined_at=_now_iso(),
    )
    project_store.upsert_member(member)
    return {"status": "created", "member": asdict(member)}


@router.delete("/{project_id}/members/{employee_id}")
async def remove_project_member(project_id: str, employee_id: str, auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_manage_access(project_id, auth_payload)
    if not project_store.remove_member(project_id, employee_id):
        raise HTTPException(404, f"Employee {employee_id} is not a member of project {project_id}")
    cleaned = _cleanup_project_chat_employee_selection(project_id, employee_id)
    return {
        "status": "deleted",
        "project_id": project_id,
        "employee_id": employee_id,
        "cleaned_chat_settings": cleaned,
    }


@router.get("/{project_id}/chat/providers")
async def list_project_chat_providers(
    project_id: str,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.ai.chat")
    from services.dynamic_mcp_runtime import list_project_external_tools_runtime

    project = _ensure_project_access(project_id, auth_payload)
    try:
        selected_provider, providers = _pick_chat_provider("", auth_payload)
    except HTTPException as exc:
        if exc.status_code != 400:
            raise
        selected_provider, providers = {}, []
    default_employee, candidates = _resolve_project_chat_employee(project_id, "")
    mcp_modules = _build_chat_mcp_modules(project_id)
    persisted_chat_settings = _normalize_project_chat_settings(getattr(project, "chat_settings", {}) or {})
    chat_settings = dict(persisted_chat_settings)
    runtime_external_tools = list_project_external_tools_runtime(project_id)
    effective_workspace_path = _resolve_project_workspace_for_chat(project, chat_settings)

    return {
        "project_id": project_id,
        "workspace_path": effective_workspace_path,
        "project_workspace_path": str(project.workspace_path or "").strip(),
        "project_ai_entry_file": str(project.ai_entry_file or "").strip(),
        "chat_modes": [{"id": "system", "label": "系统对话"}],
        "providers": providers,
        "default_provider_id": str(selected_provider.get("id") or ""),
        "default_model_name": str(selected_provider.get("default_model") or ""),
        "employees": candidates,
        "default_employee_id": str((default_employee or {}).get("id") or ""),
        "mcp_modules": mcp_modules,
        "runtime_external_tools": runtime_external_tools,
        "chat_settings": _public_project_chat_settings(persisted_chat_settings),
    }


def _serialize_chat_session(item: Any) -> dict[str, Any]:
    return {
        "id": str(getattr(item, "id", "") or "").strip(),
        "project_id": str(getattr(item, "project_id", "") or "").strip(),
        "username": str(getattr(item, "username", "") or "").strip(),
        "title": str(getattr(item, "title", "新对话") or "新对话"),
        "preview": str(getattr(item, "preview", "") or ""),
        "message_count": int(getattr(item, "message_count", 0) or 0),
        "created_at": str(getattr(item, "created_at", "") or ""),
        "updated_at": str(getattr(item, "updated_at", "") or ""),
        "last_message_at": str(getattr(item, "last_message_at", "") or ""),
    }


@router.get("/{project_id}/chat/settings")
async def get_project_chat_settings(project_id: str, auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "menu.ai.chat")
    project = _ensure_project_access(project_id, auth_payload)
    return {"project_id": project_id, "settings": _public_project_chat_settings(getattr(project, "chat_settings", {}) or {})}


@router.put("/{project_id}/chat/settings")
async def update_project_chat_settings(project_id: str, req: ProjectChatSettingsUpdateReq, auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "menu.ai.chat")
    project = _ensure_project_access(project_id, auth_payload)
    normalized = _public_project_chat_settings(req.settings or {})
    updated = replace(project, chat_settings=normalized, updated_at=_now_iso())
    project_store.save(updated)
    persisted = project_store.get(project_id)
    persisted_settings = _public_project_chat_settings(getattr(persisted, "chat_settings", {}) or {}) if persisted else normalized
    return {"status": "updated", "project_id": project_id, "settings": persisted_settings}


@router.get("/{project_id}/chat/task-tree")
async def get_project_chat_task_tree(
    project_id: str,
    session_id: str = "",
    chat_session_id: str = "",
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.ai.chat")
    _ensure_project_access(project_id, auth_payload)
    username = _current_username(auth_payload)
    normalized_session_id = str(session_id or "").strip()
    normalized_chat_session_id = str(chat_session_id or "").strip()
    if normalized_session_id:
        session = get_task_tree_by_session_id(
            project_id,
            username,
            normalized_session_id,
        )
    elif normalized_chat_session_id:
        session = get_task_tree_for_chat_session(
            project_id,
            username,
            normalized_chat_session_id,
        )
    else:
        session = get_latest_task_tree_for_user(project_id, username)
    payload = serialize_task_tree(
        session
    )
    return {"task_tree": payload}


@router.get("/{project_id}/chat/task-tree/evolution-summary")
async def get_project_chat_task_tree_evolution_summary(
    project_id: str,
    chat_session_id: str = "",
    task_tree_session_id: str = "",
    issue_code: str = "",
    source_kind: str = "",
    limit: int = 200,
    top: int = 5,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.ai.chat")
    _ensure_project_access(project_id, auth_payload)
    safe_limit = max(1, min(int(limit or 200), 500))
    safe_top = max(1, min(int(top or 5), 20))
    return build_task_tree_evolution_summary(
        project_id=project_id,
        chat_session_id=chat_session_id,
        task_tree_session_id=task_tree_session_id,
        issue_code=issue_code,
        source_kind=source_kind,
        limit=safe_limit,
        top_limit=safe_top,
    )


@router.delete("/{project_id}/chat/task-tree")
async def delete_project_chat_task_tree(
    project_id: str,
    chat_session_id: str = "",
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.ai.chat")
    _ensure_project_access(project_id, auth_payload)
    username = _current_username(auth_payload)
    normalized_chat_session_id = str(chat_session_id or "").strip()
    if not normalized_chat_session_id:
        raise HTTPException(400, "chat_session_id is required")
    removed = int(
        project_chat_task_store.delete(
            project_id,
            username,
            normalized_chat_session_id,
        )
        or 0
    )
    await _invalidate_project_requirement_records_cache(project_id)
    return {
        "status": "deleted",
        "project_id": project_id,
        "chat_session_id": normalized_chat_session_id,
        "removed_count": removed,
    }


@router.get("/{project_id}/chat/task-tree/sessions")
async def list_project_chat_task_tree_sessions(
    project_id: str,
    limit: int = 100,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.ai.chat")
    _ensure_project_access(project_id, auth_payload)
    settings = get_settings()
    safe_limit = max(1, min(int(limit or 100), 300))
    return {
        "items": list_project_task_tree_summaries(project_id, safe_limit),
        "storage_backend": str(settings.core_store_backend or "").strip() or "json",
        "project_id": project_id,
    }


@router.get("/{project_id}/requirement-records")
async def list_project_requirement_records(
    project_id: str,
    employee_id: str = Query("", max_length=80),
    query: str = Query("", max_length=200),
    memory_type: str = Query("", max_length=80),
    limit: int = Query(200, ge=1, le=500),
    auth_payload: dict = Depends(require_auth),
):
    project = _ensure_project_access(project_id, auth_payload)
    settings = get_settings()
    cache_key = _project_requirement_records_cache_key(
        project.id,
        employee_id=employee_id,
        query=query,
        memory_type=memory_type,
        limit=limit,
    )
    payload = await _load_project_requirement_records_cache(cache_key)
    if payload is None:
        payload = _build_project_requirement_records(
            project,
            employee_id=employee_id,
            query=query,
            memory_type=memory_type,
            limit=limit,
        )
        await _save_project_requirement_records_cache(project.id, cache_key, payload)
    return {
        "items": payload.get("items", []),
        "task_sessions": payload.get("task_sessions", []),
        "storage_backend": str(settings.core_store_backend or "").strip() or "json",
        "project_id": project.id,
        "project_name": project.name,
    }


@router.get("/{project_id}/memories")
async def list_project_memories(
    project_id: str,
    employee_id: str = Query("", max_length=80),
    query: str = Query("", max_length=200),
    limit: int = Query(50, ge=1, le=200),
    auth_payload: dict = Depends(require_auth),
):
    project = _ensure_project_access(project_id, auth_payload)
    safe_limit = max(1, min(int(limit or 50), 200))
    memories, _trajectory_memories = _collect_project_related_memories(
        project,
        employee_id=employee_id,
        query=query,
    )
    total = len(memories)
    return {
        "items": [_serialize_project_memory_record(item) for item in memories[:safe_limit]],
        "project_id": project.id,
        "project_name": project.name,
        "total": total,
        "limit": safe_limit,
        "has_more": total > safe_limit,
    }


@router.post("/{project_id}/requirement-records/batch-delete")
async def batch_delete_project_requirement_records(
    project_id: str,
    req: ProjectRequirementRecordBatchDeleteReq,
    auth_payload: dict = Depends(require_auth),
):
    project = _ensure_project_manage_access(project_id, auth_payload)
    requested_ids = [
        _normalize_project_record_token(item, limit=80)
        for item in (req.record_ids or [])
    ]
    requested_ids = [item for item in requested_ids if item]
    normalized_ids: list[str] = []
    seen_ids: set[str] = set()
    for item in requested_ids:
        if item in seen_ids:
            continue
        seen_ids.add(item)
        normalized_ids.append(item)
    if not normalized_ids:
        raise HTTPException(400, "record_ids is required")

    chain_index = _build_project_requirement_record_delete_index(project)
    deleted_record_ids: list[str] = []
    missing_ids: list[str] = []
    skipped_ids: list[str] = []
    deleted_task_tree_count = 0
    deleted_memory_count = 0
    deleted_work_session_count = 0
    deleted_work_event_count = 0

    for record_id in normalized_ids:
        entry = chain_index.get(record_id)
        if entry is None:
            missing_ids.append(record_id)
            continue

        task_tree_removed = 0
        for session in entry["task_sessions"]:
            username = _normalize_project_record_token(getattr(session, "username", ""), limit=80)
            chat_session_id = _normalize_project_record_token(
                getattr(session, "chat_session_id", ""),
                limit=80,
            )
            if not username or not chat_session_id:
                continue
            task_tree_removed += int(
                project_chat_task_store.delete_exact(project.id, username, chat_session_id) or 0
            )

        work_session_removed = 0
        work_event_removed = 0
        for work_session_id in sorted(entry["work_session_ids"]):
            removed = int(work_session_store.delete_by_session(work_session_id, project_id=project.id) or 0)
            if removed <= 0:
                continue
            work_session_removed += 1
            work_event_removed += removed

        memory_removed = 0
        for memory_id in sorted(entry["memory_ids"]):
            if memory_store.delete(memory_id):
                memory_removed += 1

        deleted_task_tree_count += task_tree_removed
        deleted_work_session_count += work_session_removed
        deleted_work_event_count += work_event_removed
        deleted_memory_count += memory_removed

        if task_tree_removed or work_session_removed or memory_removed:
            deleted_record_ids.append(record_id)
        else:
            skipped_ids.append(record_id)

    await _invalidate_project_requirement_records_cache(project.id)
    return {
        "status": "deleted",
        "project_id": project.id,
        "project_name": project.name,
        "requested_count": len(normalized_ids),
        "deleted_count": len(deleted_record_ids),
        "deleted_record_ids": deleted_record_ids,
        "deleted_task_tree_count": deleted_task_tree_count,
        "deleted_memory_count": deleted_memory_count,
        "deleted_work_session_count": deleted_work_session_count,
        "deleted_work_event_count": deleted_work_event_count,
        "missing_ids": missing_ids,
        "skipped_ids": skipped_ids,
    }


def _normalize_experience_topic_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", text).strip("-")
    return text[:80]


def _normalize_experience_list(
    values: Any,
    *,
    item_limit: int = 160,
    max_items: int = 8,
) -> list[str]:
    items = values if isinstance(values, list) else [values]
    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item or "").strip()
        if not text:
            continue
        text = text[:item_limit]
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(text)
        if len(normalized) >= max_items:
            break
    return normalized


def _extract_json_object_from_text(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        raise ValueError("summary result is empty")
    try:
        payload = json.loads(raw)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("summary result does not contain valid JSON")
    payload = json.loads(raw[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("summary result JSON must be an object")
    return payload


def _build_project_experience_source_lines(records: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for index, record in enumerate(records, start=1):
        root_goal = _normalize_project_record_token(record.get("rootGoal"), limit=240)
        summary_text = _normalize_project_record_token(record.get("summaryText"), limit=320)
        current_focus = _normalize_project_record_token(record.get("currentFocus"), limit=200)
        actor_label = _normalize_project_record_token(record.get("actorLabel"), limit=120)
        round_digest = _normalize_project_record_token(record.get("roundDigest"), limit=80)
        record_kind = _normalize_project_record_token(
            record.get("detailRound", {}).get("recordKind") if isinstance(record.get("detailRound"), dict) else "",
            limit=60,
        )
        parts = [
            f"记录{index}",
            f"目标={root_goal or '未命名需求'}",
            f"摘要={summary_text or '-'}",
            f"当前焦点={current_focus or '-'}",
            f"执行人={actor_label or '-'}",
            f"轮次={round_digest or '-'}",
        ]
        if record_kind:
            parts.append(f"类型={record_kind}")
        lines.append("；".join(parts))
    return lines


def _build_project_experience_summary_messages(
    project: ProjectConfig,
    records: list[dict[str, Any]],
    *,
    max_cards: int,
) -> list[dict[str, str]]:
    source_lines = _build_project_experience_source_lines(records)
    source_block = "\n".join(f"- {line}" for line in source_lines[:60])
    system_prompt = (
        "你是资深软件团队的经验萃取助手。"
        "你的任务是把需求记录总结成可复用、可按需加载的经验卡片，而不是项目复盘长文。"
        "输出必须是 JSON 对象，不要输出 Markdown 代码块。"
    )
    user_prompt = (
        f"项目名称：{project.name}\n"
        f"最多输出 {max_cards} 张经验卡片。\n"
        "要求：\n"
        "1. 经验必须通用，不要包含项目名、人员名、具体一次性背景。\n"
        "2. 每张卡片只保留一个稳定主题，避免把多个问题混成一条。\n"
        "3. 若问题只出现一次且不可复用，可以忽略，不必强行产出。\n"
        "4. topic_key 要稳定、短、可用于后续合并，例如 login-form、permission-routing。\n"
        "5. domain 只允许 frontend/backend/product/testing/workflow/general。\n"
        "6. keywords、applicable_when、signals、root_causes、recommended_actions、anti_patterns、verification 都输出数组。\n"
        "7. 输出 JSON 结构：\n"
        "{\n"
        '  "cards": [\n'
        "    {\n"
        '      "title": "经验标题",\n'
        '      "topic_key": "stable-topic-key",\n'
        '      "domain": "frontend",\n'
        '      "keywords": ["关键词"],\n'
        '      "applicable_when": ["适用场景"],\n'
        '      "signals": ["问题信号"],\n'
        '      "root_causes": ["根因模式"],\n'
        '      "recommended_actions": ["推荐做法"],\n'
        '      "anti_patterns": ["禁止做法"],\n'
        '      "verification": ["验证方式"]\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "需求记录如下：\n"
        f"{source_block}"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _normalize_experience_cards(payload: dict[str, Any], *, max_cards: int) -> list[dict[str, Any]]:
    raw_cards = payload.get("cards") if isinstance(payload, dict) else []
    if not isinstance(raw_cards, list):
        raw_cards = []
    cards: list[dict[str, Any]] = []
    seen_topics: set[str] = set()
    for item in raw_cards:
        if not isinstance(item, dict):
            continue
        title = _normalize_project_record_token(item.get("title"), limit=120)
        topic_key = _normalize_experience_topic_key(item.get("topic_key") or title)
        if not title or not topic_key or topic_key in seen_topics:
            continue
        seen_topics.add(topic_key)
        domain = _normalize_domain(str(item.get("domain") or "").strip()) or "general"
        if domain not in {"frontend", "backend", "product", "testing", "workflow", "general"}:
            domain = "general"
        cards.append(
            {
                "title": title,
                "topic_key": topic_key,
                "domain": domain,
                "keywords": _normalize_experience_list(item.get("keywords"), item_limit=60),
                "applicable_when": _normalize_experience_list(item.get("applicable_when")),
                "signals": _normalize_experience_list(item.get("signals")),
                "root_causes": _normalize_experience_list(item.get("root_causes")),
                "recommended_actions": _normalize_experience_list(item.get("recommended_actions")),
                "anti_patterns": _normalize_experience_list(item.get("anti_patterns")),
                "verification": _normalize_experience_list(item.get("verification")),
            }
        )
        if len(cards) >= max_cards:
            break
    return cards


def _parse_experience_rule_content(content: str) -> dict[str, Any]:
    parsed: dict[str, Any] = {
        "topic_key": "",
        "keywords": [],
        "applicable_when": [],
        "signals": [],
        "root_causes": [],
        "recommended_actions": [],
        "anti_patterns": [],
        "verification": [],
    }
    section_map = {
        "适用场景": "applicable_when",
        "问题信号": "signals",
        "根因模式": "root_causes",
        "推荐做法": "recommended_actions",
        "禁止做法": "anti_patterns",
        "验证方式": "verification",
    }
    current_section = ""
    for raw_line in str(content or "").splitlines():
        line = str(raw_line or "").strip()
        if not line:
            continue
        if line.startswith("- 主题键:"):
            parsed["topic_key"] = line.split(":", 1)[1].strip()
            current_section = ""
            continue
        if line.startswith("- 关键词:"):
            parsed["keywords"] = _normalize_experience_list(
                re.split(r"[、,，/|]", line.split(":", 1)[1].strip()),
                item_limit=60,
            )
            current_section = ""
            continue
        if line.startswith("## "):
            current_section = line[3:].strip()
            continue
        if current_section and line.startswith("- "):
            key = section_map.get(current_section)
            if key:
                parsed[key] = _normalize_experience_list(
                    [*parsed.get(key, []), line[2:].strip()],
                )
    return parsed


def _infer_experience_rule_scope(rule: Rule | None) -> str:
    if rule is None:
        return _EXPERIENCE_SCOPE_DEVELOPMENT
    domain = str(getattr(rule, "domain", "") or "").strip()
    title = str(getattr(rule, "title", "") or "").strip()
    if domain == _PROJECT_EXPERIENCE_RULE_DOMAIN or title.startswith(_PROJECT_EXPERIENCE_RULE_TITLE_PREFIX):
        return _EXPERIENCE_SCOPE_PROJECT
    return _EXPERIENCE_SCOPE_DEVELOPMENT


def _render_experience_rule_content(card: dict[str, Any]) -> str:
    sections = [
        ("适用场景", card.get("applicable_when") or []),
        ("问题信号", card.get("signals") or []),
        ("根因模式", card.get("root_causes") or []),
        ("推荐做法", card.get("recommended_actions") or []),
        ("禁止做法", card.get("anti_patterns") or []),
        ("验证方式", card.get("verification") or []),
    ]
    lines = [
        f"# {str(card.get('domain') or _DEVELOPMENT_EXPERIENCE_RULE_DOMAIN).strip()}卡片",
        f"- 主题键: {card['topic_key']}",
        f"- 适用领域: {card['domain']}",
        f"- 关键词: {', '.join(card.get('keywords') or [])}",
        "",
    ]
    for title, items in sections:
        normalized_items = _normalize_experience_list(items)
        if not normalized_items:
            continue
        lines.append(f"## {title}")
        lines.extend(f"- {item}" for item in normalized_items)
        lines.append("")
    return "\n".join(lines).strip()


def _merge_experience_rule_card(existing_rule: Rule, card: dict[str, Any]) -> Rule:
    parsed = _parse_experience_rule_content(str(getattr(existing_rule, "content", "") or ""))
    experience_scope = _normalize_experience_rule_scope(
        card.get("experience_scope") or _infer_experience_rule_scope(existing_rule)
    )
    merged_card = {
        "title": card["title"],
        "topic_key": card["topic_key"],
        "domain": card["domain"],
        "keywords": _normalize_experience_list([*(parsed.get("keywords") or []), *(card.get("keywords") or [])], item_limit=60),
        "applicable_when": _normalize_experience_list([*(parsed.get("applicable_when") or []), *(card.get("applicable_when") or [])]),
        "signals": _normalize_experience_list([*(parsed.get("signals") or []), *(card.get("signals") or [])]),
        "root_causes": _normalize_experience_list([*(parsed.get("root_causes") or []), *(card.get("root_causes") or [])]),
        "recommended_actions": _normalize_experience_list([*(parsed.get("recommended_actions") or []), *(card.get("recommended_actions") or [])]),
        "anti_patterns": _normalize_experience_list([*(parsed.get("anti_patterns") or []), *(card.get("anti_patterns") or [])]),
        "verification": _normalize_experience_list([*(parsed.get("verification") or []), *(card.get("verification") or [])]),
    }
    return replace(
        existing_rule,
        title=_normalize_experience_rule_title(str(card["title"] or ""), experience_scope),
        domain=_experience_rule_domain_for_scope(experience_scope),
        content=_render_experience_rule_content(merged_card),
        updated_at=rules_now_iso(),
    )


def _extract_experience_rule_topic_key(rule: Rule | None) -> str:
    if rule is None:
        return ""
    return _normalize_experience_topic_key(
        _parse_experience_rule_content(str(getattr(rule, "content", "") or "")).get("topic_key")
    )


def _build_experience_card_from_rule(rule: Rule, *, experience_scope: str) -> dict[str, Any]:
    normalized_scope = _normalize_experience_rule_scope(experience_scope)
    parsed = _parse_experience_rule_content(str(getattr(rule, "content", "") or ""))
    raw_title = _strip_experience_rule_title_prefix(str(getattr(rule, "title", "") or ""))
    topic_key = _extract_experience_rule_topic_key(rule) or _normalize_experience_topic_key(raw_title)
    return {
        "title": raw_title or (
            "项目经验"
            if normalized_scope == _EXPERIENCE_SCOPE_PROJECT
            else "开发经验"
        ),
        "topic_key": topic_key or _normalize_experience_topic_key(str(getattr(rule, "id", "") or "")),
        "domain": _experience_rule_domain_for_scope(normalized_scope),
        "experience_scope": normalized_scope,
        "keywords": _normalize_experience_list(parsed.get("keywords") or [], item_limit=60),
        "applicable_when": _normalize_experience_list(parsed.get("applicable_when") or []),
        "signals": _normalize_experience_list(parsed.get("signals") or []),
        "root_causes": _normalize_experience_list(parsed.get("root_causes") or []),
        "recommended_actions": _normalize_experience_list(parsed.get("recommended_actions") or []),
        "anti_patterns": _normalize_experience_list(parsed.get("anti_patterns") or []),
        "verification": _normalize_experience_list(parsed.get("verification") or []),
    }


def _projects_binding_experience_rule(
    rule_id: str,
    *,
    exclude_project_id: str = "",
) -> list[str]:
    normalized_rule_id = _normalize_project_record_token(rule_id, limit=80)
    excluded_project_id = _normalize_project_record_token(exclude_project_id, limit=80)
    if not normalized_rule_id:
        return []
    project_ids: list[str] = []
    for project in project_store.list_all():
        project_id = _normalize_project_record_token(getattr(project, "id", ""), limit=80)
        if not project_id or project_id == excluded_project_id:
            continue
        project_rule_ids = _normalize_project_experience_rule_ids(
            getattr(project, "experience_rule_ids", []) or []
        )
        if normalized_rule_id in project_rule_ids:
            project_ids.append(project_id)
    return project_ids


def _build_global_experience_rule_topic_index(
    *,
    experience_scope: str,
) -> dict[str, Rule]:
    topic_index: dict[str, Rule] = {}
    normalized_scope = _normalize_experience_rule_scope(experience_scope)
    for project in project_store.list_all():
        for rule_id in _normalize_project_experience_rule_ids(
            getattr(project, "experience_rule_ids", []) or []
        ):
            rule = rule_store.get(rule_id)
            if _infer_experience_rule_scope(rule) != normalized_scope:
                continue
            topic_key = _extract_experience_rule_topic_key(rule)
            if not topic_key or topic_key in topic_index or rule is None:
                continue
            topic_index[topic_key] = rule
    return topic_index


def _experience_rule_group_key(rule: Rule) -> str:
    topic_key = _extract_experience_rule_topic_key(rule)
    if topic_key:
        return topic_key
    fallback_title = _strip_experience_rule_title_prefix(str(getattr(rule, "title", "") or ""))
    return _normalize_experience_topic_key(fallback_title) or _normalize_experience_topic_key(
        str(getattr(rule, "id", "") or "")
    )


async def _consolidate_project_experience_rules(
    project: ProjectConfig,
    *,
    auth_payload: dict,
    provider_id: str = "",
    model_name: str = "",
) -> tuple[ProjectConfig, list[str], list[str], list[str]]:
    existing_rule_ids = _normalize_project_experience_rule_ids(
        getattr(project, "experience_rule_ids", []) or []
    )
    existing_rules = [
        rule
        for rule_id in existing_rule_ids
        if (rule := rule_store.get(rule_id)) is not None
    ]
    if not existing_rules:
        raise HTTPException(400, "当前项目没有可汇总的经验规则")
    grouped_rules: dict[str, list[Rule]] = {}
    ordered_group_keys: list[str] = []
    for rule in existing_rules:
        group_key = _experience_rule_group_key(rule)
        if group_key not in grouped_rules:
            grouped_rules[group_key] = []
            ordered_group_keys.append(group_key)
        grouped_rules[group_key].append(rule)

    final_rule_ids: list[str] = []
    consolidated_rule_ids: list[str] = []
    unchanged_rule_ids: list[str] = []
    deleted_rule_ids: list[str] = []

    for group_key in ordered_group_keys:
        rules_in_group = grouped_rules.get(group_key) or []
        if not rules_in_group:
            continue
        if len(rules_in_group) == 1:
            unchanged_rule_ids.append(rules_in_group[0].id)
            final_rule_ids.append(rules_in_group[0].id)
            continue

        base_rule = rules_in_group[0]
        merged_scope = _infer_experience_rule_scope(base_rule)
        merged_cards = await _merge_experience_cards_with_llm(
            project,
            [
                _build_experience_card_from_rule(rule, experience_scope=merged_scope)
                for rule in rules_in_group
            ],
            auth_payload=auth_payload,
            provider_id=provider_id,
            model_name=model_name,
            max_cards=1,
        )
        merged_card = {
            **merged_cards[0],
            "topic_key": group_key,
            "domain": _experience_rule_domain_for_scope(merged_scope),
            "experience_scope": merged_scope,
        }
        if _projects_binding_experience_rule(base_rule.id, exclude_project_id=project.id):
            base_rule = Rule(
                id=rule_store.new_id(),
                domain=str(getattr(base_rule, "domain", "") or "") or _experience_rule_domain_for_scope(merged_scope),
                title=str(getattr(base_rule, "title", "") or ""),
                content=str(getattr(base_rule, "content", "") or ""),
                severity=Severity.RECOMMENDED,
                risk_domain=RiskDomain.LOW,
                created_by=str(getattr(base_rule, "created_by", "") or "").strip()
                or _current_username(auth_payload),
            )
        merged_rule = replace(
            base_rule,
            title=_normalize_experience_rule_title(str(merged_card["title"] or ""), merged_scope),
            domain=_experience_rule_domain_for_scope(merged_scope),
            content=_render_experience_rule_content(merged_card),
            updated_at=rules_now_iso(),
            created_by=str(getattr(base_rule, "created_by", "") or "").strip()
            or _current_username(auth_payload),
        )
        rule_store.save(merged_rule)
        consolidated_rule_ids.append(merged_rule.id)
        final_rule_ids.append(merged_rule.id)

        for redundant_rule in rules_in_group:
            redundant_id = str(getattr(redundant_rule, "id", "") or "").strip()
            if not redundant_id or redundant_id == merged_rule.id:
                continue
            if _projects_binding_experience_rule(redundant_id, exclude_project_id=project.id):
                continue
            if rule_store.delete(redundant_id):
                deleted_rule_ids.append(redundant_id)

    updated_project = replace(
        project,
        experience_rule_ids=_normalize_project_experience_rule_ids(final_rule_ids),
        updated_at=_now_iso(),
    )
    project_store.save(updated_project)
    return updated_project, consolidated_rule_ids, unchanged_rule_ids, deleted_rule_ids


def _score_experience_rule(rule: Rule, task_text: str) -> tuple[int, list[str]]:
    query = str(task_text or "").strip().lower()
    if not query:
        return 0, []
    haystack = " ".join(
        [
            str(getattr(rule, "title", "") or "").lower(),
            str(getattr(rule, "content", "") or "").lower(),
        ]
    )
    terms = [
        term
        for term in re.split(r"[\s,，。；;、:/|()（）]+", query)
        if len(term) >= 2
    ]
    chinese_chunks = re.findall(r"[\u4e00-\u9fff]{2,}", query)
    for chunk in chinese_chunks:
        if len(chunk) <= 3:
            terms.append(chunk)
            continue
        for size in (2, 3):
            for index in range(0, len(chunk) - size + 1):
                terms.append(chunk[index : index + size])
    terms = list(
        dict.fromkeys(
            term
            for term in terms
            if len(term) >= 2 and term not in _EXPERIENCE_QUERY_STOPWORDS
        )
    )
    if not terms:
        terms = [query]
    matched: list[str] = []
    score = 0
    for term in terms:
        if term and term in haystack:
            matched.append(term)
            score += 3
    title = str(getattr(rule, "title", "") or "").lower()
    for term in terms:
        if term and term in title:
            score += 2
    return score, matched[:5]


async def _summarize_project_experience_cards(
    project: ProjectConfig,
    *,
    provider_id: str,
    model_name: str,
    records: list[dict[str, Any]],
    max_cards: int,
    auth_payload: dict,
) -> list[dict[str, Any]]:
    from services.llm_provider_service import get_llm_provider_service

    llm_service = get_llm_provider_service()
    provider = llm_service.get_provider_raw(
        provider_id,
        owner_username=_current_username(auth_payload),
        include_all=is_admin_like(auth_payload),
        include_shared=True,
    )
    if provider is None:
        raise HTTPException(404, f"LLM provider {provider_id} not found")
    if not bool(provider.get("enabled", True)):
        raise HTTPException(400, f"LLM provider {provider_id} is disabled")
    chosen_model = str(model_name or provider.get("default_model") or "").strip()
    if not chosen_model:
        chosen_model = str((provider.get("models") or [""])[0] or "").strip()
    if not chosen_model:
        raise HTTPException(400, "model_name is required")
    result = await llm_service.chat_completion(
        provider_id,
        chosen_model,
        _build_project_experience_summary_messages(project, records, max_cards=max_cards),
        temperature=0.1,
        max_tokens=2200,
        timeout=90,
    )
    try:
        payload = _extract_json_object_from_text(result.get("content") or "")
    except ValueError as exc:
        raise HTTPException(502, f"经验总结结果解析失败: {exc}") from exc
    cards = _normalize_experience_cards(payload, max_cards=max_cards)
    if not cards:
        raise HTTPException(502, "经验总结结果为空，未生成可保存的经验卡片")
    return cards


def _resolve_project_experience_llm_target(
    project: ProjectConfig,
    *,
    auth_payload: dict,
    provider_id: str = "",
    model_name: str = "",
) -> tuple[str, str]:
    from services.llm_provider_service import get_llm_provider_service

    llm_service = get_llm_provider_service()
    resolved_provider_id = str(provider_id or "").strip()
    resolved_model_name = str(model_name or "").strip()
    if not resolved_provider_id:
        chat_settings = getattr(project, "chat_settings", {}) or {}
        resolved_provider_id = str(chat_settings.get("provider_id") or "").strip()
        resolved_model_name = resolved_model_name or str(chat_settings.get("model_name") or "").strip()
    if not resolved_provider_id:
        raise HTTPException(400, "当前未配置可用于经验规则融合的大模型")
    provider = llm_service.get_provider_raw(
        resolved_provider_id,
        owner_username=_current_username(auth_payload),
        include_all=is_admin_like(auth_payload),
        include_shared=True,
    )
    if provider is None:
        raise HTTPException(404, f"LLM provider {resolved_provider_id} not found")
    if not bool(provider.get("enabled", True)):
        raise HTTPException(400, f"LLM provider {resolved_provider_id} is disabled")
    if not resolved_model_name:
        resolved_model_name = str(provider.get("default_model") or "").strip()
    if not resolved_model_name:
        resolved_model_name = str((provider.get("models") or [""])[0] or "").strip()
    if not resolved_model_name:
        raise HTTPException(400, "当前未配置可用于经验规则融合的模型")
    return resolved_provider_id, resolved_model_name


def _build_project_experience_merge_messages(
    project: ProjectConfig,
    cards: list[dict[str, Any]],
    *,
    max_cards: int,
) -> list[dict[str, str]]:
    normalized_cards: list[dict[str, Any]] = []
    for item in cards:
        if not isinstance(item, dict):
            continue
        normalized_cards.append(
            {
                "title": _normalize_project_record_token(item.get("title"), limit=120),
                "topic_key": _normalize_experience_topic_key(item.get("topic_key")),
                "domain": _normalize_domain(str(item.get("domain") or "").strip()) or "general",
                "keywords": _normalize_experience_list(item.get("keywords"), item_limit=60),
                "applicable_when": _normalize_experience_list(item.get("applicable_when")),
                "signals": _normalize_experience_list(item.get("signals")),
                "root_causes": _normalize_experience_list(item.get("root_causes")),
                "recommended_actions": _normalize_experience_list(item.get("recommended_actions")),
                "anti_patterns": _normalize_experience_list(item.get("anti_patterns")),
                "verification": _normalize_experience_list(item.get("verification")),
            }
        )
    source_block = json.dumps({"cards": normalized_cards}, ensure_ascii=False, indent=2)
    system_prompt = (
        "你是资深软件团队的经验规则融合助手。"
        "你的任务是把同主题的经验卡片融合成一致、无冲突、可执行的经验卡片。"
        "输出必须是 JSON 对象，不要输出 Markdown 代码块。"
    )
    user_prompt = (
        f"项目名称：{project.name}\n"
        f"最多输出 {max_cards} 张经验卡片。\n"
        "要求：\n"
        "1. 只融合同主题经验，不要把不同主题硬合成一张卡。\n"
        "2. 必须保留正确、明确、可执行的推荐做法，不要把关键动作弱化成反义或模糊描述。\n"
        "3. 若输入内容存在冲突，优先保留更具体、约束更强、可验证的表达。\n"
        "4. topic_key 要稳定，title 要简洁，domain 只允许 frontend/backend/product/testing/workflow/general。\n"
        "5. keywords、applicable_when、signals、root_causes、recommended_actions、anti_patterns、verification 都输出数组。\n"
        "6. 输出 JSON 结构：\n"
        "{\n"
        '  "cards": [\n'
        "    {\n"
        '      "title": "经验标题",\n'
        '      "topic_key": "stable-topic-key",\n'
        '      "domain": "frontend",\n'
        '      "keywords": ["关键词"],\n'
        '      "applicable_when": ["适用场景"],\n'
        '      "signals": ["问题信号"],\n'
        '      "root_causes": ["根因模式"],\n'
        '      "recommended_actions": ["推荐做法"],\n'
        '      "anti_patterns": ["禁止做法"],\n'
        '      "verification": ["验证方式"]\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "待融合经验卡片如下：\n"
        f"{source_block}"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


async def _merge_experience_cards_with_llm(
    project: ProjectConfig,
    cards: list[dict[str, Any]],
    *,
    auth_payload: dict,
    provider_id: str = "",
    model_name: str = "",
    max_cards: int = 1,
) -> list[dict[str, Any]]:
    from services.llm_provider_service import get_llm_provider_service

    if len(cards) <= 1:
        return cards[:1]
    resolved_provider_id, resolved_model_name = _resolve_project_experience_llm_target(
        project,
        auth_payload=auth_payload,
        provider_id=provider_id,
        model_name=model_name,
    )
    llm_service = get_llm_provider_service()
    result = await llm_service.chat_completion(
        resolved_provider_id,
        resolved_model_name,
        _build_project_experience_merge_messages(project, cards, max_cards=max_cards),
        temperature=0.1,
        max_tokens=2200,
        timeout=90,
    )
    try:
        payload = _extract_json_object_from_text(result.get("content") or "")
    except ValueError as exc:
        raise HTTPException(502, f"经验规则融合结果解析失败: {exc}") from exc
    merged_cards = _normalize_experience_cards(payload, max_cards=max_cards)
    if not merged_cards:
        raise HTTPException(502, "经验规则融合结果为空")
    return merged_cards


async def _upsert_project_experience_rules(
    project: ProjectConfig,
    cards: list[dict[str, Any]],
    *,
    auth_payload: dict,
    experience_scope: str,
    provider_id: str = "",
    model_name: str = "",
) -> tuple[ProjectConfig, list[str], list[str]]:
    normalized_scope = _normalize_experience_rule_scope(experience_scope)
    existing_rule_ids = _normalize_project_experience_rule_ids(
        getattr(project, "experience_rule_ids", []) or []
    )
    existing_rules = {
        rule_id: rule_store.get(rule_id)
        for rule_id in existing_rule_ids
    }
    existing_by_topic = {}
    valid_rule_ids: list[str] = []
    global_rules_by_topic = (
        _build_global_experience_rule_topic_index(experience_scope=normalized_scope)
        if normalized_scope == _EXPERIENCE_SCOPE_DEVELOPMENT
        else {}
    )
    for rule_id, rule in existing_rules.items():
        if rule is None:
            continue
        valid_rule_ids.append(rule_id)
        topic_key = _extract_experience_rule_topic_key(rule)
        if topic_key:
            existing_by_topic[topic_key] = rule

    created_rule_ids: list[str] = []
    updated_rule_ids: list[str] = []
    for card in cards:
        topic_key = _normalize_experience_topic_key(card.get("topic_key"))
        card = {
            **card,
            "domain": _experience_rule_domain_for_scope(normalized_scope),
            "experience_scope": normalized_scope,
        }
        existing_rule = existing_by_topic.get(topic_key) or global_rules_by_topic.get(topic_key)
        if existing_rule is not None:
            merged_cards = await _merge_experience_cards_with_llm(
                project,
                [
                    _build_experience_card_from_rule(
                        existing_rule,
                        experience_scope=normalized_scope,
                    ),
                    card,
                ],
                auth_payload=auth_payload,
                provider_id=provider_id,
                model_name=model_name,
                max_cards=1,
            )
            merged_card = {
                **merged_cards[0],
                "domain": _experience_rule_domain_for_scope(normalized_scope),
                "experience_scope": normalized_scope,
            }
            merged_rule = replace(
                existing_rule,
                title=_normalize_experience_rule_title(str(merged_card["title"] or ""), normalized_scope),
                domain=_experience_rule_domain_for_scope(normalized_scope),
                content=_render_experience_rule_content(merged_card),
                updated_at=rules_now_iso(),
            )
            rule_store.save(merged_rule)
            updated_rule_ids.append(merged_rule.id)
            valid_rule_ids.append(merged_rule.id)
            existing_by_topic[topic_key] = merged_rule
            global_rules_by_topic[topic_key] = merged_rule
            continue
        new_rule = Rule(
            id=rule_store.new_id(),
            domain=_experience_rule_domain_for_scope(normalized_scope),
            title=_normalize_experience_rule_title(str(card["title"] or ""), normalized_scope),
            content=_render_experience_rule_content(card),
            severity=Severity.RECOMMENDED,
            risk_domain=RiskDomain.LOW,
            created_by=_current_username(auth_payload),
        )
        rule_store.save(new_rule)
        created_rule_ids.append(new_rule.id)
        valid_rule_ids.append(new_rule.id)
        existing_by_topic[topic_key] = new_rule

    updated_project = replace(
        project,
        experience_rule_ids=_normalize_project_experience_rule_ids(
            [*valid_rule_ids, *created_rule_ids]
        ),
        updated_at=_now_iso(),
    )
    project_store.save(updated_project)
    return updated_project, created_rule_ids, updated_rule_ids


def _migrate_project_experience_rules_to_development(
    project: ProjectConfig,
    *,
    auth_payload: dict,
) -> tuple[ProjectConfig, list[str], list[str], list[str]]:
    existing_rule_ids = _normalize_project_experience_rule_ids(
        getattr(project, "experience_rule_ids", []) or []
    )
    existing_rules = [
        rule
        for rule_id in existing_rule_ids
        if (rule := rule_store.get(rule_id)) is not None
    ]
    legacy_rules = [
        rule for rule in existing_rules
        if _infer_experience_rule_scope(rule) == _EXPERIENCE_SCOPE_PROJECT
    ]
    if not legacy_rules:
        raise HTTPException(400, "当前项目没有可迁移的项目经验规则")

    development_by_topic = _build_global_experience_rule_topic_index(
        experience_scope=_EXPERIENCE_SCOPE_DEVELOPMENT,
    )
    migrated_rule_ids: list[str] = []
    created_rule_ids: list[str] = []
    updated_rule_ids: list[str] = []
    final_rule_ids: list[str] = []

    for rule_id in existing_rule_ids:
        rule = rule_store.get(rule_id)
        if rule is None:
            continue
        if _infer_experience_rule_scope(rule) != _EXPERIENCE_SCOPE_PROJECT:
            final_rule_ids.append(rule_id)
            continue

        card = _build_experience_card_from_rule(
            rule,
            experience_scope=_EXPERIENCE_SCOPE_DEVELOPMENT,
        )
        topic_key = _normalize_experience_topic_key(card.get("topic_key"))
        target_rule = development_by_topic.get(topic_key)
        if target_rule is not None:
            merged_rule = _merge_experience_rule_card(target_rule, card)
            rule_store.save(merged_rule)
            updated_rule_ids.append(merged_rule.id)
            migrated_rule_ids.append(rule.id)
            development_by_topic[topic_key] = merged_rule
            final_rule_ids.append(merged_rule.id)
            continue

        new_rule = Rule(
            id=rule_store.new_id(),
            domain=_DEVELOPMENT_EXPERIENCE_RULE_DOMAIN,
            title=_normalize_experience_rule_title(str(card["title"] or ""), _EXPERIENCE_SCOPE_DEVELOPMENT),
            content=_render_experience_rule_content(card),
            severity=Severity.RECOMMENDED,
            risk_domain=RiskDomain.LOW,
            created_by=_current_username(auth_payload),
        )
        rule_store.save(new_rule)
        created_rule_ids.append(new_rule.id)
        migrated_rule_ids.append(rule.id)
        development_by_topic[topic_key] = new_rule
        final_rule_ids.append(new_rule.id)

    updated_project = replace(
        project,
        experience_rule_ids=_normalize_project_experience_rule_ids(final_rule_ids),
        updated_at=_now_iso(),
    )
    project_store.save(updated_project)

    deleted_rule_ids: list[str] = []
    for rule in legacy_rules:
        rule_id = str(getattr(rule, "id", "") or "").strip()
        if not rule_id:
            continue
        if _projects_binding_experience_rule(rule_id):
            continue
        if rule_store.delete(rule_id):
            deleted_rule_ids.append(rule_id)

    return updated_project, created_rule_ids, updated_rule_ids, deleted_rule_ids


@router.post("/{project_id}/experience-summary-jobs")
async def summarize_project_experience(
    project_id: str,
    req: ProjectExperienceSummaryReq,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.projects")
    project = _ensure_project_manage_access(project_id, auth_payload)
    experience_scope = _normalize_experience_rule_scope(req.experience_scope)
    payload = _build_project_requirement_records(
        project,
        limit=_PROJECT_EXPERIENCE_SUMMARY_RECORD_LIMIT,
    )
    all_records = payload.get("items") if isinstance(payload, dict) else []
    if not isinstance(all_records, list):
        all_records = []
    requested_ids = [
        _normalize_project_record_token(item, limit=80)
        for item in (req.record_ids or [])
    ]
    requested_ids = [item for item in requested_ids if item]
    target_records = all_records
    if requested_ids:
        selected_id_set = set(requested_ids)
        target_records = [
            item for item in all_records
            if _normalize_project_record_token(item.get("id"), limit=80) in selected_id_set
        ]
    if not target_records:
        raise HTTPException(400, "没有可用于总结的需求记录")

    cards = await _summarize_project_experience_cards(
        project,
        provider_id=str(req.provider_id or "").strip(),
        model_name=str(req.model_name or "").strip(),
        records=target_records,
        max_cards=int(req.max_cards or 5),
        auth_payload=auth_payload,
    )
    updated_project, created_rule_ids, updated_rule_ids = await _upsert_project_experience_rules(
        project,
        cards,
        auth_payload=auth_payload,
        experience_scope=experience_scope,
        provider_id=str(req.provider_id or "").strip(),
        model_name=str(req.model_name or "").strip(),
    )

    clear_result: dict[str, Any] | None = None
    if req.clear_requirement_records:
        clear_result = await batch_delete_project_requirement_records(
            project_id,
            ProjectRequirementRecordBatchDeleteReq(
                record_ids=[
                    _normalize_project_record_token(item.get("id"), limit=80)
                    for item in target_records
                ]
            ),
            auth_payload,
        )

    return {
        "status": "completed",
        "project_id": updated_project.id,
        "project_name": updated_project.name,
        "source_record_ids": [
            _normalize_project_record_token(item.get("id"), limit=80)
            for item in target_records
        ],
        "source_record_count": len(target_records),
        "created_rule_ids": created_rule_ids,
        "updated_rule_ids": updated_rule_ids,
        "experience_rule_ids": _normalize_project_experience_rule_ids(
            getattr(updated_project, "experience_rule_ids", []) or []
        ),
        "experience_rule_bindings": _resolve_project_experience_rule_bindings(updated_project),
        "clear_result": clear_result,
        "provider_id": str(req.provider_id or "").strip(),
        "model_name": str(req.model_name or "").strip(),
        "experience_scope": experience_scope,
    }


@router.post("/{project_id}/experience-rules/migrate-to-development")
async def migrate_project_experience_rules_to_development(
    project_id: str,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.projects")
    project = _ensure_project_manage_access(project_id, auth_payload)
    updated_project, created_rule_ids, updated_rule_ids, deleted_rule_ids = (
        _migrate_project_experience_rules_to_development(
            project,
            auth_payload=auth_payload,
        )
    )
    return {
        "status": "completed",
        "project_id": updated_project.id,
        "project_name": updated_project.name,
        "created_rule_ids": created_rule_ids,
        "updated_rule_ids": updated_rule_ids,
        "deleted_rule_ids": deleted_rule_ids,
        "experience_rule_ids": _normalize_project_experience_rule_ids(
            getattr(updated_project, "experience_rule_ids", []) or []
        ),
        "experience_rule_bindings": _resolve_project_experience_rule_bindings(updated_project),
        "experience_scope": _EXPERIENCE_SCOPE_DEVELOPMENT,
    }


@router.post("/{project_id}/experience-rules/consolidate")
async def consolidate_project_experience_rules(
    project_id: str,
    req: ProjectExperienceRuleConsolidateReq | None = None,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.projects")
    project = _ensure_project_manage_access(project_id, auth_payload)
    updated_project, consolidated_rule_ids, unchanged_rule_ids, deleted_rule_ids = await _consolidate_project_experience_rules(
        project,
        auth_payload=auth_payload,
        provider_id=str(req.provider_id or "").strip() if req else "",
        model_name=str(req.model_name or "").strip() if req else "",
    )
    return {
        "status": "completed",
        "project_id": updated_project.id,
        "project_name": updated_project.name,
        "merged_rule_id": consolidated_rule_ids[0] if len(consolidated_rule_ids) == 1 else "",
        "consolidated_rule_ids": consolidated_rule_ids,
        "unchanged_rule_ids": unchanged_rule_ids,
        "remaining_rule_count": len(
            _normalize_project_experience_rule_ids(
                getattr(updated_project, "experience_rule_ids", []) or []
            )
        ),
        "deleted_rule_ids": deleted_rule_ids,
        "experience_rule_ids": _normalize_project_experience_rule_ids(
            getattr(updated_project, "experience_rule_ids", []) or []
        ),
        "experience_rule_bindings": _resolve_project_experience_rule_bindings(updated_project),
    }


@router.put("/{project_id}/experience-rules/{rule_id}")
async def update_project_experience_rule(
    project_id: str,
    rule_id: str,
    req: ProjectExperienceRuleUpdateReq,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.projects")
    project = _ensure_project_manage_access(project_id, auth_payload)
    normalized_rule_id = _normalize_project_record_token(rule_id, limit=80)
    existing_rule_ids = _normalize_project_experience_rule_ids(
        getattr(project, "experience_rule_ids", []) or []
    )
    if normalized_rule_id not in existing_rule_ids:
        raise HTTPException(404, "项目经验规则不存在")
    rule = rule_store.get(normalized_rule_id)
    if rule is None:
        raise HTTPException(404, "经验规则不存在")
    experience_scope = _infer_experience_rule_scope(rule)
    title = str(req.title or "").strip()
    content = str(req.content or "").strip()
    if not title:
        raise HTTPException(400, "title is required")
    if not content:
        raise HTTPException(400, "content is required")
    updated_rule = replace(
        rule,
        title=_normalize_experience_rule_title(title, experience_scope),
        domain=_experience_rule_domain_for_scope(experience_scope),
        content=content,
        updated_at=rules_now_iso(),
    )
    rule_store.save(updated_rule)
    return {
        "status": "updated",
        "project_id": project.id,
        "project_name": project.name,
        "rule": {
            "id": str(getattr(updated_rule, "id", "") or ""),
            "title": str(getattr(updated_rule, "title", "") or ""),
            "domain": str(getattr(updated_rule, "domain", "") or "") or _experience_rule_domain_for_scope(experience_scope),
            "preview": _extract_experience_rule_preview(content),
            "content": content,
        },
        "experience_rule_bindings": _resolve_project_experience_rule_bindings(project, include_content=True),
    }


@router.delete("/{project_id}/experience-rules/{rule_id}")
async def delete_project_experience_rule(
    project_id: str,
    rule_id: str,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.projects")
    project = _ensure_project_manage_access(project_id, auth_payload)
    normalized_rule_id = _normalize_project_record_token(rule_id, limit=80)
    existing_rule_ids = _normalize_project_experience_rule_ids(
        getattr(project, "experience_rule_ids", []) or []
    )
    if normalized_rule_id not in existing_rule_ids:
        raise HTTPException(404, "项目经验规则不存在")

    remaining_rule_ids = [item for item in existing_rule_ids if item != normalized_rule_id]
    updated_project = replace(
        project,
        experience_rule_ids=remaining_rule_ids,
        updated_at=_now_iso(),
    )
    project_store.save(updated_project)

    deleted_rule_ids: list[str] = []
    if not _projects_binding_experience_rule(normalized_rule_id):
        if rule_store.delete(normalized_rule_id):
            deleted_rule_ids.append(normalized_rule_id)

    remaining_project_ids = _projects_binding_experience_rule(normalized_rule_id)
    return {
        "status": "deleted",
        "project_id": updated_project.id,
        "project_name": updated_project.name,
        "removed_rule_id": normalized_rule_id,
        "deleted_rule_ids": deleted_rule_ids,
        "rule_deleted": bool(deleted_rule_ids),
        "remaining_project_binding_count": len(remaining_project_ids),
        "remaining_project_binding_ids": remaining_project_ids,
        "experience_rule_ids": _normalize_project_experience_rule_ids(
            getattr(updated_project, "experience_rule_ids", []) or []
        ),
        "experience_rule_bindings": _resolve_project_experience_rule_bindings(updated_project),
    }


def _resolve_project_experience_rules_payload(
    project: ProjectConfig,
    task_text: str,
    *,
    limit: int = 3,
) -> dict[str, Any]:
    task_text_value = str(task_text or "").strip()
    try:
        limit_value = max(1, min(int(limit or 3), 10))
    except (TypeError, ValueError):
        limit_value = 3
    experience_rule_ids = _normalize_project_experience_rule_ids(
        getattr(project, "experience_rule_ids", []) or []
    )
    items: list[dict[str, Any]] = []
    for rule_id in experience_rule_ids:
        rule = rule_store.get(rule_id)
        if rule is None:
            continue
        score, matched_terms = _score_experience_rule(rule, task_text_value)
        if score <= 0:
            continue
        items.append(
            {
                "id": str(getattr(rule, "id", "") or ""),
                "title": str(getattr(rule, "title", "") or ""),
                "domain": str(getattr(rule, "domain", "") or ""),
                "preview": _extract_experience_rule_preview(str(getattr(rule, "content", "") or "")),
                "content": str(getattr(rule, "content", "") or ""),
                "score": score,
                "matched_terms": matched_terms,
            }
        )
    items.sort(
        key=lambda item: (
            int(item.get("score") or 0),
            str(item.get("title") or ""),
        ),
        reverse=True,
    )
    limited_items = items[:limit_value]
    prompt_blocks = [
        "\n".join(
            [
                f"[Relevant Experience Card] {item['title']}",
                f"Preview: {item['preview'] or '-'}",
                item["content"],
            ]
        ).strip()
        for item in limited_items
    ]
    return {
        "project_id": project.id,
        "project_name": project.name,
        "task_text": task_text_value,
        "experience_rule_count": len(experience_rule_ids),
        "items": limited_items,
        "prompt_blocks": prompt_blocks,
        "assembled_context": "\n\n".join(prompt_blocks).strip(),
    }


@router.post("/{project_id}/experience-rules/resolve")
async def resolve_project_experience_rules(
    project_id: str,
    req: ProjectExperienceRuleResolveReq,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.projects")
    project = _ensure_project_access(project_id, auth_payload)
    return _resolve_project_experience_rules_payload(
        project,
        req.task_text,
        limit=req.limit,
    )


@router.get("/{project_id}/work-sessions")
async def list_project_work_sessions(
    project_id: str,
    employee_id: str = Query("", max_length=80),
    task_tree_session_id: str = Query("", max_length=80),
    task_tree_chat_session_id: str = Query("", max_length=80),
    task_node_id: str = Query("", max_length=80),
    query: str = Query("", max_length=200),
    limit: int = Query(50, ge=1, le=200),
    auth_payload: dict = Depends(require_auth),
):
    project = _ensure_project_access(project_id, auth_payload)
    safe_limit = max(1, min(int(limit or 50), 200))
    employee_names = _project_employee_name_map(project.id)
    events = work_session_store.list_events(
        project_id=project.id,
        employee_id=str(employee_id or "").strip(),
        task_tree_session_id=str(task_tree_session_id or "").strip(),
        task_tree_chat_session_id=str(task_tree_chat_session_id or "").strip(),
        task_node_id=str(task_node_id or "").strip(),
        query=str(query or "").strip(),
        limit=max(safe_limit * 8, safe_limit),
    )
    grouped: dict[str, list[Any]] = {}
    for item in events:
        session_id = str(getattr(item, "session_id", "") or "").strip()
        if not session_id:
            continue
        grouped.setdefault(session_id, []).append(item)
    sessions = [
        _serialize_project_work_session_summary(_summarize_project_work_session(items), employee_names)
        for items in grouped.values()
        if items
    ]
    sessions.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return {
        "items": sessions[:safe_limit],
        "project_id": project.id,
        "project_name": project.name,
}


@router.get("/{project_id}/work-session-events")
async def list_project_work_session_events(
    project_id: str,
    employee_id: str = Query("", max_length=80),
    session_id: str = Query("", max_length=120),
    task_tree_session_id: str = Query("", max_length=80),
    task_tree_chat_session_id: str = Query("", max_length=80),
    task_node_id: str = Query("", max_length=80),
    query: str = Query("", max_length=200),
    limit: int = Query(200, ge=1, le=500),
    auth_payload: dict = Depends(require_auth),
):
    project = _ensure_project_access(project_id, auth_payload)
    safe_limit = max(1, min(int(limit or 200), 500))
    employee_names = _project_employee_name_map(project.id)
    events = work_session_store.list_events(
        project_id=project.id,
        employee_id=str(employee_id or "").strip(),
        session_id=str(session_id or "").strip(),
        task_tree_session_id=str(task_tree_session_id or "").strip(),
        task_tree_chat_session_id=str(task_tree_chat_session_id or "").strip(),
        task_node_id=str(task_node_id or "").strip(),
        query=str(query or "").strip(),
        limit=safe_limit,
    )
    ordered = sorted(
        events,
        key=lambda item: (str(getattr(item, "created_at", "") or ""), str(getattr(item, "id", "") or "")),
        reverse=True,
    )
    return {
        "items": [_serialize_project_work_session_event(item, employee_names) for item in ordered],
        "project_id": project.id,
        "project_name": project.name,
    }


@router.get("/{project_id}/work-sessions/{session_id}")
async def get_project_work_session_detail(
    project_id: str,
    session_id: str,
    employee_id: str = Query("", max_length=80),
    task_tree_session_id: str = Query("", max_length=80),
    task_tree_chat_session_id: str = Query("", max_length=80),
    task_node_id: str = Query("", max_length=80),
    limit: int = Query(200, ge=1, le=500),
    auth_payload: dict = Depends(require_auth),
):
    project = _ensure_project_access(project_id, auth_payload)
    normalized_session_id = str(session_id or "").strip()
    if not normalized_session_id:
        raise HTTPException(400, "session_id is required")
    safe_limit = max(1, min(int(limit or 200), 500))
    employee_names = _project_employee_name_map(project.id)
    events = work_session_store.list_events(
        project_id=project.id,
        employee_id=str(employee_id or "").strip(),
        session_id=normalized_session_id,
        task_tree_session_id=str(task_tree_session_id or "").strip(),
        task_tree_chat_session_id=str(task_tree_chat_session_id or "").strip(),
        task_node_id=str(task_node_id or "").strip(),
        limit=safe_limit,
    )
    if not events:
        raise HTTPException(404, "Work session not found")
    ordered = sorted(
        events,
        key=lambda item: (str(getattr(item, "created_at", "") or ""), str(getattr(item, "id", "") or "")),
        reverse=True,
    )
    return {
        "session": _serialize_project_work_session_summary(
            _summarize_project_work_session(ordered),
            employee_names,
        ),
        "items": [_serialize_project_work_session_event(item, employee_names) for item in ordered],
        "project_id": project.id,
    }


@router.post("/{project_id}/chat/task-tree/generate")
async def generate_project_chat_task_tree(
    project_id: str,
    req: ProjectChatTaskTreeGenerateReq,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.ai.chat")
    _ensure_project_access(project_id, auth_payload)
    username = _current_username(auth_payload)
    chat_session_id = str(req.chat_session_id or "").strip()
    if not chat_session_id:
        raise HTTPException(400, "chat_session_id is required")
    message = str(req.message or "").strip()
    if not message:
        raise HTTPException(400, "message is required")
    try:
        max_steps = max(1, min(int(req.max_steps or 6), 10))
    except (TypeError, ValueError):
        max_steps = 6
    session = ensure_task_tree(
        project_id=project_id,
        username=username,
        chat_session_id=chat_session_id,
        root_goal=message,
        force=bool(req.force),
        max_steps=max_steps,
    )
    await _invalidate_project_requirement_records_cache(project_id)
    return {
        "status": "generated",
        "task_tree": serialize_task_tree(session),
    }


@router.patch("/{project_id}/chat/task-tree/nodes/{node_id}")
async def patch_project_chat_task_tree_node(
    project_id: str,
    node_id: str,
    req: ProjectChatTaskNodeUpdateReq,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.ai.chat")
    _ensure_project_access(project_id, auth_payload)
    username = _current_username(auth_payload)
    chat_session_id = str(req.chat_session_id or "").strip()
    if not chat_session_id:
        raise HTTPException(400, "chat_session_id is required")
    try:
        session = update_task_node(
            project_id=project_id,
            username=username,
            chat_session_id=chat_session_id,
            node_id=node_id,
            status=req.status,
            verification_result=req.verification_result,
            summary_for_model=req.summary_for_model,
            is_current=req.is_current,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    task_tree_payload = serialize_task_tree(session)
    history_task_tree = None
    if str(getattr(session, "status", "") or "").strip().lower() == "done":
        archived_session = archive_task_tree(
            session,
            reason="completed_task_closed",
            delete_current=True,
        )
        history_task_tree = serialize_task_tree(archived_session)
        task_tree_payload = None
    await _invalidate_project_requirement_records_cache(project_id)
    return {
        "status": "updated",
        "task_tree": task_tree_payload,
        "history_task_tree": history_task_tree,
    }


@router.patch("/{project_id}/chat/ai-entry-file")
async def update_project_chat_ai_entry_file(
    project_id: str,
    req: ProjectAiEntryFileUpdateReq,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.ai.chat")
    project = _ensure_project_access(project_id, auth_payload)
    normalized = _normalize_ai_entry_file_for_save(req.ai_entry_file)
    updated = replace(project, ai_entry_file=normalized, updated_at=_now_iso())
    project_store.save(updated)
    return {
        "status": "updated",
        "project_id": project_id,
        "ai_entry_file": normalized,
    }


@router.get("/{project_id}/chat/history")
async def list_project_chat_history(
    project_id: str,
    limit: int = 200,
    offset: int = 0,
    chat_session_id: str = "",
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.ai.chat")
    _ensure_project_access(project_id, auth_payload)
    username = _current_username(auth_payload)
    records = project_chat_store.list_messages(
        project_id,
        username,
        limit=limit,
        offset=offset,
        chat_session_id=str(chat_session_id or "").strip(),
    )
    return {"messages": [asdict(item) for item in records]}


@router.delete("/{project_id}/chat/history")
async def clear_project_chat_history(
    project_id: str,
    chat_session_id: str = "",
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.ai.chat")
    _ensure_project_access(project_id, auth_payload)
    username = _current_username(auth_payload)
    normalized_chat_session_id = str(chat_session_id or "").strip()
    removed = project_chat_store.clear_messages(
        project_id,
        username,
        normalized_chat_session_id,
    )
    if normalized_chat_session_id:
        project_chat_task_store.delete(project_id, username, normalized_chat_session_id)
    await _invalidate_project_requirement_records_cache(project_id)
    return {"status": "cleared", "removed_count": int(removed)}


@router.post("/{project_id}/chat/history/truncate")
async def truncate_project_chat_history(
    project_id: str,
    req: ProjectChatHistoryTruncateReq,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.ai.chat")
    _ensure_project_access(project_id, auth_payload)
    username = _current_username(auth_payload)
    message_id = str(req.message_id or "").strip()
    if not message_id:
        raise HTTPException(400, "message_id is required")
    removed = project_chat_store.truncate_messages(
        project_id,
        username,
        message_id,
        str(req.chat_session_id or "").strip(),
    )
    if removed <= 0:
        raise HTTPException(404, "message not found in chat session")
    return {"status": "truncated", "removed_count": int(removed)}


@router.get("/{project_id}/chat/sessions")
async def list_project_chat_sessions(
    project_id: str,
    limit: int = 50,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.ai.chat")
    _ensure_project_access(project_id, auth_payload)
    username = _current_username(auth_payload)
    records = project_chat_store.list_sessions(project_id, username, limit=limit)
    return {"sessions": [_serialize_chat_session(item) for item in records]}


@router.post("/{project_id}/chat/sessions")
async def create_project_chat_session(
    project_id: str,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.ai.chat")
    _ensure_project_access(project_id, auth_payload)
    username = _current_username(auth_payload)
    item = project_chat_store.create_session(project_id, username, "新对话")
    return {"session": _serialize_chat_session(item)}


@router.websocket("/{project_id}/chat/ws")
async def ws_project_chat(project_id: str, websocket: WebSocket):
    auth_payload = _extract_ws_auth_payload(websocket)
    if auth_payload is None:
        await websocket.close(code=4401, reason="Missing or invalid token")
        return
    try:
        _ensure_permission(auth_payload, "menu.ai.chat")
    except HTTPException:
        await websocket.close(code=4403, reason="Permission denied")
        return

    try:
        project = _ensure_project_access(project_id, auth_payload)
    except HTTPException as exc:
        code = 4404 if exc.status_code == 404 else 4403
        await websocket.close(code=code, reason=str(exc.detail))
        return

    await websocket.accept()
    username = _current_username(auth_payload)
    await websocket.send_json(
        {
            "type": "ready",
            "project_id": project_id,
            "message": "connected",
        }
    )

    active_tasks: dict[str, asyncio.Task] = {}
    cancel_events: dict[str, asyncio.Event] = {}

    async def handle_request(payload: dict):
        nonlocal active_tasks, cancel_events
        request_id = str(payload.get("request_id") or "").strip()
        if str(payload.get("type") or "").strip().lower() == "ping":
            await websocket.send_json({"type": "pong", "request_id": request_id})
            return

        if str(payload.get("type") or "").strip().lower() == "cancel":
            if request_id in cancel_events:
                cancel_events[request_id].set()
            return

        try:
            req = ProjectChatReq.model_validate(payload)
        except Exception as exc:
            await websocket.send_json({"type": "error", "request_id": request_id, "message": f"Invalid payload: {str(exc)}"})
            return
        chat_surface = _normalize_project_chat_surface(req.chat_surface)
        allow_requirement_record = _allow_project_chat_requirement_record(chat_surface)

        user_message = str(req.message or "").strip()
        assistant_message_id = str(req.assistant_message_id or "").strip()
        normalized_images = _normalize_image_inputs(req.images)
        attachment_names = [str(name or "").strip() for name in (req.attachment_names or []) if str(name or "").strip()]
        if not user_message and not normalized_images and not attachment_names:
            await websocket.send_json({"type": "error", "request_id": request_id, "message": "message is required"})
            return

        effective_user_message = user_message
        try:
            chat_session_id = _require_project_chat_session_id(req.chat_session_id)
        except ValueError as exc:
            await websocket.send_json({"type": "error", "request_id": request_id, "message": str(exc)})
            return
        if not effective_user_message and attachment_names:
            effective_user_message = f"我上传了附件：{', '.join(attachment_names)}。请先给我处理建议。"
        elif not effective_user_message and normalized_images:
            effective_user_message = "请基于我上传的图片给建议。"
        record_content = user_message or ("（发送了图片）" if normalized_images else "（发送了附件）")
        _append_chat_record(
            project_id=project_id, username=username, role="user", content=record_content,
            message_id=str(req.message_id or "").strip(),
            chat_session_id=chat_session_id,
            attachments=attachment_names, images=normalized_images,
        )

        cancel_event = asyncio.Event()
        cancel_events[request_id] = cancel_event

        try:
            runtime_settings = _resolve_chat_runtime_settings(req, project)
            selected_employees, candidates = _resolve_project_chat_employees(
                project_id,
                list(runtime_settings.get("selected_employee_ids") or []),
                str(runtime_settings.get("selected_employee_id") or ""),
            )
            selected_employee = selected_employees[0] if len(selected_employees) == 1 else None
            selected_employee_ids = [str(item.get("id") or "") for item in selected_employees if str(item.get("id") or "")]
            employee_id_val = selected_employee_ids[0] if len(selected_employee_ids) == 1 else ""

            enabled_tool_names = list(runtime_settings.get("enabled_project_tool_names") or [])
            explicit_tool_filter = bool(enabled_tool_names)
            task_tree_payload = _resolve_project_chat_task_tree_context(
                project_id,
                username,
                chat_session_id,
                runtime_settings,
                effective_user_message,
            )
            task_tree_prompt = str(
                (task_tree_payload or {}).get("model_context_summary") or ""
            ).strip()
            if _is_project_meta_query(effective_user_message):
                direct_answer = _build_project_meta_reply(project, selected_employee, candidates)
                await websocket.send_json(
                    _build_project_chat_start_payload(
                        request_id=request_id,
                        project_id=project_id,
                        provider_id="",
                        model_name="direct-project-meta",
                        employee_id=employee_id_val,
                        employee_name=str((selected_employee or {}).get("name") or ""),
                        tools_enabled=False,
                        task_tree_payload=task_tree_payload,
                    )
                )
                direct_done_payload = _build_project_chat_done_payload(
                    content=direct_answer,
                    project_id=project_id,
                    username=username,
                    chat_session_id=chat_session_id,
                    provider_id="",
                    model_name="direct-project-meta",
                    successful_tool_names=["direct-project-meta"],
                )
                direct_done_payload["request_id"] = request_id
                await websocket.send_json(
                    direct_done_payload
                )
                _append_chat_record(
                    project_id=project_id,
                    username=username,
                    role="assistant",
                    content=direct_answer,
                    message_id=assistant_message_id,
                    chat_session_id=chat_session_id,
                )
                _save_project_chat_memory_snapshot(
                    project_id=project_id,
                    user_message=effective_user_message,
                    answer=direct_answer,
                    chat_session_id=chat_session_id,
                    task_tree_payload=direct_done_payload.get("history_task_tree") or direct_done_payload.get("task_tree"),
                    selected_employee_ids=selected_employee_ids,
                    source=_compose_project_chat_memory_source("project-chat-ws-direct-meta", chat_surface),
                    allow_requirement_record=allow_requirement_record,
                )
                return

            tool_probe_name = _extract_tool_probe_name(effective_user_message)
            if tool_probe_name:
                direct_answer = _build_tool_probe_reply(
                    project_id,
                    employee_id_val,
                    tool_probe_name,
                    enabled_tool_names,
                    explicit_filter=explicit_tool_filter,
                )
                await websocket.send_json(
                    _build_project_chat_start_payload(
                        request_id=request_id,
                        project_id=project_id,
                        provider_id="",
                        model_name="direct-tool-probe",
                        employee_id=employee_id_val,
                        employee_name=str((selected_employee or {}).get("name") or ""),
                        tools_enabled=False,
                        task_tree_payload=task_tree_payload,
                    )
                )
                direct_done_payload = _build_project_chat_done_payload(
                    content=direct_answer,
                    project_id=project_id,
                    username=username,
                    chat_session_id=chat_session_id,
                    provider_id="",
                    model_name="direct-tool-probe",
                    successful_tool_names=["direct-tool-probe"],
                )
                direct_done_payload["request_id"] = request_id
                await websocket.send_json(
                    direct_done_payload
                )
                _append_chat_record(
                    project_id=project_id,
                    username=username,
                    role="assistant",
                    content=direct_answer,
                    message_id=assistant_message_id,
                    chat_session_id=chat_session_id,
                )
                _save_project_chat_memory_snapshot(
                    project_id=project_id,
                    user_message=effective_user_message,
                    answer=direct_answer,
                    chat_session_id=chat_session_id,
                    task_tree_payload=direct_done_payload.get("history_task_tree") or direct_done_payload.get("task_tree"),
                    selected_employee_ids=selected_employee_ids,
                    source=_compose_project_chat_memory_source("project-chat-ws-direct-tool-probe", chat_surface),
                    allow_requirement_record=allow_requirement_record,
                )
                return

            if _is_mcp_modules_query(effective_user_message):
                direct_answer = _build_mcp_modules_reply(project_id)
                await websocket.send_json(
                    _build_project_chat_start_payload(
                        request_id=request_id,
                        project_id=project_id,
                        provider_id="",
                        model_name="direct-mcp-modules",
                        employee_id=employee_id_val,
                        employee_name=str((selected_employee or {}).get("name") or ""),
                        tools_enabled=False,
                        task_tree_payload=task_tree_payload,
                    )
                )
                direct_done_payload = _build_project_chat_done_payload(
                    content=direct_answer,
                    project_id=project_id,
                    username=username,
                    chat_session_id=chat_session_id,
                    provider_id="",
                    model_name="direct-mcp-modules",
                    successful_tool_names=["direct-mcp-modules"],
                )
                direct_done_payload["request_id"] = request_id
                await websocket.send_json(
                    direct_done_payload
                )
                _append_chat_record(
                    project_id=project_id,
                    username=username,
                    role="assistant",
                    content=direct_answer,
                    message_id=assistant_message_id,
                    chat_session_id=chat_session_id,
                )
                _save_project_chat_memory_snapshot(
                    project_id=project_id,
                    user_message=effective_user_message,
                    answer=direct_answer,
                    chat_session_id=chat_session_id,
                    task_tree_payload=direct_done_payload.get("history_task_tree") or direct_done_payload.get("task_tree"),
                    selected_employee_ids=selected_employee_ids,
                    source=_compose_project_chat_memory_source("project-chat-ws-direct-mcp-modules", chat_surface),
                    allow_requirement_record=allow_requirement_record,
                )
                return

            resolved_runtime = await _resolve_project_chat_runtime(
                runtime_settings,
                auth_payload,
            )
            provider_mode = resolved_runtime.provider_mode
            selected_provider = resolved_runtime.provider
            provider_id = resolved_runtime.provider_id
            model_name = resolved_runtime.model_name
            from services.llm_provider_service import get_llm_provider_service

            llm_service = get_llm_provider_service()
            model_parameter_mode = _resolve_provider_model_parameter_mode(
                llm_service,
                provider_mode=provider_mode,
                selected_provider=selected_provider,
                model_name=model_name,
            )
            if model_parameter_mode in {"image", "video"}:
                await websocket.send_json(
                    _build_project_chat_start_payload(
                        request_id=request_id,
                        project_id=project_id,
                        provider_id=provider_id,
                        model_name=model_name,
                        chat_mode="system",
                        employee_id=employee_id_val,
                        employee_name=str((selected_employee or {}).get("name") or ""),
                        employee_ids=selected_employee_ids,
                        tools_enabled=False,
                        effective_tools=[],
                        effective_tool_total=0,
                        task_tree_payload=task_tree_payload,
                    )
                )
                try:
                    done_payload = await _generate_project_chat_media_done_payload(
                        llm_service=llm_service,
                        auth_payload=auth_payload,
                        project_id=project_id,
                        username=username,
                        chat_session_id=chat_session_id,
                        assistant_message_id=assistant_message_id,
                        effective_user_message=effective_user_message,
                        selected_employee_ids=selected_employee_ids,
                        provider_id=provider_id,
                        model_name=model_name,
                        runtime_settings=runtime_settings,
                        memory_source=_compose_project_chat_memory_source("project-chat-ws-media", chat_surface),
                        allow_requirement_record=allow_requirement_record,
                    )
                    done_payload["request_id"] = request_id
                    await websocket.send_json(done_payload)
                except Exception as exc:
                    _append_chat_record(
                        project_id=project_id,
                        username=username,
                        role="assistant",
                        content=f"对话失败：{str(exc)}",
                        message_id=assistant_message_id,
                        chat_session_id=chat_session_id,
                    )
                    await websocket.send_json({"type": "error", "request_id": request_id, "message": str(exc)})
                return

            max_tokens = _resolve_chat_max_tokens(runtime_settings.get("max_tokens"))
            temperature = float(runtime_settings.get("temperature") if runtime_settings.get("temperature") is not None else 0.1)
            temperature = max(0.0, min(temperature, 2.0))
            effective_workspace_path = _resolve_project_workspace_for_chat(project, runtime_settings)

            tools: list[dict] = []
            local_connector_tools: list[dict] = []
            selected_local_connector = None
            local_connector_sandbox_mode = ""
            tools_enabled = bool(runtime_settings.get("auto_use_tools")) and _should_enable_chat_tools(
                effective_user_message, attachment_names, normalized_images
            )
            if tools_enabled:
                tools = _collect_runtime_tools(
                    project_id,
                    selected_employee_ids=selected_employee_ids,
                    enabled_tool_names=enabled_tool_names,
                    explicit_tool_filter=explicit_tool_filter,
                    tool_priority=list(runtime_settings.get("tool_priority") or []),
                )
            (
                local_connector_tools,
                selected_local_connector,
                local_connector_sandbox_mode,
            ) = _resolve_local_connector_coding_tools(
                auth_payload,
                runtime_settings,
                effective_workspace_path,
            )
            if local_connector_tools:
                tools.extend(local_connector_tools)
            effective_tools, effective_tool_total = _summarize_effective_tools(tools)
            messages = _build_project_chat_messages(
                project, effective_user_message, req.history, normalized_images,
                selected_employee=selected_employee,
                selected_employees=selected_employees,
                tools=tools,
                custom_system_prompt=_resolve_default_chat_system_prompt(runtime_settings.get("system_prompt")),
                history_limit=int(runtime_settings.get("history_limit") or 20),
                answer_style=str(runtime_settings.get("answer_style") or "concise"),
                prefer_conclusion_first=bool(runtime_settings.get("prefer_conclusion_first", True)),
                workspace_path=effective_workspace_path,
                skill_resource_directory=req.skill_resource_directory,
                employee_coordination_mode=str(runtime_settings.get("employee_coordination_mode") or "auto"),
                task_tree_prompt=task_tree_prompt,
            )
            runtime_context = build_chat_runtime_context(
                project_id=project_id,
                username=username,
                chat_session_id=chat_session_id,
                employee_id=employee_id_val,
                selected_employee_ids=selected_employee_ids,
                workspace_path=effective_workspace_path,
                skill_resource_directory=req.skill_resource_directory,
                chat_surface=chat_surface,
                history=req.history,
                images=normalized_images,
                task_tree_payload=task_tree_payload,
                task_tree_prompt=task_tree_prompt,
                chat_settings=runtime_settings,
                resolved_provider=resolved_runtime,
                tools=tools,
                messages=messages,
                local_connector=selected_local_connector,
                local_connector_sandbox_mode=local_connector_sandbox_mode,
            )

        except Exception as exc:
            await websocket.send_json({"type": "error", "request_id": request_id, "message": str(exc)})
            return

        await websocket.send_json(
            _build_project_chat_start_payload(
                request_id=request_id,
                project_id=project_id,
                provider_id=provider_id,
                model_name=model_name,
                chat_mode="system",
                employee_id=employee_id_val,
                employee_name=str((selected_employee or {}).get("name") or ""),
                employee_ids=selected_employee_ids,
                tools_enabled=bool(tools),
                effective_tools=effective_tools,
                effective_tool_total=effective_tool_total,
                task_tree_payload=task_tree_payload,
            )
        )

        try:
            final_answer = ""
            stream_error = ""
            assistant_artifacts: list[dict[str, Any]] = []
            last_done_payload: dict[str, Any] | None = None

            llm_service = _resolve_chat_llm_service_runtime(
                llm_service,
                resolved_runtime,
                auth_payload,
            )

            # 创建会话和编排器
            redis_client = await get_redis_client()
            conv_manager = ConversationManager(redis_client)
            session_id = await conv_manager.create_session(project_id, employee_id_val)
            orchestrator = build_agent_orchestrator(
                llm_service,
                conv_manager,
                runtime_settings,
                orchestrator_cls=AgentOrchestrator,
            )

            async for chunk_data in orchestrator.run(
                **build_orchestrator_run_kwargs(
                    session_id=session_id,
                    user_message=effective_user_message,
                    runtime_context=runtime_context,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    cancel_event=cancel_event,
                )
            ):
                outgoing = dict(chunk_data)
                event_type = str(outgoing.get("type") or "").strip().lower()
                if event_type == "artifact":
                    artifact_batch = _normalize_chat_media_artifacts(outgoing.get("artifacts"))
                    if artifact_batch:
                        _save_chat_media_artifacts_to_materials(
                            project_id=project_id,
                            username=username,
                            chat_session_id=chat_session_id,
                            source_message_id=assistant_message_id,
                            artifacts=artifact_batch,
                            tool_name=str(outgoing.get("tool_name") or "").strip(),
                        )
                        assistant_artifacts = _merge_chat_media_artifacts(
                            assistant_artifacts,
                            artifact_batch,
                        )
                        outgoing["artifacts"] = artifact_batch
                        outgoing["images"] = _collect_chat_artifact_urls(artifact_batch, asset_type="image")
                        outgoing["videos"] = _collect_chat_artifact_urls(artifact_batch, asset_type="video")
                    else:
                        outgoing["artifacts"] = []
                        outgoing["images"] = []
                        outgoing["videos"] = []
                if event_type == "done":
                    assistant_artifacts = _merge_chat_media_artifacts(
                        assistant_artifacts,
                        _normalize_chat_media_artifacts(outgoing.get("artifacts")),
                    )
                    outgoing["artifacts"] = assistant_artifacts
                    outgoing["images"] = _collect_chat_artifact_urls(assistant_artifacts, asset_type="image")
                    outgoing["videos"] = _collect_chat_artifact_urls(assistant_artifacts, asset_type="video")
                    final_answer = str(outgoing.get("content") or "")
                    last_done_payload = dict(outgoing)
                if event_type == "error":
                    stream_error = str(outgoing.get("message") or "未知错误")
                outgoing["request_id"] = request_id
                await websocket.send_json(outgoing)

            if stream_error:
                _append_chat_record(
                    project_id=project_id, username=username, role="assistant", content=f"对话失败：{stream_error}",
                    message_id=assistant_message_id,
                    chat_session_id=chat_session_id,
                )
            else:
                assistant_images = _collect_chat_artifact_urls(assistant_artifacts, asset_type="image")
                assistant_videos = _collect_chat_artifact_urls(assistant_artifacts, asset_type="video")
                persisted_answer = (
                    final_answer
                    or (
                        "已生成图片和视频，请查看下方结果。"
                        if assistant_images and assistant_videos
                        else "已生成图片，请查看下方结果。"
                        if assistant_images
                        else "已生成视频，请查看下方结果。"
                        if assistant_videos
                        else "模型未返回有效内容。"
                    )
                )
                _append_chat_record(
                    project_id=project_id,
                    username=username,
                    role="assistant",
                    content=persisted_answer,
                    message_id=assistant_message_id,
                    chat_session_id=chat_session_id,
                    images=assistant_images,
                    videos=assistant_videos,
                )
                _save_project_chat_memory_snapshot(
                    project_id=project_id,
                    user_message=effective_user_message,
                    answer=final_answer or persisted_answer,
                    chat_session_id=chat_session_id,
                    task_tree_payload=(last_done_payload or {}).get("history_task_tree")
                    or (last_done_payload or {}).get("task_tree"),
                    selected_employee_ids=selected_employee_ids,
                    source=_compose_project_chat_memory_source("project-chat-ws", chat_surface),
                    allow_requirement_record=allow_requirement_record,
                )
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            _append_chat_record(
                project_id=project_id,
                username=username,
                role="assistant",
                content=f"对话失败：{str(exc)}",
                message_id=assistant_message_id,
                chat_session_id=chat_session_id,
            )
            await websocket.send_json({"type": "error", "request_id": request_id, "message": str(exc)})
        finally:
            cancel_events.pop(request_id, None)
            active_tasks.pop(request_id, None)

    while True:
        try:
            payload = await websocket.receive_json()
            if not isinstance(payload, dict):
                await websocket.send_json({"type": "error", "message": "Invalid payload type"})
                continue
                
            request_id = str(payload.get("request_id") or "").strip()
            payload_type = str(payload.get("type") or "").strip().lower()
            if payload_type == "cancel":
                if request_id in cancel_events:
                    cancel_events[request_id].set()
                continue

            task = asyncio.create_task(handle_request(payload))
            if request_id:
                active_tasks[request_id] = task
                
        except WebSocketDisconnect:
            for ev in cancel_events.values():
                ev.set()
            for t in active_tasks.values():
                t.cancel()
            break
        except Exception:
            await websocket.send_json({"type": "error", "message": "Invalid JSON payload"})
            continue

@router.post("/{project_id}/chat/stream")
async def stream_project_chat(
    project_id: str,
    req: ProjectChatReq,
    auth_payload: dict = Depends(require_auth),
):
    from services.llm_provider_service import get_llm_provider_service

    _ensure_permission(auth_payload, "menu.ai.chat")
    project = _ensure_project_access(project_id, auth_payload)
    username = _current_username(auth_payload)
    chat_surface = _normalize_project_chat_surface(req.chat_surface)
    allow_requirement_record = _allow_project_chat_requirement_record(chat_surface)

    user_message = str(req.message or "").strip()
    assistant_message_id = str(req.assistant_message_id or "").strip()
    normalized_images = _normalize_image_inputs(req.images)
    attachment_names = [str(name or "").strip() for name in (req.attachment_names or []) if str(name or "").strip()]
    if not user_message and not normalized_images and not attachment_names:
        raise HTTPException(400, "message is required")

    effective_user_message = user_message
    try:
        chat_session_id = _require_project_chat_session_id(req.chat_session_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not effective_user_message and attachment_names:
        effective_user_message = f"我上传了附件：{', '.join(attachment_names)}。请先给我处理建议。"
    elif not effective_user_message and normalized_images:
        effective_user_message = "请基于我上传的图片给建议。"
    record_content = user_message or ("（发送了图片）" if normalized_images else "（发送了附件）")
    _append_chat_record(
        project_id=project_id,
        username=username,
        role="user",
        content=record_content,
        message_id=str(req.message_id or "").strip(),
        chat_session_id=chat_session_id,
        attachments=attachment_names,
        images=normalized_images,
    )

    runtime_settings = _resolve_chat_runtime_settings(req, project)
    try:
        selected_employees, candidates = _resolve_project_chat_employees(
            project_id,
            list(runtime_settings.get("selected_employee_ids") or []),
            str(runtime_settings.get("selected_employee_id") or ""),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    selected_employee = selected_employees[0] if len(selected_employees) == 1 else None
    selected_employee_ids = [str(item.get("id") or "") for item in selected_employees if str(item.get("id") or "")]
    employee_id_val = selected_employee_ids[0] if len(selected_employee_ids) == 1 else ""
    enabled_tool_names = list(runtime_settings.get("enabled_project_tool_names") or [])
    explicit_tool_filter = bool(enabled_tool_names)
    try:
        task_tree_payload = _resolve_project_chat_task_tree_context(
            project_id,
            username,
            chat_session_id,
            runtime_settings,
            effective_user_message,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    task_tree_prompt = str(
        (task_tree_payload or {}).get("model_context_summary") or ""
    ).strip()
    if _is_project_meta_query(effective_user_message):
        answer = _build_project_meta_reply(project, selected_employee, candidates)

        async def direct_event_stream() -> AsyncIterator[str]:
            done_payload = _build_project_chat_done_payload(
                content=answer,
                project_id=project_id,
                username=username,
                chat_session_id=chat_session_id,
                provider_id="",
                model_name="direct-project-meta",
                successful_tool_names=["direct-project-meta"],
            )
            yield _sse_payload(
                "message",
                _build_project_chat_start_payload(
                    project_id=project_id,
                    provider_id="",
                    model_name="direct-project-meta",
                    employee_id=employee_id_val,
                    employee_name=str((selected_employee or {}).get("name") or ""),
                    tools_enabled=False,
                    task_tree_payload=task_tree_payload,
                ),
            )
            for part in _chunk_text(answer):
                yield _sse_payload("message", {"type": "delta", "content": part})
            yield _sse_payload("message", done_payload)
            _append_chat_record(
                project_id=project_id,
                username=username,
                role="assistant",
                content=answer,
                message_id=assistant_message_id,
                chat_session_id=chat_session_id,
            )
            _save_project_chat_memory_snapshot(
                project_id=project_id,
                user_message=effective_user_message,
                answer=answer,
                chat_session_id=chat_session_id,
                task_tree_payload=done_payload.get("history_task_tree") or done_payload.get("task_tree"),
                selected_employee_ids=selected_employee_ids,
                source=_compose_project_chat_memory_source("project-chat-sse-direct-meta", chat_surface),
                allow_requirement_record=allow_requirement_record,
            )

        return StreamingResponse(
            direct_event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    tool_probe_name = _extract_tool_probe_name(effective_user_message)
    if tool_probe_name:
        answer = _build_tool_probe_reply(
            project_id,
            employee_id_val,
            tool_probe_name,
            enabled_tool_names,
            explicit_filter=explicit_tool_filter,
        )

        async def direct_tool_event_stream() -> AsyncIterator[str]:
            done_payload = _build_project_chat_done_payload(
                content=answer,
                project_id=project_id,
                username=username,
                chat_session_id=chat_session_id,
                provider_id="",
                model_name="direct-tool-probe",
                successful_tool_names=["direct-tool-probe"],
            )
            yield _sse_payload(
                "message",
                _build_project_chat_start_payload(
                    project_id=project_id,
                    provider_id="",
                    model_name="direct-tool-probe",
                    employee_id=employee_id_val,
                    employee_name=str((selected_employee or {}).get("name") or ""),
                    tools_enabled=False,
                    task_tree_payload=task_tree_payload,
                ),
            )
            for part in _chunk_text(answer):
                yield _sse_payload("message", {"type": "delta", "content": part})
            yield _sse_payload("message", done_payload)
            _append_chat_record(
                project_id=project_id,
                username=username,
                role="assistant",
                content=answer,
                message_id=assistant_message_id,
                chat_session_id=chat_session_id,
            )
            _save_project_chat_memory_snapshot(
                project_id=project_id,
                user_message=effective_user_message,
                answer=answer,
                chat_session_id=chat_session_id,
                task_tree_payload=done_payload.get("history_task_tree") or done_payload.get("task_tree"),
                selected_employee_ids=selected_employee_ids,
                source=_compose_project_chat_memory_source("project-chat-sse-direct-tool-probe", chat_surface),
                allow_requirement_record=allow_requirement_record,
            )

        return StreamingResponse(
            direct_tool_event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    if _is_mcp_modules_query(effective_user_message):
        answer = _build_mcp_modules_reply(project_id)

        async def direct_mcp_event_stream() -> AsyncIterator[str]:
            done_payload = _build_project_chat_done_payload(
                content=answer,
                project_id=project_id,
                username=username,
                chat_session_id=chat_session_id,
                provider_id="",
                model_name="direct-mcp-modules",
                successful_tool_names=["direct-mcp-modules"],
            )
            yield _sse_payload(
                "message",
                _build_project_chat_start_payload(
                    project_id=project_id,
                    provider_id="",
                    model_name="direct-mcp-modules",
                    employee_id=employee_id_val,
                    employee_name=str((selected_employee or {}).get("name") or ""),
                    tools_enabled=False,
                    task_tree_payload=task_tree_payload,
                ),
            )
            for part in _chunk_text(answer):
                yield _sse_payload("message", {"type": "delta", "content": part})
            yield _sse_payload("message", done_payload)
            _append_chat_record(
                project_id=project_id,
                username=username,
                role="assistant",
                content=answer,
                message_id=assistant_message_id,
                chat_session_id=chat_session_id,
            )
            _save_project_chat_memory_snapshot(
                project_id=project_id,
                user_message=effective_user_message,
                answer=answer,
                chat_session_id=chat_session_id,
                task_tree_payload=done_payload.get("history_task_tree") or done_payload.get("task_tree"),
                selected_employee_ids=selected_employee_ids,
                source=_compose_project_chat_memory_source("project-chat-sse-direct-mcp-modules", chat_surface),
                allow_requirement_record=allow_requirement_record,
            )

        return StreamingResponse(
            direct_mcp_event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    resolved_runtime = await _resolve_project_chat_runtime(
        runtime_settings,
        auth_payload,
    )
    provider_mode = resolved_runtime.provider_mode
    selected_provider = resolved_runtime.provider
    provider_id = resolved_runtime.provider_id
    model_name = resolved_runtime.model_name

    llm_service = get_llm_provider_service()
    model_parameter_mode = _resolve_provider_model_parameter_mode(
        llm_service,
        provider_mode=provider_mode,
        selected_provider=selected_provider,
        model_name=model_name,
    )
    if model_parameter_mode in {"image", "video"}:
        async def media_event_stream() -> AsyncIterator[str]:
            yield _sse_payload(
                "message",
                _build_project_chat_start_payload(
                    project_id=project_id,
                    provider_id=provider_id,
                    model_name=model_name,
                    employee_id=str((selected_employee or {}).get("id") or ""),
                    employee_name=str((selected_employee or {}).get("name") or ""),
                    employee_ids=selected_employee_ids,
                    tools_enabled=False,
                    effective_tools=[],
                    effective_tool_total=0,
                    task_tree_payload=task_tree_payload,
                ),
            )
            try:
                done_payload = await _generate_project_chat_media_done_payload(
                    llm_service=llm_service,
                    auth_payload=auth_payload,
                    project_id=project_id,
                    username=username,
                    chat_session_id=chat_session_id,
                    assistant_message_id=assistant_message_id,
                    effective_user_message=effective_user_message,
                    selected_employee_ids=selected_employee_ids,
                    provider_id=provider_id,
                    model_name=model_name,
                    runtime_settings=runtime_settings,
                    memory_source=_compose_project_chat_memory_source("project-chat-sse-media", chat_surface),
                    allow_requirement_record=allow_requirement_record,
                )
                yield _sse_payload("message", done_payload)
            except Exception as exc:
                _append_chat_record(
                    project_id=project_id,
                    username=username,
                    role="assistant",
                    content=f"对话失败：{str(exc)}",
                    message_id=assistant_message_id,
                    chat_session_id=chat_session_id,
                )
                yield _sse_payload("message", {"type": "error", "message": str(exc)})

        return StreamingResponse(
            media_event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    max_tokens = _resolve_chat_max_tokens(runtime_settings.get("max_tokens"))
    temperature = float(runtime_settings.get("temperature") if runtime_settings.get("temperature") is not None else 0.1)
    temperature = max(0.0, min(temperature, 2.0))

    tools: list[dict] = []
    local_connector_tools: list[dict] = []
    selected_local_connector = None
    local_connector_sandbox_mode = ""
    tools_enabled = bool(runtime_settings.get("auto_use_tools")) and _should_enable_chat_tools(
        effective_user_message, attachment_names, normalized_images
    )
    if tools_enabled:
        tools = _collect_runtime_tools(
            project_id,
            selected_employee_ids=selected_employee_ids,
            enabled_tool_names=enabled_tool_names,
            explicit_tool_filter=explicit_tool_filter,
            tool_priority=list(runtime_settings.get("tool_priority") or []),
        )

    effective_workspace_path = _resolve_project_workspace_for_chat(project, runtime_settings)
    (
        local_connector_tools,
        selected_local_connector,
        local_connector_sandbox_mode,
    ) = _resolve_local_connector_coding_tools(
        auth_payload,
        runtime_settings,
        effective_workspace_path,
    )
    if local_connector_tools:
        tools.extend(local_connector_tools)
    effective_tools, effective_tool_total = _summarize_effective_tools(tools)

    messages = _build_project_chat_messages(
        project,
        effective_user_message,
        req.history,
        normalized_images,
        selected_employee=selected_employee,
        selected_employees=selected_employees,
        tools=tools,
        custom_system_prompt=_resolve_default_chat_system_prompt(runtime_settings.get("system_prompt")),
        history_limit=int(runtime_settings.get("history_limit") or 20),
        answer_style=str(runtime_settings.get("answer_style") or "concise"),
        prefer_conclusion_first=bool(runtime_settings.get("prefer_conclusion_first", True)),
        workspace_path=effective_workspace_path,
        skill_resource_directory=req.skill_resource_directory,
        employee_coordination_mode=str(runtime_settings.get("employee_coordination_mode") or "auto"),
        task_tree_prompt=task_tree_prompt,
    )
    runtime_context = build_chat_runtime_context(
        project_id=project_id,
        username=username,
        chat_session_id=chat_session_id,
        employee_id=employee_id_val,
        selected_employee_ids=selected_employee_ids,
        workspace_path=effective_workspace_path,
        skill_resource_directory=req.skill_resource_directory,
        chat_surface=chat_surface,
        history=req.history,
        images=normalized_images,
        task_tree_payload=task_tree_payload,
        task_tree_prompt=task_tree_prompt,
        chat_settings=runtime_settings,
        resolved_provider=resolved_runtime,
        tools=tools,
        messages=messages,
        local_connector=selected_local_connector,
        local_connector_sandbox_mode=local_connector_sandbox_mode,
    )

    async def event_stream() -> AsyncIterator[str]:
        yield _sse_payload(
            "message",
            _build_project_chat_start_payload(
                project_id=project_id,
                provider_id=provider_id,
                model_name=model_name,
                employee_id=str((selected_employee or {}).get("id") or ""),
                employee_name=str((selected_employee or {}).get("name") or ""),
                employee_ids=selected_employee_ids,
                tools_enabled=bool(tools),
                effective_tools=effective_tools,
                effective_tool_total=effective_tool_total,
                task_tree_payload=task_tree_payload,
            ),
        )
        try:
            llm_service_runtime = _resolve_chat_llm_service_runtime(
                llm_service,
                resolved_runtime,
                auth_payload,
            )

            redis_client = await get_redis_client()
            conv_manager = ConversationManager(redis_client)
            session_id = await conv_manager.create_session(project_id, employee_id_val)
            orchestrator = build_agent_orchestrator(
                llm_service_runtime,
                conv_manager,
                runtime_settings,
                orchestrator_cls=AgentOrchestrator,
            )

            final_answer = ""
            stream_error = ""
            assistant_artifacts: list[dict[str, Any]] = []
            last_done_payload: dict[str, Any] | None = None
            cancel_event = asyncio.Event()
            async for chunk_data in orchestrator.run(
                **build_orchestrator_run_kwargs(
                    session_id=session_id,
                    user_message=effective_user_message,
                    runtime_context=runtime_context,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    cancel_event=cancel_event,
                )
            ):
                outgoing = dict(chunk_data)
                event_type = str(outgoing.get("type") or "").strip().lower()
                if event_type == "artifact":
                    artifact_batch = _normalize_chat_media_artifacts(outgoing.get("artifacts"))
                    if artifact_batch:
                        _save_chat_media_artifacts_to_materials(
                            project_id=project_id,
                            username=username,
                            chat_session_id=chat_session_id,
                            source_message_id=assistant_message_id,
                            artifacts=artifact_batch,
                            tool_name=str(outgoing.get("tool_name") or "").strip(),
                        )
                        assistant_artifacts = _merge_chat_media_artifacts(
                            assistant_artifacts,
                            artifact_batch,
                        )
                        outgoing["artifacts"] = artifact_batch
                        outgoing["images"] = _collect_chat_artifact_urls(artifact_batch, asset_type="image")
                        outgoing["videos"] = _collect_chat_artifact_urls(artifact_batch, asset_type="video")
                    else:
                        outgoing["artifacts"] = []
                        outgoing["images"] = []
                        outgoing["videos"] = []
                if event_type == "done":
                    assistant_artifacts = _merge_chat_media_artifacts(
                        assistant_artifacts,
                        _normalize_chat_media_artifacts(outgoing.get("artifacts")),
                    )
                    outgoing["artifacts"] = assistant_artifacts
                    outgoing["images"] = _collect_chat_artifact_urls(assistant_artifacts, asset_type="image")
                    outgoing["videos"] = _collect_chat_artifact_urls(assistant_artifacts, asset_type="video")
                    final_answer = str(outgoing.get("content") or "")
                    last_done_payload = dict(outgoing)
                if event_type == "error":
                    stream_error = str(outgoing.get("message") or "未知错误")
                yield _sse_payload("message", outgoing)

            if stream_error:
                _append_chat_record(
                    project_id=project_id,
                    username=username,
                    role="assistant",
                    content=f"对话失败：{stream_error}",
                    message_id=assistant_message_id,
                    chat_session_id=chat_session_id,
                )
            else:
                assistant_images = _collect_chat_artifact_urls(assistant_artifacts, asset_type="image")
                assistant_videos = _collect_chat_artifact_urls(assistant_artifacts, asset_type="video")
                persisted_answer = (
                    final_answer
                    or (
                        "已生成图片和视频，请查看下方结果。"
                        if assistant_images and assistant_videos
                        else "已生成图片，请查看下方结果。"
                        if assistant_images
                        else "已生成视频，请查看下方结果。"
                        if assistant_videos
                        else "模型未返回有效内容。"
                    )
                )
                _append_chat_record(
                    project_id=project_id,
                    username=username,
                    role="assistant",
                    content=persisted_answer,
                    message_id=assistant_message_id,
                    chat_session_id=chat_session_id,
                    images=assistant_images,
                    videos=assistant_videos,
                )
                _save_project_chat_memory_snapshot(
                    project_id=project_id,
                    user_message=effective_user_message,
                    answer=final_answer or persisted_answer,
                    chat_session_id=chat_session_id,
                    task_tree_payload=(last_done_payload or {}).get("history_task_tree")
                    or (last_done_payload or {}).get("task_tree"),
                    selected_employee_ids=selected_employee_ids,
                    source=_compose_project_chat_memory_source("project-chat-sse", chat_surface),
                    allow_requirement_record=allow_requirement_record,
                )
        except Exception as exc:
            _append_chat_record(
                project_id=project_id,
                username=username,
                role="assistant",
                content=f"对话失败：{str(exc)}",
                message_id=assistant_message_id,
                chat_session_id=chat_session_id,
            )
            yield _sse_payload("message", {"type": "error", "message": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _build_project_manual_template_payload(project_id: str) -> dict[str, Any]:
    """构建项目使用手册正文。"""
    from routers.employees import _build_employee_manual_payload

    project = project_store.get(project_id)
    if project is None:
        raise HTTPException(404, f"Project {project_id} not found")

    member_items = _project_member_details(project_id)
    member_lines = []
    all_domains: set[str] = set()
    unique_skills: dict[str, dict] = {}
    for item in member_items:
        employee = item["employee"]
        member = item["member"]
        rule_bindings = list(item["rule_bindings"] or [])
        domains = _collect_rule_domains(rule_bindings)
        skills = item["skills"]
        for domain in domains:
            all_domains.add(str(domain))
        for skill in skills:
            unique_skills[str(skill["id"])] = skill
        member_lines.append(
            f"- {employee.name} ({employee.id}) role={member.role} "
            f"skills={len(skills)} domains={len(domains)}"
        )

    members_text = "\n".join(member_lines) if member_lines else "无"
    skills_text = (
        "\n\n".join(
            _format_manual_skill_item(
                str(s["id"]),
                str(s["name"]),
                str(s.get("description", "")),
                entry_count=int(s.get("entry_count", 0) or 0),
                sample_entries=list(s.get("sample_entries") or []),
                list_tool_name="list_project_proxy_tools",
                invoke_tool_name="invoke_project_skill_tool",
            )
            for s in unique_skills.values()
        )
        if unique_skills
        else "无"
    )
    project_rule_bindings: list[dict[str, str]] = []
    for item in member_items:
        project_rule_bindings.extend(list(item["rule_bindings"] or []))
    domains_text = _format_rule_domain_summary(project_rule_bindings) if project_rule_bindings else "无"
    project_ui_rule_bindings = _resolve_project_ui_rule_bindings(project, include_content=True)
    project_ui_rule_lines: list[str] = []
    for item in project_ui_rule_bindings:
        title = str(item.get("title") or item.get("id") or "").strip() or "未命名规则"
        rule_id = str(item.get("id") or "").strip() or "-"
        domain = str(item.get("domain") or "").strip() or "-"
        content = str(item.get("content") or "").strip() or "规则正文为空"
        project_ui_rule_lines.append(
            f"""### {title}
- 规则 ID: `{rule_id}`
- 领域: {domain}
- 优先级: 高于员工个人规则

{content}
"""
        )
    project_ui_rules_text = "\n".join(project_ui_rule_lines) if project_ui_rule_lines else "无"
    project_experience_rule_bindings = _resolve_project_experience_rule_bindings(project)
    project_experience_rule_lines: list[str] = []
    for item in project_experience_rule_bindings:
        title = str(item.get("title") or item.get("id") or "").strip() or "未命名经验规则"
        rule_id = str(item.get("id") or "").strip() or "-"
        domain = str(item.get("domain") or "").strip() or "-"
        preview = str(item.get("preview") or "").strip() or "暂无摘要"
        project_experience_rule_lines.append(
            f"- {title} (`{rule_id}` / {domain}): {preview}"
        )
    project_experience_rules_text = (
        "\n".join(project_experience_rule_lines) if project_experience_rule_lines else "无"
    )
    employee_template_lines: list[str] = []
    for item in member_items:
        employee = item["employee"]
        member = item["member"]
        employee_manual_payload = _build_employee_manual_payload(employee.id)
        employee_manual = str(employee_manual_payload.get("manual") or "").strip() or "无"
        employee_template_lines.append(
            f"""### {employee.name}（{employee.id}）
- 项目角色:{member.role}
- 复用来源:`/api/employees/{employee.id}/manual-template`
- 说明: 以下内容直接复用该员工的使用手册正文；员工手册调整后，项目手册会自动同步，无需在项目侧重复维护。

{employee_manual}
"""
        )
    employee_templates_text = "\n".join(employee_template_lines) if employee_template_lines else "无成员"
    chat_settings = getattr(project, "chat_settings", {}) or {}
    task_tree_enabled = bool(chat_settings.get("task_tree_enabled", True))
    task_tree_auto_generate = bool(chat_settings.get("task_tree_auto_generate", True))
    task_tree_manual_section = ""
    task_tree_workflow_line = ""
    if task_tree_enabled:
        task_tree_manual_section = f"""
## 任务树工作流

- 当前项目聊天已启用结构化任务树，作用域默认按 `project_id + username + chat_session_id` 隔离。
- {"发送首条任务消息后会自动生成任务树。" if task_tree_auto_generate else "当前项目未开启自动生成任务树，需要先显式生成任务树。"}
- 若当前入口没有显式携带 `chat_session_id`，必须先绑定当前会话；不要假设没有会话标识也能把任务树挂到正确聊天上。
- 任务树必须与项目记忆、工作轨迹绑定到同一条聊天会话；后续查看记忆详情时，应能回看该轮规划、执行节点和验证结果。
- 任务树节点必须直接对应用户目标下的工作步骤，不得把 `search_project_context`、`query_project_rules`、`search_ids`、`get_manual_content`、`resolve_relevant_context`、`generate_execution_plan` 这类内部检索/规划工具直接当成节点标题。
- 候选代理工具、脚本路径和类似 `Auto inferred proxy entry from scripts/...` 的描述，只能作为内部工具信息，不得直接展示为任务树节点。
- 开始执行节点时，先调用 `get_current_task_tree` 确认当前节点与节点 ID，再调用 `update_task_node_status` 标记为 `in_progress` 或 `verifying`。
- 完成节点时，必须调用 `complete_task_node_with_verification` 写入验证结果；未写验证结果前，不得把节点标记为 `done`。
- 若当前需求只是“谁 / 哪些 / 多少 / 从哪里”等查询型问题，任务树应尽量保持为单个检索回答节点，不要误拆成实现或协作开发步骤。
- 父节点完成前，必须确保全部子节点完成，并补齐父节点自己的整体验证结论。
- 当整棵任务树全部完成后，系统会自动把本次任务归档到项目历史里，并清空当前聊天上的活动任务树。
- 同一个聊天里出现下一条新需求时，系统会基于新的需求重新生成一棵活动任务树；历史归档记录仍可在项目详情的任务推进列表查看。
- 若本轮已经产生执行进展，但没有回写任务树，系统会保留节点在 `in_progress` 或 `verifying`，不会直接自动推荐完成。
- 查询型问题若已完成检索并给出明确答案，系统会自动补齐验证并归档，避免任务树停留在 `0%` 或 `67%`。
- `/ai/chat` 页面只展示当前仍在进行中的任务树；已完成或已归档任务树不应继续作为当前任务显示。
"""
        task_tree_workflow_line = "\n5. 如当前项目聊天已启用任务树，进入实现前先读取 `get_current_task_tree`；每完成一步都要写回节点状态与验证结果，未验证不得标记完成。"

    manual = f"""# {project.name} 项目使用手册

## 项目总览

- **项目 ID**：`{project.id}`
- **项目名称**：{project.name}
- **项目定位**：{project.description or "AI 开发团队"}
- **项目类型**：{_PROJECT_TYPE_LABELS.get(_normalize_project_type(getattr(project, "type", "mixed")), _PROJECT_TYPE_LABELS["mixed"])}
- **反馈升级**：{"已启用" if project.feedback_upgrade_enabled else "未启用"}
- **成员概览**：
{members_text}

### 强制执行流程
1. 收到用户提问后，先调用 `get_project_runtime_context` 或 `list_project_members` 了解成员和能力范围。
2. 进入分析、实现或排查前，先阅读本项目手册；解决问题时优先依赖项目绑定的员工、规则和技能，不要绕过项目内现成能力直接自行发挥。
3. 每次新请求都要重新调用 `query_project_rules` 获取与当前问题直接相关的规则正文；不要只看规则标题，也不要把无关项目规则全文机械带入当前问题。
4. 若项目已沉淀经验规则，且当前需求明显可能复用历史做法，调用 `resolve_project_experience_rules(task_text="<用户原始需求>")` 按需加载相关经验卡片；不要把全部经验规则机械注入上下文。
5. 先判断当前任务能否由单个项目绑定员工闭环；若可以，优先使用该员工已绑定技能及其代理工具。只有项目员工、规则、技能无法覆盖时，才使用自身通用能力补足。
6. 仅在新需求开始、续跑恢复、修复旧问题或当前问题明显依赖历史经验时，调用 `recall_project_memory` 检索相关记忆，优先传 `project_name="{project.name}"`。
7. 优先复用宿主系统的自动记忆快照；如当前入口未覆盖自动记录链路，或本轮需要额外沉淀稳定结论/关键决策，再调用一次 `save_project_memory` 补记。不要在同一需求的每个中间步骤重复写入项目记忆。
7.1 若本轮对话存在任务树或执行规划，记忆与工作轨迹必须复用同一条 `chat_session_id` / `session_id`，确保后续能从记忆详情回看规划、节点状态和验证结果。
8. 在决定是否需要多人协作前，先把本项目手册与相关员工手册视为协作基线：AI 需结合任务目标、规则、技能和工具，自主判断单人主责还是多人协作，不预设固定行业角色分工。
9. 遇到页面、交互、视觉表达类任务时，先检查本项目绑定的 UI 规则；这些规则优先级高于员工个人规则。{task_tree_workflow_line}
10. 开始实现或排查前，调用 `list_project_proxy_tools` 检查项目成员现有技能工具，再结合 `query_project_rules` 和 `resolve_project_experience_rules` 的结果收敛方案；若任务需要项目内多员工自动协作，可优先调用 `execute_project_collaboration`。
11. 锁定匹配项后，再调用 `invoke_project_skill_tool`，必要时补 `employee_id` 消歧；若采用多人协作，先明确负责人、子任务边界和结果交接。
12. 如需沉淀结构化结论、排查经验或关键决策，在自动记录之外显式调用 `save_project_memory` 追加一条可复用记忆。
13. 发现规则缺口、工具异常或稳定性问题时，调用 `submit_project_feedback_bug`。

### 记忆保存示例
```json
save_project_memory({{
  "employee_id": "<项目成员ID>",
  "content": "问题：<问题摘要>\\n结论：<最终方案>\\n关键决策：<需要沉淀的信息>",
  "project_name": "{project.name}"
}})
```

{task_tree_manual_section}

## 项目成员与员工使用手册

{employee_templates_text}

## 项目级 UI 规则（优先级高于员工个人规则）

- 页面、交互、视觉表达相关任务，先遵循这里的项目级 UI 规则，再参考员工个人规则。
- 若项目级 UI 规则与员工个人规则冲突，以项目级 UI 规则为准。

{project_ui_rules_text}

## 项目经验规则（按需加载）

- 项目经验规则用于沉淀历史需求里可复用的开发经验，不作为默认全量上下文注入。
- 当新需求与历史问题模式相近时，先调用 `resolve_project_experience_rules(task_text="<用户原始需求>")`，只取高相关经验卡片。
- 若当前任务与已有经验无关，不要为了“带上经验”而强行注入无关卡片。

{project_experience_rules_text}

## 项目共享技能索引（写手册时不要只写技能名，需结合下面信息展开）

{skills_text}

## 项目规则领域概览（仅用于快速筛选，不可替代具体规则）

{domains_text}

## 核心工具说明

- **`get_project_usage_guide`**：获取项目 MCP 使用说明与推荐调用顺序。
- **`get_project_manual`**：直接获取项目使用手册正文；也可读取 `project://<project_id>/manual` 资源。
- **`list_project_members`**：列出项目成员，用于先确定可协作员工。
- **`get_project_profile`**：读取项目基础配置、工作区和入口文件信息。
- **`get_project_runtime_context`**：查看项目运行时上下文、成员、项目级 UI 规则、规则和技能规模。
- **`resolve_project_experience_rules`**：按任务文本从项目经验规则中按需解析高相关经验卡片，避免无关经验占用上下文。
- **`recall_project_memory`**：按需检索项目记忆，优先传 `project_name="{project.name}"`；仅在新需求开始、续跑恢复、修复旧问题或明显需要历史经验时调用。
- **`save_project_memory`**：手动补记项目级结论、经验和关键决策；当当前入口未自动记录，或需要追加一条稳定结论/关键决策时再调用。不要在同一需求的每个中间步骤重复补记。若本轮存在任务树，应确保记忆与当前聊天会话绑定，后续可从记忆详情反查规划。
- **`query_project_rules`**：按关键词查询项目规则，返回项目级 UI 规则与成员规则；页面/交互类任务先看项目级 UI 规则，最终以具体规则正文为准。
- **`list_project_proxy_tools`**：列出项目可调用的成员技能工具。
- **`execute_project_collaboration`**：输入用户原始任务，由 AI 基于项目手册、员工手册、规则和工具，自主判断是否需要多人协作并生成协作步骤。
- **`invoke_project_skill_tool`**：调用项目成员技能，必要时补 `employee_id` 消歧。
- **`submit_project_feedback_bug`**：提交结构化反馈工单。

## 推荐工作流

```text
1. 获取项目上下文 / 成员信息，并先读取项目手册 → get_project_runtime_context 或 list_project_members + get_project_manual
2. 每次新请求先获取与当前任务直接相关的规则正文 → query_project_rules
3. 若项目存在经验规则且当前需求可能复用历史模式，按需解析经验卡片 → resolve_project_experience_rules
4. 优先检查项目绑定员工是否已具备可用技能工具 → list_project_proxy_tools
5. 先让项目内单员工或项目协作链路闭环；只有项目能力不足时才自行补足 → invoke_project_skill_tool / execute_project_collaboration
6. 按需记忆检索 → recall_project_memory
7. 每次对话记录 → 默认自动记录；未覆盖入口或需要额外沉淀稳定结论时，再调用一次 save_project_memory 补记，并确保与当前 chat_session_id / session_id 绑定
8. 结构化沉淀稳定结论/关键决策 → save_project_memory
9. 反馈闭环 → submit_project_feedback_bug
```

## 常见问题与故障排查

### Q1：数据库查询失败
- 首次使用需提供数据库配置。
- 检查连接信息是否正确。
- 仅支持当前技能暴露的查询能力和约束，不要越权执行。

### Q2：记忆检索无结果
- 先更换关键词。
- 检查 `project_name` 是否为 `{project.name}`。
- 必要时放宽 `employee_id` 过滤，从项目级范围继续搜索。

### Q3：规则查询返回多条结果
- 优先选择标题和当前任务最匹配的规则。
- 再比较 `domain`、`id`、`content`，不要只凭领域名判断。

### Q4：技能调用参数错误
- 先确认 `tool_name`、`employee_id` 是否真实存在。
- 再检查 `args` 是否满足工具要求。
- 无匹配技能时，改为给分析结论或转交合适成员。

## 最佳实践

### 参数规范
- 调用记忆时，必须传 `project_name="{project.name}"`。
- 调用技能时，优先传 `employee_id`，避免歧义。
- 提交反馈时，至少传 `employee_id`、`title`、`symptom`、`expected`。

### 员工选择
- 先结合项目手册、员工手册、规则和工具判断是否真的需要多人协作，不要默认多员工并行。
- 员工选择由 AI 根据当前任务自主决定；若单个员工已能闭环，就不要为凑分工而强行拆给多人。
- 需要多人协作时，先明确主负责人、辅助成员、交接边界和汇总责任。

### 记忆与规则
- 记忆检索只在新需求开始、续跑恢复、修复旧问题或明显需要历史经验时触发；不要把 recall 当成每轮固定前置步骤。
- 同一任务轮若已生成任务树并进入执行，后续优先依赖当前会话、任务树和工作轨迹，不要重复检索同一批项目记忆。
- 项目级 UI 规则优先于员工个人规则，尤其是页面、交互、视觉表达类任务。
- 项目经验规则默认按需解析，不默认全量注入；只有当前任务与经验卡片明显相关时才加载。
- 每次新请求都重新获取与当前问题匹配的规则正文，不要只凭上一次记忆或规则标题继续执行。
- 只使用与当前问题直接相关的项目规则，不要把无关规则全文机械套用到所有任务。
- 项目内已有员工、技能或协作链路可以闭环时，优先使用项目能力，不要跳过项目成员直接改走通用能力。
- 只有项目绑定员工、规则、技能都无法覆盖时，才由 AI 自行补足分析、实现或排查。
- 每次有效对话都要留下项目记忆；自动记录未覆盖时，必须手动补记。
- 结构化结论和关键决策建议额外补一条高质量记忆，便于后续复用。
- 若本轮存在任务树，记忆详情必须能回看该轮规划、节点状态和验证结果；不要把任务树和记忆拆成两条互相无法追溯的记录。
- `/ai/chat` 只展示当前进行中的任务树；查看历史任务应去项目历史或记忆详情，不应继续占据当前聊天任务区域。
- 不要把领域名直接当作规则正文。

### 事实边界
- 当前宿主系统已实现项目聊天自动记忆快照；若当前入口未接入该链路，仍需显式调用 `save_project_memory`。若已接入自动快照，不要再为同一需求的每个中间步骤重复补记。
- 不得臆造不存在的 `skill_id`、`tool_name`、`rule_id` 或规则正文。
- 面向接入方 AI 平台时，默认按 MCP 显式调用描述。
"""

    return {
        "status": "success",
        "manual": manual,
        "template": manual,
        "project_id": project.id,
        "project_name": project.name,
        "members_summary": members_text,
        "skills_summary": skills_text,
        "rule_domains_summary": domains_text,
    }


@router.get("/{project_id}/manual-template")
async def get_project_manual_template(project_id: str, auth_payload: dict = Depends(require_auth)):
    """获取项目使用手册正文。"""
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_access(project_id, auth_payload)
    return _build_project_manual_template_payload(project_id)
