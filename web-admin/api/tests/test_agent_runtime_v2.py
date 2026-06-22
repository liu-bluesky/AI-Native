import asyncio
import json

import pytest


def test_agent_runtime_v2_normalizes_delegate_mode_to_query_engine(tmp_path):
    from services.agent_runtime.v2.runtime import AgentTaskRuntime
    from services.agent_runtime.core.event_log import RuntimeEventLog
    from services.agent_runtime.core.state_store import TaskRunStore
    from services.agent_runtime.core.transcript_store import TranscriptStore

    class _FakeLLM:
        async def chat_completion_stream(self, **kwargs):
            yield {"content": "ok"}

    runtime = AgentTaskRuntime(
        llm_service=_FakeLLM(),
        state_store=TaskRunStore(tmp_path / "runs"),
        transcript_store=TranscriptStore(tmp_path / "transcripts"),
        event_log=RuntimeEventLog(tmp_path / "events"),
    )
    chunks = []

    async def _run():
        async for chunk in runtime.run(
            session_id="session-1",
            user_message="修复问题",
            tools=[],
            provider_id="provider-1",
            model_name="model-1",
            temperature=0.1,
            max_tokens=256,
            project_id="proj-1",
            employee_id="emp-1",
            cancel_event=asyncio.Event(),
            username="tester",
            chat_session_id="chat-1",
            assistant_workflow={"agent_runtime_mode": "delegate"},
        ):
            chunks.append(chunk)

    asyncio.run(_run())

    assert chunks[0]["type"] == "runtime_status"
    assert chunks[0]["runtime"] == "agent_runtime_v2"
    assert chunks[1]["mode"] == "query_engine"
    assert chunks[-1]["type"] == "done"
    assert chunks[-1]["content"] == "ok"
    files = list((tmp_path / "runs").glob("run_*.json"))
    assert len(files) == 1
    payload = files[0].read_text(encoding="utf-8")
    assert '"type": "run_created"' in payload
    assert '"type": "query_engine_started"' in payload
    transcript_files = list((tmp_path / "transcripts").glob("run_*.jsonl"))
    assert len(transcript_files) == 1
    transcript_payload = transcript_files[0].read_text(encoding="utf-8")
    assert '"type": "user_message"' in transcript_payload
    assert '"type": "model_output"' in transcript_payload
    event_files = list((tmp_path / "events").glob("run_*.jsonl"))
    assert len(event_files) == 1
    event_payload = event_files[0].read_text(encoding="utf-8")
    assert '"event_type": "run_started"' in event_payload
    assert '"event_type": "completion_decision"' in event_payload


@pytest.mark.asyncio
async def test_agent_runtime_v2_persists_resume_context(tmp_path):
    from services.agent_runtime.v2.runtime import AgentTaskRuntime
    from services.agent_runtime.core.event_log import RuntimeEventLog
    from services.agent_runtime.core.state_store import TaskRunStore
    from services.agent_runtime.core.transcript_store import TranscriptStore

    class _LocalConnector:
        id = "connector-1"

    runtime = AgentTaskRuntime(
        state_store=TaskRunStore(tmp_path / "runs"),
        transcript_store=TranscriptStore(tmp_path / "transcripts"),
        event_log=RuntimeEventLog(tmp_path / "events"),
    )

    async for _ in runtime.run(
        session_id="session-1",
        user_message="运行测试",
        tools=[
            {
                "tool_name": "project_host_run_command",
                "parameters_schema": {"type": "object"},
            }
        ],
        provider_id="provider-1",
        model_name="model-1",
        temperature=0.3,
        max_tokens=512,
        project_id="proj-1",
        employee_id="emp-1",
        cancel_event=asyncio.Event(),
        username="tester",
        chat_session_id="chat-1",
        role_ids=["admin"],
        local_connector=_LocalConnector(),
        local_connector_workspace_path="/tmp/workspace",
        host_workspace_path="/tmp/host-workspace",
        local_connector_sandbox_mode="workspace-write",
        prompt_version="prompt-v1",
        assistant_workflow={"agent_runtime_mode": "query_engine"},
        capability_routing={"enabled": True},
    ):
        pass

    runs = runtime.state_store.list_runs(project_id="proj-1", username="tester")
    assert len(runs) == 1
    resume_context = runs[0].metadata["resume_context"]
    assert resume_context["provider_id"] == "provider-1"
    assert resume_context["model_name"] == "model-1"
    assert resume_context["temperature"] == 0.3
    assert resume_context["max_tokens"] == 512
    assert resume_context["tools"][0]["tool_name"] == "project_host_run_command"
    assert resume_context["role_ids"] == ["admin"]
    assert resume_context["local_connector_id"] == "connector-1"
    assert resume_context["local_connector_workspace_path"] == "/tmp/workspace"
    assert resume_context["host_workspace_path"] == "/tmp/host-workspace"
    assert resume_context["prompt_version"] == "prompt-v1"
    assert resume_context["assistant_workflow"]["agent_runtime_mode"] == "query_engine"
    assert resume_context["capability_routing"] == {"enabled": True}


def test_agent_runtime_inspector_lists_and_loads_run_snapshot(tmp_path):
    from services.agent_runtime.core.event_log import RuntimeEventLog
    from services.agent_runtime.v2.run_inspector import AgentRuntimeInspector
    from services.agent_runtime.core.state_store import TaskRunStore
    from services.agent_runtime.core.transcript_store import TranscriptStore

    state_store = TaskRunStore(tmp_path / "runs")
    event_log = RuntimeEventLog(tmp_path / "events")
    transcript_store = TranscriptStore(tmp_path / "transcripts")
    run = state_store.create(
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
        session_id="session-1",
        user_goal="修复问题",
    )
    event_log.append(run.run_id, "run_started", {"status": "running"})
    transcript_store.append(run.run_id, "user_message", {"content": "修复问题"})

    inspector = AgentRuntimeInspector(
        state_store=state_store,
        event_log=event_log,
        transcript_store=transcript_store,
    )

    summaries = inspector.list_run_summaries(
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
    )
    snapshot = inspector.get_run_snapshot(run.run_id)

    assert [item["run_id"] for item in summaries] == [run.run_id]
    assert snapshot is not None
    assert snapshot["run"]["run_id"] == run.run_id
    assert snapshot["events"][0]["event_type"] == "run_started"
    assert snapshot["transcript"][0]["type"] == "user_message"


def test_project_chat_settings_preserve_agent_runtime_flag():
    from routers import projects as projects_router

    settings = projects_router._normalize_project_chat_settings(
        {"agent_runtime_enabled": False}
    )

    assert settings["agent_runtime_enabled"] is False


def test_project_chat_settings_enable_agent_runtime_by_default():
    from routers import projects as projects_router

    settings = projects_router._normalize_project_chat_settings({})

    assert settings["agent_runtime_enabled"] is True


def test_agent_runtime_v2_legacy_namespace_is_removed():
    import importlib.util

    assert importlib.util.find_spec("services.agent_runtime_v2") is None


def test_agent_runtime_shared_tool_registry_is_canonical():
    from services.agent_runtime.shared.tool_registry import PluginRegistry
    from services.agent_runtime.v2 import PluginRegistry as V2NamespacePluginRegistry
    from services.agent_runtime.shared.tool_registry import (
        PluginRegistry as LegacyPluginRegistry,
    )

    assert V2NamespacePluginRegistry is PluginRegistry
    assert LegacyPluginRegistry is PluginRegistry


def test_agent_runtime_shared_tool_calls_are_canonical():
    from services.agent_runtime.shared.tool_calls import CollectedToolCall, ToolCallCollector
    from services.agent_runtime.v2 import (
        CollectedToolCall as V2NamespaceCollectedToolCall,
        ToolCallCollector as V2NamespaceToolCallCollector,
    )
    from services.agent_runtime.shared.tool_calls import (
        CollectedToolCall as LegacyCollectedToolCall,
        ToolCallCollector as LegacyToolCallCollector,
    )

    assert V2NamespaceCollectedToolCall is CollectedToolCall
    assert V2NamespaceToolCallCollector is ToolCallCollector
    assert LegacyCollectedToolCall is CollectedToolCall
    assert LegacyToolCallCollector is ToolCallCollector


def test_agent_runtime_shared_tool_results_are_canonical():
    from services.agent_runtime.shared.tool_results import ToolObservation, ToolResultNormalizer
    from services.agent_runtime.v2 import (
        ToolObservation as V2NamespaceToolObservation,
        ToolResultNormalizer as V2NamespaceToolResultNormalizer,
    )
    from services.agent_runtime.shared.tool_results import (
        ToolObservation as LegacyToolObservation,
        ToolResultNormalizer as LegacyToolResultNormalizer,
    )

    assert V2NamespaceToolObservation is ToolObservation
    assert V2NamespaceToolResultNormalizer is ToolResultNormalizer
    assert LegacyToolObservation is ToolObservation
    assert LegacyToolResultNormalizer is ToolResultNormalizer


def test_agent_runtime_shared_tool_execution_runner_is_canonical():
    from services.agent_runtime.shared.tool_execution_runner import (
        ToolExecutionRecord,
        ToolExecutionRunner,
    )
    from services.agent_runtime.v2 import (
        ToolExecutionRecord as V2NamespaceToolExecutionRecord,
        ToolExecutionRunner as V2NamespaceToolExecutionRunner,
    )
    from services.agent_runtime.shared.tool_execution_runner import (
        ToolExecutionRecord as LegacyToolExecutionRecord,
        ToolExecutionRunner as LegacyToolExecutionRunner,
    )

    assert V2NamespaceToolExecutionRecord is ToolExecutionRecord
    assert V2NamespaceToolExecutionRunner is ToolExecutionRunner
    assert LegacyToolExecutionRecord is ToolExecutionRecord
    assert LegacyToolExecutionRunner is ToolExecutionRunner


def test_agent_runtime_external_executor_protocol_round_trips_task_input():
    from services.agent_runtime.shared.external_executor_protocol import (
        ExternalExecutorRiskPolicy,
        ExternalExecutorTaskInput,
    )

    task_input = ExternalExecutorTaskInput.from_dict(
        {
            "project_id": "proj-1",
            "chat_session_id": "chat-1",
            "session_id": "ws-1",
            "requirement_id": "req-1",
            "task_tree_id": "tree-1",
            "task_node_id": "node-1",
            "executor_type": "codex_cli",
            "workspace_path": "/tmp/workspace",
            "sandbox_mode": "workspace-write",
            "user_goal": "修复 bug",
            "node_goal": "运行测试并修复失败",
            "context_files": ["README.md", ""],
            "allowed_tools": ["terminal", "file"],
            "risk_policy": {
                "require_confirmation_for_destructive_actions": True,
                "network_access": "restricted",
            },
        }
    )

    assert isinstance(task_input.risk_policy, ExternalExecutorRiskPolicy)
    assert task_input.to_dict() == {
        "project_id": "proj-1",
        "chat_session_id": "chat-1",
        "session_id": "ws-1",
        "requirement_id": "req-1",
        "task_tree_id": "tree-1",
        "task_node_id": "node-1",
        "executor_type": "codex_cli",
        "workspace_path": "/tmp/workspace",
        "sandbox_mode": "workspace-write",
        "user_goal": "修复 bug",
        "node_goal": "运行测试并修复失败",
        "context_files": ["README.md"],
        "allowed_tools": ["terminal", "file"],
        "risk_policy": {
            "require_confirmation_for_destructive_actions": True,
            "network_access": "restricted",
            "sandbox_mode": "workspace-write",
        },
        "metadata": {},
    }


def test_agent_runtime_external_executor_protocol_maps_runner_events():
    from services.agent_runtime.shared.external_executor_protocol import (
        ExternalExecutorEvent,
        ExternalExecutorResult,
    )

    stdout_event = ExternalExecutorEvent.from_runner_event(
        {"type": "stdout", "data": "pytest passed\n"},
        task_node_id="node-1",
        executor_type="codex_cli",
    ).to_dict()
    failed_exit_event = ExternalExecutorEvent.from_runner_event(
        {"type": "exit", "returncode": 2},
        task_node_id="node-1",
        executor_type="codex_cli",
    ).to_dict()
    result = ExternalExecutorResult.from_dict(
        {
            "status": "done",
            "summary": "Implemented protocol",
            "changed_files": ["services/agent_runtime/shared/external_executor_protocol.py"],
            "verification": [{"summary": "pytest web-admin/api/tests/test_agent_runtime_v2.py"}],
        }
    )

    assert stdout_event["type"] == "tool_result"
    assert stdout_event["status"] == "in_progress"
    assert failed_exit_event["type"] == "failed"
    assert failed_exit_event["status"] == "failed"
    assert result.succeeded is True
    assert "Changed files:" in result.task_tree_verification_result()


def test_agent_runtime_codex_runner_adapter_normalizes_stream_events():
    from services.agent_runtime.integrations import CodexRunnerStreamAdapter
    from services.agent_runtime.shared.external_executor_protocol import ExternalExecutorTaskInput

    task_input = ExternalExecutorTaskInput.from_dict(
        {
            "project_id": "proj-1",
            "chat_session_id": "chat-1",
            "session_id": "ws-1",
            "requirement_id": "req-1",
            "task_tree_id": "tree-1",
            "task_node_id": "node-1",
            "executor_type": "codex_cli",
            "workspace_path": "/tmp/workspace",
            "user_goal": "修复测试",
            "node_goal": "运行 Codex runner",
        }
    )
    adapter = CodexRunnerStreamAdapter.from_task_input(task_input)

    events = list(
        adapter.iter_event_dicts(
            [
                {"type": "started", "exec_id": "exec-1"},
                {"type": "stdout", "data": "pytest passed\n"},
                {"type": "stderr", "data": "warning\n"},
                {"type": "exit", "exec_id": "exec-1", "returncode": 0},
                {"type": "exit", "exec_id": "exec-2", "returncode": 2},
                "plain chunk",
            ]
        )
    )

    assert [event["task_node_id"] for event in events] == ["node-1"] * len(events)
    assert [event["executor_type"] for event in events] == ["codex_cli"] * len(events)
    assert events[0]["type"] == "started"
    assert events[0]["status"] == "in_progress"
    assert events[1]["type"] == "tool_result"
    assert events[1]["message"] == "pytest passed"
    assert events[1]["data"] == {"type": "stdout", "data": "pytest passed\n"}
    assert events[2]["message"] == "warning"
    assert events[3]["type"] == "completed"
    assert events[3]["status"] == "completed"
    assert events[4]["type"] == "failed"
    assert events[4]["status"] == "failed"
    assert events[5]["message"] == "plain chunk"


def test_agent_runtime_codex_runner_adapter_outputs_ndjson_safe_events():
    from services.agent_runtime.integrations import (
        CodexRunnerStreamAdapter,
        normalize_codex_runner_events,
    )

    payloads = [
        {"type": "stdout", "data": "第一行\n"},
        {"type": "exit", "returncode": 0},
    ]
    adapter = CodexRunnerStreamAdapter(task_node_id="node-1")
    ndjson_lines = list(adapter.iter_ndjson_lines(payloads))
    normalized = normalize_codex_runner_events(payloads, task_node_id="node-1")

    assert [json.loads(line)["task_node_id"] for line in ndjson_lines] == [
        "node-1",
        "node-1",
    ]
    assert normalized[0]["message"] == "第一行"
    assert normalized[1]["status"] == "completed"


def test_agent_runtime_external_executor_protocol_is_canonical():
    from services.agent_runtime.shared.external_executor_protocol import (
        ExternalExecutorEvent,
        ExternalExecutorResult,
        ExternalExecutorTaskInput,
    )
    from services.agent_runtime.v2 import (
        ExternalExecutorEvent as V2NamespaceExternalExecutorEvent,
        ExternalExecutorResult as V2NamespaceExternalExecutorResult,
        ExternalExecutorTaskInput as V2NamespaceExternalExecutorTaskInput,
    )

    assert V2NamespaceExternalExecutorEvent is ExternalExecutorEvent
    assert V2NamespaceExternalExecutorResult is ExternalExecutorResult
    assert V2NamespaceExternalExecutorTaskInput is ExternalExecutorTaskInput


def test_agent_runtime_shared_task_run_is_canonical():
    from services.agent_runtime.core import (
        TaskRun as CoreTaskRun,
        new_run_id as core_new_run_id,
        utc_now_iso as core_utc_now_iso,
    )
    from services.agent_runtime.shared.task_run import TaskRun, new_run_id, utc_now_iso
    from services.agent_runtime.v2 import (
        TaskRun as V2NamespaceTaskRun,
        new_run_id as v2_namespace_new_run_id,
        utc_now_iso as v2_namespace_utc_now_iso,
    )
    from services.agent_runtime.core.task_run import (
        TaskRun as LegacyTaskRun,
        new_run_id as legacy_new_run_id,
        utc_now_iso as legacy_utc_now_iso,
    )

    assert CoreTaskRun is TaskRun
    assert core_new_run_id is new_run_id
    assert core_utc_now_iso is utc_now_iso
    assert V2NamespaceTaskRun is TaskRun
    assert v2_namespace_new_run_id is new_run_id
    assert v2_namespace_utc_now_iso is utc_now_iso
    assert LegacyTaskRun is TaskRun
    assert legacy_new_run_id is new_run_id
    assert legacy_utc_now_iso is utc_now_iso


def test_agent_runtime_shared_transcript_store_is_canonical():
    from services.agent_runtime.core import TranscriptStore as CoreTranscriptStore
    from services.agent_runtime.shared.transcript_store import TranscriptStore
    from services.agent_runtime.v2 import TranscriptStore as V2NamespaceTranscriptStore
    from services.agent_runtime.core.transcript_store import (
        TranscriptStore as LegacyTranscriptStore,
    )

    assert CoreTranscriptStore is TranscriptStore
    assert V2NamespaceTranscriptStore is TranscriptStore
    assert LegacyTranscriptStore is TranscriptStore


def test_agent_runtime_shared_trust_policy_is_canonical():
    from services.agent_runtime.shared.trust_policy import TrustPolicy, WorkspaceTrust
    from services.agent_runtime.v2 import (
        TrustPolicy as V2NamespaceTrustPolicy,
        WorkspaceTrust as V2NamespaceWorkspaceTrust,
    )
    from services.agent_runtime.shared.trust_policy import (
        TrustPolicy as LegacyTrustPolicy,
        WorkspaceTrust as LegacyWorkspaceTrust,
    )

    assert V2NamespaceTrustPolicy is TrustPolicy
    assert V2NamespaceWorkspaceTrust is WorkspaceTrust
    assert LegacyTrustPolicy is TrustPolicy
    assert LegacyWorkspaceTrust is WorkspaceTrust


def test_agent_runtime_shared_verification_policy_is_canonical():
    from services.agent_runtime.shared.verification_policy import (
        VerificationEvidence,
        VerificationPolicy,
        VerificationState,
    )
    from services.agent_runtime.v2 import (
        VerificationEvidence as V2NamespaceVerificationEvidence,
        VerificationPolicy as V2NamespaceVerificationPolicy,
        VerificationState as V2NamespaceVerificationState,
    )
    from services.agent_runtime.shared.verification_policy import (
        VerificationEvidence as LegacyVerificationEvidence,
        VerificationPolicy as LegacyVerificationPolicy,
        VerificationState as LegacyVerificationState,
    )

    assert V2NamespaceVerificationEvidence is VerificationEvidence
    assert V2NamespaceVerificationPolicy is VerificationPolicy
    assert V2NamespaceVerificationState is VerificationState
    assert LegacyVerificationEvidence is VerificationEvidence
    assert LegacyVerificationPolicy is VerificationPolicy
    assert LegacyVerificationState is VerificationState


