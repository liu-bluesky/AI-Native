from services.runtime.provider_resolver import ResolvedProviderRuntime
from services.runtime.run_request_factory import build_orchestrator_run_kwargs
from services.runtime.runtime_resolver import build_chat_runtime_context


def test_build_orchestrator_run_kwargs_uses_runtime_context_defaults():
    runtime_context = build_chat_runtime_context(
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
        employee_id="emp-1",
        workspace_path="/tmp/workspace",
        chat_settings={"temperature": 0.2},
        resolved_provider=ResolvedProviderRuntime(
            provider_mode="project",
            provider={"id": "provider-1"},
            providers=[{"id": "provider-1"}],
            provider_id="provider-1",
            model_name="glm-test",
        ),
        tools=[{"name": "tool-a"}],
        messages=[{"role": "user", "content": "hello"}],
        local_connector={"id": "connector-1"},
        local_connector_sandbox_mode="danger-full-access",
    )

    payload = build_orchestrator_run_kwargs(
        session_id="session-1",
        user_message="继续执行",
        runtime_context=runtime_context,
        temperature=0.3,
        max_tokens=256,
        cancel_event=object(),
    )

    assert payload["session_id"] == "session-1"
    assert payload["user_message"] == "继续执行"
    assert payload["project_id"] == "proj-1"
    assert payload["employee_id"] == "emp-1"
    assert payload["username"] == "tester"
    assert payload["chat_session_id"] == "chat-1"
    assert payload["provider_id"] == "provider-1"
    assert payload["model_name"] == "glm-test"
    assert payload["temperature"] == 0.3
    assert payload["max_tokens"] == 256
    assert payload["tools"] == [{"name": "tool-a"}]
    assert payload["messages"] == [{"role": "user", "content": "hello"}]
    assert payload["local_connector"] == {"id": "connector-1"}
    assert payload["local_connector_workspace_path"] == "/tmp/workspace"
    assert payload["host_workspace_path"] == "/tmp/workspace"
    assert payload["local_connector_sandbox_mode"] == "danger-full-access"
    assert "role_ids" not in payload
    assert "global_assistant_bridge_handler" not in payload


def test_build_orchestrator_run_kwargs_includes_optional_global_assistant_fields():
    runtime_context = build_chat_runtime_context(
        project_id="__global-assistant__",
        username="tester",
        chat_session_id="chat-global-1",
        chat_settings={},
        resolved_provider=ResolvedProviderRuntime(
            provider_mode="global",
            provider={"id": "provider-global"},
            providers=[{"id": "provider-global"}],
            provider_id="provider-global",
            model_name="glm-global",
        ),
    )
    bridge_handler = object()

    payload = build_orchestrator_run_kwargs(
        session_id="session-global-1",
        user_message="打开浏览器",
        runtime_context=runtime_context,
        temperature=0.1,
        max_tokens=512,
        cancel_event=object(),
        role_ids=["admin"],
        global_assistant_bridge_handler=bridge_handler,
    )

    assert payload["role_ids"] == ["admin"]
    assert payload["global_assistant_bridge_handler"] is bridge_handler
