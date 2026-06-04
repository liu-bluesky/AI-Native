"""Shared verification gate for development-oriented TaskRuns."""

from __future__ import annotations

from dataclasses import dataclass, field


_DEVELOPMENT_TERMS = (
    "开发",
    "实现",
    "修复",
    "重构",
    "改代码",
    "测试",
    "部署",
    "build",
    "test",
    "fix",
    "implement",
    "refactor",
)


@dataclass
class VerificationEvidence:
    kind: str
    command: str = ""
    status: str = "unknown"
    summary: str = ""

    @property
    def passed(self) -> bool:
        return self.status in {"passed", "succeeded", "success", "skipped_with_reason"}

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "command": self.command,
            "status": self.status,
            "summary": self.summary,
        }


@dataclass
class VerificationState:
    required: bool = False
    evidence: list[VerificationEvidence] = field(default_factory=list)
    blocked_reason: str = ""

    @property
    def satisfied(self) -> bool:
        if not self.required:
            return True
        if self.blocked_reason:
            return True
        return any(item.passed for item in self.evidence)

    def to_dict(self) -> dict:
        return {
            "required": self.required,
            "satisfied": self.satisfied,
            "blocked_reason": self.blocked_reason,
            "evidence": [item.to_dict() for item in self.evidence],
        }


class VerificationPolicy:
    def build_state(
        self,
        *,
        user_goal: str,
        evidence: list[VerificationEvidence] | None = None,
        blocked_reason: str = "",
    ) -> VerificationState:
        goal = str(user_goal or "").lower()
        required = any(term.lower() in goal for term in _DEVELOPMENT_TERMS)
        return VerificationState(
            required=required,
            evidence=list(evidence or []),
            blocked_reason=str(blocked_reason or "").strip(),
        )

