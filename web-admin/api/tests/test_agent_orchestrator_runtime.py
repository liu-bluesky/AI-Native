import pytest


@pytest.mark.asyncio
async def test_agent_orchestrator_run_passes_global_assistant_tool_context(monkeypatch):
    from services.agent_orchestrator import AgentOrchestrator

    captured: dict[str, object] = {}

    class _FakeToolExecutor:
        def __init__(self, *args, **kwargs):
            captured.update(kwargs)

        async def execute_parallel(self, tool_calls, timeout=None):
            return []

    class _FakeConversationManager:
        async def get_context(self, session_id, max_tokens):
            return []

    orchestrator = AgentOrchestrator(object(), _FakeConversationManager())
    cancel_event = __import__("asyncio").Event()
    cancel_event.set()
    bridge_handler = object()

    monkeypatch.setattr("services.agent_orchestrator.ToolExecutor", _FakeToolExecutor)

    results = []
    async for item in orchestrator.run(
        session_id="session-1",
        user_message="你好",
        tools=[],
        provider_id="provider-1",
        model_name="glm-test",
        temperature=0.1,
        max_tokens=256,
        project_id="proj-1",
        employee_id="",
        cancel_event=cancel_event,
        username="tester",
        chat_session_id="chat-1",
        role_ids=["admin"],
        global_assistant_bridge_handler=bridge_handler,
    ):
        results.append(item)

    assert captured["role_ids"] == ["admin"]
    assert captured["global_assistant_bridge_handler"] is bridge_handler
    assert results[-1]["type"] == "done"


@pytest.mark.asyncio
async def test_agent_orchestrator_emits_tool_details_and_guard_payload(monkeypatch):
    import asyncio
    import json

    from services.agent_orchestrator import AgentOrchestrator

    captured_finalize_messages: list[dict[str, object]] = []

    class _FakeLLM:
        def __init__(self):
            self._stream_calls = 0

        async def chat_completion_stream(self, **kwargs):
            self._stream_calls += 1
            yield {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": f"call-{self._stream_calls}",
                        "function": {
                            "name": "project_host_run_command",
                            "arguments": json.dumps(
                                {
                                    "command": "npm install -g @larksuite/cli",
                                    "cwd": "web-admin",
                                },
                                ensure_ascii=False,
                            ),
                        },
                    }
                ]
            }

        async def chat_completion(self, **kwargs):
            captured_finalize_messages[:] = list(kwargs.get("messages") or [])
            return {"content": "基于现有结果已给出结论。"}

    class _FakeToolExecutor:
        def __init__(self, *args, **kwargs):
            pass

        async def execute_parallel(self, tool_calls, timeout=None):
            return [
                {
                    "ok": True,
                    "command": "npm install -g @larksuite/cli",
                    "cwd": "/tmp/project/web-admin",
                    "workspace_path": "/tmp/project",
                    "exit_code": 0,
                    "stdout": "installed successfully",
                    "stderr": "",
                    "environment_summary": "命令在项目工作区执行：/tmp/project",
                }
            ]

    class _FakeConversationManager:
        def __init__(self):
            self.messages: list[dict[str, object]] = []

        async def get_context(self, session_id, max_tokens):
            return []

        async def append_message(self, session_id, message):
            self.messages.append(message)

    monkeypatch.setattr("services.agent_orchestrator.ToolExecutor", _FakeToolExecutor)

    orchestrator = AgentOrchestrator(
        _FakeLLM(),
        _FakeConversationManager(),
        repeated_tool_call_threshold=1,
    )
    cancel_event = asyncio.Event()

    events = []
    async for item in orchestrator.run(
        session_id="session-guard",
        user_message="帮我安装飞书 CLI",
        tools=[{"tool_name": "project_host_run_command"}],
        provider_id="provider-1",
        model_name="glm-test",
        temperature=0.1,
        max_tokens=256,
        project_id="proj-1",
        employee_id="",
        cancel_event=cancel_event,
        username="tester",
        chat_session_id="chat-guard",
    ):
        events.append(item)

    tool_start = next(item for item in events if item["type"] == "tool_start")
    tool_result = next(item for item in events if item["type"] == "tool_result")
    done_event = events[-1]

    assert tool_start["tool_name"] == "project_host_run_command"
    assert tool_start["command"] == "npm install -g @larksuite/cli"
    assert tool_start["cwd"] == "web-admin"
    assert tool_start["tool_index"] == 1
    assert tool_start["tool_count"] == 1

    assert tool_result["status"] == "success"
    assert tool_result["command"] == "npm install -g @larksuite/cli"
    assert tool_result["cwd"] == "/tmp/project/web-admin"
    assert tool_result["stdout_preview"] == "installed successfully"
    assert tool_result["environment_summary"] == "命令在项目工作区执行：/tmp/project"

    assert done_event["type"] == "done"
    assert done_event["completed_reason"] == "repeated_tool_signature"
    assert done_event["guard_reason"] == "repeated_tool_signature"
    assert "重复工具调用" in done_event["guard_message"]
    assert "不要写“我不能再发起工具调用”" in str(
        captured_finalize_messages[-1]["content"]
    )


