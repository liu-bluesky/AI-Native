"""Shared runtime adapters for tools, prompts, artifacts, and LLM access."""

from services.agent_runtime.shared.completion_policy import CompletionDecision, CompletionPolicy
from services.agent_runtime.shared.tool_calls import CollectedToolCall, ToolCallCollector
from services.agent_runtime.shared.tool_execution_runner import (
    ToolExecutionRecord,
    ToolExecutionRunner,
)
from services.agent_runtime.core.task_run import TaskRun, new_run_id, utc_now_iso
from services.agent_runtime.core.transcript_store import TranscriptStore
from services.agent_runtime.shared.trust_policy import TrustPolicy, WorkspaceTrust
from services.agent_runtime.shared.verification_policy import (
    VerificationEvidence,
    VerificationPolicy,
    VerificationState,
)
from services.agent_runtime.shared.tool_registry import (
    PluginRegistry,
    PluginRegistryContext,
    RuntimeToolEntry,
    default_plugin_registry_context,
)
from services.agent_runtime.shared.tool_results import ToolObservation, ToolResultNormalizer
from services.agent_runtime.shared.skill_registry import (
    RuntimeSkill,
    SkillRegistry,
    SlashCommand,
    runtime_skill_from_manifest,
)

__all__ = [
    "CollectedToolCall",
    "CompletionDecision",
    "CompletionPolicy",
    "PluginRegistry",
    "PluginRegistryContext",
    "RuntimeToolEntry",
    "RuntimeSkill",
    "SkillRegistry",
    "SlashCommand",
    "TaskRun",
    "ToolCallCollector",
    "ToolExecutionRecord",
    "ToolExecutionRunner",
    "ToolObservation",
    "ToolResultNormalizer",
    "TranscriptStore",
    "TrustPolicy",
    "VerificationEvidence",
    "VerificationPolicy",
    "VerificationState",
    "WorkspaceTrust",
    "default_plugin_registry_context",
    "new_run_id",
    "runtime_skill_from_manifest",
    "utc_now_iso",
]
