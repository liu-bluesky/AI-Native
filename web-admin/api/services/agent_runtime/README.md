# Agent Runtime Layout

This package is the canonical home for agent runtime code. The runtime is now
v2-only; the old v1 orchestrator implementation and shim module have been
removed.

## Directories

- `core/`: run state, event, transcript, and shared runtime data models.
- `v2/`: the current v2 implementation and future query engine first runtime
  code.
- `shared/`: tool execution, tool registry, prompt/context, artifact, and LLM
  adapters shared by multiple runtime versions.
- `integrations/`: project chat, global assistant, local connector, plugin, MCP,
  and Hermes-inspired adapter boundaries.

## Migration Rules

1. Prefer new imports from `services.agent_runtime.*` for new code.
2. Do not import `services.agent_runtime_v2`; that legacy compatibility
   namespace has been removed. Use `services.agent_runtime.v2`,
   `services.agent_runtime.core`, or `services.agent_runtime.shared`.
3. Do not add new fallback paths for removed v1 code. Runtime settings that used
   to disable v2 are accepted only as compatibility input.
4. Learn from Hermes by extracting patterns into `shared/` and `integrations/`,
   not by vendoring Hermes files directly into this runtime package.

## Migrated Modules

- `shared/tool_registry.py`: canonical implementation for `PluginRegistry`,
  `PluginRegistryContext`, `RuntimeToolEntry`, and
  `default_plugin_registry_context`.
- `shared/tool_calls.py`: canonical implementation for `CollectedToolCall` and
  `ToolCallCollector`.
- `shared/tool_results.py`: canonical implementation for `ToolObservation` and
  `ToolResultNormalizer`.
- `core/task_run.py`: canonical implementation for `TaskRun`, `new_run_id`,
  and `utc_now_iso`. The `services.agent_runtime.shared.task_run` module remains
  as a compatibility shim inside the canonical package.
- `core/transcript_store.py`: canonical implementation for `TranscriptStore`.
  The `services.agent_runtime.shared.transcript_store` module remains as a
  compatibility shim inside the canonical package.
- `core/event_log.py` and `core/state_store.py`: canonical implementations for
  runtime events and task run state.
- `shared/tool_execution_runner.py`: canonical implementation for
  `ToolExecutionRunner` and `ToolExecutionRecord`.
- `shared/trust_policy.py`: canonical implementation for `TrustPolicy` and
  `WorkspaceTrust`.
- `shared/verification_policy.py`: canonical implementation for
  `VerificationEvidence`, `VerificationState`, and `VerificationPolicy`.
- `shared/completion_policy.py`: canonical implementation for
  `CompletionDecision` and `CompletionPolicy`.
- `v2/llm_step.py`, `v2/query_engine.py`, `v2/runtime.py`,
  `v2/operation_resume.py`, `v2/resume_service.py`, `v2/run_inspector.py`, and
  `v2/event_stream.py`: canonical implementations for the v2 runtime loop,
  resume path, inspection, and event streaming.
- `v2/permission_policy.py`, `v2/permission_store.py`, and
  `v2/permission_actions.py`: canonical implementations for v2 permission
  decisions, rule storage, and user-facing permission actions.
- `shared/skill_registry.py`: Hermes-inspired skill and slash-command registry
  boundary. It models metadata and command resolution without loading or
  executing skill documents.
- `core/memory.py`: memory/session-search boundary for future project memory
  and transcript search integrations.
- `integrations/gateway.py`: adapter boundary for routing CLI, project chat,
  local connector, and platform messages into one runtime input shape.
- `v2/delegation.py`: subagent/delegation planning boundary for v2.