@pytest.mark.asyncio
async def test_agent_orchestrator_keeps_running_after_successful_tool_only_rounds(monkeypatch):
    import asyncio
    import json

    from services.agent_orchestrator import AgentOrchestrator

    class _FakeLLM:
        def __init__(self):
            self._stream_calls = 0

        async def chat_completion_stream(self, **kwargs):
            self._stream_calls += 1
            if self._stream_calls <= 3:
                yield {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": f"call-{self._stream_calls}",
                            "function": {
                                "name": "project_host_run_command",
                                "arguments": json.dumps(
                                    {"command": f"echo step-{self._stream_calls}"},
                                    ensure_ascii=False,
                                ),
                            },
                        }
                    ]
                }
                return
            yield {"content": "已完成全部工具步骤。"}

        async def chat_completion(self, **kwargs):
            return {"content": "fallback"}

    class _FakeToolExecutor:
        def __init__(self, *args, **kwargs):
            pass

        async def execute_parallel(self, tool_calls, timeout=None):
            command = json.loads(tool_calls[0]["function"]["arguments"])["command"]
            return [
                {
                    "ok": True,
                    "command": command,
                    "cwd": "/tmp/project",
                    "workspace_path": "/tmp/project",
                    "exit_code": 0,
                    "stdout": "done",
                    "stderr": "",
                }
            ]

    class _FakeConversationManager:
        async def get_context(self, session_id, max_tokens):
            return []

        async def append_message(self, session_id, message):
            return None

    monkeypatch.setattr("services.agent_orchestrator.ToolExecutor", _FakeToolExecutor)

    orchestrator = AgentOrchestrator(
        _FakeLLM(),
        _FakeConversationManager(),
        tool_only_threshold=3,
    )
    cancel_event = asyncio.Event()
    events = []
    async for item in orchestrator.run(
        session_id="session-tool-progress",
        user_message="请连续执行多个工具步骤后总结",
        tools=[{"tool_name": "project_host_run_command"}],
        provider_id="provider-1",
        model_name="glm-test",
        temperature=0.1,
        max_tokens=256,
        project_id="proj-1",
        employee_id="",
        cancel_event=cancel_event,
        username="tester",
        chat_session_id="chat-tool-progress",
    ):
        events.append(item)

    tool_results = [item for item in events if item["type"] == "tool_result"]
    assert len(tool_results) == 3
    assert events[-1]["type"] == "done"
    assert events[-1]["completed_reason"] == "completed"
    assert events[-1].get("guard_reason") != "tool_only_loops"
    assert "已完成全部工具步骤" in str(events[-1]["content"] or "")


@pytest.mark.asyncio
async def test_agent_orchestrator_auto_runs_lark_send_after_unique_contact_resolution(monkeypatch):
    import asyncio
    import json

    from services.agent_orchestrator import AgentOrchestrator

    class _FakeLLM:
        def __init__(self):
            self._stream_calls = 0
            self.messages_by_call = []

        async def chat_completion_stream(self, **kwargs):
            self._stream_calls += 1
            self.messages_by_call.append(list(kwargs.get("messages") or []))
            if self._stream_calls == 1:
                yield {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call-search",
                            "function": {
                                "name": "project_host_run_command",
                                "arguments": json.dumps(
                                    {
                                        "command": "lark-cli contact +search-user --query '屈行行'",
                                    },
                                    ensure_ascii=False,
                                ),
                            },
                        }
                    ]
                }
                return
            yield {"content": "已实际发送 test，message_id=om_123。"}

        async def chat_completion(self, **kwargs):
            return {"content": "fallback"}

    class _FakeToolExecutor:
        def __init__(self, *args, **kwargs):
            self.calls = 0

        async def execute_parallel(self, tool_calls, timeout=None):
            self.calls += 1
            command = json.loads(tool_calls[0]["function"]["arguments"])["command"]
            if self.calls == 1:
                return [
                    {
                        "ok": True,
                        "command": command,
                        "cwd": "/tmp/project",
                        "workspace_path": "/tmp/project",
                        "exit_code": 0,
                        "stdout": '{"name":"屈行行","open_id":"ou_aeda3de2ac3748fb634016a949ad6d04"}',
                        "stderr": "",
                    }
                ]
            return [
                {
                    "ok": True,
                    "command": command,
                    "cwd": "/tmp/project",
                    "workspace_path": "/tmp/project",
                    "exit_code": 0,
                    "stdout": '{"message_id":"om_123","code":0}',
                    "stderr": "",
                }
            ]

    class _FakeConversationManager:
        async def get_context(self, session_id, max_tokens):
            return []

        async def append_message(self, session_id, message):
            return None

    monkeypatch.setattr("services.agent_orchestrator.ToolExecutor", _FakeToolExecutor)

    orchestrator = AgentOrchestrator(_FakeLLM(), _FakeConversationManager())
    cancel_event = asyncio.Event()
    events = []
    async for item in orchestrator.run(
        session_id="session-lark-auto-send",
        user_message="帮我给屈行行发送 test",
        tools=[{"tool_name": "project_host_run_command"}],
        provider_id="provider-1",
        model_name="glm-test",
        temperature=0.1,
        max_tokens=256,
        project_id="proj-1",
        employee_id="",
        cancel_event=cancel_event,
        username="tester",
        chat_session_id="chat-lark-auto-send",
    ):
        events.append(item)

    auto_continue_event = next(
        item
        for item in events
        if item["type"] == "auto_continue"
        and item["reason"] == "lark_cli_send_message_workflow"
    )
    tool_results = [item for item in events if item["type"] == "tool_result"]
    assert "唯一 open_id" in str(auto_continue_event["message"] or "")
    assert len(tool_results) == 2
    assert "search-user" in str(tool_results[0].get("command") or "")
    assert "messages-send" in str(tool_results[1].get("command") or "")
    assert "ou_aeda3de2ac3748fb634016a949ad6d04" in str(
        tool_results[1].get("command") or ""
    )
    assert events[-1]["type"] == "done"
    assert "message_id=om_123" in str(events[-1]["content"] or "")


