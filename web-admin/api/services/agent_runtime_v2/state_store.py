"""Local-first TaskRun state store for agent_runtime_v2."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.config import get_project_root
from services.agent_runtime_v2.task_run import TaskRun, utc_now_iso


class TaskRunStore:
    def __init__(self, root_path: Path | None = None):
        self._root_path = root_path or (
            get_project_root() / ".ai-employee" / "agent-runtime-v2" / "task-runs"
        )

    @property
    def root_path(self) -> Path:
        return self._root_path

    def _path_for(self, run_id: str) -> Path:
        normalized_run_id = str(run_id or "").strip()
        if not normalized_run_id:
            raise ValueError("run_id is required")
        return self._root_path / f"{normalized_run_id}.json"

    def save(self, task_run: TaskRun) -> TaskRun:
        self._root_path.mkdir(parents=True, exist_ok=True)
        path = self._path_for(task_run.run_id)
        task_run.updated_at = utc_now_iso()
        path.write_text(
            json.dumps(task_run.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return task_run

    def load(self, run_id: str) -> TaskRun | None:
        path = self._path_for(run_id)
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return TaskRun.from_dict(payload) if isinstance(payload, dict) else None

    def list_runs(
        self,
        *,
        project_id: str = "",
        username: str = "",
        chat_session_id: str = "",
        limit: int = 50,
    ) -> list[TaskRun]:
        if not self._root_path.is_dir():
            return []
        normalized_project_id = str(project_id or "").strip()
        normalized_username = str(username or "").strip()
        normalized_chat_session_id = str(chat_session_id or "").strip()
        runs: list[TaskRun] = []
        for path in sorted(self._root_path.glob("run_*.json"), reverse=True):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            run = TaskRun.from_dict(payload)
            if normalized_project_id and run.project_id != normalized_project_id:
                continue
            if normalized_username and run.username != normalized_username:
                continue
            if normalized_chat_session_id and run.chat_session_id != normalized_chat_session_id:
                continue
            runs.append(run)
            if len(runs) >= max(1, int(limit or 50)):
                break
        return runs

    def create(
        self,
        *,
        project_id: str,
        username: str,
        chat_session_id: str,
        session_id: str,
        user_goal: str,
        metadata: dict[str, Any] | None = None,
    ) -> TaskRun:
        task_run = TaskRun.create(
            project_id=project_id,
            username=username,
            chat_session_id=chat_session_id,
            session_id=session_id,
            user_goal=user_goal,
            metadata=metadata,
        )
        task_run.append_event("run_created", {"status": task_run.status})
        return self.save(task_run)

    def append_event(
        self,
        task_run: TaskRun,
        event_type: str,
        payload: dict[str, Any] | None = None,
        *,
        status: str | None = None,
    ) -> TaskRun:
        if status is not None:
            task_run.status = str(status or "").strip() or task_run.status
        task_run.append_event(event_type, payload)
        return self.save(task_run)
