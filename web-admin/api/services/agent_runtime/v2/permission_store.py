"""Permission decision and rule store for agent_runtime_v2."""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from core.config import get_project_root
from services.agent_runtime.core.task_run import utc_now_iso


ALLOW_BEHAVIORS = {"allow_once", "allow_session", "allow_always"}
DENY_BEHAVIOR = "deny"

_LARK_CLI_STABLE_SUBCOMMANDS = {
    ("auth", "status"),
    ("auth", "login"),
}


def normalize_permission_command(command: str) -> str:
    normalized = str(command or "").strip()
    if not normalized:
        return ""
    try:
        parts = shlex.split(normalized)
    except ValueError:
        parts = normalized.split()
    if not parts:
        return ""
    binary = Path(str(parts[0])).name
    if binary == "lark-cli" and len(parts) >= 3:
        subcommand = (str(parts[1]).strip(), str(parts[2]).strip())
        if subcommand in _LARK_CLI_STABLE_SUBCOMMANDS:
            return " ".join(["lark-cli", subcommand[0], subcommand[1], *parts[3:]])
    return re.sub(r"\s+", " ", normalized)


def permission_command_signature(command: str) -> str:
    normalized = normalize_permission_command(command)
    if not normalized:
        return ""
    try:
        parts = shlex.split(normalized)
    except ValueError:
        parts = normalized.split()
    if len(parts) >= 3 and Path(str(parts[0])).name == "lark-cli":
        subcommand = (str(parts[1]).strip(), str(parts[2]).strip())
        if subcommand in _LARK_CLI_STABLE_SUBCOMMANDS:
            return " ".join(["lark-cli", subcommand[0], subcommand[1]])
    return normalized


@dataclass
class PermissionRule:
    rule_id: str
    behavior: str
    tool_name: str = ""
    scope: str = "session"
    project_id: str = ""
    username: str = ""
    chat_session_id: str = ""
    matcher: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)

    def matches(
        self,
        *,
        tool_name: str,
        project_id: str,
        username: str,
        chat_session_id: str,
        run_id: str = "",
        call_id: str = "",
        args: dict[str, Any] | None = None,
    ) -> bool:
        if self.tool_name and self.tool_name != str(tool_name or "").strip():
            return False
        if self.project_id and self.project_id != str(project_id or "").strip():
            return False
        if self.username and self.username != str(username or "").strip():
            return False
        if self.scope in {"once", "session"} and self.chat_session_id:
            if self.chat_session_id != str(chat_session_id or "").strip():
                return False
        matcher = dict(self.matcher or {})
        matcher_run_id = str(matcher.get("run_id") or "").strip()
        if matcher_run_id and matcher_run_id != str(run_id or "").strip():
            return False
        matcher_call_id = str(matcher.get("call_id") or "").strip()
        if matcher_call_id and matcher_call_id != str(call_id or "").strip():
            return False
        exact_command = normalize_permission_command(str(matcher.get("command_exact") or ""))
        if exact_command:
            command = normalize_permission_command(str((args or {}).get("command") or ""))
            return command == exact_command
        prefix = str(matcher.get("command_prefix") or "").strip()
        if prefix:
            command = normalize_permission_command(str((args or {}).get("command") or ""))
            return command.startswith(prefix)
        command_signature = str(matcher.get("command_signature") or "").strip()
        if command_signature:
            command = str((args or {}).get("command") or "").strip()
            return permission_command_signature(command) == command_signature
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "behavior": self.behavior,
            "tool_name": self.tool_name,
            "scope": self.scope,
            "project_id": self.project_id,
            "username": self.username,
            "chat_session_id": self.chat_session_id,
            "matcher": dict(self.matcher),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PermissionRule":
        return cls(
            rule_id=str(payload.get("rule_id") or f"perm_rule_{uuid4().hex[:16]}").strip(),
            behavior=str(payload.get("behavior") or "").strip(),
            tool_name=str(payload.get("tool_name") or "").strip(),
            scope=str(payload.get("scope") or "session").strip() or "session",
            project_id=str(payload.get("project_id") or "").strip(),
            username=str(payload.get("username") or "").strip(),
            chat_session_id=str(payload.get("chat_session_id") or "").strip(),
            matcher=dict(payload.get("matcher") or {}),
            created_at=str(payload.get("created_at") or utc_now_iso()).strip(),
        )


@dataclass
class PermissionDecision:
    decision_id: str
    run_id: str
    call_id: str
    tool_name: str
    behavior: str
    risk_level: str = "low"
    reason: str = ""
    matched_rule: dict[str, Any] | None = None
    created_at: str = field(default_factory=utc_now_iso)

    @property
    def allowed(self) -> bool:
        return self.behavior in ALLOW_BEHAVIORS

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "run_id": self.run_id,
            "call_id": self.call_id,
            "tool_name": self.tool_name,
            "behavior": self.behavior,
            "risk_level": self.risk_level,
            "reason": self.reason,
            "matched_rule": self.matched_rule,
            "created_at": self.created_at,
        }


class PermissionStore:
    def __init__(self, root_path: Path | None = None):
        self._root_path = root_path or (
            get_project_root() / ".ai-employee" / "agent-runtime-v2" / "permissions"
        )

    def _rules_path(self) -> Path:
        return self._root_path / "rules.json"

    def _decisions_path(self, run_id: str) -> Path:
        return self._root_path / "decisions" / f"{str(run_id or '').strip()}.jsonl"

    def list_rules(self) -> list[PermissionRule]:
        path = self._rules_path()
        if not path.is_file():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return [
            PermissionRule.from_dict(item)
            for item in (payload if isinstance(payload, list) else [])
            if isinstance(item, dict)
        ]

    def save_rule(self, rule: PermissionRule) -> PermissionRule:
        rules = [item for item in self.list_rules() if item.rule_id != rule.rule_id]
        rules.append(rule)
        path = self._rules_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps([item.to_dict() for item in rules], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return rule

    def record_decision(self, decision: PermissionDecision) -> PermissionDecision:
        path = self._decisions_path(decision.run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(decision.to_dict(), ensure_ascii=False) + "\n")
        return decision