@pytest.mark.asyncio
async def test_agent_orchestrator_retries_when_model_prematurely_defers_execution(monkeypatch):
    import asyncio
    import json

    from services.agent_orchestrator import AgentOrchestrator

    class _FakeLLM:
        def __init__(self):
            self._stream_calls = 0
            self.messages_by_call = []

        async def chat_completion_stream(self, **kwargs):
            self._stream_calls += 1
            self.messages_by_call.append(list(kwargs.get("messages") or []))
            if self._stream_calls == 1:
                yield {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call-search",
                            "function": {
                                "name": "project_host_run_command",
                                "arguments": json.dumps(
                                    {
                                        "command": "lark-cli contact +search-user --query '屈行行'",
                                    },
                                    ensure_ascii=False,
                                ),
                            },
                        }
                    ]
                }
                return
            if self._stream_calls == 2:
                yield {
                    "content": (
                        "已找到联系人 open_id，你现在执行下面命令即可发送。"
                        "把输出发我，我继续帮你确认。"
                    )
                }
                return
            if self._stream_calls == 3:
                messages = kwargs.get("messages") or []
                assert any(
                    "不要再让用户自己执行命令" in str(item.get("content") or "")
                    for item in messages
                    if item.get("role") == "system"
                )
                yield {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call-run",
                            "function": {
                                "name": "project_host_run_command",
                                "arguments": json.dumps(
                                    {
                                        "command": "demo-cli deploy --target staging",
                                    },
                                    ensure_ascii=False,
                                ),
                            },
                        }
                    ]
                }
                return
            yield {"content": "已实际发送 test，message_id=om_123。"}

        async def chat_completion(self, **kwargs):
            return {"content": "fallback"}

    class _FakeToolExecutor:
        def __init__(self, *args, **kwargs):
            self.calls = 0

        async def execute_parallel(self, tool_calls, timeout=None):
            self.calls += 1
            if self.calls == 1:
                return [
                    {
                        "ok": True,
                        "command": "lark-cli contact +search-user --query '屈行行'",
                        "cwd": "/tmp/project",
                        "workspace_path": "/tmp/project",
                        "exit_code": 0,
                        "stdout": '{"name":"屈行行","open_id":"ou_aeda3de2ac3748fb634016a949ad6d04"}',
                        "stderr": "",
                    }
                ]
            return [
                {
                    "ok": True,
                    "command": (
                        "lark-cli im +messages-send --as user "
                        "--user-id ou_aeda3de2ac3748fb634016a949ad6d04 "
                        "--text 'test'"
                    ),
                    "cwd": "/tmp/project",
                    "workspace_path": "/tmp/project",
                    "exit_code": 0,
                    "stdout": '{"message_id":"om_123","code":0}',
                    "stderr": "",
                }
            ]

    class _FakeConversationManager:
        async def get_context(self, session_id, max_tokens):
            return []

        async def append_message(self, session_id, message):
            return None

    monkeypatch.setattr("services.agent_orchestrator.ToolExecutor", _FakeToolExecutor)

    orchestrator = AgentOrchestrator(_FakeLLM(), _FakeConversationManager())
    cancel_event = asyncio.Event()
    events = []
    async for item in orchestrator.run(
        session_id="session-send",
        user_message="帮我给屈行行发送 test",
        tools=[{"tool_name": "project_host_run_command"}],
        provider_id="provider-1",
        model_name="glm-test",
        temperature=0.1,
        max_tokens=256,
        project_id="proj-1",
        employee_id="",
        cancel_event=cancel_event,
        username="tester",
        chat_session_id="chat-send",
    ):
        events.append(item)

    auto_continue_reasons = [
        item["reason"]
        for item in events
        if item["type"] == "auto_continue"
    ]
    tool_results = [item for item in events if item["type"] == "tool_result"]
    assert "lark_cli_send_message_workflow" in auto_continue_reasons
    assert "premature_execution_deferral" in auto_continue_reasons
    assert len(tool_results) >= 2
    assert "search-user" in str(tool_results[0].get("command") or "")
    assert any("messages-send" in str(item.get("command") or "") for item in tool_results[1:])
    assert events[-1]["type"] == "done"
    assert "message_id=om_123" in str(events[-1]["content"] or "")


