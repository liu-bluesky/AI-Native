"""Startup reconciliation for stale recoverable agent runtime runs."""

from __future__ import annotations

from datetime import datetime, timezone

from services.agent_runtime.core.event_log import RuntimeEventLog
from services.agent_runtime.core.state_store import TaskRunStore
from services.agent_runtime.core.task_run import TaskRun


class AgentRuntimeStaleRunReconciler:
    def __init__(
        self,
        *,
        state_store: TaskRunStore | None = None,
        event_log: RuntimeEventLog | None = None,
        stale_after_seconds: int = 300,
        scan_limit: int = 10000,
    ):
        self._state_store = state_store or TaskRunStore()
        self._event_log = event_log or RuntimeEventLog()
        self._stale_after_seconds = max(1, int(stale_after_seconds or 300))
        self._scan_limit = max(1, int(scan_limit or 10000))

    def reconcile(self, *, now: datetime | None = None) -> list[TaskRun]:
        current_time = now or datetime.now(timezone.utc)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)
        else:
            current_time = current_time.astimezone(timezone.utc)

        reconciled: list[TaskRun] = []
        for task_run in self._state_store.list_runs(limit=self._scan_limit):
            prior_status = str(task_run.status or "").strip()
            if prior_status not in {"running", "retry_wait"}:
                continue
            updated_at = self._parse_timestamp(task_run.updated_at)
            if updated_at is None:
                continue
            stale_seconds = max(0, int((current_time - updated_at).total_seconds()))
            if stale_seconds < self._stale_after_seconds:
                continue

            payload = {
                "prior_status": prior_status,
                "status": "interrupted",
                "stale_seconds": stale_seconds,
                "stale_after_seconds": self._stale_after_seconds,
                "reason": "service_restart_or_lost_runtime_ownership",
                "recoverable": True,
            }
            self._state_store.append_event(
                task_run,
                "stale_run_interrupted",
                payload,
                status="interrupted",
            )
            self._event_log.append(
                task_run.run_id,
                "stale_run_interrupted",
                payload,
                session_id=task_run.session_id,
            )
            reconciled.append(task_run)
        return reconciled

    @staticmethod
    def _parse_timestamp(value: str) -> datetime | None:
        normalized = str(value or "").strip()
        if not normalized:
            return None
        if normalized.endswith("Z"):
            normalized = f"{normalized[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