def test_agent_runtime_shared_completion_policy_is_canonical():
    from services.agent_runtime.shared.completion_policy import (
        CompletionDecision,
        CompletionPolicy,
    )
    from services.agent_runtime.v2 import (
        CompletionDecision as V2NamespaceCompletionDecision,
        CompletionPolicy as V2NamespaceCompletionPolicy,
    )
    from services.agent_runtime.shared.completion_policy import (
        CompletionDecision as LegacyCompletionDecision,
        CompletionPolicy as LegacyCompletionPolicy,
    )

    assert V2NamespaceCompletionDecision is CompletionDecision
    assert V2NamespaceCompletionPolicy is CompletionPolicy
    assert LegacyCompletionDecision is CompletionDecision
    assert LegacyCompletionPolicy is CompletionPolicy


def test_model_output_normalizer_parses_dsml_tool_calls():
    from services.agent_runtime.shared.model_output_normalizer import (
        normalize_model_output,
    )

    content = """
<｜｜DSML｜｜tool_calls>
<｜｜DSML｜｜invoke name="project_host_run_command">
<｜｜DSML｜｜parameter name="command" string="true">lark-cli auth status</｜｜DSML｜｜parameter>
<｜｜DSML｜｜parameter name="timeout_sec" string="false">10</｜｜DSML｜｜parameter>
</｜｜DSML｜｜invoke>
</｜｜DSML｜｜tool_calls>
""".strip()

    result = normalize_model_output(
        content=content,
        structured_tool_calls=[],
        allowed_tool_names={"project_host_run_command"},
    )

    assert result.visible_content == ""
    assert result.leak_detected is True
    assert result.leak_kinds == ["dsml_tool_calls"]
    assert result.parsed_text_tool_call_count == 1
    assert result.tool_calls[0].tool_name == "project_host_run_command"
    assert json.loads(result.tool_calls[0].arguments) == {
        "command": "lark-cli auth status",
        "timeout_sec": 10,
    }
    assert "DSML" not in result.visible_content


def test_model_output_normalizer_strips_xml_and_harmony_protocol():
    from services.agent_runtime.shared.model_output_normalizer import (
        normalize_model_output,
    )

    xml_result = normalize_model_output(
        content='<tool_call>{"name":"project_host_run_command","arguments":{"command":"pwd"}}</tool_call>',
        structured_tool_calls=[],
        allowed_tool_names={"project_host_run_command"},
    )
    harmony_result = normalize_model_output(
        content="assistant to=functions.project_host_run_command  <|commentary|>",
        structured_tool_calls=[],
        allowed_tool_names={"project_host_run_command"},
    )

    assert xml_result.visible_content == ""
    assert xml_result.parsed_text_tool_call_count == 1
    assert json.loads(xml_result.tool_calls[0].arguments) == {"command": "pwd"}
    assert harmony_result.visible_content == ""
    assert harmony_result.leak_detected is True
    assert harmony_result.tool_calls == []


def test_agent_runtime_v2_dynamic_tool_pool_relocation_is_canonical():
    from services.agent_runtime.v2.dynamic_tool_pool import DynamicToolPool
    from services.agent_runtime.v2 import DynamicToolPool as V2NamespaceDynamicToolPool
    from services.agent_runtime.v2.dynamic_tool_pool import (
        DynamicToolPool as LegacyDynamicToolPool,
    )

    assert V2NamespaceDynamicToolPool is DynamicToolPool
    assert LegacyDynamicToolPool is DynamicToolPool


def test_agent_runtime_v2_main_modules_are_canonical():
    from services.agent_runtime.v2 import (
        AgentRuntimeInspector,
        AgentRuntimeResumeRequest,
        AgentRuntimeResumeService,
        AgentTaskRuntime,
        EventStream,
        LLMStep,
        LLMStepResult,
        OperationResumeCoordinator,
        QueryEngine,
    )
    from services.agent_runtime.v2 import (
        AgentRuntimeInspector as LegacyNamespaceAgentRuntimeInspector,
        AgentRuntimeResumeRequest as LegacyNamespaceAgentRuntimeResumeRequest,
        AgentRuntimeResumeService as LegacyNamespaceAgentRuntimeResumeService,
        AgentTaskRuntime as LegacyNamespaceAgentTaskRuntime,
        EventStream as LegacyNamespaceEventStream,
        LLMStep as LegacyNamespaceLLMStep,
        LLMStepResult as LegacyNamespaceLLMStepResult,
        OperationResumeCoordinator as LegacyNamespaceOperationResumeCoordinator,
        QueryEngine as LegacyNamespaceQueryEngine,
    )
    from services.agent_runtime.v2.event_stream import EventStream as LegacyEventStream
    from services.agent_runtime.v2.llm_step import (
        LLMStep as LegacyLLMStep,
        LLMStepResult as LegacyLLMStepResult,
    )
    from services.agent_runtime.v2.operation_resume import (
        OperationResumeCoordinator as LegacyOperationResumeCoordinator,
    )
    from services.agent_runtime.v2.query_engine import QueryEngine as LegacyQueryEngine
    from services.agent_runtime.v2.resume_service import (
        AgentRuntimeResumeRequest as LegacyAgentRuntimeResumeRequest,
        AgentRuntimeResumeService as LegacyAgentRuntimeResumeService,
    )
    from services.agent_runtime.v2.run_inspector import (
        AgentRuntimeInspector as LegacyAgentRuntimeInspector,
    )
    from services.agent_runtime.v2.runtime import AgentTaskRuntime as LegacyAgentTaskRuntime

    assert LegacyNamespaceAgentRuntimeInspector is AgentRuntimeInspector
    assert LegacyNamespaceAgentRuntimeResumeRequest is AgentRuntimeResumeRequest
    assert LegacyNamespaceAgentRuntimeResumeService is AgentRuntimeResumeService
    assert LegacyNamespaceAgentTaskRuntime is AgentTaskRuntime
    assert LegacyNamespaceEventStream is EventStream
    assert LegacyNamespaceLLMStep is LLMStep
    assert LegacyNamespaceLLMStepResult is LLMStepResult
    assert LegacyNamespaceOperationResumeCoordinator is OperationResumeCoordinator
    assert LegacyNamespaceQueryEngine is QueryEngine
    assert LegacyAgentRuntimeInspector is AgentRuntimeInspector
    assert LegacyAgentRuntimeResumeRequest is AgentRuntimeResumeRequest
    assert LegacyAgentRuntimeResumeService is AgentRuntimeResumeService
    assert LegacyAgentTaskRuntime is AgentTaskRuntime
    assert LegacyEventStream is EventStream
    assert LegacyLLMStep is LLMStep
    assert LegacyLLMStepResult is LLMStepResult
    assert LegacyOperationResumeCoordinator is OperationResumeCoordinator
    assert LegacyQueryEngine is QueryEngine


def test_agent_runtime_core_state_and_events_are_canonical():
    from services.agent_runtime.core import (
        RuntimeEvent,
        RuntimeEventLog,
        TaskRunStore,
        TranscriptStore,
    )
    from services.agent_runtime.core.event_log import (
        RuntimeEvent as LegacyRuntimeEvent,
        RuntimeEventLog as LegacyRuntimeEventLog,
    )
    from services.agent_runtime.core.state_store import TaskRunStore as LegacyTaskRunStore
    from services.agent_runtime.core.transcript_store import (
        TranscriptStore as LegacyTranscriptStore,
    )

    assert LegacyRuntimeEvent is RuntimeEvent
    assert LegacyRuntimeEventLog is RuntimeEventLog
    assert LegacyTaskRunStore is TaskRunStore
    assert LegacyTranscriptStore is TranscriptStore


def test_agent_runtime_skill_registry_resolves_slash_commands():
    from services.agent_runtime.shared import (
        RuntimeSkill,
        SkillRegistry,
        SlashCommand,
        runtime_skill_from_manifest,
    )

    skill = runtime_skill_from_manifest(
        {
            "id": "project-summary",
            "description": "Summarize project sessions",
            "slash_commands": [
                {
                    "name": "summary",
                    "description": "Summarize",
                    "aliases": ["/sum"],
                }
            ],
        }
    )
    assert skill is not None

    registry = SkillRegistry([skill])
    command = registry.resolve_command("/sum latest")

    assert isinstance(skill, RuntimeSkill)
    assert isinstance(command, SlashCommand)
    assert command.name == "/summary"
    assert command.skill_id == "project-summary"
    assert registry.summary()["available_skill_total"] == 1


def test_agent_runtime_core_memory_boundary_filters_records():
    from services.agent_runtime.core import (
        InMemoryAgentMemoryIndex,
        MemoryQuery,
        MemoryRecord,
    )

    index = InMemoryAgentMemoryIndex()
    index.remember(
        MemoryRecord(
            memory_id="mem-1",
            content="Hermes gateway adapter notes",
            project_id="proj-1",
            tags=("gateway",),
        )
    )
    index.remember(
        MemoryRecord(
            memory_id="mem-2",
            content="Legacy orchestrator notes",
            project_id="proj-2",
            tags=("legacy",),
        )
    )

    result = index.search(
        MemoryQuery(query="gateway", project_id="proj-1", tags=("gateway",))
    )

    assert result.total == 1
    assert result.records[0].memory_id == "mem-1"
    assert result.summary()["backend"] == "memory"


def test_agent_runtime_gateway_router_normalizes_platform_messages():
    from services.agent_runtime.integrations import (
        BasicRuntimeGatewayAdapter,
        RuntimeGatewayMessage,
        RuntimeGatewayRouter,
    )

    router = RuntimeGatewayRouter([BasicRuntimeGatewayAdapter("project_chat")])
    message = RuntimeGatewayMessage(
        source="project_chat",
        text="继续",
        project_id="proj-1",
        chat_session_id="chat-1",
    )

    response = router.dispatch(
        message,
        lambda runtime_input: {
            "text": runtime_input["message"],
            "metadata": {"project_id": runtime_input["project_id"]},
        },
    )

    assert router.to_runtime_input(message)["chat_session_id"] == "chat-1"
    assert response.text == "继续"
    assert response.metadata == {"project_id": "proj-1"}


def test_agent_runtime_v2_delegation_boundary_is_canonical():
    from services.agent_runtime.v2 import (
        DelegationPlanner,
        DelegationPolicy,
        DelegationTask,
    )
    from services.agent_runtime.v2.delegation import DelegationTask as CanonicalDelegationTask
    from services.agent_runtime.v2.delegation import DelegationTask as LegacyDelegationTask

    planner = DelegationPlanner(DelegationPolicy(max_parallel=2, max_depth=1))
    tasks = planner.plan_batch(["inspect tools", "inspect skills"], parent_run_id="run-1")

    assert DelegationTask is CanonicalDelegationTask
    assert LegacyDelegationTask is CanonicalDelegationTask
    assert len(tasks) == 2
    assert tasks[0].runtime_input()["parent_run_id"] == "run-1"


def test_agent_runtime_resume_context_helpers_extract_tools():
    from routers import projects as projects_router

    run = {
        "metadata": {
            "resume_context": {
                "tools": [
                    {"tool_name": "project_host_run_command"},
                    {"name": "query_project_rules"},
                    {"tool_name": "project_host_run_command"},
                ]
            }
        }
    }

    resume_context = projects_router._agent_runtime_resume_context_from_run(run)
    tools = projects_router._agent_runtime_resume_tools(
        resume_context,
        "fallback_tool",
    )
    tool_names = projects_router._agent_runtime_tool_names(tools)
    fallback_tools = projects_router._agent_runtime_resume_tools(
        {},
        "fallback_tool",
    )

    assert resume_context["tools"][0]["tool_name"] == "project_host_run_command"
    assert tool_names == ["project_host_run_command", "query_project_rules"]
    assert fallback_tools == [{"tool_name": "fallback_tool"}]


def test_agent_runtime_permission_request_lookup_uses_recorded_ask_event():
    from routers import projects as projects_router

    snapshot = {
        "events": [
            {
                "event_type": "permission_decision",
                "payload": {
                    "tool_call": {
                        "call_id": "call-1",
                        "tool_name": "project_host_run_command",
                        "arguments": '{"command": "npm test"}',
                    },
                    "decision": {
                        "behavior": "ask",
                        "call_id": "call-1",
                        "tool_name": "project_host_run_command",
                    },
                },
            }
        ]
    }

    request = projects_router._find_agent_runtime_permission_request(
        snapshot,
        call_id="call-1",
        tool_name="project_host_run_command",
    )
    missing = projects_router._find_agent_runtime_permission_request(
        snapshot,
        call_id="call-2",
        tool_name="project_host_run_command",
    )

    assert request == {
        "call_id": "call-1",
        "tool_name": "project_host_run_command",
        "args": {"command": "npm test"},
    }
    assert missing is None


def test_agent_runtime_permission_request_lookup_falls_back_to_latest_matching_command():
    from routers import projects as projects_router

    snapshot = {
        "events": [
            {
                "event_type": "permission_decision",
                "payload": {
                    "args": {"command": "/opt/bin/lark-cli auth status --format json"},
                    "decision": {
                        "behavior": "ask",
                        "call_id": "call-old",
                        "tool_name": "project_host_run_command",
                    },
                },
            },
            {
                "event_type": "permission_decision",
                "payload": {
                    "tool_call": {
                        "call_id": "call-new",
                        "tool_name": "project_host_run_command",
                        "arguments": '{"command": "lark-cli auth status"}',
                    },
                    "decision": {
                        "behavior": "ask",
                        "call_id": "call-new",
                        "tool_name": "project_host_run_command",
                    },
                },
            },
        ]
    }

    request = projects_router._find_agent_runtime_permission_request(
        snapshot,
        call_id="call-old",
        tool_name="project_host_run_command",
        args={"command": "/opt/bin/lark-cli auth status --format json"},
    )

    assert request == {
        "call_id": "call-new",
        "tool_name": "project_host_run_command",
        "args": {"command": "lark-cli auth status"},
    }


def test_tool_result_normalizer_maps_result_status():
    from services.agent_runtime.shared.tool_results import ToolResultNormalizer

    normalizer = ToolResultNormalizer()
    succeeded = normalizer.normalize(
        run_id="run-1",
        call_id="call-1",
        tool_name="project_host_run_command",
        raw_result={"exit_code": 0, "stdout": "ok"},
    )
    failed = normalizer.normalize(
        run_id="run-1",
        call_id="call-2",
        tool_name="project_host_run_command",
        raw_result={"exit_code": 2, "stderr": "failed"},
    )

    assert succeeded.status == "succeeded"
    assert succeeded.is_error is False
    assert failed.status == "failed"
    assert failed.is_error is True


def test_tool_call_collector_assembles_streaming_chunks():
    from services.agent_runtime.shared.tool_calls import ToolCallCollector

    collector = ToolCallCollector()
    collector.add_chunk(
        {
            "tool_calls": [
                {
                    "index": 0,
                    "id": "call-1",
                    "function": {
                        "name": "project_host_",
                        "arguments": "{\"command\": \"npm",
                    },
                }
            ]
        }
    )
    collector.add_chunk(
        {
            "tool_calls": [
                {
                    "index": 0,
                    "function": {
                        "name": "run_command",
                        "arguments": " test\"}",
                    },
                }
            ]
        }
    )

    calls = collector.list_tool_calls()

    assert len(calls) == 1
    assert calls[0].call_id == "call-1"
    assert calls[0].tool_name == "project_host_run_command"
    assert calls[0].arguments == "{\"command\": \"npm test\"}"


@pytest.mark.asyncio
async def test_query_engine_can_complete_from_failed_tool_with_useful_stdout(tmp_path):
    from services.agent_runtime.core.event_log import RuntimeEventLog
    from services.agent_runtime.v2.llm_step import LLMStep
    from services.agent_runtime.v2.query_engine import QueryEngine
    from services.agent_runtime.core.state_store import TaskRunStore
    from services.agent_runtime.shared.tool_execution_runner import ToolExecutionRunner
    from services.agent_runtime.core.transcript_store import TranscriptStore

    class _FakeLLM:
        def __init__(self):
            self.calls = 0

        async def chat_completion_stream(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                yield {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call-1",
                            "function": {
                                "name": "project_host_run_command",
                                "arguments": "{\"command\": \"lark-cli doctor\"}",
                            },
                        }
                    ]
                }
                return
            yield {"content": "当前 lark-cli 登录人是刘蓝天；token 已过期，需要重新登录。"}

    class _FakeToolExecutor:
        async def execute_parallel(self, tool_calls, timeout=None):
            return [
                {
                    "exit_code": 1,
                    "stdout": json.dumps(
                        {
                            "checks": [
                                {
                                    "name": "token_exists",
                                    "status": "pass",
                                    "message": "token found for 刘蓝天 (ou_62ba6272243f844b5fa83abb0600358d)",
                                },
                                {
                                    "name": "token_local",
                                    "status": "fail",
                                    "message": "token expired",
                                },
                            ],
                            "ok": False,
                        },
                        ensure_ascii=False,
                    ),
                }
            ]

    state_store = TaskRunStore(tmp_path / "runs")
    event_log = RuntimeEventLog(tmp_path / "events")
    task_run = state_store.create(
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
        session_id="session-1",
        user_goal="/lark-cli 当前登录人是谁",
    )
    engine = QueryEngine(
        llm_step=LLMStep(_FakeLLM()),
        tool_runner=ToolExecutionRunner(
            _FakeToolExecutor(),
            event_log=event_log,
        ),
        state_store=state_store,
        event_log=event_log,
        transcript_store=TranscriptStore(tmp_path / "transcripts"),
        max_model_steps=3,
    )

    result = await engine.run(
        task_run,
        messages=[{"role": "user", "content": "/lark-cli 当前登录人是谁"}],
        tools=[{"tool_name": "project_host_run_command"}],
        provider_id="provider-1",
        model_name="model-1",
        temperature=0.1,
        max_tokens=256,
        task_tree_verified=True,
        goal_covered=True,
    )

    assert result.task_run.status == "completed"
    assert result.completion_decision is not None
    assert result.completion_decision.action == "complete"
    assert "刘蓝天" in result.final_content
    assert "token 已过期" in result.final_content