@pytest.mark.asyncio
async def test_agent_orchestrator_retries_next_minimum_step_deferral(monkeypatch):
    import asyncio
    import json

    from services.agent_orchestrator import AgentOrchestrator

    class _FakeLLM:
        def __init__(self):
            self._stream_calls = 0

        async def chat_completion_stream(self, **kwargs):
            self._stream_calls += 1
            if self._stream_calls == 1:
                yield {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call-create",
                            "function": {
                                "name": "project_host_run_command",
                                "arguments": json.dumps(
                                    {"command": "demo-cli create-record"},
                                    ensure_ascii=False,
                                ),
                            },
                        }
                    ]
                }
                return
            if self._stream_calls == 2:
                yield {
                    "content": (
                        "正文记录已创建，但附件还没有写入成功。\n"
                        "下一步最小操作：执行 `demo-cli upload-attachment --record rec_1`。"
                    )
                }
                return
            if self._stream_calls == 3:
                yield {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call-upload",
                            "function": {
                                "name": "project_host_run_command",
                                "arguments": json.dumps(
                                    {"command": "demo-cli upload-attachment --record rec_1"},
                                    ensure_ascii=False,
                                ),
                            },
                        }
                    ]
                }
                return
            yield {"content": "已创建记录并上传附件。"}

        async def chat_completion(self, **kwargs):
            return {"content": "fallback"}

    class _FakeToolExecutor:
        def __init__(self, *args, **kwargs):
            self.calls = 0

        async def execute_parallel(self, tool_calls, timeout=None):
            self.calls += 1
            command = json.loads(tool_calls[0]["function"]["arguments"])["command"]
            return [
                {
                    "ok": True,
                    "command": command,
                    "cwd": "/tmp/project",
                    "workspace_path": "/tmp/project",
                    "exit_code": 0,
                    "stdout": '{"ok":true}',
                    "stderr": "",
                }
            ]

    class _FakeConversationManager:
        async def get_context(self, session_id, max_tokens):
            return []

        async def append_message(self, session_id, message):
            return None

    monkeypatch.setattr("services.agent_orchestrator.ToolExecutor", _FakeToolExecutor)

    orchestrator = AgentOrchestrator(_FakeLLM(), _FakeConversationManager())
    cancel_event = asyncio.Event()
    events = []
    async for item in orchestrator.run(
        session_id="session-next-min-step",
        user_message="帮我继续创建记录并上传附件",
        tools=[{"tool_name": "project_host_run_command"}],
        provider_id="provider-1",
        model_name="glm-test",
        temperature=0.1,
        max_tokens=256,
        project_id="proj-1",
        employee_id="",
        cancel_event=cancel_event,
        username="tester",
        chat_session_id="chat-next-min-step",
    ):
        events.append(item)

    auto_continue_reasons = [
        item["reason"]
        for item in events
        if item["type"] == "auto_continue"
    ]
    tool_results = [item for item in events if item["type"] == "tool_result"]
    assert "premature_execution_deferral" in auto_continue_reasons
    assert len(tool_results) == 2
    assert "demo-cli create-record" in str(tool_results[0].get("command") or "")
    assert "demo-cli upload-attachment" in str(tool_results[1].get("command") or "")
    assert events[-1]["type"] == "done"


