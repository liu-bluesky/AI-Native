"""项目管理路由"""

from __future__ import annotations

import json
import mimetypes
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import asdict, replace
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool
import asyncio
from services.agent_orchestrator import AgentOrchestrator
from services.conversation_manager import ConversationManager
from core.redis_client import get_redis_client

# from ai_decision import ai_decide_action, execute_db_query, recommend_better_project  # 已废弃
from core.auth import decode_token
from core.config import get_api_data_dir, get_project_root
from core.deps import employee_store, external_mcp_store, is_admin_like, local_connector_store, project_chat_store, project_material_store, project_studio_export_store, project_store, require_auth, role_store, system_config_store, user_store
from services.feedback_service import get_feedback_service
from services.local_connector_service import (
    LocalConnectorLlmAdapter,
    build_local_connector_provider_id,
    chat_completion_via_connector,
    connector_base_url,
    list_connector_llm_models,
    parse_local_connector_provider_id,
)
from services.llm_chat_parameter_catalog import (
    get_chat_parameter_default_value,
    normalize_chat_parameter_value,
)
from services.llm_model_type_catalog import DEFAULT_MODEL_TYPE
from services.project_voice_service import get_project_voice_service
from models.requests import (
    ProjectAiEntryFileUpdateReq,
    ProjectChatHistoryTruncateReq,
    ProjectChatReq,
    ProjectChatSettingsUpdateReq,
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
    WorkspaceDirectoryPickReq,
    WorkspaceFilePickReq,
)
from stores.json.project_chat_store import ProjectChatMessage
from stores.json.project_material_store import ProjectMaterialAsset
from stores.json.project_studio_export_store import ProjectStudioExportJob
from stores.json.project_store import ProjectConfig, ProjectMember, ProjectUserMember, _now_iso
from core.role_permissions import has_permission, resolve_role_permissions
from stores.mcp_bridge import Classification, Memory, MemoryScope, MemoryType, memory_store, rule_store, skill_store

router = APIRouter(prefix="/api/projects", dependencies=[Depends(require_auth)])

_PROJECT_USERNAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{1,63}")
_PROJECT_EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")

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


def _can_manage_project(project_id: str, auth_payload: dict, project: ProjectConfig | None = None) -> bool:
    if _is_admin_like(auth_payload):
        return True
    username = _current_username(auth_payload)
    creator_username = _project_creator_username(project_id, project)
    return bool(username and creator_username and username == creator_username)


def _serialize_project(project: ProjectConfig, auth_payload: dict | None = None) -> dict:
    data = asdict(project)
    data.pop("chat_settings", None)
    normalized_type = _normalize_project_type(getattr(project, "type", "mixed"))
    creator_username = _project_creator_username(project.id, project)
    data["type"] = normalized_type
    data["type_label"] = _PROJECT_TYPE_LABELS.get(normalized_type, _PROJECT_TYPE_LABELS["mixed"])
    data["member_count"] = len(project_store.list_members(project.id))
    data["user_count"] = len(project_store.list_user_members(project.id))
    data["created_by"] = creator_username
    data["ui_rule_ids"] = _normalize_project_ui_rule_ids(getattr(project, "ui_rule_ids", []) or [])
    data["ui_rule_bindings"] = _resolve_project_ui_rule_bindings(project)
    if auth_payload is not None:
        current_username = _current_username(auth_payload)
        current_member = _get_project_user_member(project.id, current_username)
        data["current_user_role"] = str(getattr(current_member, "role", "") or "").strip().lower()
        data["can_manage"] = _can_manage_project(project.id, auth_payload, project)
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
    _save_project_chat_memory_snapshot(
        project_id=project_id,
        user_message=effective_user_message,
        answer=content,
        selected_employee_ids=selected_employee_ids,
        source=memory_source,
    )
    return {
        "type": "done",
        "content": content,
        "provider_id": provider_id,
        "model_name": model_name,
        "artifacts": artifacts,
        "images": images,
        "videos": videos,
    }


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
    role_id = str(auth_payload.get("role") or "").strip().lower()
    role = role_store.get(role_id)
    permissions = getattr(role, "permissions", None)
    if not has_permission(permissions, permission_key, role_id=role_id):
        raise HTTPException(403, f"Permission denied: {permission_key}")


def _ensure_any_permission(auth_payload: dict, permission_keys: list[str]) -> None:
    role_id = str(auth_payload.get("role") or "").strip().lower()
    role = role_store.get(role_id)
    permissions = getattr(role, "permissions", None)
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


def _pick_chat_provider(provider_id: str, auth_payload: dict) -> tuple[dict, list[dict]]:
    from services.llm_provider_service import get_llm_provider_service

    llm_service = get_llm_provider_service()
    providers = llm_service.list_providers(
        enabled_only=True,
        owner_username=str(auth_payload.get("sub") or "").strip(),
        include_all=is_admin_like(auth_payload),
        include_shared=True,
    )
    if not providers:
        raise HTTPException(400, "未配置可用的 LLM 提供商")
    expected = str(provider_id or "").strip()
    if expected:
        selected = next((item for item in providers if str(item.get("id") or "") == expected), None)
        if selected is None:
            raise HTTPException(404, f"LLM provider not found: {expected}")
        return selected, providers
    default_provider = next((item for item in providers if bool(item.get("is_default"))), providers[0])
    return default_provider, providers


