"""Normalize raw tool results into ToolObservation records."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class ToolObservation:
    observation_id: str
    run_id: str
    call_id: str
    tool_name: str
    status: str
    summary: str = ""
    raw_result: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_utc_now_iso)

    @property
    def is_error(self) -> bool:
        return self.status in {"error", "failed", "timeout", "blocked"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "run_id": self.run_id,
            "call_id": self.call_id,
            "tool_name": self.tool_name,
            "status": self.status,
            "summary": self.summary,
            "raw_result": dict(self.raw_result),
            "created_at": self.created_at,
        }


class ToolResultNormalizer:
    def normalize(
        self,
        *,
        run_id: str,
        call_id: str,
        tool_name: str,
        raw_result: Any,
    ) -> ToolObservation:
        payload = dict(raw_result or {}) if isinstance(raw_result, dict) else {"result": raw_result}
        status = self._resolve_status(payload)
        return ToolObservation(
            observation_id=f"obs_{uuid4().hex[:16]}",
            run_id=str(run_id or "").strip(),
            call_id=str(call_id or "").strip(),
            tool_name=str(tool_name or "").strip(),
            status=status,
            summary=self._summarize(payload, status=status),
            raw_result=payload,
        )

    def _resolve_status(self, payload: dict[str, Any]) -> str:
        if str(payload.get("status") or "").strip().lower() in {
            "blocked",
            "failed",
            "timeout",
            "succeeded",
            "success",
            "error",
            "queued",
            "running",
            "waiting_user_action",
        }:
            status = str(payload.get("status") or "").strip().lower()
            return "succeeded" if status == "success" else status
        if payload.get("ok") is False or payload.get("error"):
            return "error"
        exit_code = payload.get("exit_code")
        if exit_code is not None:
            try:
                return "succeeded" if int(exit_code) == 0 else "failed"
            except (TypeError, ValueError):
                pass
        return "succeeded"

    def _summarize(self, payload: dict[str, Any], *, status: str) -> str:
        structured = self._structured_stdout_summary(payload)
        if structured:
            return structured
        for key in ("summary", "message", "error", "stderr", "stdout"):
            value = str(payload.get(key) or "").strip()
            if value:
                return value[-500:]
        return status

    def _structured_stdout_summary(self, payload: dict[str, Any]) -> str:
        stdout = str(payload.get("stdout") or "").strip()
        if not stdout or not stdout.startswith("{"):
            return ""
        try:
            parsed = json.loads(stdout)
        except (TypeError, ValueError):
            return ""
        if not isinstance(parsed, dict):
            return ""
        lines: list[str] = []

        def add_field(label: str, *keys: str) -> None:
            for key in keys:
                value = parsed.get(key)
                if value in (None, ""):
                    continue
                lines.append(f"{label}: {str(value).strip()}")
                return

        add_field("status", "status", "login_status")
        add_field("user", "name", "user_name", "display_name", "email")
        add_field("identity", "identity", "as", "login_identity")
        add_field("brand", "brand")
        add_field("expires_at", "expires_at", "expire_at", "expired_at")
        add_field("refresh_expires_at", "refresh_expires_at", "refresh_expire_at")
        return "\n".join(lines[:8]).strip()
