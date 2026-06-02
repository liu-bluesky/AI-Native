import asyncio

import pytest


@pytest.mark.asyncio
async def test_agent_runtime_v2_can_delegate_to_legacy_when_requested(tmp_path):
    from services.agent_runtime_v2.runtime import AgentTaskRuntime
    from services.agent_runtime_v2.event_log import RuntimeEventLog
    from services.agent_runtime_v2.state_store import TaskRunStore
    from services.agent_runtime_v2.transcript_store import TranscriptStore

    class _LegacyOrchestrator:
        async def run(self, **kwargs):
            yield {"type": "delta", "content": "ok"}
            yield {"type": "done", "content": "ok"}

    runtime = AgentTaskRuntime(
        _LegacyOrchestrator(),
        state_store=TaskRunStore(tmp_path / "runs"),
        transcript_store=TranscriptStore(tmp_path / "transcripts"),
        event_log=RuntimeEventLog(tmp_path / "events"),
    )
    chunks = []
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

    assert chunks[0]["type"] == "runtime_status"
    assert chunks[0]["runtime"] == "agent_runtime_v2"
    assert chunks[1:] == [
        {"type": "delta", "content": "ok"},
        {"type": "done", "content": "ok"},
    ]
    files = list((tmp_path / "runs").glob("run_*.json"))
    assert len(files) == 1
    payload = files[0].read_text(encoding="utf-8")
    assert '"status": "completed"' in payload
    assert '"type": "run_created"' in payload
    assert '"type": "legacy_orchestrator_finished"' in payload
    transcript_files = list((tmp_path / "transcripts").glob("run_*.jsonl"))
    assert len(transcript_files) == 1
    transcript_payload = transcript_files[0].read_text(encoding="utf-8")
    assert '"type": "user_message"' in transcript_payload
    assert '"type": "legacy_done"' in transcript_payload
    event_files = list((tmp_path / "events").glob("run_*.jsonl"))
    assert len(event_files) == 1
    event_payload = event_files[0].read_text(encoding="utf-8")
    assert '"event_type": "run_started"' in event_payload
    assert '"event_type": "run_finished"' in event_payload


