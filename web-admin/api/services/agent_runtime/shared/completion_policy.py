"""Completion gate shared by agent runtime implementations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from services.agent_runtime.shared.tool_results import ToolObservation
from services.agent_runtime.shared.verification_policy import VerificationState


@dataclass
class CompletionDecision:
    action: str
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"action": self.action, "reasons": list(self.reasons)}


class CompletionPolicy:
    def evaluate(
        self,
        *,
        response_content: str = "",
        pending_operations: list[dict[str, Any]] | None = None,
        pending_user_actions: list[dict[str, Any]] | None = None,
        latest_observation: ToolObservation | None = None,
        verification: VerificationState | None = None,
        task_tree_verified: bool = False,
        goal_covered: bool = False,
    ) -> CompletionDecision:
        reasons: list[str] = []
        if not str(response_content or "").strip():
            return CompletionDecision("retry_model", ["empty_model_response"])
        if pending_operations:
            return CompletionDecision("wait_background", ["pending_background_operation"])
        if pending_user_actions:
            return CompletionDecision("request_user", ["pending_user_action"])
        if latest_observation is not None and latest_observation.is_error:
            return CompletionDecision("fail", ["latest_tool_observation_failed"])
        if verification is not None and not verification.satisfied:
            return CompletionDecision("verify", ["verification_required"])
        if not task_tree_verified:
            reasons.append("task_tree_not_verified")
        if not goal_covered:
            reasons.append("goal_not_confirmed")
        if reasons:
            return CompletionDecision("continue", reasons)
        return CompletionDecision("complete", ["completion_gate_satisfied"])
