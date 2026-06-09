"""Runtime capability contract for Hermes-grade agent platform features."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


CAPABILITY_STATUS_PLANNED = "planned"
CAPABILITY_STATUS_PARTIAL = "partial"
CAPABILITY_STATUS_AVAILABLE = "available"


@dataclass(frozen=True)
class RuntimeCapability:
    capability_id: str
    name: str
    category: str
    status: str
    phase: int
    summary: str
    modules: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    acceptance: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "name": self.name,
            "category": self.category,
            "status": self.status,
            "phase": self.phase,
            "summary": self.summary,
            "modules": list(self.modules),
            "dependencies": list(self.dependencies),
            "acceptance": list(self.acceptance),
        }


@dataclass(frozen=True)
class RuntimeCapabilityCatalog:
    capabilities: tuple[RuntimeCapability, ...] = field(default_factory=tuple)

    def ids(self) -> list[str]:
        return [item.capability_id for item in self.capabilities]

    def get(self, capability_id: str) -> RuntimeCapability | None:
        target = str(capability_id or "").strip()
        for item in self.capabilities:
            if item.capability_id == target:
                return item
        return None

    def by_phase(self) -> dict[int, list[dict[str, Any]]]:
        grouped: dict[int, list[dict[str, Any]]] = {}
        for item in self.capabilities:
            grouped.setdefault(item.phase, []).append(item.to_dict())
        return grouped

    def by_category(self) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for item in self.capabilities:
            grouped.setdefault(item.category, []).append(item.to_dict())
        return grouped

    def summary(self) -> dict[str, Any]:
        status_counts: dict[str, int] = {}
        for item in self.capabilities:
            status_counts[item.status] = status_counts.get(item.status, 0) + 1
        return {
            "capability_total": len(self.capabilities),
            "status_counts": status_counts,
            "capability_ids": self.ids(),
            "phases": sorted({item.phase for item in self.capabilities}),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.summary(),
            "capabilities": [item.to_dict() for item in self.capabilities],
        }


def default_hermes_runtime_capability_catalog() -> RuntimeCapabilityCatalog:
    """Return the canonical roadmap contract for the in-product agent runtime."""

    return RuntimeCapabilityCatalog(
        capabilities=(
            RuntimeCapability(
                capability_id="agent_loop",
                name="Agent Loop",
                category="runtime_core",
                status=CAPABILITY_STATUS_PARTIAL,
                phase=1,
                summary="Run model steps, execute tools, append observations, and decide completion state.",
                modules=("services.agent_runtime.v2.query_engine",),
                acceptance=("complete/retry/blocked/waiting states are explicit",),
            ),
            RuntimeCapability(
                capability_id="provider_adapter",
                name="Provider Adapter",
                category="model_io",
                status=CAPABILITY_STATUS_PLANNED,
                phase=2,
                summary="Normalize provider streaming chunks, tool calls, usage, and errors before runtime consumption.",
                modules=("services.agent_runtime.v2.llm_step",),
                dependencies=("agent_loop",),
                acceptance=("QueryEngine consumes a stable provider-neutral step result",),
            ),
            RuntimeCapability(
                capability_id="tool_registry",
                name="Tool Registry",
                category="tools",
                status=CAPABILITY_STATUS_PARTIAL,
                phase=3,
                summary="Register built-in, project, MCP, plugin, browser, skill, and connector tools with source metadata.",
                modules=("services.agent_runtime.shared.tool_registry",),
                dependencies=("agent_loop",),
                acceptance=("Every runtime tool has a stable name, source, availability, trust state, and schema",),
            ),
            RuntimeCapability(
                capability_id="tool_permission_approval",
                name="Tool Permission Approval",
                category="security",
                status=CAPABILITY_STATUS_PARTIAL,
                phase=3,
                summary="Classify tool risk, request approval when needed, and resume execution after user decisions.",
                modules=(
                    "services.agent_runtime.v2.permission_policy",
                    "services.agent_runtime.v2.permission_store",
                ),
                dependencies=("tool_registry",),
                acceptance=("High-risk tools cannot bypass approval policy",),
            ),
            RuntimeCapability(
                capability_id="builtin_tools",
                name="Terminal/File/Browser/Search Tools",
                category="tools",
                status=CAPABILITY_STATUS_PARTIAL,
                phase=3,
                summary="Expose core local and browser tools through the same schema, permission, and result pipeline.",
                modules=("services.tool_executor", "services.agent_runtime.v2.browser_tool_loader"),
                dependencies=("tool_registry", "tool_permission_approval"),
                acceptance=("Core tools produce normalized ToolObservation records",),
            ),
            RuntimeCapability(
                capability_id="skills",
                name="Skills",
                category="knowledge",
                status=CAPABILITY_STATUS_PARTIAL,
                phase=4,
                summary="Discover, validate, and inject reusable skill instructions and slash commands.",
                modules=("services.agent_runtime.shared.skill_registry",),
                dependencies=("agent_loop",),
                acceptance=("Runtime can list available skills and missing dependency hints",),
            ),
            RuntimeCapability(
                capability_id="memory",
                name="Memory",
                category="knowledge",
                status=CAPABILITY_STATUS_PARTIAL,
                phase=4,
                summary="Persist user preferences, project facts, work facts, and retrieval provenance.",
                modules=("services.agent_runtime.core.memory",),
                dependencies=("session_management",),
                acceptance=("Memory injection is scoped and auditable",),
            ),
            RuntimeCapability(
                capability_id="session_management",
                name="Session Management",
                category="state",
                status=CAPABILITY_STATUS_PARTIAL,
                phase=4,
                summary="Persist task runs, transcripts, event logs, and resume context per project chat session.",
                modules=(
                    "services.agent_runtime.core.state_store",
                    "services.agent_runtime.core.transcript_store",
                    "services.agent_runtime.core.event_log",
                ),
                dependencies=("agent_loop",),
                acceptance=("A task run can be inspected and resumed without tool-only content pollution",),
            ),
            RuntimeCapability(
                capability_id="context_compression",
                name="Context Compression",
                category="state",
                status=CAPABILITY_STATUS_PLANNED,
                phase=4,
                summary="Summarize long transcripts into checkpoints while preserving audit records.",
                dependencies=("session_management", "memory"),
                acceptance=("Long-running sessions can continue from checkpoint summaries",),
            ),
            RuntimeCapability(
                capability_id="mcp",
                name="MCP",
                category="integrations",
                status=CAPABILITY_STATUS_PARTIAL,
                phase=5,
                summary="Register MCP tools, resources, and prompts as first-class runtime capabilities.",
                dependencies=("tool_registry", "tool_permission_approval"),
                acceptance=("MCP tools execute through the same registry and approval pipeline",),
            ),
            RuntimeCapability(
                capability_id="gateway",
                name="Gateway",
                category="integrations",
                status=CAPABILITY_STATUS_PARTIAL,
                phase=5,
                summary="Route external messages into project runtime sessions and structured responses.",
                modules=("services.agent_runtime.integrations.gateway",),
                dependencies=("session_management",),
                acceptance=("Gateway messages can create or resume TaskRun records",),
            ),
            RuntimeCapability(
                capability_id="cron",
                name="Cron",
                category="automation",
                status=CAPABILITY_STATUS_PLANNED,
                phase=5,
                summary="Schedule prompts or scripts with persisted context, delivery target, and last output.",
                dependencies=("gateway", "session_management"),
                acceptance=("Cron executions write transcript and delivery events",),
            ),
            RuntimeCapability(
                capability_id="background_process",
                name="Subprocess/Background Process",
                category="execution",
                status=CAPABILITY_STATUS_PARTIAL,
                phase=6,
                summary="Track long-running commands, logs, user waits, cancellation, and resume handles.",
                modules=("services.operation_wait_task_service",),
                dependencies=("tool_permission_approval", "session_management"),
                acceptance=("Background work exposes status, log cursor, cancel, and resume metadata",),
            ),
            RuntimeCapability(
                capability_id="multi_platform_messages",
                name="Multi-platform Messages",
                category="integrations",
                status=CAPABILITY_STATUS_PLANNED,
                phase=5,
                summary="Deliver runtime outputs to Feishu first, then other messaging backends through a stable interface.",
                dependencies=("gateway",),
                acceptance=("Delivery result is recorded with target, status, and error summary",),
            ),
            RuntimeCapability(
                capability_id="configuration_system",
                name="Configuration System",
                category="platform",
                status=CAPABILITY_STATUS_PARTIAL,
                phase=2,
                summary="Validate provider, tool, approval, gateway, and runtime settings for API and UI consumption.",
                modules=("core.config",),
                acceptance=("Runtime settings can be serialized with validation errors and restart hints",),
            ),
            RuntimeCapability(
                capability_id="error_recovery_state_machine",
                name="Error Recovery and State Machine",
                category="runtime_core",
                status=CAPABILITY_STATUS_PARTIAL,
                phase=6,
                summary="Represent failures, retries, waiting states, approvals, and recovery with explicit reasons.",
                modules=(
                    "services.agent_runtime.shared.completion_policy",
                    "services.agent_runtime.v2.operation_resume",
                ),
                dependencies=("agent_loop", "background_process"),
                acceptance=("Every non-complete state has a machine-readable reason and user-facing next step",),
            ),
        )
    )