async def _build_connector_chat_provider(connector: Any) -> dict[str, Any] | None:
    connector_id = str(getattr(connector, "id", "") or "").strip()
    if not connector_id or not connector_base_url(connector):
        return None
    try:
        llm_info = await list_connector_llm_models(connector)
    except Exception:
        llm_info = {
            "enabled": False,
            "default_model": "",
            "models": [],
        }
    if not bool(llm_info.get("enabled")):
        return None
    models = [
        str(item or "").strip()
        for item in (llm_info.get("models") or [])
        if str(item or "").strip()
    ]
    default_model = str(llm_info.get("default_model") or "").strip()
    if default_model and default_model not in models:
        models = [default_model, *models]
    if not models:
        return None
    connector_name = str(getattr(connector, "connector_name", "") or "").strip() or connector_id
    connector_owner = str(getattr(connector, "owner_username", "") or "").strip()
    provider_name = (
        f"本地连接器 · {connector_name} · {connector_owner}"
        if connector_owner
        else f"本地连接器 · {connector_name}"
    )
    return {
        "id": build_local_connector_provider_id(connector_id),
        "name": provider_name,
        "provider_type": "local-connector",
        "base_url": connector_base_url(connector),
        "models": models,
        "model_configs": [
            {
                "name": model_name,
                "model_type": DEFAULT_MODEL_TYPE,
            }
            for model_name in models
        ],
        "default_model": default_model or models[0],
        "enabled": True,
        "is_default": False,
        "connector_id": connector_id,
        "connector_name": connector_name,
        "connector_owner_username": connector_owner,
    }


async def _resolve_provider_runtime_target(
    provider_id: str,
    auth_payload: dict,
) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    connector_id = parse_local_connector_provider_id(provider_id)
    if connector_id:
        connector = _resolve_accessible_local_connector_for_llm(connector_id, auth_payload)
        if connector is None:
            raise HTTPException(404, "Local connector not found")
        provider = await _build_connector_chat_provider(connector)
        if provider is None:
            raise HTTPException(400, "当前本地连接器未配置可用模型")
        return "local_connector", provider, [provider]
    provider, providers = _pick_chat_provider(provider_id, auth_payload)
    return "provider", provider, providers


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
    normalized = [str(item or "").strip() for item in (enabled_tool_names or []) if str(item or "").strip()]
    allowed = set(normalized)
    if not allowed:
        return tools
    filtered = []
    for item in tools:
        tool_name = str(item.get("tool_name") or "").strip()
        if tool_name in allowed:
            filtered.append(item)
    return filtered


def _sort_tools_by_priority(tools: list[dict[str, Any]], tool_priority: list[str] | None) -> list[dict[str, Any]]:
    normalized = [str(item or "").strip() for item in (tool_priority or []) if str(item or "").strip()]
    if not normalized:
        return tools
    priority_map = {name: idx for idx, name in enumerate(normalized)}
    return sorted(
        tools,
        key=lambda item: (
            priority_map.get(str(item.get("tool_name") or "").strip(), 10**9),
            str(item.get("tool_name") or "").strip(),
        ),
    )


def _collect_runtime_tools(
    project_id: str,
    *,
    selected_employee_ids: list[str] | None,
    enabled_tool_names: list[str] | None,
    explicit_tool_filter: bool,
    tool_priority: list[str] | None,
) -> list[dict[str, Any]]:
    from services.dynamic_mcp_runtime import list_project_external_tools_runtime, list_project_proxy_tools_runtime

    internal_tools = list_project_proxy_tools_runtime(project_id, "")
    internal_tools = _filter_project_tools_by_employee_ids(internal_tools, selected_employee_ids)
    internal_tools = _filter_project_tools_by_names(
        internal_tools,
        enabled_tool_names,
        explicit_filter=explicit_tool_filter,
    )

    external_tools = list_project_external_tools_runtime(project_id)
    tools = internal_tools + external_tools
    tools = _sort_tools_by_priority(tools, list(tool_priority or []))
    return tools


def _summarize_effective_tools(
    tools: list[dict[str, Any]] | None,
    *,
    max_items: int = 24,
) -> tuple[list[dict[str, str]], int]:
    source_tools = tools if isinstance(tools, list) else []
    summarized: list[dict[str, str]] = []
    for item in source_tools[:max_items]:
        if not isinstance(item, dict):
            continue
        tool_name = str(item.get("tool_name") or "").strip()
        if not tool_name:
            continue
        module_type = str(item.get("module_type") or "").strip().lower()
        if tool_name.startswith("local_connector_"):
            source = "local_connector"
        elif module_type == "external_mcp_tool":
            source = "external_mcp"
        elif module_type == "system_mcp_tool":
            source = "system_mcp"
        elif bool(item.get("builtin")) or str(item.get("skill_id") or "").strip() == "__builtin__":
            source = "builtin"
        elif str(item.get("employee_id") or "").strip():
            source = "project_skill"
        else:
            source = "project_tool"
        summarized.append(
            {
                "tool_name": tool_name,
                "source": source,
                "description": str(item.get("description") or "").strip(),
            }
        )
    return summarized, len(source_tools)


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
    }
    for key, value in override.items():
        if key in req.model_fields_set and value is not None:
            merged[key] = value
    return _normalize_project_chat_settings(merged)


