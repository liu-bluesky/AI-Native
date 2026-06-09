"""项目聊天运行态快照路由测试"""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import requests
from fastapi.testclient import TestClient


def _build_project_chat_runtime_test_client(tmp_path, monkeypatch, auth_payload):
    from core import config as core_config
    from core.deps import require_auth
    from core.server import create_app
    from stores import factory as store_factory

    monkeypatch.setenv("CORE_STORE_BACKEND", "json")
    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()
    for proxy_name in (
        "role_store",
        "bot_connector_store",
        "system_config_store",
        "project_store",
        "project_chat_store",
        "project_chat_runtime_store",
        "project_chat_task_store",
        "work_session_store",
        "task_tree_evolution_store",
    ):
        getattr(store_factory, proxy_name)._instance = None

    app = create_app()
    app.dependency_overrides[require_auth] = lambda: auth_payload
    return TestClient(app), store_factory


def test_feishu_project_chat_session_id_isolates_group_and_private_messages():
    from services.feishu.feishu_bot_service import _resolve_feishu_project_chat_session_id

    group_sender_1 = _resolve_feishu_project_chat_session_id(
        connector_id="conn-feishu-1",
        chat_type="group",
        chat_id="oc_group_1",
        thread_id="",
        sender_open_id="ou_sender_1",
    )
    group_sender_2 = _resolve_feishu_project_chat_session_id(
        connector_id="conn-feishu-1",
        chat_type="group",
        chat_id="oc_group_1",
        thread_id="",
        sender_open_id="ou_sender_2",
    )
    other_group = _resolve_feishu_project_chat_session_id(
        connector_id="conn-feishu-1",
        chat_type="group",
        chat_id="oc_group_2",
        thread_id="",
        sender_open_id="ou_sender_1",
    )
    private_sender_1 = _resolve_feishu_project_chat_session_id(
        connector_id="conn-feishu-1",
        chat_type="p2p",
        chat_id="oc_private",
        thread_id="",
        sender_open_id="ou_sender_1",
    )
    private_sender_2 = _resolve_feishu_project_chat_session_id(
        connector_id="conn-feishu-1",
        chat_type="p2p",
        chat_id="oc_private",
        thread_id="",
        sender_open_id="ou_sender_2",
    )

    assert group_sender_1 == group_sender_2
    assert group_sender_1 != other_group
    assert private_sender_1 != private_sender_2


def test_parse_feishu_text_message_preserves_mention_display_name():
    from services.feishu.feishu_bot_service import _parse_feishu_text_message

    class Obj:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    event = Obj(
        event=Obj(
            message=Obj(
                message_type="text",
                content='{"text":"@_user_1 请跟进这个需求"}',
                mentions=[Obj(key="@_user_1", name="刘蓝天")],
            )
        )
    )

    assert _parse_feishu_text_message(event) == "@刘蓝天 请跟进这个需求"



def test_project_chat_ws_disconnect_unregisters_without_name_error(tmp_path, monkeypatch):
    from core.auth import create_token
    from stores.json.project_store import ProjectConfig, ProjectUserMember

    client, store_factory = _build_project_chat_runtime_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    store_factory.project_store.upsert_user_member(
        ProjectUserMember(project_id="proj-1", username="tester", role="owner")
    )

    token = create_token("tester", role="admin", roles=["admin"])
    with client.websocket_connect(f"/api/projects/proj-1/chat/ws?token={token}") as websocket:
        ready = websocket.receive_json()
        assert ready["type"] == "ready"


def test_project_chat_runtime_snapshot_routes_and_history_cleanup(tmp_path, monkeypatch):
    from stores.json.project_chat_store import ProjectChatMessage
    from stores.json.project_store import ProjectConfig

    client, store_factory = _build_project_chat_runtime_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    session = store_factory.project_chat_store.create_session("proj-1", "tester", "新对话")
    store_factory.project_chat_store.append_message(
        ProjectChatMessage(
            project_id="proj-1",
            username="tester",
            role="user",
            content="请继续安装并授权",
            chat_session_id=session.id,
        )
    )

    save_response = client.put(
        "/api/projects/proj-1/chat/runtime",
        json={
            "chat_session_id": session.id,
            "payload": {
                "version": 1,
                "terminal": {
                    "status": "running",
                    "session_id": "term-1",
                },
                "messages": {
                    "chat-msg-1": {
                        "display_mode": "terminal",
                    }
                },
            },
        },
    )
    assert save_response.status_code == 200
    assert save_response.json()["snapshot"]["chat_session_id"] == session.id

    get_response = client.get(
        "/api/projects/proj-1/chat/runtime",
        params={"chat_session_id": session.id},
    )
    assert get_response.status_code == 200
    snapshot = get_response.json()["snapshot"]
    assert snapshot["payload"]["terminal"]["status"] == "running"
    assert snapshot["payload"]["messages"]["chat-msg-1"]["display_mode"] == "terminal"

    clear_response = client.delete(
        "/api/projects/proj-1/chat/history",
        params={"chat_session_id": session.id},
    )
    assert clear_response.status_code == 200

    after_clear_response = client.get(
        "/api/projects/proj-1/chat/runtime",
        params={"chat_session_id": session.id},
    )
    assert after_clear_response.status_code == 200
    assert after_clear_response.json()["snapshot"] is None


def test_agent_runtime_resume_persists_same_assistant_message_id(tmp_path, monkeypatch):
    from routers import projects as projects_router
    from stores.json.project_chat_store import ProjectChatMessage
    from stores.json.project_store import ProjectConfig

    _client, store_factory = _build_project_chat_runtime_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    session = store_factory.project_chat_store.create_session("proj-1", "tester", "新对话")
    store_factory.project_chat_store.append_message(
        ProjectChatMessage(
            id="assistant-1",
            project_id="proj-1",
            username="tester",
            role="assistant",
            content="等待授权",
            chat_session_id=session.id,
            source_context={"assistant_workflow": {"status": "running"}},
        )
    )

    updated = projects_router._persist_agent_runtime_resume_chat_message(
        project_id="proj-1",
        username="tester",
        chat_session_id=session.id,
        assistant_message_id="assistant-1",
        content="授权后已经继续完成",
        run_id="run-1",
        call_id="call-1",
        tool_name="project_host_run_command",
        resume_payload={"continuation": {"final_content": "授权后已经继续完成"}},
        runtime_events=[
            {
                "event_type": "permission_decision",
                "created_at": "2026-01-01T00:00:00+00:00",
                "payload": {
                    "decision": {
                        "behavior": "ask",
                        "call_id": "call-1",
                        "tool_name": "project_host_run_command",
                    },
                    "tool_call": {
                        "call_id": "call-1",
                        "tool_name": "project_host_run_command",
                        "arguments": "{\"command\":\"pwd\"}",
                    },
                },
            },
            {
                "event_type": "permission_action_applied",
                "created_at": "2026-01-01T00:00:01+00:00",
                "payload": {
                    "action": "allow_once",
                    "call_id": "call-1",
                    "rule": {"tool_name": "project_host_run_command"},
                },
            },
            {
                "event_type": "query_engine_completed",
                "created_at": "2026-01-01T00:00:02+00:00",
                "payload": {},
            },
        ],
    )

    assert updated is not None
    assert updated.id == "assistant-1"
    assert updated.content == "授权后已经继续完成"
    messages = store_factory.project_chat_store.list_messages(
        "proj-1",
        "tester",
        limit=0,
        chat_session_id=session.id,
    )
    assert [item.id for item in messages] == ["assistant-1"]
    assert messages[0].source_context["assistant_workflow"]["status"] == "running"
    assert messages[0].source_context["agent_runtime_v2"]["run_id"] == "run-1"
    trace = messages[0].source_context["agent_runtime_trace"]
    assert any(item["text"] == "工具调用等待授权" for item in trace["process_log"])
    assert any(item["text"] == "工具调用授权已保存" for item in trace["process_log"])
    permission_operation = next(
        item
        for item in trace["operations"]
        if item["operationId"] == "agent-runtime-permission:run-1:call-1"
    )
    assert permission_operation["phase"] == "completed"
    assert permission_operation["actionType"] == "none"


def test_agent_runtime_resume_falls_back_to_auth_status_result(tmp_path, monkeypatch):
    from routers import projects as projects_router
    from stores.json.project_chat_store import ProjectChatMessage
    from stores.json.project_store import ProjectConfig

    _client, store_factory = _build_project_chat_runtime_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    session = store_factory.project_chat_store.create_session("proj-1", "tester", "新对话")
    store_factory.project_chat_store.append_message(
        ProjectChatMessage(
            id="assistant-1",
            project_id="proj-1",
            username="tester",
            role="assistant",
            content="等待授权",
            chat_session_id=session.id,
            source_context={"assistant_workflow": {"status": "running"}},
        )
    )

    updated = projects_router._persist_agent_runtime_resume_chat_message(
        project_id="proj-1",
        username="tester",
        chat_session_id=session.id,
        assistant_message_id="assistant-1",
        content="",
        run_id="run-1",
        call_id="call-1",
        tool_name="project_host_run_command",
        resume_payload={
            "records": [
                {
                    "tool_call": {
                        "call_id": "call-1",
                        "tool_name": "project_host_run_command",
                        "arguments": json.dumps(
                            {
                                "command": (
                                    "/opt/plugin/bin/lark-cli auth status --format json"
                                )
                            }
                        ),
                    },
                    "raw_result": {
                        "exit_code": 0,
                        "stdout": json.dumps({"ok": True, "identity": "user"}),
                        "stderr": "",
                    },
                }
            ],
            "continuation": {"final_content": ""},
        },
        runtime_events=[],
    )

    assert updated is None


def test_agent_runtime_resume_does_not_fallback_to_tool_output_without_final_answer():
    from routers import projects as projects_router

    content = projects_router._agent_runtime_resume_final_content(
        {
            "records": [
                {
                    "tool_call": {
                        "call_id": "call-1",
                        "tool_name": "project_host_run_command",
                        "arguments": json.dumps(
                            {
                                "command": (
                                    "/opt/plugin/bin/lark-cli auth status --format json"
                                )
                            }
                        ),
                    },
                    "raw_result": {
                        "exit_code": 0,
                        "stdout": json.dumps({"ok": True, "identity": "user"}),
                        "stderr": "",
                    },
                }
            ],
            "continuation": {"final_content": "本轮执行已结束"},
        }
    )

    assert content == ""


def test_direct_lark_cli_reply_is_processed_by_model():
    from routers import projects as projects_router

    class FakeLlmService:
        def __init__(self):
            self.calls = []

        async def chat_completion(
            self,
            provider_id,
            model_name,
            messages,
            temperature=0.2,
            max_tokens=1024,
            timeout=45,
        ):
            self.calls.append(
                {
                    "provider_id": provider_id,
                    "model_name": model_name,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "timeout": timeout,
                }
            )
            return {
                "content": "结论：当前没有 user 登录态，只能使用 bot 身份调用飞书 API。",
                "provider_id": provider_id,
                "model_name": model_name,
            }

    fallback = "已直接执行 lark-cli 命令。"
    result = asyncio.run(
        projects_router._build_direct_lark_cli_model_reply(
            llm_service=FakeLlmService(),
            provider_id="openai",
            model_name="gpt-5.4",
            user_message="/lark-cli 检测登录",
            result={
                "command": "lark-cli auth status",
                "exit_code": 0,
                "stdout": json.dumps({"identity": "bot", "note": "No user logged in."}),
                "stderr": "",
                "workspace_path": "/repo",
            },
            fallback_reply=fallback,
        )
    )

    assert result["model_processed"] is True
    assert result["content"].startswith("结论：当前没有 user 登录态")
    assert result["content"] != fallback


def test_ambiguous_update_request_builds_structured_clarify_interaction():
    from routers import projects as projects_router

    payload = projects_router._build_project_chat_clarify_interaction_payload(
        user_message="你是否可以更新",
        chat_session_id="chat-clarify-1",
        request_id="req-clarify-1",
    )

    assert payload is not None
    assert payload["type"] == "user_action_required"
    assert payload["workflow_kind"] == "clarify"
    assert payload["action_type"] == "interaction_form"
    schema = payload["interaction_schema"]
    assert schema["title"] == "需要你确认更新目标"
    choice_field = schema["schema"][0]
    assert choice_field["prop"] == "update_target"
    assert choice_field["componentName"] == "ElRadioGroup"
    assert len(choice_field["children"]) == 4

    pending = projects_router._build_project_chat_pending_interaction(payload)
    assert pending is not None
    assert pending["phase"] == "waiting_user"
    assert pending["workflow_kind"] == "clarify"
    assert pending["interaction_schema"]["title"] == "需要你确认更新目标"
    assert (
        projects_router._should_handle_project_chat_operation_interaction_submit(
            {
                "chat_session_id": "chat-clarify-1",
                "interaction_operation_id": pending["operation_id"],
                "interaction_action_type": "interaction_form",
                "workflow_kind": "clarify",
                "workflow_state": payload,
                "interaction_data": {"update_target": "code_feature"},
            }
        )
        is False
    )


def test_clear_commands_do_not_trigger_update_clarify_interaction():
    from routers import projects as projects_router

    assert (
        projects_router._build_project_chat_clarify_interaction_payload(
            user_message="/lark-cli 退出",
            chat_session_id="chat-clarify-1",
        )
        is None
    )
    assert (
        projects_router._build_project_chat_clarify_interaction_payload(
            user_message="学习 Hermes 后修改当前系统代码交互逻辑",
            chat_session_id="chat-clarify-1",
        )
        is None
    )


def test_project_chat_session_update_and_feishu_manual_binding(tmp_path, monkeypatch):
    from routers import projects as projects_router
    from services.feishu.feishu_bot_service import _find_or_bind_feishu_manual_chat_session
    from stores.json.project_store import ProjectConfig

    client, store_factory = _build_project_chat_runtime_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))

    create_response = client.post(
        "/api/projects/proj-1/chat/sessions",
        json={
            "title": "飞书群：产品研发群",
            "source_context": {
                "source_type": "group_message",
                "platform": "feishu",
                "connector_id": "conn-feishu-1",
                "external_chat_name": "产品研发群",
            },
        },
    )
    assert create_response.status_code == 200
    session = create_response.json()["session"]
    assert session["source_context"]["connector_id"] == "conn-feishu-1"
    assert "external_chat_id" not in session["source_context"]

    patch_response = client.patch(
        f"/api/projects/proj-1/chat/sessions/{session['id']}",
        json={
            "title": "售前需求群",
            "source_context": {
                "source_type": "group_message",
                "platform": "feishu",
                "connector_id": "conn-feishu-1",
                "external_chat_name": "产品研发群",
            },
        },
    )
    assert patch_response.status_code == 200
    updated = patch_response.json()["session"]
    assert updated["title"] == "售前需求群"

    bound = _find_or_bind_feishu_manual_chat_session(
        project_id="proj-1",
        username="tester",
        connector_id="conn-feishu-1",
        chat_id="oc_real_group_1",
        chat_type="group",
        projects_router=projects_router,
    )
    assert bound is not None
    bound_session_id, bound_context = bound
    assert bound_session_id == session["id"]
    assert bound_context["external_chat_id"] == "oc_real_group_1"
    assert bound_context["thread_key"] == "feishu:conn-feishu-1:chat:oc_real_group_1"


def test_project_chat_session_resolve_source_uses_feishu_search(tmp_path, monkeypatch):
    from stores.json.project_store import ProjectConfig

    client, store_factory = _build_project_chat_runtime_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    store_factory.bot_connector_store.replace_all(
        [
            {
                "id": "conn-feishu-1",
                "platform": "feishu",
                "name": "飞书机器人",
                "enabled": True,
                "project_id": "",
                "app_id": "cli_xxx",
                "app_secret": "secret_xxx",
                "bot_open_id": "ou_bot_1",
                "system_prompt": "你是飞书群里的需求协作机器人，只回答和项目推进有关的问题。",
            }
        ]
    )
    create_response = client.post(
        "/api/projects/proj-1/chat/sessions",
        json={
            "title": "飞书群：产品研发群",
            "source_context": {
                "source_type": "group_message",
                "platform": "feishu",
                "connector_id": "conn-feishu-1",
                "external_chat_name": "产品研发群",
            },
        },
    )
    assert create_response.status_code == 200
    session = create_response.json()["session"]

    def fake_resolve(connector, chat_name, *, identity="bot"):
        assert connector["id"] == "conn-feishu-1"
        assert chat_name == "产品研发群"
        assert identity == "bot"
        return {"chat_id": "oc_real_group_1", "name": "产品研发群"}

    monkeypatch.setattr(
        "services.feishu.feishu_bot_service.resolve_feishu_chat_by_name",
        fake_resolve,
    )
    resolve_response = client.post(
        f"/api/projects/proj-1/chat/sessions/{session['id']}/resolve-source",
    )
    assert resolve_response.status_code == 200
    payload = resolve_response.json()
    assert payload["resolved"] is True
    resolved_context = payload["session"]["source_context"]
    assert resolved_context["external_chat_id"] == "oc_real_group_1"
    assert resolved_context["thread_key"] == "feishu:conn-feishu-1:chat:oc_real_group_1"


def test_project_chat_session_resolve_source_can_use_user_identity(tmp_path, monkeypatch):
    from stores.json.project_store import ProjectConfig

    client, store_factory = _build_project_chat_runtime_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    store_factory.bot_connector_store.replace_all(
        [
            {
                "id": "conn-feishu-1",
                "platform": "feishu",
                "name": "飞书机器人",
                "enabled": True,
                "project_id": "",
                "app_id": "cli_xxx",
                "app_secret": "secret_xxx",
            }
        ]
    )
    create_response = client.post(
        "/api/projects/proj-1/chat/sessions",
        json={
            "title": "飞书群：产品研发群",
            "source_context": {
                "source_type": "group_message",
                "platform": "feishu",
                "connector_id": "conn-feishu-1",
                "external_chat_name": "产品研发群",
                "resolve_identity": "user",
            },
        },
    )
    assert create_response.status_code == 200
    session = create_response.json()["session"]
    calls = []

    def fake_resolve(connector, chat_name, *, identity="bot"):
        calls.append({"connector": connector, "chat_name": chat_name, "identity": identity})
        return {"chat_id": "oc_user_visible_group", "name": "产品研发群"}

    monkeypatch.setattr(
        "services.feishu.feishu_bot_service.resolve_feishu_chat_by_name",
        fake_resolve,
    )
    resolve_response = client.post(
        f"/api/projects/proj-1/chat/sessions/{session['id']}/resolve-source",
        json={"identity": "user"},
    )
    assert resolve_response.status_code == 200
    payload = resolve_response.json()
    assert calls[0]["connector"]["id"] == "conn-feishu-1"
    assert calls[0]["connector"]["app_id"] == "cli_xxx"
    assert calls[0]["chat_name"] == "产品研发群"
    assert calls[0]["identity"] == "user"
    resolved_context = payload["session"]["source_context"]
    assert resolved_context["external_chat_id"] == "oc_user_visible_group"
    assert resolved_context["resolve_identity"] == "user"


def test_feishu_message_event_routes_by_project_chat_session_binding(tmp_path, monkeypatch):
    from services.feishu.feishu_bot_service import process_feishu_message_event
    from stores.json.project_store import ProjectConfig, ProjectUserMember

    client, store_factory = _build_project_chat_runtime_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    store_factory.project_store.upsert_user_member(
        ProjectUserMember(project_id="proj-1", username="tester", role="owner")
    )
    store_factory.bot_connector_store.replace_all(
        [
            {
                "id": "conn-feishu-1",
                "platform": "feishu",
                "name": "飞书机器人",
                "enabled": True,
                "project_id": "",
                "app_id": "cli_xxx",
                "app_secret": "secret_xxx",
                "bot_open_id": "ou_bot_1",
                "system_prompt": "你是飞书群里的需求协作机器人，只回答和项目推进有关的问题。",
            }
        ]
    )

    create_response = client.post(
        "/api/projects/proj-1/chat/sessions",
        json={
            "title": "飞书群：产品研发群",
            "source_context": {
                "source_type": "group_message",
                "platform": "feishu",
                "connector_id": "conn-feishu-1",
                "external_chat_id": "oc_real_group_1",
                "external_chat_name": "产品研发群",
            },
        },
    )
    assert create_response.status_code == 200
    session = create_response.json()["session"]

    store_factory.system_config_store.patch_global({"voice_output_enabled": True})

    calls = []
    replies = []
    speech_calls = []

    class FakeResult:
        content = "收到"

    async def fake_run_project_chat_once(**kwargs):
        calls.append(kwargs)
        return FakeResult()

    async def fake_reply_feishu_text(connector, **kwargs):
        replies.append((connector, kwargs))

    async def fake_enqueue_system_speech(text, **kwargs):
        speech_calls.append({"text": text, **kwargs})
        return {"queued": True, "reason": ""}

    monkeypatch.setattr(
        "services.feishu.feishu_bot_service.run_project_chat_once",
        fake_run_project_chat_once,
    )
    monkeypatch.setattr(
        "services.feishu.feishu_bot_service._reply_feishu_text",
        fake_reply_feishu_text,
    )
    monkeypatch.setattr(
        "services.feishu.feishu_bot_service.enqueue_system_speech",
        fake_enqueue_system_speech,
    )

    class Obj:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    event = Obj(
        event=Obj(
            sender=Obj(sender_type="user", sender_id=Obj(open_id="ou_sender_1")),
            message=Obj(
                chat_type="group",
                chat_id="oc_real_group_1",
                thread_id="",
                message_id="om_message_1",
                message_type="text",
                content='{"text":"@_user_1 帮我总结一下"}',
                mentions=[Obj(key="@_user_1", id=Obj(open_id="ou_bot_1"))],
            ),
        )
    )

    import asyncio

    asyncio.run(process_feishu_message_event("conn-feishu-1", event))

    assert len(calls) == 1
    assert calls[0]["project_id"] == "proj-1"
    assert calls[0]["username"] == "tester"
    req = calls[0]["req"]
    assert req.chat_session_id == session["id"]
    assert req.message == "帮我总结一下"
    assert "你是飞书群里的需求协作机器人，只回答和项目推进有关的问题。" in req.system_prompt
    assert "飞书机器人通用工作流约束" in req.system_prompt
    assert "lark-cli im +messages-reply" in req.system_prompt
    assert req.skill_resource_directory.endswith("skills")
    assert req.source_context["external_chat_id"] == "oc_real_group_1"
    assert req.source_context["thread_key"] == "feishu:conn-feishu-1:chat:oc_real_group_1"
    assert speech_calls == []
    assert replies[0][1]["message_id"] == "om_message_1"


def test_feishu_message_event_auto_binds_unbound_group_to_connector_project(tmp_path, monkeypatch):
    from services.feishu.feishu_bot_service import process_feishu_message_event
    from stores.json.project_store import ProjectConfig, ProjectUserMember

    client, store_factory = _build_project_chat_runtime_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一", created_by="tester"))
    store_factory.project_store.upsert_user_member(
        ProjectUserMember(project_id="proj-1", username="tester", role="owner")
    )
    store_factory.bot_connector_store.replace_all(
        [
            {
                "id": "conn-feishu-1",
                "platform": "feishu",
                "name": "飞书机器人",
                "enabled": True,
                "project_id": "proj-1",
                "app_id": "cli_xxx",
                "app_secret": "secret_xxx",
                "bot_open_id": "ou_bot_1",
                "system_prompt": "你是飞书群里的需求协作机器人。",
                "provider_id": "provider-bot",
                "model_name": "bot-model",
            }
        ]
    )

    calls = []
    replies = []

    class FakeResult:
        content = "请补充复现步骤、期望结果和实际结果。"

    async def fake_run_project_chat_once(**kwargs):
        calls.append(kwargs)
        return FakeResult()

    async def fake_reply_feishu_text(connector, **kwargs):
        replies.append((connector, kwargs))

    monkeypatch.setattr(
        "services.feishu.feishu_bot_service.run_project_chat_once",
        fake_run_project_chat_once,
    )
    monkeypatch.setattr(
        "services.feishu.feishu_bot_service._reply_feishu_text",
        fake_reply_feishu_text,
    )
    monkeypatch.setattr(
        "services.feishu.feishu_bot_service._resolve_feishu_chat_name_by_id",
        lambda connector, chat_id: "数转CRM技术小组",
    )

    class Obj:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    event = Obj(
        event=Obj(
            sender=Obj(sender_type="user", sender_id=Obj(open_id="ou_sender_1")),
            message=Obj(
                chat_type="group",
                chat_id="oc_unbound_group_1",
                thread_id="",
                message_id="om_unbound_1",
                message_type="text",
                content='{"text":"@_user_1 记录bug：客户列表筛选重置异常"}',
                mentions=[Obj(key="@_user_1", id=Obj(open_id="ou_bot_1"))],
            ),
        )
    )

    import asyncio

    asyncio.run(process_feishu_message_event("conn-feishu-1", event))

    assert len(calls) == 1
    assert calls[0]["project_id"] == "proj-1"
    assert calls[0]["username"] == "tester"
    req = calls[0]["req"]
    assert req.message == "记录bug：客户列表筛选重置异常"
    assert req.provider_id == "provider-bot"
    assert req.model_name == "bot-model"
    assert req.source_context["platform"] == "feishu"
    assert req.source_context["connector_id"] == "conn-feishu-1"
    assert req.source_context["external_chat_id"] == "oc_unbound_group_1"
    assert req.source_context["external_chat_name"] == "数转CRM技术小组"
    assert req.source_context["thread_key"] == "feishu:conn-feishu-1:chat:oc_unbound_group_1"
    sessions = store_factory.project_chat_store.list_sessions("proj-1", "tester", limit=20)
    created = next(item for item in sessions if item.id == req.chat_session_id)
    assert created.title == "飞书群：数转CRM技术小组"
    assert created.external_chat_id == "oc_unbound_group_1"
    assert replies[0][1]["message_id"] == "om_unbound_1"

    event.event.message.message_id = "om_unbound_2"
    event.event.message.content = '{"text":"@_user_1 补充：期望能清空筛选，实际没有清空"}'
    asyncio.run(process_feishu_message_event("conn-feishu-1", event))

    assert len(calls) == 2
    assert calls[1]["req"].chat_session_id == req.chat_session_id


def test_feishu_record_bug_message_does_not_confirm_stale_pending_archive(tmp_path, monkeypatch):
    from services.feishu.feishu_bot_service import process_feishu_message_event
    from stores.json.project_store import ProjectConfig, ProjectUserMember

    client, store_factory = _build_project_chat_runtime_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一", created_by="tester"))
    store_factory.project_store.upsert_user_member(
        ProjectUserMember(project_id="proj-1", username="tester", role="owner")
    )
    store_factory.bot_connector_store.replace_all(
        [
            {
                "id": "conn-feishu-1",
                "platform": "feishu",
                "name": "飞书机器人",
                "enabled": True,
                "project_id": "proj-1",
                "app_id": "cli_xxx",
                "app_secret": "secret_xxx",
                "provider_id": "provider-bot",
                "model_name": "bot-model",
            }
        ]
    )
    create_response = client.post(
        "/api/projects/proj-1/chat/sessions",
        json={
            "title": "飞书私聊：飞书私聊-1a7e3653",
            "source_context": {
                "source_type": "private_message",
                "platform": "feishu",
                "connector_id": "conn-feishu-1",
                "external_chat_id": "oc_private_1",
                "external_chat_name": "飞书私聊-1a7e3653",
            },
        },
    )
    assert create_response.status_code == 200
    session = create_response.json()["session"]
    projects_router = __import__("routers.projects", fromlist=["_append_chat_record"])
    projects_router._append_chat_record(
        project_id="proj-1",
        username="tester",
        role="assistant",
        content="【待归档类型】\nbug\n\n【待归档状态】\n已整理，尚未写入\n\n【结构化内容】\n- 标题：旧的 npm 安装包错",
        message_id="bot-reply-pending-old",
        chat_session_id=session["id"],
        source_context={
            "source_type": "private_message",
            "platform": "feishu",
            "connector_id": "conn-feishu-1",
            "external_chat_id": "oc_private_1",
            "external_chat_name": "飞书私聊-1a7e3653",
            "thread_key": "feishu:conn-feishu-1:chat:oc_private_1",
        },
    )

    from services.assistant import global_assistant_task_service as tasks

    archive_calls = []
    model_calls = []
    replies = []

    def fake_archive(**kwargs):
        archive_calls.append(kwargs)
        raise AssertionError("new record-bug commands must not retry stale pending archive replies")

    class FakeResult:
        content = "请补充 bug 的复现步骤、期望结果和实际结果。"

    async def fake_run_project_chat_once(**kwargs):
        model_calls.append(kwargs)
        return FakeResult()

    async def fake_reply_feishu_text(connector, **kwargs):
        replies.append((connector, kwargs))

    monkeypatch.setattr(tasks, "archive_feishu_task_message", fake_archive)
    monkeypatch.setattr("services.feishu.feishu_bot_service.run_project_chat_once", fake_run_project_chat_once)
    monkeypatch.setattr("services.feishu.feishu_bot_service._reply_feishu_text", fake_reply_feishu_text)

    class Obj:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    event = Obj(
        event=Obj(
            sender=Obj(sender_type="user", sender_id=Obj(open_id="ou_sender_1")),
            message=Obj(
                chat_type="p2p",
                chat_id="oc_private_1",
                thread_id="",
                message_id="om_record_bug_1",
                message_type="text",
                content='{"text":"记录bug"}',
                mentions=[],
            ),
        )
    )

    import asyncio

    asyncio.run(process_feishu_message_event("conn-feishu-1", event))

    assert archive_calls == []
    assert len(model_calls) == 1
    req = model_calls[0]["req"]
    assert req.chat_session_id == session["id"]
    assert req.message == "记录bug"
    assert replies[0][1]["message_id"] == "om_record_bug_1"


def test_feishu_message_event_unbound_group_without_project_binding_still_replies(tmp_path, monkeypatch):
    from services.feishu.feishu_bot_service import process_feishu_message_event
    from stores.json.project_store import ProjectConfig

    client, store_factory = _build_project_chat_runtime_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    store_factory.project_store.save(ProjectConfig(id="proj-2", name="项目二"))
    store_factory.bot_connector_store.replace_all(
        [
            {
                "id": "conn-feishu-1",
                "platform": "feishu",
                "name": "飞书机器人",
                "enabled": True,
                "project_id": "",
                "app_id": "cli_xxx",
                "app_secret": "secret_xxx",
                "bot_open_id": "ou_bot_1",
            }
        ]
    )

    calls = []
    replies = []

    async def fake_run_project_chat_once(**kwargs):
        calls.append(kwargs)
        class FakeResult:
            content = "收到，我先按当前飞书群上下文处理。"

        return FakeResult()

    async def fake_reply_feishu_text(connector, **kwargs):
        replies.append((connector, kwargs))

    monkeypatch.setattr(
        "services.feishu.feishu_bot_service.run_project_chat_once",
        fake_run_project_chat_once,
    )
    monkeypatch.setattr(
        "services.feishu.feishu_bot_service._reply_feishu_text",
        fake_reply_feishu_text,
    )

    class Obj:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    event = Obj(
        event=Obj(
            sender=Obj(sender_type="user", sender_id=Obj(open_id="ou_sender_1")),
            message=Obj(
                chat_type="group",
                chat_id="oc_unbound_group_1",
                thread_id="",
                message_id="om_unbound_1",
                message_type="text",
                content='{"text":"@_user_1 记录需求：新增客户标签"}',
                mentions=[Obj(key="@_user_1", id=Obj(open_id="ou_bot_1"))],
            ),
        )
    )

    import asyncio

    asyncio.run(process_feishu_message_event("conn-feishu-1", event))

    assert len(calls) == 1
    assert calls[0]["project_id"] == "proj-1"
    assert calls[0]["username"] == "admin"
    req = calls[0]["req"]
    assert req.message == "记录需求：新增客户标签"
    assert req.source_context["source_type"] == "group_message"
    assert req.source_context["external_chat_id"] == "oc_unbound_group_1"
    assert req.source_context["thread_key"] == "feishu:conn-feishu-1:chat:oc_unbound_group_1"
    assert store_factory.project_chat_store.get_session("proj-1", "admin", req.chat_session_id) is not None
    assert replies[0][1]["message_id"] == "om_unbound_1"


def test_feishu_group_text_without_mention_is_ignored(tmp_path, monkeypatch):
    from services.feishu.feishu_bot_service import process_feishu_message_event
    from stores.json.project_store import ProjectConfig, ProjectUserMember

    _client, store_factory = _build_project_chat_runtime_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    store_factory.project_store.upsert_user_member(
        ProjectUserMember(project_id="proj-1", username="tester", role="owner")
    )
    store_factory.bot_connector_store.replace_all(
        [
            {
                "id": "conn-feishu-1",
                "platform": "feishu",
                "name": "飞书机器人",
                "enabled": True,
                "project_id": "proj-1",
                "app_id": "cli_xxx",
                "app_secret": "secret_xxx",
            }
        ]
    )

    calls = []
    replies = []

    async def fake_run_project_chat_once(**kwargs):
        calls.append(kwargs)
        raise AssertionError("unmentioned group text should not enter project chat")

    async def fake_reply_feishu_text(connector, **kwargs):
        replies.append((connector, kwargs))

    monkeypatch.setattr("services.feishu.feishu_bot_service.run_project_chat_once", fake_run_project_chat_once)
    monkeypatch.setattr("services.feishu.feishu_bot_service._reply_feishu_text", fake_reply_feishu_text)

    class Obj:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    event = Obj(
        event=Obj(
            sender=Obj(sender_type="user", sender_id=Obj(open_id="ou_sender_1")),
            message=Obj(
                chat_type="group",
                chat_id="oc_real_group_1",
                thread_id="",
                message_id="om_plain_1",
                message_type="text",
                content='{"text":"这个群里普通聊天不要机器人回复"}',
                mentions=[],
            ),
        )
    )

    import asyncio

    asyncio.run(process_feishu_message_event("conn-feishu-1", event))

    assert calls == []
    assert replies == []
    sessions = store_factory.project_chat_store.list_sessions("proj-1", "tester", limit=20)
    assert sessions == []


def test_feishu_group_text_mentioning_other_user_without_bot_identity_is_ignored(tmp_path, monkeypatch):
    from services.feishu.feishu_bot_service import process_feishu_message_event
    from stores.json.project_store import ProjectConfig, ProjectUserMember

    _client, store_factory = _build_project_chat_runtime_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    store_factory.project_store.upsert_user_member(
        ProjectUserMember(project_id="proj-1", username="tester", role="owner")
    )
    store_factory.bot_connector_store.replace_all(
        [
            {
                "id": "conn-feishu-1",
                "platform": "feishu",
                "name": "飞书机器人",
                "enabled": True,
                "project_id": "proj-1",
                "app_id": "cli_xxx",
                "app_secret": "secret_xxx",
            }
        ]
    )

    calls = []
    replies = []

    async def fake_run_project_chat_once(**kwargs):
        calls.append(kwargs)
        raise AssertionError("group text mentioning another user should not enter project chat without bot identity")

    async def fake_reply_feishu_text(connector, **kwargs):
        replies.append((connector, kwargs))

    monkeypatch.setattr("services.feishu.feishu_bot_service.run_project_chat_once", fake_run_project_chat_once)
    monkeypatch.setattr("services.feishu.feishu_bot_service._reply_feishu_text", fake_reply_feishu_text)

    class Obj:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    event = Obj(
        event=Obj(
            sender=Obj(sender_type="user", sender_id=Obj(open_id="ou_sender_1")),
            message=Obj(
                chat_type="group",
                chat_id="oc_real_group_1",
                thread_id="",
                message_id="om_other_mention_without_bot_id_1",
                message_type="text",
                content='{"text":"@_user_2 这条不是给机器人"}',
                mentions=[
                    Obj(
                        key="@_user_2",
                        id=Obj(open_id="ou_someone_else", user_id="u_someone_else", union_id="on_someone_else"),
                    )
                ],
            ),
        )
    )

    import asyncio

    asyncio.run(process_feishu_message_event("conn-feishu-1", event))

    assert calls == []
    assert replies == []
    sessions = store_factory.project_chat_store.list_sessions("proj-1", "tester", limit=20)
    assert sessions == []


