"""Project chat external-agent task queue (JSON implementation)."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_TASK_STATUS_VALUES = {"queued", "claimed", "completed", "failed", "cancelled", "timeout"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_token(value: str, max_len: int = 128) -> str:
    token = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())
    token = token.strip("._-")
    if not token:
        raise ValueError("invalid token")
    return token[:max_len]


def _normalize_text(value: object, limit: int = 4000) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()[:limit]


def _normalize_json_object(value: object, *, limit: int = 200_000) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    try:
        payload = json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    encoded = json.dumps(payload, ensure_ascii=False)
    if len(encoded) <= limit:
        return payload
    return {
        "truncated": True,
        "preview": encoded[:limit],
    }


def _normalize_status(value: object, fallback: str = "queued") -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in _TASK_STATUS_VALUES else fallback


@dataclass
class ProjectChatExternalAgentTask:
    id: str
    project_id: str
    username: str
    task_type: str = "bot_local_chat"
    status: str = "queued"
    external_agent_type: str = "codex_cli"
    runner_id: str = ""
    runner_session_id: str = ""
    workspace_path: str = ""
    request: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)
    error_message: str = ""
    claimed_at: str = ""
    completed_at: str = ""
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def __post_init__(self) -> None:
        self.id = _normalize_text(self.id, 80) or f"ext-task-{uuid.uuid4().hex[:12]}"
        self.project_id = _normalize_text(self.project_id, 80)
        self.username = _normalize_text(self.username, 80)
        self.task_type = _normalize_text(self.task_type, 80) or "bot_local_chat"
        self.status = _normalize_status(self.status)
        self.external_agent_type = _normalize_text(self.external_agent_type, 80) or "codex_cli"
        self.runner_id = _normalize_text(self.runner_id, 120)
        self.runner_session_id = _normalize_text(self.runner_session_id, 120)
        self.workspace_path = _normalize_text(self.workspace_path, 1000)
        self.request = _normalize_json_object(self.request)
        self.result = _normalize_json_object(self.result, limit=80_000)
        self.error_message = _normalize_text(self.error_message, 2000)
        self.claimed_at = _normalize_text(self.claimed_at, 40)
        self.completed_at = _normalize_text(self.completed_at, 40)
        self.created_at = _normalize_text(self.created_at or _now_iso(), 40) or _now_iso()
        self.updated_at = _normalize_text(self.updated_at or _now_iso(), 40) or _now_iso()


class ProjectChatExternalAgentTaskStore:
    def __init__(self, data_dir: Path) -> None:
        self._root = data_dir / "project-chat-external-agent-tasks"
        self._root.mkdir(parents=True, exist_ok=True)

    def _project_dir(self, project_id: str) -> Path:
        return self._root / _safe_token(project_id)

    def _task_path(self, project_id: str, task_id: str) -> Path:
        return self._project_dir(project_id) / f"{_safe_token(task_id)}.json"

    def _read_task_path(self, path: Path) -> ProjectChatExternalAgentTask | None:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(raw, dict):
            return None
        try:
            return ProjectChatExternalAgentTask(**raw)
        except TypeError:
            return None

    def _write(self, task: ProjectChatExternalAgentTask) -> ProjectChatExternalAgentTask:
        project_dir = self._project_dir(task.project_id)
        project_dir.mkdir(parents=True, exist_ok=True)
        task.updated_at = _now_iso()
        path = self._task_path(task.project_id, task.id)
        path.write_text(json.dumps(asdict(task), ensure_ascii=False, indent=2), encoding="utf-8")
        return task

    def save(self, task: ProjectChatExternalAgentTask) -> ProjectChatExternalAgentTask:
        return self._write(task)

    def enqueue(
        self,
        *,
        project_id: str,
        username: str,
        request: dict[str, Any],
        external_agent_type: str = "codex_cli",
        task_type: str = "bot_local_chat",
    ) -> ProjectChatExternalAgentTask:
        task = ProjectChatExternalAgentTask(
            id=f"ext-task-{uuid.uuid4().hex[:12]}",
            project_id=project_id,
            username=username,
            task_type=task_type,
            external_agent_type=external_agent_type,
            workspace_path=str(request.get("workspacePath") or request.get("workspace_path") or "").strip(),
            request=request,
        )
        return self._write(task)

    def get(self, project_id: str, task_id: str) -> ProjectChatExternalAgentTask | None:
        normalized_project_id = str(project_id or "").strip()
        normalized_task_id = str(task_id or "").strip()
        if not normalized_project_id or not normalized_task_id:
            return None
        return self._read_task_path(self._task_path(normalized_project_id, normalized_task_id))

    def claim_next(
        self,
        *,
        project_id: str,
        username: str,
        runner_id: str = "",
        supported_agent_types: list[str] | None = None,
        workspace_path: str = "",
    ) -> ProjectChatExternalAgentTask | None:
        normalized_project_id = str(project_id or "").strip()
        normalized_username = str(username or "").strip()
        if not normalized_project_id or not normalized_username:
            return None
        supported = {
            str(item or "").strip().lower()
            for item in (supported_agent_types or [])
            if str(item or "").strip()
        }
        project_dir = self._project_dir(normalized_project_id)
        if not project_dir.exists():
            return None
        tasks = [
            task
            for task in (
                self._read_task_path(path)
                for path in sorted(project_dir.glob("*.json"))
            )
            if task is not None
        ]
        tasks.sort(key=lambda item: item.created_at)
        for task in tasks:
            if task.status != "queued":
                continue
            if task.username != normalized_username:
                continue
            if supported and task.external_agent_type.lower() not in supported and task.task_type.lower() not in supported:
                continue
            task.status = "claimed"
            task.runner_id = _normalize_text(runner_id, 120)
            if workspace_path:
                task.workspace_path = _normalize_text(workspace_path, 1000)
                task.request["workspacePath"] = task.workspace_path
            task.claimed_at = _now_iso()
            return self._write(task)
        return None

    def complete(
        self,
        *,
        project_id: str,
        task_id: str,
        status: str,
        content: str = "",
        error_message: str = "",
        runner_session_id: str = "",
        runner_meta: dict[str, Any] | None = None,
    ) -> ProjectChatExternalAgentTask:
        task = self.get(project_id, task_id)
        if task is None:
            raise ValueError("task not found")
        task.status = _normalize_status(status, fallback="completed")
        task.runner_session_id = _normalize_text(runner_session_id, 120)
        task.error_message = _normalize_text(error_message, 2000)
        task.result = _normalize_json_object(
            {
                "content": _normalize_text(content, 12000),
                "runner_meta": runner_meta or {},
            },
            limit=80_000,
        )
        task.completed_at = _now_iso()
        return self._write(task)
