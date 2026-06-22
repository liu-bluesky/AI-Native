"""Canonical protocol checks for liuAgent V0.1.

The existing runtime already owns execution. This module only owns the protocol
contract so future adapters do not each invent their own event and command
shape.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


AGENT_EVENT_TYPES = {
    "message_delta",
    "message_completed",
    "approval_required",
    "open_url",
    "tool_started",
    "tool_result",
    "state_changed",
    "error",
}

ADAPTER_COMMAND_TYPES = {
    "permission_decision",
    "open_url_done",
    "submit_text",
    "cancel",
    "resume",
}

IDEMPOTENT_COMMAND_TYPES = {
    "permission_decision",
    "open_url_done",
    "cancel",
    "resume",
}

GRANT_SCOPES = {"once", "run", "session", "workspace"}

APPROVAL_DECISION_TO_SCOPE = {
    "approve_once": "once",
    "approve_run": "run",
    "approve_session": "session",
    "approve_workspace": "workspace",
}

PERMISSION_DECISION_VALUES = {
    *APPROVAL_DECISION_TO_SCOPE.keys(),
    "deny",
    "revise",
}

WAITING_FOR_VALUES = {
    "model",
    "tool",
    "approval",
    "user",
    "adapter_action",
}


class ContractError(ValueError):
    """Raised when a runtime payload violates the shared protocol contract."""


def _clean_str(value: Any) -> str:
    return str(value or "").strip()


def _require_mapping(value: Any, *, field_name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{field_name} must be an object")
    return dict(value)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_agent_event(
    *,
    event_type: str,
    session_id: str,
    payload: Mapping[str, Any] | None = None,
    run_id: str = "",
    event_id: str = "",
    created_at: str = "",
) -> dict[str, Any]:
    """Build a full AgentEvent envelope and validate it before returning.

    中文注释：事件不能只传 payload。CLI、Web、Desktop 都需要同一组追踪字段，
    否则后续 replay、审计和 UI 去重会各自猜字段。
    """

    event = {
        "event_id": _clean_str(event_id) or f"evt_{uuid4().hex[:16]}",
        "type": _clean_str(event_type),
        "session_id": _clean_str(session_id),
        "run_id": _clean_str(run_id),
        "created_at": _clean_str(created_at) or _utc_now_iso(),
        "payload": dict(payload or {}),
    }
    return validate_agent_event(event)


def validate_agent_event(event: Mapping[str, Any]) -> dict[str, Any]:
    payload = _require_mapping(event, field_name="event")
    event_type = _clean_str(payload.get("type") or payload.get("event_type"))
    if event_type not in AGENT_EVENT_TYPES:
        raise ContractError(f"unsupported event type: {event_type or '<empty>'}")
    normalized = {
        "event_id": _clean_str(payload.get("event_id")),
        "type": event_type,
        "session_id": _clean_str(payload.get("session_id")),
        "run_id": _clean_str(payload.get("run_id")),
        "created_at": _clean_str(payload.get("created_at")),
        "payload": _require_mapping(payload.get("payload"), field_name="event.payload"),
    }
    for field_name in ("event_id", "session_id", "created_at"):
        if not normalized[field_name]:
            raise ContractError(f"{field_name} is required")
    if event_type == "state_changed":
        normalized["payload"] = validate_state_changed_payload(normalized["payload"])
    return normalized


def validate_permission_option(option: Mapping[str, Any]) -> dict[str, Any]:
    payload = _require_mapping(option, field_name="permission option")
    decision = _clean_str(payload.get("decision"))
    if decision not in PERMISSION_DECISION_VALUES:
        raise ContractError(f"unsupported permission decision: {decision or '<empty>'}")
    grant_scope = _clean_str(payload.get("grant_scope"))

    # 中文注释：批准类按钮必须显式绑定授权范围，拒绝/修改不能携带授权范围。
    expected_scope = APPROVAL_DECISION_TO_SCOPE.get(decision)
    if expected_scope:
        if grant_scope != expected_scope:
            raise ContractError(
                f"{decision} must use grant_scope={expected_scope}"
            )
    elif grant_scope:
        raise ContractError(f"{decision} must not include grant_scope")
    if grant_scope and grant_scope not in GRANT_SCOPES:
        raise ContractError(f"unsupported grant_scope: {grant_scope}")
    label = _clean_str(payload.get("label"))
    if not label:
        raise ContractError("permission option label is required")
    normalized = {
        "decision": decision,
        "label": label,
        "is_default": bool(payload.get("is_default", False)),
    }
    if grant_scope:
        normalized["grant_scope"] = grant_scope
    return normalized


def validate_permission_decision_against_options(
    decision_payload: Mapping[str, Any],
    options: list[Mapping[str, Any]],
) -> dict[str, Any]:
    decision = _require_mapping(decision_payload, field_name="permission decision")
    normalized_options = [validate_permission_option(item) for item in options]
    decision_value = _clean_str(decision.get("decision"))
    grant_scope = _clean_str(decision.get("grant_scope"))

    # 中文注释：用户回传必须命中当时展示过的结构化选项，避免 UI 文案或越权范围进入协议层。
    for option in normalized_options:
        if option["decision"] != decision_value:
            continue
        if _clean_str(option.get("grant_scope")) == grant_scope:
            return {
                **decision,
                "decision": decision_value,
                **({"grant_scope": grant_scope} if grant_scope else {}),
            }
    raise ContractError("permission decision does not match presented options")


def validate_adapter_command(command: Mapping[str, Any]) -> dict[str, Any]:
    payload = _require_mapping(command, field_name="adapter command")
    command_type = _clean_str(payload.get("type"))
    if command_type not in ADAPTER_COMMAND_TYPES:
        raise ContractError(f"unsupported adapter command type: {command_type or '<empty>'}")
    command_id = _clean_str(payload.get("command_id"))
    if not command_id:
        raise ContractError("command_id is required")
    command_payload = _require_mapping(
        payload.get("payload"),
        field_name="adapter command payload",
    )
    idempotency_key = _clean_str(payload.get("idempotency_key"))
    if command_type in IDEMPOTENT_COMMAND_TYPES and not idempotency_key:
        raise ContractError(f"{command_type} requires idempotency_key")
    payload_key = _clean_str(command_payload.get("idempotency_key"))
    if payload_key and idempotency_key and payload_key != idempotency_key:
        raise ContractError("payload idempotency_key must match command idempotency_key")
    if command_type == "permission_decision":
        options = command_payload.get("options")
        if isinstance(options, list):
            validate_permission_decision_against_options(command_payload, options)
    return {
        "command_id": command_id,
        "type": command_type,
        "idempotency_key": idempotency_key,
        "payload": command_payload,
    }


def validate_state_changed_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    state = _require_mapping(payload, field_name="state_changed payload")
    from_status = _clean_str(state.get("from"))
    to_status = _clean_str(state.get("to"))
    if not from_status or not to_status:
        raise ContractError("state_changed payload requires from and to")
    waiting_for = _clean_str(state.get("waiting_for"))
    pending_request_id = _clean_str(state.get("pending_request_id"))
    pending_tool_batch_id = _clean_str(state.get("pending_tool_batch_id"))
    pending_adapter_action_id = _clean_str(state.get("pending_adapter_action_id"))
    raw_tool_ids = state.get("pending_tool_call_ids")
    pending_tool_call_ids = [
        _clean_str(item)
        for item in (raw_tool_ids if isinstance(raw_tool_ids, list) else [])
        if _clean_str(item)
    ]

    if waiting_for and waiting_for not in WAITING_FOR_VALUES:
        raise ContractError(f"unsupported waiting_for: {waiting_for}")

    # 中文注释：pending 字段是恢复入口，必须和 waiting_for 一一对应，不能混用。
    if waiting_for == "approval" and not pending_request_id:
        raise ContractError("waiting_for=approval requires pending_request_id")
    if waiting_for == "tool" and not (pending_tool_call_ids or pending_tool_batch_id):
        raise ContractError("waiting_for=tool requires pending tool ids")
    if waiting_for in {"user", "adapter_action"} and not pending_adapter_action_id:
        raise ContractError(
            f"waiting_for={waiting_for} requires pending_adapter_action_id"
        )
    if waiting_for != "approval" and pending_request_id:
        raise ContractError("pending_request_id is only valid for approval waits")
    if waiting_for != "tool" and (pending_tool_call_ids or pending_tool_batch_id):
        raise ContractError("pending tool fields are only valid for tool waits")
    if waiting_for not in {"user", "adapter_action"} and pending_adapter_action_id:
        raise ContractError(
            "pending_adapter_action_id is only valid for user or adapter_action waits"
        )

    return {
        "from": from_status,
        "to": to_status,
        "waiting_for": waiting_for or None,
        "pending_request_id": pending_request_id or None,
        "pending_tool_call_ids": pending_tool_call_ids,
        "pending_tool_batch_id": pending_tool_batch_id or None,
        "pending_adapter_action_id": pending_adapter_action_id or None,
    }