def test_feishu_event_handler_acknowledges_message_read_events():
    from services.feishu import feishu_bot_service as service

    if not service.is_feishu_sdk_available():
        pytest.skip(service.get_feishu_sdk_error_message())

    import asyncio

    loop = asyncio.new_event_loop()
    try:
        handler = service.build_feishu_event_handler({"id": "conn-feishu-1"}, loop=loop)
        assert "p2.im.message.message_read_v1" in handler._processorMap
    finally:
        loop.close()


def test_feishu_group_text_mentioning_other_user_is_ignored(tmp_path, monkeypatch):
    from services.feishu.feishu_bot_service import process_feishu_message_event
    from stores.json.project_store import ProjectConfig, ProjectUserMember

    _client, store_factory = _build_project_chat_runtime_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    store_factory.project_store.upsert_user_member(
        ProjectUserMember(project_id="proj-1", username="tester", role="owner")
    )
    store_factory.bot_connector_store.replace_all(
        [
            {
                "id": "conn-feishu-1",
                "platform": "feishu",
                "name": "飞书机器人",
                "enabled": True,
                "project_id": "proj-1",
                "app_id": "cli_xxx",
                "app_secret": "secret_xxx",
                "bot_open_id": "ou_bot_1",
            }
        ]
    )

    calls = []
    replies = []

    async def fake_run_project_chat_once(**kwargs):
        calls.append(kwargs)
        raise AssertionError("group text mentioning another user should not enter project chat")

    async def fake_reply_feishu_text(connector, **kwargs):
        replies.append((connector, kwargs))

    monkeypatch.setattr("services.feishu.feishu_bot_service.run_project_chat_once", fake_run_project_chat_once)
    monkeypatch.setattr("services.feishu.feishu_bot_service._reply_feishu_text", fake_reply_feishu_text)

    class Obj:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    event = Obj(
        event=Obj(
            sender=Obj(sender_type="user", sender_id=Obj(open_id="ou_sender_1")),
            message=Obj(
                chat_type="group",
                chat_id="oc_real_group_1",
                thread_id="",
                message_id="om_other_mention_1",
                message_type="text",
                content='{"text":"@_user_2 这条不是给机器人"}',
                mentions=[
                    Obj(
                        key="@_user_2",
                        id=Obj(open_id="ou_someone_else", user_id="u_someone_else", union_id="on_someone_else"),
                    )
                ],
            ),
        )
    )

    import asyncio

    asyncio.run(process_feishu_message_event("conn-feishu-1", event))

    assert calls == []
    assert replies == []
    sessions = store_factory.project_chat_store.list_sessions("proj-1", "tester", limit=20)
    assert sessions == []


def test_feishu_group_text_mentioning_configured_bot_is_processed(tmp_path, monkeypatch):
    from services.feishu.feishu_bot_service import process_feishu_message_event
    from stores.json.project_store import ProjectConfig, ProjectUserMember

    _client, store_factory = _build_project_chat_runtime_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    store_factory.project_store.upsert_user_member(
        ProjectUserMember(project_id="proj-1", username="tester", role="owner")
    )
    store_factory.bot_connector_store.replace_all(
        [
            {
                "id": "conn-feishu-1",
                "platform": "feishu",
                "name": "飞书机器人",
                "enabled": True,
                "project_id": "proj-1",
                "app_id": "cli_xxx",
                "app_secret": "secret_xxx",
                "bot_open_id": "ou_bot_1",
            }
        ]
    )

    calls = []
    replies = []

    class FakeResult:
        content = "收到"

    async def fake_run_project_chat_once(**kwargs):
        calls.append(kwargs)
        return FakeResult()

    async def fake_reply_feishu_text(connector, **kwargs):
        replies.append((connector, kwargs))

    monkeypatch.setattr("services.feishu.feishu_bot_service.run_project_chat_once", fake_run_project_chat_once)
    monkeypatch.setattr("services.feishu.feishu_bot_service._reply_feishu_text", fake_reply_feishu_text)

    class Obj:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    event = Obj(
        event=Obj(
            sender=Obj(sender_type="user", sender_id=Obj(open_id="ou_sender_1")),
            message=Obj(
                chat_type="group",
                chat_id="oc_real_group_1",
                thread_id="",
                message_id="om_bot_mention_1",
                message_type="text",
                content='{"text":"@_user_1 帮我总结一下"}',
                mentions=[
                    Obj(
                        key="@_user_1",
                        id=Obj(open_id="ou_bot_1", user_id="u_bot_1", union_id="on_bot_1"),
                    )
                ],
            ),
        )
    )

    import asyncio

    asyncio.run(process_feishu_message_event("conn-feishu-1", event))

    assert len(calls) == 1
    assert calls[0]["req"].message == "帮我总结一下"
    assert replies[0][1]["message_id"] == "om_bot_mention_1"


def test_feishu_followup_group_text_without_explicit_mention_is_ignored_even_if_mentions_metadata_remains(
    tmp_path,
    monkeypatch,
):
    from services.feishu.feishu_bot_service import process_feishu_message_event
    from stores.json.project_store import ProjectConfig, ProjectUserMember

    _client, store_factory = _build_project_chat_runtime_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    store_factory.project_store.upsert_user_member(
        ProjectUserMember(project_id="proj-1", username="tester", role="owner")
    )
    store_factory.bot_connector_store.replace_all(
        [
            {
                "id": "conn-feishu-1",
                "platform": "feishu",
                "name": "飞书机器人",
                "enabled": True,
                "project_id": "proj-1",
                "app_id": "cli_xxx",
                "app_secret": "secret_xxx",
                "bot_open_id": "ou_bot_1",
            }
        ]
    )

    calls = []
    replies = []

    class FakeResult:
        content = "收到"

    async def fake_run_project_chat_once(**kwargs):
        calls.append(kwargs)
        return FakeResult()

    async def fake_reply_feishu_text(connector, **kwargs):
        replies.append((connector, kwargs))

    monkeypatch.setattr("services.feishu.feishu_bot_service.run_project_chat_once", fake_run_project_chat_once)
    monkeypatch.setattr("services.feishu.feishu_bot_service._reply_feishu_text", fake_reply_feishu_text)

    class Obj:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    first_event = Obj(
        event=Obj(
            sender=Obj(sender_type="user", sender_id=Obj(open_id="ou_sender_1")),
            message=Obj(
                chat_type="group",
                chat_id="oc_real_group_1",
                thread_id="",
                message_id="om_first_mention_1",
                message_type="text",
                content='{"text":"@_user_1 帮我总结一下"}',
                mentions=[Obj(key="@_user_1", id=Obj(open_id="ou_bot_1"))],
            ),
        )
    )

    followup_event = Obj(
        event=Obj(
            sender=Obj(sender_type="user", sender_id=Obj(open_id="ou_sender_1")),
            message=Obj(
                chat_type="group",
                chat_id="oc_real_group_1",
                thread_id="",
                message_id="om_followup_plain_1",
                message_type="text",
                content='{"text":"继续补充这一条，不要再次触发机器人"}',
                mentions=[Obj(key="@_user_1", id=Obj(open_id="ou_bot_1"))],
            ),
        )
    )

    import asyncio

    asyncio.run(process_feishu_message_event("conn-feishu-1", first_event))
    asyncio.run(process_feishu_message_event("conn-feishu-1", followup_event))

    assert len(calls) == 1
    assert calls[0]["req"].message == "帮我总结一下"
    assert len(replies) == 1
    assert replies[0][1]["message_id"] == "om_first_mention_1"


def test_feishu_group_text_with_visible_bot_name_mention_is_processed_without_bot_id(tmp_path, monkeypatch):
    from services.feishu.feishu_bot_service import process_feishu_message_event
    from stores.json.project_store import ProjectConfig, ProjectUserMember

    _client, store_factory = _build_project_chat_runtime_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    store_factory.project_store.upsert_user_member(
        ProjectUserMember(project_id="proj-1", username="tester", role="owner")
    )
    store_factory.bot_connector_store.replace_all(
        [
            {
                "id": "conn-feishu-1",
                "platform": "feishu",
                "name": "飞书机器人",
                "enabled": True,
                "project_id": "proj-1",
                "app_id": "cli_xxx",
                "app_secret": "secret_xxx",
            }
        ]
    )

    calls = []
    replies = []

    class FakeResult:
        content = "收到"

    async def fake_run_project_chat_once(**kwargs):
        calls.append(kwargs)
        return FakeResult()

    async def fake_reply_feishu_text(connector, **kwargs):
        replies.append((connector, kwargs))

    monkeypatch.setattr("services.feishu.feishu_bot_service.run_project_chat_once", fake_run_project_chat_once)
    monkeypatch.setattr("services.feishu.feishu_bot_service._reply_feishu_text", fake_reply_feishu_text)

    class Obj:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    event = Obj(
        event=Obj(
            sender=Obj(sender_type="user", sender_id=Obj(open_id="ou_sender_1")),
            message=Obj(
                chat_type="group",
                chat_id="oc_real_group_1",
                thread_id="",
                message_id="om_visible_name_1",
                message_type="text",
                content='{"text":"@飞书机器人 帮我总结一下今天的讨论"}',
                mentions=[Obj(key="@_user_1", name="飞书机器人")],
            ),
        )
    )

    import asyncio

    asyncio.run(process_feishu_message_event("conn-feishu-1", event))

    assert len(calls) == 1
    assert calls[0]["req"].message == "帮我总结一下今天的讨论"
    assert replies[0][1]["message_id"] == "om_visible_name_1"


def test_feishu_group_text_uses_runtime_bot_identity_when_connector_name_differs(tmp_path, monkeypatch):
    from services.feishu.feishu_bot_service import process_feishu_message_event
    from stores.json.project_store import ProjectConfig, ProjectUserMember

    _client, store_factory = _build_project_chat_runtime_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    store_factory.project_store.upsert_user_member(
        ProjectUserMember(project_id="proj-1", username="tester", role="owner")
    )
    store_factory.bot_connector_store.replace_all(
        [
            {
                "id": "conn-feishu-1",
                "platform": "feishu",
                "name": "个人组织",
                "enabled": True,
                "project_id": "proj-1",
                "app_id": "cli_xxx",
                "app_secret": "secret_xxx",
            }
        ]
    )

    calls = []
    replies = []

    class FakeResult:
        content = "收到"

    async def fake_run_project_chat_once(**kwargs):
        calls.append(kwargs)
        return FakeResult()

    async def fake_reply_feishu_text(connector, **kwargs):
        replies.append((connector, kwargs))

    monkeypatch.setattr("services.feishu.feishu_bot_service.run_project_chat_once", fake_run_project_chat_once)
    monkeypatch.setattr("services.feishu.feishu_bot_service._reply_feishu_text", fake_reply_feishu_text)
    monkeypatch.setattr(
        "services.feishu.feishu_bot_service._get_feishu_runtime_bot_identity",
        lambda connector: {
            "bot_open_id": "ou_runtime_bot_1",
            "bot_name": "jx 飞书 CLI",
        },
    )

    class Obj:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    event = Obj(
        event=Obj(
            sender=Obj(sender_type="user", sender_id=Obj(open_id="ou_sender_1")),
            message=Obj(
                chat_type="group",
                chat_id="oc_real_group_2",
                thread_id="",
                message_id="om_runtime_identity_1",
                message_type="text",
                content='{"text":"@jx 飞书 CLI 你会什么功能"}',
                mentions=[Obj(key="@_user_1", name="jx 飞书 CLI", id=Obj(open_id="ou_runtime_bot_1"))],
            ),
        )
    )

    import asyncio

    asyncio.run(process_feishu_message_event("conn-feishu-1", event))

    assert len(calls) == 1
    assert calls[0]["req"].message == "你会什么功能"
    assert replies[0][1]["message_id"] == "om_runtime_identity_1"


def test_feishu_group_text_with_thread_id_without_mention_is_ignored(tmp_path, monkeypatch):
    from services.feishu.feishu_bot_service import process_feishu_message_event
    from stores.json.project_store import ProjectConfig, ProjectUserMember

    _client, store_factory = _build_project_chat_runtime_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    store_factory.project_store.upsert_user_member(
        ProjectUserMember(project_id="proj-1", username="tester", role="owner")
    )
    store_factory.bot_connector_store.replace_all(
        [
            {
                "id": "conn-feishu-1",
                "platform": "feishu",
                "name": "飞书机器人",
                "enabled": True,
                "project_id": "proj-1",
                "app_id": "cli_xxx",
                "app_secret": "secret_xxx",
            }
        ]
    )

    calls = []
    replies = []

    async def fake_run_project_chat_once(**kwargs):
        calls.append(kwargs)
        raise AssertionError("unmentioned group text with thread id should not enter project chat")

    async def fake_reply_feishu_text(connector, **kwargs):
        replies.append((connector, kwargs))

    monkeypatch.setattr("services.feishu.feishu_bot_service.run_project_chat_once", fake_run_project_chat_once)
    monkeypatch.setattr("services.feishu.feishu_bot_service._reply_feishu_text", fake_reply_feishu_text)

    class Obj:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    event = Obj(
        event=Obj(
            sender=Obj(sender_type="user", sender_id=Obj(open_id="ou_sender_1")),
            message=Obj(
                chat_type="group",
                chat_id="oc_real_group_1",
                thread_id="omt_root_or_thread_id",
                message_id="om_plain_thread_1",
                message_type="text",
                content='{"text":"这是一条普通群聊消息，不应该触发机器人"}',
                mentions=[],
            ),
        )
    )

    import asyncio

    asyncio.run(process_feishu_message_event("conn-feishu-1", event))

    assert calls == []
    assert replies == []
    sessions = store_factory.project_chat_store.list_sessions("proj-1", "tester", limit=20)
    assert sessions == []


def test_feishu_group_image_without_mention_is_ignored(tmp_path, monkeypatch):
    from services.feishu.feishu_bot_service import process_feishu_message_event
    from stores.json.project_store import ProjectConfig, ProjectUserMember

    _client, store_factory = _build_project_chat_runtime_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    store_factory.project_store.upsert_user_member(
        ProjectUserMember(project_id="proj-1", username="tester", role="owner")
    )
    store_factory.bot_connector_store.replace_all(
        [
            {
                "id": "conn-feishu-1",
                "platform": "feishu",
                "name": "飞书机器人",
                "enabled": True,
                "project_id": "proj-1",
                "app_id": "cli_xxx",
                "app_secret": "secret_xxx",
            }
        ]
    )

    calls = []
    replies = []
    downloads = []

    async def fake_run_project_chat_once(**kwargs):
        calls.append(kwargs)
        raise AssertionError("unmentioned group image should not enter project chat")

    async def fake_reply_feishu_text(connector, **kwargs):
        replies.append((connector, kwargs))

    def fake_download_resource(*args, **kwargs):
        downloads.append(kwargs)
        raise AssertionError("unmentioned group image should not be downloaded")

    monkeypatch.setattr("services.feishu.feishu_bot_service.run_project_chat_once", fake_run_project_chat_once)
    monkeypatch.setattr("services.feishu.feishu_bot_service._reply_feishu_text", fake_reply_feishu_text)
    monkeypatch.setattr("services.feishu.feishu_bot_service._download_feishu_message_resource", fake_download_resource)

    class Obj:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    event = Obj(
        event=Obj(
            sender=Obj(sender_type="user", sender_id=Obj(open_id="ou_sender_1")),
            message=Obj(
                chat_type="group",
                chat_id="oc_real_group_1",
                thread_id="",
                message_id="om_group_image_plain_1",
                message_type="image",
                content='{"image_key":"img_v3_group_plain_1"}',
                mentions=[],
            ),
        )
    )

    import asyncio

    asyncio.run(process_feishu_message_event("conn-feishu-1", event))

    assert calls == []
    assert replies == []
    assert downloads == []
    sessions = store_factory.project_chat_store.list_sessions("proj-1", "tester", limit=20)
    assert sessions == []


def test_feishu_listen_all_group_messages_does_not_reply_to_plain_text(tmp_path, monkeypatch):
    from services.feishu.feishu_bot_service import process_feishu_message_event
    from stores.json.project_store import ProjectConfig, ProjectUserMember

    _client, store_factory = _build_project_chat_runtime_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    store_factory.project_store.upsert_user_member(
        ProjectUserMember(project_id="proj-1", username="tester", role="owner")
    )
    store_factory.bot_connector_store.replace_all(
        [
            {
                "id": "conn-feishu-1",
                "platform": "feishu",
                "name": "飞书机器人",
                "enabled": True,
                "project_id": "proj-1",
                "app_id": "cli_xxx",
                "app_secret": "secret_xxx",
                "listen_all_group_messages": True,
                "respond_to_all_group_messages": True,
            }
        ]
    )

    calls = []
    replies = []

    async def fake_run_project_chat_once(**kwargs):
        calls.append(kwargs)
        raise AssertionError("listen_all_group_messages must not mean reply to every group text")

    async def fake_reply_feishu_text(connector, **kwargs):
        replies.append((connector, kwargs))

    monkeypatch.setattr("services.feishu.feishu_bot_service.run_project_chat_once", fake_run_project_chat_once)
    monkeypatch.setattr("services.feishu.feishu_bot_service._reply_feishu_text", fake_reply_feishu_text)

    class Obj:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    event = Obj(
        event=Obj(
            sender=Obj(sender_type="user", sender_id=Obj(open_id="ou_sender_1")),
            message=Obj(
                chat_type="group",
                chat_id="oc_real_group_1",
                thread_id="",
                message_id="om_plain_listen_all_1",
                message_type="text",
                content='{"text":"开启监听也不应该自动回复每一条普通群消息"}',
                mentions=[],
            ),
        )
    )

    import asyncio

    asyncio.run(process_feishu_message_event("conn-feishu-1", event))

    assert calls == []
    assert replies == []
    sessions = store_factory.project_chat_store.list_sessions("proj-1", "tester", limit=20)
    assert sessions == []


def test_feishu_reply_uses_lark_cli_with_configured_identity(monkeypatch):
    from services.feishu import feishu_bot_service as service

    calls = []

    class Completed:
        returncode = 0
        stdout = "{}"
        stderr = ""

    def fake_run(command, **kwargs):
        calls.append({"command": command, **kwargs})
        return Completed()

    monkeypatch.setattr(service.subprocess, "run", fake_run)

    service._reply_feishu_text_with_lark_cli(
        {"reply_identity": "user"},
        message_id="om_message_1",
        content="收到",
        reply_in_thread=True,
    )

    command = calls[0]["command"]
    assert command[:3] == ["lark-cli", "im", "+messages-reply"]
    assert command[command.index("--message-id") + 1] == "om_message_1"
    assert command[command.index("--text") + 1] == "收到"
    assert command[command.index("--as") + 1] == "user"
    assert command[command.index("--idempotency-key") + 1] == "feishu-reply-om_message_1"
    assert "--reply-in-thread" in command


def test_feishu_bot_reply_uses_open_api_without_lark_cli(monkeypatch):
    from services.feishu import feishu_bot_service as service

    calls = []

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    def fake_run(*args, **kwargs):
        raise AssertionError("bot reply should not call lark-cli")

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        if url.endswith("/tenant_access_token/internal"):
            return FakeResponse({"code": 0, "tenant_access_token": "tenant-token"})
        if url.endswith("/im/v1/messages/om_message_1/reply"):
            return FakeResponse({"code": 0, "data": {"message_id": "om_reply_1"}})
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(service.subprocess, "run", fake_run)
    monkeypatch.setattr(service.requests, "post", fake_post)

    import asyncio

    asyncio.run(service._reply_feishu_text(
        {"reply_identity": "bot", "app_id": "cli_xxx", "app_secret": "secret_xxx"},
        message_id="om_message_1",
        content="收到",
        reply_in_thread=True,
    ))

    reply_kwargs = calls[1][1]
    assert reply_kwargs["headers"]["Authorization"] == "Bearer tenant-token"
    assert reply_kwargs["params"]["uuid"] == "feishu-reply-om_message_1"
    assert reply_kwargs["json"] == {
        "msg_type": "text",
        "content": json.dumps({"text": "收到"}, ensure_ascii=False),
        "reply_in_thread": True,
    }


def test_feishu_bot_reply_open_api_error_is_clear(monkeypatch):
    from services.feishu import feishu_bot_service as service

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    def fake_post(url, **kwargs):
        if url.endswith("/tenant_access_token/internal"):
            return FakeResponse({"code": 0, "tenant_access_token": "tenant-token"})
        if url.endswith("/im/v1/messages/om_message_1/reply"):
            return FakeResponse({"code": 230001, "msg": "message not found"})
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(service.requests, "post", fake_post)

    with pytest.raises(RuntimeError, match="message not found"):
        service._reply_feishu_text_with_open_api(
            {"reply_identity": "bot", "app_id": "cli_xxx", "app_secret": "secret_xxx"},
            message_id="om_message_1",
            content="收到",
        )


def test_feishu_non_text_image_message_routes_resource_to_model_context(tmp_path, monkeypatch):
    from services.feishu.feishu_bot_service import process_feishu_message_event
    from stores.json.project_store import ProjectConfig, ProjectUserMember

    client, store_factory = _build_project_chat_runtime_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    store_factory.project_store.upsert_user_member(
        ProjectUserMember(project_id="proj-1", username="tester", role="owner")
    )
    store_factory.bot_connector_store.replace_all(
        [
            {
                "id": "conn-feishu-1",
                "platform": "feishu",
                "name": "飞书机器人",
                "enabled": True,
                "project_id": "",
                "app_id": "cli_xxx",
                "app_secret": "secret_xxx",
                "bot_open_id": "ou_bot_1",
            }
        ]
    )
    create_response = client.post(
        "/api/projects/proj-1/chat/sessions",
        json={
            "title": "飞书群：产品研发群",
            "source_context": {
                "source_type": "group_message",
                "platform": "feishu",
                "connector_id": "conn-feishu-1",
                "external_chat_id": "oc_real_group_1",
                "external_chat_name": "产品研发群",
            },
        },
    )
    assert create_response.status_code == 200
    session = create_response.json()["session"]

    calls = []
    replies = []

    class FakeResult:
        content = "已收到图片，会结合上下文处理。"

    async def fake_run_project_chat_once(**kwargs):
        calls.append(kwargs)
        return FakeResult()

    async def fake_reply_feishu_text(connector, **kwargs):
        replies.append((connector, kwargs))

    def fake_download_resource(connector, **kwargs):
        from services.feishu.feishu_bot_service import _feishu_resource_root

        image_path = _feishu_resource_root() / "conn-feishu-1" / "om_image_1" / "img_v3_1.png"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image_path.write_bytes(b"fake image")
        return {
            "file_key": kwargs["file_key"],
            "type": "image",
            "filename": "img_v3_1.png",
            "path": str(image_path),
            "url": "/api/bot-events/feishu/conn-feishu-1/resources/om_image_1/img_v3_1.png",
            "content_type": "image/png",
        }

    monkeypatch.setattr(
        "services.feishu.feishu_bot_service.run_project_chat_once",
        fake_run_project_chat_once,
    )
    monkeypatch.setattr(
        "services.feishu.feishu_bot_service._reply_feishu_text",
        fake_reply_feishu_text,
    )
    monkeypatch.setattr(
        "services.feishu.feishu_bot_service._download_feishu_message_resource",
        fake_download_resource,
    )
    class Obj:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    event = Obj(
        event=Obj(
            sender=Obj(sender_type="user", sender_id=Obj(open_id="ou_sender_1")),
            message=Obj(
                chat_type="group",
                chat_id="oc_real_group_1",
                thread_id="",
                message_id="om_image_1",
                message_type="image",
                content='{"image_key":"img_v3_1"}',
                mentions=[Obj(key="@_user_1", id=Obj(open_id="ou_bot_1"))],
            ),
        )
    )

    import asyncio

    asyncio.run(process_feishu_message_event("conn-feishu-1", event))

    assert len(calls) == 1
    req = calls[0]["req"]
    assert req.message == "用户发送了图片。"
    assert req.images == ["/api/bot-events/feishu/conn-feishu-1/resources/om_image_1/img_v3_1.png"]
    assert req.source_context["image_urls"] == [
        "/api/bot-events/feishu/conn-feishu-1/resources/om_image_1/img_v3_1.png",
    ]
    assert req.source_context["message_resources"] == [
        {"file_key": "img_v3_1", "type": "image", "label": "图片", "message_id": "om_image_1"}
    ]
    image_path = Path(req.source_context["attachment_files"][0]["path"])
    assert image_path.name == "img_v3_1.png"
    assert "message_resources" in req.system_prompt
    assert "lark-im" in req.system_prompt
    assert replies[0][1]["message_id"] == "om_image_1"
    assert not image_path.exists()


def test_feishu_group_follow_up_resource_message_continues_open_workflow_without_new_mention(tmp_path, monkeypatch):
    from stores.json.project_chat_store import ProjectChatMessage
    from services.feishu.feishu_bot_service import process_feishu_message_event
    from stores.json.project_store import ProjectConfig, ProjectUserMember

    client, store_factory = _build_project_chat_runtime_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    store_factory.project_store.upsert_user_member(
        ProjectUserMember(project_id="proj-1", username="tester", role="owner")
    )
    store_factory.bot_connector_store.replace_all(
        [
            {
                "id": "conn-feishu-1",
                "platform": "feishu",
                "name": "飞书机器人",
                "enabled": True,
                "project_id": "",
                "app_id": "cli_xxx",
                "app_secret": "secret_xxx",
                "bot_open_id": "ou_bot_1",
            }
        ]
    )
    create_response = client.post(
        "/api/projects/proj-1/chat/sessions",
        json={
            "title": "飞书群：产品研发群",
            "source_context": {
                "source_type": "group_message",
                "platform": "feishu",
                "connector_id": "conn-feishu-1",
                "external_chat_id": "oc_real_group_1",
                "external_chat_name": "产品研发群",
            },
        },
    )
    assert create_response.status_code == 200
    session = create_response.json()["session"]
    store_factory.project_chat_store.append_message(
        ProjectChatMessage(
            id="om_prev_bug_1",
            project_id="proj-1",
            username="tester",
            role="user",
            content="@飞书机器人 记录一个bug 登录页白屏",
            chat_session_id=session["id"],
            source_context={
                "platform": "feishu",
                "sender_id": "ou_sender_1",
                "connector_id": "conn-feishu-1",
                "external_chat_id": "oc_real_group_1",
                "external_chat_name": "产品研发群",
                "source_type": "group_message",
            },
        )
    )
    store_factory.project_chat_store.append_message(
        ProjectChatMessage(
            id="bot_prev_bug_1",
            project_id="proj-1",
            username="tester",
            role="assistant",
            content="请继续补充截图或附件，我会继续处理。",
            chat_session_id=session["id"],
            source_context={
                "platform": "feishu",
                "connector_id": "conn-feishu-1",
                "external_chat_id": "oc_real_group_1",
                "external_chat_name": "产品研发群",
                "source_type": "group_message",
                "assistant_workflow": {
                    "primary_task_type": "bugfix",
                    "task_types": ["bugfix"],
                    "execution_mode": "collect_then_confirm",
                    "confirmation_policy": "once_before_write",
                    "requires_tooling": True,
                    "status": "collecting",
                },
            },
        )
    )

    calls = []
    replies = []

    class FakeResult:
        content = "已收到图片，会继续补充到当前 bug。"

    async def fake_run_project_chat_once(**kwargs):
        calls.append(kwargs)
        return FakeResult()

    async def fake_reply_feishu_text(connector, **kwargs):
        replies.append((connector, kwargs))

    def fake_download_resource(connector, **kwargs):
        from services.feishu.feishu_bot_service import _feishu_resource_root

        image_path = _feishu_resource_root() / "conn-feishu-1" / "om_image_followup_1" / "img_v3_followup_1.png"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image_path.write_bytes(b"fake image")
        return {
            "file_key": kwargs["file_key"],
            "type": "image",
            "filename": "img_v3_followup_1.png",
            "path": str(image_path),
            "url": "/api/bot-events/feishu/conn-feishu-1/resources/om_image_followup_1/img_v3_followup_1.png",
            "content_type": "image/png",
        }

    monkeypatch.setattr("services.feishu.feishu_bot_service.run_project_chat_once", fake_run_project_chat_once)
    monkeypatch.setattr("services.feishu.feishu_bot_service._reply_feishu_text", fake_reply_feishu_text)
    monkeypatch.setattr("services.feishu.feishu_bot_service._download_feishu_message_resource", fake_download_resource)

    class Obj:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    event = Obj(
        event=Obj(
            sender=Obj(sender_type="user", sender_id=Obj(open_id="ou_sender_1")),
            message=Obj(
                chat_type="group",
                chat_id="oc_real_group_1",
                thread_id="",
                message_id="om_image_followup_1",
                message_type="image",
                content='{"image_key":"img_v3_followup_1"}',
                mentions=[],
            ),
        )
    )

    import asyncio

    asyncio.run(process_feishu_message_event("conn-feishu-1", event))

    assert len(calls) == 1
    assert calls[0]["req"].message == "用户发送了图片。"
    assert replies[0][1]["message_id"] == "om_image_followup_1"


def test_feishu_text_redownloads_recent_image_resource_for_model_context(tmp_path, monkeypatch):
    from services.feishu.feishu_bot_service import process_feishu_message_event
    from stores.json.project_store import ProjectConfig, ProjectUserMember

    client, store_factory = _build_project_chat_runtime_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    store_factory.project_store.upsert_user_member(
        ProjectUserMember(project_id="proj-1", username="tester", role="owner")
    )
    store_factory.bot_connector_store.replace_all(
        [
            {
                "id": "conn-feishu-1",
                "platform": "feishu",
                "name": "飞书机器人",
                "enabled": True,
                "project_id": "",
                "app_id": "cli_xxx",
                "app_secret": "secret_xxx",
                "bot_open_id": "ou_bot_1",
            }
        ]
    )
    create_response = client.post(
        "/api/projects/proj-1/chat/sessions",
        json={
            "title": "飞书群：数转CRM技术小组",
            "source_context": {
                "source_type": "group_message",
                "platform": "feishu",
                "connector_id": "conn-feishu-1",
                "external_chat_id": "oc_real_group_1",
                "external_chat_name": "数转CRM技术小组",
            },
        },
    )
    assert create_response.status_code == 200
    session = create_response.json()["session"]
    projects_router = __import__("routers.projects", fromlist=["_append_chat_record"])
    projects_router._append_chat_record(
        project_id="proj-1",
        username="tester",
        role="user",
        content="（飞书发送了图片：/api/bot-events/feishu/conn-feishu-1/resources/om_image_1/img_v3_1.png）",
        message_id="om_image_1",
        chat_session_id=session["id"],
        images=["/api/bot-events/feishu/conn-feishu-1/resources/om_image_1/img_v3_1.png"],
        source_context={
            "source_type": "group_message",
            "platform": "feishu",
            "connector_id": "conn-feishu-1",
            "external_chat_id": "oc_real_group_1",
            "external_chat_name": "数转CRM技术小组",
            "external_message_id": "om_image_1",
            "thread_key": "feishu:conn-feishu-1:chat:oc_real_group_1",
            "message_resources": [
                {
                    "message_id": "om_image_1",
                    "file_key": "img_v3_1",
                    "type": "image",
                    "label": "图片",
                }
            ],
        },
    )

    calls = []
    replies = []
    image_path = tmp_path / "redownloaded.png"

    class FakeResult:
        content = "已收到，会结合最近图片处理。"

    async def fake_run_project_chat_once(**kwargs):
        calls.append(kwargs)
        return FakeResult()

    async def fake_reply_feishu_text(connector, **kwargs):
        replies.append((connector, kwargs))

    def fake_download_resource(connector, **kwargs):
        assert kwargs["message_id"] == "om_image_1"
        assert kwargs["file_key"] == "img_v3_1"
        image_path.write_bytes(b"fake image")
        return {
            "file_key": kwargs["file_key"],
            "type": "image",
            "filename": "img_v3_1.png",
            "path": str(image_path),
            "url": "/api/bot-events/feishu/conn-feishu-1/resources/om_image_1/img_v3_1.png",
            "content_type": "image/png",
        }

    monkeypatch.setattr("services.feishu.feishu_bot_service.run_project_chat_once", fake_run_project_chat_once)
    monkeypatch.setattr("services.feishu.feishu_bot_service._reply_feishu_text", fake_reply_feishu_text)
    monkeypatch.setattr("services.feishu.feishu_bot_service._download_feishu_message_resource", fake_download_resource)

    class Obj:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    event = Obj(
        event=Obj(
            sender=Obj(sender_type="user", sender_id=Obj(open_id="ou_sender_1")),
            message=Obj(
                chat_type="group",
                chat_id="oc_real_group_1",
                thread_id="",
                message_id="om_append_1",
                message_type="text",
                content='{"text":"@_user_1 追加"}',
                mentions=[Obj(key="@_user_1", id=Obj(open_id="ou_bot_1"))],
            ),
        )
    )

    import asyncio

    asyncio.run(process_feishu_message_event("conn-feishu-1", event))

    assert len(calls) == 1
    req = calls[0]["req"]
    assert req.images == ["/api/bot-events/feishu/conn-feishu-1/resources/om_image_1/img_v3_1.png"]
    assert req.source_context["attachment_files"][0]["path"] == str(image_path)
    assert req.source_context["attachment_files"][0]["file_key"] == "img_v3_1"
    assert req.source_context["message_resources"][0]["message_id"] == "om_image_1"
    stored = store_factory.project_chat_store.list_messages(
        "proj-1",
        "tester",
        limit=10,
        chat_session_id=session["id"],
    )
    assert stored[0].source_context["message_resources"][0]["file_key"] == "img_v3_1"
    assert replies[0][1]["message_id"] == "om_append_1"
    assert "已收到" in replies[0][1]["content"]