@pytest.mark.asyncio
async def test_query_engine_creates_observation_and_continues_after_tool(tmp_path):
    from services.agent_runtime.core.event_log import RuntimeEventLog
    from services.agent_runtime.v2.llm_step import LLMStep
    from services.agent_runtime.v2.query_engine import QueryEngine
    from services.agent_runtime.core.state_store import TaskRunStore
    from services.agent_runtime.shared.tool_execution_runner import ToolExecutionRunner
    from services.agent_runtime.core.transcript_store import TranscriptStore

    class _FakeLLM:
        def __init__(self):
            self.calls = 0

        async def chat_completion_stream(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                yield {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call-1",
                            "function": {
                                "name": "project_host_run_command",
                                "arguments": "{\"command\": \"pytest\"}",
                            },
                        }
                    ]
                }
                return
            yield {"content": "已验证完成。"}

    class _FakeToolExecutor:
        async def execute_parallel(self, tool_calls, timeout=None):
            return [{"exit_code": 0, "stdout": "1 passed"}]

    state_store = TaskRunStore(tmp_path / "runs")
    event_log = RuntimeEventLog(tmp_path / "events")
    transcript_store = TranscriptStore(tmp_path / "transcripts")
    task_run = state_store.create(
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
        session_id="session-1",
        user_goal="查询状态",
    )
    engine = QueryEngine(
        llm_step=LLMStep(_FakeLLM()),
        tool_runner=ToolExecutionRunner(
            _FakeToolExecutor(),
            event_log=event_log,
        ),
        state_store=state_store,
        event_log=event_log,
        transcript_store=transcript_store,
        max_model_steps=3,
    )

    result = await engine.run(
        task_run,
        messages=[{"role": "user", "content": "查询状态"}],
        tools=[
            {
                "tool_name": "project_host_run_command",
                "parameters_schema": {"type": "object", "properties": {}},
            }
        ],
        provider_id="provider-1",
        model_name="model-1",
        temperature=0.1,
        max_tokens=256,
        task_tree_verified=True,
        goal_covered=True,
    )

    events = [item.event_type for item in event_log.list_events(task_run.run_id)]
    assert result.task_run.status == "completed"
    assert result.observations[0].status == "succeeded"
    assert "tool_observation_created" in events
    assert "completion_decision" in events


@pytest.mark.asyncio
async def test_query_engine_stops_before_total_tool_call_budget_is_exceeded(tmp_path):
    from services.agent_runtime.core.event_log import RuntimeEventLog
    from services.agent_runtime.v2.llm_step import LLMStep
    from services.agent_runtime.v2.query_engine import QueryEngine
    from services.agent_runtime.core.state_store import TaskRunStore
    from services.agent_runtime.shared.tool_execution_runner import ToolExecutionRunner
    from services.agent_runtime.core.transcript_store import TranscriptStore

    class _FakeLLM:
        def __init__(self):
            self.calls = 0

        async def chat_completion_stream(self, **kwargs):
            self.calls += 1
            yield {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": f"call-{self.calls}",
                        "function": {
                            "name": "project_host_run_command",
                            "arguments": "{\"command\": \"pytest\"}",
                        },
                    }
                ]
            }

    class _FakeToolExecutor:
        def __init__(self):
            self.calls = 0

        async def execute_parallel(self, tool_calls, timeout=None):
            self.calls += 1
            return [{"exit_code": 0, "stdout": "1 passed"}]

    state_store = TaskRunStore(tmp_path / "runs")
    event_log = RuntimeEventLog(tmp_path / "events")
    executor = _FakeToolExecutor()
    task_run = state_store.create(
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
        session_id="session-1",
        user_goal="查询状态",
    )
    engine = QueryEngine(
        llm_step=LLMStep(_FakeLLM()),
        tool_runner=ToolExecutionRunner(
            executor,
            event_log=event_log,
        ),
        state_store=state_store,
        event_log=event_log,
        transcript_store=TranscriptStore(tmp_path / "transcripts"),
        max_model_steps=3,
        max_tool_calls_per_round=1,
        max_tool_calls_total=1,
    )

    result = await engine.run(
        task_run,
        messages=[{"role": "user", "content": "查询状态"}],
        tools=[
            {
                "tool_name": "project_host_run_command",
                "parameters_schema": {"type": "object", "properties": {}},
            }
        ],
        provider_id="provider-1",
        model_name="model-1",
        temperature=0.1,
        max_tokens=256,
        task_tree_verified=True,
        goal_covered=True,
    )

    events = [item.event_type for item in event_log.list_events(task_run.run_id)]
    assert executor.calls == 1
    assert result.task_run.status == "failed"
    assert result.total_tool_calls == 1
    assert result.completion_decision is not None
    assert result.completion_decision.action == "fail"
    assert "tool_call_budget_exceeded" in result.completion_decision.reasons
    assert "tool_call_budget_exceeded" in events
    assert "工具调用次数已达到上限" in result.final_content


@pytest.mark.asyncio
async def test_query_engine_fails_when_tool_succeeds_but_model_never_answers(tmp_path):
    from services.agent_runtime.core.event_log import RuntimeEventLog
    from services.agent_runtime.v2.llm_step import LLMStep
    from services.agent_runtime.v2.query_engine import QueryEngine
    from services.agent_runtime.core.state_store import TaskRunStore
    from services.agent_runtime.shared.tool_execution_runner import ToolExecutionRunner
    from services.agent_runtime.core.transcript_store import TranscriptStore

    class _FakeLLM:
        def __init__(self):
            self.calls = 0

        async def chat_completion_stream(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                yield {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call-1",
                            "function": {
                                "name": "complete_task_node_with_verification",
                                "arguments": "{\"node_id\": \"node-1\"}",
                            },
                        }
                    ]
                }
            elif False:
                yield {}

    class _FakeToolExecutor:
        async def execute_parallel(self, tool_calls, timeout=None):
            return [{"ok": True, "status": "succeeded"}]

    state_store = TaskRunStore(tmp_path / "runs")
    event_log = RuntimeEventLog(tmp_path / "events")
    task_run = state_store.create(
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
        session_id="session-1",
        user_goal="检测登录状态",
    )
    engine = QueryEngine(
        llm_step=LLMStep(_FakeLLM()),
        tool_runner=ToolExecutionRunner(
            _FakeToolExecutor(),
            event_log=event_log,
        ),
        state_store=state_store,
        event_log=event_log,
        transcript_store=TranscriptStore(tmp_path / "transcripts"),
        max_model_steps=2,
    )

    result = await engine.run(
        task_run,
        messages=[{"role": "user", "content": "检测登录状态"}],
        tools=[{"tool_name": "complete_task_node_with_verification"}],
        provider_id="provider-1",
        model_name="model-1",
        temperature=0.1,
        max_tokens=256,
        task_tree_verified=True,
        goal_covered=True,
    )

    assert result.task_run.status == "failed"
    assert result.final_content == ""
    assert result.completion_decision is not None
    assert result.completion_decision.action == "fail"
    assert "missing_final_response_after_tool" in result.completion_decision.reasons
    assert result.observations[0].status == "succeeded"


@pytest.mark.asyncio
async def test_query_engine_waits_when_permission_required(tmp_path):
    from services.agent_runtime.core.event_log import RuntimeEventLog
    from services.agent_runtime.v2.llm_step import LLMStep
    from services.agent_runtime.v2.permission_policy import PermissionPolicy
    from services.agent_runtime.v2.permission_store import PermissionStore
    from services.agent_runtime.v2.query_engine import QueryEngine
    from services.agent_runtime.core.state_store import TaskRunStore
    from services.agent_runtime.shared.tool_execution_runner import ToolExecutionRunner
    from services.agent_runtime.core.transcript_store import TranscriptStore

    class _FakeLLM:
        async def chat_completion_stream(self, **kwargs):
            yield {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "call-1",
                        "function": {
                            "name": "project_host_run_command",
                            "arguments": "{\"command\": \"npm test\"}",
                        },
                    }
                ]
            }

    class _FakeToolExecutor:
        def __init__(self):
            self.calls = 0

        async def execute_parallel(self, tool_calls, timeout=None):
            self.calls += 1
            return [{"exit_code": 0, "stdout": "should not run"}]

    state_store = TaskRunStore(tmp_path / "runs")
    event_log = RuntimeEventLog(tmp_path / "events")
    task_run = state_store.create(
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
        session_id="session-1",
        user_goal="运行测试",
    )
    executor = _FakeToolExecutor()
    engine = QueryEngine(
        llm_step=LLMStep(_FakeLLM()),
        tool_runner=ToolExecutionRunner(
            executor,
            event_log=event_log,
            permission_policy=PermissionPolicy(PermissionStore(tmp_path / "permissions")),
            project_id="proj-1",
            username="tester",
            chat_session_id="chat-1",
            workspace_trusted=False,
        ),
        state_store=state_store,
        event_log=event_log,
        transcript_store=TranscriptStore(tmp_path / "transcripts"),
        max_model_steps=3,
    )

    result = await engine.run(
        task_run,
        messages=[{"role": "user", "content": "运行测试"}],
        tools=[{"tool_name": "project_host_run_command"}],
        provider_id="provider-1",
        model_name="model-1",
        temperature=0.1,
        max_tokens=256,
    )

    events = [item.event_type for item in event_log.list_events(task_run.run_id)]
    assert executor.calls == 0
    assert result.task_run.status == "waiting_user"
    assert result.completion_decision is not None
    assert result.completion_decision.action == "request_user"
    assert "permission_required" in result.completion_decision.reasons
    assert result.observations[0].status == "blocked"
    assert "query_engine_blocked" in [event["type"] for event in result.task_run.events]
    assert "permission_decision" in events


@pytest.mark.asyncio
async def test_query_engine_continues_when_operation_wait_has_no_user_action(tmp_path):
    from services.agent_runtime.core.event_log import RuntimeEventLog
    from services.agent_runtime.v2.llm_step import LLMStep
    from services.agent_runtime.v2.query_engine import QueryEngine
    from services.agent_runtime.core.state_store import TaskRunStore
    from services.agent_runtime.shared.tool_execution_runner import ToolExecutionRunner
    from services.agent_runtime.core.transcript_store import TranscriptStore

    class _FakeLLM:
        def __init__(self):
            self.calls = 0

        async def chat_completion_stream(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                yield {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call-1",
                            "function": {
                                "name": "project_host_run_command",
                                "arguments": "{\"command\": \"lark-cli auth login\"}",
                            },
                        }
                    ]
                }
                return
            yield {"content": "登录命令缺少授权范围，我会换用带业务域的命令继续。"}

    class _FakeToolExecutor:
        async def execute_parallel(self, tool_calls, timeout=None):
            return [
                {
                    "ok": False,
                    "source": "operation_wait_task",
                    "status": "waiting_user_action",
                    "task_id": "operation-wait-1",
                    "command": "lark-cli auth login",
                }
            ]

    state_store = TaskRunStore(tmp_path / "runs")
    event_log = RuntimeEventLog(tmp_path / "events")
    task_run = state_store.create(
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
        session_id="session-1",
        user_goal="登录飞书后继续",
    )
    engine = QueryEngine(
        llm_step=LLMStep(_FakeLLM()),
        tool_runner=ToolExecutionRunner(
            _FakeToolExecutor(),
            event_log=event_log,
        ),
        state_store=state_store,
        event_log=event_log,
        transcript_store=TranscriptStore(tmp_path / "transcripts"),
        max_model_steps=3,
    )

    result = await engine.run(
        task_run,
        messages=[{"role": "user", "content": "登录飞书后继续"}],
        tools=[{"tool_name": "project_host_run_command"}],
        provider_id="provider-1",
        model_name="model-1",
        temperature=0.1,
        max_tokens=256,
        task_tree_verified=True,
        goal_covered=True,
    )

    events = [item.event_type for item in event_log.list_events(task_run.run_id)]
    assert result.task_run.status == "completed"
    assert result.completion_decision is not None
    assert result.completion_decision.action == "complete"
    assert "query_engine_waiting_operation" not in [event["type"] for event in result.task_run.events]
    assert "tool_observation_created" in events


@pytest.mark.asyncio
async def test_query_engine_waits_when_background_operation_has_interaction_schema(tmp_path):
    from services.agent_runtime.core.event_log import RuntimeEventLog
    from services.agent_runtime.v2.llm_step import LLMStep
    from services.agent_runtime.v2.query_engine import QueryEngine
    from services.agent_runtime.core.state_store import TaskRunStore
    from services.agent_runtime.shared.tool_execution_runner import ToolExecutionRunner
    from services.agent_runtime.core.transcript_store import TranscriptStore

    class _FakeLLM:
        async def chat_completion_stream(self, **kwargs):
            yield {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "call-1",
                        "function": {
                            "name": "project_host_run_command",
                            "arguments": "{\"command\": \"lark-cli auth login\"}",
                        },
                    }
                ]
            }

    class _FakeToolExecutor:
        async def execute_parallel(self, tool_calls, timeout=None):
            return [
                {
                    "ok": False,
                    "source": "operation_wait_task",
                    "status": "waiting_user_action",
                    "task_id": "operation-wait-1",
                    "command": "lark-cli auth login",
                    "interaction_schema": {
                        "title": "选择 lark-cli 授权业务域",
                        "schema": [{"label": "业务域", "prop": "domains"}],
                    },
                }
            ]

    state_store = TaskRunStore(tmp_path / "runs")
    event_log = RuntimeEventLog(tmp_path / "events")
    task_run = state_store.create(
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
        session_id="session-1",
        user_goal="登录飞书后继续",
    )
    engine = QueryEngine(
        llm_step=LLMStep(_FakeLLM()),
        tool_runner=ToolExecutionRunner(
            _FakeToolExecutor(),
            event_log=event_log,
        ),
        state_store=state_store,
        event_log=event_log,
        transcript_store=TranscriptStore(tmp_path / "transcripts"),
        max_model_steps=3,
    )

    result = await engine.run(
        task_run,
        messages=[{"role": "user", "content": "登录飞书后继续"}],
        tools=[{"tool_name": "project_host_run_command"}],
        provider_id="provider-1",
        model_name="model-1",
        temperature=0.1,
        max_tokens=256,
    )

    assert result.task_run.status == "waiting_user"
    assert result.completion_decision is not None
    assert result.completion_decision.action == "request_user"
    assert "background_operation_pending" in result.completion_decision.reasons
    assert "query_engine_waiting_operation" in [event["type"] for event in result.task_run.events]
    assert "等待用户操作" in result.final_content
    assert "lark-cli auth login" in result.final_content
    assert "表单" in result.final_content
    assert "授权范围" in result.final_content
    assert "下一步" in result.final_content


@pytest.mark.asyncio
async def test_query_engine_waiting_operation_ignores_model_command_tutorial(tmp_path):
    from services.agent_runtime.core.event_log import RuntimeEventLog
    from services.agent_runtime.v2.llm_step import LLMStep
    from services.agent_runtime.v2.query_engine import QueryEngine
    from services.agent_runtime.core.state_store import TaskRunStore
    from services.agent_runtime.shared.tool_execution_runner import ToolExecutionRunner
    from services.agent_runtime.core.transcript_store import TranscriptStore

    class _FakeLLM:
        async def chat_completion_stream(self, **kwargs):
            yield {
                "content": "请执行 lark-cli auth login 完成登录。",
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "call-1",
                        "function": {
                            "name": "project_host_run_command",
                            "arguments": "{\"command\": \"lark-cli auth login\"}",
                        },
                    }
                ],
            }

    class _FakeToolExecutor:
        async def execute_parallel(self, tool_calls, timeout=None):
            return [
                {
                    "ok": False,
                    "source": "operation_wait_task",
                    "operation_kind": "auth_login",
                    "operation_label": "网页登录授权",
                    "status": "waiting_user_action",
                    "task_id": "operation-wait-1",
                    "command": "lark-cli auth login",
                    "authorization_url": "https://passport.feishu.cn/suite/passport/oauth/authorize?client_id=cli",
                    "action_type": "open_url",
                }
            ]

    state_store = TaskRunStore(tmp_path / "runs")
    event_log = RuntimeEventLog(tmp_path / "events")
    task_run = state_store.create(
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
        session_id="session-1",
        user_goal="/lark-cli 登录",
    )
    engine = QueryEngine(
        llm_step=LLMStep(_FakeLLM()),
        tool_runner=ToolExecutionRunner(
            _FakeToolExecutor(),
            event_log=event_log,
        ),
        state_store=state_store,
        event_log=event_log,
        transcript_store=TranscriptStore(tmp_path / "transcripts"),
        max_model_steps=3,
    )

    result = await engine.run(
        task_run,
        messages=[{"role": "user", "content": "/lark-cli 登录"}],
        tools=[{"tool_name": "project_host_run_command"}],
        provider_id="provider-1",
        model_name="model-1",
        temperature=0.1,
        max_tokens=256,
    )

    assert result.task_run.status == "waiting_user"
    assert "等待用户操作" in result.final_content
    assert "lark-cli auth login" in result.final_content
    assert "授权链接" in result.final_content
    assert "浏览器" in result.final_content
    assert "下一步" in result.final_content
    assert "请执行" not in result.final_content