@pytest.mark.asyncio
async def test_agent_orchestrator_auto_runs_followup_command_from_tool_hint(monkeypatch):
    import asyncio
    import json

    from services.agent_orchestrator import AgentOrchestrator

    class _FakeLLM:
        def __init__(self):
            self._stream_calls = 0
            self.messages_by_call = []

        async def chat_completion_stream(self, **kwargs):
            self._stream_calls += 1
            self.messages_by_call.append(list(kwargs.get("messages") or []))
            if self._stream_calls == 1:
                yield {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call-run",
                            "function": {
                                "name": "project_host_run_command",
                                "arguments": json.dumps(
                                    {"command": "demo-cli deploy --target staging"},
                                    ensure_ascii=False,
                                ),
                            },
                        }
                    ]
                }
                return
            yield {"content": "已自动补跑后续命令，并继续完成任务。"}

        async def chat_completion(self, **kwargs):
            return {"content": "fallback"}

    class _FakeToolExecutor:
        def __init__(self, *args, **kwargs):
            self.calls = 0

        async def execute_parallel(self, tool_calls, timeout=None):
            self.calls += 1
            command = json.loads(tool_calls[0]["function"]["arguments"])["command"]
            if self.calls == 1:
                return [
                    {
                        "ok": True,
                        "command": command,
                        "cwd": "/tmp/project",
                        "workspace_path": "/tmp/project",
                        "exit_code": 0,
                        "stdout": json.dumps(
                            {
                                "ok": False,
                                "message": "next step required",
                                "hint": "run `demo-cli auth login --scope deploy` in the background",
                            },
                            ensure_ascii=False,
                        ),
                        "stderr": "",
                    }
                ]
            return [
                {
                    "ok": False,
                    "timed_out": True,
                    "command": command,
                    "cwd": "/tmp/project",
                    "workspace_path": "/tmp/project",
                    "exit_code": 124,
                    "stdout": "login started\nwaiting for completion...",
                    "stderr": "",
                }
            ]

    class _FakeConversationManager:
        async def get_context(self, session_id, max_tokens):
            return []

        async def append_message(self, session_id, message):
            return None

    monkeypatch.setattr("services.agent_orchestrator.ToolExecutor", _FakeToolExecutor)

    orchestrator = AgentOrchestrator(_FakeLLM(), _FakeConversationManager())
    cancel_event = asyncio.Event()
    events = []
    async for item in orchestrator.run(
        session_id="session-followup",
        user_message="帮我直接执行 demo-cli 部署",
        tools=[{"tool_name": "project_host_run_command"}],
        provider_id="provider-1",
        model_name="glm-test",
        temperature=0.1,
        max_tokens=256,
        project_id="proj-1",
        employee_id="",
        cancel_event=cancel_event,
        username="tester",
        chat_session_id="chat-followup",
    ):
        events.append(item)

    auto_continue_event = next(
        item
        for item in events
        if item["type"] == "auto_continue"
        and item["reason"] == "auto_followup_command"
    )
    tool_results = [item for item in events if item["type"] == "tool_result"]
    assert "系统已自动继续执行" in str(auto_continue_event["message"] or "")
    assert "demo-cli auth login --scope" in str(
        auto_continue_event["previous_response_preview"] or ""
    )
    assert len(tool_results) == 2
    assert "demo-cli deploy" in str(tool_results[0].get("command") or "")
    assert "demo-cli auth login --scope" in str(tool_results[1].get("command") or "")
    second_call_messages = orchestrator._llm.messages_by_call[1]
    auto_followup_tool_index = next(
        index
        for index, item in enumerate(second_call_messages)
        if item.get("role") == "tool"
        and item.get("tool_call_id") == "auto-followup-1"
    )
    assert second_call_messages[auto_followup_tool_index - 1]["role"] == "assistant"
    assert (
        second_call_messages[auto_followup_tool_index - 1]["tool_calls"][0]["id"]
        == "auto-followup-1"
    )
    assert events[-1]["type"] == "done"
    assert "继续完成任务" in str(events[-1]["content"] or "")


@pytest.mark.asyncio
async def test_agent_orchestrator_ignores_cross_binary_auto_followup_command(monkeypatch):
    import asyncio
    import json

    from services.agent_orchestrator import AgentOrchestrator

    class _FakeLLM:
        def __init__(self):
            self._stream_calls = 0

        async def chat_completion_stream(self, **kwargs):
            self._stream_calls += 1
            if self._stream_calls == 1:
                yield {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call-help",
                            "function": {
                                "name": "project_host_run_command",
                                "arguments": json.dumps(
                                    {"command": "demo-cli help"},
                                    ensure_ascii=False,
                                ),
                            },
                        }
                    ]
                }
                return
            yield {"content": "已查看帮助，没有执行不完整命令。"}

        async def chat_completion(self, **kwargs):
            return {"content": "fallback"}

    class _FakeToolExecutor:
        def __init__(self, *args, **kwargs):
            self.commands = []

        async def execute_parallel(self, tool_calls, timeout=None):
            command = json.loads(tool_calls[0]["function"]["arguments"])["command"]
            self.commands.append(command)
            return [
                {
                    "ok": True,
                    "command": command,
                    "cwd": "/tmp/project",
                    "workspace_path": "/tmp/project",
                    "exit_code": 0,
                    "stdout": "Use `other-cli auth login` to authenticate.",
                    "stderr": "",
                }
            ]

    class _FakeConversationManager:
        async def get_context(self, session_id, max_tokens):
            return []

        async def append_message(self, session_id, message):
            return None

    monkeypatch.setattr("services.agent_orchestrator.ToolExecutor", _FakeToolExecutor)

    orchestrator = AgentOrchestrator(_FakeLLM(), _FakeConversationManager())
    cancel_event = asyncio.Event()
    events = []
    async for item in orchestrator.run(
        session_id="session-incomplete-followup",
        user_message="查看 demo-cli 帮助",
        tools=[{"tool_name": "project_host_run_command"}],
        provider_id="provider-1",
        model_name="glm-test",
        temperature=0.1,
        max_tokens=256,
        project_id="proj-1",
        employee_id="",
        cancel_event=cancel_event,
        username="tester",
        chat_session_id="chat-incomplete-followup",
    ):
        events.append(item)

    assert not [item for item in events if item["type"] == "auto_continue"]
    tool_results = [item for item in events if item["type"] == "tool_result"]
    assert len(tool_results) == 1
    assert tool_results[0]["command"] == "demo-cli help"
    assert events[-1]["type"] == "done"
    assert "没有执行不完整命令" in str(events[-1]["content"] or "")


