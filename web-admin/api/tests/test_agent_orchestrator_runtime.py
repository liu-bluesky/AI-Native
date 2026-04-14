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
