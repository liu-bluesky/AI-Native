"""Read-only inspection helpers for agent_runtime_v2 runs."""

from __future__ import annotations

from typing import Any

from services.agent_runtime.core.event_log import RuntimeEventLog
from services.agent_runtime.core.state_store import TaskRunStore
from services.agent_runtime.core.transcript_store import TranscriptStore


class AgentRuntimeInspector:
    def __init__(
        self,
        *,
        state_store: TaskRunStore | None = None,
        event_log: RuntimeEventLog | None = None,
        transcript_store: TranscriptStore | None = None,
    ):
        self._state_store = state_store or TaskRunStore()
        self._event_log = event_log or RuntimeEventLog()
        self._transcript_store = transcript_store or TranscriptStore()

    def get_run_snapshot(self, run_id: str) -> dict[str, Any] | None:
        run = self._state_store.load(run_id)
        if run is None:
            return None
        return {
            "run": run.to_dict(),
            "events": [event.to_dict() for event in self._event_log.list_events(run.run_id)],
            "transcript": self._transcript_store.list_events(run.run_id),
        }

    def list_run_summaries(
        self,
        *,
        project_id: str = "",
        username: str = "",
        chat_session_id: str = "",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        runs = self._state_store.list_runs(
            project_id=project_id,
            username=username,
            chat_session_id=chat_session_id,
            limit=limit,
        )
        return [
            {
                "run_id": run.run_id,
                "project_id": run.project_id,
                "username": run.username,
                "chat_session_id": run.chat_session_id,
                "session_id": run.session_id,
                "status": run.status,
                "user_goal": run.user_goal,
                "created_at": run.created_at,
                "updated_at": run.updated_at,
                "metadata": dict(run.metadata),
            }
            for run in runs
        ]