@pytest.mark.asyncio
async def test_agent_orchestrator_recovers_from_lark_auth_scope_validation_error(monkeypatch):
    import asyncio
    import json

    from services.agent_orchestrator import AgentOrchestrator

    class _FakeLLM:
        def __init__(self):
            self._stream_calls = 0

        async def chat_completion_stream(self, **kwargs):
            self._stream_calls += 1
            if self._stream_calls == 1:
                yield {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call-login",
                            "function": {
                                "name": "project_host_run_command",
                                "arguments": json.dumps(
                                    {
                                        "command": 'lark-cli auth login --scope "im:message.send_as_user"',
                                    },
                                    ensure_ascii=False,
                                ),
                            },
                        }
                    ]
                }
                return
            yield {"content": "已自动改用 domain 授权，并等待你在浏览器完成授权。"}

        async def chat_completion(self, **kwargs):
            return {"content": "fallback"}

    class _FakeToolExecutor:
        def __init__(self, *args, **kwargs):
            self.calls = 0

        async def execute_parallel(self, tool_calls, timeout=None):
            self.calls += 1
            command = json.loads(tool_calls[0]["function"]["arguments"])["command"]
            if self.calls == 1:
                return [
                    {
                        "ok": False,
                        "command": command,
                        "cwd": "/tmp/project",
                        "workspace_path": "/tmp/project",
                        "exit_code": 3,
                        "stdout": "",
                        "stderr": json.dumps(
                            {
                                "ok": False,
                                "error": {
                                    "type": "auth",
                                    "message": (
                                        "device authorization failed: Device authorization failed: "
                                        "The provided scope list contains invalid or malformed scopes. "
                                        "Please ensure all scopes are valid."
                                    ),
                                },
                            },
                            ensure_ascii=False,
                        ),
                    }
                ]
            return [
                {
                    "ok": False,
                    "timed_out": True,
                    "command": command,
                    "cwd": "/tmp/project",
                    "workspace_path": "/tmp/project",
                    "exit_code": 124,
                    "stdout": (
                        "在浏览器中打开以下链接进行认证:\n"
                        "https://open.feishu.cn/page/cli?user_code=abc\n"
                        "等待用户授权..."
                    ),
                    "stderr": "",
                }
            ]

    class _FakeConversationManager:
        async def get_context(self, session_id, max_tokens):
            return []

        async def append_message(self, session_id, message):
            return None

    monkeypatch.setattr("services.agent_orchestrator.ToolExecutor", _FakeToolExecutor)

    orchestrator = AgentOrchestrator(_FakeLLM(), _FakeConversationManager())
    cancel_event = asyncio.Event()
    events = []
    async for item in orchestrator.run(
        session_id="session-lark-auth-recovery",
        user_message="继续完成飞书授权",
        tools=[{"tool_name": "project_host_run_command"}],
        provider_id="provider-1",
        model_name="glm-test",
        temperature=0.1,
        max_tokens=256,
        project_id="proj-1",
        employee_id="",
        cancel_event=cancel_event,
        username="tester",
        chat_session_id="chat-lark-auth-recovery",
    ):
        events.append(item)

    auto_continue_event = next(
        item
        for item in events
        if item["type"] == "auto_continue"
        and item["reason"] == "auto_followup_command"
    )
    tool_results = [item for item in events if item["type"] == "tool_result"]
    assert "系统已自动继续执行" in str(auto_continue_event["message"] or "")
    assert "auth login --domain im" in str(
        auto_continue_event["previous_response_preview"] or ""
    )
    assert len(tool_results) == 2
    assert 'auth login --scope "im:message.send_as_user"' in str(
        tool_results[0].get("command") or ""
    )
    assert "auth login --domain im" in str(tool_results[1].get("command") or "")
    assert events[-1]["type"] == "done"
    assert "等待你在浏览器完成授权" in str(events[-1]["content"] or "")


