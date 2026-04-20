from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.deps import project_store

_STATE_DIR = Path(".ai-employee") / "query-mcp"
_ACTIVE_SESSIONS_DIR = "active-sessions"
_LEGACY_CURRENT_SESSION_FILE = "current-session.json"
_LEGACY_JSON_POINTER_FILES = ("current-work-session.json", "current-query-session.json")
_LEGACY_TEXT_POINTER_FILES = {
    "chat_session_id": ("chat_session_id.txt", "chat_session_id"),
    "session_id": ("session_id.txt", "session_id"),
}
_STATE_FIELD_LIMITS = {
    "project_id": 120,
    "project_name": 200,
    "workspace_path": 1000,
    "employee_id": 120,
    "chat_session_id": 200,
    "session_id": 200,
    "root_goal": 1000,
    "latest_status": 80,
    "phase": 80,
    "step": 200,
    "developer_name": 120,
    "key_owner_username": 120,
    "source": 120,
    "updated_at": 80,
}
_TERMINAL_STATUSES = {"done", "completed", "archived", "closed"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(value: object, limit: int = 400) -> str:
    return str(value or "").strip()[:limit]


def _safe_name(value: object, fallback: str = "unknown") -> str:
    normalized = _normalize_text(value, 200)
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", normalized).strip("._")
    return cleaned or fallback


def _normalize_state_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    normalized: dict[str, Any] = {}
    for field, limit in _STATE_FIELD_LIMITS.items():
        value = _normalize_text(payload.get(field), limit)
        if value:
            normalized[field] = value
    return normalized


def _merge_state_payloads(*payloads: dict[str, Any] | None) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for payload in payloads:
        normalized = _normalize_state_payload(payload)
        for field, value in normalized.items():
            if field not in merged:
                merged[field] = value
    return merged


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


def _active_session_path(chat_session_id: str, project_id: str = "", workspace_path: str = "") -> Path | None:
    state_root = _state_root(project_id, workspace_path)
    if state_root is None:
        return None
    return state_root / _ACTIVE_SESSIONS_DIR / f"{_safe_name(chat_session_id)}.json"


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


def _legacy_current_session_path(project_id: str = "", workspace_path: str = "") -> Path | None:
    state_root = _state_root(project_id, workspace_path)
    if state_root is None:
        return None
    return state_root / _LEGACY_CURRENT_SESSION_FILE


def _is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, PermissionError):
        return False


def _extract_pid_from_chat_session_id(chat_session_id: str) -> int:
    parts = chat_session_id.split(".")
    for part in parts:
        if part.isdigit() and len(part) >= 2:
            return int(part)
    return 0


def _load_latest_active_session(project_id: str, workspace_path: str = "") -> dict[str, Any]:
    state_root = _state_root(project_id, workspace_path)
    if state_root is None:
        return {}
    sessions_dir = state_root / _ACTIVE_SESSIONS_DIR
    if not sessions_dir.exists():
        return {}
    project_id_value = _normalize_text(project_id, 120)
    best_payload: dict[str, Any] = {}
    best_updated_at = ""
    for path in sessions_dir.glob("*.json"):
        payload = _read_json(path)
        if not payload:
            continue
        payload_project_id = _normalize_text(payload.get("project_id"), 120)
        if payload_project_id and payload_project_id != project_id_value:
            continue
        updated_at = _normalize_text(payload.get("updated_at"), 80)
        if updated_at >= best_updated_at:
            best_payload = payload
            best_updated_at = updated_at
    return best_payload


def _read_json(path: Path | None) -> dict[str, Any]:
    try:
        if path is None or not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _read_text(path: Path | None, limit: int = 400) -> str:
    try:
        if path is None or not path.exists():
            return ""
        return path.read_text(encoding="utf-8").strip()[:limit]
    except Exception:
        return ""