def test_feishu_text_recovers_recent_image_resource_from_previous_reply_text(tmp_path, monkeypatch):
    from services.feishu.feishu_bot_service import process_feishu_message_event
    from stores.json.project_store import ProjectConfig, ProjectUserMember

    client, store_factory = _build_project_chat_runtime_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    store_factory.project_store.upsert_user_member(
        ProjectUserMember(project_id="proj-1", username="tester", role="owner")
    )
    store_factory.bot_connector_store.replace_all(
        [
            {
                "id": "conn-feishu-1",
                "platform": "feishu",
                "name": "飞书机器人",
                "enabled": True,
                "project_id": "",
                "app_id": "cli_xxx",
                "app_secret": "secret_xxx",
                "bot_open_id": "ou_bot_1",
            }
        ]
    )
    create_response = client.post(
        "/api/projects/proj-1/chat/sessions",
        json={
            "title": "飞书私聊：飞书私聊-1a7e3653",
            "source_context": {
                "source_type": "private_message",
                "platform": "feishu",
                "connector_id": "conn-feishu-1",
                "external_chat_id": "oc_private_1",
                "external_chat_name": "飞书私聊-1a7e3653",
            },
        },
    )
    assert create_response.status_code == 200
    session = create_response.json()["session"]
    projects_router = __import__("routers.projects", fromlist=["_append_chat_record"])
    projects_router._append_chat_record(
        project_id="proj-1",
        username="tester",
        role="assistant",
        content=(
            "已确认可用图片资源：\n"
            "- 消息 ID：`om_x100b6f0bae692ca4c34185843396674`\n"
            "- 图片 key：`img_v3_0211l_d971ac95-7324-4776-b88c-c2fd54844bcg`"
        ),
        message_id="bot-resource-summary",
        chat_session_id=session["id"],
        source_context={
            "source_type": "private_message",
            "platform": "feishu",
            "connector_id": "conn-feishu-1",
            "external_chat_id": "oc_private_1",
            "thread_key": "feishu:conn-feishu-1:chat:oc_private_1",
        },
    )

    calls = []
    image_path = tmp_path / "recovered.png"

    class FakeResult:
        content = "已收到，会使用刚才那张图片。"

    async def fake_run_project_chat_once(**kwargs):
        calls.append(kwargs)
        return FakeResult()

    async def fake_reply_feishu_text(connector, **kwargs):
        return None

    def fake_download_resource(connector, **kwargs):
        assert kwargs["message_id"] == "om_x100b6f0bae692ca4c34185843396674"
        assert kwargs["file_key"] == "img_v3_0211l_d971ac95-7324-4776-b88c-c2fd54844bcg"
        image_path.write_bytes(b"fake image")
        return {
            "file_key": kwargs["file_key"],
            "type": "image",
            "filename": "recovered.png",
            "path": str(image_path),
            "url": "/api/bot-events/feishu/conn-feishu-1/resources/om_x100b6f0bae692ca4c34185843396674/recovered.png",
            "content_type": "image/png",
        }

    monkeypatch.setattr("services.feishu.feishu_bot_service.run_project_chat_once", fake_run_project_chat_once)
    monkeypatch.setattr("services.feishu.feishu_bot_service._reply_feishu_text", fake_reply_feishu_text)
    monkeypatch.setattr("services.feishu.feishu_bot_service._download_feishu_message_resource", fake_download_resource)

    class Obj:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    event = Obj(
        event=Obj(
            sender=Obj(sender_type="user", sender_id=Obj(open_id="ou_sender_1")),
            message=Obj(
                chat_type="p2p",
                chat_id="oc_private_1",
                thread_id="",
                message_id="om_use_previous_image",
                message_type="text",
                content='{"text":"用这个图片继续记录"}',
                mentions=[],
            ),
        )
    )

    import asyncio

    asyncio.run(process_feishu_message_event("conn-feishu-1", event))

    assert len(calls) == 1
    req = calls[0]["req"]
    assert req.source_context["attachment_files"][0]["path"] == str(image_path)
    assert req.source_context["message_resources"][0]["message_id"] == "om_x100b6f0bae692ca4c34185843396674"
    assert req.source_context["message_resources"][0]["file_key"] == "img_v3_0211l_d971ac95-7324-4776-b88c-c2fd54844bcg"


def test_feishu_resource_ref_text_parser_keeps_message_id_file_key_pairs():
    from services.feishu.feishu_bot_service import _extract_feishu_resource_refs_from_text

    refs = _extract_feishu_resource_refs_from_text(
        "【已定位图片】\n"
        "- 消息 ID：`om_first_message`\n"
        "- 图片 key：`img_v3_first_key`\n\n"
        "【另一张附件】\n"
        "- 消息 ID：`om_second_message`\n"
        "- 附件 key：`file_v3_second_key`\n"
    )

    assert refs == [
        {
            "message_id": "om_first_message",
            "file_key": "img_v3_first_key",
            "type": "image",
            "label": "图片",
        },
        {
            "message_id": "om_second_message",
            "file_key": "file_v3_second_key",
            "type": "file",
            "label": "附件",
        },
    ]


def test_feishu_resource_ref_text_parser_ignores_unpaired_keys():
    from services.feishu.feishu_bot_service import _extract_feishu_resource_refs_from_text

    refs = _extract_feishu_resource_refs_from_text(
        "图片 key：`img_v3_old_key`\n\n"
        "【已定位图片】\n"
        "- 消息 ID：`om_current_message`\n"
        "- 图片 key：`img_v3_current_key`\n"
    )

    assert refs == [
        {
            "message_id": "om_current_message",
            "file_key": "img_v3_current_key",
            "type": "image",
            "label": "图片",
        }
    ]


def test_download_feishu_message_resource_reports_feishu_error_body(tmp_path, monkeypatch):
    from services.feishu import feishu_bot_service

    class FakeResponse:
        status_code = 400
        headers = {"Content-Type": "application/json"}
        text = '{"code":234002,"msg":"file_key does not match message_id"}'
        content = b""

        def json(self):
            return {"code": 234002, "msg": "file_key does not match message_id"}

    def fake_get(*args, **kwargs):
        return FakeResponse()

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    monkeypatch.setattr(feishu_bot_service, "_get_feishu_tenant_access_token", lambda connector: "tenant-token")
    monkeypatch.setattr(requests, "get", fake_get)

    with pytest.raises(RuntimeError) as exc_info:
        feishu_bot_service._download_feishu_message_resource(
            {"id": "conn-feishu-1"},
            connector_id="conn-feishu-1",
            message_id="om_current_message",
            file_key="img_v3_old_key",
            resource_type="image",
        )

    message = str(exc_info.value)
    assert "HTTP 400" in message
    assert "message_id=om_current_message" in message
    assert "file_key=img_v3_old_key" in message
    assert "code=234002" in message
    assert "file_key does not match message_id" in message


def test_feishu_text_with_image_and_target_title_routes_to_model_with_resource_context(tmp_path, monkeypatch):
    from services.feishu.feishu_bot_service import process_feishu_message_event
    from stores.json.project_store import ProjectConfig, ProjectUserMember

    client, store_factory = _build_project_chat_runtime_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    store_factory.project_store.upsert_user_member(
        ProjectUserMember(project_id="proj-1", username="tester", role="owner")
    )
    store_factory.bot_connector_store.replace_all(
        [
            {
                "id": "conn-feishu-1",
                "platform": "feishu",
                "name": "飞书机器人",
                "enabled": True,
                "project_id": "",
                "app_id": "cli_xxx",
                "app_secret": "secret_xxx",
                "bot_open_id": "ou_bot_1",
            }
        ]
    )
    create_response = client.post(
        "/api/projects/proj-1/chat/sessions",
        json={
            "title": "飞书群：数转CRM技术小组",
            "source_context": {
                "source_type": "group_message",
                "platform": "feishu",
                "connector_id": "conn-feishu-1",
                "external_chat_id": "oc_real_group_1",
                "external_chat_name": "数转CRM技术小组",
            },
        },
    )
    assert create_response.status_code == 200

    calls = []
    replies = []
    image_path = tmp_path / "img_v3_1.png"
    image_path.write_bytes(b"fake image")

    class FakeResult:
        content = "已收到，会结合这张图片和标题上下文处理。"

    async def fake_run_project_chat_once(**kwargs):
        calls.append(kwargs)
        return FakeResult()

    async def fake_reply_feishu_text(connector, **kwargs):
        replies.append((connector, kwargs))

    def fake_download_resource(connector, **kwargs):
        return {
            "file_key": kwargs["file_key"],
            "type": "image",
            "filename": "img_v3_1.png",
            "path": str(image_path),
            "url": "/api/bot-events/feishu/conn-feishu-1/resources/om_post_1/img_v3_1.png",
            "content_type": "image/png",
        }

    monkeypatch.setattr("services.feishu.feishu_bot_service.run_project_chat_once", fake_run_project_chat_once)
    monkeypatch.setattr("services.feishu.feishu_bot_service._reply_feishu_text", fake_reply_feishu_text)
    monkeypatch.setattr("services.feishu.feishu_bot_service._download_feishu_message_resource", fake_download_resource)

    class Obj:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    post_content = {
        "title": "",
        "content": [
            [
                {"tag": "img", "image_key": "img_post_1"},
                {"tag": "text", "text": "这个图片追加到 标题是 ‘Git 代码仓库无法提交/推送，提示无权限’ 的数据里面"},
            ]
        ],
    }
    event = Obj(
        event=Obj(
            sender=Obj(sender_type="user", sender_id=Obj(open_id="ou_sender_1")),
            message=Obj(
                chat_type="group",
                chat_id="oc_real_group_1",
                thread_id="",
                message_id="om_post_1",
                message_type="post",
                content=json.dumps(post_content, ensure_ascii=False),
                mentions=[Obj(key="@_user_1", id=Obj(open_id="ou_bot_1"))],
            ),
        )
    )

    import asyncio

    asyncio.run(process_feishu_message_event("conn-feishu-1", event))

    assert len(calls) == 1
    req = calls[0]["req"]
    assert req.message == "这个图片追加到 标题是 ‘Git 代码仓库无法提交/推送，提示无权限’ 的数据里面"
    assert req.images == ["/api/bot-events/feishu/conn-feishu-1/resources/om_post_1/img_v3_1.png"]
    assert req.source_context["message_resources"] == [
        {"file_key": "img_post_1", "type": "image", "label": "图片", "message_id": "om_post_1"}
    ]
    assert req.source_context["attachment_files"][0]["path"] == str(image_path)
    assert replies[0][1]["message_id"] == "om_post_1"
    assert "结合这张图片" in replies[0][1]["content"]


def test_feishu_post_message_with_image_routes_text_to_project_chat(tmp_path, monkeypatch):
    from services.feishu.feishu_bot_service import process_feishu_message_event
    from stores.json.project_store import ProjectConfig, ProjectUserMember

    client, store_factory = _build_project_chat_runtime_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    store_factory.project_store.upsert_user_member(
        ProjectUserMember(project_id="proj-1", username="tester", role="owner")
    )
    store_factory.bot_connector_store.replace_all(
        [
            {
                "id": "conn-feishu-1",
                "platform": "feishu",
                "name": "飞书机器人",
                "enabled": True,
                "project_id": "",
                "app_id": "cli_xxx",
                "app_secret": "secret_xxx",
                "bot_open_id": "ou_bot_1",
            }
        ]
    )
    create_response = client.post(
        "/api/projects/proj-1/chat/sessions",
        json={
            "title": "飞书群：产品研发群",
            "source_context": {
                "source_type": "group_message",
                "platform": "feishu",
                "connector_id": "conn-feishu-1",
                "external_chat_id": "oc_real_group_1",
                "external_chat_name": "产品研发群",
            },
        },
    )
    assert create_response.status_code == 200
    session = create_response.json()["session"]

    calls = []
    replies = []
    image_path = tmp_path / "post-image.png"
    image_path.write_bytes(b"fake image")

    class FakeResult:
        content = "已收到图文内容"

    async def fake_run_project_chat_once(**kwargs):
        calls.append(kwargs)
        return FakeResult()

    async def fake_reply_feishu_text(connector, **kwargs):
        replies.append((connector, kwargs))

    def fake_download_resource(connector, **kwargs):
        return {
            "file_key": kwargs["file_key"],
            "type": "image",
            "filename": "post-image.png",
            "path": str(image_path),
            "url": "/api/bot-events/feishu/conn-feishu-1/resources/om_post_1/post-image.png",
            "content_type": "image/png",
        }

    monkeypatch.setattr(
        "services.feishu.feishu_bot_service.run_project_chat_once",
        fake_run_project_chat_once,
    )
    monkeypatch.setattr(
        "services.feishu.feishu_bot_service._reply_feishu_text",
        fake_reply_feishu_text,
    )
    monkeypatch.setattr(
        "services.feishu.feishu_bot_service._download_feishu_message_resource",
        fake_download_resource,
    )

    class Obj:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    post_content = {
        "title": "",
        "content": [
            [
                {"tag": "at", "user_id": "ou_bot", "user_name": "飞书 CLI"},
                {"tag": "text", "text": "1. 标题 CRM 客户详情页点击图片上传按钮无响应"},
                {"tag": "img", "image_key": "img_post_1"},
            ]
        ],
    }
    event = Obj(
        event=Obj(
            sender=Obj(sender_type="user", sender_id=Obj(open_id="ou_sender_1")),
            message=Obj(
                chat_type="group",
                chat_id="oc_real_group_1",
                thread_id="",
                message_id="om_post_1",
                message_type="post",
                content=json.dumps(post_content, ensure_ascii=False),
                mentions=[Obj(key="@_user_1", id=Obj(open_id="ou_bot_1"))],
            ),
        )
    )

    import asyncio

    asyncio.run(process_feishu_message_event("conn-feishu-1", event))

    assert len(calls) == 1
    req = calls[0]["req"]
    assert req.chat_session_id == session["id"]
    assert req.message == "1. 标题 CRM 客户详情页点击图片上传按钮无响应"
    assert req.images == ["/api/bot-events/feishu/conn-feishu-1/resources/om_post_1/post-image.png"]
    assert req.source_context["attachment_files"][0]["path"] == str(image_path)
    assert replies[0][1]["message_id"] == "om_post_1"


def test_feishu_text_message_recursively_extracts_nested_image_and_file_resources(tmp_path, monkeypatch):
    from services.feishu.feishu_bot_service import process_feishu_message_event
    from stores.json.project_store import ProjectConfig, ProjectUserMember

    client, store_factory = _build_project_chat_runtime_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    store_factory.project_store.upsert_user_member(
        ProjectUserMember(project_id="proj-1", username="tester", role="owner")
    )
    store_factory.bot_connector_store.replace_all(
        [
            {
                "id": "conn-feishu-1",
                "platform": "feishu",
                "name": "飞书机器人",
                "enabled": True,
                "project_id": "",
                "app_id": "cli_xxx",
                "app_secret": "secret_xxx",
            }
        ]
    )
    create_response = client.post(
        "/api/projects/proj-1/chat/sessions",
        json={
            "title": "飞书私聊：飞书私聊-1a7e3653",
            "source_context": {
                "source_type": "private_message",
                "platform": "feishu",
                "connector_id": "conn-feishu-1",
                "external_chat_id": "oc_private_1",
                "external_chat_name": "飞书私聊-1a7e3653",
            },
        },
    )
    assert create_response.status_code == 200

    calls = []
    replies = []
    download_calls = []

    class FakeResult:
        content = "已收到，会结合图片和附件处理。"

    async def fake_run_project_chat_once(**kwargs):
        calls.append(kwargs)
        return FakeResult()

    async def fake_reply_feishu_text(connector, **kwargs):
        replies.append((connector, kwargs))

    def fake_download_resource(connector, **kwargs):
        download_calls.append(kwargs)
        suffix = ".png" if kwargs["resource_type"] == "image" else ".txt"
        resource_path = tmp_path / f"{kwargs['file_key']}{suffix}"
        resource_path.write_bytes(b"fake resource")
        return {
            "file_key": kwargs["file_key"],
            "type": kwargs["resource_type"],
            "filename": resource_path.name,
            "path": str(resource_path),
            "url": f"/api/bot-events/feishu/conn-feishu-1/resources/om_mixed_1/{resource_path.name}",
            "content_type": "image/png" if kwargs["resource_type"] == "image" else "text/plain",
        }

    monkeypatch.setattr("services.feishu.feishu_bot_service.run_project_chat_once", fake_run_project_chat_once)
    monkeypatch.setattr("services.feishu.feishu_bot_service._reply_feishu_text", fake_reply_feishu_text)
    monkeypatch.setattr("services.feishu.feishu_bot_service._download_feishu_message_resource", fake_download_resource)

    class Obj:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    content = {
        "text": "用这个图片和附件记录问题",
        "rich_content": {
            "blocks": [
                {"tag": "img", "imageKey": "img_nested_1"},
                {"tag": "file", "file_key": "file_nested_1"},
            ]
        },
    }
    event = Obj(
        event=Obj(
            sender=Obj(sender_type="user", sender_id=Obj(open_id="ou_sender_1")),
            message=Obj(
                chat_type="p2p",
                chat_id="oc_private_1",
                thread_id="",
                message_id="om_mixed_1",
                message_type="text",
                content=json.dumps(content, ensure_ascii=False),
                mentions=[],
            ),
        )
    )

    import asyncio

    asyncio.run(process_feishu_message_event("conn-feishu-1", event))

    assert [item["file_key"] for item in download_calls] == ["img_nested_1", "file_nested_1"]
    assert [item["resource_type"] for item in download_calls] == ["image", "file"]
    assert len(calls) == 1
    req = calls[0]["req"]
    assert req.message == "用这个图片和附件记录问题"
    assert req.images == ["/api/bot-events/feishu/conn-feishu-1/resources/om_mixed_1/img_nested_1.png"]
    assert req.source_context["message_resources"] == [
        {"file_key": "img_nested_1", "type": "image", "label": "图片", "message_id": "om_mixed_1"},
        {"file_key": "file_nested_1", "type": "file", "label": "附件", "message_id": "om_mixed_1"},
    ]
    assert [Path(item["path"]).name for item in req.source_context["attachment_files"]] == [
        "img_nested_1.png",
        "file_nested_1.txt",
    ]
    assert replies[0][1]["message_id"] == "om_mixed_1"


def _is_bitable_upload_all_call(args):
    return args[:3] == ["api", "POST", "/open-apis/drive/v1/medias/upload_all"]


def _is_bitable_record_put_call(args):
    return (
        len(args) >= 3
        and args[:2] == ["api", "PUT"]
        and str(args[2]).startswith("/open-apis/bitable/v1/apps/")
        and "/records/" in str(args[2])
    )


def _is_bitable_record_upload_attachment_call(args):
    return args[:2] == ["base", "+record-upload-attachment"]


def _cli_json_arg(args, flag):
    return json.loads(args[args.index(flag) + 1])


