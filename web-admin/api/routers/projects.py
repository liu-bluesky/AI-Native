"""项目管理路由"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import asdict, replace
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool
import asyncio
from services.agent_orchestrator import AgentOrchestrator
from services.conversation_manager import ConversationManager
from core.redis_client import get_redis_client

# from ai_decision import ai_decide_action, execute_db_query, recommend_better_project  # 已废弃
from core.auth import decode_token
from core.deps import employee_store, external_mcp_store, is_admin_like, local_connector_store, project_chat_store, project_material_store, project_store, require_auth, role_store, system_config_store, user_store
from services.feedback_service import get_feedback_service
from services.local_connector_service import (
    LocalConnectorLlmAdapter,
    build_local_connector_provider_id,
    chat_completion_via_connector,
    connector_base_url,
    list_connector_llm_models,
    parse_local_connector_provider_id,
)
from models.requests import (
    ProjectAiEntryFileUpdateReq,
    ProjectChatHistoryTruncateReq,
    ProjectChatReq,
    ProjectChatSettingsUpdateReq,
    ProjectCreateReq,
    ProjectMaterialAssetCreateReq,
    ProjectMaterialAssetUpdateReq,
    ProjectMemberAddReq,
    ProjectUserAddReq,
    ProjectUpdateReq,
    WorkspaceDirectoryPickReq,
    WorkspaceFilePickReq,
)
from stores.json.project_chat_store import ProjectChatMessage
from stores.json.project_material_store import ProjectMaterialAsset
from stores.json.project_store import ProjectConfig, ProjectMember, ProjectUserMember, _now_iso
from core.role_permissions import has_permission, resolve_role_permissions
from stores.mcp_bridge import Classification, Memory, MemoryScope, MemoryType, memory_store, rule_store, skill_store

router = APIRouter(prefix="/api/projects", dependencies=[Depends(require_auth)])


_PROJECT_CHAT_SETTINGS_DEFAULTS: dict[str, Any] = {
    "chat_mode": "system",
    "local_connector_id": "",
    "connector_workspace_path": "",
    "connector_sandbox_mode": "workspace-write",
    "connector_sandbox_mode_explicit": False,
    "selected_employee_id": "",
    "selected_employee_ids": [],
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
}

_PROJECT_TYPE_VALUES = {"image", "storyboard_video", "mixed"}
_PROJECT_TYPE_LABELS = {
    "image": "图片项目",
    "storyboard_video": "分镜视频项目",
    "mixed": "综合项目",
}
_PROJECT_MATERIAL_ASSET_TYPES = {"image", "storyboard", "video"}
_PROJECT_MATERIAL_GROUP_LABELS = {
    "image": "图片",
    "storyboard_video": "分镜 / 视频",
}
_PROJECT_MATERIAL_ASSET_LABELS = {
    "image": "图片",
    "storyboard": "分镜",
    "video": "视频",
}
_PROJECT_MATERIAL_STATUS_VALUES = {"draft", "ready", "archived"}
_PROJECT_MATERIAL_STATUS_LABELS = {
    "draft": "草稿",
    "ready": "可用",
    "archived": "归档",
}


def _serialize_project(project: ProjectConfig) -> dict:
    data = asdict(project)
    data.pop("chat_settings", None)
    normalized_type = _normalize_project_type(getattr(project, "type", "mixed"))
    data["type"] = normalized_type
    data["type_label"] = _PROJECT_TYPE_LABELS.get(normalized_type, _PROJECT_TYPE_LABELS["mixed"])
    data["member_count"] = len(project_store.list_members(project.id))
    data["user_count"] = len(project_store.list_user_members(project.id))
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


def _normalize_material_url(value: Any, *, limit: int = 20000) -> str:
    return str(value or "").strip()[:limit]


def _normalize_material_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _serialize_project_material_asset(asset: ProjectMaterialAsset) -> dict[str, Any]:
    payload = asdict(asset)
    payload["asset_type_label"] = _PROJECT_MATERIAL_ASSET_LABELS.get(asset.asset_type, asset.asset_type)
    payload["group_type_label"] = _PROJECT_MATERIAL_GROUP_LABELS.get(asset.group_type, asset.group_type)
    payload["status_label"] = _PROJECT_MATERIAL_STATUS_LABELS.get(asset.status, asset.status)
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


def _normalize_chat_image_artifacts(values: Any) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        return []
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for index, item in enumerate(values, start=1):
        if not isinstance(item, dict):
            continue
        preview_url = _normalize_material_url(
            item.get("preview_url") or item.get("previewUrl") or item.get("thumbnail_url") or item.get("thumbnailUrl"),
        )
        content_url = _normalize_material_url(
            item.get("content_url")
            or item.get("contentUrl")
            or item.get("image_url")
            or item.get("imageUrl")
            or item.get("url"),
        )
        if not preview_url:
            preview_url = content_url
        if not content_url:
            content_url = preview_url
        if not preview_url and not content_url:
            continue
        artifact_key = f"{preview_url}||{content_url}"
        if artifact_key in seen:
            continue
        seen.add(artifact_key)
        metadata = _normalize_material_mapping(item.get("metadata"))
        result.append(
            {
                "asset_type": "image",
                "title": _normalize_material_text(
                    item.get("title") or f"AI 生成图片 #{index}",
                    limit=120,
                ) or f"AI 生成图片 #{index}",
                "summary": _normalize_material_text(item.get("summary"), limit=1000),
                "preview_url": preview_url,
                "content_url": content_url,
                "mime_type": _guess_material_image_mime_type(
                    content_url or preview_url,
                    item.get("mime_type") or item.get("mimeType"),
                ),
                "metadata": metadata,
            }
        )
    return result


def _merge_chat_image_artifacts(
    current: list[dict[str, Any]] | None,
    incoming: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    return _normalize_chat_image_artifacts([*(current or []), *(incoming or [])])


def _collect_chat_image_urls(values: list[dict[str, Any]] | None) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for item in values or []:
        for candidate in (
            str((item or {}).get("preview_url") or "").strip(),
            str((item or {}).get("content_url") or "").strip(),
        ):
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            urls.append(candidate)
    return urls


def _save_chat_image_artifacts_to_materials(
    *,
    project_id: str,
    username: str,
    chat_session_id: str,
    source_message_id: str,
    artifacts: list[dict[str, Any]] | None,
    tool_name: str = "",
) -> list[ProjectMaterialAsset]:
    normalized_artifacts = _normalize_chat_image_artifacts(artifacts)
    if not normalized_artifacts:
        return []
    existing_items = project_material_store.list_by_project(project_id)
    existing_keys: set[str] = set()
    for item in existing_items:
        if getattr(item, "asset_type", "") != "image":
            continue
        metadata = item.metadata if isinstance(item.metadata, dict) else {}
        artifact_key = str(metadata.get("artifact_key") or "").strip()
        if artifact_key:
            existing_keys.add(artifact_key)
    saved: list[ProjectMaterialAsset] = []
    for artifact in normalized_artifacts:
        preview_url = str(artifact.get("preview_url") or "").strip()
        content_url = str(artifact.get("content_url") or "").strip()
        artifact_key = "||".join(
            [
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
            asset_type="image",
            group_type="image",
            title=_normalize_material_text(
                artifact.get("title") or "AI 生成图片",
                limit=120,
            ) or "AI 生成图片",
            summary=_normalize_material_text(artifact.get("summary"), limit=1000),
            source_message_id=_normalize_material_text(source_message_id, limit=120),
            source_chat_session_id=_normalize_material_text(chat_session_id, limit=120),
            source_username=_normalize_material_text(username, limit=120),
            created_by=_normalize_material_text(username, limit=120),
            preview_url=_normalize_material_url(preview_url),
            content_url=_normalize_material_url(content_url),
            mime_type=_normalize_material_text(
                artifact.get("mime_type")
                or _guess_material_image_mime_type(content_url or preview_url),
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
        package_path = Path(__file__).resolve().parents[3] / package_path
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


def _build_project_chat_messages(
    project: ProjectConfig,
    user_message: str,
    history: list[dict] | None,
    images: list[str] | None = None,
    selected_employee: dict[str, Any] | None = None,
    tools: list[dict] | None = None,
    custom_system_prompt: str | None = None,
    history_limit: int = 20,
    answer_style: str = "concise",
    prefer_conclusion_first: bool = True,
    workspace_path: str = "",
    skill_resource_directory: str = "",
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
    system_prompt = (
        f"{base_prompt}\n{workspace_info}{ai_entry_info}\n\n{tool_list_text}\n{order_hint}\n{style_hint}"
        f"{skill_resource_prompt}"
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
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{1,63}", username):
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
    if _is_admin_like(auth_payload):
        return project
    username = _current_username(auth_payload)
    member = _get_project_user_member(project_id, username)
    if member is None:
        raise HTTPException(403, f"Project manage access denied: {project_id}")
    member_role = str(getattr(member, "role", "") or "").strip().lower()
    if member_role != "owner":
        raise HTTPException(403, f"Project manage access denied: {project_id}")
    return project


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
    return {"projects": [_serialize_project(item) for item in visible_projects]}


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
    project = ProjectConfig(
        id=project_store.new_id(),
        name=str(req.name or "").strip(),
        description=req.description,
        type=_normalize_project_type(req.type),
        mcp_instruction=_normalize_project_mcp_instruction_for_save(req.mcp_instruction),
        workspace_path=_normalize_workspace_path_for_save(req.workspace_path),
        ai_entry_file=_normalize_ai_entry_file_for_save(req.ai_entry_file),
        mcp_enabled=req.mcp_enabled,
        feedback_upgrade_enabled=req.feedback_upgrade_enabled,
    )
    if not project.name:
        raise HTTPException(400, "name is required")
    project_store.save(project)
    creator_username = _normalize_project_username(_current_username(auth_payload))
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
    return {"status": "created", "project": _serialize_project(project)}


@router.get("/{project_id}")
async def get_project(project_id: str, auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "menu.projects")
    project = _ensure_project_access(project_id, auth_payload)
    return {"project": _serialize_project(project)}


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
    if not project_material_store.delete(project_id, asset_id):
        raise HTTPException(404, f"Material asset {asset_id} not found")
    return {"status": "deleted", "asset_id": asset_id}


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


def _apply_project_update(project_id: str, req: ProjectUpdateReq) -> dict:
    project = project_store.get(project_id)
    if project is None:
        raise HTTPException(404, f"Project {project_id} not found")
    updates = req.model_dump(exclude_none=True)
    if not updates:
        return {"status": "no_change", "project": _serialize_project(project)}
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
    updates["updated_at"] = _now_iso()
    updated = replace(project, **updates)
    project_store.save(updated)
    if "feedback_upgrade_enabled" in updates:
        _sync_feedback_project_flag(updated.id, bool(updated.feedback_upgrade_enabled))
    return {"status": "updated", "project": _serialize_project(updated)}


@router.put("/{project_id}")
async def update_project(project_id: str, req: ProjectUpdateReq, auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_manage_access(project_id, auth_payload)
    return _apply_project_update(project_id, req)


@router.patch("/{project_id}")
async def patch_project(project_id: str, req: ProjectUpdateReq, auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "menu.projects")
    _ensure_project_manage_access(project_id, auth_payload)
    return _apply_project_update(project_id, req)


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
    can_manage = _is_admin_like(auth_payload) or str(
        getattr(_get_project_user_member(project_id, _current_username(auth_payload)), "role", "") or ""
    ).strip().lower() == "owner"
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
                tools=tools,
                custom_system_prompt=_resolve_default_chat_system_prompt(runtime_settings.get("system_prompt")),
                history_limit=int(runtime_settings.get("history_limit") or 20),
                answer_style=str(runtime_settings.get("answer_style") or "concise"),
                prefer_conclusion_first=bool(runtime_settings.get("prefer_conclusion_first", True)),
                workspace_path=effective_workspace_path,
                skill_resource_directory=req.skill_resource_directory,
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
            from services.llm_provider_service import get_llm_provider_service

            final_answer = ""
            stream_error = ""
            assistant_artifacts: list[dict[str, Any]] = []
            llm_service = get_llm_provider_service()

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
                    artifact_batch = _normalize_chat_image_artifacts(outgoing.get("artifacts"))
                    if artifact_batch:
                        _save_chat_image_artifacts_to_materials(
                            project_id=project_id,
                            username=username,
                            chat_session_id=chat_session_id,
                            source_message_id=assistant_message_id,
                            artifacts=artifact_batch,
                            tool_name=str(outgoing.get("tool_name") or "").strip(),
                        )
                        assistant_artifacts = _merge_chat_image_artifacts(
                            assistant_artifacts,
                            artifact_batch,
                        )
                        outgoing["artifacts"] = artifact_batch
                        outgoing["images"] = _collect_chat_image_urls(artifact_batch)
                    else:
                        outgoing["artifacts"] = []
                        outgoing["images"] = []
                if event_type == "done":
                    assistant_artifacts = _merge_chat_image_artifacts(
                        assistant_artifacts,
                        _normalize_chat_image_artifacts(outgoing.get("artifacts")),
                    )
                    outgoing["artifacts"] = assistant_artifacts
                    outgoing["images"] = _collect_chat_image_urls(assistant_artifacts)
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
                assistant_images = _collect_chat_image_urls(assistant_artifacts)
                persisted_answer = (
                    final_answer
                    or ("已生成图片，请查看下方结果。" if assistant_images else "模型未返回有效内容。")
                )
                _append_chat_record(
                    project_id=project_id,
                    username=username,
                    role="assistant",
                    content=persisted_answer,
                    message_id=assistant_message_id,
                    chat_session_id=chat_session_id,
                    images=assistant_images,
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

    llm_service = get_llm_provider_service()
    messages = _build_project_chat_messages(
        project,
        effective_user_message,
        req.history,
        normalized_images,
        selected_employee=selected_employee,
        tools=tools,
        custom_system_prompt=_resolve_default_chat_system_prompt(runtime_settings.get("system_prompt")),
        history_limit=int(runtime_settings.get("history_limit") or 20),
        answer_style=str(runtime_settings.get("answer_style") or "concise"),
        prefer_conclusion_first=bool(runtime_settings.get("prefer_conclusion_first", True)),
        workspace_path=effective_workspace_path,
        skill_resource_directory=req.skill_resource_directory,
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
                    artifact_batch = _normalize_chat_image_artifacts(outgoing.get("artifacts"))
                    if artifact_batch:
                        _save_chat_image_artifacts_to_materials(
                            project_id=project_id,
                            username=username,
                            chat_session_id=chat_session_id,
                            source_message_id=assistant_message_id,
                            artifacts=artifact_batch,
                            tool_name=str(outgoing.get("tool_name") or "").strip(),
                        )
                        assistant_artifacts = _merge_chat_image_artifacts(
                            assistant_artifacts,
                            artifact_batch,
                        )
                        outgoing["artifacts"] = artifact_batch
                        outgoing["images"] = _collect_chat_image_urls(artifact_batch)
                    else:
                        outgoing["artifacts"] = []
                        outgoing["images"] = []
                if event_type == "done":
                    assistant_artifacts = _merge_chat_image_artifacts(
                        assistant_artifacts,
                        _normalize_chat_image_artifacts(outgoing.get("artifacts")),
                    )
                    outgoing["artifacts"] = assistant_artifacts
                    outgoing["images"] = _collect_chat_image_urls(assistant_artifacts)
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
                assistant_images = _collect_chat_image_urls(assistant_artifacts)
                persisted_answer = (
                    final_answer
                    or ("已生成图片，请查看下方结果。" if assistant_images else "模型未返回有效内容。")
                )
                _append_chat_record(
                    project_id=project_id,
                    username=username,
                    role="assistant",
                    content=persisted_answer,
                    message_id=assistant_message_id,
                    chat_session_id=chat_session_id,
                    images=assistant_images,
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
4. 开始实现或排查前，调用 `query_project_rules` 和 `list_project_proxy_tools` 搜索匹配的规则与技能。
5. 锁定匹配项后，再调用 `invoke_project_skill_tool`，必要时补 `employee_id` 消歧。
6. 如需沉淀结构化结论、排查经验或关键决策，在自动记录之外显式调用 `save_project_memory` 追加一条可复用记忆。
7. 发现规则缺口、工具异常或稳定性问题时，调用 `submit_project_feedback_bug`。

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

## 项目共享技能索引（写手册时不要只写技能名，需结合下面信息展开）

{skills_text}

## 项目规则领域概览（仅用于快速筛选，不可替代具体规则）

{domains_text}

## 核心工具说明

- **`get_project_usage_guide`**：获取项目 MCP 使用说明与推荐调用顺序。
- **`get_project_manual`**：直接获取项目使用手册正文；也可读取 `project://<project_id>/manual` 资源。
- **`list_project_members`**：列出项目成员，用于先确定可协作员工。
- **`get_project_profile`**：读取项目基础配置、工作区和入口文件信息。
- **`get_project_runtime_context`**：查看项目运行时上下文、成员、规则和技能规模。
- **`recall_project_memory`**：检索项目记忆，优先传 `project_name="{project.name}"`。
- **`save_project_memory`**：手动补记项目级结论、经验和关键决策；当当前入口未自动记录或需要追加结构化沉淀时必须调用。
- **`query_project_rules`**：按关键词查询项目规则，最终以具体规则正文为准。
- **`list_project_proxy_tools`**：列出项目可调用的成员技能工具。
- **`invoke_project_skill_tool`**：调用项目成员技能，必要时补 `employee_id` 消歧。
- **`submit_project_feedback_bug`**：提交结构化反馈工单。

## 推荐工作流

```text
1. 获取项目上下文 / 成员信息 → get_project_runtime_context 或 list_project_members
2. 记忆检索 → recall_project_memory
3. 每次对话记录 → 默认自动记录；未覆盖入口则立刻 save_project_memory 补记
4. 先搜索匹配的规则与技能 → query_project_rules + list_project_proxy_tools
5. 锁定匹配项后再调用技能 → invoke_project_skill_tool
6. 结构化沉淀结论 → save_project_memory
7. 反馈闭环 → submit_project_feedback_bug
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
- 根据任务类型选择合适员工。
- 跨端任务拆分给相关员工分别处理，再做汇总。

### 记忆与规则
- 先检索记忆，再检索规则，再决定是否调用技能。
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