@pytest.mark.asyncio
async def test_query_engine_executes_dsml_text_tool_call_without_showing_protocol(tmp_path):
    from services.agent_runtime.core.event_log import RuntimeEventLog
    from services.agent_runtime.v2.llm_step import LLMStep
    from services.agent_runtime.v2.query_engine import QueryEngine
    from services.agent_runtime.core.state_store import TaskRunStore
    from services.agent_runtime.shared.tool_execution_runner import ToolExecutionRunner
    from services.agent_runtime.core.transcript_store import TranscriptStore

    class _FakeLLM:
        def __init__(self):
            self.calls = 0

        async def chat_completion_stream(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                yield {
                    "content": """
<｜｜DSML｜｜tool_calls>
<｜｜DSML｜｜invoke name="project_host_run_command">
<｜｜DSML｜｜parameter name="command" string="true">lark-cli auth status</｜｜DSML｜｜parameter>
<｜｜DSML｜｜parameter name="timeout_sec" string="false">10</｜｜DSML｜｜parameter>
</｜｜DSML｜｜invoke>
</｜｜DSML｜｜tool_calls>
""".strip()
                }
                return
            yield {"content": "已检查登录状态。"}

    class _FakeToolExecutor:
        def __init__(self):
            self.calls = []

        async def execute_parallel(self, tool_calls, timeout=None):
            self.calls.extend(tool_calls)
            return [
                {
                    "ok": True,
                    "stdout": "{\"identity\":\"bot\",\"logged_in\":false}",
                    "command": "lark-cli auth status",
                }
            ]

    llm = _FakeLLM()
    executor = _FakeToolExecutor()
    state_store = TaskRunStore(tmp_path / "runs")
    event_log = RuntimeEventLog(tmp_path / "events")
    transcript_store = TranscriptStore(tmp_path / "transcripts")
    task_run = state_store.create(
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
        session_id="session-1",
        user_goal="/lark-cli 登录",
    )
    engine = QueryEngine(
        llm_step=LLMStep(llm),
        tool_runner=ToolExecutionRunner(
            executor,
            event_log=event_log,
        ),
        state_store=state_store,
        event_log=event_log,
        transcript_store=transcript_store,
        max_model_steps=3,
    )

    result = await engine.run(
        task_run,
        messages=[{"role": "user", "content": "/lark-cli 登录"}],
        tools=[{"tool_name": "project_host_run_command"}],
        provider_id="provider-1",
        model_name="model-1",
        temperature=0.1,
        max_tokens=256,
        task_tree_verified=True,
        goal_covered=True,
    )

    events = event_log.list_events(task_run.run_id)
    normalized_events = [
        item for item in events if item.event_type == "model_output_normalized"
    ]
    transcript = transcript_store.list_events(task_run.run_id)
    first_model_output = next(item for item in transcript if item["type"] == "model_output")

    assert result.task_run.status == "completed"
    assert result.final_content == "已检查登录状态。"
    assert len(executor.calls) == 1
    first_tool_call = executor.calls[0]
    assert first_tool_call["function"]["name"] == "project_host_run_command"
    first_arguments = json.loads(first_tool_call["function"]["arguments"])
    assert first_arguments["command"] == "lark-cli auth status"
    assert first_arguments["timeout_sec"] == 10
    assert first_arguments["_agent_runtime_tool_name"] == "project_host_run_command"
    assert normalized_events
    assert normalized_events[0].payload["parsed_text_tool_call_count"] == 1
    assert "DSML" not in normalized_events[0].payload.get("content_preview", "")
    assert first_model_output["payload"]["content"] == ""
    assert "DSML" in first_model_output["payload"]["raw_content"]


@pytest.mark.asyncio
async def test_query_engine_executes_harmony_text_tool_call_without_showing_protocol(tmp_path):
    from services.agent_runtime.core.event_log import RuntimeEventLog
    from services.agent_runtime.v2.llm_step import LLMStep
    from services.agent_runtime.v2.query_engine import QueryEngine
    from services.agent_runtime.core.state_store import TaskRunStore
    from services.agent_runtime.shared.tool_execution_runner import ToolExecutionRunner
    from services.agent_runtime.core.transcript_store import TranscriptStore

    class _FakeLLM:
        def __init__(self):
            self.calls = 0

        async def chat_completion_stream(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                yield {
                    "content": "assistant to=functions.project_host_run_command "
                    '{"command":"lark-cli auth status","timeout_sec":10}'
                }
                return
            yield {"content": "已检查飞书登录状态。"}

    class _FakeToolExecutor:
        def __init__(self):
            self.calls = []

        async def execute_parallel(self, tool_calls, timeout=None):
            self.calls.extend(tool_calls)
            return [
                {
                    "ok": True,
                    "stdout": "{\"logged_in\":true}",
                    "command": "lark-cli auth status",
                }
            ]

    executor = _FakeToolExecutor()
    state_store = TaskRunStore(tmp_path / "runs")
    event_log = RuntimeEventLog(tmp_path / "events")
    transcript_store = TranscriptStore(tmp_path / "transcripts")
    task_run = state_store.create(
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
        session_id="session-1",
        user_goal="/lark-cli 登录",
    )
    engine = QueryEngine(
        llm_step=LLMStep(_FakeLLM()),
        tool_runner=ToolExecutionRunner(executor, event_log=event_log),
        state_store=state_store,
        event_log=event_log,
        transcript_store=transcript_store,
        max_model_steps=3,
    )

    result = await engine.run(
        task_run,
        messages=[{"role": "user", "content": "/lark-cli 登录"}],
        tools=[{"tool_name": "project_host_run_command"}],
        provider_id="provider-1",
        model_name="model-1",
        temperature=0.1,
        max_tokens=256,
        task_tree_verified=True,
        goal_covered=True,
    )

    transcript = transcript_store.list_events(task_run.run_id)
    first_model_output = next(item for item in transcript if item["type"] == "model_output")
    first_tool_call = executor.calls[0]
    first_arguments = json.loads(first_tool_call["function"]["arguments"])

    assert result.task_run.status == "completed"
    assert result.final_content == "已检查飞书登录状态。"
    assert len(executor.calls) == 1
    assert first_tool_call["function"]["name"] == "project_host_run_command"
    assert first_arguments["command"] == "lark-cli auth status"
    assert first_arguments["timeout_sec"] == 10
    assert first_arguments["_agent_runtime_tool_name"] == "project_host_run_command"
    assert first_model_output["payload"]["content"] == ""
    assert "to=functions" in first_model_output["payload"]["raw_content"]
    assert "to=functions" not in result.final_content


@pytest.mark.asyncio
async def test_query_engine_does_not_complete_harmony_tool_call_leak(tmp_path):
    from services.agent_runtime.core.event_log import RuntimeEventLog
    from services.agent_runtime.v2.llm_step import LLMStep
    from services.agent_runtime.v2.query_engine import QueryEngine
    from services.agent_runtime.core.state_store import TaskRunStore
    from services.agent_runtime.core.transcript_store import TranscriptStore

    class _FakeLLM:
        async def chat_completion_stream(self, **kwargs):
            yield {
                "content": "assistant to=functions.project_host_run_command "
                "command=lark-cli auth status"
            }

    state_store = TaskRunStore(tmp_path / "runs")
    event_log = RuntimeEventLog(tmp_path / "events")
    task_run = state_store.create(
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
        session_id="session-1",
        user_goal="/lark-cli 登录",
    )
    engine = QueryEngine(
        llm_step=LLMStep(_FakeLLM()),
        tool_runner=None,
        state_store=state_store,
        event_log=event_log,
        transcript_store=TranscriptStore(tmp_path / "transcripts"),
        max_model_steps=1,
    )

    result = await engine.run(
        task_run,
        messages=[{"role": "user", "content": "/lark-cli 登录"}],
        tools=[{"tool_name": "project_host_run_command"}],
        provider_id="provider-1",
        model_name="model-1",
        temperature=0.1,
        max_tokens=256,
        task_tree_verified=True,
        goal_covered=True,
    )

    events = event_log.list_events(task_run.run_id)

    assert result.task_run.status == "failed"
    assert result.completion_decision is not None
    assert result.completion_decision.action == "fail"
    assert result.final_content == ""
    assert any(
        item.event_type == "completion_decision"
        and item.payload["reasons"] == ["protocol_leak_retry"]
        for item in events
    )
    assert any(item.event_type == "model_output_normalized" for item in events)
    assert "to=functions" not in result.final_content


@pytest.mark.asyncio
async def test_query_engine_auth_operation_queued_reports_actionable_waiting_state(tmp_path):
    from services.agent_runtime.core.event_log import RuntimeEventLog
    from services.agent_runtime.v2.llm_step import LLMStep
    from services.agent_runtime.v2.query_engine import QueryEngine
    from services.agent_runtime.core.state_store import TaskRunStore
    from services.agent_runtime.shared.tool_execution_runner import ToolExecutionRunner
    from services.agent_runtime.core.transcript_store import TranscriptStore

    class _FakeLLM:
        async def chat_completion_stream(self, **kwargs):
            yield {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "call-1",
                        "function": {
                            "name": "project_host_run_command",
                            "arguments": "{\"command\": \"lark-cli auth login --domain im\"}",
                        },
                    }
                ],
            }

    class _FakeToolExecutor:
        async def execute_parallel(self, tool_calls, timeout=None):
            return [
                {
                    "ok": False,
                    "source": "operation_wait_task",
                    "operation_kind": "auth_login",
                    "operation_label": "网页登录授权",
                    "status": "queued",
                    "task_id": "operation-wait-1",
                    "command": "lark-cli auth login --domain im",
                }
            ]

    state_store = TaskRunStore(tmp_path / "runs")
    event_log = RuntimeEventLog(tmp_path / "events")
    task_run = state_store.create(
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
        session_id="session-1",
        user_goal="/lark-cli 登录用户身份",
    )
    engine = QueryEngine(
        llm_step=LLMStep(_FakeLLM()),
        tool_runner=ToolExecutionRunner(
            _FakeToolExecutor(),
            event_log=event_log,
        ),
        state_store=state_store,
        event_log=event_log,
        transcript_store=TranscriptStore(tmp_path / "transcripts"),
        max_model_steps=3,
    )

    result = await engine.run(
        task_run,
        messages=[{"role": "user", "content": "/lark-cli 登录用户身份"}],
        tools=[{"tool_name": "project_host_run_command"}],
        provider_id="provider-1",
        model_name="model-1",
        temperature=0.1,
        max_tokens=256,
    )

    assert result.task_run.status == "waiting_user"
    assert result.completion_decision is not None
    assert result.completion_decision.action == "request_user"
    assert "等待用户操作" in result.final_content
    assert "网页登录授权" in result.final_content
    assert "lark-cli auth login --domain im" in result.final_content
    assert "operation-wait-1" in result.final_content
    assert "queued" in result.final_content
    assert "下一步" in result.final_content


@pytest.mark.asyncio
async def test_query_engine_reports_missing_host_workspace_as_environment_block(tmp_path):
    from services.agent_runtime.core.event_log import RuntimeEventLog
    from services.agent_runtime.v2.llm_step import LLMStep
    from services.agent_runtime.v2.query_engine import QueryEngine
    from services.agent_runtime.core.state_store import TaskRunStore
    from services.agent_runtime.shared.tool_execution_runner import ToolExecutionRunner
    from services.agent_runtime.core.transcript_store import TranscriptStore

    class _FakeLLM:
        async def chat_completion_stream(self, **kwargs):
            yield {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "call-1",
                        "function": {
                            "name": "project_host_run_command",
                            "arguments": "{\"command\": \"lark-cli auth login\"}",
                        },
                    }
                ],
            }

    class _FakeToolExecutor:
        async def execute_parallel(self, tool_calls, timeout=None):
            return [
                {
                    "ok": False,
                    "error": "Host workspace_path does not exist",
                    "requested_workspace_path": "/Volumes/苹果1_5T/work/数字化转型/CRM",
                    "command": "lark-cli auth login",
                }
            ]

    state_store = TaskRunStore(tmp_path / "runs")
    event_log = RuntimeEventLog(tmp_path / "events")
    task_run = state_store.create(
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
        session_id="session-1",
        user_goal="/lark-cli 登录",
    )
    engine = QueryEngine(
        llm_step=LLMStep(_FakeLLM()),
        tool_runner=ToolExecutionRunner(
            _FakeToolExecutor(),
            event_log=event_log,
        ),
        state_store=state_store,
        event_log=event_log,
        transcript_store=TranscriptStore(tmp_path / "transcripts"),
        max_model_steps=3,
    )

    result = await engine.run(
        task_run,
        messages=[{"role": "user", "content": "/lark-cli 登录"}],
        tools=[{"tool_name": "project_host_run_command"}],
        provider_id="provider-1",
        model_name="model-1",
        temperature=0.1,
        max_tokens=256,
    )

    assert result.task_run.status == "blocked"
    assert result.completion_decision is not None
    assert result.completion_decision.action == "blocked"
    assert "host_workspace_missing" in result.completion_decision.reasons
    assert "执行环境阻塞" in result.final_content
    assert "不能继续等待授权" in result.final_content
    assert "/Volumes/苹果1_5T/work/数字化转型/CRM" in result.final_content
    assert "lark-cli auth login" in result.final_content
    assert result.final_content != "等待你授权工具调用后继续。"


@pytest.mark.asyncio
async def test_llm_step_returns_structured_error_when_stream_raises_dns_error():
    from services.agent_runtime.v2.llm_step import LLMStep

    class _FailingLLM:
        async def chat_completion_stream(self, **kwargs):
            if False:
                yield {}
            raise OSError("[Errno 8] nodename nor servname provided, or not known")

    result = await LLMStep(_FailingLLM()).run(
        provider_id="provider-1",
        model_name="model-1",
        messages=[{"role": "user", "content": "检测登录"}],
        tools=[{"tool_name": "project_host_run_command"}],
        temperature=0.1,
        max_tokens=256,
    )

    assert result.error is not None
    assert result.error["error_type"] == "OSError"
    assert "模型服务地址无法解析" in result.error["message"]
    assert "nodename nor servname" in result.error["raw_error"]
    assert result.provider_id == "provider-1"
    assert result.model_name == "model-1"


@pytest.mark.asyncio
async def test_query_engine_returns_llm_error_content_when_stream_raises(tmp_path):
    from services.agent_runtime.core.event_log import RuntimeEventLog
    from services.agent_runtime.v2.llm_step import LLMStep
    from services.agent_runtime.v2.query_engine import QueryEngine
    from services.agent_runtime.core.state_store import TaskRunStore
    from services.agent_runtime.core.transcript_store import TranscriptStore

    class _FailingLLM:
        async def chat_completion_stream(self, **kwargs):
            if False:
                yield {}
            raise OSError("[Errno 8] nodename nor servname provided, or not known")

    state_store = TaskRunStore(tmp_path / "runs")
    event_log = RuntimeEventLog(tmp_path / "events")
    task_run = state_store.create(
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
        session_id="session-1",
        user_goal="检测登录",
    )
    engine = QueryEngine(
        llm_step=LLMStep(_FailingLLM()),
        state_store=state_store,
        event_log=event_log,
        transcript_store=TranscriptStore(tmp_path / "transcripts"),
        max_model_steps=3,
    )

    result = await engine.run(
        task_run,
        messages=[{"role": "user", "content": "检测登录"}],
        tools=[{"tool_name": "project_host_run_command"}],
        provider_id="provider-1",
        model_name="model-1",
        temperature=0.1,
        max_tokens=256,
    )

    assert result.task_run.status == "failed"
    assert result.completion_decision is not None
    assert result.completion_decision.action == "fail"
    assert "llm_error" in result.completion_decision.reasons
    assert "模型服务地址无法解析" in result.final_content
    assert "query_engine_failed" in [event["type"] for event in result.task_run.events]


def test_query_engine_blocks_when_permission_rule_denies(tmp_path):
    async def _run():
        from services.agent_runtime.core.event_log import RuntimeEventLog
        from services.agent_runtime.v2.llm_step import LLMStep
        from services.agent_runtime.v2.permission_policy import PermissionPolicy
        from services.agent_runtime.v2.permission_store import (
            PermissionRule,
            PermissionStore,
        )
        from services.agent_runtime.v2.query_engine import QueryEngine
        from services.agent_runtime.core.state_store import TaskRunStore
        from services.agent_runtime.shared.tool_execution_runner import ToolExecutionRunner
        from services.agent_runtime.core.transcript_store import TranscriptStore

        class _FakeLLM:
            async def chat_completion_stream(self, **kwargs):
                yield {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call-1",
                            "function": {
                                "name": "project_host_run_command",
                                "arguments": "{\"command\": \"npm test\"}",
                            },
                        }
                    ]
                }

        class _FakeToolExecutor:
            def __init__(self):
                self.calls = 0

            async def execute_parallel(self, tool_calls, timeout=None):
                self.calls += 1
                return [{"exit_code": 0, "stdout": "should not run"}]

        permission_store = PermissionStore(tmp_path / "permissions")
        permission_store.save_rule(
            PermissionRule(
                rule_id="rule-deny",
                behavior="deny",
                tool_name="project_host_run_command",
                project_id="proj-1",
                username="tester",
                chat_session_id="chat-1",
                matcher={"command_prefix": "npm test"},
            )
        )
        executor = _FakeToolExecutor()
        state_store = TaskRunStore(tmp_path / "runs")
        event_log = RuntimeEventLog(tmp_path / "events")
        task_run = state_store.create(
            project_id="proj-1",
            username="tester",
            chat_session_id="chat-1",
            session_id="session-1",
            user_goal="运行测试",
        )
        engine = QueryEngine(
            llm_step=LLMStep(_FakeLLM()),
            tool_runner=ToolExecutionRunner(
                executor,
                event_log=event_log,
                permission_policy=PermissionPolicy(permission_store),
                project_id="proj-1",
                username="tester",
                chat_session_id="chat-1",
                workspace_trusted=True,
            ),
            state_store=state_store,
            event_log=event_log,
            transcript_store=TranscriptStore(tmp_path / "transcripts"),
            max_model_steps=3,
        )

        result = await engine.run(
            task_run,
            messages=[{"role": "user", "content": "运行测试"}],
            tools=[{"tool_name": "project_host_run_command"}],
            provider_id="provider-1",
            model_name="model-1",
            temperature=0.1,
            max_tokens=256,
        )

        assert executor.calls == 0
        assert result.task_run.status == "blocked"
        assert result.completion_decision is not None
        assert result.completion_decision.action == "blocked"
        assert "permission_denied" in result.completion_decision.reasons
        assert result.observations[0].status == "blocked"
        assert result.observations[0].raw_result["permission_decision"]["behavior"] == "deny"
        assert "query_engine_blocked" in [event["type"] for event in result.task_run.events]

    asyncio.run(_run())


@pytest.mark.asyncio
async def test_query_engine_empty_model_response_does_not_complete(tmp_path):
    from services.agent_runtime.core.event_log import RuntimeEventLog
    from services.agent_runtime.v2.llm_step import LLMStep
    from services.agent_runtime.v2.query_engine import QueryEngine
    from services.agent_runtime.core.state_store import TaskRunStore
    from services.agent_runtime.core.transcript_store import TranscriptStore

    class _EmptyLLM:
        async def chat_completion_stream(self, **kwargs):
            if False:
                yield {}

    state_store = TaskRunStore(tmp_path / "runs")
    event_log = RuntimeEventLog(tmp_path / "events")
    task_run = state_store.create(
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
        session_id="session-1",
        user_goal="查询状态",
    )
    engine = QueryEngine(
        llm_step=LLMStep(_EmptyLLM()),
        state_store=state_store,
        event_log=event_log,
        transcript_store=TranscriptStore(tmp_path / "transcripts"),
        max_model_steps=1,
    )

    result = await engine.run(
        task_run,
        messages=[{"role": "user", "content": "查询状态"}],
        tools=[],
        provider_id="provider-1",
        model_name="model-1",
        temperature=0.1,
        max_tokens=256,
        task_tree_verified=True,
        goal_covered=True,
    )

    assert result.task_run.status == "failed"
    assert result.completion_decision is not None
    assert result.completion_decision.action == "fail"
    assert "model_step_budget_exceeded" in result.completion_decision.reasons


