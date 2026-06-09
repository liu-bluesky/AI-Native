"""Context checkpoint summaries for resumable agent runtime sessions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from services.agent_runtime.core.transcript_store import TranscriptStore


@dataclass(frozen=True)
class ContextCheckpoint:
    run_id: str
    summary: str
    event_count: int = 0
    tool_call_count: int = 0
    observation_count: int = 0
    blocked_count: int = 0
    latest_user_goal: str = ""
    latest_visible_assistant: str = ""
    tool_summaries: tuple[str, ...] = ()
    observations: tuple[str, ...] = ()
    raw_event_ids: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "summary": self.summary,
            "event_count": self.event_count,
            "tool_call_count": self.tool_call_count,
            "observation_count": self.observation_count,
            "blocked_count": self.blocked_count,
            "latest_user_goal": self.latest_user_goal,
            "latest_visible_assistant": self.latest_visible_assistant,
            "tool_summaries": list(self.tool_summaries),
            "observations": list(self.observations),
            "raw_event_ids": list(self.raw_event_ids),
            "metadata": dict(self.metadata),
        }

    def to_resume_messages(self) -> list[dict[str, str]]:
        messages = [
            {
                "role": "system",
                "content": f"Runtime checkpoint summary:\n{self.summary}",
            }
        ]
        if self.latest_user_goal:
            messages.append({"role": "user", "content": self.latest_user_goal})
        if self.latest_visible_assistant:
            messages.append(
                {"role": "assistant", "content": self.latest_visible_assistant}
            )
        return [message for message in messages if str(message.get("content") or "").strip()]


class ContextCheckpointBuilder:
    def __init__(self, transcript_store: TranscriptStore):
        self._transcript_store = transcript_store

    def build(self, run_id: str, *, max_events: int = 80) -> ContextCheckpoint:
        normalized_run_id = str(run_id or "").strip()
        events = self._transcript_store.list_events(normalized_run_id)
        if max_events > 0:
            events = events[-max_events:]
        latest_user_goal = ""
        latest_visible_assistant = ""
        tool_summaries: list[str] = []
        observations: list[str] = []
        raw_event_ids: list[str] = []
        tool_call_count = 0
        observation_count = 0
        blocked_count = 0
        for event in events:
            raw_event_ids.append(str(event.get("event_id") or "").strip())
            event_type = str(event.get("type") or "").strip()
            payload_raw = event.get("payload")
            payload: dict[str, Any] = dict(payload_raw) if isinstance(payload_raw, dict) else {}
            content = _visible_content(payload)
            if event_type in {"user_input", "user_message", "input"} and content:
                latest_user_goal = content
            elif event_type in {"model_output", "assistant_message", "assistant"}:
                if content:
                    latest_visible_assistant = content
                for call in _tool_calls(payload):
                    tool_call_count += 1
                    tool_summaries.append(_tool_call_summary(call))
            elif event_type in {"tool_observation", "tool_result", "tool_execution"}:
                observation_count += 1
                summary = _observation_summary(payload)
                if summary:
                    observations.append(summary)
            if event_type in {"blocked", "waiting_user", "permission_decision"}:
                blocked_count += 1
        summary = _compose_summary(
            latest_user_goal=latest_user_goal,
            latest_visible_assistant=latest_visible_assistant,
            tool_summaries=tool_summaries,
            observations=observations,
            blocked_count=blocked_count,
        )
        return ContextCheckpoint(
            run_id=normalized_run_id,
            summary=summary,
            event_count=len(events),
            tool_call_count=tool_call_count,
            observation_count=observation_count,
            blocked_count=blocked_count,
            latest_user_goal=latest_user_goal,
            latest_visible_assistant=latest_visible_assistant,
            tool_summaries=tuple(tool_summaries[-10:]),
            observations=tuple(observations[-10:]),
            raw_event_ids=tuple(item for item in raw_event_ids if item),
            metadata={"source": "transcript", "max_events": max_events},
        )


def _visible_content(payload: dict[str, Any]) -> str:
    for key in ("visible_content", "content", "text", "final_content"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _tool_calls(payload: dict[str, Any]) -> list[dict[str, Any]]:
    calls = payload.get("tool_calls") or payload.get("collected_tool_calls") or []
    if not isinstance(calls, list):
        return []
    return [call for call in calls if isinstance(call, dict)]


def _tool_call_summary(call: dict[str, Any]) -> str:
    tool_name = str(call.get("tool_name") or call.get("name") or "tool").strip()
    args = call.get("arguments") or call.get("args") or ""
    args_preview = str(args or "").strip()
    if len(args_preview) > 160:
        args_preview = args_preview[:157].rstrip() + "..."
    return f"{tool_name}: {args_preview}" if args_preview else tool_name


def _observation_summary(payload: dict[str, Any]) -> str:
    tool_name = str(payload.get("tool_name") or payload.get("name") or "tool").strip()
    status = str(payload.get("status") or payload.get("state") or "").strip()
    summary = str(
        payload.get("summary")
        or payload.get("output_preview")
        or payload.get("stdout_preview")
        or payload.get("error")
        or ""
    ).strip()
    parts = [part for part in (tool_name, status, summary) if part]
    return " - ".join(parts)


def _compose_summary(
    *,
    latest_user_goal: str,
    latest_visible_assistant: str,
    tool_summaries: list[str],
    observations: list[str],
    blocked_count: int,
) -> str:
    lines: list[str] = []
    if latest_user_goal:
        lines.append(f"Recent goal: {latest_user_goal}")
    if tool_summaries:
        lines.append("Recent tools: " + "; ".join(tool_summaries[-5:]))
    if observations:
        lines.append("Key observations: " + "; ".join(observations[-5:]))
    if blocked_count:
        lines.append(f"Unresolved blocking signals: {blocked_count}")
    if latest_visible_assistant:
        lines.append(f"Last visible assistant message: {latest_visible_assistant}")
    return "\n".join(lines) or "No transcript events available."


__all__ = ["ContextCheckpoint", "ContextCheckpointBuilder"]