@pytest.mark.asyncio
async def test_agent_orchestrator_retries_pending_lark_send_after_successful_auth(monkeypatch):
    import asyncio
    import json

    from services.agent_orchestrator import AgentOrchestrator

    class _FakeLLM:
        def __init__(self):
            self._stream_calls = 0

        async def chat_completion_stream(self, **kwargs):
            self._stream_calls += 1
            if self._stream_calls == 1:
                yield {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call-send",
                            "function": {
                                "name": "project_host_run_command",
                                "arguments": json.dumps(
                                    {
                                        "command": (
                                            "lark-cli im +messages-send --as user "
                                            "--user-id ou_aeda3de2ac3748fb634016a949ad6d04 "
                                            "--text 'test'"
                                        ),
                                    },
                                    ensure_ascii=False,
                                ),
                            },
                        }
                    ]
                }
                return
            yield {"content": "已完成授权并自动重试发送，message_id=om_456。"}

        async def chat_completion(self, **kwargs):
            return {"content": "fallback"}

    class _FakeToolExecutor:
        def __init__(self, *args, **kwargs):
            self.calls = 0

        async def execute_parallel(self, tool_calls, timeout=None):
            self.calls += 1
            command = json.loads(tool_calls[0]["function"]["arguments"])["command"]
            if self.calls == 1:
                return [
                    {
                        "ok": True,
                        "command": command,
                        "cwd": "/tmp/project",
                        "workspace_path": "/tmp/project",
                        "exit_code": 0,
                        "stdout": json.dumps(
                            {
                                "ok": False,
                                "identity": "user",
                                "error": {
                                    "type": "missing_scope",
                                    "message": "missing required scope(s): im:message.send_as_user",
                                    "hint": (
                                        'run `lark-cli auth login --scope "im:message.send_as_user"` '
                                        "in the background."
                                    ),
                                },
                            },
                            ensure_ascii=False,
                        ),
                        "stderr": "",
                    }
                ]
            if self.calls == 2:
                return [
                    {
                        "ok": True,
                        "command": command,
                        "cwd": "/tmp/project",
                        "workspace_path": "/tmp/project",
                        "exit_code": 0,
                        "stdout": '{"ok":true,"authorized":true}',
                        "stderr": "",
                    }
                ]
            return [
                {
                    "ok": True,
                    "command": command,
                    "cwd": "/tmp/project",
                    "workspace_path": "/tmp/project",
                    "exit_code": 0,
                    "stdout": '{"message_id":"om_456","code":0}',
                    "stderr": "",
                }
            ]

    class _FakeConversationManager:
        async def get_context(self, session_id, max_tokens):
            return []

        async def append_message(self, session_id, message):
            return None

    monkeypatch.setattr("services.agent_orchestrator.ToolExecutor", _FakeToolExecutor)

    orchestrator = AgentOrchestrator(_FakeLLM(), _FakeConversationManager())
    cancel_event = asyncio.Event()
    events = []
    async for item in orchestrator.run(
        session_id="session-lark-auth-resend",
        user_message="帮我直接给屈行行发送 test",
        tools=[{"tool_name": "project_host_run_command"}],
        provider_id="provider-1",
        model_name="glm-test",
        temperature=0.1,
        max_tokens=256,
        project_id="proj-1",
        employee_id="",
        cancel_event=cancel_event,
        username="tester",
        chat_session_id="chat-lark-auth-resend",
    ):
        events.append(item)

    auto_continue_reasons = [
        item["reason"]
        for item in events
        if item["type"] == "auto_continue"
    ]
    tool_results = [item for item in events if item["type"] == "tool_result"]
    assert auto_continue_reasons == [
        "auto_followup_command",
        "lark_cli_resume_after_auth",
    ]
    assert len(tool_results) == 3
    assert "messages-send" in str(tool_results[0].get("command") or "")
    assert "auth login --scope" in str(tool_results[1].get("command") or "")
    assert "messages-send" in str(tool_results[2].get("command") or "")
    assert events[-1]["type"] == "done"
    assert "message_id=om_456" in str(events[-1]["content"] or "")


@pytest.mark.asyncio
async def test_agent_orchestrator_stops_on_browser_authorization_wait(monkeypatch):
    import asyncio
    import json

    from services.agent_orchestrator import AgentOrchestrator

    class _FakeLLM:
        async def chat_completion_stream(self, **kwargs):
            yield {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "call-auth",
                        "function": {
                            "name": "project_host_run_command",
                            "arguments": json.dumps(
                                {
                                    "command": 'lark-cli auth login --scope "im:message.send_as_user"',
                                },
                                ensure_ascii=False,
                            ),
                        },
                    }
                ]
            }

        async def chat_completion(self, **kwargs):
            return {"content": "fallback"}

    class _FakeToolExecutor:
        def __init__(self, *args, **kwargs):
            pass

        async def execute_parallel(self, tool_calls, timeout=None):
            command = json.loads(tool_calls[0]["function"]["arguments"])["command"]
            return [
                {
                    "ok": False,
                    "command": command,
                    "source": "operation_wait_task",
                    "operation_kind": "auth_login",
                    "operation_label": "网页登录授权",
                    "interactive": True,
                    "requires_user_action": True,
                    "waiting_user_action": True,
                    "action_type": "open_url",
                    "authorization_url": "https://open.feishu.cn/mock-auth",
                    "status": "waiting_user_action",
                    "status_label": "等待授权",
                    "next_step": "请在浏览器完成授权后回到对话框继续。",
                    "task_id": "cli-plugin-login-1",
                    "stdout": "",
                    "stderr": "",
                    "exit_code": None,
                }
            ]

    class _FakeConversationManager:
        def __init__(self):
            self.messages = []

        async def get_context(self, session_id, max_tokens):
            return []

        async def append_message(self, session_id, message):
            self.messages.append(message)

    monkeypatch.setattr("services.agent_orchestrator.ToolExecutor", _FakeToolExecutor)
    monkeypatch.setattr("services.agent_orchestrator.audit_task_tree_round", lambda **kwargs: None)

    conversation = _FakeConversationManager()
    orchestrator = AgentOrchestrator(_FakeLLM(), conversation)
    cancel_event = asyncio.Event()
    events = []
    async for item in orchestrator.run(
        session_id="session-auth-wait",
        user_message="帮我登录飞书用户态",
        tools=[{"tool_name": "project_host_run_command"}],
        provider_id="provider-1",
        model_name="glm-test",
        temperature=0.1,
        max_tokens=256,
        project_id="proj-1",
        employee_id="",
        cancel_event=cancel_event,
        username="tester",
        chat_session_id="chat-auth-wait",
    ):
        events.append(item)

    waiting_event = next(item for item in events if item["type"] == "user_action_required")
    done_event = next(item for item in events if item["type"] == "done")
    tool_results = [item for item in events if item["type"] == "tool_result"]

    assert len(tool_results) == 1
    assert waiting_event["authorization_url"] == "https://open.feishu.cn/mock-auth"
    assert waiting_event["task_id"] == "cli-plugin-login-1"
    assert waiting_event["action_type"] == "open_url"
    assert "resume_command" in waiting_event
    assert done_event["completed_reason"] == "waiting_user_action"
    assert "完成授权" in str(done_event["content"] or "")