@pytest.mark.asyncio
async def test_query_engine_continue_decision_runs_another_model_step(tmp_path):
    from services.agent_runtime.shared.completion_policy import CompletionDecision
    from services.agent_runtime.core.event_log import RuntimeEventLog
    from services.agent_runtime.v2.llm_step import LLMStep
    from services.agent_runtime.v2.query_engine import QueryEngine
    from services.agent_runtime.core.state_store import TaskRunStore
    from services.agent_runtime.core.transcript_store import TranscriptStore

    class _FakeLLM:
        def __init__(self):
            self.calls = 0

        async def chat_completion_stream(self, **kwargs):
            self.calls += 1
            yield {"content": f"第 {self.calls} 轮"}

    class _ContinueThenCompletePolicy:
        def __init__(self):
            self.calls = 0

        def evaluate(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return CompletionDecision("continue", ["goal_not_confirmed"])
            return CompletionDecision("complete", ["completion_gate_satisfied"])

    llm = _FakeLLM()
    policy = _ContinueThenCompletePolicy()
    state_store = TaskRunStore(tmp_path / "runs")
    event_log = RuntimeEventLog(tmp_path / "events")
    task_run = state_store.create(
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
        session_id="session-1",
        user_goal="查询状态",
    )
    engine = QueryEngine(
        llm_step=LLMStep(llm),
        state_store=state_store,
        event_log=event_log,
        transcript_store=TranscriptStore(tmp_path / "transcripts"),
        completion_policy=policy,
        max_model_steps=3,
    )

    result = await engine.run(
        task_run,
        messages=[{"role": "user", "content": "查询状态"}],
        tools=[],
        provider_id="provider-1",
        model_name="model-1",
        temperature=0.1,
        max_tokens=256,
    )

    assert llm.calls == 2
    assert policy.calls == 2
    assert result.task_run.status == "completed"
    assert result.final_content == "第 2 轮"
    assert result.completion_decision is not None
    assert result.completion_decision.action == "complete"


@pytest.mark.asyncio
async def test_query_engine_continue_budget_exceeded_fails_not_running(tmp_path):
    from services.agent_runtime.core.event_log import RuntimeEventLog
    from services.agent_runtime.v2.llm_step import LLMStep
    from services.agent_runtime.v2.query_engine import QueryEngine
    from services.agent_runtime.core.state_store import TaskRunStore
    from services.agent_runtime.core.transcript_store import TranscriptStore

    class _FakeLLM:
        def __init__(self):
            self.calls = 0

        async def chat_completion_stream(self, **kwargs):
            self.calls += 1
            yield {"content": f"未收口响应 {self.calls}"}

    llm = _FakeLLM()
    state_store = TaskRunStore(tmp_path / "runs")
    event_log = RuntimeEventLog(tmp_path / "events")
    task_run = state_store.create(
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
        session_id="session-1",
        user_goal="查询状态",
    )
    engine = QueryEngine(
        llm_step=LLMStep(llm),
        state_store=state_store,
        event_log=event_log,
        transcript_store=TranscriptStore(tmp_path / "transcripts"),
        max_model_steps=2,
    )

    result = await engine.run(
        task_run,
        messages=[{"role": "user", "content": "查询状态"}],
        tools=[],
        provider_id="provider-1",
        model_name="model-1",
        temperature=0.1,
        max_tokens=256,
        task_tree_verified=False,
        goal_covered=False,
    )

    assert llm.calls == 2
    assert result.task_run.status == "failed"
    assert result.completion_decision is not None
    assert result.completion_decision.action == "fail"
    assert "model_step_budget_exceeded" in result.completion_decision.reasons
    assert "query_engine_paused" not in [event["type"] for event in result.task_run.events]


@pytest.mark.asyncio
async def test_agent_runtime_v2_query_engine_requires_real_completion_evidence(tmp_path):
    from services.agent_runtime.core.event_log import RuntimeEventLog
    from services.agent_runtime.v2.runtime import AgentTaskRuntime
    from services.agent_runtime.core.state_store import TaskRunStore
    from services.agent_runtime.core.transcript_store import TranscriptStore

    class _FakeLLM:
        def __init__(self):
            self.calls = 0

        async def chat_completion_stream(self, **kwargs):
            self.calls += 1
            yield {"content": f"第 {self.calls} 轮回答"}

    llm = _FakeLLM()
    runtime = AgentTaskRuntime(
        llm_service=llm,
        runtime_options={"max_model_steps": 2},
        state_store=TaskRunStore(tmp_path / "runs"),
        transcript_store=TranscriptStore(tmp_path / "transcripts"),
        event_log=RuntimeEventLog(tmp_path / "events"),
    )

    chunks = []
    async for chunk in runtime.run(
        session_id="session-1",
        user_message="修复项目里的问题",
        tools=[],
        provider_id="provider-1",
        model_name="model-1",
        temperature=0.1,
        max_tokens=256,
        project_id="proj-1",
        employee_id="emp-1",
        cancel_event=asyncio.Event(),
        username="tester",
        chat_session_id="chat-1",
    ):
        chunks.append(chunk)

    assert llm.calls == 1
    assert chunks[1]["completion_decision"]["action"] == "verify"
    assert "verification_required" in chunks[1]["completion_decision"]["reasons"]
    assert chunks[-1]["agent_runtime"]["status"] == "verifying"


@pytest.mark.asyncio
async def test_agent_runtime_v2_query_engine_mode_is_default(tmp_path):
    from services.agent_runtime.core.event_log import RuntimeEventLog
    from services.agent_runtime.v2.runtime import AgentTaskRuntime
    from services.agent_runtime.core.state_store import TaskRunStore
    from services.agent_runtime.core.transcript_store import TranscriptStore

    class _FakeLLM:
        async def chat_completion_stream(self, **kwargs):
            yield {"content": "可以继续。"}

    runtime = AgentTaskRuntime(
        llm_service=_FakeLLM(),
        state_store=TaskRunStore(tmp_path / "runs"),
        transcript_store=TranscriptStore(tmp_path / "transcripts"),
        event_log=RuntimeEventLog(tmp_path / "events"),
    )

    chunks = []
    async for chunk in runtime.run(
        session_id="session-1",
        user_message="查询状态",
        tools=[],
        provider_id="provider-1",
        model_name="model-1",
        temperature=0.1,
        max_tokens=256,
        project_id="proj-1",
        employee_id="emp-1",
        cancel_event=asyncio.Event(),
        username="tester",
        chat_session_id="chat-1",
    ):
        chunks.append(chunk)

    assert chunks[0]["type"] == "runtime_status"
    assert chunks[1]["mode"] == "query_engine"
    assert chunks[-1]["type"] == "done"
    assert chunks[-1]["content"] == "可以继续。"
    assert chunks[-1]["agent_runtime"]["status"] == "completed"


def test_agent_runtime_v2_query_engine_mode_accepts_injected_llm_service(tmp_path):
    from services.agent_runtime.core.event_log import RuntimeEventLog
    from services.agent_runtime.v2.runtime import AgentTaskRuntime
    from services.agent_runtime.core.state_store import TaskRunStore
    from services.agent_runtime.core.transcript_store import TranscriptStore

    class _FakeLLM:
        async def chat_completion_stream(self, **kwargs):
            yield {"content": "已注入。"}

    runtime = AgentTaskRuntime(
        llm_service=_FakeLLM(),
        state_store=TaskRunStore(tmp_path / "runs"),
        transcript_store=TranscriptStore(tmp_path / "transcripts"),
        event_log=RuntimeEventLog(tmp_path / "events"),
    )
    chunks = []

    async def _run():
        async for chunk in runtime.run(
            session_id="session-1",
            user_message="查询状态",
            tools=[],
            provider_id="provider-1",
            model_name="model-1",
            temperature=0.1,
            max_tokens=256,
            project_id="proj-1",
            employee_id="emp-1",
            cancel_event=asyncio.Event(),
            username="tester",
            chat_session_id="chat-1",
        ):
            chunks.append(chunk)

    asyncio.run(_run())

    assert chunks[0]["type"] == "runtime_status"
    assert chunks[1]["mode"] == "query_engine"
    assert chunks[-1]["type"] == "done"
    assert chunks[-1]["content"] == "已注入。"
    assert chunks[-1]["agent_runtime"]["status"] == "completed"


def test_agent_runtime_v2_query_engine_mode_requires_explicit_llm_service(tmp_path):
    from services.agent_runtime.core.event_log import RuntimeEventLog
    from services.agent_runtime.v2.runtime import AgentTaskRuntime
    from services.agent_runtime.core.state_store import TaskRunStore
    from services.agent_runtime.core.transcript_store import TranscriptStore

    runtime = AgentTaskRuntime(
        state_store=TaskRunStore(tmp_path / "runs"),
        transcript_store=TranscriptStore(tmp_path / "transcripts"),
        event_log=RuntimeEventLog(tmp_path / "events"),
    )
    chunks = []

    async def _run():
        async for chunk in runtime.run(
            session_id="session-1",
            user_message="查询状态",
            tools=[],
            provider_id="provider-1",
            model_name="model-1",
            temperature=0.1,
            max_tokens=256,
            project_id="proj-1",
            employee_id="emp-1",
            cancel_event=asyncio.Event(),
            username="tester",
            chat_session_id="chat-1",
        ):
            chunks.append(chunk)

    asyncio.run(_run())

    assert chunks[-1]["type"] == "error"
    assert chunks[-1]["message"] == (
        "agent_runtime_v2 query engine unavailable: llm service is missing"
    )


def test_agent_runtime_v2_legacy_mode_does_not_use_fallback_factory(tmp_path):
    from services.agent_runtime.core.event_log import RuntimeEventLog
    from services.agent_runtime.v2.runtime import AgentTaskRuntime
    from services.agent_runtime.core.state_store import TaskRunStore
    from services.agent_runtime.core.transcript_store import TranscriptStore

    class _FakeLLM:
        async def chat_completion_stream(self, **kwargs):
            yield {"content": "v2 ok"}

    runtime = AgentTaskRuntime(
        llm_service=_FakeLLM(),
        state_store=TaskRunStore(tmp_path / "runs"),
        transcript_store=TranscriptStore(tmp_path / "transcripts"),
        event_log=RuntimeEventLog(tmp_path / "events"),
    )
    chunks = []

    async def _run():
        async for chunk in runtime.run(
            session_id="session-1",
            user_message="交给 legacy",
            tools=[],
            provider_id="provider-1",
            model_name="model-1",
            temperature=0.1,
            max_tokens=256,
            project_id="proj-1",
            employee_id="emp-1",
            cancel_event=asyncio.Event(),
            username="tester",
            chat_session_id="chat-1",
            assistant_workflow={"agent_runtime_mode": "legacy"},
        ):
            chunks.append(chunk)

    asyncio.run(_run())

    assert chunks[0]["type"] == "runtime_status"
    assert chunks[1]["mode"] == "query_engine"
    assert chunks[-1]["type"] == "done"
    assert chunks[-1]["content"] == "v2 ok"


def test_agent_runtime_v2_query_engine_default_uses_injected_llm(tmp_path):
    from services.agent_runtime.core.event_log import RuntimeEventLog
    from services.agent_runtime.v2.runtime import AgentTaskRuntime
    from services.agent_runtime.core.state_store import TaskRunStore
    from services.agent_runtime.core.transcript_store import TranscriptStore

    class _FakeLLM:
        async def chat_completion_stream(self, **kwargs):
            yield {"content": "query ok"}

    runtime = AgentTaskRuntime(
        llm_service=_FakeLLM(),
        state_store=TaskRunStore(tmp_path / "runs"),
        transcript_store=TranscriptStore(tmp_path / "transcripts"),
        event_log=RuntimeEventLog(tmp_path / "events"),
    )
    chunks = []

    async def _run():
        async for chunk in runtime.run(
            session_id="session-1",
            user_message="默认 v2",
            tools=[],
            provider_id="provider-1",
            model_name="model-1",
            temperature=0.1,
            max_tokens=256,
            project_id="proj-1",
            employee_id="emp-1",
            cancel_event=asyncio.Event(),
            username="tester",
            chat_session_id="chat-1",
        ):
            chunks.append(chunk)

    asyncio.run(_run())

    assert chunks[1]["mode"] == "query_engine"
    assert chunks[-1]["type"] == "done"
    assert chunks[-1]["content"] == "query ok"


def test_agent_runtime_v2_accepts_injected_conversation_manager():
    from services.agent_runtime.v2.runtime import AgentTaskRuntime

    conversation_manager = object()

    runtime = AgentTaskRuntime(
        conversation_manager=conversation_manager,
    )

    assert runtime._resolve_conversation_manager() is conversation_manager


def test_agent_runtime_v2_tool_executor_factory_receives_query_context():
    from services.agent_runtime.v2.runtime import AgentTaskRuntime

    executor = object()
    calls = []

    def _build_tool_executor(**kwargs):
        calls.append(kwargs)
        return executor

    runtime = AgentTaskRuntime(tool_executor_factory=_build_tool_executor)

    resolved = runtime._resolve_tool_executor(
        project_id="proj-1",
        employee_id="emp-1",
        username="tester",
        chat_session_id="chat-1",
        role_ids=["role-1"],
        allowed_tool_names=["status_lookup"],
        local_connector=None,
        local_connector_workspace_path="/tmp/local",
        host_workspace_path="/tmp/host",
        local_connector_sandbox_mode="workspace-write",
        global_assistant_bridge_handler=None,
    )

    assert resolved is executor
    assert calls == [
        {
            "project_id": "proj-1",
            "employee_id": "emp-1",
            "username": "tester",
            "chat_session_id": "chat-1",
            "role_ids": ["role-1"],
            "allowed_tool_names": ["status_lookup"],
            "local_connector": None,
            "local_connector_workspace_path": "/tmp/local",
            "host_workspace_path": "/tmp/host",
            "local_connector_sandbox_mode": "workspace-write",
            "global_assistant_bridge_handler": None,
        }
    ]


def test_agent_runtime_v2_query_engine_uses_injected_tool_executor(tmp_path):
    from services.agent_runtime.core.event_log import RuntimeEventLog
    from services.agent_runtime.v2.runtime import AgentTaskRuntime
    from services.agent_runtime.core.state_store import TaskRunStore
    from services.agent_runtime.core.transcript_store import TranscriptStore

    class _FakeLLM:
        def __init__(self):
            self.calls = 0

        async def chat_completion_stream(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                yield {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call-1",
                            "function": {
                                "name": "status_lookup",
                                "arguments": "{}",
                            },
                        }
                    ]
                }
                return
            yield {"content": "查询结果：tool ok"}

    class _FakeToolExecutor:
        def __init__(self):
            self.calls = []

        async def execute_parallel(self, tool_calls, timeout=None):
            self.calls.extend(tool_calls)
            return [{"ok": True, "result": "tool ok"}]

    executor = _FakeToolExecutor()
    runtime = AgentTaskRuntime(
        llm_service=_FakeLLM(),
        tool_executor=executor,
        state_store=TaskRunStore(tmp_path / "runs"),
        transcript_store=TranscriptStore(tmp_path / "transcripts"),
        event_log=RuntimeEventLog(tmp_path / "events"),
    )
    chunks = []

    async def _run():
        async for chunk in runtime.run(
            session_id="session-1",
            user_message="查询状态",
            tools=[
                {
                    "tool_name": "status_lookup",
                    "parameters_schema": {"type": "object", "properties": {}},
                }
            ],
            provider_id="provider-1",
            model_name="model-1",
            temperature=0.1,
            max_tokens=256,
            project_id="proj-1",
            employee_id="emp-1",
            cancel_event=asyncio.Event(),
            username="tester",
            chat_session_id="chat-1",
        ):
            chunks.append(chunk)

    asyncio.run(_run())

    assert executor.calls[0]["function"]["name"] == "status_lookup"
    assert chunks[1]["mode"] == "query_engine"
    assert chunks[-1]["type"] == "done"
    assert chunks[-1]["content"] == "查询结果：tool ok"


@pytest.mark.asyncio
async def test_agent_runtime_v2_done_marks_permission_waiting_user(tmp_path):
    from services.agent_runtime.core.event_log import RuntimeEventLog
    from services.agent_runtime.v2.runtime import AgentTaskRuntime
    from services.agent_runtime.core.state_store import TaskRunStore
    from services.agent_runtime.core.transcript_store import TranscriptStore

    class _FakeLLM:
        async def chat_completion_stream(self, **kwargs):
            yield {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "call-1",
                        "function": {
                            "name": "project_host_run_command",
                            "arguments": "{\"command\": \"sudo echo ok\"}",
                        },
                    }
                ]
            }

    runtime = AgentTaskRuntime(
        llm_service=_FakeLLM(),
        state_store=TaskRunStore(tmp_path / "runs"),
        transcript_store=TranscriptStore(tmp_path / "transcripts"),
        event_log=RuntimeEventLog(tmp_path / "events"),
    )

    chunks = []
    async for chunk in runtime.run(
        session_id="session-1",
        user_message="运行高风险命令",
        tools=[{"tool_name": "project_host_run_command"}],
        provider_id="provider-1",
        model_name="model-1",
        temperature=0.1,
        max_tokens=256,
        project_id="proj-1",
        employee_id="emp-1",
        cancel_event=asyncio.Event(),
        username="tester",
        chat_session_id="chat-1",
        host_workspace_path="/tmp/untrusted-workspace",
    ):
        chunks.append(chunk)

    assert chunks[-1]["type"] == "done"
    assert chunks[-1]["completed_reason"] == "waiting_user_action"
    assert chunks[-1]["guard_reason"] == "waiting_user_action"
    assert chunks[-1]["agent_runtime"]["status"] == "waiting_user"
    assert chunks[-1]["content"] == "等待你授权工具调用后继续。"


@pytest.mark.asyncio
async def test_agent_runtime_v2_done_preserves_operation_wait_task_interaction_schema(tmp_path, monkeypatch):
    from services.agent_runtime.core.event_log import RuntimeEventLog
    from services.agent_runtime.v2.runtime import AgentTaskRuntime
    from services.agent_runtime.core.state_store import TaskRunStore
    from services.agent_runtime.core.transcript_store import TranscriptStore

    class _FakeLLM:
        async def chat_completion_stream(self, **kwargs):
            yield {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "call-1",
                        "function": {
                            "name": "project_host_run_command",
                            "arguments": "{\"command\": \"lark-cli auth login\"}",
                        },
                    }
                ]
            }

    async def _fake_execute_parallel(self, tool_calls, timeout=None):
        return [
            {
                "ok": False,
                "source": "operation_wait_task",
                "operation_kind": "auth_login",
                "operation_label": "网页登录授权",
                "status": "waiting_user_action",
                "status_label": "等待操作",
                "task_id": "operation-wait-1",
                "command": "lark-cli auth login",
                "interaction_schema": {
                    "title": "选择 lark-cli 授权业务域",
                    "schema": [{"label": "业务域", "prop": "domains"}],
                },
                "action_type": "interaction_form",
            }
        ]

    monkeypatch.setattr(
        "services.tool_executor.ToolExecutor.execute_parallel",
        _fake_execute_parallel,
    )

    runtime = AgentTaskRuntime(
        llm_service=_FakeLLM(),
        state_store=TaskRunStore(tmp_path / "runs"),
        transcript_store=TranscriptStore(tmp_path / "transcripts"),
        event_log=RuntimeEventLog(tmp_path / "events"),
    )

    chunks = []
    async for chunk in runtime.run(
        session_id="session-1",
        user_message="/lark-cli 登录",
        tools=[{"tool_name": "project_host_run_command"}],
        provider_id="provider-1",
        model_name="model-1",
        temperature=0.1,
        max_tokens=256,
        project_id="proj-1",
        employee_id="emp-1",
        cancel_event=asyncio.Event(),
        username="tester",
        chat_session_id="chat-1",
    ):
        chunks.append(chunk)

    assert chunks[-1]["type"] == "done"
    assert chunks[-1]["completed_reason"] == "waiting_user_action"
    assert chunks[-1]["source"] == "operation_wait_task"
    assert chunks[-1]["task_id"] == "operation-wait-1"
    assert chunks[-1]["action_type"] == "interaction_form"
    assert chunks[-1]["interaction_schema"]["title"] == "选择 lark-cli 授权业务域"


def test_completion_policy_requires_verification_for_dev_task():
    from services.agent_runtime.shared.completion_policy import CompletionPolicy
    from services.agent_runtime.shared.verification_policy import VerificationPolicy

    verification = VerificationPolicy().build_state(user_goal="修复接口并跑测试")
    decision = CompletionPolicy().evaluate(
        response_content="已修改完成",
        verification=verification,
        task_tree_verified=True,
        goal_covered=True,
    )

    assert decision.action == "verify"
    assert "verification_required" in decision.reasons


