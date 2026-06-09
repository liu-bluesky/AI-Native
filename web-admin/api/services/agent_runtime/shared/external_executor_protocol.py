"""Protocol models for external project execution agents."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ExternalExecutorType(str, Enum):
    CODEX_CLI = "codex_cli"
    CLAUDE_CODE = "claude_code"
    HERMES = "hermes"
    MCP_TOOL = "mcp_tool"
    LOCAL_TOOL = "local_tool"


class ExternalExecutorStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    WAITING_USER_ACTION = "waiting_user_action"
    RESUMING = "resuming"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class ExternalExecutorEventType(str, Enum):
    STARTED = "started"
    THINKING = "thinking"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    FILE_CHANGED = "file_changed"
    WAITING_USER_ACTION = "waiting_user_action"
    RESUMING = "resuming"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"


_STATUS_ALIASES = {
    "": ExternalExecutorStatus.PENDING,
    "created": ExternalExecutorStatus.PENDING,
    "running": ExternalExecutorStatus.IN_PROGRESS,
    "started": ExternalExecutorStatus.IN_PROGRESS,
    "done": ExternalExecutorStatus.COMPLETED,
    "succeeded": ExternalExecutorStatus.COMPLETED,
    "success": ExternalExecutorStatus.COMPLETED,
    "error": ExternalExecutorStatus.FAILED,
    "cancelled_by_user": ExternalExecutorStatus.CANCELLED,
    "canceled": ExternalExecutorStatus.CANCELLED,
}


_EVENT_ALIASES = {
    "stdout": ExternalExecutorEventType.TOOL_RESULT,
    "stderr": ExternalExecutorEventType.TOOL_RESULT,
    "chunk": ExternalExecutorEventType.TOOL_RESULT,
    "exit": ExternalExecutorEventType.COMPLETED,
    "workspace_materialized": ExternalExecutorEventType.FILE_CHANGED,
    "permission_required": ExternalExecutorEventType.WAITING_USER_ACTION,
    "approval_required": ExternalExecutorEventType.WAITING_USER_ACTION,
}


def _clean_str(value: Any) -> str:
    return str(value or "").strip()


def _string_list(value: Any) -> list[str]:
    return [_clean_str(item) for item in list(value or []) if _clean_str(item)]


def _dict_list(value: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in list(value or []) if isinstance(item, dict)]


def normalize_external_executor_type(value: Any) -> str:
    raw = _clean_str(value).lower()
    for item in ExternalExecutorType:
        if raw == item.value:
            return item.value
    return raw or ExternalExecutorType.CODEX_CLI.value


def normalize_external_executor_status(value: Any) -> str:
    raw = _clean_str(value).lower()
    if raw in _STATUS_ALIASES:
        return _STATUS_ALIASES[raw].value
    for item in ExternalExecutorStatus:
        if raw == item.value:
            return item.value
    return ExternalExecutorStatus.PENDING.value


def normalize_external_executor_event_type(value: Any) -> str:
    raw = _clean_str(value).lower()
    if raw in _EVENT_ALIASES:
        return _EVENT_ALIASES[raw].value
    for item in ExternalExecutorEventType:
        if raw == item.value:
            return item.value
    return ExternalExecutorEventType.TOOL_RESULT.value


@dataclass(frozen=True)
class ExternalExecutorRiskPolicy:
    require_confirmation_for_destructive_actions: bool = True
    network_access: str = "restricted"
    sandbox_mode: str = "workspace-write"

    def to_dict(self) -> dict[str, Any]:
        return {
            "require_confirmation_for_destructive_actions": bool(
                self.require_confirmation_for_destructive_actions
            ),
            "network_access": _clean_str(self.network_access) or "restricted",
            "sandbox_mode": _clean_str(self.sandbox_mode) or "workspace-write",
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "ExternalExecutorRiskPolicy":
        source = payload if isinstance(payload, dict) else {}
        return cls(
            require_confirmation_for_destructive_actions=bool(
                source.get("require_confirmation_for_destructive_actions", True)
            ),
            network_access=_clean_str(source.get("network_access")) or "restricted",
            sandbox_mode=_clean_str(source.get("sandbox_mode")) or "workspace-write",
        )


@dataclass(frozen=True)
class ExternalExecutorTaskInput:
    project_id: str
    chat_session_id: str
    session_id: str
    requirement_id: str
    task_tree_id: str
    task_node_id: str
    executor_type: str
    workspace_path: str
    user_goal: str
    node_goal: str
    sandbox_mode: str = "workspace-write"
    context_files: tuple[str, ...] = ()
    allowed_tools: tuple[str, ...] = ()
    risk_policy: ExternalExecutorRiskPolicy = field(default_factory=ExternalExecutorRiskPolicy)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": _clean_str(self.project_id),
            "chat_session_id": _clean_str(self.chat_session_id),
            "session_id": _clean_str(self.session_id),
            "requirement_id": _clean_str(self.requirement_id),
            "task_tree_id": _clean_str(self.task_tree_id),
            "task_node_id": _clean_str(self.task_node_id),
            "executor_type": normalize_external_executor_type(self.executor_type),
            "workspace_path": _clean_str(self.workspace_path),
            "sandbox_mode": _clean_str(self.sandbox_mode) or "workspace-write",
            "user_goal": _clean_str(self.user_goal),
            "node_goal": _clean_str(self.node_goal),
            "context_files": list(self.context_files),
            "allowed_tools": list(self.allowed_tools),
            "risk_policy": self.risk_policy.to_dict(),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ExternalExecutorTaskInput":
        source = payload if isinstance(payload, dict) else {}
        return cls(
            project_id=_clean_str(source.get("project_id")),
            chat_session_id=_clean_str(source.get("chat_session_id")),
            session_id=_clean_str(source.get("session_id")),
            requirement_id=_clean_str(source.get("requirement_id")),
            task_tree_id=_clean_str(source.get("task_tree_id")),
            task_node_id=_clean_str(source.get("task_node_id")),
            executor_type=normalize_external_executor_type(source.get("executor_type")),
            workspace_path=_clean_str(source.get("workspace_path")),
            sandbox_mode=_clean_str(source.get("sandbox_mode")) or "workspace-write",
            user_goal=_clean_str(source.get("user_goal")),
            node_goal=_clean_str(source.get("node_goal")),
            context_files=tuple(_string_list(source.get("context_files"))),
            allowed_tools=tuple(_string_list(source.get("allowed_tools"))),
            risk_policy=ExternalExecutorRiskPolicy.from_dict(
                source.get("risk_policy") if isinstance(source.get("risk_policy"), dict) else None
            ),
            metadata=dict(source.get("metadata") or {})
            if isinstance(source.get("metadata"), dict)
            else {},
        )


@dataclass(frozen=True)
class ExternalExecutorEvent:
    event_type: str
    task_node_id: str = ""
    executor_type: str = ""
    status: str = ""
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        normalized_event_type = normalize_external_executor_event_type(self.event_type)
        return {
            "type": normalized_event_type,
            "task_node_id": _clean_str(self.task_node_id),
            "executor_type": normalize_external_executor_type(self.executor_type),
            "status": normalize_external_executor_status(
                self.status or _status_from_event_type(normalized_event_type)
            ),
            "message": _clean_str(self.message),
            "data": dict(self.data),
        }

    @classmethod
    def from_runner_event(
        cls,
        payload: dict[str, Any],
        *,
        task_node_id: str = "",
        executor_type: str = ExternalExecutorType.CODEX_CLI.value,
    ) -> "ExternalExecutorEvent":
        source = payload if isinstance(payload, dict) else {}
        raw_type = _clean_str(source.get("type"))
        event_type = normalize_external_executor_event_type(raw_type)
        status = _status_from_event_type(event_type)
        if raw_type == "exit":
            returncode = source.get("returncode")
            status = (
                ExternalExecutorStatus.COMPLETED.value
                if returncode == 0
                else ExternalExecutorStatus.FAILED.value
            )
            event_type = (
                ExternalExecutorEventType.COMPLETED.value
                if returncode == 0
                else ExternalExecutorEventType.FAILED.value
            )
        message = _clean_str(
            source.get("message")
            or source.get("data")
            or source.get("reason")
            or source.get("error")
        )
        return cls(
            event_type=event_type,
            task_node_id=task_node_id,
            executor_type=executor_type,
            status=status,
            message=message,
            data=dict(source),
        )


def _status_from_event_type(event_type: str) -> str:
    normalized = normalize_external_executor_event_type(event_type)
    if normalized == ExternalExecutorEventType.WAITING_USER_ACTION.value:
        return ExternalExecutorStatus.WAITING_USER_ACTION.value
    if normalized == ExternalExecutorEventType.RESUMING.value:
        return ExternalExecutorStatus.RESUMING.value
    if normalized == ExternalExecutorEventType.VERIFYING.value:
        return ExternalExecutorStatus.VERIFYING.value
    if normalized == ExternalExecutorEventType.COMPLETED.value:
        return ExternalExecutorStatus.COMPLETED.value
    if normalized == ExternalExecutorEventType.FAILED.value:
        return ExternalExecutorStatus.FAILED.value
    return ExternalExecutorStatus.IN_PROGRESS.value


@dataclass(frozen=True)
class ExternalExecutorResult:
    status: str
    summary: str = ""
    changed_files: tuple[str, ...] = ()
    commands: tuple[dict[str, Any], ...] = ()
    verification: tuple[dict[str, Any], ...] = ()
    risks: tuple[str, ...] = ()
    next_steps: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        return normalize_external_executor_status(self.status) == ExternalExecutorStatus.COMPLETED.value

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": normalize_external_executor_status(self.status),
            "summary": _clean_str(self.summary),
            "changed_files": list(self.changed_files),
            "commands": [dict(item) for item in self.commands],
            "verification": [dict(item) for item in self.verification],
            "risks": list(self.risks),
            "next_steps": list(self.next_steps),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ExternalExecutorResult":
        source = payload if isinstance(payload, dict) else {}
        return cls(
            status=normalize_external_executor_status(source.get("status")),
            summary=_clean_str(source.get("summary")),
            changed_files=tuple(_string_list(source.get("changed_files"))),
            commands=tuple(_dict_list(source.get("commands"))),
            verification=tuple(_dict_list(source.get("verification"))),
            risks=tuple(_string_list(source.get("risks"))),
            next_steps=tuple(_string_list(source.get("next_steps"))),
            metadata=dict(source.get("metadata") or {})
            if isinstance(source.get("metadata"), dict)
            else {},
        )

    def task_tree_verification_result(self) -> str:
        parts = []
        if self.summary:
            parts.append(_clean_str(self.summary))
        if self.changed_files:
            parts.append("Changed files: " + ", ".join(self.changed_files))
        if self.verification:
            labels = [
                _clean_str(item.get("summary") or item.get("command") or item.get("name"))
                for item in self.verification
                if _clean_str(item.get("summary") or item.get("command") or item.get("name"))
            ]
            if labels:
                parts.append("Verification: " + "; ".join(labels))
        if self.risks:
            parts.append("Risks: " + "; ".join(self.risks))
        return "\n".join(parts).strip()


@dataclass(frozen=True)
class ExternalExecutorSelectionDecision:
    executor_type: str
    reason: str
    alternatives: tuple[dict[str, Any], ...] = ()
    permissions: dict[str, Any] = field(default_factory=dict)
    verification_plan: tuple[str, ...] = ()
    requires_user_confirmation: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "executor_type": normalize_external_executor_type(self.executor_type),
            "reason": _clean_str(self.reason),
            "alternatives": [dict(item) for item in self.alternatives],
            "permissions": dict(self.permissions),
            "verification_plan": list(self.verification_plan),
            "requires_user_confirmation": bool(self.requires_user_confirmation),
        }


__all__ = [
    "ExternalExecutorEvent",
    "ExternalExecutorEventType",
    "ExternalExecutorResult",
    "ExternalExecutorRiskPolicy",
    "ExternalExecutorSelectionDecision",
    "ExternalExecutorStatus",
    "ExternalExecutorTaskInput",
    "ExternalExecutorType",
    "normalize_external_executor_event_type",
    "normalize_external_executor_status",
    "normalize_external_executor_type",
]
