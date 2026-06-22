"""Transcript event storage for agent runtimes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from core.config import get_project_root
from services.agent_runtime.core.task_run import utc_now_iso


class TranscriptStore:
    def __init__(self, root_path: Path | None = None):
        self._root_path = root_path or (
            get_project_root() / ".ai-employee" / "agent-runtime-v2" / "transcripts"
        )

    def _path_for(self, run_id: str) -> Path:
        normalized_run_id = str(run_id or "").strip()
        if not normalized_run_id:
            raise ValueError("run_id is required")
        return self._root_path / f"{normalized_run_id}.jsonl"

    def append(
        self,
        run_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
        *,
        session_id: str = "",
    ) -> dict[str, Any]:
        # 中文注释：Transcript 是 replay 来源，session_id 允许后续按会话恢复，不再只靠 run_id 反查。
        event = {
            "event_id": f"evt_{uuid4().hex[:16]}",
            "run_id": str(run_id or "").strip(),
            "session_id": str(session_id or "").strip(),
            "type": str(event_type or "").strip() or "event",
            "created_at": utc_now_iso(),
            "payload": dict(payload or {}),
        }
        path = self._path_for(run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        return event

    def list_events(self, run_id: str) -> list[dict[str, Any]]:
        path = self._path_for(run_id)
        if not path.is_file():
            return []
        events: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                events.append(payload)
        return events