@pytest.mark.asyncio
async def test_agent_runtime_v2_persists_resume_context(tmp_path):
    from services.agent_runtime_v2.runtime import AgentTaskRuntime
    from services.agent_runtime_v2.event_log import RuntimeEventLog
    from services.agent_runtime_v2.state_store import TaskRunStore
    from services.agent_runtime_v2.transcript_store import TranscriptStore

    class _LegacyOrchestrator:
        async def run(self, **kwargs):
            yield {"type": "done", "content": "ok"}

    class _LocalConnector:
        id = "connector-1"

    runtime = AgentTaskRuntime(
        _LegacyOrchestrator(),
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
    from services.agent_runtime_v2.event_log import RuntimeEventLog
    from services.agent_runtime_v2.run_inspector import AgentRuntimeInspector
    from services.agent_runtime_v2.state_store import TaskRunStore
    from services.agent_runtime_v2.transcript_store import TranscriptStore

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
    from services.agent_runtime_v2.tool_result_normalizer import ToolResultNormalizer

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
    from services.agent_runtime_v2.tool_call_collector import ToolCallCollector

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
async def test_query_engine_creates_observation_and_continues_after_tool(tmp_path):
    from services.agent_runtime_v2.event_log import RuntimeEventLog
    from services.agent_runtime_v2.llm_step import LLMStep
    from services.agent_runtime_v2.query_engine import QueryEngine
    from services.agent_runtime_v2.state_store import TaskRunStore
    from services.agent_runtime_v2.tool_execution_runner import ToolExecutionRunner
    from services.agent_runtime_v2.transcript_store import TranscriptStore

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
async def test_query_engine_fails_when_tool_succeeds_but_model_never_answers(tmp_path):
    from services.agent_runtime_v2.event_log import RuntimeEventLog
    from services.agent_runtime_v2.llm_step import LLMStep
    from services.agent_runtime_v2.query_engine import QueryEngine
    from services.agent_runtime_v2.state_store import TaskRunStore
    from services.agent_runtime_v2.tool_execution_runner import ToolExecutionRunner
    from services.agent_runtime_v2.transcript_store import TranscriptStore

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
    from services.agent_runtime_v2.event_log import RuntimeEventLog
    from services.agent_runtime_v2.llm_step import LLMStep
    from services.agent_runtime_v2.permission_policy import PermissionPolicy
    from services.agent_runtime_v2.permission_store import PermissionStore
    from services.agent_runtime_v2.query_engine import QueryEngine
    from services.agent_runtime_v2.state_store import TaskRunStore
    from services.agent_runtime_v2.tool_execution_runner import ToolExecutionRunner
    from services.agent_runtime_v2.transcript_store import TranscriptStore

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
async def test_query_engine_waits_when_background_operation_pending(tmp_path):
    from services.agent_runtime_v2.event_log import RuntimeEventLog
    from services.agent_runtime_v2.llm_step import LLMStep
    from services.agent_runtime_v2.query_engine import QueryEngine
    from services.agent_runtime_v2.state_store import TaskRunStore
    from services.agent_runtime_v2.tool_execution_runner import ToolExecutionRunner
    from services.agent_runtime_v2.transcript_store import TranscriptStore

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

    events = [item.event_type for item in event_log.list_events(task_run.run_id)]
    assert result.task_run.status == "waiting_user"
    assert result.completion_decision is not None
    assert result.completion_decision.action == "request_user"
    assert "background_operation_pending" in result.completion_decision.reasons
    assert "query_engine_waiting_operation" in [event["type"] for event in result.task_run.events]
    assert "tool_observation_created" in events


@pytest.mark.asyncio
async def test_llm_step_returns_structured_error_when_stream_raises_dns_error():
    from services.agent_runtime_v2.llm_step import LLMStep

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
    from services.agent_runtime_v2.event_log import RuntimeEventLog
    from services.agent_runtime_v2.llm_step import LLMStep
    from services.agent_runtime_v2.query_engine import QueryEngine
    from services.agent_runtime_v2.state_store import TaskRunStore
    from services.agent_runtime_v2.transcript_store import TranscriptStore

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
        from services.agent_runtime_v2.event_log import RuntimeEventLog
        from services.agent_runtime_v2.llm_step import LLMStep
        from services.agent_runtime_v2.permission_policy import PermissionPolicy
        from services.agent_runtime_v2.permission_store import (
            PermissionRule,
            PermissionStore,
        )
        from services.agent_runtime_v2.query_engine import QueryEngine
        from services.agent_runtime_v2.state_store import TaskRunStore
        from services.agent_runtime_v2.tool_execution_runner import ToolExecutionRunner
        from services.agent_runtime_v2.transcript_store import TranscriptStore

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
    from services.agent_runtime_v2.event_log import RuntimeEventLog
    from services.agent_runtime_v2.llm_step import LLMStep
    from services.agent_runtime_v2.query_engine import QueryEngine
    from services.agent_runtime_v2.state_store import TaskRunStore
    from services.agent_runtime_v2.transcript_store import TranscriptStore

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
    from services.agent_runtime_v2.completion_policy import CompletionDecision
    from services.agent_runtime_v2.event_log import RuntimeEventLog
    from services.agent_runtime_v2.llm_step import LLMStep
    from services.agent_runtime_v2.query_engine import QueryEngine
    from services.agent_runtime_v2.state_store import TaskRunStore
    from services.agent_runtime_v2.transcript_store import TranscriptStore

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
    from services.agent_runtime_v2.event_log import RuntimeEventLog
    from services.agent_runtime_v2.llm_step import LLMStep
    from services.agent_runtime_v2.query_engine import QueryEngine
    from services.agent_runtime_v2.state_store import TaskRunStore
    from services.agent_runtime_v2.transcript_store import TranscriptStore

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
async def test_agent_runtime_v2_query_engine_mode_is_default(tmp_path):
    from services.agent_runtime_v2.event_log import RuntimeEventLog
    from services.agent_runtime_v2.runtime import AgentTaskRuntime
    from services.agent_runtime_v2.state_store import TaskRunStore
    from services.agent_runtime_v2.transcript_store import TranscriptStore

    class _FakeLLM:
        async def chat_completion_stream(self, **kwargs):
            yield {"content": "可以继续。"}

    class _LegacyOrchestrator:
        def __init__(self):
            self._llm = _FakeLLM()

        async def run(self, **kwargs):
            yield {"type": "done", "content": "legacy"}

    runtime = AgentTaskRuntime(
        _LegacyOrchestrator(),
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


@pytest.mark.asyncio
async def test_agent_runtime_v2_done_marks_permission_waiting_user(tmp_path):
    from services.agent_runtime_v2.event_log import RuntimeEventLog
    from services.agent_runtime_v2.runtime import AgentTaskRuntime
    from services.agent_runtime_v2.state_store import TaskRunStore
    from services.agent_runtime_v2.transcript_store import TranscriptStore

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

    class _LegacyOrchestrator:
        def __init__(self):
            self._llm = _FakeLLM()

        async def run(self, **kwargs):
            yield {"type": "done", "content": "legacy"}

    runtime = AgentTaskRuntime(
        _LegacyOrchestrator(),
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


def test_completion_policy_requires_verification_for_dev_task():
    from services.agent_runtime_v2.completion_policy import CompletionPolicy
    from services.agent_runtime_v2.verification_policy import VerificationPolicy

    verification = VerificationPolicy().build_state(user_goal="修复接口并跑测试")
    decision = CompletionPolicy().evaluate(
        response_content="已修改完成",
        verification=verification,
        task_tree_verified=True,
        goal_covered=True,
    )

    assert decision.action == "verify"
    assert "verification_required" in decision.reasons


def test_permission_policy_asks_when_workspace_untrusted(tmp_path):
    from services.agent_runtime_v2.permission_policy import PermissionPolicy
    from services.agent_runtime_v2.permission_store import PermissionStore

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


def test_permission_action_allow_always_reuses_lark_auth_status_signature(tmp_path):
    from services.agent_runtime_v2.event_log import RuntimeEventLog
    from services.agent_runtime_v2.permission_actions import PermissionActionService
    from services.agent_runtime_v2.permission_policy import PermissionPolicy
    from services.agent_runtime_v2.permission_store import PermissionStore
    from services.agent_runtime_v2.trust_policy import TrustPolicy

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
    from services.agent_runtime_v2.event_log import RuntimeEventLog
    from services.agent_runtime_v2.permission_policy import PermissionPolicy
    from services.agent_runtime_v2.permission_store import PermissionStore
    from services.agent_runtime_v2.tool_call_collector import CollectedToolCall
    from services.agent_runtime_v2.tool_execution_runner import ToolExecutionRunner

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
    assert executor.calls == 0
    assert len(records) == 1
    assert records[0].observation.status == "blocked"
    assert records[0].permission_decision is not None
    assert records[0].permission_decision.behavior == "ask"
    assert records[0].raw_result["permission_decision"]["behavior"] == "ask"
    assert "permission_decision" in events
    assert "tool_observation_created" in events


@pytest.mark.asyncio
async def test_tool_runner_executes_when_permission_rule_allows(tmp_path):
    from services.agent_runtime_v2.event_log import RuntimeEventLog
    from services.agent_runtime_v2.permission_policy import PermissionPolicy
    from services.agent_runtime_v2.permission_store import (
        PermissionRule,
        PermissionStore,
    )
    from services.agent_runtime_v2.tool_call_collector import CollectedToolCall
    from services.agent_runtime_v2.tool_execution_runner import ToolExecutionRunner

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
            behavior="allow_session",
            tool_name="project_host_run_command",
            project_id="proj-1",
            username="tester",
            chat_session_id="chat-1",
            matcher={"command_prefix": "sudo echo"},
        )
    )
    executor = _FakeToolExecutor()
    runner = ToolExecutionRunner(
        executor,
        event_log=RuntimeEventLog(tmp_path / "events"),
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

    assert executor.calls == 1
    assert executor.tool_calls[0]["function"]["arguments"] == "{\"command\": \"sudo echo ok\"}"
    assert records[0].observation.status == "succeeded"
    assert records[0].raw_result["stdout"] == "allowed"


def test_trust_policy_marks_workspace_trusted(tmp_path):
    from services.agent_runtime_v2.trust_policy import TrustPolicy

    policy = TrustPolicy(tmp_path)
    trust = policy.mark_trusted(
        workspace_path="/tmp/workspace",
        username="tester",
    )

    assert trust.trusted is True
    assert trust.trusted_by == "tester"
    assert policy.ensure_workspace_trusted("/tmp/workspace").trusted is True


def test_permission_action_service_saves_allow_once_rule(tmp_path):
    from services.agent_runtime_v2.event_log import RuntimeEventLog
    from services.agent_runtime_v2.permission_actions import PermissionActionService
    from services.agent_runtime_v2.permission_policy import PermissionPolicy
    from services.agent_runtime_v2.permission_store import PermissionStore
    from services.agent_runtime_v2.trust_policy import TrustPolicy

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
    from services.agent_runtime_v2.event_log import RuntimeEventLog
    from services.agent_runtime_v2.operation_resume import OperationResumeCoordinator
    from services.agent_runtime_v2.permission_actions import PermissionActionService
    from services.agent_runtime_v2.permission_policy import PermissionPolicy
    from services.agent_runtime_v2.permission_store import PermissionStore
    from services.agent_runtime_v2.state_store import TaskRunStore
    from services.agent_runtime_v2.transcript_store import TranscriptStore
    from services.agent_runtime_v2.trust_policy import TrustPolicy

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
    assert executor.calls[0]["function"]["arguments"] == "{\"command\": \"npm test\"}"
    assert reloaded is not None
    assert reloaded.status == "running"
    assert "operation_resume_started" in events
    assert "operation_resume_completed" in events


@pytest.mark.asyncio
async def test_operation_resume_can_continue_query_engine_after_allow_once(tmp_path):
    from services.agent_runtime_v2.event_log import RuntimeEventLog
    from services.agent_runtime_v2.operation_resume import OperationResumeCoordinator
    from services.agent_runtime_v2.permission_actions import PermissionActionService
    from services.agent_runtime_v2.permission_policy import PermissionPolicy
    from services.agent_runtime_v2.permission_store import PermissionStore
    from services.agent_runtime_v2.state_store import TaskRunStore
    from services.agent_runtime_v2.transcript_store import TranscriptStore
    from services.agent_runtime_v2.trust_policy import TrustPolicy

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
    from services.agent_runtime_v2.event_log import RuntimeEventLog
    from services.agent_runtime_v2.operation_resume import OperationResumeCoordinator
    from services.agent_runtime_v2.permission_policy import PermissionPolicy
    from services.agent_runtime_v2.permission_store import PermissionStore
    from services.agent_runtime_v2.state_store import TaskRunStore
    from services.agent_runtime_v2.transcript_store import TranscriptStore
    from services.agent_runtime_v2.trust_policy import TrustPolicy

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


def test_permission_action_service_saves_deny_rule(tmp_path):
    from services.agent_runtime_v2.event_log import RuntimeEventLog
    from services.agent_runtime_v2.permission_actions import PermissionActionService
    from services.agent_runtime_v2.permission_policy import PermissionPolicy
    from services.agent_runtime_v2.permission_store import PermissionStore
    from services.agent_runtime_v2.trust_policy import TrustPolicy

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
    from services.agent_runtime_v2.event_log import RuntimeEventLog
    from services.agent_runtime_v2.permission_actions import PermissionActionService
    from services.agent_runtime_v2.permission_store import PermissionStore
    from services.agent_runtime_v2.trust_policy import TrustPolicy

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
    from services.agent_runtime_v2.dynamic_tool_pool import DynamicToolPool

    pool = DynamicToolPool.from_runtime_tools(
        [
            {"tool_name": "b_tool", "description": "B"},
            {"tool_name": "a_tool", "description": "A", "builtin": True},
            {"tool_name": "a_tool", "description": "duplicate"},
        ],
        tool_priority=["a_tool"],
    )

    assert pool.names() == ["a_tool", "b_tool"]
    summary = pool.summary()
    assert summary["effective_tool_total"] == 2
    assert summary["effective_tools"][0]["tool_name"] == "a_tool"
    assert summary["plugin_registry"]["registered_tool_total"] == 2


def test_plugin_registry_classifies_runtime_tool_sources():
    from services.agent_runtime_v2.plugin_registry import PluginRegistry

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
    from services.agent_runtime_v2.plugin_registry import (
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
    from services.agent_runtime_v2.dynamic_tool_pool import DynamicToolPool
    from services.agent_runtime_v2.plugin_registry import PluginRegistryContext

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

    assert untrusted_pool.names() == []
    assert trusted_pool.names() == [
        "global_assistant_browser_actions",
        "global_assistant_browser_requests",
    ]
    browser_summary = trusted_pool.summary()["effective_tools"][0]
    assert browser_summary["source"] == "browser"
    assert browser_summary["plugin_id"] == "browser-tools"
    assert browser_summary["version"] == "builtin"


def test_plugin_registry_uses_cli_plugin_status_for_availability():
    from services.agent_runtime_v2.plugin_registry import (
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
    from services.agent_runtime_v2 import plugin_registry

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
    from services.agent_runtime_v2.event_log import RuntimeEvent
    from services.agent_runtime_v2.event_stream import EventStream

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
    assert published == [payload]