def _filter_project_tools_by_employee_ids(
    tools: list[dict[str, Any]],
    employee_ids: list[str] | None,
) -> list[dict[str, Any]]:
    normalized = [str(item or "").strip() for item in (employee_ids or []) if str(item or "").strip()]
    allowed = set(normalized)
    if not allowed:
        return tools
    filtered: list[dict[str, Any]] = []
    for item in tools:
        employee_id = str(item.get("employee_id") or "").strip()
        # builtin / global tool keeps empty employee_id
        if not employee_id or employee_id in allowed:
            filtered.append(item)
    return filtered


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
) -> list[dict[str, Any]]:
    workspace_info = ""
    effective_workspace_path = str(workspace_path or project.workspace_path or "").strip()
    if effective_workspace_path:
        workspace_info = f"\n\n当前项目工作区路径: {effective_workspace_path}\n请在此目录下进行代码开发和文件操作。"
    ai_entry_info = ""
    ai_entry_file = str(project.ai_entry_file or "").strip()
    if ai_entry_file:
        ai_entry_path = Path(ai_entry_file).expanduser()
        if effective_workspace_path and not ai_entry_path.is_absolute():
            resolved_entry_hint = str(Path(effective_workspace_path) / ai_entry_file)
            ai_entry_info = (
                f"\n\n当前项目 AI 入口文件: {ai_entry_file}"
                f"\n该入口文件相对于项目工作区，对应路径: {resolved_entry_hint}"
                "\n在开始分析、编码、调用工具或回答项目前，优先读取这个入口文件，并按其中约定理解项目规则、目录结构、实现约束和执行顺序。"
                "\n仅当该入口文件不存在、无法访问或信息不足时，再自行补充读取项目内其他相关规则文件。"
            )
        else:
            ai_entry_info = (
                f"\n\n当前项目 AI 入口文件: {ai_entry_file}"
                "\n在开始分析、编码、调用工具或回答项目前，优先读取这个入口文件，并按其中约定理解项目规则、目录结构、实现约束和执行顺序。"
                "\n仅当该入口文件不存在、无法访问或信息不足时，再自行补充读取项目内其他相关规则文件。"
            )

    tool_names = [t.get("tool_name", "") for t in (tools or [])] if tools else []
    tool_list_text = f"可用工具({len(tool_names)}个): {', '.join(tool_names)}" if tool_names else "当前无可用工具"

    base_prompt = (custom_system_prompt or "").strip()
    if not base_prompt:
        base_prompt = "你是项目开发助手。"
        base_prompt += "\n可按需调用工具检索最新项目上下文并完成用户请求。"
        base_prompt += "\n当用户询问项目信息、员工信息、规则、MCP 服务时，优先调用 search_project_context 再回答。"
        base_prompt += "\n当用户询问当前项目有哪些员工、成员、规则、工具或 MCP 能力时，不要先说无法获取；先调用 query_project_members、query_project_rules 或 search_project_context。"
        base_prompt += "\n当用户明确要完整项目配置、聊天配置、成员原始关系或单员工完整档案时，优先调用 get_project_detail 或 get_project_employee_detail。"

    style_hint = {
        "concise": "输出风格：简洁，避免冗长。",
        "balanced": "输出风格：平衡，先结论后关键步骤。",
        "detailed": "输出风格：详细，覆盖关键前提、步骤与风险。",
    }.get(str(answer_style or "concise").strip().lower(), "输出风格：简洁，避免冗长。")
    order_hint = "回答顺序：先给结论再给步骤。" if prefer_conclusion_first else "回答顺序：按自然推理顺序给出。"
    skill_resource_prompt = _build_skill_resource_prompt_block(
        skill_resource_directory,
    )
    coordination_mode = str(employee_coordination_mode or "auto").strip().lower()
    multi_employee_prompt = (
        _build_multi_employee_collaboration_prompt(selected_employees, tools)
        if coordination_mode == "auto"
        else ""
    )
    system_prompt = (
        f"{base_prompt}\n{workspace_info}{ai_entry_info}\n\n{tool_list_text}\n{order_hint}\n{style_hint}"
        f"{skill_resource_prompt}{multi_employee_prompt}"
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
        system_prompt += (
            "\n当前项目已绑定 UI 规则，这些规则优先级高于员工个人规则；涉及页面、交互、视觉表达时必须先遵循项目 UI 规则。"
            f"\nproject_ui_rule_titles={', '.join(project_ui_rule_titles) or '-'}。"
            f"\nproject_ui_rule_domains={', '.join(project_ui_rule_domains) or '-'}。"
            "\n项目 UI 规则正文：\n"
            + "\n".join(project_ui_rule_lines)
        )
    if selected_employee:
        rule_bindings = list(selected_employee.get("rule_bindings") or [])
        rule_titles = [str(item.get("title") or item.get("id") or "").strip() for item in rule_bindings]
        rule_titles = [item for item in rule_titles if item]
        rule_domains = _collect_rule_domains(rule_bindings)
        workflow = [str(item or "").strip() for item in (selected_employee.get("default_workflow") or []) if str(item or "").strip()]
        system_prompt += (
            f"\n当前执行员工：{selected_employee.get('name') or selected_employee.get('id')} "
            f"({selected_employee.get('id')})，"
            f"goal={str(selected_employee.get('goal') or '-').strip() or '-'}，"
            f"skills={', '.join(selected_employee.get('skill_names') or []) or '-'}，"
            f"rule_titles={', '.join(rule_titles) or '-'}，"
            f"rule_domains={', '.join(rule_domains) or '-'}。"
        )
        if workflow:
            system_prompt += f"\n默认工作流：{' -> '.join(workflow)}。"
        tool_usage_policy = str(selected_employee.get("tool_usage_policy") or "").strip()
        if tool_usage_policy:
            system_prompt += f"\n工具使用策略：{tool_usage_policy}"
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {
            "role": "system",
            "content": (
                f"当前项目: id={project.id}, name={project.name}, description={project.description or '-'}"
            ),
        },
        *_normalize_chat_history(history, limit=history_limit),
    ]
    normalized_images = _normalize_image_inputs(images)
    if normalized_images:
        content = [{"type": "text", "text": user_message or "请基于图片给建议。"}]
        for img in normalized_images:
            content.append({"type": "image_url", "image_url": {"url": img}})
        messages.append({"role": "user", "content": content})
    else:
        messages.append({"role": "user", "content": user_message})
    return messages


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
) -> list[dict[str, Any]]:
    base_prompt = (custom_system_prompt or "").strip()
    if not base_prompt:
        base_prompt = "你是通用 AI 助手。"
        base_prompt += "\n当前没有选中项目，请基于通用知识直接回答。"
        base_prompt += "\n如果用户问题依赖项目、代码库、员工、MCP 或规则配置，请明确提示需要先选择项目后再继续。"

    style_hint = {
        "concise": "输出风格：简洁，避免冗长。",
        "balanced": "输出风格：平衡，先结论后关键步骤。",
        "detailed": "输出风格：详细，覆盖关键前提、步骤与风险。",
    }.get(str(answer_style or "concise").strip().lower(), "输出风格：简洁，避免冗长。")
    order_hint = "回答顺序：先给结论再给步骤。" if prefer_conclusion_first else "回答顺序：按自然推理顺序给出。"
    skill_resource_prompt = _build_skill_resource_prompt_block(
        skill_resource_directory,
    )
    system_prompt = (
        f"{base_prompt}\n\n当前模式：通用对话（未选择项目）。\n{order_hint}\n{style_hint}"
        f"{skill_resource_prompt}"
    )
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        *_normalize_chat_history(history, limit=history_limit),
    ]
    normalized_images = _normalize_image_inputs(images)
    if normalized_images:
        content = [{"type": "text", "text": user_message or "请基于图片给建议。"}]
        for img in normalized_images:
            content.append({"type": "image_url", "image_url": {"url": img}})
        messages.append({"role": "user", "content": content})
    else:
        messages.append({"role": "user", "content": user_message})
    return messages


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
    return str(auth_payload.get("role") or "").strip().lower()