def test_feishu_archive_attachment_append_updates_latest_bitable_record(tmp_path, monkeypatch):
    from core import config as core_config
    from services.feishu import feishu_archive_writer_service as writer

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()
    archive_path = tmp_path / "api-data" / "feishu-archive-docs.json"
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.write_text(
        json.dumps(
            {
                "version": 1,
                "archives": {
                    "archive-1": {
                        "archive_key": "archive-1",
                        "connector_id": "conn-feishu-1",
                        "external_chat_id": "oc_real_group_1",
                        "writer_type": "bitable",
                        "writer_mode": "lark_cli_user",
                        "app_token": "app_1",
                        "table_id": "tbl_1",
                        "record_id": "rec_1",
                        "document_title": "bug文档【飞书机器人】",
                        "last_attachment_text": "",
                        "updated_at": "2026-04-26T10:00:00+00:00",
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    commands = []
    upload_cwds = []
    image_path = tmp_path / "image.png"
    image_path.write_bytes(b"fake image")

    def fake_run_lark_cli_json(args, *, timeout=90, cwd=None):
        commands.append(args)
        if _is_bitable_record_upload_attachment_call(args):
            upload_cwds.append(cwd)
            return {"record_id": "rec_1", "updated": True}
        if args[:2] == ["base", "+field-list"]:
            return {
                "data": {
                    "fields": [
                        {"name": "归档时间", "type": "text"},
                        {"name": "类型", "type": "text"},
                        {"name": "标题", "type": "text"},
                        {"name": "摘要", "type": "text"},
                        {"name": "详细内容", "type": "text"},
                        {"name": "优先级", "type": "text"},
                        {"name": "负责人", "type": "text"},
                        {"name": "提出人", "type": "text"},
                        {"name": "来源群", "type": "text"},
                        {"name": "图片/附件", "type": "text"},
                        {"name": "图片附件", "type": "attachment"},
                        {"name": "消息链接", "type": "text"},
                        {"name": "聊天记录", "type": "text"},
                    ]
                }
            }
        return {"record_id": "rec_1", "updated": True}

    monkeypatch.setattr(writer, "_run_lark_cli_json", fake_run_lark_cli_json)

    result = writer.append_feishu_archive_attachments(
        source_context={
            "connector_id": "conn-feishu-1",
            "external_chat_id": "oc_real_group_1",
            "external_message_id": "om_image_1",
        },
        attachment_urls=["/api/bot-events/feishu/conn-feishu-1/resources/om_image_1/image.png"],
        attachment_files=[{"path": str(image_path), "filename": "image.png"}],
    )

    assert result["status"] == "updated"
    assert result["uploaded_count"] == 1
    assert commands[0][:2] == ["base", "+field-list"]
    assert _is_bitable_record_upload_attachment_call(commands[1])
    assert commands[1][commands[1].index("--base-token") + 1] == "app_1"
    assert commands[1][commands[1].index("--table-id") + 1] == "tbl_1"
    assert commands[1][commands[1].index("--record-id") + 1] == "rec_1"
    assert commands[1][commands[1].index("--field-id") + 1] == "图片附件"
    assert commands[1][commands[1].index("--file") + 1] == "./image.png"
    assert upload_cwds == [image_path.parent]
    state = json.loads(archive_path.read_text(encoding="utf-8"))
    assert state["archives"]["archive-1"]["last_external_message_id"] == "om_image_1"
    assert state["archives"]["archive-1"]["last_attachment_upload_count"] == 1


def test_feishu_archive_attachment_append_can_target_record_by_title(tmp_path, monkeypatch):
    from core import config as core_config
    from services.feishu import feishu_archive_writer_service as writer

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()
    archive_path = tmp_path / "api-data" / "feishu-archive-docs.json"
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.write_text(
        json.dumps(
            {
                "version": 1,
                "archives": {
                    "archive-1": {
                        "archive_key": "archive-1",
                        "connector_id": "conn-feishu-1",
                        "external_chat_id": "oc_real_group_1",
                        "writer_type": "bitable",
                        "writer_mode": "lark_cli_user",
                        "app_token": "app_1",
                        "table_id": "tbl_1",
                        "record_id": "rec_latest",
                        "document_title": "数转CRM技术小组-bug表格【简信软件CMR】",
                        "last_title": "上一条记录",
                        "updated_at": "2026-04-26T10:00:00+00:00",
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    image_path = tmp_path / "image.png"
    image_path.write_bytes(b"fake image")
    commands = []

    def fake_run_lark_cli_json(args, *, timeout=90, cwd=None):
        commands.append(args)
        if args[:2] == ["base", "+record-search"]:
            return {
                "data": {
                    "records": [
                        {
                            "record_id": "recvjstM2eMtiL",
                            "fields": {"标题": "Git 代码仓库无法提交/推送，提示无权限"},
                        }
                    ]
                }
            }
        if args[:2] == ["base", "+field-list"]:
            return {"data": {"fields": [{"id": "fld_attach", "name": "图片附件", "type": "attachment"}]}}
        if _is_bitable_record_upload_attachment_call(args):
            return {"record": {"record_id": "recvjstM2eMtiL"}}
        return {}

    monkeypatch.setattr(writer, "_run_lark_cli_json", fake_run_lark_cli_json)

    result = writer.append_feishu_archive_attachments(
        source_context={
            "connector_id": "conn-feishu-1",
            "external_chat_id": "oc_real_group_1",
            "external_message_id": "om_image_1",
        },
        attachment_files=[{"path": str(image_path), "filename": "image.png"}],
        message_text="这个图片追加到 标题是 ‘Git 代码仓库无法提交/推送，提示无权限’ 的数据里面",
    )

    upload_calls = [args for args in commands if _is_bitable_record_upload_attachment_call(args)]
    put_calls = [args for args in commands if _is_bitable_record_put_call(args)]
    assert result["status"] == "updated"
    assert result["record_id"] == "recvjstM2eMtiL"
    assert upload_calls
    assert put_calls == []
    assert upload_calls[0][upload_calls[0].index("--record-id") + 1] == "recvjstM2eMtiL"


def test_feishu_archive_attachment_append_skips_when_target_title_not_found(tmp_path, monkeypatch):
    from core import config as core_config
    from services.feishu import feishu_archive_writer_service as writer

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()
    archive_path = tmp_path / "api-data" / "feishu-archive-docs.json"
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.write_text(
        json.dumps(
            {
                "version": 1,
                "archives": {
                    "archive-1": {
                        "archive_key": "archive-1",
                        "connector_id": "conn-feishu-1",
                        "external_chat_id": "oc_real_group_1",
                        "writer_type": "bitable",
                        "writer_mode": "lark_cli_user",
                        "app_token": "app_1",
                        "table_id": "tbl_1",
                        "record_id": "rec_latest",
                        "document_title": "数转CRM技术小组-bug表格【简信软件CMR】",
                        "last_title": "上一条记录",
                        "updated_at": "2026-04-26T10:00:00+00:00",
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    image_path = tmp_path / "image.png"
    image_path.write_bytes(b"fake image")
    commands = []

    def fake_run_lark_cli_json(args, *, timeout=90, cwd=None):
        commands.append(args)
        if args[:2] == ["base", "+record-search"]:
            return {
                "data": {
                    "records": [
                        {
                            "record_id": "rec_other",
                            "fields": {"标题": "另一个标题"},
                        }
                    ]
                }
            }
        if args[:2] == ["base", "+field-list"]:
            raise AssertionError("should not prepare attachment upload when target title is not found")
        return {}

    monkeypatch.setattr(writer, "_run_lark_cli_json", fake_run_lark_cli_json)

    result = writer.append_feishu_archive_attachments(
        source_context={
            "connector_id": "conn-feishu-1",
            "external_chat_id": "oc_real_group_1",
            "external_message_id": "om_image_1",
        },
        attachment_files=[{"path": str(image_path), "filename": "image.png"}],
        message_text="这个图片追加到 标题是 ‘Git 代码仓库无法提交/推送，提示无权限’ 的数据里面",
    )

    upload_calls = [args for args in commands if _is_bitable_record_upload_attachment_call(args)]
    assert result["status"] == "skipped"
    assert "未找到标题为" in result["message"]
    assert upload_calls == []


def test_feishu_archive_attachment_upload_uses_existing_attachment_field_name(tmp_path, monkeypatch):
    from core import config as core_config
    from services.feishu import feishu_archive_writer_service as writer

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()
    archive_path = tmp_path / "api-data" / "feishu-archive-docs.json"
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.write_text(
        json.dumps(
            {
                "version": 1,
                "archives": {
                    "archive-1": {
                        "archive_key": "archive-1",
                        "connector_id": "conn-feishu-1",
                        "external_chat_id": "oc_real_group_1",
                        "writer_type": "bitable",
                        "writer_mode": "lark_cli_user",
                        "app_token": "app_1",
                        "table_id": "tbl_1",
                        "record_id": "rec_1",
                        "attachment_field_name": "图片附件",
                        "updated_at": "2026-04-26T10:00:00+00:00",
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    image_path = tmp_path / "image.png"
    image_path.write_bytes(b"fake image")
    commands = []
    upload_cwds = []

    def fake_run_lark_cli_json(args, *, timeout=90, cwd=None):
        commands.append(args)
        if _is_bitable_record_upload_attachment_call(args):
            upload_cwds.append(cwd)
        if args[:2] == ["base", "+field-list"]:
            return {"data": {"fields": [{"id": "fld_attach_1", "name": "图片附件", "type": "attachment"}]}}
        if _is_bitable_record_upload_attachment_call(args):
            return {"record": {"record_id": "rec_1"}}
        return {}

    monkeypatch.setattr(writer, "_run_lark_cli_json", fake_run_lark_cli_json)

    result = writer.append_feishu_archive_attachments(
        source_context={
            "connector_id": "conn-feishu-1",
            "external_chat_id": "oc_real_group_1",
            "external_message_id": "om_image_1",
        },
        attachment_files=[{"path": str(image_path), "filename": "image.png"}],
    )

    upload_calls = [args for args in commands if _is_bitable_record_upload_attachment_call(args)]
    put_calls = [args for args in commands if _is_bitable_record_put_call(args)]
    assert result["status"] == "updated"
    assert upload_calls[0][upload_calls[0].index("--file") + 1] == "./image.png"
    assert put_calls == []
    assert upload_cwds == [image_path.parent]


def test_feishu_archive_attachment_append_creates_attachment_field_for_legacy_text_field(tmp_path, monkeypatch):
    from core import config as core_config
    from services.feishu import feishu_archive_writer_service as writer

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()
    archive_path = tmp_path / "api-data" / "feishu-archive-docs.json"
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.write_text(
        json.dumps(
            {
                "version": 1,
                "archives": {
                    "archive-1": {
                        "archive_key": "archive-1",
                        "connector_id": "conn-feishu-1",
                        "external_chat_id": "oc_real_group_1",
                        "writer_type": "bitable",
                        "writer_mode": "lark_cli_user",
                        "app_token": "app_1",
                        "table_id": "tbl_1",
                        "record_id": "rec_1",
                        "attachment_field_name": "图片附件2",
                        "document_title": "bug文档【飞书机器人】",
                        "updated_at": "2026-04-26T10:00:00+00:00",
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    image_path = tmp_path / "legacy-image.png"
    image_path.write_bytes(b"fake image")
    commands = []

    def fake_run_lark_cli_json(args, *, timeout=90, cwd=None):
        commands.append(args)
        if args[:2] == ["base", "+field-list"]:
            return {"data": {"fields": [{"name": "图片/附件", "type": "text"}]}}
        if args[:2] == ["base", "+field-create"]:
            return {"field": {"id": "fld_attachment"}, "created": True}
        if _is_bitable_record_upload_attachment_call(args):
            return {"record": {"record_id": "rec_1"}}
        return {}

    monkeypatch.setattr(writer, "_run_lark_cli_json", fake_run_lark_cli_json)

    result = writer.append_feishu_archive_attachments(
        source_context={
            "connector_id": "conn-feishu-1",
            "external_chat_id": "oc_real_group_1",
            "external_message_id": "om_image_1",
        },
        attachment_urls=["/api/bot-events/feishu/conn-feishu-1/resources/om_image_1/legacy-image.png"],
        attachment_files=[{"path": str(image_path), "filename": "legacy-image.png"}],
    )

    created_attachment_fields = [
        json.loads(args[args.index("--json") + 1])
        for args in commands
        if args[:2] == ["base", "+field-create"] and json.loads(args[args.index("--json") + 1]).get("type") == "attachment"
    ]
    upload_calls = [args for args in commands if _is_bitable_record_upload_attachment_call(args)]
    put_calls = [args for args in commands if _is_bitable_record_put_call(args)]
    assert result["status"] == "updated"
    assert created_attachment_fields[0] == {"name": "图片附件", "type": "attachment"}
    assert upload_calls[0][upload_calls[0].index("--file") + 1] == "./legacy-image.png"
    assert put_calls == []
    state = json.loads(archive_path.read_text(encoding="utf-8"))
    assert state["archives"]["archive-1"]["attachment_field_name"] == "图片附件"


def test_feishu_archive_attachment_append_reuses_existing_attachment_field(tmp_path, monkeypatch):
    from core import config as core_config
    from services.feishu import feishu_archive_writer_service as writer

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()
    archive_path = tmp_path / "api-data" / "feishu-archive-docs.json"
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.write_text(
        json.dumps(
            {
                "version": 1,
                "archives": {
                    "archive-1": {
                        "archive_key": "archive-1",
                        "connector_id": "conn-feishu-1",
                        "external_chat_id": "oc_real_group_1",
                        "writer_type": "bitable",
                        "writer_mode": "lark_cli_user",
                        "app_token": "app_1",
                        "table_id": "tbl_1",
                        "record_id": "rec_1",
                        "document_title": "bug文档【飞书机器人】",
                        "updated_at": "2026-04-26T10:00:00+00:00",
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    image_path = tmp_path / "image.png"
    image_path.write_bytes(b"fake image")
    commands = []

    def fake_run_lark_cli_json(args, *, timeout=90, cwd=None):
        commands.append(args)
        if args[:2] == ["base", "+field-list"]:
            return {
                "data": {
                    "fields": [
                        {"name": "图片/附件", "type": "text"},
                        {"name": "图片附件", "type": "attachment"},
                        {"name": "图片附件2", "type": "attachment"},
                    ]
                }
            }
        if _is_bitable_record_upload_attachment_call(args):
            return {"record": {"record_id": "rec_1"}}
        return {}

    monkeypatch.setattr(writer, "_run_lark_cli_json", fake_run_lark_cli_json)

    result = writer.append_feishu_archive_attachments(
        source_context={
            "connector_id": "conn-feishu-1",
            "external_chat_id": "oc_real_group_1",
            "external_message_id": "om_image_1",
        },
        attachment_urls=["/api/bot-events/feishu/conn-feishu-1/resources/om_image_1/image.png"],
        attachment_files=[{"path": str(image_path), "filename": "image.png"}],
    )

    assert result["status"] == "updated"
    assert result["attachment_field_name"] == "图片附件"
    created_attachment_fields = [
        json.loads(args[args.index("--json") + 1])
        for args in commands
        if args[:2] == ["base", "+field-create"]
        and json.loads(args[args.index("--json") + 1]).get("type") == "attachment"
    ]
    assert created_attachment_fields == []
    upload_calls = [args for args in commands if _is_bitable_record_upload_attachment_call(args)]
    put_calls = [args for args in commands if _is_bitable_record_put_call(args)]
    assert upload_calls[0][upload_calls[0].index("--file") + 1] == "./image.png"
    assert put_calls == []


def test_feishu_message_event_queues_speech_only_when_task_listener_matches(tmp_path, monkeypatch):
    from services.feishu.feishu_bot_service import process_feishu_message_event
    from services.assistant.global_assistant_task_service import upsert_global_assistant_task
    from stores.json.project_store import ProjectConfig, ProjectUserMember

    client, store_factory = _build_project_chat_runtime_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    store_factory.project_store.upsert_user_member(
        ProjectUserMember(project_id="proj-1", username="tester", role="owner")
    )
    store_factory.bot_connector_store.replace_all(
        [
            {
                "id": "conn-feishu-1",
                "platform": "feishu",
                "name": "飞书机器人",
                "enabled": True,
                "project_id": "proj-1",
                "app_id": "cli_xxx",
                "app_secret": "secret_xxx",
                "bot_open_id": "ou_bot_1",
            }
        ]
    )
    create_response = client.post(
        "/api/projects/proj-1/chat/sessions",
        json={
            "title": "飞书群：产品研发群",
            "source_context": {
                "source_type": "group_message",
                "platform": "feishu",
                "connector_id": "conn-feishu-1",
                "external_chat_id": "oc_real_group_1",
                "external_chat_name": "产品研发群",
            },
        },
    )
    assert create_response.status_code == 200
    upsert_global_assistant_task(
        username="tester",
        project_id="proj-1",
        task={
            "id": "task-listen-summary",
            "description": "监听 产品研发群 总结需求 时播报",
            "status": "todo",
            "listen_enabled": True,
        },
    )

    calls = []
    replies = []
    speech_calls = []

    class FakeResult:
        content = "收到，已总结需求"

    async def fake_run_project_chat_once(**kwargs):
        calls.append(kwargs)
        return FakeResult()

    async def fake_reply_feishu_text(connector, **kwargs):
        replies.append((connector, kwargs))

    async def fake_enqueue_system_speech(text, **kwargs):
        speech_calls.append({"text": text, **kwargs})
        return {"queued": True, "reason": ""}

    monkeypatch.setattr(
        "services.feishu.feishu_bot_service.run_project_chat_once",
        fake_run_project_chat_once,
    )
    monkeypatch.setattr(
        "services.feishu.feishu_bot_service._reply_feishu_text",
        fake_reply_feishu_text,
    )
    monkeypatch.setattr(
        "services.feishu.feishu_bot_service.enqueue_system_speech",
        fake_enqueue_system_speech,
    )

    class Obj:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    event = Obj(
        event=Obj(
            sender=Obj(sender_type="user", sender_id=Obj(open_id="ou_sender_1")),
            message=Obj(
                chat_type="group",
                chat_id="oc_real_group_1",
                thread_id="",
                message_id="om_message_2",
                message_type="text",
                content='{"text":"@_user_1 帮我总结需求"}',
                mentions=[Obj(key="@_user_1", id=Obj(open_id="ou_bot_1"))],
            ),
        )
    )

    import asyncio

    asyncio.run(process_feishu_message_event("conn-feishu-1", event))

    assert len(calls) == 1
    assert replies[0][1]["message_id"] == "om_message_2"
    assert speech_calls == [
        {
            "text": "飞书群 产品研发群有新事项：帮我总结需求。机器人已回复，请查看。",
            "owner_username": "tester",
            "role_ids": ["admin"],
            "source": "feishu-task-listener",
            "require_enabled": True,
        }
    ]



def test_global_assistant_task_listener_extracts_need_trigger(tmp_path, monkeypatch):
    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services.assistant.global_assistant_task_service import (
        match_global_assistant_tasks_for_event,
        upsert_global_assistant_task,
    )

    upsert_global_assistant_task(
        username="tester",
        project_id="proj-1",
        task={
            "id": "task-need-alert",
            "description": "有需求的时候提示",
            "status": "todo",
            "listen_enabled": True,
        },
    )

    matches = match_global_assistant_tasks_for_event(
        username="tester",
        project_id="proj-1",
        message_text="我有个新需求，帮忙看一下",
        source_context={"platform": "feishu"},
    )

    assert [item["id"] for item in matches] == ["task-need-alert"]


def test_global_assistant_task_infers_dynamic_project_chat_action_for_reminder(tmp_path, monkeypatch):
    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services.assistant.global_assistant_task_service import upsert_global_assistant_task

    task = upsert_global_assistant_task(
        username="tester",
        project_id="proj-1",
        task={
            "id": "task-remind-bug",
            "description": "飞书群里监听到 新增bug 或 处理bug 时提醒用户",
            "status": "todo",
            "listen_enabled": True,
            "actions": [{"type": "record", "label": "记录任务执行"}],
        },
    )

    assert task["actions"][0]["type"] == "project_chat"
    assert task["actions"][0]["label"] == "大模型动态执行"
    assert task["actions"][0]["params"]["mode"] == "dynamic_task"


def test_global_assistant_task_module_empty_speech_action_migrates_to_stable_system_speech(tmp_path, monkeypatch):
    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services.assistant.global_assistant_task_service import upsert_global_assistant_task

    task = upsert_global_assistant_task(
        username="tester",
        project_id="proj-1",
        task={
            "id": "task-remind-clock-in",
            "title": "提醒",
            "description": "提醒 打卡 重复2次",
            "source": "tasks-module",
            "status": "todo",
            "task_type": "reminder",
            "actions": [{"type": "system_speech", "label": "系统播报"}],
        },
    )

    assert task["actions"][0]["type"] == "system_speech"
    assert task["actions"][0]["label"] == "系统播报"
    assert task["actions"][0]["params"]["text"] == "提醒 打卡"
    assert task["actions"][0]["params"]["repeat"] == 2


def test_global_assistant_task_engine_records_event_execution(tmp_path, monkeypatch):
    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services.assistant.global_assistant_task_service import (
        list_global_assistant_tasks,
        process_global_assistant_tasks_for_event,
        upsert_global_assistant_task,
    )

    upsert_global_assistant_task(
        username="tester",
        project_id="proj-1",
        task={
            "id": "task-file-processing",
            "title": "处理文件任务",
            "description": "群里出现合同文件时处理文件",
            "task_type": "file_processing",
            "status": "todo",
            "triggers": [
                {
                    "type": "event",
                    "enabled": True,
                    "source": "feishu",
                    "phrases": ["合同文件"],
                }
            ],
            "actions": [{"type": "file_processing", "label": "处理合同文件"}],
        },
    )

    matches = process_global_assistant_tasks_for_event(
        username="tester",
        project_id="proj-1",
        message_text="这里有一份合同文件需要归档",
        source_context={"platform": "feishu"},
    )
    tasks = list_global_assistant_tasks(username="tester", project_id="proj-1")

    assert [item["id"] for item in matches] == ["task-file-processing"]
    assert tasks[0]["task_type"] == "file_processing"
    assert tasks[0]["execution_count"] == 1
    assert tasks[0]["execution_history"][0]["trigger_type"] == "event"
    assert tasks[0]["execution_history"][0]["action_results"][0]["action_type"] == "file_processing"


def test_global_assistant_task_upsert_preserves_runtime_execution_fields(tmp_path, monkeypatch):
    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services.assistant.global_assistant_task_service import (
        execute_global_assistant_task,
        list_global_assistant_tasks,
        upsert_global_assistant_task,
    )

    upsert_global_assistant_task(
        username="tester",
        project_id="proj-1",
        task={
            "id": "task-runtime-preserve",
            "title": "监听 bug",
            "description": "监听到 bug 时提醒",
            "status": "todo",
            "triggers": [{"type": "event", "enabled": True, "source": "feishu", "phrases": ["bug"]}],
            "actions": [{"type": "system_speech", "label": "后台语音提醒"}],
        },
    )
    execute_global_assistant_task(
        username="tester",
        project_id="proj-1",
        task_id="task-runtime-preserve",
        trigger_type="event",
        message_text="新增 bug",
        match_reason="phrase:bug",
    )

    upsert_global_assistant_task(
        username="tester",
        project_id="proj-1",
        task={
            "id": "task-runtime-preserve",
            "title": "监听 bug",
            "description": "前端旧缓存同步",
            "status": "todo",
            "triggers": [{"type": "event", "enabled": True, "source": "feishu", "phrases": ["bug"]}],
            "actions": [{"type": "system_speech", "label": "后台语音提醒"}],
        },
    )
    tasks = list_global_assistant_tasks(username="tester", project_id="proj-1")

    assert tasks[0]["execution_count"] == 1
    assert len(tasks[0]["execution_history"]) == 1
    assert tasks[0]["last_run_at"]


def test_global_assistant_task_rejects_edit_while_doing(tmp_path, monkeypatch):
    import pytest

    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services.assistant.global_assistant_task_service import (
        list_global_assistant_tasks,
        upsert_global_assistant_task,
    )

    upsert_global_assistant_task(
        username="tester",
        project_id="proj-1",
        task={
            "id": "task-running",
            "title": "监听 bug",
            "description": "监听到 bug 时提醒",
            "status": "doing",
            "triggers": [{"type": "event", "enabled": True, "source": "feishu", "phrases": ["bug"]}],
            "actions": [{"type": "system_speech", "label": "后台语音提醒"}],
        },
    )

    with pytest.raises(ValueError, match="进行中的任务不允许编辑"):
        upsert_global_assistant_task(
            username="tester",
            project_id="proj-1",
            task={
                "id": "task-running",
                "title": "监听需求",
                "description": "监听到需求时提醒",
                "status": "doing",
                "triggers": [{"type": "event", "enabled": True, "source": "feishu", "phrases": ["需求"]}],
                "actions": [{"type": "system_speech", "label": "后台语音提醒"}],
            },
        )

    upsert_global_assistant_task(
        username="tester",
        project_id="proj-1",
        task={
            "id": "task-running",
            "title": "监听 bug",
            "description": "监听到 bug 时提醒",
            "status": "done",
            "triggers": [{"type": "event", "enabled": True, "source": "feishu", "phrases": ["bug"]}],
            "actions": [{"type": "system_speech", "label": "后台语音提醒"}],
        },
    )
    tasks = list_global_assistant_tasks(username="tester", project_id="proj-1")

    assert tasks[0]["status"] == "done"
    assert tasks[0]["description"] == "监听到 bug 时提醒"


def test_global_assistant_task_engine_runs_due_schedule(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services.assistant.global_assistant_task_service import (
        list_global_assistant_tasks,
        run_due_global_assistant_tasks,
        upsert_global_assistant_task,
    )

    due_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(timespec="seconds")
    upsert_global_assistant_task(
        username="tester",
        project_id="proj-1",
        task={
            "id": "task-scheduled",
            "title": "定时任务",
            "description": "到点记录一次",
            "status": "todo",
            "triggers": [
                {
                    "type": "schedule",
                    "enabled": True,
                    "schedule": {"next_run_at": due_at, "interval_seconds": 60},
                }
            ],
            "actions": [{"type": "record", "label": "记录执行"}],
        },
    )

    executed = run_due_global_assistant_tasks()
    tasks = list_global_assistant_tasks(username="tester", project_id="proj-1")

    assert [item["id"] for item in executed] == ["task-scheduled"]
    assert tasks[0]["execution_count"] == 1
    assert tasks[0]["execution_history"][0]["trigger_type"] == "schedule"
    assert tasks[0]["next_run_at"]


def test_global_assistant_task_infers_schedule_from_natural_reminder_time(tmp_path, monkeypatch):
    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services.assistant.global_assistant_task_service import list_global_assistant_tasks, upsert_global_assistant_task

    upsert_global_assistant_task(
        username="tester",
        project_id="proj-1",
        task={
            "id": "task-natural-reminder",
            "title": "下午两点21提醒 吃饭",
            "description": "下午两点21提醒 吃饭",
            "status": "todo",
            "source": "global-assistant",
            "task_type": "workflow",
            "created_at": "2026-04-27T06:19:50+00:00",
            "triggers": [{"type": "event", "enabled": False, "source": "feishu", "phrases": []}],
            "actions": [{"type": "project_chat", "label": "大模型动态执行", "params": {"mode": "dynamic_task"}}],
        },
    )

    tasks = list_global_assistant_tasks(username="tester", project_id="proj-1")

    assert tasks[0]["next_run_at"] == "2026-04-27T06:21:00+00:00"
    schedule_trigger = [item for item in tasks[0]["triggers"] if item["type"] == "schedule"][0]
    assert schedule_trigger["source"] == "natural-language"
    assert schedule_trigger["schedule"]["next_run_at"] == "2026-04-27T06:21:00+00:00"


def test_global_assistant_task_route_uses_llm_classifier_schedule(tmp_path, monkeypatch):
    from routers import projects as projects_router
    from services.runtime.provider_resolver import ResolvedProviderRuntime

    client, _store_factory = _build_project_chat_runtime_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )

    async def fake_resolve_runtime(runtime_settings, auth_payload):
        return ResolvedProviderRuntime(
            provider_mode="provider",
            provider={"id": "provider-1", "models": ["model-1"], "default_model": "model-1"},
            providers=[],
            provider_id="provider-1",
            model_name="model-1",
        )

    class FakeLlmService:
        async def chat_completion(self, provider_id, model_name, messages, **kwargs):
            assert provider_id == "provider-1"
            assert model_name == "model-1"
            return {
                "content": json.dumps(
                    {
                        "title": "提醒吃饭",
                        "description": "下午两点21提醒 吃饭",
                        "task_type": "reminder",
                        "triggers": [
                            {
                                "type": "schedule",
                                "enabled": True,
                                "schedule": {
                                    "run_at": "2026-04-27T14:21:00+08:00",
                                    "next_run_at": "2026-04-27T14:21:00+08:00",
                                    "interval_seconds": 0,
                                },
                            }
                        ],
                        "summary": "用户要求在明确时间提醒吃饭",
                    },
                    ensure_ascii=False,
                )
            }

    monkeypatch.setattr(projects_router, "_resolve_global_assistant_chat_runtime", fake_resolve_runtime)
    monkeypatch.setattr(
        "services.providers.llm_provider_service.get_llm_provider_service",
        lambda: FakeLlmService(),
    )

    response = client.post(
        "/api/projects/chat/global/tasks",
        headers={"X-Project-Id": "proj-1"},
        json={
            "title": "下午两点21提醒 吃饭",
            "description": "下午两点21提醒 吃饭",
            "source": "global-assistant",
            "task_type": "workflow",
        },
    )

    assert response.status_code == 200
    task = response.json()["task"]
    assert task["task_type"] == "reminder"
    assert task["next_run_at"] == "2026-04-27T06:21:00+00:00"
    schedule_trigger = [item for item in task["triggers"] if item["type"] == "schedule"][0]
    assert schedule_trigger["source"] == "llm-classifier"
    assert schedule_trigger["schedule"]["next_run_at"] == "2026-04-27T06:21:00+00:00"
    assert task["actions"][0]["type"] == "system_speech"
    assert task["actions"][0]["params"]["text"] == "下午两点21提醒 吃饭"


def test_global_assistant_task_classifier_does_not_treat_repeat_count_as_daily_interval():
    from routers.projects import _merge_global_task_classifier_result

    task = _merge_global_task_classifier_result(
        {
            "title": "测试成功提醒",
            "description": "下午2点49分发送消息提醒：测试成功，共提醒2次。",
            "task_type": "workflow",
        },
        {
            "task_type": "reminder",
            "triggers": [
                {
                    "type": "schedule",
                    "schedule": {
                        "run_at": "2026-04-27T14:49:00+08:00",
                        "next_run_at": "2026-04-27T14:49:00+08:00",
                        "interval_seconds": 86400,
                    },
                }
            ],
            "summary": "提醒两次",
        },
    )

    schedule_trigger = [item for item in task["triggers"] if item["type"] == "schedule"][0]
    assert schedule_trigger["schedule"]["interval_seconds"] == 0


def test_global_assistant_task_classifier_prefers_local_same_day_daily_time():
    from routers.projects import _merge_global_task_classifier_result

    task = _merge_global_task_classifier_result(
        {
            "title": "下班提醒",
            "description": "每天下午4点05提醒：下班，提醒3次",
            "task_type": "workflow",
            "created_at": "2026-04-27T08:02:00+00:00",
        },
        {
            "task_type": "reminder",
            "triggers": [
                {
                    "type": "schedule",
                    "schedule": {
                        "run_at": "2026-04-28T16:05:00+08:00",
                        "next_run_at": "2026-04-28T16:05:00+08:00",
                        "interval_seconds": 86400,
                    },
                }
            ],
            "summary": "每天提醒下班",
        },
    )

    schedule_trigger = [item for item in task["triggers"] if item["type"] == "schedule"][0]
    assert schedule_trigger["schedule"]["run_at"] == "2026-04-27T08:05:00+00:00"
    assert schedule_trigger["schedule"]["next_run_at"] == "2026-04-27T08:05:00+00:00"
    assert schedule_trigger["schedule"]["interval_seconds"] == 86400
    assert task["next_run_at"] == "2026-04-27T08:05:00+00:00"


def test_global_assistant_reminder_classifier_uses_stable_system_speech_action(tmp_path, monkeypatch):
    from core import config as core_config
    from routers.projects import _merge_global_task_classifier_result
    from services.assistant.global_assistant_task_service import upsert_global_assistant_task

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    task = _merge_global_task_classifier_result(
        {
            "title": "15:19提醒查看营销云",
            "description": "下午3点19提醒：看看营销云，提醒2次。",
            "task_type": "workflow",
            "source": "global-assistant",
        },
        {
            "task_type": "reminder",
            "triggers": [
                {
                    "type": "schedule",
                    "schedule": {
                        "run_at": "2026-04-27T15:19:00+08:00",
                        "next_run_at": "2026-04-27T15:19:00+08:00",
                        "interval_seconds": 0,
                    },
                }
            ],
            "summary": "定时提醒查看营销云，提醒两次",
        },
    )
    normalized = upsert_global_assistant_task(username="tester", project_id="proj-1", task=task)

    assert normalized["task_type"] == "reminder"
    assert normalized["actions"][0]["type"] == "system_speech"
    assert normalized["actions"][0]["label"] == "系统播报"
    assert normalized["actions"][0]["params"]["text"] == "看看营销云"
    assert normalized["actions"][0]["params"]["repeat"] == 2


def test_global_assistant_task_route_uses_local_connector_classifier(tmp_path, monkeypatch):
    from routers import projects as projects_router
    from services.runtime.provider_resolver import ResolvedProviderRuntime

    client, _store_factory = _build_project_chat_runtime_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )

    async def fake_resolve_runtime(runtime_settings, auth_payload):
        return ResolvedProviderRuntime(
            provider_mode="local_connector",
            provider={"id": "local-connector:connector-1", "models": ["local-model"]},
            providers=[],
            provider_id="local-connector:connector-1",
            model_name="local-model",
            connector_id="connector-1",
        )

    async def fake_chat_completion_via_connector(connector, **kwargs):
        assert connector == {"id": "connector-1"}
        assert kwargs["model_name"] == "local-model"
        return {
            "content": json.dumps(
                {
                    "title": "提醒喝水",
                    "description": "下午三点提醒喝水",
                    "task_type": "reminder",
                    "triggers": [
                        {
                            "type": "schedule",
                            "enabled": True,
                            "schedule": {
                                "run_at": "2026-04-27T15:00:00+08:00",
                                "next_run_at": "2026-04-27T15:00:00+08:00",
                            },
                        }
                    ],
                },
                ensure_ascii=False,
            )
        }

    monkeypatch.setattr(projects_router, "_resolve_global_assistant_chat_runtime", fake_resolve_runtime)
    monkeypatch.setattr(
        projects_router,
        "_resolve_accessible_local_connector_for_llm",
        lambda connector_id, auth_payload: {"id": connector_id},
    )
    monkeypatch.setattr(
        projects_router,
        "chat_completion_via_connector",
        fake_chat_completion_via_connector,
    )

    response = client.post(
        "/api/projects/chat/global/tasks",
        headers={"X-Project-Id": "proj-1"},
        json={
            "title": "下午三点提醒喝水",
            "description": "下午三点提醒喝水",
            "source": "global-assistant",
            "task_type": "workflow",
        },
    )

    assert response.status_code == 200
    task = response.json()["task"]
    assert task["task_type"] == "reminder"
    assert task["next_run_at"] == "2026-04-27T07:00:00+00:00"
    schedule_trigger = [item for item in task["triggers"] if item["type"] == "schedule"][0]
    assert schedule_trigger["source"] == "llm-classifier"


def test_global_assistant_task_route_falls_back_to_natural_schedule_parser(tmp_path, monkeypatch):
    client, _store_factory = _build_project_chat_runtime_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )

    response = client.post(
        "/api/projects/chat/global/tasks",
        headers={"X-Project-Id": "proj-1"},
        json={
            "title": "2026年4月27日14:21提醒吃饭",
            "description": "2026年4月27日14:21提醒吃饭",
            "source": "global-assistant",
            "task_type": "workflow",
            "triggers": [{"type": "event", "enabled": False, "source": "feishu", "phrases": []}],
            "actions": [{"type": "project_chat", "label": "大模型动态执行", "params": {"mode": "dynamic_task"}}],
        },
    )

    assert response.status_code == 200
    task = response.json()["task"]
    assert task["next_run_at"] == "2026-04-27T06:21:00+00:00"
    schedule_trigger = [item for item in task["triggers"] if item["type"] == "schedule"][0]
    assert schedule_trigger["source"] == "natural-language"


def test_global_assistant_task_engine_queues_due_system_speech(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services.providers import system_speech_service
    from services.assistant.global_assistant_task_service import (
        list_global_assistant_tasks,
        run_due_global_assistant_tasks,
        upsert_global_assistant_task,
    )

    queued_calls = []

    async def fake_enqueue_system_speech(text, **kwargs):
        queued_calls.append({"text": text, **kwargs})
        return {"queued": True, "reason": "", "queue_size": 1, "text_length": len(text)}

    monkeypatch.setattr(system_speech_service, "enqueue_system_speech", fake_enqueue_system_speech)
    due_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(timespec="seconds")
    upsert_global_assistant_task(
        username="tester",
        project_id="proj-1",
        task={
            "id": "task-scheduled-speech",
            "title": "定时提醒",
            "description": "上班了上班了",
            "status": "todo",
            "task_type": "reminder",
            "triggers": [
                {
                    "type": "schedule",
                    "enabled": True,
                    "schedule": {"next_run_at": due_at},
                }
            ],
            "actions": [
                {
                    "type": "system_speech",
                    "label": "系统提醒",
                    "params": {"text": "上班了上班了", "role_ids": ["admin"], "require_enabled": False},
                }
            ],
        },
    )

    executed = run_due_global_assistant_tasks()
    tasks = list_global_assistant_tasks(username="tester", project_id="proj-1")

    assert [item["id"] for item in executed] == ["task-scheduled-speech"]
    assert queued_calls == [
        {
            "text": "上班了上班了",
            "owner_username": "tester",
            "role_ids": ["admin"],
            "source": "global-assistant-task",
            "require_enabled": False,
        }
    ]
    assert tasks[0]["status"] == "done"
    assert tasks[0]["execution_history"][0]["action_results"][0]["status"] == "queued"


def test_global_assistant_system_speech_action_respects_disabled_config_in_event_loop(monkeypatch):
    import asyncio
    from types import SimpleNamespace

    from services.providers import system_speech_service
    from services.assistant.global_assistant_task_service import _enqueue_system_speech_action

    monkeypatch.setattr(
        system_speech_service.system_config_store,
        "get_global",
        lambda: SimpleNamespace(voice_output_enabled=False),
    )

    async def run_action():
        return _enqueue_system_speech_action(
            {"created_by": "tester", "description": "上班了上班了"},
            {"type": "system_speech", "params": {"text": "上班了上班了", "require_enabled": True}},
        )

    result = asyncio.run(run_action())

    assert result == {"queued": False, "reason": "系统未开启语音播报"}


def test_global_assistant_project_chat_action_uses_llm_dynamic_plan_for_repeated_speech(tmp_path, monkeypatch):
    from core import config as core_config
    from stores.json.project_store import ProjectConfig

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    client, store_factory = _build_project_chat_runtime_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin", "roles": ["admin"]},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))

    from services.chat import project_chat_execution_service, system_speech_service
    from services.assistant.global_assistant_task_service import execute_global_assistant_task, upsert_global_assistant_task

    chat_calls = []
    queued_calls = []

    class FakeResult:
        content = '{"actions":[{"type":"system_speech","text":"睡觉","repeat":3}],"summary":"已理解为播报睡觉三次"}'

    async def fake_run_project_chat_once(**kwargs):
        chat_calls.append(kwargs)
        return FakeResult()

    async def fake_enqueue_system_speech(text, **kwargs):
        queued_calls.append({"text": text, **kwargs})
        return {"queued": True, "reason": "", "queue_size": len(queued_calls), "text_length": len(text)}

    monkeypatch.setattr(project_chat_execution_service, "run_project_chat_once", fake_run_project_chat_once)
    monkeypatch.setattr(system_speech_service, "enqueue_system_speech", fake_enqueue_system_speech)

    upsert_global_assistant_task(
        username="tester",
        project_id="proj-1",
        task={
            "id": "task-dynamic-repeat-sleep",
            "title": "睡觉提醒",
            "description": "到时间提醒 睡觉 重复执行3次",
            "status": "todo",
            "task_type": "workflow",
            "actions": [{"type": "project_chat", "label": "大模型动态执行"}],
        },
    )

    executed = execute_global_assistant_task(
        username="tester",
        project_id="proj-1",
        task_id="task-dynamic-repeat-sleep",
        trigger_type="schedule",
        match_reason="schedule-due",
    )

    assert executed is not None
    assert chat_calls
    assert "到时间提醒 睡觉 重复执行3次" in chat_calls[0]["req"].message
    dynamic_session_id = chat_calls[0]["req"].chat_session_id
    assert dynamic_session_id == "chat-session-global-task-task-dynamic-repeat-sleep"
    assert store_factory.project_chat_store.get_session("proj-1", "tester", dynamic_session_id) is not None
    assert [item.id for item in store_factory.project_chat_store.list_sessions("proj-1", "tester")] == [
        dynamic_session_id
    ]
    assert [item["text"] for item in queued_calls] == ["睡觉", "睡觉", "睡觉"]
    assert executed["latest_execution"]["action_results"][0]["status"] == "completed"
    assert executed["latest_execution"]["action_results"][0]["dynamic_action_count"] == 3


def test_global_assistant_async_project_chat_action_finalizes_execution_history(tmp_path, monkeypatch):
    import asyncio

    from core import config as core_config
    from stores.json.project_store import ProjectConfig

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    client, store_factory = _build_project_chat_runtime_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin", "roles": ["admin"]},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))

    from services.chat import project_chat_execution_service, system_speech_service
    from services.assistant.global_assistant_task_service import (
        execute_global_assistant_task,
        list_global_assistant_tasks,
        upsert_global_assistant_task,
    )

    class FakeResult:
        content = '{"actions":[{"type":"system_speech","text":"测试成功","repeat":2}],"summary":"播报两次"}'

    queued_calls = []

    async def fake_run_project_chat_once(**kwargs):
        return FakeResult()

    async def fake_enqueue_system_speech(text, **kwargs):
        queued_calls.append({"text": text, **kwargs})
        return {"queued": True, "reason": "", "queue_size": len(queued_calls), "text_length": len(text)}

    monkeypatch.setattr(project_chat_execution_service, "run_project_chat_once", fake_run_project_chat_once)
    monkeypatch.setattr(system_speech_service, "enqueue_system_speech", fake_enqueue_system_speech)

    upsert_global_assistant_task(
        username="tester",
        project_id="proj-1",
        task={
            "id": "task-async-dynamic-repeat-success",
            "title": "测试成功提醒",
            "description": "下午2点49分发送消息提醒：测试成功，共提醒2次。",
            "status": "todo",
            "task_type": "workflow",
            "actions": [{"id": "action-dynamic", "type": "project_chat", "label": "大模型动态执行"}],
        },
    )

    async def run_in_loop():
        executed = execute_global_assistant_task(
            username="tester",
            project_id="proj-1",
            task_id="task-async-dynamic-repeat-success",
            trigger_type="schedule",
            match_reason="schedule-due",
        )
        assert executed is not None
        assert executed["latest_execution"]["action_results"][0]["status"] == "queued"
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    asyncio.run(run_in_loop())
    tasks = list_global_assistant_tasks(username="tester", project_id="proj-1")
    latest = tasks[0]["execution_history"][-1]["action_results"][0]
    assert latest["status"] == "completed"
    assert latest["dynamic_action_count"] == 2
    assert [item["text"] for item in queued_calls] == ["测试成功", "测试成功"]


def test_global_assistant_async_project_chat_failure_reactivates_schedule_for_retry(tmp_path, monkeypatch):
    import asyncio

    from core import config as core_config
    from stores.json.project_store import ProjectConfig

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    client, store_factory = _build_project_chat_runtime_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin", "roles": ["admin"]},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))

    from services.chat import project_chat_execution_service
    from services.assistant.global_assistant_task_service import (
        execute_global_assistant_task,
        list_global_assistant_tasks,
        upsert_global_assistant_task,
    )

    async def fake_run_project_chat_once(**kwargs):
        raise RuntimeError("llm unavailable")

    monkeypatch.setattr(project_chat_execution_service, "run_project_chat_once", fake_run_project_chat_once)

    upsert_global_assistant_task(
        username="tester",
        project_id="proj-1",
        task={
            "id": "task-async-dynamic-failure",
            "title": "失败重试提醒",
            "description": "下午2点49分发送消息提醒：测试成功。",
            "status": "todo",
            "task_type": "workflow",
            "next_run_at": "2026-04-27T06:49:00+00:00",
            "triggers": [
                {
                    "type": "schedule",
                    "enabled": True,
                    "schedule": {
                        "run_at": "2026-04-27T06:49:00+00:00",
                        "next_run_at": "2026-04-27T06:49:00+00:00",
                        "interval_seconds": 0,
                    },
                }
            ],
            "actions": [{"id": "action-dynamic", "type": "project_chat", "label": "大模型动态执行"}],
        },
    )

    async def run_in_loop():
        executed = execute_global_assistant_task(
            username="tester",
            project_id="proj-1",
            task_id="task-async-dynamic-failure",
            trigger_type="schedule",
            match_reason="schedule-due",
        )
        assert executed is not None
        assert executed["latest_execution"]["action_results"][0]["status"] == "queued"
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    asyncio.run(run_in_loop())
    task = list_global_assistant_tasks(username="tester", project_id="proj-1")[0]
    latest = task["execution_history"][-1]["action_results"][0]
    assert task["status"] == "todo"
    assert task["next_run_at"]
    assert latest["status"] == "failed"
    assert "llm unavailable" in latest["message"]


def test_global_assistant_system_speech_action_repeats_without_llm(tmp_path, monkeypatch):
    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services.providers import system_speech_service
    from services.assistant.global_assistant_task_service import (
        execute_global_assistant_task,
        upsert_global_assistant_task,
    )

    queued_calls = []

    async def fake_enqueue_system_speech(text, **kwargs):
        queued_calls.append({"text": text, **kwargs})
        return {"queued": True, "reason": "", "queue_size": len(queued_calls), "text_length": len(text)}

    monkeypatch.setattr(system_speech_service, "enqueue_system_speech", fake_enqueue_system_speech)

    upsert_global_assistant_task(
        username="tester",
        project_id="proj-1",
        task={
            "id": "task-stable-reminder",
            "title": "15:19提醒查看营销云",
            "description": "下午3点19提醒：看看营销云，提醒2次。",
            "status": "todo",
            "task_type": "reminder",
            "actions": [
                {
                    "id": "action-speech",
                    "type": "system_speech",
                    "label": "系统播报",
                    "params": {"text": "看看营销云", "repeat": 2, "require_enabled": False},
                }
            ],
        },
    )

    executed = execute_global_assistant_task(
        username="tester",
        project_id="proj-1",
        task_id="task-stable-reminder",
        trigger_type="schedule",
        match_reason="schedule-due",
    )

    assert executed is not None
    latest = executed["latest_execution"]["action_results"][0]
    assert latest["action_type"] == "system_speech"
    assert latest["status"] == "queued"
    assert latest["queued_count"] == 2
    assert [item["text"] for item in queued_calls] == ["看看营销云", "看看营销云"]


def test_postgres_project_chat_store_create_session_accepts_explicit_session_id():
    import inspect

    from stores.postgres.project_chat_store import ProjectChatStorePostgres

    assert "session_id" in inspect.signature(ProjectChatStorePostgres.create_session).parameters


def test_feishu_meeting_reminder_parser_handles_fixed_time():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from services.feishu.feishu_scheduled_reminder_service import parse_feishu_meeting_reminder

    parsed = parse_feishu_meeting_reminder(
        "@_user_1 明天下午三点开会，提醒大家",
        now=datetime(2026, 4, 27, 11, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
    )

    assert parsed is not None
    assert parsed.meeting_label == "2026-04-28 15:00"
    assert parsed.reminder_label == "2026-04-28 14:50"
    assert parsed.meeting_at.isoformat(timespec="seconds") == "2026-04-28T07:00:00+00:00"
    assert parsed.reminder_at.isoformat(timespec="seconds") == "2026-04-28T06:50:00+00:00"
    assert parse_feishu_meeting_reminder("几点开会？", now=datetime(2026, 4, 27, 11, 0, tzinfo=ZoneInfo("Asia/Shanghai"))) is None
    urgent = parse_feishu_meeting_reminder(
        "今天15:00开会，提醒一下",
        now=datetime(2026, 4, 27, 14, 55, tzinfo=ZoneInfo("Asia/Shanghai")),
    )
    assert urgent is not None
    assert urgent.meeting_label == "2026-04-27 15:00"
    assert urgent.reminder_label == "2026-04-27 14:55"


def test_feishu_message_event_creates_group_meeting_reminder(tmp_path, monkeypatch):
    from services.feishu.feishu_bot_service import process_feishu_message_event
    from services.assistant.global_assistant_task_service import list_global_assistant_tasks
    from stores.json.project_store import ProjectConfig, ProjectUserMember

    client, store_factory = _build_project_chat_runtime_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    store_factory.project_store.upsert_user_member(
        ProjectUserMember(project_id="proj-1", username="tester", role="owner")
    )
    store_factory.bot_connector_store.replace_all(
        [
            {
                "id": "conn-feishu-1",
                "platform": "feishu",
                "name": "飞书机器人",
                "enabled": True,
                "project_id": "proj-1",
                "app_id": "cli_xxx",
                "app_secret": "secret_xxx",
                "reply_identity": "user",
            }
        ]
    )
    create_response = client.post(
        "/api/projects/proj-1/chat/sessions",
        json={
            "title": "飞书群：产品研发群",
            "source_context": {
                "source_type": "group_message",
                "platform": "feishu",
                "connector_id": "conn-feishu-1",
                "external_chat_id": "oc_real_group_1",
                "external_chat_name": "产品研发群",
            },
        },
    )
    assert create_response.status_code == 200

    class FakeResult:
        content = "收到"

    replies = []

    async def fake_run_project_chat_once(**kwargs):
        return FakeResult()

    async def fake_reply_feishu_text(connector, **kwargs):
        replies.append((connector, kwargs))

    monkeypatch.setattr(
        "services.feishu.feishu_bot_service.run_project_chat_once",
        fake_run_project_chat_once,
    )
    monkeypatch.setattr(
        "services.feishu.feishu_bot_service._reply_feishu_text",
        fake_reply_feishu_text,
    )

    class Obj:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    event = Obj(
        event=Obj(
            sender=Obj(sender_type="user", sender_id=Obj(open_id="ou_sender_1")),
            message=Obj(
                chat_type="group",
                chat_id="oc_real_group_1",
                thread_id="",
                message_id="om_meeting_1",
                message_type="text",
                content='{"text":"@_user_1 明天下午三点开会，提醒大家"}',
                mentions=[Obj(key="@_user_1")],
            ),
        )
    )

    import asyncio

    asyncio.run(process_feishu_message_event("conn-feishu-1", event))

    tasks = list_global_assistant_tasks(username="tester", project_id="proj-1")
    assert len(tasks) == 1
    assert tasks[0]["task_type"] == "reminder"
    assert tasks[0]["actions"][0]["type"] == "feishu_message"
    assert tasks[0]["actions"][0]["params"]["chat_id"] == "oc_real_group_1"
    assert tasks[0]["actions"][0]["params"]["identity"] == "user"
    assert tasks[0]["actions"][0]["params"]["remind_before_minutes"] == 10
    assert "14:50" in tasks[0]["next_run_at"] or tasks[0]["next_run_at"].endswith("T06:50:00+00:00")
    assert "已创建会议提醒" in replies[0][1]["content"]


def test_feishu_scheduled_reminder_sends_due_message_and_completes(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services.feishu import feishu_scheduled_reminder_service as reminders
    from services.assistant.global_assistant_task_service import (
        list_global_assistant_tasks,
        run_due_global_assistant_tasks,
        upsert_global_assistant_task,
    )

    calls = []

    class Completed:
        returncode = 0
        stdout = "{}"
        stderr = ""

    def fake_run(command, **kwargs):
        calls.append({"command": command, **kwargs})
        return Completed()

    monkeypatch.setattr(reminders.subprocess, "run", fake_run)
    due_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(timespec="seconds")
    upsert_global_assistant_task(
        username="tester",
        project_id="proj-1",
        task={
            "id": "feishu-reminder-test",
            "title": "会议提醒",
            "description": "下午三点开会",
            "status": "todo",
            "task_type": "reminder",
            "triggers": [{"type": "schedule", "enabled": True, "source": "feishu", "schedule": {"next_run_at": due_at}}],
            "actions": [
                {
                    "type": "feishu_message",
                    "label": "飞书到点提醒",
                    "params": {"chat_id": "oc_real_group_1", "text": "会议提醒：下午三点开会", "identity": "bot"},
                }
            ],
        },
    )

    executed = run_due_global_assistant_tasks()
    tasks = list_global_assistant_tasks(username="tester", project_id="proj-1")

    assert [item["id"] for item in executed] == ["feishu-reminder-test"]
    assert calls[0]["command"][:3] == ["lark-cli", "im", "+messages-send"]
    assert calls[0]["command"][calls[0]["command"].index("--chat-id") + 1] == "oc_real_group_1"
    assert calls[0]["command"][calls[0]["command"].index("--text") + 1] == "会议提醒：下午三点开会"
    assert tasks[0]["status"] == "done"
    assert tasks[0]["next_run_at"] == ""


def test_feishu_archive_writer_docx_creates_once_then_appends_when_configured(tmp_path, monkeypatch):
    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services.feishu import feishu_archive_writer_service as writer

    monkeypatch.setattr(
        writer,
        "get_bot_connector",
        lambda connector_id: {
            "id": connector_id,
            "platform": "feishu",
            "agent_name": "飞书机器人",
            "app_id": "app-id",
            "app_secret": "app-secret",
        },
    )
    monkeypatch.setattr(writer, "_get_tenant_access_token", lambda connector: "tenant-token")

    post_calls = []

    def fake_post(path, *, token, payload, timeout=15):
        post_calls.append({"path": path, "payload": payload, "token": token})
        if path == "/open-apis/docx/v1/documents":
            return {"document": {"document_id": "doc-created"}}
        return {"children": []}

    monkeypatch.setattr(writer, "_post_feishu_json", fake_post)
    monkeypatch.setattr(writer, "_get_feishu_json", lambda *args, **kwargs: {"items": []})

    task = {"title": "监听 bug", "description": "监听新增bug后归档"}
    action = {
        "id": "action-1",
        "type": "project_chat",
        "params": {
            "workflow": "feishu_bot_auto_archive_to_doc_table",
            "writer_type": "docx",
            "categories": {"bug": {}, "需求": {}, "功能": {}, "会议": {}},
        },
    }
    source_context = {
        "connector_id": "feishu-main",
        "external_chat_id": "oc-1",
        "external_chat_name": "aitest",
        "external_message_id": "om-1",
        "sender_id": "ou-1",
    }

    first = writer.archive_feishu_task_message(
        task=task,
        action=action,
        message_text="新增bug：登录页报错",
        source_context=source_context,
    )
    second = writer.archive_feishu_task_message(
        task=task,
        action=action,
        message_text="新增bug：导航丢失",
        source_context={**source_context, "external_message_id": "om-2"},
    )

    create_calls = [item for item in post_calls if item["path"] == "/open-apis/docx/v1/documents"]
    append_calls = [item for item in post_calls if item["path"].endswith("/children")]

    assert len(create_calls) == 1
    assert len(append_calls) == 3
    assert first["created"] is True
    assert second["created"] is False
    assert first["writer_type"] == "docx"
    assert first["archive_key"] == "feishu-main|oc-1|bug"
    assert first["document_title"] == "aitest-bug文档【飞书机器人】"


def test_feishu_archive_writer_sheet_creates_once_then_appends(tmp_path, monkeypatch):
    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services.feishu import feishu_archive_writer_service as writer

    monkeypatch.setattr(
        writer,
        "get_bot_connector",
        lambda connector_id: {
            "id": connector_id,
            "platform": "feishu",
            "agent_name": "飞书机器人",
            "app_id": "app-id",
            "app_secret": "app-secret",
        },
    )
    monkeypatch.setattr(writer, "_get_tenant_access_token", lambda connector: "tenant-token")

    post_calls = []

    def fake_post(path, *, token, payload, timeout=15):
        post_calls.append({"path": path, "payload": payload, "token": token})
        if path == "/open-apis/sheets/v3/spreadsheets":
            return {"spreadsheet": {"spreadsheet_token": "sht-1"}}
        return {}

    monkeypatch.setattr(writer, "_post_feishu_json", fake_post)
    monkeypatch.setattr(writer, "_get_feishu_json", lambda *args, **kwargs: {"sheets": [{"sheet_id": "gid-1"}]})

    task = {"title": "监听 bug", "description": "监听新增bug后归档"}
    action = {
        "id": "action-1",
        "type": "project_chat",
        "params": {
            "workflow": "feishu_bot_auto_archive_to_doc_table",
            "writer_type": "sheet",
            "categories": {"bug": {}, "需求": {}, "功能": {}, "会议": {}},
        },
    }
    source_context = {
        "connector_id": "feishu-main",
        "external_chat_id": "oc-1",
        "external_chat_name": "aitest",
        "external_message_id": "om-1",
        "sender_id": "ou-1",
    }

    first = writer.archive_feishu_task_message(
        task=task,
        action=action,
        message_text="新增bug：登录页报错",
        source_context=source_context,
    )
    second = writer.archive_feishu_task_message(
        task=task,
        action=action,
        message_text="新增bug：导航丢失",
        source_context={**source_context, "external_message_id": "om-2"},
    )

    create_calls = [item for item in post_calls if item["path"] == "/open-apis/sheets/v3/spreadsheets"]
    append_calls = [item for item in post_calls if item["path"].endswith("/values_append")]

    assert len(create_calls) == 1
    assert len(append_calls) == 3
    assert first["created"] is True
    assert second["created"] is False
    assert first["writer_type"] == "sheet"
    assert first["archive_key"] == "feishu-main|oc-1|bug|sheet"
    assert first["document_title"] == "aitest-bug表格【飞书机器人】"
    assert first["sheet_id"] == "gid-1"


def test_feishu_archive_writer_bitable_creates_once_then_adds_records(tmp_path, monkeypatch):
    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services.feishu import feishu_archive_writer_service as writer

    monkeypatch.setattr(
        writer,
        "get_bot_connector",
        lambda connector_id: {
            "id": connector_id,
            "platform": "feishu",
            "agent_name": "飞书机器人",
            "app_id": "app-id",
            "app_secret": "app-secret",
        },
    )
    monkeypatch.setattr(writer, "_get_tenant_access_token", lambda connector: "tenant-token")

    post_calls = []

    def fake_post(path, *, token, payload, timeout=15):
        post_calls.append({"path": path, "payload": payload, "token": token})
        if path == "/open-apis/bitable/v1/apps":
            return {"app": {"app_token": "base-1"}}
        if path == "/open-apis/bitable/v1/apps/base-1/tables":
            return {"table": {"table_id": "tbl-1"}}
        if path == "/open-apis/bitable/v1/apps/base-1/tables/tbl-1/records":
            return {"record": {"record_id": f"rec-{len(post_calls)}"}}
        return {}

    monkeypatch.setattr(writer, "_post_feishu_json", fake_post)

    task = {"title": "监听 bug", "description": "监听新增bug后归档"}
    action = {
        "id": "action-1",
        "type": "project_chat",
        "params": {
            "workflow": "feishu_bot_auto_archive_to_doc_table",
            "categories": {"bug": "bitable", "需求": "bitable", "功能": "bitable", "会议": "bitable"},
        },
    }
    source_context = {
        "connector_id": "feishu-main",
        "external_chat_id": "oc-1",
        "external_chat_name": "aitest",
        "external_message_id": "om-1",
        "sender_id": "ou-1",
    }

    first = writer.archive_feishu_task_message(
        task=task,
        action=action,
        message_text="新增bug：登录页报错",
        source_context=source_context,
    )
    second = writer.archive_feishu_task_message(
        task=task,
        action=action,
        message_text="新增bug：导航丢失",
        source_context={**source_context, "external_message_id": "om-2"},
    )

    app_calls = [item for item in post_calls if item["path"] == "/open-apis/bitable/v1/apps"]
    table_calls = [item for item in post_calls if item["path"] == "/open-apis/bitable/v1/apps/base-1/tables"]
    record_calls = [item for item in post_calls if item["path"].endswith("/records")]

    assert len(app_calls) == 1
    assert len(table_calls) == 1
    assert len(record_calls) == 2
    assert first["created"] is True
    assert second["created"] is False
    assert first["writer_type"] == "bitable"
    assert first["archive_key"] == "feishu-main|oc-1|bug|bitable"
    assert first["document_title"] == "aitest-bug表格【飞书机器人】"
    assert first["table_id"] == "tbl-1"


def test_feishu_archive_writer_cli_user_docx_creates_once_then_updates(tmp_path, monkeypatch):
    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services.feishu import feishu_archive_writer_service as writer

    monkeypatch.setattr(
        writer,
        "get_bot_connector",
        lambda connector_id: {
            "id": connector_id,
            "platform": "feishu",
            "agent_name": "飞书机器人",
            "tenant_domain": "tenant.feishu.cn",
        },
    )
    monkeypatch.setattr(
        writer,
        "_get_tenant_access_token",
        lambda connector: (_ for _ in ()).throw(AssertionError("CLI user mode must not use bot token")),
    )

    cli_calls = []

    def fake_cli(args, *, timeout=90):
        cli_calls.append(args)
        if args[:2] == ["docs", "+create"]:
            return {"document": {"document_id": "doc-cli-1", "url": "https://tenant.feishu.cn/docx/doc-cli-1"}}
        if args[:2] == ["docs", "+update"]:
            return {"ok": True}
        return {}

    monkeypatch.setattr(writer, "_run_lark_cli_json", fake_cli)

    task = {"title": "监听 bug", "description": "监听新增bug后归档"}
    action = {
        "id": "action-1",
        "type": "project_chat",
        "params": {
            "workflow": "feishu_bot_auto_archive_to_doc_table",
            "writer_type": "docx",
            "writer_mode": "lark_cli_user",
            "categories": {"bug": {}, "需求": {}, "功能": {}, "会议": {}},
        },
    }
    source_context = {
        "connector_id": "feishu-main",
        "external_chat_id": "oc-1",
        "external_chat_name": "aitest",
        "external_message_id": "om-1",
        "sender_id": "ou-1",
    }

    first = writer.archive_feishu_task_message(
        task=task,
        action=action,
        message_text="新增bug：登录页报错",
        source_context=source_context,
    )
    second = writer.archive_feishu_task_message(
        task=task,
        action=action,
        message_text="新增bug：导航丢失",
        source_context={**source_context, "external_message_id": "om-2"},
    )

    assert [call[:2] for call in cli_calls] == [["docs", "+create"], ["docs", "+update"]]
    assert first["created"] is True
    assert second["created"] is False
    assert first["writer_mode"] == "lark_cli_user"
    assert first["archive_key"] == "feishu-main|oc-1|bug|docx|lark_cli_user"
    assert first["doc_url"] == "https://tenant.feishu.cn/docx/doc-cli-1"


def test_feishu_archive_writer_cli_user_sheet_creates_once_then_appends(tmp_path, monkeypatch):
    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services.feishu import feishu_archive_writer_service as writer

    monkeypatch.setattr(
        writer,
        "get_bot_connector",
        lambda connector_id: {"id": connector_id, "platform": "feishu", "agent_name": "飞书机器人"},
    )
    monkeypatch.setattr(
        writer,
        "_get_tenant_access_token",
        lambda connector: (_ for _ in ()).throw(AssertionError("CLI user mode must not use bot token")),
    )

    cli_calls = []

    def fake_cli(args, *, timeout=90):
        cli_calls.append(args)
        if args[:2] == ["sheets", "+create"]:
            return {"spreadsheet": {"spreadsheet_token": "sht-cli-1", "sheet_id": "gid-1", "url": "https://tenant.feishu.cn/sheets/sht-cli-1"}}
        if args[:2] == ["sheets", "+append"]:
            return {"ok": True}
        return {}

    monkeypatch.setattr(writer, "_run_lark_cli_json", fake_cli)

    task = {"title": "监听 bug", "description": "监听新增bug后归档"}
    action = {
        "id": "action-1",
        "type": "project_chat",
        "params": {
            "workflow": "feishu_bot_auto_archive_to_doc_table",
            "categories": {"bug": {"writer_type": "sheet", "writer_mode": "lark_cli_user"}},
        },
    }
    source_context = {
        "connector_id": "feishu-main",
        "external_chat_id": "oc-1",
        "external_chat_name": "aitest",
        "external_message_id": "om-1",
        "sender_id": "ou-1",
    }

    first = writer.archive_feishu_task_message(
        task=task,
        action=action,
        message_text="新增bug：登录页报错",
        source_context=source_context,
    )
    second = writer.archive_feishu_task_message(
        task=task,
        action=action,
        message_text="新增bug：导航丢失",
        source_context={**source_context, "external_message_id": "om-2"},
    )

    assert [call[:2] for call in cli_calls] == [["sheets", "+create"], ["sheets", "+append"]]
    assert first["writer_type"] == "sheet"
    assert first["writer_mode"] == "lark_cli_user"
    assert first["archive_key"] == "feishu-main|oc-1|bug|sheet|lark_cli_user"
    assert first["created"] is True
    assert second["created"] is False
    assert first["sheet_id"] == "gid-1"


def test_feishu_archive_writer_cli_user_bitable_accepts_string_category_config(tmp_path, monkeypatch):
    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services.feishu import feishu_archive_writer_service as writer

    monkeypatch.setattr(
        writer,
        "get_bot_connector",
        lambda connector_id: {"id": connector_id, "platform": "feishu", "agent_name": "飞书机器人"},
    )
    monkeypatch.setattr(
        writer,
        "_get_tenant_access_token",
        lambda connector: (_ for _ in ()).throw(AssertionError("CLI user mode must not use bot token")),
    )

    cli_calls = []
    table_field_payloads = []

    def fake_cli(args, *, timeout=90):
        cli_calls.append(args)
        if args[:2] == ["base", "+base-create"]:
            return {"base": {"app_token": "app-cli-1", "url": "https://tenant.feishu.cn/base/app-cli-1"}}
        if args[:2] == ["base", "+table-create"]:
            table_field_payloads.append(json.loads(args[args.index("--fields") + 1]))
            return {"fields": [{"id": "fld-should-not-be-used"}], "table": {"id": "tbl-cli-1"}}
        if args[:2] == ["base", "+record-upsert"]:
            return {"fields": [{"id": "fld-should-not-be-used"}], "record": {"id": f"rec-cli-{len(cli_calls)}"}}
        return {}

    monkeypatch.setattr(writer, "_run_lark_cli_json", fake_cli)

    task = {"title": "监听 bug", "description": "监听新增bug后归档"}
    action = {
        "id": "action-1",
        "type": "project_chat",
        "params": {
            "workflow": "feishu_bot_auto_archive_to_doc_table",
            "writer_mode": "lark_cli_user",
            "categories": {"bug": "bitable", "需求": "bitable", "功能": "bitable", "会议": "docx"},
        },
    }
    source_context = {
        "connector_id": "feishu-main",
        "external_chat_id": "oc-1",
        "external_chat_name": "aitest",
        "external_message_id": "om-1",
        "sender_id": "ou-1",
    }

    first = writer.archive_feishu_task_message(
        task=task,
        action=action,
        message_text="新增bug：登录页报错",
        source_context=source_context,
    )
    second = writer.archive_feishu_task_message(
        task=task,
        action=action,
        message_text="新增bug：导航丢失",
        source_context={**source_context, "external_message_id": "om-2"},
    )

    command_pairs = [call[:2] for call in cli_calls]
    assert command_pairs[:3] == [
        ["base", "+base-create"],
        ["base", "+table-create"],
        ["base", "+record-upsert"],
    ]
    assert [item for item in command_pairs if item == ["base", "+record-upsert"]] == [
        ["base", "+record-upsert"],
        ["base", "+record-upsert"],
    ]
    assert ["base", "+field-list"] in command_pairs
    attachment_fields = [item for item in table_field_payloads[0] if item["name"] == "图片附件"]
    assert attachment_fields == [{"name": "图片附件", "type": "attachment"}]
    attachment_text_fields = [item for item in table_field_payloads[0] if item["name"] == "图片/附件"]
    assert attachment_text_fields == [{"name": "图片/附件", "type": "text"}]
    assert first["writer_type"] == "bitable"
    assert first["writer_mode"] == "lark_cli_user"
    assert first["archive_key"] == "feishu-main|oc-1|bug|bitable|lark_cli_user"
    assert first["created"] is True
    assert second["created"] is False
    assert first["table_id"] == "tbl-cli-1"
    assert first["doc_url"] == "https://tenant.feishu.cn/base/app-cli-1?table=tbl-cli-1"


def test_feishu_archive_writer_cli_user_bitable_writes_friendly_structured_fields(tmp_path, monkeypatch):
    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services.feishu import feishu_archive_writer_service as writer

    monkeypatch.setattr(
        writer,
        "get_bot_connector",
        lambda connector_id: {"id": connector_id, "platform": "feishu", "agent_name": "飞书机器人"},
    )
    monkeypatch.setattr(
        writer,
        "_get_tenant_access_token",
        lambda connector: (_ for _ in ()).throw(AssertionError("CLI user mode must not use bot token")),
    )

    record_payloads = []

    def fake_cli(args, *, timeout=90):
        if args[:2] == ["base", "+base-create"]:
            return {"base": {"app_token": "app-cli-1", "url": "https://tenant.feishu.cn/base/app-cli-1"}}
        if args[:2] == ["base", "+table-create"]:
            return {"table": {"id": "tbl-cli-1"}}
        if args[:2] == ["base", "+record-upsert"]:
            record_payloads.append(json.loads(args[args.index("--json") + 1]))
            return {"record": {"id": "rec-cli-1"}}
        return {}

    monkeypatch.setattr(writer, "_run_lark_cli_json", fake_cli)

    result = writer.archive_feishu_task_message(
        task={"title": "监听 bug", "description": "监听新增bug后归档"},
        action={
            "id": "action-1",
            "type": "project_chat",
            "params": {
                "workflow": "feishu_bot_auto_archive_to_doc_table",
                "writer_mode": "lark_cli_user",
                "writer_type": "bitable",
                "categories": {"bug": "bitable"},
            },
        },
        message_text=(
            "用户先说客户列表筛选重置异常\n\n"
            "【结构化内容】\n"
            "- 标题：CRM 客户列表页筛选条件重置按钮失效\n"
            "- 问题描述：设置多项筛选条件后，点击重置按钮无法清空。\n"
            "- 复现步骤：\n"
            "  1. 进入客户列表\n"
            "  2. 选择筛选条件\n"
            "  3. 点击重置\n"
            "- 期望结果：筛选条件被清空\n"
            "- 实际结果：筛选条件仍保留\n"
            "- 影响范围：手机端和电脑端均出现\n"
            "- 优先级：中\n"
            "- 负责人：刘蓝天\n"
            "- 提出人：屈行行\n"
            "- 消息链接：https://tenant.feishu.cn/message/om-1"
        ),
        source_context={
            "connector_id": "feishu-main",
            "external_chat_id": "oc-1",
            "external_chat_name": "aitest",
            "sender_id": "ou-1",
            "image_urls": ["https://tenant.feishu.cn/file/image-1"],
        },
    )

    assert result["status"] == "saved"
    assert record_payloads[0]["类型"] == "bug"
    assert record_payloads[0]["标题"] == "CRM 客户列表页筛选条件重置按钮失效"
    assert record_payloads[0]["摘要"] == "设置多项筛选条件后，点击重置按钮无法清空。"
    assert record_payloads[0]["优先级"] == "中"
    assert record_payloads[0]["负责人"] == "刘蓝天"
    assert record_payloads[0]["提出人"] == "屈行行"
    assert record_payloads[0]["来源群"] == "aitest"
    assert record_payloads[0]["图片/附件"] == "https://tenant.feishu.cn/file/image-1"
    assert record_payloads[0]["消息链接"] == "https://tenant.feishu.cn/message/om-1"
    assert record_payloads[0]["问题描述"] == "设置多项筛选条件后，点击重置按钮无法清空。"
    assert "进入客户列表" in record_payloads[0]["复现步骤"]
    assert record_payloads[0]["期望结果"] == "筛选条件被清空"
    assert record_payloads[0]["实际结果"] == "筛选条件仍保留"
    assert record_payloads[0]["影响范围"] == "手机端和电脑端均出现"
    assert "复现步骤" in record_payloads[0]["详细内容"]
    assert "聊天记录" in record_payloads[0]
    assert "external_chat_id" not in record_payloads[0]


def test_feishu_archive_writer_cli_user_bitable_uploads_attachments_from_top_level_record_id(tmp_path, monkeypatch):
    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services.feishu import feishu_archive_writer_service as writer

    monkeypatch.setattr(
        writer,
        "get_bot_connector",
        lambda connector_id: {"id": connector_id, "platform": "feishu", "agent_name": "飞书机器人"},
    )
    monkeypatch.setattr(
        writer,
        "_get_tenant_access_token",
        lambda connector: (_ for _ in ()).throw(AssertionError("CLI user mode must not use bot token")),
    )

    image_path = tmp_path / "bug.png"
    image_path.write_bytes(b"fake image")
    commands = []
    upload_cwds = []

    def fake_cli(args, *, timeout=90, cwd=None):
        commands.append(args)
        if _is_bitable_record_upload_attachment_call(args):
            upload_cwds.append(cwd)
        if args[:2] == ["base", "+base-create"]:
            return {"base": {"app_token": "app-cli-1", "url": "https://tenant.feishu.cn/base/app-cli-1"}}
        if args[:2] == ["base", "+table-create"]:
            return {"table": {"id": "tbl-cli-1"}}
        if args[:2] == ["base", "+record-upsert"]:
            return {"id": "rec-cli-1", "created": True}
        return {}

    monkeypatch.setattr(writer, "_run_lark_cli_json", fake_cli)

    result = writer.archive_feishu_task_message(
        task={"title": "监听 bug", "description": "监听新增bug后归档"},
        action={
            "id": "action-1",
            "type": "project_chat",
            "params": {
                "workflow": "feishu_bot_auto_archive_to_doc_table",
                "writer_mode": "lark_cli_user",
                "writer_type": "bitable",
                "categories": {"bug": "bitable"},
            },
        },
        message_text="新增bug：图片没有归档",
        source_context={
            "connector_id": "feishu-main",
            "external_chat_id": "oc-1",
            "external_chat_name": "aitest",
            "attachment_files": [{"path": str(image_path), "filename": "bug.png"}],
        },
    )

    upload_calls = [args for args in commands if _is_bitable_record_upload_attachment_call(args)]
    put_calls = [args for args in commands if _is_bitable_record_put_call(args)]
    assert result["record_id"] == "rec-cli-1"
    assert result["attachment_upload_count"] == 1
    assert upload_calls
    assert put_calls == []
    assert upload_calls[0][upload_calls[0].index("--as") + 1] == "bot"
    assert upload_calls[0][upload_calls[0].index("--file") + 1] == "./bug.png"
    assert upload_calls[0][upload_calls[0].index("--record-id") + 1] == "rec-cli-1"
    assert upload_cwds == [image_path.parent]


def test_feishu_archive_writer_cli_user_bitable_keeps_record_when_attachment_token_unavailable(tmp_path, monkeypatch):
    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services.feishu import feishu_archive_writer_service as writer

    monkeypatch.setattr(
        writer,
        "get_bot_connector",
        lambda connector_id: {"id": connector_id, "platform": "feishu", "agent_name": "飞书机器人"},
    )
    monkeypatch.setattr(
        writer,
        "_get_tenant_access_token",
        lambda connector: (_ for _ in ()).throw(AssertionError("CLI user mode must not use bot token")),
    )

    image_path = tmp_path / "bug.png"
    image_path.write_bytes(b"fake image")

    def fake_cli(args, *, timeout=90, cwd=None):
        if args[:2] == ["base", "+base-create"]:
            return {"base": {"app_token": "app-cli-1", "url": "https://tenant.feishu.cn/base/app-cli-1"}}
        if args[:2] == ["base", "+table-create"]:
            return {"table": {"id": "tbl-cli-1"}}
        if args[:2] == ["base", "+record-upsert"]:
            return {"id": "rec-cli-1", "created": True}
        if _is_bitable_record_upload_attachment_call(args):
            raise RuntimeError("Attachment file_token is unavailable")
        return {}

    monkeypatch.setattr(writer, "_run_lark_cli_json", fake_cli)

    result = writer.archive_feishu_task_message(
        task={"title": "监听 bug", "description": "监听新增bug后归档"},
        action={
            "id": "action-1",
            "type": "project_chat",
            "params": {
                "workflow": "feishu_bot_auto_archive_to_doc_table",
                "writer_mode": "lark_cli_user",
                "writer_type": "bitable",
                "categories": {"bug": "bitable"},
            },
        },
        message_text="新增bug：图片没有归档",
        source_context={
            "connector_id": "feishu-main",
            "external_chat_id": "oc-1",
            "external_chat_name": "aitest",
            "attachment_files": [{"path": str(image_path), "filename": "bug.png"}],
        },
    )

    assert result["status"] == "saved"
    assert result["record_id"] == "rec-cli-1"
    assert result["attachment_upload_count"] == 0
    assert "Attachment file_token is unavailable" in result["attachment_error"]


def test_feishu_archive_writer_cli_user_bitable_does_not_fallback_to_manual_media_token(tmp_path, monkeypatch):
    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services.feishu import feishu_archive_writer_service as writer

    monkeypatch.setattr(
        writer,
        "get_bot_connector",
        lambda connector_id: {"id": connector_id, "platform": "feishu", "agent_name": "飞书机器人"},
    )
    monkeypatch.setattr(
        writer,
        "_get_tenant_access_token",
        lambda connector: (_ for _ in ()).throw(AssertionError("CLI user mode must not use bot token")),
    )

    image_path = tmp_path / "dead_loop_correct.png"
    image_path.write_bytes(b"fake png image")
    commands = []

    def fake_cli(args, *, timeout=90, cwd=None):
        commands.append(args)
        if args[:2] == ["base", "+base-create"]:
            return {"base": {"app_token": "app-cli-1", "url": "https://tenant.feishu.cn/base/app-cli-1"}}
        if args[:2] == ["base", "+table-create"]:
            return {"table": {"id": "tbl-cli-1"}}
        if args[:2] == ["base", "+field-list"]:
            return {"data": {"fields": [{"id": "fld-attach", "name": "图片附件", "type": "attachment"}]}}
        if args[:2] == ["base", "+record-upsert"]:
            return {"id": "rec-cli-1", "created": True}
        if _is_bitable_record_upload_attachment_call(args):
            raise RuntimeError("Attachment file_token is unavailable")
        return {}

    monkeypatch.setattr(writer, "_run_lark_cli_json", fake_cli)

    result = writer.archive_feishu_task_message(
        task={"title": "监听 bug", "description": "监听新增bug后归档"},
        action={
            "id": "action-1",
            "type": "project_chat",
            "params": {
                "workflow": "feishu_bot_auto_archive_to_doc_table",
                "writer_mode": "lark_cli_user",
                "writer_type": "bitable",
                "categories": {"bug": "bitable"},
            },
        },
        message_text="新增bug：图片没有归档",
        source_context={
            "connector_id": "feishu-main",
            "external_chat_id": "oc-1",
            "external_chat_name": "aitest",
            "attachment_files": [{"path": str(image_path), "filename": "dead_loop_correct.png"}],
        },
    )

    upload_all_calls = [args for args in commands if _is_bitable_upload_all_call(args)]
    put_calls = [args for args in commands if _is_bitable_record_put_call(args)]
    assert result["status"] == "saved"
    assert result["attachment_upload_count"] == 0
    assert "Attachment file_token is unavailable" in result["attachment_error"]
    assert upload_all_calls == []
    assert put_calls == []


def test_feishu_confirmed_archive_reply_mentions_attachment_failure_after_saved_record():
    from services.feishu.feishu_bot_service import _build_confirmed_archive_reply

    reply = _build_confirmed_archive_reply(
        [
            {
                "actions": [
                    {
                        "type": "project_chat",
                        "params": {"workflow": "feishu_bot_auto_archive_to_doc_table"},
                    }
                ],
                "latest_execution": {
                    "action_results": [
                        {
                            "action_type": "project_chat",
                            "status": "saved",
                            "document_title": "数转CRM技术小组-bug文档",
                            "record_id": "rec-cli-1",
                            "attachment_error": "Attachment file_token is unavailable",
                        }
                    ]
                },
            }
        ]
    )

    assert "已保存到：数转CRM技术小组-bug文档" in reply
    assert "记录 ID：rec-cli-1" in reply
    assert "附件图片暂未写入成功" in reply


def test_feishu_archive_writer_cli_user_bitable_uploads_attachments_from_record_id_list(tmp_path, monkeypatch):
    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services.feishu import feishu_archive_writer_service as writer

    monkeypatch.setattr(
        writer,
        "get_bot_connector",
        lambda connector_id: {"id": connector_id, "platform": "feishu", "agent_name": "飞书机器人"},
    )
    monkeypatch.setattr(
        writer,
        "_get_tenant_access_token",
        lambda connector: (_ for _ in ()).throw(AssertionError("CLI user mode must not use bot token")),
    )

    image_path = tmp_path / "bug.png"
    image_path.write_bytes(b"fake image")
    commands = []
    upload_cwds = []

    def fake_cli(args, *, timeout=90, cwd=None):
        commands.append(args)
        if _is_bitable_record_upload_attachment_call(args):
            upload_cwds.append(cwd)
        if args[:2] == ["base", "+base-create"]:
            return {"base": {"app_token": "app-cli-1", "url": "https://tenant.feishu.cn/base/app-cli-1"}}
        if args[:2] == ["base", "+table-create"]:
            return {"table": {"id": "tbl-cli-1"}}
        if args[:2] == ["base", "+field-list"]:
            return {"data": {"fields": [{"id": "fld-attach", "name": "图片附件", "type": "attachment"}]}}
        if args[:2] == ["base", "+record-upsert"]:
            return {
                "ok": True,
                "identity": "user",
                "data": {
                    "created": True,
                    "record": {
                        "data": [["图片没有归档", "bug"]],
                        "field_id_list": ["fld-title", "fld-type"],
                        "fields": ["标题", "类型"],
                        "record_id_list": ["rec-cli-list-1"],
                    },
                },
            }
        if _is_bitable_upload_all_call(args):
            return {"data": {"file_token": "file-token-1"}}
        if _is_bitable_record_put_call(args):
            return {"record": {"record_id": "rec-cli-list-1"}}
        return {}

    monkeypatch.setattr(writer, "_run_lark_cli_json", fake_cli)

    result = writer.archive_feishu_task_message(
        task={"title": "监听 bug", "description": "监听新增bug后归档"},
        action={
            "id": "action-1",
            "type": "project_chat",
            "params": {
                "workflow": "feishu_bot_auto_archive_to_doc_table",
                "writer_mode": "lark_cli_user",
                "writer_type": "bitable",
                "categories": {"bug": "bitable"},
            },
        },
        message_text="新增bug：图片没有归档",
        source_context={
            "connector_id": "feishu-main",
            "external_chat_id": "oc-1",
            "external_chat_name": "aitest",
            "app_token": "unused",
            "attachment_files": [{"path": str(image_path), "filename": "bug.png"}],
        },
    )

    upload_calls = [args for args in commands if _is_bitable_record_upload_attachment_call(args)]
    put_calls = [args for args in commands if _is_bitable_record_put_call(args)]
    assert result["record_id"] == "rec-cli-list-1"
    assert result["attachment_upload_count"] == 1
    assert upload_calls
    assert put_calls == []
    assert upload_calls[0][upload_calls[0].index("--as") + 1] == "bot"
    assert upload_calls[0][upload_calls[0].index("--file") + 1] == "./bug.png"
    assert upload_calls[0][upload_calls[0].index("--record-id") + 1] == "rec-cli-list-1"
    assert upload_cwds == [image_path.parent]


def test_feishu_archive_writer_cli_user_bitable_uploads_attachments_from_object_record_id_list(
    tmp_path,
    monkeypatch,
):
    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services.feishu import feishu_archive_writer_service as writer

    monkeypatch.setattr(
        writer,
        "get_bot_connector",
        lambda connector_id: {"id": connector_id, "platform": "feishu", "agent_name": "飞书机器人"},
    )
    monkeypatch.setattr(
        writer,
        "_get_tenant_access_token",
        lambda connector: (_ for _ in ()).throw(AssertionError("CLI user mode must not use bot token")),
    )

    image_path = tmp_path / "dead_loop_correct.png"
    image_path.write_bytes(b"fake image")
    commands = []
    upload_cwds = []

    def fake_cli(args, *, timeout=90, cwd=None):
        commands.append(args)
        if _is_bitable_record_upload_attachment_call(args):
            upload_cwds.append(cwd)
        if args[:2] == ["base", "+base-create"]:
            return {"base": {"app_token": "app-cli-1", "url": "https://tenant.feishu.cn/base/app-cli-1"}}
        if args[:2] == ["base", "+table-create"]:
            return {"table": {"id": "tbl-cli-1"}}
        if args[:2] == ["base", "+field-list"]:
            return {"data": {"fields": [{"id": "fld-attach", "name": "图片附件", "type": "attachment"}]}}
        if args[:2] == ["base", "+record-upsert"]:
            return {
                "ok": True,
                "data": {
                    "created": True,
                    "record_id_list": [{"record_id": "rec-cli-object-list-1"}],
                },
            }
        if _is_bitable_upload_all_call(args):
            return {"data": {"file_token": "file-token-1"}}
        if _is_bitable_record_put_call(args):
            return {"record": {"record_id": "rec-cli-object-list-1"}}
        return {}

    monkeypatch.setattr(writer, "_run_lark_cli_json", fake_cli)

    result = writer.archive_feishu_task_message(
        task={"title": "监听 bug", "description": "监听新增bug后归档"},
        action={
            "id": "action-1",
            "type": "project_chat",
            "params": {
                "workflow": "feishu_bot_auto_archive_to_doc_table",
                "writer_mode": "lark_cli_user",
                "writer_type": "bitable",
                "categories": {"bug": "bitable"},
            },
        },
        message_text="新增bug：图片没有归档",
        source_context={
            "connector_id": "feishu-main",
            "external_chat_id": "oc-1",
            "external_chat_name": "aitest",
            "app_token": "unused",
            "attachment_files": [{"path": str(image_path), "filename": "dead_loop_correct.png"}],
        },
    )

    upload_calls = [args for args in commands if _is_bitable_record_upload_attachment_call(args)]
    put_calls = [args for args in commands if _is_bitable_record_put_call(args)]
    assert result["record_id"] == "rec-cli-object-list-1"
    assert result["attachment_upload_count"] == 1
    assert upload_calls
    assert put_calls == []
    assert upload_calls[0][upload_calls[0].index("--as") + 1] == "bot"
    assert upload_calls[0][upload_calls[0].index("--file") + 1] == "./dead_loop_correct.png"
    assert upload_calls[0][upload_calls[0].index("--record-id") + 1] == "rec-cli-object-list-1"
    assert upload_cwds == [image_path.parent]


def test_feishu_archive_writer_cli_user_bitable_parses_inline_numbered_markdown(tmp_path, monkeypatch):
    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services.feishu import feishu_archive_writer_service as writer

    monkeypatch.setattr(
        writer,
        "get_bot_connector",
        lambda connector_id: {"id": connector_id, "platform": "feishu", "agent_name": "飞书机器人"},
    )
    monkeypatch.setattr(
        writer,
        "_get_tenant_access_token",
        lambda connector: (_ for _ in ()).throw(AssertionError("CLI user mode must not use bot token")),
    )

    record_payloads = []

    def fake_cli(args, *, timeout=90):
        if args[:2] == ["base", "+base-create"]:
            return {"base": {"app_token": "app-cli-1", "url": "https://tenant.feishu.cn/base/app-cli-1"}}
        if args[:2] == ["base", "+table-create"]:
            return {"table": {"id": "tbl-cli-1"}}
        if args[:2] == ["base", "+record-upsert"]:
            record_payloads.append(json.loads(args[args.index("--json") + 1]))
            return {"record": {"id": "rec-cli-1"}}
        return {}

    monkeypatch.setattr(writer, "_run_lark_cli_json", fake_cli)

    result = writer.archive_feishu_task_message(
        task={"title": "监听 bug", "description": "监听新增bug后归档"},
        action={
            "id": "action-1",
            "type": "project_chat",
            "params": {
                "workflow": "feishu_bot_auto_archive_to_doc_table",
                "writer_mode": "lark_cli_user",
                "writer_type": "bitable",
                "categories": {"bug": "bitable"},
            },
        },
        message_text=(
            "1. **标题**CRM 客户详情页点击图片上传按钮无响应 "
            "2. **问题描述**在CRM后台客户详情模块内，点击图片上传功能按钮无任何反馈，无法正常上传本地图片资料。 "
            "3. **复现步骤** - 登录CRM后台管理系统 - 进入客户列表，打开任意客户详情页面 "
            "- 找到资料图片上传模块，点击上传按钮 - 尝试选择本地图片进行上传操作 "
            "4. **期望结果**点击上传按钮可正常唤起本地文件选择窗口，支持选中图片完成上传操作。 "
            "5. **实际结果**点击图片上传按钮无弹窗、无加载、无任何交互反馈，完全无法执行图片上传。 "
            "6. **影响范围** - 问题在PC端全浏览器环境均可复现 - Windows、Mac 电脑设备均存在该问题 "
            "- 其他功能按钮操作正常，仅图片上传功能异常 - **优先级**：中 - **负责人**：张启明 "
            "- **提出人**：王乐乐。 来源群：aitest；消息链接：无；创建时间：按当前时间记录。"
        ),
        source_context={
            "connector_id": "feishu-main",
            "external_chat_id": "oc-1",
            "external_chat_name": "aitest",
            "sender_id": "ou_2934bdacd659b781726c6323fce62b5b",
        },
    )

    assert result["status"] == "saved"
    assert record_payloads[0]["类型"] == "bug"
    assert record_payloads[0]["标题"] == "CRM 客户详情页点击图片上传按钮无响应"
    assert record_payloads[0]["摘要"].startswith("在CRM后台客户详情模块内")
    assert record_payloads[0]["优先级"] == "中"
    assert record_payloads[0]["负责人"] == "张启明"
    assert record_payloads[0]["提出人"] == "王乐乐"
    assert record_payloads[0]["来源群"] == "aitest"
    assert record_payloads[0]["消息链接"] == "无"
    assert "复现步骤" in record_payloads[0]["详细内容"]
    assert "ou_2934bdacd659b781726c6323fce62b5b" not in record_payloads[0]["提出人"]


def test_feishu_archive_writer_cli_user_bitable_normalizes_at_mentions_in_person_fields(tmp_path, monkeypatch):
    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services.feishu import feishu_archive_writer_service as writer

    monkeypatch.setattr(
        writer,
        "get_bot_connector",
        lambda connector_id: {"id": connector_id, "platform": "feishu", "agent_name": "飞书机器人"},
    )
    monkeypatch.setattr(
        writer,
        "_get_tenant_access_token",
        lambda connector: (_ for _ in ()).throw(AssertionError("CLI user mode must not use bot token")),
    )

    record_payloads = []

    def fake_cli(args, *, timeout=90):
        if args[:2] == ["base", "+base-create"]:
            return {"base": {"app_token": "app-cli-1", "url": "https://tenant.feishu.cn/base/app-cli-1"}}
        if args[:2] == ["base", "+table-create"]:
            return {"table": {"id": "tbl-cli-1"}}
        if args[:2] == ["base", "+record-upsert"]:
            record_payloads.append(json.loads(args[args.index("--json") + 1]))
            return {"record": {"id": "rec-cli-1"}}
        return {}

    monkeypatch.setattr(writer, "_run_lark_cli_json", fake_cli)

    result = writer.archive_feishu_task_message(
        task={"title": "监听 bug", "description": "监听新增bug后归档"},
        action={
            "id": "action-1",
            "type": "project_chat",
            "params": {
                "workflow": "feishu_bot_auto_archive_to_doc_table",
                "writer_mode": "lark_cli_user",
                "writer_type": "bitable",
                "categories": {"bug": "bitable"},
            },
        },
        message_text=(
            "【结构化内容】\n"
            "- 标题：图片记录总是失败\n"
            "- 问题描述：正文可以写入，但图片附件上传经常失败。\n"
            "- 优先级：高\n"
            "- 负责人：@刘蓝天\n"
            "- 提出人：@张亚辉\n"
            "- 来源群：飞书私聊-1a7e3653\n"
        ),
        source_context={
            "connector_id": "feishu-main",
            "external_chat_id": "oc-1",
            "external_chat_name": "aitest",
            "sender_id": "ou-1",
        },
    )

    assert result["status"] == "saved"
    assert record_payloads[0]["负责人"] == "刘蓝天"
    assert record_payloads[0]["提出人"] == "张亚辉"


def test_feishu_archive_writer_defaults_requirement_archive_to_bitable(tmp_path, monkeypatch):
    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services.feishu import feishu_archive_writer_service as writer

    monkeypatch.setattr(
        writer,
        "get_bot_connector",
        lambda connector_id: {"id": connector_id, "platform": "feishu", "agent_name": "飞书机器人"},
    )
    monkeypatch.setattr(
        writer,
        "_get_tenant_access_token",
        lambda connector: (_ for _ in ()).throw(AssertionError("CLI user mode must not use bot token")),
    )

    table_create_calls = []
    record_payloads = []

    def fake_cli(args, *, timeout=90):
        if args[:2] == ["base", "+base-create"]:
            return {"base": {"app_token": "app-cli-req", "url": "https://tenant.feishu.cn/base/app-cli-req"}}
        if args[:2] == ["base", "+table-create"]:
            table_create_calls.append(args)
            return {"table": {"id": "tbl-cli-req"}}
        if args[:2] == ["base", "+record-upsert"]:
            record_payloads.append(json.loads(args[args.index("--json") + 1]))
            return {"record": {"id": "rec-cli-req"}}
        return {}

    monkeypatch.setattr(writer, "_run_lark_cli_json", fake_cli)

    result = writer.archive_feishu_task_message(
        task={"title": "监听需求", "description": "按分类自动归档 bug、需求、功能、会议"},
        action={
            "id": "action-1",
            "type": "project_chat",
            "params": {
                "workflow": "feishu_bot_auto_archive_to_doc_table",
                "writer_mode": "lark_cli_user",
            },
        },
        message_text=(
            "【待归档类型】\n需求\n\n"
            "【结构化内容】\n"
            "- 标题：移动端考勤记录页面\n"
            "- 背景：需要补齐移动端考勤查询能力。\n"
            "- 目标：支持移动端查看每日考勤记录。\n"
            "- 优先级：高\n"
        ),
        source_context={
            "connector_id": "feishu-main",
            "external_chat_id": "oc-1",
            "external_chat_name": "南京嘉华",
        },
    )

    assert result["status"] == "saved"
    assert result["category"] == "需求"
    assert result["writer_type"] == "bitable"
    assert result["table_id"] == "tbl-cli-req"
    assert result["document_title"] == "南京嘉华-需求表格【飞书机器人】"
    assert len(table_create_calls) == 1
    assert record_payloads[0]["类型"] == "需求"


def test_feishu_archive_writer_cli_user_bitable_existing_table_adds_friendly_fields(tmp_path, monkeypatch):
    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services.feishu import feishu_archive_writer_service as writer

    monkeypatch.setattr(
        writer,
        "get_bot_connector",
        lambda connector_id: {"id": connector_id, "platform": "feishu", "agent_name": "飞书机器人"},
    )
    monkeypatch.setattr(
        writer,
        "_get_tenant_access_token",
        lambda connector: (_ for _ in ()).throw(AssertionError("CLI user mode must not use bot token")),
    )
    state_path = tmp_path / "api-data" / "feishu-archive-docs.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "version": 1,
                "archives": {
                    "feishu-main|oc-1|bug|bitable|lark_cli_user": {
                        "app_token": "app-existing",
                        "doc_id": "app-existing",
                        "document_id": "app-existing",
                        "table_id": "tbl-existing",
                        "doc_url": "https://tenant.feishu.cn/base/app-existing",
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    created_fields = []

    def fake_cli(args, *, timeout=90):
        if args[:2] == ["base", "+field-list"]:
            return {"data": {"fields": [{"name": "分类"}, {"name": "机器人"}]}}
        if args[:2] == ["base", "+field-create"]:
            created_fields.append(json.loads(args[args.index("--json") + 1]))
            return {"field": {"id": "fld-new"}, "created": True}
        if args[:2] == ["base", "+record-upsert"]:
            return {"record": {"id": "rec-existing"}}
        return {}

    monkeypatch.setattr(writer, "_run_lark_cli_json", fake_cli)

    result = writer.archive_feishu_task_message(
        task={"title": "监听 bug", "description": "监听新增bug后归档"},
        action={
            "id": "action-1",
            "type": "project_chat",
            "params": {
                "workflow": "feishu_bot_auto_archive_to_doc_table",
                "writer_mode": "lark_cli_user",
                "writer_type": "bitable",
                "categories": {"bug": "bitable"},
            },
        },
        message_text=(
            "【结构化内容】\n"
            "- 标题：登录页报错\n"
            "- 问题描述：输入账号密码后页面直接报错。\n"
            "- 复现步骤：打开登录页，输入账号密码，点击登录。\n"
            "- 期望结果：正常进入系统。\n"
            "- 实际结果：页面提示 500。\n"
            "- 验收标准：修复后可正常登录。\n"
            "- 优先级：高"
        ),
        source_context={"connector_id": "feishu-main", "external_chat_id": "oc-1", "external_chat_name": "aitest"},
    )

    assert result["created"] is False
    created_field_names = [item["name"] for item in created_fields]
    assert "标题" in created_field_names
    assert "摘要" in created_field_names
    assert "问题描述" in created_field_names
    assert "复现步骤" in created_field_names
    assert "期望结果" in created_field_names
    assert "实际结果" in created_field_names
    assert "验收标准" in created_field_names
    assert {"name": "图片附件", "type": "attachment"} in created_fields
    assert "external_chat_id" not in created_field_names


def test_feishu_archive_writer_uses_pending_archive_type_for_requirement_bitable(tmp_path, monkeypatch):
    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services.feishu import feishu_archive_writer_service as writer

    monkeypatch.setattr(
        writer,
        "get_bot_connector",
        lambda connector_id: {"id": connector_id, "platform": "feishu", "agent_name": "飞书机器人"},
    )
    monkeypatch.setattr(
        writer,
        "_get_tenant_access_token",
        lambda connector: (_ for _ in ()).throw(AssertionError("CLI user mode must not use bot token")),
    )

    table_field_payloads = []
    record_payloads = []

    def fake_cli(args, *, timeout=90):
        if args[:2] == ["base", "+base-create"]:
            return {"base": {"app_token": "app-req", "url": "https://tenant.feishu.cn/base/app-req"}}
        if args[:2] == ["base", "+table-create"]:
            table_field_payloads.append(json.loads(args[args.index("--fields") + 1]))
            return {"table": {"id": "tbl-req"}}
        if args[:2] == ["base", "+record-upsert"]:
            record_payloads.append(json.loads(args[args.index("--json") + 1]))
            return {"record": {"id": "rec-req"}}
        return {}

    monkeypatch.setattr(writer, "_run_lark_cli_json", fake_cli)

    result = writer.archive_feishu_task_message(
        task={"title": "飞书机器人多轮信息归档到分类文档表格", "description": "按分类自动归档 bug、需求、功能、会议"},
        action={
            "id": "action-1",
            "type": "project_chat",
            "params": {
                "workflow": "feishu_bot_auto_archive_to_doc_table",
                "writer_mode": "lark_cli_user",
                "categories": {"bug": "bitable", "需求": "bitable", "功能": "bitable", "会议": "docx"},
            },
        },
        message_text=(
            "创建一个新的 UI 风格\n\n"
            "机器人整理结果：\n"
            "【待归档类型】\n需求\n\n"
            "【待归档状态】\n已整理，尚未写入群文档\n\n"
            "【结构化内容】\n"
            "- 标题：创建一个新的 UI 风格\n"
            "- 背景：现有界面风格需要升级\n"
            "- 目标：提供新的 UI 视觉风格\n"
            "- 详细说明：设计一套新的 UI 风格\n"
            "- 验收标准：可在页面中查看并应用\n"
            "- 优先级：中\n"
            "- 负责人：未指定\n"
            "- 提出人：张三\n"
            "- 来源群：产品群\n"
            "- 消息链接：无\n"
            "- 创建时间：2026-05-12"
        ),
        source_context={
            "platform": "feishu",
            "archive_input": "assistant_structured_reply",
            "connector_id": "feishu-main",
            "external_chat_id": "oc-1",
            "external_chat_name": "产品群",
        },
    )

    assert result["status"] == "saved"
    assert result["category"] == "需求"
    assert result["archive_key"] == "feishu-main|oc-1|需求|bitable|lark_cli_user"
    assert result["document_title"] == "产品群-需求表格【飞书机器人】"
    created_field_names = [item["name"] for item in table_field_payloads[0]]
    assert "背景" in created_field_names
    assert "目标" in created_field_names
    assert "详细说明" in created_field_names
    assert "验收标准" in created_field_names
    assert record_payloads[0]["类型"] == "需求"
    assert record_payloads[0]["标题"] == "创建一个新的 UI 风格"
    assert record_payloads[0]["背景"] == "现有界面风格需要升级"


def test_feishu_archive_writer_skips_raw_feishu_auto_archive_message(tmp_path, monkeypatch):
    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services.feishu import feishu_archive_writer_service as writer

    monkeypatch.setattr(
        writer,
        "get_bot_connector",
        lambda connector_id: {"id": connector_id, "platform": "feishu", "agent_name": "飞书机器人"},
    )

    cli_calls = []
    monkeypatch.setattr(writer, "_run_lark_cli_json", lambda *args, **kwargs: cli_calls.append(args) or {})

    result = writer.archive_feishu_task_message(
        task={"title": "监听需求", "description": "按分类自动归档 bug、需求、功能、会议"},
        action={
            "id": "action-1",
            "type": "project_chat",
            "params": {
                "workflow": "feishu_bot_auto_archive_to_doc_table",
                "writer_mode": "lark_cli_user",
                "categories": {"bug": "bitable", "需求": "bitable"},
            },
        },
        message_text="创建一个新的 UI 风格",
        source_context={
            "platform": "feishu",
            "connector_id": "feishu-main",
            "external_chat_id": "oc-1",
            "external_chat_name": "产品群",
        },
    )

    assert result["status"] == "skipped"
    assert "结构化字段" in result["message"]
    assert cli_calls == []


def test_feishu_archive_writer_cli_user_bitable_recreates_deleted_base(tmp_path, monkeypatch):
    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services.feishu import feishu_archive_writer_service as writer

    monkeypatch.setattr(
        writer,
        "get_bot_connector",
        lambda connector_id: {"id": connector_id, "platform": "feishu", "agent_name": "飞书机器人"},
    )
    monkeypatch.setattr(
        writer,
        "_get_tenant_access_token",
        lambda connector: (_ for _ in ()).throw(AssertionError("CLI user mode must not use bot token")),
    )
    state_path = tmp_path / "api-data" / "feishu-archive-docs.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "version": 1,
                "archives": {
                    "feishu-main|oc-1|bug|bitable|lark_cli_user": {
                        "app_token": "app-deleted",
                        "doc_id": "app-deleted",
                        "document_id": "app-deleted",
                        "table_id": "tbl-deleted",
                        "doc_url": "https://tenant.feishu.cn/base/app-deleted",
                        "created_at": "2026-05-12T01:00:00+00:00",
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    commands = []
    record_payloads = []

    def fake_cli(args, *, timeout=90):
        commands.append(args)
        if args[:2] == ["base", "+field-list"]:
            raise RuntimeError(
                'lark-cli 执行失败，请先确认已执行 lark-cli auth login：{"ok":false,"identity":"user",'
                '"error":{"type":"api_error","code":1002,"message":"API call failed: [1002] note has been deleted"}}'
            )
        if args[:2] == ["base", "+base-create"]:
            return {"base": {"app_token": "app-new", "url": "https://tenant.feishu.cn/base/app-new"}}
        if args[:2] == ["base", "+table-create"]:
            return {"table": {"id": "tbl-new"}}
        if args[:2] == ["base", "+record-upsert"]:
            record_payloads.append(json.loads(args[args.index("--json") + 1]))
            return {"record": {"id": "rec-new"}}
        return {}

    monkeypatch.setattr(writer, "_run_lark_cli_json", fake_cli)

    result = writer.archive_feishu_task_message(
        task={"title": "监听 bug", "description": "监听新增bug后归档"},
        action={
            "id": "action-1",
            "type": "project_chat",
            "params": {
                "workflow": "feishu_bot_auto_archive_to_doc_table",
                "writer_mode": "lark_cli_user",
                "writer_type": "bitable",
                "categories": {"bug": "bitable"},
            },
        },
        message_text="新增bug：登录页报错",
        source_context={"connector_id": "feishu-main", "external_chat_id": "oc-1", "external_chat_name": "aitest"},
    )

    command_pairs = [item[:2] for item in commands]
    assert command_pairs[:4] == [
        ["base", "+field-list"],
        ["base", "+base-create"],
        ["base", "+table-create"],
        ["base", "+record-upsert"],
    ]
    assert result["status"] == "saved"
    assert result["created"] is True
    assert result["doc_id"] == "app-new"
    assert result["table_id"] == "tbl-new"
    assert result["record_id"] == "rec-new"
    assert record_payloads[0]["标题"] == "新增bug：登录页报错"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    record = state["archives"]["feishu-main|oc-1|bug|bitable|lark_cli_user"]
    assert record["doc_id"] == "app-new"
    assert record["table_id"] == "tbl-new"
    assert record["recreated_from_deleted"] is True


def test_global_assistant_archive_action_returns_saved(tmp_path, monkeypatch):
    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services.assistant import global_assistant_task_service as tasks

    monkeypatch.setattr(
        tasks,
        "archive_feishu_task_message",
        lambda **kwargs: {
            "status": "saved",
            "archive_key": "feishu-main|oc-1|bug",
            "category": "bug",
            "document_title": "aitest-bug文档【飞书机器人】",
            "document_id": "doc-1",
            "doc_id": "doc-1",
            "created": True,
            "message": "已保存到：aitest-bug文档【飞书机器人】",
        },
    )

    tasks.upsert_global_assistant_task(
        username="tester",
        project_id="proj-1",
        task={
            "id": "task-archive",
            "title": "监听 bug",
            "description": "监听新增bug后归档",
            "status": "todo",
            "triggers": [{"type": "event", "enabled": True, "source": "feishu", "phrases": ["bug"]}],
            "actions": [
                {
                    "id": "action-archive",
                    "type": "project_chat",
                    "label": "归档到群文档",
                    "params": {"workflow": "feishu_bot_auto_archive_to_doc_table"},
                }
            ],
        },
    )

    matches = tasks.process_global_assistant_tasks_for_event(
        username="tester",
        project_id="proj-1",
        message_text="新增bug：登录页报错",
        source_context={"platform": "feishu", "connector_id": "feishu-main", "external_chat_id": "oc-1"},
    )

    result = matches[0]["latest_execution"]["action_results"][0]
    assert result["status"] == "saved"
    assert result["archive_key"] == "feishu-main|oc-1|bug"
    assert result["document_title"] == "aitest-bug文档【飞书机器人】"
    assert result["doc_id"] == "doc-1"


def test_global_assistant_archive_action_preserves_skipped_status(tmp_path, monkeypatch):
    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services.assistant import global_assistant_task_service as tasks

    monkeypatch.setattr(
        tasks,
        "archive_feishu_task_message",
        lambda **kwargs: {
            "status": "skipped",
            "created": False,
            "archive_key": "",
            "category": "",
            "message": "飞书自动归档需要先由机器人整理出结构化字段，已跳过原始消息写入",
        },
    )

    tasks.upsert_global_assistant_task(
        username="tester",
        project_id="proj-1",
        task={
            "id": "task-archive",
            "title": "监听需求",
            "description": "按分类自动归档 bug、需求、功能、会议",
            "status": "todo",
            "triggers": [{"type": "event", "enabled": True, "source": "feishu", "phrases": ["UI"]}],
            "actions": [
                {
                    "id": "action-archive",
                    "type": "project_chat",
                    "label": "归档到群文档",
                    "params": {"workflow": "feishu_bot_auto_archive_to_doc_table"},
                }
            ],
        },
    )

    matches = tasks.process_global_assistant_tasks_for_event(
        username="tester",
        project_id="proj-1",
        message_text="创建一个新的 UI 风格",
        source_context={"platform": "feishu", "connector_id": "feishu-main", "external_chat_id": "oc-1"},
    )

    result = matches[0]["latest_execution"]["action_results"][0]
    assert result["status"] == "skipped"
    assert "结构化字段" in result["message"]
    assert not result["archive_key"]


def test_feishu_confirmed_archive_reply_overrides_model_text():
    from services.feishu.feishu_bot_service import _build_confirmed_archive_reply

    reply = _build_confirmed_archive_reply(
        [
            {
                "actions": [
                    {
                        "type": "project_chat",
                        "params": {"workflow": "feishu_bot_auto_archive_to_doc_table"},
                    }
                ],
                "latest_execution": {
                    "action_results": [
                        {
                            "action_type": "project_chat",
                            "status": "saved",
                            "document_title": "aitest-bug文档【飞书机器人】",
                            "doc_id": "doc-1",
                        }
                    ]
                },
            }
        ]
    )

    assert "已保存到：aitest-bug文档【飞书机器人】" in reply
    assert "文档ID：doc-1" in reply


def test_feishu_archive_truth_prompt_binds_current_group_and_bot():
    from services.feishu.feishu_bot_service import _build_feishu_archive_truth_prompt

    prompt = _build_feishu_archive_truth_prompt(
        {"agent_name": "飞书机器人"},
        {"external_chat_name": "aitest"},
    )

    assert "飞书机器人" in prompt
    assert "aitest" in prompt
    assert "当前群 + 当前机器人 + 分类" in prompt
    assert "禁止回复“已归档”" in prompt
    assert "普通文档、电子表格、多维表格或任务系统" in prompt
    assert "目标资源不存在时按已选择类型创建后再写入" in prompt
    assert "目标多维表格不存在时应创建后再追加记录" not in prompt
    assert "标题、问题描述、复现步骤" not in prompt


def test_feishu_agent_workflow_prompt_uses_ai_tools_and_does_not_force_base():
    from services.feishu.feishu_bot_service import _build_feishu_agent_workflow_prompt

    prompt = _build_feishu_agent_workflow_prompt(
        {"reply_identity": "bot"},
        {
            "source_type": "private_message",
            "connector_id": "feishu-main",
            "external_chat_id": "oc-private",
            "external_chat_name": "飞书私聊",
            "external_message_id": "om-1",
            "workspace_path": "/repo/workspace",
        },
        skill_resource_directory="/repo/.ai-employee/skills/host-marketplace",
    )

    assert "确认发送并记录" in prompt
    assert "不要再次要求用户确认" in prompt
    assert "本地环境和系统提供的工具技能" in prompt
    assert "当前项目本地工作区：/repo/workspace" in prompt
    assert "读取 SKILL.md" in prompt
    assert "搜索/技能安装能力" in prompt
    assert "停止处理的条件只有两类" in prompt
    assert "只要下一步清晰且工具可用，就继续调用工具执行" in prompt
    assert "不要把“下一步最小操作”“请稍后回复重新执行”“暂时未能完成写入”作为最终回复" in prompt
    assert "不要把“记录 bug/需求/功能/会议”固定理解为多维表格" in prompt
    assert "飞书群记录归档默认使用多维表格 Base" not in prompt


def test_feishu_archive_clarification_request_is_skipped(tmp_path, monkeypatch):
    from services.feishu import feishu_archive_writer_service as writer

    monkeypatch.setattr(
        writer,
        "get_bot_connector",
        lambda connector_id: {
            "id": connector_id,
            "platform": "feishu",
            "name": "飞书机器人",
            "agent_name": "飞书机器人",
        },
    )

    archive_calls = []
    monkeypatch.setattr(writer, "_write_docx_archive", lambda **kwargs: archive_calls.append(kwargs) or None)
    monkeypatch.setattr(writer, "_write_sheet_archive", lambda **kwargs: archive_calls.append(kwargs) or None)
    monkeypatch.setattr(writer, "_write_bitable_archive", lambda **kwargs: archive_calls.append(kwargs) or None)
    monkeypatch.setattr(writer, "_write_cli_docx_archive", lambda **kwargs: archive_calls.append(kwargs) or None)
    monkeypatch.setattr(writer, "_write_cli_sheet_archive", lambda **kwargs: archive_calls.append(kwargs) or None)
    monkeypatch.setattr(writer, "_write_cli_bitable_archive", lambda **kwargs: archive_calls.append(kwargs) or None)

    result = writer.archive_feishu_task_message(
        task={
            "id": "task-archive",
            "title": "飞书机器人多轮信息归档到分类文档表格",
            "description": "按分类自动归档 bug、需求、功能、会议",
        },
        action={
            "id": "action-archive",
            "type": "project_chat",
            "label": "归档到群文档",
            "params": {"workflow": "feishu_bot_auto_archive_to_doc_table"},
        },
        message_text="我提问：记录 bug 需要什么信息？请提供模板。",
        source_context={
            "platform": "feishu",
            "connector_id": "feishu-main",
            "external_chat_id": "oc-1",
            "external_chat_name": "aitest",
        },
    )

    assert result["status"] == "skipped"
    assert result["category"] == "澄清请求"
    assert archive_calls == []


def test_feishu_structured_pending_archive_reply_executes_archive_task(tmp_path, monkeypatch):
    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services.assistant import global_assistant_task_service as tasks
    from services.feishu.feishu_bot_service import _process_feishu_archive_tasks_after_reply

    archive_calls = []

    def fake_archive(**kwargs):
        archive_calls.append(kwargs)
        return {
            "status": "saved",
            "archive_key": "feishu-main|oc-1|bug",
            "category": "bug",
            "writer_type": "docx",
            "document_title": "aitest-bug文档【飞书机器人】",
            "document_id": "doc-1",
            "doc_id": "doc-1",
            "created": True,
            "message": "已保存到：aitest-bug文档【飞书机器人】",
        }

    monkeypatch.setattr(tasks, "archive_feishu_task_message", fake_archive)
    tasks.upsert_global_assistant_task(
        username="tester",
        project_id="proj-1",
        task={
            "id": "task-archive",
            "title": "飞书机器人多轮信息归档到分类文档表格",
            "description": "按分类自动归档 bug、需求、功能、会议",
            "status": "todo",
            "listen_enabled": True,
            "triggers": [{"type": "event", "enabled": True, "source": "feishu", "phrases": ["bug"]}],
            "actions": [
                {
                    "id": "action-archive",
                    "type": "project_chat",
                    "label": "归档到群文档",
                    "params": {"workflow": "feishu_bot_auto_archive_to_doc_table"},
                }
            ],
        },
    )

    pre_reply_matches = tasks.process_global_assistant_tasks_for_event(
        username="tester",
        project_id="proj-1",
        message_text="CRM 登录页在微信浏览器顶部导航丢失 bug",
        source_context={"platform": "feishu", "connector_id": "feishu-main", "external_chat_id": "oc-1"},
        skip_auto_archive_actions=True,
    )

    assert pre_reply_matches == []
    assert archive_calls == []

    processed = _process_feishu_archive_tasks_after_reply(
        username="tester",
        project_id="proj-1",
        message_text="CRM 登录页在微信浏览器顶部导航丢失",
        reply_content=(
            "【待归档类型】\nbug\n\n"
            "【待归档状态】\n已整理，尚未写入群文档\n\n"
            "【结构化内容】\n"
            "- 标题：CRM 登录页在微信浏览器顶部导航丢失\n"
            "- 问题描述：微信浏览器内顶部导航区域丢失"
        ),
        source_context={"platform": "feishu", "connector_id": "feishu-main", "external_chat_id": "oc-1"},
        already_matched_tasks=[],
    )

    assert len(archive_calls) == 1
    assert "机器人整理结果" in archive_calls[0]["message_text"]
    assert "问题描述：微信浏览器内顶部导航区域丢失" in archive_calls[0]["message_text"]
    assert [item["id"] for item in processed] == ["task-archive"]
    result = processed[0]["latest_execution"]["action_results"][0]
    assert result["status"] == "saved"
    assert result["document_title"] == "aitest-bug文档【飞书机器人】"


def test_feishu_archive_writer_docx_entry_includes_structured_category_fields(tmp_path, monkeypatch):
    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services.feishu import feishu_archive_writer_service as writer

    monkeypatch.setattr(
        writer,
        "get_bot_connector",
        lambda connector_id: {
            "id": connector_id,
            "platform": "feishu",
            "agent_name": "飞书机器人",
            "app_id": "cli-app",
            "app_secret": "cli-secret",
        },
    )
    monkeypatch.setattr(writer, "_get_tenant_access_token", lambda connector: "tenant-token")

    archive_calls = []

    def fake_write_docx_archive(**kwargs):
        archive_calls.append(kwargs)
        return {
            "document_id": "doc-1",
            "doc_id": "doc-1",
            "doc_url": "https://tenant.feishu.cn/docx/doc-1",
        }, True

    monkeypatch.setattr(writer, "_write_docx_archive", fake_write_docx_archive)

    result = writer.archive_feishu_task_message(
        task={"title": "监听 bug", "description": "按分类自动归档 bug、需求、功能、会议"},
        action={
            "id": "action-archive",
            "type": "project_chat",
            "params": {"workflow": "feishu_bot_auto_archive_to_doc_table", "writer_type": "docx"},
        },
        message_text=(
            "机器人整理结果：\n"
            "【待归档类型】\nbug\n\n"
            "【待归档状态】\n已整理，尚未写入群文档\n\n"
            "【结构化内容】\n"
            "- 标题：登录页报错\n"
            "- 问题描述：输入账号密码后页面直接报错。\n"
            "- 复现步骤：打开登录页，输入账号密码，点击登录。\n"
            "- 期望结果：正常进入系统。\n"
            "- 实际结果：页面提示 500。\n"
            "- 影响范围：全部用户。\n"
            "- 优先级：高\n"
            "- 负责人：张三\n"
            "- 提出人：李四\n"
            "- 来源群：产品群\n"
            "- 消息链接：无\n"
            "- 创建时间：2026-05-12"
        ),
        source_context={
            "platform": "feishu",
            "archive_input": "assistant_structured_reply",
            "connector_id": "feishu-main",
            "external_chat_id": "oc-1",
            "external_chat_name": "产品群",
        },
    )

    assert result["status"] == "saved"
    assert result["writer_type"] == "docx"
    entry = archive_calls[0]["entry"]
    assert "结构化内容：" in entry
    assert "复现步骤：打开登录页，输入账号密码，点击登录。" in entry
    assert "期望结果：正常进入系统。" in entry
    assert "实际结果：页面提示 500。" in entry
    assert "影响范围：全部用户。" in entry


def test_feishu_failed_archive_reply_reports_failure():
    from services.feishu.feishu_bot_service import _build_failed_archive_reply

    reply = _build_failed_archive_reply(
        [
            {
                "actions": [
                    {
                        "type": "project_chat",
                        "params": {"workflow": "feishu_bot_auto_archive_to_doc_table"},
                    }
                ],
                "latest_execution": {
                    "action_results": [
                        {
                            "action_type": "project_chat",
                            "status": "failed",
                            "message": "lark-cli 执行失败：not_found",
                        }
                    ]
                },
            }
        ]
    )

    assert reply == "归档写入失败：lark-cli 执行失败：not_found"


def test_feishu_failed_archive_reply_hides_internal_budget_details():
    from services.feishu.feishu_bot_service import _build_failed_archive_reply

    reply = _build_failed_archive_reply(
        [
            {
                "actions": [
                    {
                        "type": "project_chat",
                        "params": {"workflow": "feishu_bot_auto_archive_to_doc_table"},
                    }
                ],
                "latest_execution": {
                    "action_results": [
                        {
                            "action_type": "project_chat",
                            "status": "failed",
                            "message": "本轮停止原因：已达到工具执行预算上限，尚未获得写入成功结果。",
                        }
                    ]
                },
            }
        ]
    )

    assert "工具执行预算" not in reply
    assert "本轮停止原因" not in reply
    assert "当前处理已暂停" in reply
    assert "不要重复发送同一句“重新执行”" in reply


def test_feishu_structured_pending_archive_reruns_after_failed_pre_match(tmp_path, monkeypatch):
    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services.assistant import global_assistant_task_service as tasks
    from services.feishu.feishu_bot_service import _process_feishu_archive_tasks_after_reply

    calls = []

    def fake_archive(**kwargs):
        calls.append(kwargs)
        return {
            "status": "saved",
            "archive_key": "feishu-main|oc-1|bug|bitable|lark_cli_user",
            "category": "bug",
            "writer_type": "bitable",
            "writer_mode": "lark_cli_user",
            "document_title": "aitest-bug表格【飞书机器人】",
            "document_id": "base-1",
            "doc_id": "base-1",
            "doc_url": "https://tenant.feishu.cn/base/base-1",
            "created": False,
            "message": "已保存到：aitest-bug表格【飞书机器人】",
        }

    monkeypatch.setattr(tasks, "archive_feishu_task_message", fake_archive)
    tasks.upsert_global_assistant_task(
        username="tester",
        project_id="proj-1",
        task={
            "id": "task-archive",
            "title": "飞书机器人多轮信息归档到分类文档表格",
            "description": "按分类自动归档 bug、需求、功能、会议",
            "status": "todo",
            "listen_enabled": True,
            "triggers": [{"type": "event", "enabled": True, "source": "feishu", "phrases": ["bug"]}],
            "actions": [
                {
                    "id": "action-archive",
                    "type": "project_chat",
                    "label": "归档到群文档",
                    "params": {"workflow": "feishu_bot_auto_archive_to_doc_table"},
                }
            ],
        },
    )

    processed = _process_feishu_archive_tasks_after_reply(
        username="tester",
        project_id="proj-1",
        message_text="新增bug：登录页报错",
        reply_content="【待归档类型】\nbug\n\n【待归档状态】\n已整理，尚未写入群文档\n\n【结构化内容】\n- 标题：登录页报错",
        source_context={"platform": "feishu", "connector_id": "feishu-main", "external_chat_id": "oc-1"},
        already_matched_tasks=[
            {
                "id": "task-archive",
                "actions": [
                    {
                        "type": "project_chat",
                        "params": {"workflow": "feishu_bot_auto_archive_to_doc_table"},
                    }
                ],
                "latest_execution": {
                    "action_results": [
                        {"action_type": "project_chat", "status": "failed", "message": "previous failure"}
                    ]
                },
            }
        ],
    )

    assert len(calls) == 1
    assert [item["id"] for item in processed] == ["task-archive"]
    result = processed[0]["latest_execution"]["action_results"][0]
    assert result["status"] == "saved"
    assert result["doc_url"] == "https://tenant.feishu.cn/base/base-1"


def test_feishu_confirmation_retries_recent_pending_archive_without_model(tmp_path, monkeypatch):
    from services.feishu.feishu_bot_service import process_feishu_message_event
    from stores.json.project_store import ProjectConfig, ProjectUserMember

    _client, store_factory = _build_project_chat_runtime_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    store_factory.project_store.upsert_user_member(
        ProjectUserMember(project_id="proj-1", username="tester", role="owner")
    )
    store_factory.bot_connector_store.replace_all(
        [
            {
                "id": "conn-feishu-1",
                "platform": "feishu",
                "name": "飞书机器人",
                "agent_name": "简信软件CMR",
                "enabled": True,
                "project_id": "proj-1",
                "app_id": "cli_xxx",
                "app_secret": "secret_xxx",
            }
        ]
    )
    create_response = _client.post(
        "/api/projects/proj-1/chat/sessions",
        json={
            "title": "飞书私聊：飞书私聊-1a7e3653",
            "source_context": {
                "source_type": "private_message",
                "platform": "feishu",
                "connector_id": "conn-feishu-1",
                "external_chat_id": "oc_private_1",
                "external_chat_name": "飞书私聊-1a7e3653",
            },
        },
    )
    assert create_response.status_code == 200
    session = create_response.json()["session"]
    projects_router = __import__("routers.projects", fromlist=["_append_chat_record"])
    pending_reply = (
        "【待归档类型】\n"
        "bug\n\n"
        "【待归档状态】\n"
        "已整理，尚未写入群归档表\n\n"
        "【目标多维表格】\n"
        "飞书私聊-1a7e3653-bug表格【简信软件CMR】\n\n"
        "【结构化内容】\n"
        "- 标题：npm 安装包报错，无法安装 npm 包\n"
        "- 实际结果：执行 npm install 后安装失败，具体报错见附件截图。"
    )
    projects_router._append_chat_record(
        project_id="proj-1",
        username="tester",
        role="assistant",
        content=pending_reply,
        message_id="bot-reply-pending",
        chat_session_id=session["id"],
        source_context={
            "source_type": "private_message",
            "platform": "feishu",
            "connector_id": "conn-feishu-1",
            "external_chat_id": "oc_private_1",
            "external_chat_name": "飞书私聊-1a7e3653",
            "thread_key": "feishu:conn-feishu-1:chat:oc_private_1",
        },
    )

    from services.assistant import global_assistant_task_service as tasks

    archive_calls = []
    replies = []

    def fake_archive(**kwargs):
        archive_calls.append(kwargs)
        return {
            "status": "saved",
            "archive_key": "conn-feishu-1|oc_private_1|bug|bitable|lark_cli_user",
            "category": "bug",
            "writer_type": "bitable",
            "document_title": "飞书私聊-1a7e3653-bug表格【简信软件CMR】",
            "document_id": "base-1",
            "doc_id": "base-1",
            "doc_url": "https://tenant.feishu.cn/base/base-1",
            "created": True,
            "message": "已保存到：飞书私聊-1a7e3653-bug表格【简信软件CMR】",
        }

    async def fake_run_project_chat_once(**kwargs):
        raise AssertionError("archive confirmation should retry the pending record without calling the model")

    async def fake_reply_feishu_text(connector, **kwargs):
        replies.append((connector, kwargs))

    monkeypatch.setattr(tasks, "archive_feishu_task_message", fake_archive)
    monkeypatch.setattr("services.feishu.feishu_bot_service.run_project_chat_once", fake_run_project_chat_once)
    monkeypatch.setattr("services.feishu.feishu_bot_service._reply_feishu_text", fake_reply_feishu_text)
    tasks.upsert_global_assistant_task(
        username="tester",
        project_id="proj-1",
        task={
            "id": "task-archive",
            "title": "飞书机器人多轮信息归档到分类表格",
            "description": "按分类自动归档 bug、需求、功能、会议",
            "status": "todo",
            "listen_enabled": True,
            "triggers": [{"type": "event", "enabled": True, "source": "feishu", "phrases": ["bug"]}],
            "actions": [
                {
                    "id": "action-archive",
                    "type": "project_chat",
                    "label": "归档到群表格",
                    "params": {"workflow": "feishu_bot_auto_archive_to_doc_table"},
                }
            ],
        },
    )

    class Obj:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    event = Obj(
        event=Obj(
            sender=Obj(sender_type="user", sender_id=Obj(open_id="ou_sender_1")),
            message=Obj(
                chat_type="p2p",
                chat_id="oc_private_1",
                thread_id="",
                message_id="om_retry_1",
                message_type="text",
                content='{"text":"重新执行"}',
                mentions=[],
            ),
        )
    )

    import asyncio

    asyncio.run(process_feishu_message_event("conn-feishu-1", event))

    assert len(archive_calls) == 1
    assert "机器人整理结果" in archive_calls[0]["message_text"]
    assert "npm 安装包报错" in archive_calls[0]["message_text"]
    assert replies[0][1]["message_id"] == "om_retry_1"
    assert "已保存到：飞书私聊-1a7e3653-bug表格【简信软件CMR】" in replies[0][1]["content"]
    latest_messages = store_factory.project_chat_store.list_messages(
        "proj-1",
        "tester",
        limit=20,
        chat_session_id=session["id"],
    )
    assistant_messages = [item for item in latest_messages if str(getattr(item, "role", "") or "") == "assistant"]
    assert assistant_messages[-1].source_context["archive_workflow"]["status"] == "written"


def test_feishu_confirmation_retries_direct_bitable_pending_reply_without_model(tmp_path, monkeypatch):
    from services.feishu.feishu_bot_service import process_feishu_message_event
    from stores.json.project_store import ProjectConfig, ProjectUserMember

    _client, store_factory = _build_project_chat_runtime_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    store_factory.project_store.upsert_user_member(
        ProjectUserMember(project_id="proj-1", username="tester", role="owner")
    )
    store_factory.bot_connector_store.replace_all(
        [
            {
                "id": "conn-feishu-1",
                "platform": "feishu",
                "name": "飞书机器人",
                "agent_name": "简信软件CMR",
                "enabled": True,
                "project_id": "proj-1",
                "app_id": "cli_xxx",
                "app_secret": "secret_xxx",
            }
        ]
    )
    create_response = _client.post(
        "/api/projects/proj-1/chat/sessions",
        json={
            "title": "飞书私聊：飞书私聊-1a7e3653",
            "source_context": {
                "source_type": "private_message",
                "platform": "feishu",
                "connector_id": "conn-feishu-1",
                "external_chat_id": "oc_private_1",
                "external_chat_name": "飞书私聊-1a7e3653",
            },
        },
    )
    assert create_response.status_code == 200
    session = create_response.json()["session"]
    projects_router = __import__("routers.projects", fromlist=["_append_chat_record"])
    pending_reply = (
        "已找到目标“文档”，但它实际是一个飞书多维表格 Base，当前尚未追加数据成功。\n\n"
        "【已定位目标】\n"
        "- 名称：数转CRM技术小组-bug文档\n"
        "- 类型：BITABLE / 多维表格\n"
        "- Base Token：`Jp08b4CKvaUMlks8BfycP8cMnLh`\n\n"
        "【已定位数据表】\n"
        "- 表名：数据表\n"
        "- Table ID：`tbl86f5sPLsaFNW0`\n\n"
        "【待写入内容】\n"
        "- 标题：npm 安装包错\n"
        "- 问题描述：执行 npm 安装包时出现错误，导致依赖无法正常安装。\n"
        "- 复现步骤：执行 `npm install`\n"
        "- 期望结果：npm 包可以正常安装完成。\n"
        "- 实际结果：npm 安装包失败，具体错误见截图。\n"
        "- 影响范围：本地开发环境，影响当前项目依赖安装。\n"
        "- 优先级：高\n"
        "- 负责人：刘蓝天\n"
        "- 提出人：当前飞书私聊用户\n"
        "- 来源群：飞书私聊-1a7e3653\n\n"
        "最小下一步：继续向 `Jp08b4CKvaUMlks8BfycP8cMnLh / tbl86f5sPLsaFNW0` 追加这条 bug 记录。"
    )
    projects_router._append_chat_record(
        project_id="proj-1",
        username="tester",
        role="assistant",
        content=pending_reply,
        message_id="bot-reply-direct-pending",
        chat_session_id=session["id"],
        source_context={
            "source_type": "private_message",
            "platform": "feishu",
            "connector_id": "conn-feishu-1",
            "external_chat_id": "oc_private_1",
            "external_chat_name": "飞书私聊-1a7e3653",
            "thread_key": "feishu:conn-feishu-1:chat:oc_private_1",
        },
    )

    from services.assistant import global_assistant_task_service as tasks

    archive_calls = []
    replies = []

    def fake_archive(**kwargs):
        archive_calls.append(kwargs)
        context = kwargs["source_context"]
        assert context["archive_target_base_token"] == "Jp08b4CKvaUMlks8BfycP8cMnLh"
        assert context["archive_target_table_id"] == "tbl86f5sPLsaFNW0"
        assert context["archive_writer_mode"] == "lark_cli_user"
        return {
            "status": "saved",
            "archive_key": "conn-feishu-1|oc_private_1|bug|bitable|lark_cli_user",
            "category": "bug",
            "writer_type": "bitable",
            "writer_mode": "lark_cli_user",
            "document_title": "数转CRM技术小组-bug文档",
            "document_id": "Jp08b4CKvaUMlks8BfycP8cMnLh",
            "doc_id": "Jp08b4CKvaUMlks8BfycP8cMnLh",
            "table_id": "tbl86f5sPLsaFNW0",
            "record_id": "rec-1",
            "created": False,
            "message": "已保存到：数转CRM技术小组-bug文档",
        }

    async def fake_run_project_chat_once(**kwargs):
        raise AssertionError("direct bitable retry should not call the model")

    async def fake_reply_feishu_text(connector, **kwargs):
        replies.append((connector, kwargs))

    monkeypatch.setattr(tasks, "archive_feishu_task_message", fake_archive)
    monkeypatch.setattr("services.feishu.feishu_bot_service.run_project_chat_once", fake_run_project_chat_once)
    monkeypatch.setattr("services.feishu.feishu_bot_service._reply_feishu_text", fake_reply_feishu_text)
    tasks.upsert_global_assistant_task(
        username="tester",
        project_id="proj-1",
        task={
            "id": "task-archive",
            "title": "飞书机器人多轮信息归档到分类表格",
            "description": "按分类自动归档 bug、需求、功能、会议",
            "status": "todo",
            "listen_enabled": True,
            "triggers": [{"type": "event", "enabled": True, "source": "feishu", "phrases": ["bug"]}],
            "actions": [
                {
                    "id": "action-archive",
                    "type": "project_chat",
                    "label": "归档到群表格",
                    "params": {"workflow": "feishu_bot_auto_archive_to_doc_table"},
                }
            ],
        },
    )

    class Obj:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    event = Obj(
        event=Obj(
            sender=Obj(sender_type="user", sender_id=Obj(open_id="ou_sender_1")),
            message=Obj(
                chat_type="p2p",
                chat_id="oc_private_1",
                thread_id="",
                message_id="om_retry_direct_1",
                message_type="text",
                content='{"text":"重新执行"}',
                mentions=[],
            ),
        )
    )

    import asyncio

    asyncio.run(process_feishu_message_event("conn-feishu-1", event))

    assert len(archive_calls) == 1
    assert "【待写入内容】" in archive_calls[0]["message_text"]
    assert "npm 安装包错" in archive_calls[0]["message_text"]
    assert replies[0][1]["message_id"] == "om_retry_direct_1"
    assert "已保存到：数转CRM技术小组-bug文档" in replies[0][1]["content"]


def test_feishu_confirmation_retries_direct_bitable_attachment_pending_reply_without_model(tmp_path, monkeypatch):
    from services.feishu.feishu_bot_service import process_feishu_message_event
    from stores.json.project_store import ProjectConfig, ProjectUserMember

    _client, store_factory = _build_project_chat_runtime_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    store_factory.project_store.upsert_user_member(
        ProjectUserMember(project_id="proj-1", username="tester", role="owner")
    )
    store_factory.bot_connector_store.replace_all(
        [
            {
                "id": "conn-feishu-1",
                "platform": "feishu",
                "name": "飞书机器人",
                "agent_name": "简信软件CMR",
                "enabled": True,
                "project_id": "proj-1",
                "app_id": "cli_xxx",
                "app_secret": "secret_xxx",
            }
        ]
    )
    create_response = _client.post(
        "/api/projects/proj-1/chat/sessions",
        json={
            "title": "飞书私聊：飞书私聊-1a7e3653",
            "source_context": {
                "source_type": "private_message",
                "platform": "feishu",
                "connector_id": "conn-feishu-1",
                "external_chat_id": "oc_private_1",
                "external_chat_name": "飞书私聊-1a7e3653",
            },
        },
    )
    assert create_response.status_code == 200
    session = create_response.json()["session"]

    workspace_tmp = Path.cwd().parent.parent / "tmp" / "pytest-feishu-direct-attachment"
    workspace_tmp.mkdir(parents=True, exist_ok=True)
    image_path = workspace_tmp / "user_bug_source.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n")

    projects_router = __import__("routers.projects", fromlist=["_append_chat_record"])
    pending_reply = (
        "已部分完成：已根据图片模拟创建了一条 bug 记录，但图片附件还没有成功写入附件字段。\n\n"
        "保存位置：`数转CRM技术小组-bug文档`\n"
        "Base：`Jp08b4CKvaUMlks8BfycP8cMnLh`\n"
        "数据表：`tbl86f5sPLsaFNW0`\n"
        "记录 ID：`recvjtcMhhvfVf`\n\n"
        "已下载图片到本地：\n"
        f"`{image_path}`\n\n"
        "下一步最小操作：把该图片上传到这条记录的 `附件 / fldwq2POgh` 字段。"
    )
    projects_router._append_chat_record(
        project_id="proj-1",
        username="tester",
        role="assistant",
        content=pending_reply,
        message_id="bot-reply-attachment-pending",
        chat_session_id=session["id"],
        source_context={
            "source_type": "private_message",
            "platform": "feishu",
            "connector_id": "conn-feishu-1",
            "external_chat_id": "oc_private_1",
            "external_chat_name": "飞书私聊-1a7e3653",
            "thread_key": "feishu:conn-feishu-1:chat:oc_private_1",
        },
    )

    from services.feishu import feishu_archive_writer_service as writer

    lark_calls = []
    replies = []

    def fake_run_lark_cli_json(command, timeout=90, cwd=None):
        lark_calls.append((command, cwd))
        if _is_bitable_record_upload_attachment_call(command):
            assert command[command.index("--base-token") + 1] == "Jp08b4CKvaUMlks8BfycP8cMnLh"
            assert command[command.index("--table-id") + 1] == "tbl86f5sPLsaFNW0"
            assert command[command.index("--record-id") + 1] == "recvjtcMhhvfVf"
            assert command[command.index("--field-id") + 1] == "fldwq2POgh"
            assert command[command.index("--as") + 1] == "bot"
            assert command[command.index("--file") + 1] == "./user_bug_source.png"
            assert cwd == image_path.parent
            return {"data": {"record_id": "recvjtcMhhvfVf"}}
        raise AssertionError(f"unexpected lark-cli call: {command}")

    async def fake_run_project_chat_once(**kwargs):
        raise AssertionError("direct attachment retry should not call the model")

    async def fake_reply_feishu_text(connector, **kwargs):
        replies.append((connector, kwargs))

    monkeypatch.setattr(writer, "_run_lark_cli_json", fake_run_lark_cli_json)
    monkeypatch.setattr("services.feishu.feishu_bot_service.run_project_chat_once", fake_run_project_chat_once)
    monkeypatch.setattr("services.feishu.feishu_bot_service._reply_feishu_text", fake_reply_feishu_text)

    class Obj:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    event = Obj(
        event=Obj(
            sender=Obj(sender_type="user", sender_id=Obj(open_id="ou_sender_1")),
            message=Obj(
                chat_type="p2p",
                chat_id="oc_private_1",
                thread_id="",
                message_id="om_retry_attachment_1",
                message_type="text",
                content='{"text":"重新执行"}',
                mentions=[],
            ),
        )
    )

    import asyncio

    asyncio.run(process_feishu_message_event("conn-feishu-1", event))

    assert len(lark_calls) == 1
    assert replies[0][1]["message_id"] == "om_retry_attachment_1"
    assert "已把附件写入：数转CRM技术小组-bug文档" in replies[0][1]["content"]
    assert "记录 ID：recvjtcMhhvfVf" in replies[0][1]["content"]
    assert not image_path.exists()


def test_feishu_confirmation_executes_direct_bitable_create_with_resource_ref_without_model(tmp_path, monkeypatch):
    from services.feishu.feishu_bot_service import process_feishu_message_event
    from stores.json.project_store import ProjectConfig, ProjectUserMember

    _client, store_factory = _build_project_chat_runtime_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    store_factory.project_store.upsert_user_member(
        ProjectUserMember(project_id="proj-1", username="tester", role="owner")
    )
    store_factory.bot_connector_store.replace_all(
        [
            {
                "id": "conn-feishu-1",
                "platform": "feishu",
                "name": "飞书机器人",
                "agent_name": "简信软件CMR",
                "enabled": True,
                "project_id": "proj-1",
                "app_id": "cli_xxx",
                "app_secret": "secret_xxx",
            }
        ]
    )
    create_response = _client.post(
        "/api/projects/proj-1/chat/sessions",
        json={
            "title": "飞书私聊：飞书私聊-1a7e3653",
            "source_context": {
                "source_type": "private_message",
                "platform": "feishu",
                "connector_id": "conn-feishu-1",
                "external_chat_id": "oc_private_1",
                "external_chat_name": "飞书私聊-1a7e3653",
            },
        },
    )
    assert create_response.status_code == 200
    session = create_response.json()["session"]

    projects_router = __import__("routers.projects", fromlist=["_append_chat_record"])
    pending_reply = (
        "未完成保存；本轮已定位到你这条消息里的图片，并确认了 `数转CRM技术小组-bug文档` 字段结构，"
        "但还没有收到“记录创建 + 附件上传成功”的返回，所以不能说已保存。\n\n"
        "【待归档类型】\n"
        "bug\n\n"
        "【目标文档】\n"
        "`数转CRM技术小组-bug文档`\n"
        "- Base：`Jp08b4CKvaUMlks8BfycP8cMnLh`\n"
        "- 数据表：`tbl86f5sPLsaFNW0`\n"
        "- 附件字段：`fldwq2POgh`\n\n"
        "【已定位图片】\n"
        "- 消息 ID：`om_x100b6f75451de080c4d0bf0535de071`\n"
        "- 图片 key：`img_v3_0211l_1e327be9-2ac7-4b5c-8f98-a9467462eddg`\n\n"
        "【结构化内容】\n"
        "- 标题：Bug：记录 bug 时机器人反复回复暂时未能完成写入，形成死循环\n"
        "- 问题描述：用户在记录 bug 并多次回复“继续 / 重新执行”后，机器人持续返回失败提示。\n"
        "- 优先级：高\n"
        "- 提出人：刘蓝天\n"
        "- 来源群：飞书私聊-1a7e3653\n\n"
        "下一步最小操作：下载图片，创建 bug 记录，并把图片上传到附件字段 `fldwq2POgh`。"
    )
    projects_router._append_chat_record(
        project_id="proj-1",
        username="tester",
        role="assistant",
        content=pending_reply,
        message_id="bot-reply-direct-create-pending",
        chat_session_id=session["id"],
        source_context={
            "source_type": "private_message",
            "platform": "feishu",
            "connector_id": "conn-feishu-1",
            "external_chat_id": "oc_private_1",
            "external_chat_name": "飞书私聊-1a7e3653",
            "thread_key": "feishu:conn-feishu-1:chat:oc_private_1",
        },
    )

    workspace_tmp = Path.cwd().parent.parent / "tmp" / "pytest-feishu-direct-create"
    workspace_tmp.mkdir(parents=True, exist_ok=True)
    downloaded_path = workspace_tmp / "dead_loop_correct.png"
    archive_calls = []
    replies = []

    def fake_download_resource(connector, *, connector_id, message_id, file_key, resource_type):
        assert connector_id == "conn-feishu-1"
        assert message_id == "om_x100b6f75451de080c4d0bf0535de071"
        assert file_key == "img_v3_0211l_1e327be9-2ac7-4b5c-8f98-a9467462eddg"
        assert resource_type == "image"
        downloaded_path.write_bytes(b"\x89PNG\r\n\x1a\n")
        return {
            "file_key": file_key,
            "type": resource_type,
            "filename": downloaded_path.name,
            "path": str(downloaded_path),
            "url": "/api/bot-events/feishu/resources/dead_loop_correct.png",
        }

    def fake_archive(**kwargs):
        archive_calls.append(kwargs)
        context = kwargs["source_context"]
        assert context["archive_target_base_token"] == "Jp08b4CKvaUMlks8BfycP8cMnLh"
        assert context["archive_target_table_id"] == "tbl86f5sPLsaFNW0"
        assert context["archive_writer_mode"] == "lark_cli_user"
        assert context["attachment_files"][0]["path"] == str(downloaded_path)
        assert "机器人整理结果" in kwargs["message_text"]
        assert "结构化内容" in kwargs["message_text"]
        return {
            "status": "saved",
            "archive_key": "conn-feishu-1|oc_private_1|bug|bitable|lark_cli_user",
            "category": "bug",
            "writer_type": "bitable",
            "writer_mode": "lark_cli_user",
            "document_title": "数转CRM技术小组-bug文档",
            "document_id": "Jp08b4CKvaUMlks8BfycP8cMnLh",
            "doc_id": "Jp08b4CKvaUMlks8BfycP8cMnLh",
            "table_id": "tbl86f5sPLsaFNW0",
            "record_id": "recvjsuccess",
            "attachment_upload_count": 1,
            "message": "已保存到：数转CRM技术小组-bug文档",
        }

    async def fake_run_project_chat_once(**kwargs):
        raise AssertionError("direct bitable create retry should not call the model")

    async def fake_reply_feishu_text(connector, **kwargs):
        replies.append((connector, kwargs))

    monkeypatch.setattr("services.feishu.feishu_bot_service._download_feishu_message_resource", fake_download_resource)
    monkeypatch.setattr("services.feishu.feishu_bot_service.archive_feishu_task_message", fake_archive)
    monkeypatch.setattr("services.feishu.feishu_bot_service.run_project_chat_once", fake_run_project_chat_once)
    monkeypatch.setattr("services.feishu.feishu_bot_service._reply_feishu_text", fake_reply_feishu_text)

    class Obj:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    event = Obj(
        event=Obj(
            sender=Obj(sender_type="user", sender_id=Obj(open_id="ou_sender_1")),
            message=Obj(
                chat_type="p2p",
                chat_id="oc_private_1",
                thread_id="",
                message_id="om_retry_direct_create_1",
                message_type="text",
                content='{"text":"那你继续"}',
                mentions=[],
            ),
        )
    )

    import asyncio

    asyncio.run(process_feishu_message_event("conn-feishu-1", event))

    assert len(archive_calls) == 1
    assert replies[0][1]["message_id"] == "om_retry_direct_create_1"
    assert "已保存到：数转CRM技术小组-bug文档" in replies[0][1]["content"]
    assert "记录 ID：recvjsuccess" in replies[0][1]["content"]
    assert "请稍后回复" not in replies[0][1]["content"]
    assert not downloaded_path.exists()


def test_feishu_direct_bitable_resource_download_failure_reports_real_cause(tmp_path, monkeypatch):
    from services.feishu.feishu_bot_service import process_feishu_message_event
    from stores.json.project_store import ProjectConfig, ProjectUserMember

    _client, store_factory = _build_project_chat_runtime_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    store_factory.project_store.upsert_user_member(
        ProjectUserMember(project_id="proj-1", username="tester", role="owner")
    )
    store_factory.bot_connector_store.replace_all(
        [
            {
                "id": "conn-feishu-1",
                "platform": "feishu",
                "name": "飞书机器人",
                "agent_name": "简信软件CMR",
                "enabled": True,
                "project_id": "proj-1",
                "app_id": "cli_xxx",
                "app_secret": "secret_xxx",
            }
        ]
    )
    create_response = _client.post(
        "/api/projects/proj-1/chat/sessions",
        json={
            "title": "飞书私聊：飞书私聊-1a7e3653",
            "source_context": {
                "source_type": "private_message",
                "platform": "feishu",
                "connector_id": "conn-feishu-1",
                "external_chat_id": "oc_private_1",
                "external_chat_name": "飞书私聊-1a7e3653",
            },
        },
    )
    assert create_response.status_code == 200
    session = create_response.json()["session"]

    projects_router = __import__("routers.projects", fromlist=["_append_chat_record"])
    pending_reply = (
        "未完成保存；本轮已定位到图片，并确认了目标表字段结构。\n\n"
        "【目标文档】\n"
        "`数转CRM技术小组-bug文档`\n"
        "- Base：`Jp08b4CKvaUMlks8BfycP8cMnLh`\n"
        "- 数据表：`tbl86f5sPLsaFNW0`\n\n"
        "【已定位图片】\n"
        "- 消息 ID：`om_correct_message`\n"
        "- 图片 key：`img_v3_correct_key`\n\n"
        "【结构化内容】\n"
        "- 标题：Bug：附件下载失败应说清楚原因\n"
        "- 问题描述：资源 key 已定位但下载失败时，不应回复没有资源标识。\n"
        "- 优先级：高"
    )
    projects_router._append_chat_record(
        project_id="proj-1",
        username="tester",
        role="assistant",
        content=pending_reply,
        message_id="bot-reply-direct-download-failed",
        chat_session_id=session["id"],
        source_context={
            "source_type": "private_message",
            "platform": "feishu",
            "connector_id": "conn-feishu-1",
            "external_chat_id": "oc_private_1",
            "external_chat_name": "飞书私聊-1a7e3653",
            "thread_key": "feishu:conn-feishu-1:chat:oc_private_1",
        },
    )

    archive_calls = []
    replies = []

    def fake_download_resource(connector, *, connector_id, message_id, file_key, resource_type):
        assert message_id == "om_correct_message"
        assert file_key == "img_v3_correct_key"
        raise RuntimeError(
            "飞书资源下载失败：HTTP 400; message_id=om_correct_message; "
            "file_key=img_v3_correct_key; type=image; code=234002; msg=file_key does not match message_id"
        )

    def fake_archive(**kwargs):
        archive_calls.append(kwargs)
        assert kwargs["source_context"]["resource_download_errors"][0]["file_key"] == "img_v3_correct_key"
        assert "attachment_files" not in kwargs["source_context"]
        return {
            "status": "saved",
            "document_title": "数转CRM技术小组-bug文档",
            "table_id": "tbl86f5sPLsaFNW0",
            "record_id": "recvjdownloadfailed",
            "attachment_upload_count": 0,
        }

    async def fake_run_project_chat_once(**kwargs):
        raise AssertionError("direct bitable create retry should not call the model")

    async def fake_reply_feishu_text(connector, **kwargs):
        replies.append((connector, kwargs))

    monkeypatch.setattr("services.feishu.feishu_bot_service._download_feishu_message_resource", fake_download_resource)
    monkeypatch.setattr("services.feishu.feishu_bot_service.archive_feishu_task_message", fake_archive)
    monkeypatch.setattr("services.feishu.feishu_bot_service.run_project_chat_once", fake_run_project_chat_once)
    monkeypatch.setattr("services.feishu.feishu_bot_service._reply_feishu_text", fake_reply_feishu_text)

    class Obj:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    event = Obj(
        event=Obj(
            sender=Obj(sender_type="user", sender_id=Obj(open_id="ou_sender_1")),
            message=Obj(
                chat_type="p2p",
                chat_id="oc_private_1",
                thread_id="",
                message_id="om_retry_direct_download_failed",
                message_type="text",
                content='{"text":"那你继续"}',
                mentions=[],
            ),
        )
    )

    import asyncio

    asyncio.run(process_feishu_message_event("conn-feishu-1", event))

    assert len(archive_calls) == 1
    reply = replies[0][1]["content"]
    assert "已保存到：数转CRM技术小组-bug文档" in reply
    assert "但附件暂未写入成功：飞书资源下载失败" in reply
    assert "file_key=img_v3_correct_key" in reply
    assert "没有拿到" not in reply
    assert "资源标识" not in reply
    assert "请稍后回复" not in reply


def test_redownload_feishu_message_resources_sanitizes_reserved_log_extra(monkeypatch, caplog):
    from services.feishu import feishu_bot_service

    def fake_download_resource(connector, *, connector_id, message_id, file_key, resource_type):
        raise RuntimeError(
            "飞书资源下载失败：HTTP 400; "
            f"message_id={message_id}; file_key={file_key}; type={resource_type}; "
            "code=234003 msg=File not in msg."
        )

    monkeypatch.setattr(feishu_bot_service, "_download_feishu_message_resource", fake_download_resource)

    import asyncio

    errors: list[dict[str, str]] = []
    with caplog.at_level("INFO"):
        restored = asyncio.run(
            feishu_bot_service._redownload_feishu_message_resources(
                {"id": "conn-feishu-1"},
                connector_id="conn-feishu-1",
                resource_refs=[
                    {
                        "connector_id": "conn-feishu-1",
                        "message_id": "om_x100b6f75857e60bcc4c5389f2c5b97c",
                        "file_key": "img_v3_0211l_d971ac95-7324-4776-b88c-c2fd54844bcg",
                        "type": "image",
                    }
                ],
                download_errors=errors,
            )
        )

    assert restored == []
    assert errors and errors[0]["message"].startswith("飞书资源下载失败：HTTP 400")
    assert "File not in msg." in errors[0]["message"]
    assert any(record.message == "failed to redownload recent feishu message resource" for record in caplog.records)


def test_feishu_archive_writer_uses_direct_bitable_target_from_pending_reply(tmp_path, monkeypatch):
    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services.feishu import feishu_archive_writer_service as writer

    monkeypatch.setattr(
        writer,
        "get_bot_connector",
        lambda connector_id: {
            "id": connector_id,
            "platform": "feishu",
            "agent_name": "简信软件CMR",
            "app_id": "cli-app",
            "app_secret": "cli-secret",
        },
    )
    monkeypatch.setattr(writer, "_get_tenant_access_token", lambda connector: "tenant-token")

    calls = []

    def fake_write_cli_bitable_archive(**kwargs):
        calls.append(kwargs)
        assert kwargs["target_app_token"] == "Jp08b4CKvaUMlks8BfycP8cMnLh"
        assert kwargs["target_table_id"] == "tbl86f5sPLsaFNW0"
        assert kwargs["target_document_title"] == "数转CRM技术小组-bug文档"
        assert kwargs["fields"]["标题"] == "npm 安装包错"
        assert kwargs["fields"]["实际结果"] == "npm 安装包失败，具体错误见截图。"
        return {
            "app_token": "Jp08b4CKvaUMlks8BfycP8cMnLh",
            "base_token": "Jp08b4CKvaUMlks8BfycP8cMnLh",
            "table_id": "tbl86f5sPLsaFNW0",
            "record_id": "rec-1",
            "document_id": "Jp08b4CKvaUMlks8BfycP8cMnLh",
            "doc_id": "Jp08b4CKvaUMlks8BfycP8cMnLh",
            "doc_url": "https://tenant.feishu.cn/base/Jp08b4CKvaUMlks8BfycP8cMnLh?table=tbl86f5sPLsaFNW0",
        }, False

    monkeypatch.setattr(writer, "_write_cli_bitable_archive", fake_write_cli_bitable_archive)

    result = writer.archive_feishu_task_message(
        task={"title": "监听 bug", "description": "按分类自动归档 bug、需求、功能、会议"},
        action={
            "id": "action-archive",
            "type": "project_chat",
            "params": {"workflow": "feishu_bot_auto_archive_to_doc_table"},
        },
        message_text=(
            "机器人整理结果：\n"
            "已找到目标“文档”，但它实际是一个飞书多维表格 Base，当前尚未追加数据成功。\n\n"
            "【已定位目标】\n"
            "- Base Token：`Jp08b4CKvaUMlks8BfycP8cMnLh`\n\n"
            "【已定位数据表】\n"
            "- Table ID：`tbl86f5sPLsaFNW0`\n\n"
            "【待写入内容】\n"
            "- 标题：npm 安装包错\n"
            "- 实际结果：npm 安装包失败，具体错误见截图。"
        ),
        source_context={
            "platform": "feishu",
            "archive_input": "assistant_structured_reply",
            "connector_id": "conn-feishu-1",
            "external_chat_id": "oc_private_1",
            "external_chat_name": "飞书私聊-1a7e3653",
            "archive_target_base_token": "Jp08b4CKvaUMlks8BfycP8cMnLh",
            "archive_target_table_id": "tbl86f5sPLsaFNW0",
            "archive_target_document_title": "数转CRM技术小组-bug文档",
            "archive_writer_mode": "lark_cli_user",
        },
    )

    assert len(calls) == 1
    assert result["status"] == "saved"
    assert result["writer_type"] == "bitable"
    assert result["writer_mode"] == "lark_cli_user"
    assert result["document_title"] == "数转CRM技术小组-bug文档"
    assert result["table_id"] == "tbl86f5sPLsaFNW0"


def test_feishu_archive_writer_bitable_without_record_id_is_not_reported_as_saved(tmp_path, monkeypatch):
    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services.feishu import feishu_archive_writer_service as writer

    monkeypatch.setattr(
        writer,
        "get_bot_connector",
        lambda connector_id: {
            "id": connector_id,
            "platform": "feishu",
            "agent_name": "简信软件CMR",
            "app_id": "cli-app",
            "app_secret": "cli-secret",
        },
    )

    def fake_write_cli_bitable_archive(**kwargs):
        assert kwargs["target_app_token"] == "FCBHbED6Ya1XLUsxslKc4aQRnZg"
        assert kwargs["target_table_id"] == "tblbSsfH5secYYYj"
        return {
            "app_token": "FCBHbED6Ya1XLUsxslKc4aQRnZg",
            "base_token": "FCBHbED6Ya1XLUsxslKc4aQRnZg",
            "table_id": "tblbSsfH5secYYYj",
            "record_id": "",
            "document_id": "FCBHbED6Ya1XLUsxslKc4aQRnZg",
            "doc_id": "FCBHbED6Ya1XLUsxslKc4aQRnZg",
            "doc_url": "https://jianxin1.feishu.cn/base/FCBHbED6Ya1XLUsxslKc4aQRnZg?table=tblbSsfH5secYYYj&view=vewwpUxCVx",
        }, False

    monkeypatch.setattr(writer, "_write_cli_bitable_archive", fake_write_cli_bitable_archive)

    result = writer.archive_feishu_task_message(
        task={"title": "监听功能归档", "description": "按分类自动归档功能"},
        action={
            "id": "action-archive",
            "type": "project_chat",
            "params": {"workflow": "feishu_bot_auto_archive_to_doc_table"},
        },
        message_text=(
            "把这条功能记录写到 https://jianxin1.feishu.cn/base/FCBHbED6Ya1XLUsxslKc4aQRnZg"
            "?table=tblbSsfH5secYYYj&view=vewwpUxCVx\n"
            "【待写入内容】\n"
            "- 标题：移动端考勤记录页面\n"
            "- 类型：功能"
        ),
        source_context={
            "platform": "feishu",
            "archive_input": "assistant_structured_reply",
            "connector_id": "conn-feishu-1",
            "external_chat_id": "oc_private_1",
            "external_chat_name": "南京嘉华",
            "archive_writer_mode": "lark_cli_user",
        },
    )

    assert result["status"] == "pending"
    assert result["table_id"] == "tblbSsfH5secYYYj"
    assert result["record_id"] == ""
    assert "未确认写入成功" in result["message"]
    assert "未拿到记录 ID" in result["message"]


def test_feishu_archive_writer_bitable_without_record_id_falls_back_to_title_lookup(tmp_path, monkeypatch):
    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services.feishu import feishu_archive_writer_service as writer

    monkeypatch.setattr(
        writer,
        "get_bot_connector",
        lambda connector_id: {
            "id": connector_id,
            "platform": "feishu",
            "agent_name": "简信软件CMR",
            "app_id": "cli-app",
            "app_secret": "cli-secret",
        },
    )

    def fake_run_lark_cli_json(args, *, timeout=90, cwd=None):
        if args[:2] == ["base", "+record-upsert"]:
            return {
                "data": {
                    "records": [],
                }
            }
        if args[:2] == ["base", "+record-search"]:
            payload = json.loads(args[args.index("--json") + 1])
            assert payload["keyword"] == "移动端考勤记录页面"
            return {
                "data": {
                    "records": [
                        {
                            "record_id": "rec_found_by_title",
                            "fields": {"标题": "移动端考勤记录页面"},
                        }
                    ]
                }
            }
        raise AssertionError(f"unexpected lark-cli call: {args}")

    monkeypatch.setattr(writer, "_run_lark_cli_json", fake_run_lark_cli_json)

    result = writer.archive_feishu_task_message(
        task={"title": "监听功能归档", "description": "按分类自动归档功能"},
        action={
            "id": "action-archive",
            "type": "project_chat",
            "params": {"workflow": "feishu_bot_auto_archive_to_doc_table"},
        },
        message_text=(
            "把这条功能记录写到 https://jianxin1.feishu.cn/base/FCBHbED6Ya1XLUsxslKc4aQRnZg"
            "?table=tblbSsfH5secYYYj&view=vewwpUxCVx\n"
            "【待写入内容】\n"
            "- 标题：移动端考勤记录页面\n"
            "- 类型：功能"
        ),
        source_context={
            "platform": "feishu",
            "archive_input": "assistant_structured_reply",
            "connector_id": "conn-feishu-1",
            "external_chat_id": "oc_private_1",
            "external_chat_name": "南京嘉华",
            "archive_writer_mode": "lark_cli_user",
        },
    )

    assert result["status"] == "saved"
    assert result["table_id"] == "tblbSsfH5secYYYj"
    assert result["record_id"] == "rec_found_by_title"


def test_feishu_unconfirmed_archive_reply_is_downgraded():
    from services.feishu.feishu_bot_service import _downgrade_unconfirmed_archive_reply

    reply = _downgrade_unconfirmed_archive_reply(
        "已归档，保存到：**bug文档【机器人】**",
        [
            {
                "actions": [
                    {
                        "type": "project_chat",
                        "params": {"workflow": "feishu_bot_auto_archive_to_doc_table"},
                    }
                ],
                "latest_execution": {
                    "action_results": [
                        {"action_type": "project_chat", "status": "recorded"}
                    ]
                },
            }
        ],
    )

    assert "尚未真实写入飞书群归档表" in reply
    assert "已归档" not in reply
    assert "保存到" not in reply
    assert "待归档" in reply


def test_feishu_success_reply_prevents_retrying_older_pending_archive(tmp_path, monkeypatch):
    from services.feishu.feishu_bot_service import process_feishu_message_event
    from stores.json.project_store import ProjectConfig, ProjectUserMember

    client, store_factory = _build_project_chat_runtime_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一", created_by="tester"))
    store_factory.project_store.upsert_user_member(
        ProjectUserMember(project_id="proj-1", username="tester", role="owner")
    )
    store_factory.bot_connector_store.replace_all(
        [
            {
                "id": "conn-feishu-1",
                "platform": "feishu",
                "name": "飞书机器人",
                "enabled": True,
                "project_id": "proj-1",
                "app_id": "cli_xxx",
                "app_secret": "secret_xxx",
                "provider_id": "provider-bot",
                "model_name": "bot-model",
            }
        ]
    )
    create_response = client.post(
        "/api/projects/proj-1/chat/sessions",
        json={
            "title": "飞书私聊：机器人测试群",
            "source_context": {
                "source_type": "private_message",
                "platform": "feishu",
                "connector_id": "conn-feishu-1",
                "external_chat_id": "oc_private_1",
                "external_chat_name": "机器人测试群",
            },
        },
    )
    assert create_response.status_code == 200
    session = create_response.json()["session"]
    projects_router = __import__("routers.projects", fromlist=["_append_chat_record"])
    projects_router._append_chat_record(
        project_id="proj-1",
        username="tester",
        role="assistant",
        content="【待归档类型】\nbug\n\n【待归档状态】\n已整理，尚未写入\n\n【结构化内容】\n- 标题：旧的登录页白屏",
        message_id="bot-reply-pending-old",
        chat_session_id=session["id"],
        source_context={
            "source_type": "private_message",
            "platform": "feishu",
            "connector_id": "conn-feishu-1",
            "external_chat_id": "oc_private_1",
            "external_chat_name": "机器人测试群",
            "thread_key": "feishu:conn-feishu-1:chat:oc_private_1",
        },
    )
    projects_router._append_chat_record(
        project_id="proj-1",
        username="tester",
        role="assistant",
        content=(
            "已保存。\n\n"
            "保存到：\n"
            "`机器人测试群-bug表格【简信软件CMR】`\n\n"
            "已实际核验到：\n"
            "- Base 已存在：`https://jianxin1.feishu.cn/base/LWTibVMqhaQDAnsj381cXfTUnTg`\n"
            "- bug 数据表已存在：`tblWMppfZIFcsrGH`"
        ),
        message_id="bot-reply-saved-new",
        chat_session_id=session["id"],
        source_context={
            "source_type": "private_message",
            "platform": "feishu",
            "connector_id": "conn-feishu-1",
            "external_chat_id": "oc_private_1",
            "external_chat_name": "机器人测试群",
            "thread_key": "feishu:conn-feishu-1:chat:oc_private_1",
            "archive_workflow": {"status": "written", "updated_at": "2026-05-14T00:00:00+00:00"},
        },
    )

    from services.assistant import global_assistant_task_service as tasks

    archive_calls = []
    model_calls = []
    replies = []

    def fake_archive(**kwargs):
        archive_calls.append(kwargs)
        raise AssertionError("success reply must prevent retrying older pending archive")

    class FakeResult:
        content = "如果要继续记录新 bug，请直接发新的问题内容。"

    async def fake_run_project_chat_once(**kwargs):
        model_calls.append(kwargs)
        return FakeResult()

    async def fake_reply_feishu_text(connector, **kwargs):
        replies.append((connector, kwargs))

    monkeypatch.setattr(tasks, "archive_feishu_task_message", fake_archive)
    monkeypatch.setattr("services.feishu.feishu_bot_service.run_project_chat_once", fake_run_project_chat_once)
    monkeypatch.setattr("services.feishu.feishu_bot_service._reply_feishu_text", fake_reply_feishu_text)

    class Obj:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    event = Obj(
        event=Obj(
            sender=Obj(sender_type="user", sender_id=Obj(open_id="ou_sender_1")),
            message=Obj(
                chat_type="p2p",
                chat_id="oc_private_1",
                thread_id="",
                message_id="om_after_saved_1",
                message_type="text",
                content='{"text":"重新执行"}',
                mentions=[],
            ),
        )
    )

    import asyncio

    asyncio.run(process_feishu_message_event("conn-feishu-1", event))

    assert archive_calls == []
    assert len(model_calls) == 1
    assert replies[0][1]["message_id"] == "om_after_saved_1"


def test_feishu_legacy_success_reply_still_blocks_retry_of_older_pending(tmp_path, monkeypatch):
    from services.feishu.feishu_bot_service import process_feishu_message_event
    from stores.json.project_store import ProjectConfig, ProjectUserMember

    client, store_factory = _build_project_chat_runtime_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一", created_by="tester"))
    store_factory.project_store.upsert_user_member(
        ProjectUserMember(project_id="proj-1", username="tester", role="owner")
    )
    store_factory.bot_connector_store.replace_all(
        [
            {
                "id": "conn-feishu-1",
                "platform": "feishu",
                "name": "飞书机器人",
                "enabled": True,
                "project_id": "proj-1",
                "app_id": "cli_xxx",
                "app_secret": "secret_xxx",
                "provider_id": "provider-bot",
                "model_name": "bot-model",
            }
        ]
    )
    create_response = client.post(
        "/api/projects/proj-1/chat/sessions",
        json={
            "title": "飞书私聊：机器人测试群",
            "source_context": {
                "source_type": "private_message",
                "platform": "feishu",
                "connector_id": "conn-feishu-1",
                "external_chat_id": "oc_private_1",
                "external_chat_name": "机器人测试群",
            },
        },
    )
    assert create_response.status_code == 200
    session = create_response.json()["session"]
    projects_router = __import__("routers.projects", fromlist=["_append_chat_record"])
    projects_router._append_chat_record(
        project_id="proj-1",
        username="tester",
        role="assistant",
        content="【待归档类型】\nbug\n\n【待归档状态】\n已整理，尚未写入\n\n【结构化内容】\n- 标题：旧的登录页白屏",
        message_id="bot-reply-pending-old",
        chat_session_id=session["id"],
        source_context={
            "source_type": "private_message",
            "platform": "feishu",
            "connector_id": "conn-feishu-1",
            "external_chat_id": "oc_private_1",
            "external_chat_name": "机器人测试群",
            "thread_key": "feishu:conn-feishu-1:chat:oc_private_1",
        },
    )
    projects_router._append_chat_record(
        project_id="proj-1",
        username="tester",
        role="assistant",
        content="已保存到：机器人测试群-bug表格【简信软件CMR】",
        message_id="bot-reply-saved-legacy",
        chat_session_id=session["id"],
        source_context={
            "source_type": "private_message",
            "platform": "feishu",
            "connector_id": "conn-feishu-1",
            "external_chat_id": "oc_private_1",
            "external_chat_name": "机器人测试群",
            "thread_key": "feishu:conn-feishu-1:chat:oc_private_1",
        },
    )

    from services.assistant import global_assistant_task_service as tasks

    archive_calls = []
    model_calls = []

    def fake_archive(**kwargs):
        archive_calls.append(kwargs)
        raise AssertionError("legacy success reply must still stop retrying older pending archive")

    class FakeResult:
        content = "如果要继续记录新 bug，请直接发新的问题内容。"

    async def fake_run_project_chat_once(**kwargs):
        model_calls.append(kwargs)
        return FakeResult()

    async def fake_reply_feishu_text(connector, **kwargs):
        return None

    monkeypatch.setattr(tasks, "archive_feishu_task_message", fake_archive)
    monkeypatch.setattr("services.feishu.feishu_bot_service.run_project_chat_once", fake_run_project_chat_once)
    monkeypatch.setattr("services.feishu.feishu_bot_service._reply_feishu_text", fake_reply_feishu_text)

    class Obj:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    event = Obj(
        event=Obj(
            sender=Obj(sender_type="user", sender_id=Obj(open_id="ou_sender_1")),
            message=Obj(
                chat_type="p2p",
                chat_id="oc_private_1",
                thread_id="",
                message_id="om_after_legacy_saved_1",
                message_type="text",
                content='{"text":"重新执行"}',
                mentions=[],
            ),
        )
    )

    import asyncio

    asyncio.run(process_feishu_message_event("conn-feishu-1", event))

    assert archive_calls == []
    assert len(model_calls) == 1


def test_feishu_message_event_without_session_binding_auto_creates_session_and_replies(tmp_path, monkeypatch):
    from services.feishu.feishu_bot_service import process_feishu_message_event
    from stores.json.project_store import ProjectConfig, ProjectUserMember

    _client, store_factory = _build_project_chat_runtime_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    store_factory.project_store.upsert_user_member(
        ProjectUserMember(project_id="proj-1", username="tester", role="owner")
    )
    store_factory.bot_connector_store.replace_all(
        [
            {
                "id": "conn-feishu-1",
                "platform": "feishu",
                "name": "飞书机器人",
                "enabled": True,
                "project_id": "",
                "app_id": "cli_xxx",
                "app_secret": "secret_xxx",
            }
        ]
    )

    calls = []
    replies = []

    async def fake_run_project_chat_once(**kwargs):
        calls.append(kwargs)

        class FakeResult:
            content = "你好"

        return FakeResult()

    async def fake_reply_feishu_text(connector, **kwargs):
        replies.append((connector, kwargs))

    monkeypatch.setattr(
        "services.feishu.feishu_bot_service.run_project_chat_once",
        fake_run_project_chat_once,
    )
    monkeypatch.setattr(
        "services.feishu.feishu_bot_service._reply_feishu_text",
        fake_reply_feishu_text,
    )

    class Obj:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    event = Obj(
        event=Obj(
            sender=Obj(sender_type="user", sender_id=Obj(open_id="ou_sender_1")),
            message=Obj(
                chat_type="group",
                chat_id="oc_unbound_group",
                thread_id="",
                message_id="om_message_1",
                message_type="text",
                content='{"text":"@_user_1 你好"}',
                mentions=[Obj(key="@_user_1")],
            ),
        )
    )

    import asyncio

    asyncio.run(process_feishu_message_event("conn-feishu-1", event))

    assert len(calls) == 1
    assert calls[0]["project_id"] == "proj-1"
    assert calls[0]["username"] == "admin"
    req = calls[0]["req"]
    assert req.message == "你好"
    assert req.source_context["source_type"] == "group_message"
    assert req.source_context["external_chat_id"] == "oc_unbound_group"
    assert req.source_context["thread_key"] == "feishu:conn-feishu-1:chat:oc_unbound_group"
    assert store_factory.project_chat_store.get_session("proj-1", "admin", req.chat_session_id) is not None
    assert replies[0][1]["message_id"] == "om_message_1"


def test_resolve_feishu_chat_by_name_reads_search_meta_data(monkeypatch):
    from services.feishu.feishu_bot_service import resolve_feishu_chat_by_name

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        if url.endswith("/tenant_access_token/internal"):
            return FakeResponse({"code": 0, "tenant_access_token": "tenant-token"})
        if url.endswith("/im/v2/chats/search"):
            return FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "items": [
                            {
                                "meta_data": {
                                    "chat_id": "oc_real_group_1",
                                    "name": "产品研发群",
                                    "description": "研发讨论",
                                }
                            }
                        ]
                    },
                }
            )
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr("services.feishu.feishu_bot_service.requests.post", fake_post)

    chat = resolve_feishu_chat_by_name(
        {"app_id": "cli_xxx", "app_secret": "secret_xxx"},
        "产品研发群",
    )

    assert chat == {
        "chat_id": "oc_real_group_1",
        "name": "产品研发群",
        "description": "研发讨论",
    }
    assert calls[1][1]["json"]["query"] == "产品研发群"


def test_resolve_feishu_chat_by_name_user_identity_uses_lark_cli(monkeypatch):
    from services.feishu.feishu_bot_service import resolve_feishu_chat_by_name

    calls = []

    class Completed:
        returncode = 0
        stdout = json.dumps(
            {
                "data": {
                    "items": [
                        {
                            "chat_id": "oc_user_visible_group",
                            "name": "产品研发群",
                        }
                    ]
                }
            },
            ensure_ascii=False,
        )
        stderr = ""

    def fake_run(command, **kwargs):
        calls.append({"command": command, "kwargs": kwargs})
        return Completed()

    monkeypatch.setattr("services.feishu.feishu_bot_service.subprocess.run", fake_run)

    chat = resolve_feishu_chat_by_name(
        {"app_id": "cli_xxx", "app_secret": "secret_xxx"},
        "产品研发群",
        identity="user",
    )

    assert chat["chat_id"] == "oc_user_visible_group"
    command = calls[0]["command"]
    assert command[:3] == ["lark-cli", "im", "+chat-search"]
    assert command[command.index("--as") + 1] == "user"
    assert command[command.index("--query") + 1] == "产品研发群"


def test_resolve_feishu_chat_by_name_user_identity_reports_authorization_hint(monkeypatch):
    from services.feishu.feishu_bot_service import resolve_feishu_chat_by_name

    class Completed:
        returncode = 1
        stdout = json.dumps(
            {
                "ok": False,
                "identity": "user",
                "error": {
                    "type": "api_error",
                    "message": "API call failed: need_user_authorization (user: ou_xxx)",
                },
                "_notice": {
                    "update": {
                        "current": "1.0.18",
                        "latest": "1.0.20",
                    }
                },
            },
            ensure_ascii=False,
        )
        stderr = ""

    monkeypatch.setattr(
        "services.feishu.feishu_bot_service.subprocess.run",
        lambda *args, **kwargs: Completed(),
    )

    with pytest.raises(RuntimeError) as exc_info:
        resolve_feishu_chat_by_name(
            {"app_id": "cli_xxx", "app_secret": "secret_xxx"},
            "产品研发群",
            identity="user",
        )

    message = str(exc_info.value)
    assert "用户身份搜索飞书群需要先完成 lark-cli 用户授权" in message
    assert "lark-cli auth login --scope \"im:chat:read\"" in message
    assert "当前 1.0.18，最新 1.0.20" in message


def test_archive_workflow_state_service_builds_pending_state():
    from services.chat.archive_workflow_state_service import (
        archive_workflow_status,
        build_pending_archive_workflow_state,
        reply_contains_structured_pending_archive,
        with_archive_workflow_state,
    )

    reply = (
        "【待归档类型】\n"
        "bug\n\n"
        "【待归档状态】\n"
        "已整理，尚未写入群归档表\n\n"
        "【结构化内容】\n"
        "- 标题：登录页白屏"
    )

    assert reply_contains_structured_pending_archive(reply) is True
    state = build_pending_archive_workflow_state(reply_content=reply)
    assert state["status"] == "pending_confirmation"
    context = with_archive_workflow_state({"platform": "feishu"}, state)
    assert archive_workflow_status(context) == "pending_confirmation"
    assert context["archive_workflow"]["reply_content"] == reply


def test_run_project_chat_once_persists_pending_archive_workflow_state(tmp_path, monkeypatch):
    from core import config as core_config
    from services.chat.project_chat_execution_service import run_project_chat_once
    from stores.json.project_store import ProjectConfig

    monkeypatch.setenv("CORE_STORE_BACKEND", "json")
    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from routers import projects as projects_router
    from stores import factory as store_factory

    for proxy_name in (
        "role_store",
        "bot_connector_store",
        "system_config_store",
        "project_store",
        "project_chat_store",
        "project_chat_runtime_store",
        "project_chat_task_store",
        "work_session_store",
        "task_tree_evolution_store",
    ):
        getattr(store_factory, proxy_name)._instance = None

    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))

    class _FakeConversationManager:
        def __init__(self, redis):
            self.redis = redis

        async def create_session(self, project_id, employee_id):
            return "session-1"

        async def delete_session(self, session_id):
            return None

    class _FakeOrchestrator:
        async def run(self, **kwargs):
            yield {
                "type": "done",
                "content": (
                    "【待归档类型】\n"
                    "bug\n\n"
                    "【待归档状态】\n"
                    "已整理，尚未写入群归档表\n\n"
                    "【结构化内容】\n"
                    "- 标题：登录页白屏\n"
                    "- 问题描述：打开登录页后页面白屏"
                ),
            }

    monkeypatch.setattr(
        projects_router,
        "_resolve_project_chat_runtime",
        AsyncMock(
            return_value=type(
                "ResolvedRuntime",
                (),
                {
                    "provider_mode": "system",
                    "provider": {"id": "provider-1", "default_model": "glm-test"},
                    "provider_id": "provider-1",
                    "model_name": "glm-test",
                },
            )()
        ),
    )
    monkeypatch.setattr(
        projects_router,
        "_resolve_provider_model_parameter_mode",
        lambda *args, **kwargs: "text",
    )
    monkeypatch.setattr(projects_router, "_collect_runtime_tools", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        projects_router,
        "_maybe_enrich_project_chat_message_with_url_content",
        AsyncMock(side_effect=lambda message, *args, **kwargs: message),
    )
    monkeypatch.setattr(
        projects_router,
        "_build_project_chat_messages",
        lambda *args, **kwargs: [{"role": "user", "content": "记录 bug"}],
    )
    monkeypatch.setattr(
        projects_router,
        "build_chat_runtime_context",
        lambda **kwargs: type(
            "RuntimeContext",
            (),
            {
                "resolved_tools": tuple(),
                "provider_id": "provider-1",
                "model_name": "glm-test",
                "project_id": "proj-1",
                "employee_id": "",
                "username": "tester",
                "chat_session_id": "chat-1",
                "resolved_messages": tuple([{"role": "user", "content": "记录 bug"}]),
                "local_connector": None,
                "workspace_path": "",
                "host_workspace_path": "",
                "local_connector_sandbox_mode": "workspace-write",
                "metadata": {},
            },
        )(),
    )
    monkeypatch.setattr(
        projects_router,
        "_resolve_chat_llm_service_runtime",
        lambda llm_service, *args, **kwargs: llm_service,
    )
    monkeypatch.setattr(
        "services.providers.llm_provider_service.get_llm_provider_service",
        lambda: object(),
    )
    monkeypatch.setattr(projects_router, "get_redis_client", AsyncMock(return_value=object()))
    monkeypatch.setattr(projects_router, "ConversationManager", _FakeConversationManager)
    monkeypatch.setattr(
        projects_router,
        "build_agent_orchestrator",
        lambda *args, **kwargs: _FakeOrchestrator(),
    )
    monkeypatch.setattr(projects_router, "_save_project_chat_memory_snapshot", lambda **kwargs: None)

    from models.requests import ProjectChatReq

    result = __import__("asyncio").run(
        run_project_chat_once(
            project_id="proj-1",
            username="tester",
            req=ProjectChatReq(
                message="记录 bug",
                chat_session_id="chat-1",
                assistant_message_id="assistant-1",
                source_context={
                    "platform": "feishu",
                    "connector_id": "conn-feishu-1",
                    "external_chat_id": "oc-1",
                },
            ),
            auth_payload={"sub": "tester", "role": "admin"},
            save_memory_snapshot=False,
            publish_realtime=False,
        )
    )

    assert "待归档状态" in result.content
    messages = store_factory.project_chat_store.list_messages(
        "proj-1",
        "tester",
        limit=20,
        chat_session_id="chat-1",
    )
    assistant_messages = [item for item in messages if str(item.role or "") == "assistant"]
    assert assistant_messages[-1].source_context["archive_workflow"]["status"] == "pending_confirmation"
    assert assistant_messages[-1].source_context["assistant_workflow"]["primary_task_type"] == "bugfix"
    assert assistant_messages[-1].source_context["assistant_workflow"]["status"] == "pending_confirmation"


def test_prepare_assistant_workflow_state_keeps_confirmed_once_for_follow_up():
    from services.assistant.assistant_workflow_policy_service import prepare_assistant_workflow_state

    previous_state = {
        "primary_task_type": "bugfix",
        "task_types": ["bugfix", "requirement"],
        "execution_mode": "collect_then_confirm",
        "confirmation_policy": "once_before_write",
        "requires_tooling": True,
        "status": "pending_confirmation",
    }

    next_state = prepare_assistant_workflow_state(
        user_message="确认，直接写入",
        source_context={"platform": "feishu"},
        previous_state=previous_state,
        chat_surface="main-chat",
        auto_use_tools=True,
    )

    assert next_state["primary_task_type"] == "bugfix"
    assert next_state["confirmed_once"] is True
    assert next_state["confirmation_count"] == 1
    assert next_state["status"] == "confirmed_once"


def test_assistant_workflow_keeps_plain_chat_as_direct_answer_with_tools_allowed():
    from services.assistant.assistant_workflow_state_service import build_assistant_workflow_state

    state = build_assistant_workflow_state(user_message="你好", auto_use_tools=True)

    assert state["primary_task_type"] == "general"
    assert state["execution_mode"] == "direct_answer"
    assert state["requires_tooling"] is False


def test_project_chat_tools_are_not_enabled_for_plain_greeting():
    from routers import projects as projects_router

    assert projects_router._should_enable_chat_tools("你好", [], []) is False


def test_project_chat_tools_remain_enabled_for_explicit_tool_intent():
    from routers import projects as projects_router

    assert projects_router._should_enable_chat_tools("查询项目里面有几个员工", [], []) is True
    assert projects_router._should_enable_chat_tools("看看项目里面有几个员工", [], []) is True
    assert projects_router._should_enable_chat_tools("帮我执行测试", [], []) is True


def test_project_chat_tools_follow_previous_tool_workflow_for_short_continue():
    from routers import projects as projects_router
    from services.assistant.assistant_workflow_policy_service import prepare_assistant_workflow_state

    previous_state = {
        "primary_task_type": "automation",
        "task_types": ["automation"],
        "execution_mode": "agent_execution",
        "confirmation_policy": "on_high_risk_only",
        "requires_tooling": True,
        "status": "ready",
    }
    next_state = prepare_assistant_workflow_state(
        user_message="继续",
        previous_state=previous_state,
        auto_use_tools=True,
    )

    assert next_state["primary_task_type"] == "automation"
    assert next_state["requires_tooling"] is True
    assert projects_router._should_enable_chat_tools("继续", [], [], next_state) is True


def test_direct_answer_without_tools_disables_agent_runtime_wrapper():
    from routers import projects as projects_router

    runtime_settings = {"agent_runtime_enabled": True, "auto_use_tools": True}
    adjusted = projects_router._runtime_settings_for_assistant_workflow(
        runtime_settings,
        {"execution_mode": "direct_answer"},
        [],
    )

    assert adjusted["agent_runtime_enabled"] is False
    assert runtime_settings["agent_runtime_enabled"] is True


def test_tool_intent_keeps_agent_runtime_wrapper_available():
    from routers import projects as projects_router

    runtime_settings = {"agent_runtime_enabled": True, "auto_use_tools": True}
    adjusted = projects_router._runtime_settings_for_assistant_workflow(
        runtime_settings,
        {"execution_mode": "direct_answer"},
        [{"tool_name": "query_project_rules"}],
    )

    assert adjusted is runtime_settings
    assert adjusted["agent_runtime_enabled"] is True


def test_run_project_chat_once_reuses_previous_confirmed_workflow_for_short_follow_up(tmp_path, monkeypatch):
    from core import config as core_config
    from services.chat.project_chat_execution_service import run_project_chat_once
    from stores.json.project_chat_store import ProjectChatMessage
    from stores.json.project_store import ProjectConfig

    monkeypatch.setenv("CORE_STORE_BACKEND", "json")
    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from routers import projects as projects_router
    from stores import factory as store_factory

    for proxy_name in (
        "role_store",
        "bot_connector_store",
        "system_config_store",
        "project_store",
        "project_chat_store",
        "project_chat_runtime_store",
        "project_chat_task_store",
        "work_session_store",
        "task_tree_evolution_store",
    ):
        getattr(store_factory, proxy_name)._instance = None

    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    store_factory.project_chat_store.append_message(
        ProjectChatMessage(
            id="assistant-prev",
            project_id="proj-1",
            username="tester",
            role="assistant",
            content="请确认后我就写入。",
            chat_session_id="chat-1",
            source_context={
                "platform": "feishu",
                "assistant_workflow": {
                    "primary_task_type": "bugfix",
                    "task_types": ["bugfix"],
                    "execution_mode": "collect_then_confirm",
                    "confirmation_policy": "once_before_write",
                    "requires_tooling": True,
                    "status": "pending_confirmation",
                },
            },
        )
    )

    class _FakeConversationManager:
        def __init__(self, redis):
            self.redis = redis

        async def create_session(self, project_id, employee_id):
            return "session-1"

        async def delete_session(self, session_id):
            return None

    class _FakeOrchestrator:
        async def run(self, **kwargs):
            assert kwargs["assistant_workflow"]["confirmed_once"] is True
            assert kwargs["assistant_workflow"]["primary_task_type"] == "bugfix"
            yield {
                "type": "done",
                "content": "已写入 bug 表。",
            }

    monkeypatch.setattr(
        projects_router,
        "_resolve_project_chat_runtime",
        AsyncMock(
            return_value=type(
                "ResolvedRuntime",
                (),
                {
                    "provider_mode": "system",
                    "provider": {"id": "provider-1", "default_model": "glm-test"},
                    "provider_id": "provider-1",
                    "model_name": "glm-test",
                },
            )()
        ),
    )
    monkeypatch.setattr(
        projects_router,
        "_resolve_provider_model_parameter_mode",
        lambda *args, **kwargs: "text",
    )
    monkeypatch.setattr(projects_router, "_collect_runtime_tools", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        projects_router,
        "_maybe_enrich_project_chat_message_with_url_content",
        AsyncMock(side_effect=lambda message, *args, **kwargs: message),
    )
    monkeypatch.setattr(
        projects_router,
        "_build_project_chat_messages",
        lambda *args, **kwargs: [{"role": "user", "content": "确认，直接写入"}],
    )
    monkeypatch.setattr(
        projects_router,
        "build_chat_runtime_context",
        lambda **kwargs: type(
            "RuntimeContext",
            (),
            {
                "resolved_tools": tuple(),
                "provider_id": "provider-1",
                "model_name": "glm-test",
                "project_id": "proj-1",
                "employee_id": "",
                "username": "tester",
                "chat_session_id": "chat-1",
                "resolved_messages": tuple([{"role": "user", "content": "确认，直接写入"}]),
                "local_connector": None,
                "workspace_path": "",
                "host_workspace_path": "",
                "local_connector_sandbox_mode": "workspace-write",
                "capability_routing": {},
                "metadata": kwargs.get("metadata") or {},
            },
        )(),
    )
    monkeypatch.setattr(
        projects_router,
        "_resolve_chat_llm_service_runtime",
        lambda llm_service, *args, **kwargs: llm_service,
    )
    monkeypatch.setattr(
        "services.providers.llm_provider_service.get_llm_provider_service",
        lambda: object(),
    )
    monkeypatch.setattr(projects_router, "get_redis_client", AsyncMock(return_value=object()))
    monkeypatch.setattr(projects_router, "ConversationManager", _FakeConversationManager)
    monkeypatch.setattr(
        projects_router,
        "build_agent_orchestrator",
        lambda *args, **kwargs: _FakeOrchestrator(),
    )
    monkeypatch.setattr(projects_router, "_save_project_chat_memory_snapshot", lambda **kwargs: None)

    from models.requests import ProjectChatReq

    result = __import__("asyncio").run(
        run_project_chat_once(
            project_id="proj-1",
            username="tester",
            req=ProjectChatReq(
                message="确认，直接写入",
                chat_session_id="chat-1",
                assistant_message_id="assistant-2",
                source_context={
                    "platform": "feishu",
                    "connector_id": "conn-feishu-1",
                    "external_chat_id": "oc-1",
                },
            ),
            auth_payload={"sub": "tester", "role": "admin"},
            save_memory_snapshot=False,
            publish_realtime=False,
        )
    )

    assert result.content == "已写入 bug 表。"
    messages = store_factory.project_chat_store.list_messages(
        "proj-1",
        "tester",
        limit=20,
        chat_session_id="chat-1",
    )
    assistant_messages = [item for item in messages if str(item.role or "") == "assistant"]
    assert assistant_messages[-1].source_context["assistant_workflow"]["confirmed_once"] is True
    assert assistant_messages[-1].source_context["assistant_workflow"]["primary_task_type"] == "bugfix"


def test_capability_routing_prompt_prefers_existing_cli_and_tools():
    from services.assistant.assistant_workflow_policy_service import build_capability_routing_prompt

    prompt = build_capability_routing_prompt(
        [
            {
                "tool_name": "project_host_run_command",
                "source": "local_host",
            },
            {
                "tool_name": "lark_doc__docs_update",
                "source": "project_skill",
            },
        ]
    )

    assert "优先复用当前已经可调用的 CLI、tool、skill、MCP" in prompt
    assert "本地 CLI/命令能力" in prompt
    assert "已有能力的编排" in prompt


def test_build_project_chat_messages_includes_capability_routing_prompt(tmp_path, monkeypatch):
    from core import config as core_config
    from stores.json.project_store import ProjectConfig

    monkeypatch.setenv("CORE_STORE_BACKEND", "json")
    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from routers import projects as projects_router

    messages = projects_router._build_project_chat_messages(
        ProjectConfig(id="proj-1", name="项目一"),
        "帮我编辑飞书文档",
        history=[],
        tools=[
            {"tool_name": "project_host_run_command", "source": "local_host"},
            {"tool_name": "lark_doc__docs_update", "source": "project_skill"},
        ],
        assistant_workflow_state={
            "primary_task_type": "docs",
            "execution_mode": "tool_augmented",
            "confirmation_policy": "once_before_write",
            "status": "ready",
        },
    )

    system_message = messages[0]["content"]
    assert "优先复用当前已经可调用的 CLI、tool、skill、MCP" in system_message
    assert "当前可复用本地 CLI/命令" in system_message


def test_assistant_capability_router_builds_write_first_route_after_confirmation():
    from services.assistant.assistant_capability_router_service import (
        apply_capability_routing,
        build_capability_routing_decision,
    )

    tools = [
        {"tool_name": "project_host_run_command", "description": "Run shell command"},
        {"tool_name": "lark_doc__docs_update", "employee_id": "emp-1", "description": "Update doc"},
        {"tool_name": "query_project_rules", "builtin": True, "description": "Query rules"},
    ]
    assistant_workflow = {
        "primary_task_type": "docs",
        "execution_mode": "tool_augmented",
        "confirmation_policy": "once_before_write",
        "confirmed_once": True,
        "status": "confirmed_once",
    }

    routed = apply_capability_routing(
        tools,
        assistant_workflow=assistant_workflow,
        chat_surface="project-chat",
    )
    decision = build_capability_routing_decision(
        routed,
        assistant_workflow=assistant_workflow,
        chat_surface="project-chat",
    )

    assert [item["tool_name"] for item in routed][:2] == [
        "lark_doc__docs_update",
        "project_host_run_command",
    ]
    assert decision["confirmed_once"] is True
    assert decision["preferred_tags"][:2] == ["docs", "write"]
