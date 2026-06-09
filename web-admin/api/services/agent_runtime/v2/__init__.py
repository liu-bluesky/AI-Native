"""Compatibility namespace for the v2 agent runtime."""

from importlib import import_module
from typing import Any

_LAZY_EXPORTS = {
    "AgentRuntimeInspector": ("services.agent_runtime.v2.run_inspector", "AgentRuntimeInspector"),
    "AgentRuntimeResumeRequest": (
        "services.agent_runtime.v2.resume_service",
        "AgentRuntimeResumeRequest",
    ),
    "AgentRuntimeResumeService": (
        "services.agent_runtime.v2.resume_service",
        "AgentRuntimeResumeService",
    ),
    "AgentTaskRuntime": ("services.agent_runtime.v2.runtime", "AgentTaskRuntime"),
    "BackgroundProcessHandle": (
        "services.agent_runtime.core.background_process",
        "BackgroundProcessHandle",
    ),
    "BackgroundProcessRegistry": (
        "services.agent_runtime.core.background_process",
        "BackgroundProcessRegistry",
    ),
    "CollectedToolCall": ("services.agent_runtime.shared.tool_calls", "CollectedToolCall"),
    "CompletionDecision": ("services.agent_runtime.shared.completion_policy", "CompletionDecision"),
    "CompletionPolicy": ("services.agent_runtime.shared.completion_policy", "CompletionPolicy"),
    "ContextCheckpoint": ("services.agent_runtime.core.context_checkpoint", "ContextCheckpoint"),
    "ContextCheckpointBuilder": (
        "services.agent_runtime.core.context_checkpoint",
        "ContextCheckpointBuilder",
    ),
    "DEFAULT_BLOCKED_DELEGATION_TOOLS": (
        "services.agent_runtime.v2.delegation",
        "DEFAULT_BLOCKED_DELEGATION_TOOLS",
    ),
    "DelegationExecutor": ("services.agent_runtime.v2.delegation", "DelegationExecutor"),
    "DelegationPlanner": ("services.agent_runtime.v2.delegation", "DelegationPlanner"),
    "DelegationPolicy": ("services.agent_runtime.v2.delegation", "DelegationPolicy"),
    "DelegationResult": ("services.agent_runtime.v2.delegation", "DelegationResult"),
    "DelegationTask": ("services.agent_runtime.v2.delegation", "DelegationTask"),
    "DynamicToolPool": ("services.agent_runtime.v2.dynamic_tool_pool", "DynamicToolPool"),
    "EventStream": ("services.agent_runtime.v2.event_stream", "EventStream"),
    "ExternalExecutorEvent": (
        "services.agent_runtime.shared.external_executor_protocol",
        "ExternalExecutorEvent",
    ),
    "ExternalExecutorEventType": (
        "services.agent_runtime.shared.external_executor_protocol",
        "ExternalExecutorEventType",
    ),
    "ExternalExecutorResult": (
        "services.agent_runtime.shared.external_executor_protocol",
        "ExternalExecutorResult",
    ),
    "ExternalExecutorRiskPolicy": (
        "services.agent_runtime.shared.external_executor_protocol",
        "ExternalExecutorRiskPolicy",
    ),
    "ExternalExecutorSelectionDecision": (
        "services.agent_runtime.shared.external_executor_protocol",
        "ExternalExecutorSelectionDecision",
    ),
    "ExternalExecutorStatus": (
        "services.agent_runtime.shared.external_executor_protocol",
        "ExternalExecutorStatus",
    ),
    "ExternalExecutorTaskInput": (
        "services.agent_runtime.shared.external_executor_protocol",
        "ExternalExecutorTaskInput",
    ),
    "ExternalExecutorType": (
        "services.agent_runtime.shared.external_executor_protocol",
        "ExternalExecutorType",
    ),
    "LLMStep": ("services.agent_runtime.v2.llm_step", "LLMStep"),
    "LLMStepResult": ("services.agent_runtime.v2.llm_step", "LLMStepResult"),
    "ModelOutputNormalizationResult": (
        "services.agent_runtime.shared.model_output_normalizer",
        "ModelOutputNormalizationResult",
    ),
    "OperationResumeCoordinator": (
        "services.agent_runtime.v2.operation_resume",
        "OperationResumeCoordinator",
    ),
    "PermissionActionService": (
        "services.agent_runtime.v2.permission_actions",
        "PermissionActionService",
    ),
    "PermissionDecision": ("services.agent_runtime.v2.permission_store", "PermissionDecision"),
    "PermissionPolicy": ("services.agent_runtime.v2.permission_policy", "PermissionPolicy"),
    "PermissionRule": ("services.agent_runtime.v2.permission_store", "PermissionRule"),
    "PermissionStore": ("services.agent_runtime.v2.permission_store", "PermissionStore"),
    "PluginRegistry": ("services.agent_runtime.shared.tool_registry", "PluginRegistry"),
    "PluginRegistryContext": (
        "services.agent_runtime.shared.tool_registry",
        "PluginRegistryContext",
    ),
    "ProviderCapabilityMetadata": (
        "services.agent_runtime.shared.provider_events",
        "ProviderCapabilityMetadata",
    ),
    "ProviderStreamAdapter": (
        "services.agent_runtime.shared.provider_events",
        "ProviderStreamAdapter",
    ),
    "ProviderStreamEvent": (
        "services.agent_runtime.shared.provider_events",
        "ProviderStreamEvent",
    ),
    "ProviderStreamEventType": (
        "services.agent_runtime.shared.provider_events",
        "ProviderStreamEventType",
    ),
    "QueryEngine": ("services.agent_runtime.v2.query_engine", "QueryEngine"),
    "RuntimeToolEntry": ("services.agent_runtime.shared.tool_registry", "RuntimeToolEntry"),
    "RuntimeCapability": (
        "services.agent_runtime.shared.runtime_capabilities",
        "RuntimeCapability",
    ),
    "RuntimeCapabilityCatalog": (
        "services.agent_runtime.shared.runtime_capabilities",
        "RuntimeCapabilityCatalog",
    ),
    "TaskRun": ("services.agent_runtime.core.task_run", "TaskRun"),
    "ToolCallCollector": ("services.agent_runtime.shared.tool_calls", "ToolCallCollector"),
    "ToolExecutionRecord": (
        "services.agent_runtime.shared.tool_execution_runner",
        "ToolExecutionRecord",
    ),
    "ToolExecutionRunner": (
        "services.agent_runtime.shared.tool_execution_runner",
        "ToolExecutionRunner",
    ),
    "ToolObservation": ("services.agent_runtime.shared.tool_results", "ToolObservation"),
    "ToolResultNormalizer": ("services.agent_runtime.shared.tool_results", "ToolResultNormalizer"),
    "TranscriptStore": ("services.agent_runtime.core.transcript_store", "TranscriptStore"),
    "TrustPolicy": ("services.agent_runtime.shared.trust_policy", "TrustPolicy"),
    "VerificationEvidence": (
        "services.agent_runtime.shared.verification_policy",
        "VerificationEvidence",
    ),
    "VerificationPolicy": (
        "services.agent_runtime.shared.verification_policy",
        "VerificationPolicy",
    ),
    "VerificationState": (
        "services.agent_runtime.shared.verification_policy",
        "VerificationState",
    ),
    "WorkspaceTrust": ("services.agent_runtime.shared.trust_policy", "WorkspaceTrust"),
    "default_plugin_registry_context": (
        "services.agent_runtime.shared.tool_registry",
        "default_plugin_registry_context",
    ),
    "default_hermes_runtime_capability_catalog": (
        "services.agent_runtime.shared.runtime_capabilities",
        "default_hermes_runtime_capability_catalog",
    ),
    "normalize_model_output": (
        "services.agent_runtime.shared.model_output_normalizer",
        "normalize_model_output",
    ),
    "normalize_external_executor_event_type": (
        "services.agent_runtime.shared.external_executor_protocol",
        "normalize_external_executor_event_type",
    ),
    "normalize_external_executor_status": (
        "services.agent_runtime.shared.external_executor_protocol",
        "normalize_external_executor_status",
    ),
    "normalize_external_executor_type": (
        "services.agent_runtime.shared.external_executor_protocol",
        "normalize_external_executor_type",
    ),
    "new_run_id": ("services.agent_runtime.core.task_run", "new_run_id"),
    "utc_now_iso": ("services.agent_runtime.core.task_run", "utc_now_iso"),
}


