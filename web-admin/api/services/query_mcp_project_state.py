from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.deps import project_store

_STATE_DIR = Path(".ai-employee") / "query-mcp"
_TERMINAL_STATUSES = {"done", "completed", "archived", "closed"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(value: object, limit: int = 400) -> str:
    return str(value or "").strip()[:limit]


def _safe_name(value: object, fallback: str = "unknown") -> str:
    normalized = _normalize_text(value, 200)
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", normalized).strip("._")
    return cleaned or fallback


def _resolve_project_workspace_path(project_id: str = "", workspace_path: str = "") -> str:
    direct = _normalize_text(workspace_path, 1000)
    if direct:
        candidate = Path(direct).expanduser()
        if candidate.is_dir():
            return str(candidate)
    project_id_value = _normalize_text(project_id, 120)
    if not project_id_value:
        return ""
    try:
        project = project_store.get(project_id_value)
    except Exception:
        project = None
    if project is None:
        return ""
    chat_settings = getattr(project, "chat_settings", {}) or {}
    connector_workspace_path = _normalize_text(
        chat_settings.get("connector_workspace_path"),
        1000,
    )
    if connector_workspace_path:
        candidate = Path(connector_workspace_path).expanduser()
        if candidate.is_dir():
            return str(candidate)
    project_workspace_path = _normalize_text(getattr(project, "workspace_path", ""), 1000)
    if project_workspace_path:
        candidate = Path(project_workspace_path).expanduser()
        if candidate.is_dir():
            return str(candidate)
    return ""


def _state_root(project_id: str = "", workspace_path: str = "") -> Path | None:
    workspace_root = _resolve_project_workspace_path(project_id, workspace_path)
    if workspace_root:
        return Path(workspace_root) / _STATE_DIR
    return None


def _active_state_path(project_id: str, workspace_path: str = "") -> Path | None:
    state_root = _state_root(project_id, workspace_path)
    if state_root is None:
        return None
    return state_root / "active" / f"{_safe_name(project_id)}.json"


def _session_state_path(project_id: str, chat_session_id: str, workspace_path: str = "") -> Path | None:
    state_root = _state_root(project_id, workspace_path)
    if state_root is None:
        return None
    file_name = f"{_safe_name(project_id)}__{_safe_name(chat_session_id)}.json"
    return state_root / "session-history" / file_name


def _read_json(path: Path | None) -> dict[str, Any]:
    try:
        if path is None or not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_query_mcp_project_state(project_id: str, workspace_path: str = "") -> dict[str, Any]:
    project_id_value = _normalize_text(project_id, 120)
    if not project_id_value:
        return {}
    payload = _read_json(_active_state_path(project_id_value, workspace_path))
    if payload:
        return payload
    state_root = _state_root(project_id_value, workspace_path)
    if state_root is None:
        return {}
    history_dir = state_root / "session-history"
    if not history_dir.exists():
        return {}
    candidates = sorted(history_dir.glob(f"{_safe_name(project_id_value)}__*.json"))
    latest_payload: dict[str, Any] = {}
    latest_updated_at = ""
    for path in candidates:
        payload = _read_json(path)
        updated_at = _normalize_text(payload.get("updated_at"), 80)
        if updated_at >= latest_updated_at and payload:
            latest_payload = payload
            latest_updated_at = updated_at
    return latest_payload


def load_resumable_query_mcp_project_state(project_id: str, workspace_path: str = "") -> dict[str, Any]:
    payload = load_query_mcp_project_state(project_id, workspace_path)
    if not payload:
        return {}
    latest_status = _normalize_text(payload.get("latest_status"), 40).lower()
    if latest_status in _TERMINAL_STATUSES:
        return {}
    if not _normalize_text(payload.get("chat_session_id"), 200):
        return {}
    return payload


def save_query_mcp_project_state(
    *,
    project_id: str,
    chat_session_id: str,
    workspace_path: str = "",
    project_name: str = "",
    employee_id: str = "",
    session_id: str = "",
    root_goal: str = "",
    latest_status: str = "",
    phase: str = "",
    step: str = "",
    developer_name: str = "",
    key_owner_username: str = "",
    source: str = "",
) -> dict[str, Any]:
    project_id_value = _normalize_text(project_id, 120)
    chat_session_id_value = _normalize_text(chat_session_id, 200)
    if not project_id_value or not chat_session_id_value:
        return {}
    active_path = _active_state_path(project_id_value, workspace_path)
    session_path = _session_state_path(project_id_value, chat_session_id_value, workspace_path)
    if active_path is None or session_path is None:
        return {}
    existing = _read_json(session_path) or _read_json(active_path)
    payload = {
        "project_id": project_id_value,
        "project_name": _normalize_text(project_name, 200)
        or _normalize_text(existing.get("project_name"), 200),
        "workspace_path": _resolve_project_workspace_path(project_id_value, workspace_path)
        or _normalize_text(existing.get("workspace_path"), 1000),
        "employee_id": _normalize_text(employee_id, 120)
        or _normalize_text(existing.get("employee_id"), 120),
        "chat_session_id": chat_session_id_value,
        "session_id": _normalize_text(session_id, 200)
        or _normalize_text(existing.get("session_id"), 200),
        "root_goal": _normalize_text(root_goal, 1000)
        or _normalize_text(existing.get("root_goal"), 1000),
        "latest_status": _normalize_text(latest_status, 80)
        or _normalize_text(existing.get("latest_status"), 80),
        "phase": _normalize_text(phase, 80) or _normalize_text(existing.get("phase"), 80),
        "step": _normalize_text(step, 200) or _normalize_text(existing.get("step"), 200),
        "developer_name": _normalize_text(developer_name, 120)
        or _normalize_text(existing.get("developer_name"), 120),
        "key_owner_username": _normalize_text(key_owner_username, 120)
        or _normalize_text(existing.get("key_owner_username"), 120),
        "source": _normalize_text(source, 120) or _normalize_text(existing.get("source"), 120),
        "updated_at": _now_iso(),
    }
    active_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.parent.mkdir(parents=True, exist_ok=True)
    active_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    session_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
