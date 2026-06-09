"""Background process handles for runtime state recovery."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from services.agent_runtime.core.task_run import utc_now_iso

TERMINAL_BACKGROUND_STATUSES = {"completed", "failed", "cancelled"}


@dataclass(frozen=True)
class BackgroundProcessHandle:
    process_id: str
    command: str
    cwd: str = ""
    status: str = "running"
    started_at: str = ""
    updated_at: str = ""
    exit_code: int | None = None
    log_cursor: int = 0
    resume_token: str = ""
    cancel_token: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def terminal(self) -> bool:
        return self.status in TERMINAL_BACKGROUND_STATUSES

    def to_dict(self) -> dict[str, Any]:
        return {
            "process_id": self.process_id,
            "command": self.command,
            "cwd": self.cwd,
            "status": self.status,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "exit_code": self.exit_code,
            "log_cursor": self.log_cursor,
            "resume_token": self.resume_token,
            "cancel_token": self.cancel_token,
            "terminal": self.terminal,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "BackgroundProcessHandle":
        return cls(
            process_id=str(payload.get("process_id") or "").strip(),
            command=str(payload.get("command") or "").strip(),
            cwd=str(payload.get("cwd") or "").strip(),
            status=str(payload.get("status") or "running").strip() or "running",
            started_at=str(payload.get("started_at") or "").strip(),
            updated_at=str(payload.get("updated_at") or "").strip(),
            exit_code=_coerce_optional_int(payload.get("exit_code")),
            log_cursor=max(0, _coerce_int(payload.get("log_cursor"), 0)),
            resume_token=str(payload.get("resume_token") or "").strip(),
            cancel_token=str(payload.get("cancel_token") or "").strip(),
            metadata=dict(payload.get("metadata") or {}),
        )


class BackgroundProcessRegistry:
    def __init__(self, handles: list[BackgroundProcessHandle] | None = None):
        self._handles: dict[str, BackgroundProcessHandle] = {
            handle.process_id: handle
            for handle in handles or []
            if str(handle.process_id or "").strip()
        }
        self._logs: dict[str, list[str]] = {handle.process_id: [] for handle in handles or []}

    def register(self, handle: BackgroundProcessHandle) -> BackgroundProcessHandle:
        now = utc_now_iso()
        normalized = replace(
            handle,
            started_at=handle.started_at or now,
            updated_at=now,
            status=handle.status or "running",
        )
        self._handles[normalized.process_id] = normalized
        self._logs.setdefault(normalized.process_id, [])
        return normalized

    def get(self, process_id: str) -> BackgroundProcessHandle | None:
        return self._handles.get(str(process_id or "").strip())

    def list(self, *, include_terminal: bool = True) -> list[BackgroundProcessHandle]:
        handles = list(self._handles.values())
        if not include_terminal:
            handles = [handle for handle in handles if not handle.terminal]
        return sorted(handles, key=lambda item: item.updated_at or item.started_at, reverse=True)

    def append_log(self, process_id: str, line: str) -> BackgroundProcessHandle | None:
        handle = self.get(process_id)
        if handle is None:
            return None
        self._logs.setdefault(handle.process_id, []).append(str(line or ""))
        updated = replace(
            handle,
            log_cursor=len(self._logs[handle.process_id]),
            updated_at=utc_now_iso(),
        )
        self._handles[handle.process_id] = updated
        return updated

    def read_log(self, process_id: str, *, cursor: int = 0, limit: int = 100) -> dict[str, Any]:
        handle = self.get(process_id)
        lines = self._logs.get(str(process_id or "").strip(), [])
        start = max(0, int(cursor or 0))
        end = min(len(lines), start + max(1, int(limit or 100)))
        return {
            "process_id": str(process_id or "").strip(),
            "status": handle.status if handle is not None else "not_found",
            "cursor": start,
            "next_cursor": end,
            "total": len(lines),
            "lines": lines[start:end],
        }

    def update_status(
        self,
        process_id: str,
        *,
        status: str,
        exit_code: int | None = None,
    ) -> BackgroundProcessHandle | None:
        handle = self.get(process_id)
        if handle is None:
            return None
        updated = replace(
            handle,
            status=str(status or handle.status).strip() or handle.status,
            exit_code=exit_code,
            updated_at=utc_now_iso(),
        )
        self._handles[handle.process_id] = updated
        return updated

    def cancel(self, process_id: str) -> BackgroundProcessHandle | None:
        return self.update_status(process_id, status="cancelled", exit_code=-15)

    def resume_payload(self, process_id: str) -> dict[str, Any] | None:
        handle = self.get(process_id)
        if handle is None:
            return None
        return {
            "process_id": handle.process_id,
            "status": handle.status,
            "resume_token": handle.resume_token,
            "cancel_token": handle.cancel_token,
            "log_cursor": handle.log_cursor,
            "metadata": dict(handle.metadata),
        }


def _coerce_optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return _coerce_int(value, 0)


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


__all__ = ["BackgroundProcessHandle", "BackgroundProcessRegistry"]