def _is_admin_like(auth_payload: dict) -> bool:
    role_id = _current_role_id(auth_payload)
    role = role_store.get(role_id)
    permissions = getattr(role, "permissions", [])
    resolved = resolve_role_permissions(permissions, role_id)
    return "*" in set(resolved)


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
    return _current_role_id(auth_payload) in _connector_llm_shared_with_roles(item)


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
    return str(project.workspace_path or "").strip()


def _resolve_local_connector_coding_tools(
    auth_payload: dict,
    settings: dict[str, Any],
    workspace_path: str,
) -> tuple[list[dict[str, Any]], Any | None, str]:
    _ = (auth_payload, settings, workspace_path)
    return [], None, ""


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
) -> list[str]:
    preferred = [
        str(item or "").strip()
        for item in (selected_employee_ids or [])
        if str(item or "").strip()
    ]
    member_ids = [
        str(getattr(member, "employee_id", "") or "").strip()
        for member in project_store.list_members(project_id)
    ]
    ordered_ids = preferred + member_ids
    result: list[str] = []
    seen: set[str] = set()
    for employee_id in ordered_ids:
        if not employee_id or employee_id in seen:
            continue
        if employee_store.get(employee_id) is None:
            continue
        seen.add(employee_id)
        result.append(employee_id)
    return result