def test_project_chat_done_operation_wait_task_builds_auth_operation_event():
    from routers.projects import _build_project_chat_operation_event

    event = _build_project_chat_operation_event(
        {
            "type": "done",
            "source": "operation_wait_task",
            "chat_session_id": "chat-1",
            "completed_reason": "waiting_user_action",
            "guard_reason": "waiting_user_action",
            "content": "内部授权任务已创建，等待你在表单中选择授权范围。",
            "workflow_kind": "auth_login",
            "workflow_label": "网页登录授权",
            "task_id": "operation-wait-1",
            "status": "waiting_user_action",
            "action_type": "interaction_form",
            "interaction_schema": {
                "title": "选择 lark-cli 授权业务域",
                "schema": [{"label": "业务域", "prop": "domains"}],
            },
        }
    )

    assert event is not None
    assert event["type"] == "operation_event"
    assert event["operation_id"] == "auth:operation-wait-1"
    assert event["kind"] == "auth"
    assert event["phase"] == "waiting_user"
    assert event["action_type"] == "interaction_form"
    assert event["meta"]["interaction_schema"]["title"] == "选择 lark-cli 授权业务域"


def test_permission_policy_asks_when_workspace_untrusted(tmp_path):
    from services.agent_runtime.v2.permission_policy import PermissionPolicy
    from services.agent_runtime.v2.permission_store import PermissionStore

    decision = PermissionPolicy(PermissionStore(tmp_path)).evaluate(
        run_id="run-1",
        call_id="call-1",
        tool_name="project_host_run_command",
        args={"command": "sudo echo ok"},
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
        workspace_trusted=False,
    )

    assert decision.behavior == "ask"
    assert decision.risk_level == "high"
    assert decision.allowed is False


def test_background_process_registry_tracks_logs_cancel_and_resume_payload():
    from services.agent_runtime.core.background_process import (
        BackgroundProcessHandle,
        BackgroundProcessRegistry,
    )

    registry = BackgroundProcessRegistry()
    handle = registry.register(
        BackgroundProcessHandle(
            process_id="proc-1",
            command="npm run build",
            cwd="/workspace",
            resume_token="resume-1",
            cancel_token="cancel-1",
            metadata={"run_id": "run-1"},
        )
    )

    registry.append_log(handle.process_id, "building")
    registry.append_log(handle.process_id, "done")
    page = registry.read_log(handle.process_id, cursor=1, limit=1)
    cancelled = registry.cancel(handle.process_id)
    resume_payload = registry.resume_payload(handle.process_id)

    assert handle.status == "running"
    assert page["lines"] == ["done"]
    assert page["next_cursor"] == 2
    assert cancelled is not None
    assert cancelled.status == "cancelled"
    assert cancelled.terminal is True
    assert resume_payload == {
        "process_id": "proc-1",
        "status": "cancelled",
        "resume_token": "resume-1",
        "cancel_token": "cancel-1",
        "log_cursor": 2,
        "metadata": {"run_id": "run-1"},
    }


def test_gateway_message_builds_runtime_integration_envelope_for_cron_and_delivery():
    from services.agent_runtime.integrations.gateway import RuntimeGatewayMessage

    message = RuntimeGatewayMessage(
        source="cron",
        text="生成日报",
        project_id="proj-1",
        chat_session_id="chat-1",
        session_id="session-1",
        channel_id="feishu-chat",
        delivery_target="feishu:chat-1",
        schedule="0 9 * * *",
        context_from=("run-a", "", "run-b"),
        metadata={"kind": "daily"},
    )

    envelope = message.envelope()
    runtime_input = message.runtime_input()

    assert envelope.resume_key == "proj-1:chat-1:session-1:cron"
    assert runtime_input["message"] == "生成日报"
    assert runtime_input["delivery_target"] == "feishu:chat-1"
    assert runtime_input["schedule"] == "0 9 * * *"
    assert runtime_input["context_from"] == ["run-a", "run-b"]
    assert runtime_input["resume_key"] == envelope.resume_key


def test_gateway_router_dispatches_mcp_and_message_inputs_through_same_shape():
    from services.agent_runtime.integrations.gateway import RuntimeGatewayMessage, RuntimeGatewayRouter

    router = RuntimeGatewayRouter()
    seen_inputs = []

    def handler(runtime_input):
        seen_inputs.append(runtime_input)
        return {
            "text": "ok",
            "events": [{"type": "runtime_started", "source": runtime_input["source"]}],
            "metadata": {"resume_key": runtime_input["resume_key"]},
        }

    mcp_response = router.dispatch(
        RuntimeGatewayMessage(
            source="mcp",
            text="调用 MCP 工具",
            project_id="proj-1",
            chat_session_id="chat-1",
            metadata={"tool_name": "query_center.search"},
        ),
        handler,
    )
    feishu_response = router.dispatch(
        RuntimeGatewayMessage(
            source="feishu",
            text="继续任务",
            project_id="proj-1",
            chat_session_id="chat-1",
            delivery_target="feishu:chat-1",
        ),
        handler,
    )

    assert mcp_response.text == "ok"
    assert feishu_response.events[0]["source"] == "feishu"
    assert seen_inputs[0]["source"] == "mcp"
    assert seen_inputs[1]["delivery_target"] == "feishu:chat-1"
    assert seen_inputs[0]["resume_key"] == "proj-1:chat-1:mcp"


def test_transcript_checkpoint_filters_tool_only_assistant_content(tmp_path):
    from services.agent_runtime.core.context_checkpoint import ContextCheckpointBuilder
    from services.agent_runtime.core.transcript_store import TranscriptStore

    store = TranscriptStore(tmp_path / "transcripts")
    store.append("run-1", "user_input", {"content": "请运行测试并修复失败"})
    store.append(
        "run-1",
        "model_output",
        {
            "content": "",
            "tool_calls": [
                {
                    "call_id": "call-1",
                    "tool_name": "project_host_run_command",
                    "arguments": '{"command": "pytest -q"}',
                }
            ],
        },
    )
    store.append(
        "run-1",
        "tool_observation",
        {
            "call_id": "call-1",
            "tool_name": "project_host_run_command",
            "status": "failed",
            "summary": "1 failed",
        },
    )
    store.append("run-1", "model_output", {"content": "已定位失败用例。"})

    checkpoint = ContextCheckpointBuilder(store).build("run-1", max_events=10)
    resume_messages = checkpoint.to_resume_messages()

    assert checkpoint.tool_call_count == 1
    assert checkpoint.observation_count == 1
    assert "pytest -q" in checkpoint.summary
    assert "1 failed" in checkpoint.summary
    assert resume_messages[0]["role"] == "system"
    assert "checkpoint" in resume_messages[0]["content"].lower()
    assert all(message.get("content") for message in resume_messages)
    assert not any(message.get("content") == "" for message in resume_messages)


def test_runtime_inspector_snapshot_includes_checkpoint(tmp_path):
    from services.agent_runtime.core.event_log import RuntimeEventLog
    from services.agent_runtime.core.state_store import TaskRunStore
    from services.agent_runtime.core.transcript_store import TranscriptStore
    from services.agent_runtime.v2.run_inspector import AgentRuntimeInspector

    state_store = TaskRunStore(tmp_path / "runs")
    transcript_store = TranscriptStore(tmp_path / "transcripts")
    run = state_store.create(
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
        session_id="session-1",
        user_goal="继续开发 runtime",
    )
    transcript_store.append(run.run_id, "user_input", {"content": "继续开发 runtime"})
    transcript_store.append(
        run.run_id,
        "tool_observation",
        {"tool_name": "pytest", "status": "passed", "summary": "91 passed"},
    )

    snapshot = AgentRuntimeInspector(
        state_store=state_store,
        event_log=RuntimeEventLog(tmp_path / "events"),
        transcript_store=transcript_store,
    ).get_run_snapshot(run.run_id)

    assert snapshot is not None
    assert snapshot["checkpoint"]["latest_user_goal"] == "继续开发 runtime"
    assert "91 passed" in snapshot["checkpoint"]["summary"]
    assert snapshot["background_processes"] == []


def test_runtime_inspector_snapshot_includes_background_processes(tmp_path):
    from services.agent_runtime.core.background_process import (
        BackgroundProcessHandle,
        BackgroundProcessRegistry,
    )
    from services.agent_runtime.core.state_store import TaskRunStore
    from services.agent_runtime.v2.run_inspector import AgentRuntimeInspector

    state_store = TaskRunStore(tmp_path / "runs")
    registry = BackgroundProcessRegistry()
    run = state_store.create(
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
        session_id="session-1",
        user_goal="构建",
    )
    registry.register(
        BackgroundProcessHandle(
            process_id="proc-1",
            command="npm run build",
            metadata={"run_id": run.run_id},
        )
    )
    registry.register(
        BackgroundProcessHandle(
            process_id="proc-other",
            command="pytest",
            metadata={"run_id": "other"},
        )
    )

    snapshot = AgentRuntimeInspector(
        state_store=state_store,
        background_registry=registry,
    ).get_run_snapshot(run.run_id)

    assert snapshot is not None
    assert [item["process_id"] for item in snapshot["background_processes"]] == [
        "proc-1"
    ]


def test_context_checkpoint_is_exported_from_shared_and_v2():
    from services.agent_runtime import shared
    from services.agent_runtime import v2
    from services.agent_runtime.core.background_process import (
        BackgroundProcessHandle,
        BackgroundProcessRegistry,
    )
    from services.agent_runtime.core.context_checkpoint import ContextCheckpointBuilder

    assert shared.ContextCheckpointBuilder is ContextCheckpointBuilder
    assert v2.ContextCheckpointBuilder is ContextCheckpointBuilder
    assert shared.BackgroundProcessHandle is BackgroundProcessHandle
    assert shared.BackgroundProcessRegistry is BackgroundProcessRegistry
    assert v2.BackgroundProcessHandle is BackgroundProcessHandle
    assert v2.BackgroundProcessRegistry is BackgroundProcessRegistry


def test_permission_policy_uses_registry_metadata_without_lowering_command_risk(tmp_path):
    from services.agent_runtime.v2.permission_policy import PermissionPolicy
    from services.agent_runtime.v2.permission_store import PermissionStore

    policy = PermissionPolicy(PermissionStore(tmp_path))
    low_metadata = policy.evaluate(
        run_id="run-1",
        call_id="call-1",
        tool_name="project_host_run_command",
        args={"command": "sudo echo ok"},
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
        workspace_trusted=True,
        tool_entry={"risk_level": "low", "permission_scope": "project"},
    )
    high_metadata = policy.evaluate(
        run_id="run-1",
        call_id="call-2",
        tool_name="custom_tool",
        args={},
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
        workspace_trusted=False,
        tool_entry={"risk_level": "high", "permission_scope": "workspace"},
    )

    assert low_metadata.risk_level == "high"
    assert low_metadata.behavior == "ask"
    assert high_metadata.risk_level == "high"
    assert high_metadata.behavior == "ask"
    assert high_metadata.reason == "workspace is not trusted"


def test_permission_action_allow_always_reuses_lark_auth_status_signature(tmp_path):
    from services.agent_runtime.core.event_log import RuntimeEventLog
    from services.agent_runtime.v2.permission_actions import PermissionActionService
    from services.agent_runtime.v2.permission_policy import PermissionPolicy
    from services.agent_runtime.v2.permission_store import PermissionStore
    from services.agent_runtime.shared.trust_policy import TrustPolicy

    store = PermissionStore(tmp_path / "permissions")
    service = PermissionActionService(
        permission_store=store,
        trust_policy=TrustPolicy(tmp_path / "trust"),
        event_log=RuntimeEventLog(tmp_path / "events"),
    )

    rule = service.apply_permission_action(
        action="allow_always",
        run_id="run-1",
        call_id="call-1",
        tool_name="project_host_run_command",
        args={"command": "/opt/plugin/bin/lark-cli auth status --format json"},
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
    )
    allowed = PermissionPolicy(store).evaluate(
        run_id="run-2",
        call_id="call-2",
        tool_name="project_host_run_command",
        args={"command": "lark-cli auth status"},
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-2",
        workspace_trusted=False,
    )
    other_command = PermissionPolicy(store).evaluate(
        run_id="run-2",
        call_id="call-3",
        tool_name="project_host_run_command",
        args={"command": "lark-cli contact +search-user --query tester"},
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-2",
        workspace_trusted=True,
    )

    assert rule.scope == "project"
    assert rule.chat_session_id == ""
    assert rule.matcher == {"command_signature": "lark-cli auth status"}
    assert allowed.behavior == "allow_always"
    assert allowed.matched_rule is not None
    assert other_command.behavior == "allow_once"


def test_agent_runtime_trace_merges_lark_auth_permission_cards_by_signature():
    from routers import projects as projects_router

    trace = projects_router._agent_runtime_trace_from_events(
        [
            {
                "event_type": "permission_decision",
                "payload": {
                    "args": {"command": "/opt/bin/lark-cli auth status --format json"},
                    "decision": {
                        "behavior": "ask",
                        "call_id": "call-1",
                        "tool_name": "project_host_run_command",
                    },
                },
            },
            {
                "event_type": "permission_decision",
                "payload": {
                    "args": {"command": "lark-cli auth status"},
                    "decision": {
                        "behavior": "ask",
                        "call_id": "call-2",
                        "tool_name": "project_host_run_command",
                    },
                },
            },
        ],
        "run-1",
    )

    permission_operations = [
        item
        for item in trace["operations"]
        if item["meta"].get("agent_runtime_permission") == "true"
    ]
    assert len(permission_operations) == 1
    assert permission_operations[0]["operationId"] == (
        "agent-runtime-permission:run-1:command:lark-cli auth status"
    )
    assert permission_operations[0]["meta"]["call_id"] == "call-2"


@pytest.mark.asyncio
async def test_tool_runner_blocks_permission_ask_without_executor_call(tmp_path):
    from services.agent_runtime.core.event_log import RuntimeEventLog
    from services.agent_runtime.v2.permission_policy import PermissionPolicy
    from services.agent_runtime.v2.permission_store import PermissionStore
    from services.agent_runtime.shared.tool_calls import CollectedToolCall
    from services.agent_runtime.shared.tool_execution_runner import ToolExecutionRunner

    class _FakeToolExecutor:
        def __init__(self):
            self.calls = 0

        async def execute_parallel(self, tool_calls, timeout=None):
            self.calls += 1
            return [{"exit_code": 0, "stdout": "should not run"}]

    executor = _FakeToolExecutor()
    event_log = RuntimeEventLog(tmp_path / "events")
    runner = ToolExecutionRunner(
        executor,
        event_log=event_log,
        permission_policy=PermissionPolicy(PermissionStore(tmp_path / "permissions")),
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
        workspace_trusted=False,
    )

    records = await runner.execute(
        run_id="run-1",
        tool_calls=[
            CollectedToolCall(
                call_id="call-1",
                tool_name="project_host_run_command",
                arguments="{\"command\": \"npm test\"}",
                raw={},
            )
        ],
    )

    events = [item.event_type for item in event_log.list_events("run-1")]
    approval_event = next(
        item
        for item in event_log.list_events("run-1")
        if item.event_type == "approval_required"
    )
    assert executor.calls == 0
    assert len(records) == 1
    assert records[0].observation.status == "blocked"
    assert records[0].permission_decision is not None
    assert records[0].permission_decision.behavior == "ask"
    assert records[0].raw_result["permission_decision"]["behavior"] == "ask"
    assert records[0].raw_result["permission_request"]["request_id"]
    assert approval_event.session_id == "chat-1"
    assert approval_event.payload["action"] == "command.run"
    assert approval_event.payload["options"][0]["decision"] == "approve_once"
    assert approval_event.payload["options"][0]["grant_scope"] == "once"
    assert approval_event.payload["options"][-1]["decision"] == "deny"
    assert "permission_decision" in events
    assert "approval_required" in events


@pytest.mark.asyncio
async def test_tool_runner_delegates_local_builtin_tools_to_desktop_client(tmp_path):
    from services.agent_runtime.core.event_log import RuntimeEventLog
    from services.agent_runtime.v2.permission_policy import PermissionPolicy
    from services.agent_runtime.v2.permission_store import PermissionStore
    from services.agent_runtime.shared.tool_calls import CollectedToolCall
    from services.agent_runtime.shared.tool_execution_runner import ToolExecutionRunner

    class _FakeToolExecutor:
        def __init__(self):
            self.calls = 0

        async def execute_parallel(self, tool_calls, timeout=None):
            self.calls += 1
            return [{"ok": False, "error": "server executor must not run"}]

    executor = _FakeToolExecutor()
    event_log = RuntimeEventLog(tmp_path / "events")
    runner = ToolExecutionRunner(
        executor,
        event_log=event_log,
        permission_policy=PermissionPolicy(PermissionStore(tmp_path / "permissions")),
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
        workspace_trusted=True,
        tool_entries=[
            {
                "tool_name": "list_files",
                "execution_backend": "builtin",
                "permission_scope": "workspace",
            }
        ],
    )

    records = await runner.execute(
        run_id="run-1",
        tool_calls=[
            CollectedToolCall(
                call_id="call-1",
                tool_name="list_files",
                arguments="{\"path\": \".\"}",
                raw={},
            )
        ],
    )

    assert executor.calls == 0
    assert len(records) == 1
    assert records[0].observation.status == "waiting_user_action"
    assert records[0].raw_result["source"] == "desktop_client_tool"
    assert records[0].raw_result["task_id"].startswith("desktop-tool-")
    assert records[0].raw_result["tool_name"] == "list_files"
    assert records[0].raw_result["tool_args"] == {"path": "."}
    events = event_log.list_events("run-1")
    assert [item.event_type for item in events].count("tool_observation_created") == 1
    observation_event = next(
        item for item in events if item.event_type == "tool_observation_created"
    )
    assert observation_event.payload["raw_result"]["source"] == "desktop_client_tool"


@pytest.mark.asyncio
async def test_tool_runner_executes_when_permission_rule_allows_once(tmp_path):
    from services.agent_runtime.core.event_log import RuntimeEventLog
    from services.agent_runtime.v2.permission_policy import PermissionPolicy
    from services.agent_runtime.v2.permission_store import (
        PermissionRule,
        PermissionStore,
    )
    from services.agent_runtime.shared.tool_calls import CollectedToolCall
    from services.agent_runtime.shared.tool_execution_runner import ToolExecutionRunner

    class _FakeToolExecutor:
        def __init__(self):
            self.calls = 0
            self.tool_calls = []

        async def execute_parallel(self, tool_calls, timeout=None):
            self.calls += 1
            self.tool_calls.extend(tool_calls)
            return [{"exit_code": 0, "stdout": "allowed"}]

    store = PermissionStore(tmp_path / "permissions")
    store.save_rule(
        PermissionRule(
            rule_id="rule-1",
            behavior="allow_once",
            tool_name="project_host_run_command",
            project_id="proj-1",
            username="tester",
            chat_session_id="chat-1",
            matcher={"command_prefix": "sudo echo"},
        )
    )
    executor = _FakeToolExecutor()
    event_log = RuntimeEventLog(tmp_path / "events")
    runner = ToolExecutionRunner(
        executor,
        event_log=event_log,
        permission_policy=PermissionPolicy(store),
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
        workspace_trusted=True,
    )

    records = await runner.execute(
        run_id="run-1",
        tool_calls=[
            CollectedToolCall(
                call_id="call-1",
                tool_name="project_host_run_command",
                arguments="{\"command\": \"sudo echo ok\"}",
                raw={},
            )
        ],
    )

    permission_event = next(
        item
        for item in event_log.list_events("run-1")
        if item.event_type == "permission_decision"
    )
    events = [item.event_type for item in event_log.list_events("run-1")]
    assert executor.calls == 1
    executed_args = json.loads(executor.tool_calls[0]["function"]["arguments"])
    assert executed_args["command"] == "sudo echo ok"
    assert executed_args["_agent_runtime_run_id"] == "run-1"
    assert executed_args["_agent_runtime_call_id"] == "call-1"
    assert executed_args["_agent_runtime_tool_name"] == "project_host_run_command"
    assert records[0].observation.status == "succeeded"
    assert records[0].raw_result["stdout"] == "allowed"
    assert permission_event.payload["decision"]["behavior"] == "allow_once"
    assert permission_event.payload["decision"]["decision"] == "approve_once"
    assert permission_event.payload["decision"]["grant_scope"] == "once"
    assert "approval_required" not in events