def _write_json(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    normalized = _normalize_state_payload(payload)
    if not normalized:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_latest_history_payload(project_id: str, workspace_path: str = "") -> dict[str, Any]:
    state_root = _state_root(project_id, workspace_path)
    if state_root is None:
        return {}
    history_dir = state_root / "session-history"
    if not history_dir.exists():
        return {}
    candidates = sorted(history_dir.glob(f"{_safe_name(project_id)}__*.json"))
    latest_payload: dict[str, Any] = {}
    latest_updated_at = ""
    for path in candidates:
        payload = _read_json(path)
        updated_at = _normalize_text(payload.get("updated_at"), 80)
        if updated_at >= latest_updated_at and payload:
            latest_payload = payload
            latest_updated_at = updated_at
    return latest_payload


def _read_legacy_env_state(project_id: str, workspace_path: str = "") -> dict[str, Any]:
    state_root = _state_root(project_id, workspace_path)
    if state_root is None:
        return {}
    raw = _read_text(state_root / "session.env", 2000)
    if not raw:
        return {}
    parsed: dict[str, str] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        parsed[key.strip().lower()] = value.strip().strip("\"'")
    env_payload = {
        "project_id": parsed.get("project_id", ""),
        "chat_session_id": parsed.get("chat_session_id", ""),
        "session_id": parsed.get("session_id", ""),
        "root_goal": parsed.get("root_goal", ""),
    }
    project_id_value = _normalize_text(project_id, 120)
    payload_project_id = _normalize_text(env_payload.get("project_id"), 120)
    if payload_project_id and payload_project_id != project_id_value:
        return {}
    if not payload_project_id and project_id_value:
        env_payload["project_id"] = project_id_value
    return _normalize_state_payload(env_payload)


def _load_legacy_pointer_state(project_id: str, workspace_path: str = "") -> dict[str, Any]:
    project_id_value = _normalize_text(project_id, 120)
    state_root = _state_root(project_id_value, workspace_path)
    if state_root is None:
        return {}
    legacy_json_payloads: list[dict[str, Any]] = []
    for file_name in _LEGACY_JSON_POINTER_FILES:
        payload = _read_json(state_root / file_name)
        if not payload:
            continue
        payload_project_id = _normalize_text(payload.get("project_id"), 120)
        if payload_project_id and payload_project_id != project_id_value:
            continue
        if not payload_project_id:
            payload = {**payload, "project_id": project_id_value}
        legacy_json_payloads.append(payload)
    fallback_text_payload = {
        "project_id": project_id_value,
        "chat_session_id": "",
        "session_id": "",
    }
    for field, file_names in _LEGACY_TEXT_POINTER_FILES.items():
        for file_name in file_names:
            value = _read_text(state_root / file_name, _STATE_FIELD_LIMITS[field])
            if value:
                fallback_text_payload[field] = value
                break
    return _merge_state_payloads(
        *legacy_json_payloads,
        _read_legacy_env_state(project_id_value, workspace_path),
        fallback_text_payload,
    )


def load_current_query_mcp_session(project_id: str, workspace_path: str = "") -> dict[str, Any]:
    project_id_value = _normalize_text(project_id, 120)
    if not project_id_value:
        return {}
    current_payload = _load_latest_active_session(project_id_value, workspace_path)
    if not current_payload:
        legacy_payload = _read_json(_legacy_current_session_path(project_id_value, workspace_path))
        legacy_project_id = _normalize_text(legacy_payload.get("project_id"), 120)
        if legacy_project_id and legacy_project_id != project_id_value:
            legacy_payload = {}
        elif legacy_payload and not legacy_project_id:
            legacy_payload = {**legacy_payload, "project_id": project_id_value}
        current_payload = legacy_payload
    current_project_id = _normalize_text(current_payload.get("project_id"), 120)
    if current_project_id and current_project_id != project_id_value:
        current_payload = {}
    elif current_payload and not current_project_id:
        current_payload = {**current_payload, "project_id": project_id_value}
    resolved_chat_session_id = _normalize_text(current_payload.get("chat_session_id"), 200)
    return _merge_state_payloads(
        current_payload,
        _read_json(_session_state_path(project_id_value, resolved_chat_session_id, workspace_path))
        if resolved_chat_session_id
        else {},
        _load_legacy_pointer_state(project_id_value, workspace_path),
    )


def load_query_mcp_local_state(project_id: str, workspace_path: str = "") -> dict[str, Any]:
    project_id_value = _normalize_text(project_id, 120)
    if not project_id_value:
        return {}
    current_payload = load_current_query_mcp_session(project_id_value, workspace_path)
    if current_payload:
        return _merge_state_payloads(
            current_payload,
            _read_json(_active_state_path(project_id_value, workspace_path)),
            _load_latest_history_payload(project_id_value, workspace_path),
        )
    active_payload = _read_json(_active_state_path(project_id_value, workspace_path))
    history_payload = _load_latest_history_payload(project_id_value, workspace_path)
    legacy_payload = _load_legacy_pointer_state(project_id_value, workspace_path)
    return _merge_state_payloads(active_payload, history_payload, legacy_payload)


def load_resumable_query_mcp_local_state(project_id: str, workspace_path: str = "") -> dict[str, Any]:
    payload = load_query_mcp_local_state(project_id, workspace_path)
    if not payload:
        return {}
    latest_status = _normalize_text(payload.get("latest_status"), 40).lower()
    if latest_status in _TERMINAL_STATUSES:
        return {}
    if not _normalize_text(payload.get("chat_session_id"), 200):
        return {}
    return payload


def persist_query_mcp_local_state(
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
    active_session_path = _active_session_path(chat_session_id_value, project_id_value, workspace_path)
    if active_path is None or session_path is None or active_session_path is None:
        return {}
    existing = _merge_state_payloads(
        _read_json(active_session_path),
        _read_json(session_path),
        _read_json(active_path),
        _load_legacy_pointer_state(project_id_value, workspace_path),
    )
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
    _write_json(active_session_path, payload)
    _write_json(session_path, payload)
    _write_json(active_path, payload)
    return _normalize_state_payload(payload)


def load_query_mcp_project_state(project_id: str, workspace_path: str = "") -> dict[str, Any]:
    return load_query_mcp_local_state(project_id, workspace_path)


def load_resumable_query_mcp_project_state(project_id: str, workspace_path: str = "") -> dict[str, Any]:
    return load_resumable_query_mcp_local_state(project_id, workspace_path)


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
    return persist_query_mcp_local_state(
        project_id=project_id,
        chat_session_id=chat_session_id,
        workspace_path=workspace_path,
        project_name=project_name,
        employee_id=employee_id,
        session_id=session_id,
        root_goal=root_goal,
        latest_status=latest_status,
        phase=phase,
        step=step,
        developer_name=developer_name,
        key_owner_username=key_owner_username,
        source=source,
    )