@pytest.mark.asyncio
async def test_agent_orchestrator_stops_on_queued_login_task(monkeypatch):
    import asyncio
    import json

    from services.agent_orchestrator import AgentOrchestrator

    class _FakeLLM:
        async def chat_completion_stream(self, **kwargs):
            yield {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "call-auth-queued",
                        "function": {
                            "name": "project_host_run_command",
                            "arguments": json.dumps(
                                {
                                    "command": "lark-cli auth login --recommend",
                                },
                                ensure_ascii=False,
                            ),
                        },
                    }
                ]
            }

        async def chat_completion(self, **kwargs):
            return {"content": "fallback"}

    class _FakeToolExecutor:
        def __init__(self, *args, **kwargs):
            pass

        async def execute_parallel(self, tool_calls, timeout=None):
            command = json.loads(tool_calls[0]["function"]["arguments"])["command"]
            return [
                {
                    "ok": False,
                    "command": command,
                    "source": "operation_wait_task",
                    "operation_kind": "auth_login",
                    "operation_label": "网页登录授权",
                    "interactive": True,
                    "requires_user_action": False,
                    "waiting_user_action": False,
                    "action_type": "none",
                    "authorization_url": "",
                    "status": "queued",
                    "status_label": "排队中",
                    "next_step": "任务已创建，等待后台执行",
                    "task_id": "cli-plugin-login-queued-1",
                    "stdout": "",
                    "stderr": "",
                    "exit_code": None,
                }
            ]

    class _FakeConversationManager:
        def __init__(self):
            self.messages = []

        async def get_context(self, session_id, max_tokens):
            return []

        async def append_message(self, session_id, message):
            self.messages.append(message)

    monkeypatch.setattr("services.agent_orchestrator.ToolExecutor", _FakeToolExecutor)
    monkeypatch.setattr("services.agent_orchestrator.audit_task_tree_round", lambda **kwargs: None)

    conversation = _FakeConversationManager()
    orchestrator = AgentOrchestrator(_FakeLLM(), conversation)
    cancel_event = asyncio.Event()
    events = []
    async for item in orchestrator.run(
        session_id="session-auth-queued",
        user_message="帮我登录飞书用户态",
        tools=[{"tool_name": "project_host_run_command"}],
        provider_id="provider-1",
        model_name="glm-test",
        temperature=0.1,
        max_tokens=256,
        project_id="proj-1",
        employee_id="",
        cancel_event=cancel_event,
        username="tester",
        chat_session_id="chat-auth-queued",
    ):
        events.append(item)

    done_event = next(item for item in events if item["type"] == "done")
    workflow_state_event = next(item for item in events if item["type"] == "workflow_state")
    operation_state_event = next(item for item in events if item["type"] == "operation_task_state")
    tool_result = next(item for item in events if item["type"] == "tool_result")

    assert tool_result["task_id"] == "cli-plugin-login-queued-1"
    assert tool_result["task_status"] == "queued"
    assert workflow_state_event["workflow_kind"] == "auth_login"
    assert workflow_state_event["status"] == "queued"
    assert workflow_state_event["summary"] == "外部操作已创建，等待后续结果"
    assert operation_state_event["status"] == "queued"
    assert operation_state_event["summary"] == "外部操作已创建，等待后续结果"
    assert done_event["completed_reason"] == "background_task_pending"
    assert done_event["content"] == ""
    assert done_event["guard_message"] == "任务已创建，等待后台执行"
    assert done_event["task_id"] == "cli-plugin-login-queued-1"