@pytest.mark.asyncio
async def test_tool_runner_records_registry_metadata_in_permission_events(tmp_path):
    from services.agent_runtime.core.event_log import RuntimeEventLog
    from services.agent_runtime.shared.tool_calls import CollectedToolCall
    from services.agent_runtime.shared.tool_execution_runner import ToolExecutionRunner
    from services.agent_runtime.v2.permission_policy import PermissionPolicy
    from services.agent_runtime.v2.permission_store import PermissionStore

    class _FakeToolExecutor:
        async def execute_parallel(self, tool_calls, timeout=None):
            return [{"exit_code": 0, "stdout": "should not run"}]

    event_log = RuntimeEventLog(tmp_path / "events")
    runner = ToolExecutionRunner(
        _FakeToolExecutor(),
        event_log=event_log,
        permission_policy=PermissionPolicy(PermissionStore(tmp_path / "permissions")),
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
        workspace_trusted=False,
        tool_entries=[
            {
                "tool_name": "custom_workspace_tool",
                "risk_level": "high",
                "permission_scope": "workspace",
                "execution_backend": "local_connector",
                "audit_policy": "full",
            }
        ],
    )

    records = await runner.execute(
        run_id="run-1",
        tool_calls=[
            CollectedToolCall(
                call_id="call-1",
                tool_name="custom_workspace_tool",
                arguments="{}",
                raw={},
            )
        ],
    )
    permission_event = next(
        item
        for item in event_log.list_events("run-1")
        if item.event_type == "permission_decision"
    )

    assert records[0].observation.status == "blocked"
    assert records[0].raw_result["tool_entry"]["execution_backend"] == "local_connector"
    assert records[0].raw_result["permission_decision"]["risk_level"] == "high"
    assert records[0].raw_result["permission_request"]["scope"] == "workspace"
    assert permission_event.payload["tool_entry"]["audit_policy"] == "full"
    assert permission_event.payload["permission_request"]["request_id"]


def test_trust_policy_marks_workspace_trusted(tmp_path):
    from services.agent_runtime.shared.trust_policy import TrustPolicy

    policy = TrustPolicy(tmp_path)
    trust = policy.mark_trusted(
        workspace_path="/tmp/workspace",
        username="tester",
    )

    assert trust.trusted is True
    assert trust.trusted_by == "tester"
    assert policy.ensure_workspace_trusted("/tmp/workspace").trusted is True


def test_permission_action_service_saves_allow_once_rule(tmp_path):
    from services.agent_runtime.core.event_log import RuntimeEventLog
    from services.agent_runtime.v2.permission_actions import PermissionActionService
    from services.agent_runtime.v2.permission_policy import PermissionPolicy
    from services.agent_runtime.v2.permission_store import PermissionStore
    from services.agent_runtime.shared.trust_policy import TrustPolicy

    store = PermissionStore(tmp_path / "permissions")
    service = PermissionActionService(
        permission_store=store,
        trust_policy=TrustPolicy(tmp_path / "trust"),
        event_log=RuntimeEventLog(tmp_path / "events"),
    )

    rule = service.apply_permission_action(
        action="allow_once",
        run_id="run-1",
        call_id="call-1",
        tool_name="project_host_run_command",
        args={"command": "sudo echo ok"},
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
    )

    allowed = PermissionPolicy(store).evaluate(
        run_id="run-1",
        call_id="call-1",
        tool_name="project_host_run_command",
        args={"command": "npm test"},
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
        workspace_trusted=True,
    )
    other_call = PermissionPolicy(store).evaluate(
        run_id="run-1",
        call_id="call-2",
        tool_name="project_host_run_command",
        args={"command": "sudo echo ok"},
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
        workspace_trusted=True,
    )

    assert rule.behavior == "allow_once"
    assert rule.matcher == {"run_id": "run-1", "call_id": "call-1"}
    assert allowed.behavior == "allow_once"
    assert other_call.behavior == "ask"


@pytest.mark.asyncio
async def test_operation_resume_runs_original_permission_tool_call(tmp_path):
    from services.agent_runtime.core.event_log import RuntimeEventLog
    from services.agent_runtime.v2.operation_resume import OperationResumeCoordinator
    from services.agent_runtime.v2.permission_actions import PermissionActionService
    from services.agent_runtime.v2.permission_policy import PermissionPolicy
    from services.agent_runtime.v2.permission_store import PermissionStore
    from services.agent_runtime.core.state_store import TaskRunStore
    from services.agent_runtime.core.transcript_store import TranscriptStore
    from services.agent_runtime.shared.trust_policy import TrustPolicy

    class _FakeToolExecutor:
        def __init__(self):
            self.calls = []

        async def execute_parallel(self, tool_calls, timeout=None):
            self.calls.extend(tool_calls)
            return [{"exit_code": 0, "stdout": "resumed"}]

    state_store = TaskRunStore(tmp_path / "runs")
    event_log = RuntimeEventLog(tmp_path / "events")
    task_run = state_store.create(
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
        session_id="session-1",
        user_goal="运行测试",
    )
    state_store.append_event(task_run, "query_engine_blocked", {}, status="waiting_user")
    event_log.append(
        task_run.run_id,
        "permission_decision",
        {
            "tool_call": {
                "call_id": "call-1",
                "tool_name": "project_host_run_command",
                "arguments": "{\"command\": \"npm test\"}",
            },
            "decision": {
                "behavior": "ask",
                "call_id": "call-1",
                "tool_name": "project_host_run_command",
            },
        },
    )
    store = PermissionStore(tmp_path / "permissions")
    PermissionActionService(
        permission_store=store,
        trust_policy=TrustPolicy(tmp_path / "trust"),
        event_log=event_log,
    ).apply_permission_action(
        action="allow_once",
        run_id=task_run.run_id,
        call_id="call-1",
        tool_name="project_host_run_command",
        args={"command": "npm test"},
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
    )
    executor = _FakeToolExecutor()

    result = await OperationResumeCoordinator(
        state_store=state_store,
        transcript_store=TranscriptStore(tmp_path / "transcripts"),
        event_log=event_log,
        permission_policy=PermissionPolicy(store),
    ).resume_permission_action(
        run_id=task_run.run_id,
        call_id="call-1",
        tool_name="project_host_run_command",
        tool_executor=executor,
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
        workspace_trusted=True,
    )

    events = [item.event_type for item in event_log.list_events(task_run.run_id)]
    reloaded = state_store.load(task_run.run_id)
    assert result.resumed is True
    assert result.status == "running"
    assert result.records[0].observation.status == "succeeded"
    resumed_args = json.loads(executor.calls[0]["function"]["arguments"])
    assert resumed_args["command"] == "npm test"
    assert resumed_args["_agent_runtime_run_id"] == task_run.run_id
    assert resumed_args["_agent_runtime_call_id"] == "call-1"
    assert resumed_args["_agent_runtime_tool_name"] == "project_host_run_command"
    assert reloaded is not None
    assert reloaded.status == "running"
    assert "operation_resume_started" in events
    assert "operation_resume_completed" in events


@pytest.mark.asyncio
async def test_operation_resume_can_continue_query_engine_after_allow_once(tmp_path):
    from services.agent_runtime.core.event_log import RuntimeEventLog
    from services.agent_runtime.v2.operation_resume import OperationResumeCoordinator
    from services.agent_runtime.v2.permission_actions import PermissionActionService
    from services.agent_runtime.v2.permission_policy import PermissionPolicy
    from services.agent_runtime.v2.permission_store import PermissionStore
    from services.agent_runtime.core.state_store import TaskRunStore
    from services.agent_runtime.core.transcript_store import TranscriptStore
    from services.agent_runtime.shared.trust_policy import TrustPolicy

    class _FakeLLM:
        def __init__(self):
            self.messages = []

        async def chat_completion_stream(self, **kwargs):
            self.messages.append(list(kwargs.get("messages") or []))
            yield {"content": "授权后的命令已执行，继续完成。"}

    class _FakeToolExecutor:
        async def execute_parallel(self, tool_calls, timeout=None):
            return [{"exit_code": 0, "stdout": "resumed"}]

    state_store = TaskRunStore(tmp_path / "runs")
    event_log = RuntimeEventLog(tmp_path / "events")
    transcript_store = TranscriptStore(tmp_path / "transcripts")
    task_run = state_store.create(
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
        session_id="session-1",
        user_goal="运行高风险命令后继续",
        metadata={"provider_id": "provider-1", "model_name": "model-1"},
    )
    transcript_store.append(
        task_run.run_id,
        "initial_messages",
        {"messages": [{"role": "user", "content": "运行高风险命令后继续"}]},
    )
    state_store.append_event(task_run, "query_engine_blocked", {}, status="waiting_user")
    event_log.append(
        task_run.run_id,
        "permission_decision",
        {
            "tool_call": {
                "call_id": "call-1",
                "tool_name": "project_host_run_command",
                "arguments": "{\"command\": \"sudo echo ok\"}",
            },
            "decision": {
                "behavior": "ask",
                "call_id": "call-1",
                "tool_name": "project_host_run_command",
            },
        },
    )
    store = PermissionStore(tmp_path / "permissions")
    PermissionActionService(
        permission_store=store,
        trust_policy=TrustPolicy(tmp_path / "trust"),
        event_log=event_log,
    ).apply_permission_action(
        action="allow_once",
        run_id=task_run.run_id,
        call_id="call-1",
        tool_name="project_host_run_command",
        args={"command": "sudo echo ok"},
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
    )
    llm = _FakeLLM()

    result = await OperationResumeCoordinator(
        state_store=state_store,
        transcript_store=transcript_store,
        event_log=event_log,
        permission_policy=PermissionPolicy(store),
    ).resume_permission_action(
        run_id=task_run.run_id,
        call_id="call-1",
        tool_name="project_host_run_command",
        tool_executor=_FakeToolExecutor(),
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
        workspace_trusted=True,
        llm_service=llm,
        tools=[{"tool_name": "project_host_run_command"}],
        provider_id="provider-1",
        model_name="model-1",
        max_model_steps=1,
    )

    events = [item.event_type for item in event_log.list_events(task_run.run_id)]
    assert result.resumed is True
    assert result.continuation is not None
    assert result.status == "completed"
    assert result.continuation.final_content == "授权后的命令已执行，继续完成。"
    assert result.continuation.task_run.status == "completed"
    assert llm.messages[0][-2]["tool_calls"][0]["id"] == "call-1"
    assert llm.messages[0][-1]["role"] == "tool"
    assert "operation_resume_continuation_started" in events
    assert "operation_resume_continuation_completed" in events


@pytest.mark.asyncio
async def test_operation_resume_can_continue_after_background_task_completion(tmp_path):
    from services.agent_runtime.core.event_log import RuntimeEventLog
    from services.agent_runtime.v2.operation_resume import OperationResumeCoordinator
    from services.agent_runtime.v2.permission_policy import PermissionPolicy
    from services.agent_runtime.v2.permission_store import PermissionStore
    from services.agent_runtime.core.state_store import TaskRunStore
    from services.agent_runtime.core.transcript_store import TranscriptStore
    from services.agent_runtime.shared.trust_policy import TrustPolicy

    class _FakeLLM:
        def __init__(self):
            self.messages = []

        async def chat_completion_stream(self, **kwargs):
            self.messages.append(list(kwargs.get("messages") or []))
            yield {"content": "后台授权完成，已继续执行。"}

    class _FakeToolExecutor:
        async def execute_parallel(self, tool_calls, timeout=None):
            return [{"exit_code": 0, "stdout": "unused"}]

    state_store = TaskRunStore(tmp_path / "runs")
    event_log = RuntimeEventLog(tmp_path / "events")
    transcript_store = TranscriptStore(tmp_path / "transcripts")
    task_run = state_store.create(
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
        session_id="session-1",
        user_goal="登录飞书后继续",
        metadata={"provider_id": "provider-1", "model_name": "model-1"},
    )
    transcript_store.append(
        task_run.run_id,
        "initial_messages",
        {"messages": [{"role": "user", "content": "登录飞书后继续"}]},
    )
    state_store.append_event(
        task_run,
        "query_engine_waiting_operation",
        {},
        status="waiting_user",
    )
    event_log.append(
        task_run.run_id,
        "tool_observation_created",
        {
            "run_id": task_run.run_id,
            "call_id": "call-1",
            "tool_name": "project_host_run_command",
            "status": "succeeded",
            "summary": "waiting",
            "raw_result": {
                "ok": False,
                "source": "operation_wait_task",
                "status": "waiting_user_action",
                "task_id": "operation-wait-1",
                "command": "lark-cli auth login",
            },
        },
    )
    llm = _FakeLLM()

    result = await OperationResumeCoordinator(
        state_store=state_store,
        transcript_store=transcript_store,
        event_log=event_log,
        permission_policy=PermissionPolicy(PermissionStore(tmp_path / "permissions")),
    ).resume_background_operation(
        run_id=task_run.run_id,
        tool_executor=_FakeToolExecutor(),
        operation_task={
            "task_id": "operation-wait-1",
            "operation_kind": "auth_login",
            "operation_label": "网页登录授权",
            "status": "succeeded",
            "status_label": "已完成",
            "ok": True,
            "execution_ok": True,
            "stdout": "authenticated",
            "stderr": "",
            "exit_code": 0,
        },
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
        workspace_trusted=True,
        llm_service=llm,
        tools=[{"tool_name": "project_host_run_command"}],
        provider_id="provider-1",
        model_name="model-1",
        max_model_steps=1,
    )

    events = [item.event_type for item in event_log.list_events(task_run.run_id)]
    assert result.resumed is True
    assert result.continuation is not None
    assert result.continuation.final_content == "后台授权完成，已继续执行。"
    assert llm.messages[0][-2]["tool_calls"][0]["id"] == "call-1"
    assert llm.messages[0][-1]["role"] == "tool"
    assert "background_operation_resume_started" in events
    assert "background_operation_continuation_completed" in events


@pytest.mark.asyncio
async def test_tool_execution_runner_passes_runtime_metadata_to_project_host_command(tmp_path):
    import json

    from services.agent_runtime.core.event_log import RuntimeEventLog
    from services.agent_runtime.v2.permission_policy import PermissionPolicy
    from services.agent_runtime.v2.permission_store import PermissionStore
    from services.agent_runtime.shared.tool_calls import CollectedToolCall
    from services.agent_runtime.shared.tool_execution_runner import ToolExecutionRunner

    class _FakeToolExecutor:
        def __init__(self):
            self.received_tool_calls = []

        async def execute_parallel(self, tool_calls, timeout=None):
            self.received_tool_calls = list(tool_calls)
            args = json.loads(tool_calls[0]["function"]["arguments"])
            return [
                {
                    "ok": True,
                    "command": args.get("command"),
                    "runtime_run_id": args.get("_agent_runtime_run_id"),
                    "runtime_call_id": args.get("_agent_runtime_call_id"),
                    "runtime_tool_name": args.get("_agent_runtime_tool_name"),
                }
            ]

    event_log = RuntimeEventLog(tmp_path / "events")
    executor = _FakeToolExecutor()
    records = await ToolExecutionRunner(
        executor,
        event_log=event_log,
        permission_policy=PermissionPolicy(PermissionStore(tmp_path / "permissions")),
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
        workspace_trusted=True,
    ).execute(
        run_id="run-1",
        tool_calls=[
            CollectedToolCall(
                call_id="call-1",
                tool_name="project_host_run_command",
                arguments='{"command": "lark-cli auth login", "timeout_sec": 20}',
                raw={
                    "id": "call-1",
                    "type": "function",
                    "function": {
                        "name": "project_host_run_command",
                        "arguments": '{"command": "lark-cli auth login", "timeout_sec": 20}',
                    },
                },
            )
        ],
    )

    executed_args = json.loads(
        executor.received_tool_calls[0]["function"]["arguments"]
    )
    permission_events = [
        item
        for item in event_log.list_events("run-1")
        if item.event_type == "permission_decision"
    ]
    assert executed_args["_agent_runtime_run_id"] == "run-1"
    assert executed_args["_agent_runtime_call_id"] == "call-1"
    assert executed_args["_agent_runtime_tool_name"] == "project_host_run_command"
    assert records[0].raw_result["runtime_run_id"] == "run-1"
    assert permission_events
    assert json.loads(
        permission_events[0].payload["tool_call"]["arguments"]
    )["_agent_runtime_run_id"] == "run-1"


def test_permission_action_service_saves_deny_rule(tmp_path):
    from services.agent_runtime.core.event_log import RuntimeEventLog
    from services.agent_runtime.v2.permission_actions import PermissionActionService
    from services.agent_runtime.v2.permission_policy import PermissionPolicy
    from services.agent_runtime.v2.permission_store import PermissionStore
    from services.agent_runtime.shared.trust_policy import TrustPolicy

    store = PermissionStore(tmp_path / "permissions")
    PermissionActionService(
        permission_store=store,
        trust_policy=TrustPolicy(tmp_path / "trust"),
        event_log=RuntimeEventLog(tmp_path / "events"),
    ).apply_permission_action(
        action="deny",
        run_id="run-1",
        call_id="call-1",
        tool_name="project_host_run_command",
        args={"command": "npm test"},
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
    )

    decision = PermissionPolicy(store).evaluate(
        run_id="run-2",
        call_id="call-2",
        tool_name="project_host_run_command",
        args={"command": "npm test"},
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
        workspace_trusted=True,
    )

    assert decision.behavior == "deny"
    assert decision.allowed is False


def test_permission_action_service_trusts_workspace(tmp_path):
    from services.agent_runtime.core.event_log import RuntimeEventLog
    from services.agent_runtime.v2.permission_actions import PermissionActionService
    from services.agent_runtime.v2.permission_store import PermissionStore
    from services.agent_runtime.shared.trust_policy import TrustPolicy

    trust_policy = TrustPolicy(tmp_path / "trust")
    service = PermissionActionService(
        permission_store=PermissionStore(tmp_path / "permissions"),
        trust_policy=trust_policy,
        event_log=RuntimeEventLog(tmp_path / "events"),
    )

    trust = service.trust_workspace(
        workspace_path="/tmp/workspace",
        username="tester",
        metadata={"project_id": "proj-1"},
    )

    assert trust.trusted is True
    assert trust.metadata["project_id"] == "proj-1"
    assert trust_policy.ensure_workspace_trusted("/tmp/workspace").trusted is True