def _save_project_chat_memory_snapshot(
    *,
    project_id: str,
    user_message: str,
    answer: str,
    selected_employee_ids: list[str] | None = None,
    source: str = "project-chat",
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

    target_ids = _resolve_project_memory_target_employee_ids(project_id, selected_employee_ids)
    if not target_ids:
        return

    project_name = str(getattr(project, "name", "") or project_id).strip() or "default"
    content = f"[用户问题] {question[:1200]}\n[最终结论] {conclusion[:2800]}"
    for employee_id in target_ids:
        try:
            memory_store.save(
                Memory(
                    id=memory_store.new_id(),
                    employee_id=employee_id,
                    type=MemoryType.PROJECT_CONTEXT,
                    content=content,
                    project_name=project_name,
                    importance=0.6,
                    scope=MemoryScope.EMPLOYEE_PRIVATE,
                    classification=Classification.INTERNAL,
                    purpose_tags=("auto-capture", "project-chat", source),
                )
            )
        except Exception:
            continue


@router.post("/chat/global")
async def chat_without_project(
    req: ProjectChatReq,
    auth_payload: dict = Depends(require_auth),
):
    # 预留接口：当前前端默认关闭“未选择项目时的普通对话”入口，
    # 但保留这条通用对话链路，后续如产品重新开放可直接复用。
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
    provider_mode, selected_provider, _ = await _resolve_provider_runtime_target(
        str(runtime_settings.get("provider_id") or ""),
        auth_payload,
    )
    provider_id = str(selected_provider.get("id") or "").strip()
    model_name = str(
        runtime_settings.get("model_name")
        or selected_provider.get("default_model")
        or (selected_provider.get("models") or [""])[0]
    ).strip()
    if not provider_id or not model_name:
        raise HTTPException(400, "未找到可用模型")

    effective_user_message = user_message
    if not effective_user_message and attachment_names:
        effective_user_message = (
            f"我上传了附件：{'、'.join(attachment_names)}。请先给我处理建议。"
        )
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
    )

    llm_service = get_llm_provider_service()
    try:
        if provider_mode == "local_connector":
            connector = _resolve_accessible_local_connector_for_llm(
                parse_local_connector_provider_id(provider_id),
                auth_payload,
            )
            if connector is None:
                raise HTTPException(404, "Local connector not found")
            result = await chat_completion_via_connector(
                connector,
                model_name=model_name,
                messages=messages,
                temperature=float(runtime_settings.get("temperature") or 0.1),
                max_tokens=_resolve_chat_max_tokens(runtime_settings.get("max_tokens")),
                timeout=120,
            )
        else:
            result = await llm_service.chat_completion(
                provider_id=provider_id,
                model_name=model_name,
                messages=messages,
                temperature=float(runtime_settings.get("temperature") or 0.1),
                max_tokens=_resolve_chat_max_tokens(runtime_settings.get("max_tokens")),
                timeout=120,
            )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"Global chat failed: {exc}") from exc

    answer = str(result.get("content") or "").strip() or "模型未返回有效内容。"
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
    if _is_admin_like(auth_payload):
        visible_projects = projects
    else:
        username = _current_username(auth_payload)
        visible_projects = []
        for item in projects:
            member = _get_project_user_member(item.id, username)
            if member is not None and bool(getattr(member, "enabled", True)):
                visible_projects.append(item)
    return {"projects": [_serialize_project(item, auth_payload) for item in visible_projects]}


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
    removed = project_chat_store.clear_messages(
        project_id,
        username,
        str(chat_session_id or "").strip(),
    )
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

        user_message = str(req.message or "").strip()
        assistant_message_id = str(req.assistant_message_id or "").strip()
        normalized_images = _normalize_image_inputs(req.images)
        attachment_names = [str(name or "").strip() for name in (req.attachment_names or []) if str(name or "").strip()]
        if not user_message and not normalized_images and not attachment_names:
            await websocket.send_json({"type": "error", "request_id": request_id, "message": "message is required"})
            return

        effective_user_message = user_message
        chat_session_id = str(req.chat_session_id or "").strip()
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
            if _is_project_meta_query(effective_user_message):
                direct_answer = _build_project_meta_reply(project, selected_employee, candidates)
                await websocket.send_json(
                    {
                        "type": "start",
                        "request_id": request_id,
                        "project_id": project_id,
                        "provider_id": "",
                        "model_name": "direct-project-meta",
                        "employee_id": employee_id_val,
                        "employee_name": str((selected_employee or {}).get("name") or ""),
                        "tools_enabled": False,
                    }
                )
                await websocket.send_json(
                    {
                        "type": "done",
                        "request_id": request_id,
                        "content": direct_answer,
                        "provider_id": "",
                        "model_name": "direct-project-meta",
                    }
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
                    selected_employee_ids=selected_employee_ids,
                    source="project-chat-ws-direct-meta",
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
                    {
                        "type": "start",
                        "request_id": request_id,
                        "project_id": project_id,
                        "provider_id": "",
                        "model_name": "direct-tool-probe",
                        "employee_id": employee_id_val,
                        "employee_name": str((selected_employee or {}).get("name") or ""),
                        "tools_enabled": False,
                    }
                )
                await websocket.send_json(
                    {
                        "type": "done",
                        "request_id": request_id,
                        "content": direct_answer,
                        "provider_id": "",
                        "model_name": "direct-tool-probe",
                    }
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
                    selected_employee_ids=selected_employee_ids,
                    source="project-chat-ws-direct-tool-probe",
                )
                return

            if _is_mcp_modules_query(effective_user_message):
                direct_answer = _build_mcp_modules_reply(project_id)
                await websocket.send_json(
                    {
                        "type": "start",
                        "request_id": request_id,
                        "project_id": project_id,
                        "provider_id": "",
                        "model_name": "direct-mcp-modules",
                        "employee_id": employee_id_val,
                        "employee_name": str((selected_employee or {}).get("name") or ""),
                        "tools_enabled": False,
                    }
                )
                await websocket.send_json(
                    {
                        "type": "done",
                        "request_id": request_id,
                        "content": direct_answer,
                        "provider_id": "",
                        "model_name": "direct-mcp-modules",
                    }
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
                    selected_employee_ids=selected_employee_ids,
                    source="project-chat-ws-direct-mcp-modules",
                )
                return

            provider_mode, selected_provider, _ = await _resolve_provider_runtime_target(
                str(runtime_settings.get("provider_id") or ""),
                auth_payload,
            )
            provider_id = str(selected_provider.get("id") or "")
            model_name = str(runtime_settings.get("model_name") or "").strip() or str(selected_provider.get("default_model") or "")
            if not model_name:
                raise ValueError("model_name is required")
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
                    {
                        "type": "start",
                        "request_id": request_id,
                        "project_id": project_id,
                        "provider_id": provider_id,
                        "model_name": model_name,
                        "chat_mode": "system",
                        "employee_id": employee_id_val,
                        "employee_name": str((selected_employee or {}).get("name") or ""),
                        "employee_ids": selected_employee_ids,
                        "tools_enabled": False,
                        "effective_tools": [],
                        "effective_tool_total": 0,
                    }
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
                        memory_source="project-chat-ws-media",
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
            )

        except Exception as exc:
            await websocket.send_json({"type": "error", "request_id": request_id, "message": str(exc)})
            return

        await websocket.send_json({
            "type": "start", "request_id": request_id, "project_id": project_id,
            "provider_id": provider_id, "model_name": model_name,
            "chat_mode": "system",
            "employee_id": employee_id_val,
            "employee_name": str((selected_employee or {}).get("name") or ""),
            "employee_ids": selected_employee_ids,
            "tools_enabled": bool(tools),
            "effective_tools": effective_tools,
            "effective_tool_total": effective_tool_total,
        })

        try:
            final_answer = ""
            stream_error = ""
            assistant_artifacts: list[dict[str, Any]] = []

            if provider_mode == "local_connector":
                connector = _resolve_accessible_local_connector_for_llm(
                    parse_local_connector_provider_id(provider_id),
                    auth_payload,
                )
                if connector is None:
                    raise ValueError("Local connector not found")
                llm_service = LocalConnectorLlmAdapter(connector)

            # 创建会话和编排器
            redis_client = await get_redis_client()
            conv_manager = ConversationManager(redis_client)
            session_id = await conv_manager.create_session(project_id, employee_id_val)
            orchestrator = AgentOrchestrator(
                llm_service,
                conv_manager,
                max_loops=int(runtime_settings.get("max_loop_rounds") or 20),
                max_tool_rounds=int(runtime_settings.get("max_tool_rounds") or 6),
                repeated_tool_call_threshold=int(runtime_settings.get("repeated_tool_call_threshold") or 2),
                tool_only_threshold=int(runtime_settings.get("tool_only_threshold") or 3),
                tool_budget_strategy=str(runtime_settings.get("tool_budget_strategy") or "finalize"),
                max_tool_calls_per_round=int(runtime_settings.get("max_tool_calls_per_round") or 6),
                tool_timeout_sec=int(runtime_settings.get("tool_timeout_sec") or 60),
                tool_retry_count=int(runtime_settings.get("tool_retry_count") or 0),
            )

            async for chunk_data in orchestrator.run(
                session_id=session_id,
                user_message=effective_user_message,
                tools=tools,
                provider_id=provider_id,
                model_name=model_name,
                temperature=temperature,
                max_tokens=max_tokens,
                project_id=project_id,
                employee_id=employee_id_val,
                cancel_event=cancel_event,
                messages=messages,
                local_connector=selected_local_connector,
                local_connector_workspace_path=effective_workspace_path,
                local_connector_sandbox_mode=local_connector_sandbox_mode,
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
                    selected_employee_ids=selected_employee_ids,
                    source="project-chat-ws",
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

    user_message = str(req.message or "").strip()
    assistant_message_id = str(req.assistant_message_id or "").strip()
    normalized_images = _normalize_image_inputs(req.images)
    attachment_names = [str(name or "").strip() for name in (req.attachment_names or []) if str(name or "").strip()]
    if not user_message and not normalized_images and not attachment_names:
        raise HTTPException(400, "message is required")

    effective_user_message = user_message
    chat_session_id = str(req.chat_session_id or "").strip()
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
    if _is_project_meta_query(effective_user_message):
        answer = _build_project_meta_reply(project, selected_employee, candidates)

        async def direct_event_stream() -> AsyncIterator[str]:
            yield _sse_payload(
                "message",
                {
                    "type": "start",
                    "project_id": project_id,
                    "provider_id": "",
                    "model_name": "direct-project-meta",
                    "employee_id": employee_id_val,
                    "employee_name": str((selected_employee or {}).get("name") or ""),
                    "tools_enabled": False,
                },
            )
            for part in _chunk_text(answer):
                yield _sse_payload("message", {"type": "delta", "content": part})
            yield _sse_payload(
                "message",
                {"type": "done", "content": answer, "provider_id": "", "model_name": "direct-project-meta"},
            )
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
                selected_employee_ids=selected_employee_ids,
                source="project-chat-sse-direct-meta",
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
            yield _sse_payload(
                "message",
                {
                    "type": "start",
                    "project_id": project_id,
                    "provider_id": "",
                    "model_name": "direct-tool-probe",
                    "employee_id": employee_id_val,
                    "employee_name": str((selected_employee or {}).get("name") or ""),
                    "tools_enabled": False,
                },
            )
            for part in _chunk_text(answer):
                yield _sse_payload("message", {"type": "delta", "content": part})
            yield _sse_payload(
                "message",
                {"type": "done", "content": answer, "provider_id": "", "model_name": "direct-tool-probe"},
            )
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
                selected_employee_ids=selected_employee_ids,
                source="project-chat-sse-direct-tool-probe",
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
            yield _sse_payload(
                "message",
                {
                    "type": "start",
                    "project_id": project_id,
                    "provider_id": "",
                    "model_name": "direct-mcp-modules",
                    "employee_id": employee_id_val,
                    "employee_name": str((selected_employee or {}).get("name") or ""),
                    "tools_enabled": False,
                },
            )
            for part in _chunk_text(answer):
                yield _sse_payload("message", {"type": "delta", "content": part})
            yield _sse_payload(
                "message",
                {"type": "done", "content": answer, "provider_id": "", "model_name": "direct-mcp-modules"},
            )
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
                selected_employee_ids=selected_employee_ids,
                source="project-chat-sse-direct-mcp-modules",
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

    provider_mode, selected_provider, _ = await _resolve_provider_runtime_target(
        str(runtime_settings.get("provider_id") or ""),
        auth_payload,
    )
    provider_id = str(selected_provider.get("id") or "")
    model_name = str(runtime_settings.get("model_name") or "").strip() or str(selected_provider.get("default_model") or "")
    if not model_name:
        raise HTTPException(400, "model_name is required")

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
                {
                    "type": "start",
                    "project_id": project_id,
                    "provider_id": provider_id,
                    "model_name": model_name,
                    "employee_id": str((selected_employee or {}).get("id") or ""),
                    "employee_name": str((selected_employee or {}).get("name") or ""),
                    "employee_ids": selected_employee_ids,
                    "tools_enabled": False,
                    "effective_tools": [],
                    "effective_tool_total": 0,
                },
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
                    memory_source="project-chat-sse-media",
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
    )

    async def event_stream() -> AsyncIterator[str]:
        yield _sse_payload(
            "message",
            {
                "type": "start",
                "project_id": project_id,
                "provider_id": provider_id,
                "model_name": model_name,
                "employee_id": str((selected_employee or {}).get("id") or ""),
                "employee_name": str((selected_employee or {}).get("name") or ""),
                "employee_ids": selected_employee_ids,
                "tools_enabled": bool(tools),
                "effective_tools": effective_tools,
                "effective_tool_total": effective_tool_total,
            },
        )
        try:
            if provider_mode == "local_connector":
                connector = _resolve_accessible_local_connector_for_llm(
                    parse_local_connector_provider_id(provider_id),
                    auth_payload,
                )
                if connector is None:
                    raise HTTPException(404, "Local connector not found")
                llm_service_runtime = LocalConnectorLlmAdapter(connector)
            else:
                llm_service_runtime = llm_service

            redis_client = await get_redis_client()
            conv_manager = ConversationManager(redis_client)
            session_id = await conv_manager.create_session(project_id, employee_id_val)
            orchestrator = AgentOrchestrator(
                llm_service_runtime,
                conv_manager,
                max_loops=int(runtime_settings.get("max_loop_rounds") or 20),
                max_tool_rounds=int(runtime_settings.get("max_tool_rounds") or 6),
                repeated_tool_call_threshold=int(runtime_settings.get("repeated_tool_call_threshold") or 2),
                tool_only_threshold=int(runtime_settings.get("tool_only_threshold") or 3),
                tool_budget_strategy=str(runtime_settings.get("tool_budget_strategy") or "finalize"),
                max_tool_calls_per_round=int(runtime_settings.get("max_tool_calls_per_round") or 6),
                tool_timeout_sec=int(runtime_settings.get("tool_timeout_sec") or 60),
                tool_retry_count=int(runtime_settings.get("tool_retry_count") or 0),
            )

            final_answer = ""
            stream_error = ""
            assistant_artifacts: list[dict[str, Any]] = []
            cancel_event = asyncio.Event()
            async for chunk_data in orchestrator.run(
                session_id=session_id,
                user_message=effective_user_message,
                tools=tools,
                provider_id=provider_id,
                model_name=model_name,
                temperature=temperature,
                max_tokens=max_tokens,
                project_id=project_id,
                employee_id=employee_id_val,
                cancel_event=cancel_event,
                messages=messages,
                local_connector=selected_local_connector,
                local_connector_workspace_path=effective_workspace_path,
                local_connector_sandbox_mode=local_connector_sandbox_mode,
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
                    selected_employee_ids=selected_employee_ids,
                    source="project-chat-sse",
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
2. 再调用 `recall_project_memory` 检索相关记忆，优先传 `project_name="{project.name}"`。
3. 每次有效对话都必须记录到项目记忆；当前宿主系统对项目聊天默认自动记录问答快照，如当前入口未覆盖自动记录链路，则在本轮结束后立即调用 `save_project_memory` 补记。
4. 在决定是否需要多人协作前，先把本项目手册与相关员工手册视为协作基线：AI 需结合任务目标、规则、技能和工具，自主判断单人主责还是多人协作，不预设固定行业角色分工。
5. 遇到页面、交互、视觉表达类任务时，先检查本项目绑定的 UI 规则；这些规则优先级高于员工个人规则。
6. 开始实现或排查前，调用 `query_project_rules` 和 `list_project_proxy_tools` 搜索匹配的规则与技能；`query_project_rules` 返回的规则中，项目级 UI 规则应优先遵循。若任务需要项目内多员工自动协作，可优先调用 `execute_project_collaboration`。
7. 锁定匹配项后，再调用 `invoke_project_skill_tool`，必要时补 `employee_id` 消歧；若采用多人协作，先明确负责人、子任务边界和结果交接。
8. 如需沉淀结构化结论、排查经验或关键决策，在自动记录之外显式调用 `save_project_memory` 追加一条可复用记忆。
9. 发现规则缺口、工具异常或稳定性问题时，调用 `submit_project_feedback_bug`。

### 记忆保存示例
```json
save_project_memory({{
  "employee_id": "<项目成员ID>",
  "content": "问题：<问题摘要>\\n结论：<最终方案>\\n关键决策：<需要沉淀的信息>",
  "project_name": "{project.name}"
}})
```

## 项目成员与员工使用手册

{employee_templates_text}

## 项目级 UI 规则（优先级高于员工个人规则）

- 页面、交互、视觉表达相关任务，先遵循这里的项目级 UI 规则，再参考员工个人规则。
- 若项目级 UI 规则与员工个人规则冲突，以项目级 UI 规则为准。

{project_ui_rules_text}

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
- **`recall_project_memory`**：检索项目记忆，优先传 `project_name="{project.name}"`。
- **`save_project_memory`**：手动补记项目级结论、经验和关键决策；当当前入口未自动记录或需要追加结构化沉淀时必须调用。
- **`query_project_rules`**：按关键词查询项目规则，返回项目级 UI 规则与成员规则；页面/交互类任务先看项目级 UI 规则，最终以具体规则正文为准。
- **`list_project_proxy_tools`**：列出项目可调用的成员技能工具。
- **`execute_project_collaboration`**：输入用户原始任务，由 AI 基于项目手册、员工手册、规则和工具，自主判断是否需要多人协作并生成协作步骤。
- **`invoke_project_skill_tool`**：调用项目成员技能，必要时补 `employee_id` 消歧。
- **`submit_project_feedback_bug`**：提交结构化反馈工单。

## 推荐工作流

```text
1. 获取项目上下文 / 成员信息 → get_project_runtime_context 或 list_project_members
2. 记忆检索 → recall_project_memory
3. 每次对话记录 → 默认自动记录；未覆盖入口则立刻 save_project_memory 补记
4. 结合项目手册与员工手册，自主判断单人主责还是多人协作；多人任务优先考虑 execute_project_collaboration
5. 先检查项目级 UI 规则，再搜索匹配的成员规则与技能 → query_project_rules + list_project_proxy_tools
6. 锁定匹配项后再调用技能 → execute_project_collaboration 或 invoke_project_skill_tool
7. 结构化沉淀结论 → save_project_memory
8. 反馈闭环 → submit_project_feedback_bug
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
- 先检索记忆，再检索规则，再决定是否调用技能。
- 项目级 UI 规则优先于员工个人规则，尤其是页面、交互、视觉表达类任务。
- 每次有效对话都要留下项目记忆；自动记录未覆盖时，必须手动补记。
- 结构化结论和关键决策建议额外补一条高质量记忆，便于后续复用。
- 不要把领域名直接当作规则正文。

### 事实边界
- 当前宿主系统已实现项目聊天自动记忆快照；若当前入口未接入该链路，仍需显式调用 `save_project_memory`。
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
