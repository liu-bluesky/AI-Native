"""User-facing permission and trust actions for agent_runtime_v2."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from services.agent_runtime.core.event_log import RuntimeEventLog
from services.agent_runtime.v2.permission_store import (
    PermissionRule,
    PermissionStore,
    normalize_permission_command,
    permission_command_signature,
)
from services.agent_runtime.shared.trust_policy import TrustPolicy, WorkspaceTrust


ALLOW_ACTIONS = {"allow_once", "allow_session", "allow_always"}
PERMISSION_ACTIONS = ALLOW_ACTIONS | {"deny"}


class PermissionActionService:
    def __init__(
        self,
        *,
        permission_store: PermissionStore | None = None,
        trust_policy: TrustPolicy | None = None,
        event_log: RuntimeEventLog | None = None,
    ):
        self._permission_store = permission_store or PermissionStore()
        self._trust_policy = trust_policy or TrustPolicy()
        self._event_log = event_log or RuntimeEventLog()

    def apply_permission_action(
        self,
        *,
        action: str,
        run_id: str,
        call_id: str,
        tool_name: str,
        args: dict[str, Any] | None = None,
        project_id: str = "",
        username: str = "",
        chat_session_id: str = "",
    ) -> PermissionRule:
        normalized_action = str(action or "").strip().lower()
        if normalized_action not in PERMISSION_ACTIONS:
            raise ValueError("unsupported permission action")
        payload = dict(args or {})
        rule = PermissionRule(
            rule_id=f"perm_rule_{uuid4().hex[:16]}",
            behavior=normalized_action,
            tool_name=str(tool_name or "").strip(),
            scope=self._scope_for_action(normalized_action),
            project_id=str(project_id or "").strip(),
            username=str(username or "").strip(),
            chat_session_id=(
                str(chat_session_id or "").strip()
                if normalized_action in {"allow_once", "allow_session", "deny"}
                else ""
            ),
            matcher=self._matcher_for_action(
                action=normalized_action,
                run_id=run_id,
                call_id=call_id,
                args=payload,
            ),
        )
        self._permission_store.save_rule(rule)
        self._event_log.append(
            run_id,
            "permission_action_applied",
            {
                "action": normalized_action,
                "rule": rule.to_dict(),
                "call_id": str(call_id or "").strip(),
            },
        )
        return rule

    def trust_workspace(
        self,
        *,
        workspace_path: str,
        username: str,
        source: str = "project_chat",
        metadata: dict[str, Any] | None = None,
    ) -> WorkspaceTrust:
        return self._trust_policy.mark_trusted(
            workspace_path=workspace_path,
            username=username,
            source=source,
            metadata=metadata,
        )

    def get_workspace_trust(self, workspace_path: str) -> WorkspaceTrust:
        return self._trust_policy.ensure_workspace_trusted(workspace_path)

    def _scope_for_action(self, action: str) -> str:
        if action == "allow_once":
            return "once"
        if action in {"allow_session", "deny"}:
            return "session"
        return "project"

    def _matcher_for_action(
        self,
        *,
        action: str,
        run_id: str,
        call_id: str,
        args: dict[str, Any],
    ) -> dict[str, Any]:
        if action == "allow_once":
            return {
                "run_id": str(run_id or "").strip(),
                "call_id": str(call_id or "").strip(),
            }
        command = str(args.get("command") or "").strip()
        if command:
            signature = permission_command_signature(command)
            normalized_command = normalize_permission_command(command)
            if signature and signature != normalized_command:
                return {"command_signature": signature}
            return {"command_exact": normalized_command}
        return {}