def test_dynamic_tool_pool_deduplicates_and_summarizes_tools():
    from services.agent_runtime.v2.dynamic_tool_pool import DynamicToolPool
    from services.agent_runtime.builtin_tools.definitions import BUILTIN_TOOL_NAMES

    pool = DynamicToolPool.from_runtime_tools(
        [
            {"tool_name": "b_tool", "description": "B"},
            {"tool_name": "a_tool", "description": "A", "builtin": True},
            {"tool_name": "a_tool", "description": "duplicate"},
        ],
        tool_priority=["a_tool"],
    )

    names = pool.names()
    assert names[:2] == ["a_tool", "b_tool"]
    assert "b_tool" in names
    assert BUILTIN_TOOL_NAMES.issubset(set(names))
    summary = pool.summary()
    assert summary["effective_tool_total"] == len(BUILTIN_TOOL_NAMES) + 2
    assert summary["effective_tools"][0]["tool_name"] == "a_tool"
    assert summary["plugin_registry"]["registered_tool_total"] == len(BUILTIN_TOOL_NAMES) + 2


def test_dynamic_tool_pool_exposes_builtin_runtime_contracts():
    from services.agent_runtime.v2.dynamic_tool_pool import DynamicToolPool
    from services.agent_runtime.builtin_tools.definitions import BUILTIN_TOOL_NAMES

    pool = DynamicToolPool.from_runtime_tools([])
    names = set(pool.names())

    assert BUILTIN_TOOL_NAMES.issubset(names)
    tools = {item["tool_name"]: item for item in pool.openai_tools()}
    read_file = tools["read_file"]
    assert read_file["parameters_schema"]["required"] == ["path"]
    assert read_file["risk_level"] == "low"
    assert read_file["execution_backend"] == "builtin"
    assert tools["call_mcp_tool"]["execution_backend"] == "mcp"
    assert tools["call_mcp_tool"]["requires_approval"] is True


def test_plugin_registry_classifies_runtime_tool_sources():
    from services.agent_runtime.shared.tool_registry import PluginRegistry

    registry = PluginRegistry.from_runtime_tools(
        [
            {"tool_name": "project_host_run_command"},
            {"tool_name": "browser_open_page"},
            {"tool_name": "cli_plugin_login", "plugin_id": "hermes"},
            {"tool_name": "lark_doc_search", "skill_id": "lark-doc"},
            {"tool_name": "query_project_rules", "mcp_server_name": "query-center"},
        ]
    )

    summaries = {item["tool_name"]: item for item in registry.summary()["registered_tools"]}

    assert summaries["browser_open_page"]["source"] == "browser"
    assert summaries["project_host_run_command"]["source"] == "project"
    assert summaries["cli_plugin_login"]["source"] == "plugin"
    assert summaries["cli_plugin_login"]["plugin_id"] == "hermes"
    assert summaries["lark_doc_search"]["source"] == "skill"
    assert summaries["query_project_rules"]["source"] == "mcp"


def test_plugin_registry_reads_skill_manifest_version_and_blocks_untrusted_project_skill(tmp_path):
    from services.agent_runtime.shared.tool_registry import (
        PluginRegistry,
        PluginRegistryContext,
    )

    skill_dir = tmp_path / ".ai-employee" / "skills" / "my-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "manifest.json").write_text(
        (
            "{\n"
            "  \"id\": \"my-skill\",\n"
            "  \"name\": \"My Skill\",\n"
            "  \"version\": \"1.2.3\",\n"
            "  \"description\": \"Local project skill\"\n"
            "}\n"
        ),
        encoding="utf-8",
    )

    registry = PluginRegistry.from_runtime_tools(
        [{"tool_name": "my_tool", "skill_id": "my-skill"}],
        context=PluginRegistryContext(
            workspace_path=str(tmp_path),
            workspace_trusted=False,
            skill_roots=[tmp_path / ".ai-employee" / "skills"],
        ),
    )

    summary = registry.summary()
    tool = summary["registered_tools"][0]
    assert tool["version"] == "1.2.3"
    assert tool["plugin_name"] == "My Skill"
    assert tool["requires_trust"] is True
    assert tool["trusted"] is False
    assert tool["available"] is False
    assert tool["load_status"] == "blocked_untrusted_workspace"
    assert registry.names() == []


def test_dynamic_tool_pool_filters_browser_tools_until_workspace_trusted():
    from services.agent_runtime.v2.dynamic_tool_pool import DynamicToolPool
    from services.agent_runtime.shared.tool_registry import PluginRegistryContext
    from services.agent_runtime.builtin_tools.definitions import BUILTIN_TOOL_NAMES

    untrusted_pool = DynamicToolPool.from_runtime_tools(
        [],
        context=PluginRegistryContext(
            workspace_trusted=False,
            include_browser_tools=True,
            browser_bridge_available=True,
        ),
    )
    trusted_pool = DynamicToolPool.from_runtime_tools(
        [],
        context=PluginRegistryContext(
            workspace_trusted=True,
            include_browser_tools=True,
            browser_bridge_available=True,
        ),
    )

    assert set(untrusted_pool.names()) == BUILTIN_TOOL_NAMES - {
        "list_files",
        "read_file",
        "search_text",
        "apply_patch",
        "write_file",
        "check_command_risk",
        "run_command",
        "download_file",
    }
    assert set(trusted_pool.names()) >= {
        "global_assistant_browser_actions",
        "global_assistant_browser_requests",
    }
    browser_summary = {
        item["tool_name"]: item
        for item in trusted_pool.summary()["effective_tools"]
    }["global_assistant_browser_actions"]
    assert browser_summary["source"] == "browser"
    assert browser_summary["plugin_id"] == "browser-tools"
    assert browser_summary["version"] == "builtin"


def test_plugin_registry_uses_cli_plugin_status_for_availability():
    from services.agent_runtime.shared.tool_registry import (
        PluginRegistry,
        PluginRegistryContext,
    )

    installed = PluginRegistry.from_runtime_tools(
        [{"tool_name": "cli_plugin_login", "plugin_id": "hermes"}],
        context=PluginRegistryContext(
            workspace_trusted=True,
            cli_plugin_status={
                "hermes": {
                    "installed": True,
                    "installed_version": "0.5.1",
                    "status": "installed",
                }
            },
        ),
    )
    missing = PluginRegistry.from_runtime_tools(
        [{"tool_name": "cli_plugin_login", "plugin_id": "missing"}],
        context=PluginRegistryContext(
            workspace_trusted=True,
            cli_plugin_status={
                "missing": {
                    "installed": False,
                    "status": "not_installed",
                }
            },
        ),
    )

    installed_tool = installed.summary()["registered_tools"][0]
    missing_tool = missing.summary()["registered_tools"][0]
    assert installed.names() == ["cli_plugin_login"]
    assert installed_tool["version"] == "0.5.1"
    assert installed_tool["installed"] is True
    assert installed_tool["load_status"] == "installed"
    assert missing.names() == []
    assert missing_tool["installed"] is False
    assert missing_tool["available"] is False
    assert missing_tool["load_status"] == "not_installed"


def test_default_plugin_registry_context_reads_cli_plugin_install_receipt(tmp_path, monkeypatch):
    from services.agent_runtime.shared import tool_registry as plugin_registry

    state_dir = tmp_path / ".ai-employee" / "cli-plugin-market"
    state_dir.mkdir(parents=True)
    (state_dir / "install-state.json").write_text(
        (
            "{\n"
            "  \"installs\": {\n"
            "    \"hermes\": {\n"
            "      \"installed\": true,\n"
            "      \"installed_version\": \"0.5.1\",\n"
            "      \"latest_version\": \"0.5.2\",\n"
            "      \"detection_source\": \"receipt\"\n"
            "    }\n"
            "  }\n"
            "}\n"
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(plugin_registry, "get_project_root", lambda: tmp_path)

    context = plugin_registry.default_plugin_registry_context()

    assert context.cli_plugin_status["hermes"]["installed"] is True
    assert context.cli_plugin_status["hermes"]["installed_version"] == "0.5.1"
    assert context.cli_plugin_status["hermes"]["latest_version"] == "0.5.2"
    assert context.cli_plugin_status["hermes"]["status"] == "installed"


@pytest.mark.asyncio
async def test_event_stream_builds_agent_runtime_event_payload():
    from services.agent_runtime.core.event_log import RuntimeEvent
    from services.agent_runtime.v2.event_stream import EventStream

    published = []

    async def _publish(payload):
        published.append(payload)

    stream = EventStream(
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
        publisher=_publish,
    )
    event = RuntimeEvent.create(
        run_id="run-1",
        event_type="llm_step_completed",
        payload={"step_index": 1},
    )

    payload = await stream.publish(event)

    assert payload["type"] == "agent_runtime_event"
    assert payload["event_type"] == "llm_step_completed"
    assert payload["event"]["type"] == "llm_step_completed"
    assert payload["event"]["session_id"] == "chat-1"
    assert published == [payload]



@pytest.mark.asyncio
async def test_llm_step_consumes_provider_stream_adapter(monkeypatch):
    from services.agent_runtime.shared.provider_events import (
        ProviderStreamAdapter,
        ProviderStreamEvent,
        ProviderStreamEventType,
    )
    from services.agent_runtime.v2.llm_step import LLMStep

    normalized_chunks = []

    def _normalize_chunk(self, chunk):
        normalized_chunks.append(
            {
                "provider_id": self.provider_id,
                "model_name": self.model_name,
                "chunk": dict(chunk),
            }
        )
        return [
            ProviderStreamEvent(
                event_type=ProviderStreamEventType.CONTENT_DELTA,
                provider_id=self.provider_id,
                model_name=self.model_name,
                text=f"normalized:{chunk.get('content')}",
                raw=dict(chunk),
            )
        ]

    monkeypatch.setattr(ProviderStreamAdapter, "normalize_chunk", _normalize_chunk)

    class _FakeLLM:
        async def chat_completion_stream(self, **kwargs):
            yield {"content": "raw"}

    result = await LLMStep(_FakeLLM()).run(
        provider_id="provider-1",
        model_name="model-1",
        messages=[{"role": "user", "content": "hi"}],
    )

    assert result.content == "normalized:raw"
    assert result.provider_id == "provider-1"
    assert result.model_name == "model-1"
    assert normalized_chunks == [
        {
            "provider_id": "provider-1",
            "model_name": "model-1",
            "chunk": {"content": "raw"},
        }
    ]


def test_provider_stream_adapter_normalizes_content_tool_usage_and_error_events():
    from services.agent_runtime.shared.provider_events import (
        ProviderStreamAdapter,
        ProviderStreamEvent,
        ProviderStreamEventType,
    )

    adapter = ProviderStreamAdapter(provider_id="provider-1", model_name="model-1")
    events = adapter.normalize_chunks(
        [
            {"content": "你好"},
            {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "call-1",
                        "function": {
                            "name": "project_host_run_command",
                            "arguments": "{\"command\":\"pwd\"}",
                        },
                    }
                ]
            },
            {
                "usage": {"prompt_tokens": 3, "completion_tokens": 5},
                "provider_id": "provider-override",
                "model_name": "model-override",
            },
            {"type": "error", "message": "rate limit", "retryable": True},
        ]
    )

    assert [event.event_type for event in events] == [
        ProviderStreamEventType.CONTENT_DELTA,
        ProviderStreamEventType.TOOL_CALL_DELTA,
        ProviderStreamEventType.USAGE,
        ProviderStreamEventType.ERROR,
    ]
    assert isinstance(events[0], ProviderStreamEvent)
    assert events[0].text == "你好"
    assert events[1].tool_calls[0]["function"]["name"] == "project_host_run_command"
    assert events[2].usage == {"prompt_tokens": 3, "completion_tokens": 5}
    assert events[2].provider_id == "provider-override"
    assert events[2].model_name == "model-override"
    assert events[3].error["message"] == "rate limit"
    assert events[3].retryable is True


def test_provider_stream_adapter_normalizes_openai_choice_delta_chunks():
    from services.agent_runtime.shared.provider_events import (
        ProviderStreamAdapter,
        ProviderStreamEventType,
    )

    adapter = ProviderStreamAdapter(provider_id="openai", model_name="gpt-test")
    result = adapter.build_step_result(
        adapter.normalize_chunks(
            [
                {
                    "choices": [
                        {
                            "delta": {
                                "content": "查",
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "call-1",
                                        "function": {
                                            "name": "project_host_run_command",
                                            "arguments": "{\"command\":",
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                },
                {
                    "choices": [
                        {
                            "delta": {
                                "content": "询",
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "function": {
                                            "arguments": "\"pwd\"}",
                                        },
                                    }
                                ],
                            }
                        }
                    ],
                    "usage": {"total_tokens": 9},
                },
            ]
        )
    )
    events = adapter.normalize_chunk(
        {"choices": [{"delta": {"content": "x"}}]}
    )

    assert events[0].event_type == ProviderStreamEventType.CONTENT_DELTA
    assert result.content == "查询"
    assert result.usage == {"total_tokens": 9}
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool_name == "project_host_run_command"
    assert result.tool_calls[0].arguments == "{\"command\":\"pwd\"}"


def test_provider_stream_adapter_normalizes_responses_output_item_chunks():
    from services.agent_runtime.shared.provider_events import ProviderStreamAdapter

    adapter = ProviderStreamAdapter(provider_id="responses", model_name="gpt-responses")
    events = adapter.normalize_chunks(
        [
            {
                "type": "response.output_text.delta",
                "delta": "授权",
            },
            {
                "type": "response.function_call_arguments.delta",
                "item_id": "call-1",
                "name": "project_host_run_command",
                "delta": "{\"command\":",
            },
            {
                "type": "response.function_call_arguments.delta",
                "item_id": "call-1",
                "delta": "\"lark-cli auth status\"}",
            },
            {
                "type": "response.completed",
                "response": {
                    "usage": {"input_tokens": 4, "output_tokens": 7},
                },
            },
        ]
    )
    result = adapter.build_step_result(events)

    assert result.content == "授权"
    assert result.usage == {"input_tokens": 4, "output_tokens": 7}
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].call_id == "call-1"
    assert result.tool_calls[0].tool_name == "project_host_run_command"
    assert result.tool_calls[0].arguments == "{\"command\":\"lark-cli auth status\"}"


def test_provider_stream_adapter_exposes_capability_metadata():
    from services.agent_runtime.shared.provider_events import (
        ProviderCapabilityMetadata,
        ProviderStreamAdapter,
    )

    openai_adapter = ProviderStreamAdapter(provider_id="openai", model_name="gpt-4o")
    explicit_adapter = ProviderStreamAdapter(
        provider_id="custom",
        model_name="local-vision-json",
        capabilities={
            "native_tool_calls": True,
            "vision": True,
            "json_mode": True,
            "stream_usage": False,
        },
    )
    metadata = ProviderCapabilityMetadata(
        provider_id="responses",
        model_name="gpt-responses",
        native_tool_calls=True,
        reasoning=True,
        json_mode=True,
        stream_usage=True,
    )
    metadata_adapter = ProviderStreamAdapter(capabilities=metadata)

    assert openai_adapter.capabilities.to_dict() == {
        "provider_id": "openai",
        "model_name": "gpt-4o",
        "native_tool_calls": True,
        "vision": True,
        "reasoning": False,
        "json_mode": True,
        "stream_usage": True,
    }
    assert explicit_adapter.capabilities.provider_id == "custom"
    assert explicit_adapter.capabilities.model_name == "local-vision-json"
    assert explicit_adapter.capabilities.native_tool_calls is True
    assert explicit_adapter.capabilities.vision is True
    assert explicit_adapter.capabilities.json_mode is True
    assert explicit_adapter.capabilities.stream_usage is False
    assert metadata_adapter.capabilities is metadata



def test_provider_stream_adapter_builds_llm_step_result_contract():
    from services.agent_runtime.shared.provider_events import ProviderStreamAdapter

    adapter = ProviderStreamAdapter(provider_id="provider-1", model_name="model-1")
    result = adapter.build_step_result(
        adapter.normalize_chunks(
            [
                {"content": "执行"},
                {"content": "完成"},
                {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call-1",
                            "function": {
                                "name": "project_host_run_command",
                                "arguments": "{\"command\":\"pwd\"}",
                            },
                        }
                    ]
                },
                {"usage": {"total_tokens": 12}},
            ]
        ),
        max_tool_calls=3,
    )

    assert result.content == "执行完成"
    assert result.provider_id == "provider-1"
    assert result.model_name == "model-1"
    assert result.usage == {"total_tokens": 12}
    assert result.error is None
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool_name == "project_host_run_command"
    assert result.tool_calls[0].arguments == "{\"command\":\"pwd\"}"



def test_provider_stream_adapter_is_exported_from_shared_and_v2():
    from services.agent_runtime.shared import (
        ProviderCapabilityMetadata,
        ProviderStreamAdapter,
        ProviderStreamEvent,
        ProviderStreamEventType,
    )
    from services.agent_runtime import v2

    assert v2.ProviderCapabilityMetadata is ProviderCapabilityMetadata
    assert v2.ProviderStreamAdapter is ProviderStreamAdapter
    assert v2.ProviderStreamEvent is ProviderStreamEvent
    assert v2.ProviderStreamEventType is ProviderStreamEventType


def test_hermes_runtime_capability_catalog_covers_platform_features():
    from services.agent_runtime.shared.runtime_capabilities import (
        default_hermes_runtime_capability_catalog,
    )

    catalog = default_hermes_runtime_capability_catalog()
    expected_ids = {
        "agent_loop",
        "provider_adapter",
        "tool_registry",
        "tool_permission_approval",
        "builtin_tools",
        "skills",
        "memory",
        "session_management",
        "context_compression",
        "mcp",
        "gateway",
        "cron",
        "background_process",
        "multi_platform_messages",
        "configuration_system",
        "error_recovery_state_machine",
    }

    assert set(catalog.ids()) == expected_ids
    assert len(catalog.ids()) == len(set(catalog.ids()))
    assert catalog.get("agent_loop").status == "partial"
    assert catalog.get("context_compression").status == "planned"
    assert catalog.summary()["capability_total"] == len(expected_ids)
    assert catalog.by_phase()[1][0]["capability_id"] == "agent_loop"
    assert "tools" in catalog.by_category()


def test_hermes_runtime_capability_catalog_is_exported_from_shared_and_v2():
    from services.agent_runtime.shared import (
        RuntimeCapability,
        RuntimeCapabilityCatalog,
        default_hermes_runtime_capability_catalog,
    )
    from services.agent_runtime import v2

    shared_catalog = default_hermes_runtime_capability_catalog()
    v2_catalog = v2.default_hermes_runtime_capability_catalog()

    assert isinstance(shared_catalog, RuntimeCapabilityCatalog)
    assert isinstance(shared_catalog.get("agent_loop"), RuntimeCapability)
    assert v2.RuntimeCapability is RuntimeCapability
    assert v2.RuntimeCapabilityCatalog is RuntimeCapabilityCatalog
    assert v2_catalog.ids() == shared_catalog.ids()
