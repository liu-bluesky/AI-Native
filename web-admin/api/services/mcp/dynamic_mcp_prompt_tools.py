"""Shared prompt preview/sync helpers for MCP tools."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Any

from core.deps import project_store

PROMPT_PREVIEW_TOOL_NAME = "get_query_mcp_cli_prompt_preview"
PROMPT_SYNC_TOOL_NAME = "sync_query_mcp_cli_prompt_to_local_file"


def _normalize_text(value: Any, max_length: int = 1000) -> str:
    text = str(value or "").strip()
    if max_length > 0:
        return text[:max_length]
    return text


def prompt_preview_tool_descriptor(employee_id: str = "") -> dict[str, Any]:
    employee_id_value = _normalize_text(employee_id, 120)
    return {
        "tool_name": PROMPT_PREVIEW_TOOL_NAME,
        "employee_id": employee_id_value,
        "base_tool_name": PROMPT_PREVIEW_TOOL_NAME,
        "scoped_tool_name": PROMPT_PREVIEW_TOOL_NAME,
        "skill_id": "__builtin__",
        "entry_name": PROMPT_PREVIEW_TOOL_NAME,
        "script_type": "builtin",
        "description": "获取与统一 MCP 接入弹窗“展开引导提示词预览”一致的 CLI 引导提示词。",
        "builtin": True,
        "parameters_schema": {
            "type": "object",
            "properties": {
                "chat_session_id": {
                    "type": "string",
                    "description": "可选，当前聊天会话 ID；项目 MCP 中未传时使用当前项目会话上下文。",
                },
                "clarity_threshold": {
                    "type": "integer",
                    "description": "可选，清晰度确认阈值，范围 1-5，默认 3。",
                },
            },
            "required": [],
        },
    }


def prompt_sync_tool_descriptor(employee_id: str = "") -> dict[str, Any]:
    employee_id_value = _normalize_text(employee_id, 120)
    return {
        "tool_name": PROMPT_SYNC_TOOL_NAME,
        "employee_id": employee_id_value,
        "base_tool_name": PROMPT_SYNC_TOOL_NAME,
        "scoped_tool_name": PROMPT_SYNC_TOOL_NAME,
        "skill_id": "__builtin__",
        "entry_name": PROMPT_SYNC_TOOL_NAME,
        "script_type": "builtin",
        "description": "把服务器渲染出的 runtime.cli_prompt 写入当前项目工作区内的目标文件。",
        "builtin": True,
        "parameters_schema": {
            "type": "object",
            "properties": {
                "chat_session_id": {
                    "type": "string",
                    "description": "可选，当前聊天会话 ID；项目 MCP 中未传时使用当前项目会话上下文。",
                },
                "workspace_path": {
                    "type": "string",
                    "description": "必填，当前客户端项目工作区绝对路径。",
                },
                "target_file": {
                    "type": "string",
                    "description": "可选，要写入的工作区内相对路径，默认 AGENTS.md。",
                },
                "backup": {
                    "type": "boolean",
                    "description": "可选，覆盖前是否备份已存在文件，默认 true。",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "可选，只预演不写入文件，默认 false。",
                },
                "clarity_threshold": {
                    "type": "integer",
                    "description": "可选，清晰度确认阈值，范围 1-5，默认 3。",
                },
            },
            "required": ["workspace_path"],
        },
    }


def project_prompt_tool_descriptors(employee_id: str = "") -> list[dict[str, Any]]:
    return [
        prompt_preview_tool_descriptor(employee_id),
        prompt_sync_tool_descriptor(employee_id),
    ]


def get_query_mcp_cli_prompt_preview_runtime(
    project_id: str = "",
    chat_session_id: str = "",
    clarity_threshold: int = 3,
) -> dict[str, Any]:
    project_id_value = _normalize_text(project_id, 120)
    chat_session_id_value = _normalize_text(chat_session_id, 120)
    try:
        threshold_value = max(1, min(5, int(clarity_threshold or 3)))
    except (TypeError, ValueError):
        threshold_value = 3
    if project_id_value and project_store.get(project_id_value) is None:
        return {"error": f"Project {project_id_value} not found"}
    from routers.projects import _build_query_mcp_cli_prompt

    rendered = _build_query_mcp_cli_prompt(
        project_id=project_id_value,
        chat_session_id=chat_session_id_value,
        clarity_confirm_threshold=threshold_value,
    )
    return {
        "status": "preview",
        "project_id": project_id_value,
        "chat_session_id": chat_session_id_value,
        "template_source": "system_config.query_mcp_bootstrap_prompt_template",
        "rendered_field": "runtime.cli_prompt",
        "rendered_cli_prompt": rendered,
        "content_hash": hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
    }


def sync_query_mcp_cli_prompt_to_local_file_runtime(
    project_id: str = "",
    chat_session_id: str = "",
    workspace_path: str = "",
    target_file: str = "AGENTS.md",
    backup: bool = True,
    dry_run: bool = False,
    clarity_threshold: int = 3,
) -> dict[str, Any]:
    preview = get_query_mcp_cli_prompt_preview_runtime(
        project_id=project_id,
        chat_session_id=chat_session_id,
        clarity_threshold=clarity_threshold,
    )
    if preview.get("error"):
        return preview
    workspace_value = _normalize_text(workspace_path, 2000)
    if not workspace_value:
        return {"status": "blocked", "reason": "workspace_path is required"}
    root = Path(workspace_value).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        return {"status": "blocked", "reason": "workspace_path does not exist or is not a directory"}
    target_value = _normalize_text(target_file, 1000) or "AGENTS.md"
    target_path = (root / target_value).resolve()
    try:
        target_path.relative_to(root)
    except ValueError:
        return {"status": "blocked", "reason": "target_file must be inside workspace_path"}
    rendered = str(preview.get("rendered_cli_prompt") or "")
    existing = ""
    if target_path.exists():
        if not target_path.is_file():
            return {"status": "blocked", "reason": "target_file is not a file"}
        try:
            existing = target_path.read_text(encoding="utf-8")
        except OSError as exc:
            return {"status": "blocked", "reason": f"failed to read target_file: {exc}"}
    changed = existing != rendered
    if not changed:
        return {
            **preview,
            "status": "no_change",
            "target_file": str(target_path),
            "backup_file": "",
            "changed": False,
        }
    if dry_run:
        return {
            **preview,
            "status": "dry_run",
            "target_file": str(target_path),
            "backup_file": "",
            "changed": True,
        }
    backup_file = ""
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if backup and target_path.exists():
            backup_path = target_path.with_name(
                f"{target_path.name}.bak.{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
            )
            backup_path.write_text(existing, encoding="utf-8")
            backup_file = str(backup_path)
        target_path.write_text(rendered, encoding="utf-8")
    except OSError as exc:
        return {"status": "blocked", "reason": f"failed to write target_file: {exc}"}
    return {
        **preview,
        "status": "synced",
        "target_file": str(target_path),
        "backup_file": backup_file,
        "changed": True,
    }
