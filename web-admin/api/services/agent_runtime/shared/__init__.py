"""Shared runtime adapters for tools, prompts, artifacts, and LLM access."""

from services.agent_runtime.core.background_process import (
    BackgroundProcessHandle,
    BackgroundProcessRegistry,
)
from services.agent_runtime.shared.completion_policy import CompletionDecision, CompletionPolicy
from services.agent_runtime.shared.tool_calls import CollectedToolCall, ToolCallCollector
from services.agent_runtime.core.context_checkpoint import (
    ContextCheckpoint,
    ContextCheckpointBuilder,
)
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
from services.agent_runtime.shared.runtime_capabilities import (
    RuntimeCapability,
    RuntimeCapabilityCatalog,
    default_hermes_runtime_capability_catalog,
)
from services.agent_runtime.shared.provider_events import (
    ProviderCapabilityMetadata,
    ProviderStreamAdapter,
    ProviderStreamEvent,
    ProviderStreamEventType,
)
from services.agent_runtime.shared.external_executor_protocol import (
    ExternalExecutorEvent,
    ExternalExecutorEventType,
    ExternalExecutorResult,
    ExternalExecutorRiskPolicy,
    ExternalExecutorSelectionDecision,
    ExternalExecutorStatus,
    ExternalExecutorTaskInput,
    ExternalExecutorType,
    normalize_external_executor_event_type,
    normalize_external_executor_status,
    normalize_external_executor_type,
)

__all__ = [
    "BackgroundProcessHandle",
    "BackgroundProcessRegistry",
    "CollectedToolCall",
    "CompletionDecision",
    "CompletionPolicy",
    "ContextCheckpoint",
    "ContextCheckpointBuilder",
    "ExternalExecutorEvent",
    "ExternalExecutorEventType",
    "ExternalExecutorResult",
    "ExternalExecutorRiskPolicy",
    "ExternalExecutorSelectionDecision",
    "ExternalExecutorStatus",
    "ExternalExecutorTaskInput",
    "ExternalExecutorType",
    "PluginRegistry",
    "PluginRegistryContext",
    "ProviderCapabilityMetadata",
    "ProviderStreamAdapter",
    "ProviderStreamEvent",
    "ProviderStreamEventType",
    "RuntimeCapability",
    "RuntimeCapabilityCatalog",
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
    "default_hermes_runtime_capability_catalog",
    "default_plugin_registry_context",
    "normalize_external_executor_event_type",
    "normalize_external_executor_status",
    "normalize_external_executor_type",
    "new_run_id",
    "runtime_skill_from_manifest",
    "utc_now_iso",
]
