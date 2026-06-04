"""Delegation boundaries for v2 runtime subagent support."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


DEFAULT_BLOCKED_DELEGATION_TOOLS = (
    "delegate_task",
    "clarify",
    "memory",
    "send_message",
    "execute_code",
)


@dataclass(frozen=True)
class DelegationPolicy:
    max_parallel: int = 3
    max_depth: int = 1
    blocked_tools: tuple[str, ...] = DEFAULT_BLOCKED_DELEGATION_TOOLS
    default_toolsets: tuple[str, ...] = ("terminal", "file", "web")

    def allows_depth(self, depth: int) -> bool:
        return int(depth) <= int(self.max_depth)

    def allowed_tools(self, tool_names: list[str] | tuple[str, ...]) -> tuple[str, ...]:
        blocked = set(self.blocked_tools)
        return tuple(name for name in tool_names if name not in blocked)


@dataclass(frozen=True)
class DelegationTask:
    task_id: str
    goal: str
    context: str = ""
    toolsets: tuple[str, ...] = ()
    parent_run_id: str = ""
    depth: int = 1
    max_iterations: int = 50
    metadata: dict[str, Any] = field(default_factory=dict)

    def runtime_input(self, policy: DelegationPolicy | None = None) -> dict[str, Any]:
        effective_policy = policy or DelegationPolicy()
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "context": self.context,
            "toolsets": list(self.toolsets or effective_policy.default_toolsets),
            "parent_run_id": self.parent_run_id,
            "depth": self.depth,
            "max_iterations": self.max_iterations,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class DelegationResult:
    task_id: str
    status: str
    summary: str = ""
    changed_files: tuple[str, ...] = ()
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        return self.status in {"completed", "succeeded", "done"}


class DelegationExecutor(Protocol):
    def execute(self, tasks: tuple[DelegationTask, ...]) -> tuple[DelegationResult, ...]:
        ...


class DelegationPlanner:
    """Builds bounded delegation tasks without owning execution."""

    def __init__(self, policy: DelegationPolicy | None = None):
        self.policy = policy or DelegationPolicy()

    def plan_single(
        self,
        goal: str,
        *,
        task_id: str = "delegate-1",
        context: str = "",
        toolsets: tuple[str, ...] = (),
        parent_run_id: str = "",
        depth: int = 1,
        metadata: dict[str, Any] | None = None,
    ) -> DelegationTask:
        if not self.policy.allows_depth(depth):
            raise ValueError("delegation depth exceeds policy")
        return DelegationTask(
            task_id=task_id,
            goal=goal,
            context=context,
            toolsets=toolsets or self.policy.default_toolsets,
            parent_run_id=parent_run_id,
            depth=depth,
            metadata=dict(metadata or {}),
        )

    def plan_batch(
        self,
        goals: list[str] | tuple[str, ...],
        *,
        context: str = "",
        toolsets: tuple[str, ...] = (),
        parent_run_id: str = "",
        depth: int = 1,
    ) -> tuple[DelegationTask, ...]:
        if len(goals) > self.policy.max_parallel:
            raise ValueError("delegation batch exceeds max_parallel policy")
        return tuple(
            self.plan_single(
                goal,
                task_id=f"delegate-{index}",
                context=context,
                toolsets=toolsets,
                parent_run_id=parent_run_id,
                depth=depth,
            )
            for index, goal in enumerate(goals, start=1)
        )


__all__ = [
    "DEFAULT_BLOCKED_DELEGATION_TOOLS",
    "DelegationExecutor",
    "DelegationPlanner",
    "DelegationPolicy",
    "DelegationResult",
    "DelegationTask",
]
