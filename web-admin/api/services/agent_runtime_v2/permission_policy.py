"""Permission policy for agent_runtime_v2."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from services.agent_runtime_v2.permission_store import (
    DENY_BEHAVIOR,
    PermissionDecision,
    PermissionStore,
)


_SENSITIVE_COMMAND_TERMS = (
    " rm ",
    "rm -",
    "sudo ",
    "chmod ",
    "chown ",
    "git reset",
    "git clean",
    "docker stop",
    "docker rm",
    "kill -9",
)


class PermissionPolicy:
    def __init__(self, store: PermissionStore | None = None):
        self._store = store or PermissionStore()

    def evaluate(
        self,
        *,
        run_id: str,
        call_id: str,
        tool_name: str,
        args: dict[str, Any] | None = None,
        project_id: str = "",
        username: str = "",
        chat_session_id: str = "",
        workspace_trusted: bool = True,
    ) -> PermissionDecision:
        normalized_tool = str(tool_name or "").strip()
        payload = dict(args or {})
        matched_rule = self._match_rule(
            run_id=run_id,
            call_id=call_id,
            tool_name=normalized_tool,
            args=payload,
            project_id=project_id,
            username=username,
            chat_session_id=chat_session_id,
        )
        risk_level = self._risk_level(normalized_tool, payload)
        if matched_rule is not None and matched_rule.behavior == DENY_BEHAVIOR:
            return self._record(
                run_id=run_id,
                call_id=call_id,
                tool_name=normalized_tool,
                behavior="deny",
                risk_level=risk_level,
                reason="matched deny rule",
                matched_rule=matched_rule.to_dict(),
            )
        if self._requires_trust(normalized_tool) and not workspace_trusted:
            return self._record(
                run_id=run_id,
                call_id=call_id,
                tool_name=normalized_tool,
                behavior="ask",
                risk_level="high",
                reason="workspace is not trusted",
                matched_rule=None,
            )
        if matched_rule is not None:
            return self._record(
                run_id=run_id,
                call_id=call_id,
                tool_name=normalized_tool,
                behavior=matched_rule.behavior,
                risk_level=risk_level,
                reason="matched permission rule",
                matched_rule=matched_rule.to_dict(),
            )
        if risk_level in {"high", "critical"}:
            behavior = "ask"
        else:
            behavior = "allow_once"
        return self._record(
            run_id=run_id,
            call_id=call_id,
            tool_name=normalized_tool,
            behavior=behavior,
            risk_level=risk_level,
            reason="default policy",
            matched_rule=None,
        )

    def _match_rule(
        self,
        *,
        run_id: str,
        call_id: str,
        tool_name: str,
        args: dict[str, Any],
        project_id: str,
        username: str,
        chat_session_id: str,
    ):
        matching = [
            rule
            for rule in self._store.list_rules()
            if rule.matches(
                tool_name=tool_name,
                args=args,
                project_id=project_id,
                username=username,
                chat_session_id=chat_session_id,
                run_id=run_id,
                call_id=call_id,
            )
        ]
        if not matching:
            return None
        deny = [rule for rule in matching if rule.behavior == DENY_BEHAVIOR]
        if deny:
            return deny[-1]
        return matching[-1]

    def _record(
        self,
        *,
        run_id: str,
        call_id: str,
        tool_name: str,
        behavior: str,
        risk_level: str,
        reason: str,
        matched_rule: dict[str, Any] | None,
    ) -> PermissionDecision:
        decision = PermissionDecision(
            decision_id=f"perm_{uuid4().hex[:16]}",
            run_id=str(run_id or "").strip(),
            call_id=str(call_id or "").strip(),
            tool_name=tool_name,
            behavior=behavior,
            risk_level=risk_level,
            reason=reason,
            matched_rule=matched_rule,
        )
        return self._store.record_decision(decision)

    def _requires_trust(self, tool_name: str) -> bool:
        return tool_name in {"project_host_run_command"} or tool_name.startswith("local_connector_")

    def _risk_level(self, tool_name: str, args: dict[str, Any]) -> str:
        if tool_name == "project_host_run_command":
            command = f" {str(args.get('command') or '').strip().lower()} "
            if any(term in command for term in _SENSITIVE_COMMAND_TERMS):
                return "high"
            return "medium"
        if tool_name.startswith("local_connector_write"):
            return "medium"
        return "low"