def __getattr__(name: str) -> Any:
    if name not in _LAZY_EXPORTS:
        raise AttributeError(name)
    module_name, attribute_name = _LAZY_EXPORTS[name]
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value


__all__ = [
    "AgentRuntimeInspector",
    "AgentRuntimeResumeRequest",
    "AgentRuntimeResumeService",
    "AgentTaskRuntime",
    "BackgroundProcessHandle",
    "BackgroundProcessRegistry",
    "CollectedToolCall",
    "CompletionDecision",
    "CompletionPolicy",
    "ContextCheckpoint",
    "ContextCheckpointBuilder",
    "DEFAULT_BLOCKED_DELEGATION_TOOLS",
    "DelegationExecutor",
    "DelegationPlanner",
    "DelegationPolicy",
    "DelegationResult",
    "DelegationTask",
    "DynamicToolPool",
    "EventStream",
    "ExternalExecutorEvent",
    "ExternalExecutorEventType",
    "ExternalExecutorResult",
    "ExternalExecutorRiskPolicy",
    "ExternalExecutorSelectionDecision",
    "ExternalExecutorStatus",
    "ExternalExecutorTaskInput",
    "ExternalExecutorType",
    "LLMStep",
    "LLMStepResult",
    "ModelOutputNormalizationResult",
    "OperationResumeCoordinator",
    "PermissionActionService",
    "PermissionDecision",
    "PermissionPolicy",
    "PermissionRule",
    "PermissionStore",
    "PluginRegistry",
    "PluginRegistryContext",
    "ProviderCapabilityMetadata",
    "ProviderStreamAdapter",
    "ProviderStreamEvent",
    "ProviderStreamEventType",
    "QueryEngine",
    "RuntimeCapability",
    "RuntimeCapabilityCatalog",
    "RuntimeToolEntry",
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
    "normalize_model_output",
    "new_run_id",
    "utc_now_iso",
]
