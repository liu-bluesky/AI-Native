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
    "CollectedToolCall": ("services.agent_runtime.shared.tool_calls", "CollectedToolCall"),
    "CompletionDecision": ("services.agent_runtime.shared.completion_policy", "CompletionDecision"),
    "CompletionPolicy": ("services.agent_runtime.shared.completion_policy", "CompletionPolicy"),
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
    "LLMStep": ("services.agent_runtime.v2.llm_step", "LLMStep"),
    "LLMStepResult": ("services.agent_runtime.v2.llm_step", "LLMStepResult"),
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
    "QueryEngine": ("services.agent_runtime.v2.query_engine", "QueryEngine"),
    "RuntimeToolEntry": ("services.agent_runtime.shared.tool_registry", "RuntimeToolEntry"),
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
    "CollectedToolCall",
    "CompletionDecision",
    "CompletionPolicy",
    "DEFAULT_BLOCKED_DELEGATION_TOOLS",
    "DelegationExecutor",
    "DelegationPlanner",
    "DelegationPolicy",
    "DelegationResult",
    "DelegationTask",
    "DynamicToolPool",
    "EventStream",
    "LLMStep",
    "LLMStepResult",
    "OperationResumeCoordinator",
    "PermissionActionService",
    "PermissionDecision",
    "PermissionPolicy",
    "PermissionRule",
    "PermissionStore",
    "PluginRegistry",
    "PluginRegistryContext",
    "QueryEngine",
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
    "default_plugin_registry_context",
    "new_run_id",
    "utc_now_iso",
]
