"""全局助手路由测试"""

import asyncio
import base64
import pytest
from fastapi.testclient import TestClient


def _build_global_assistant_test_client(tmp_path, monkeypatch, auth_payload):
    from core import config as core_config
    from core.deps import require_auth
    from core.server import create_app
    from stores import mcp_bridge as mcp_bridge_store
    from stores import factory as store_factory

    monkeypatch.setenv("CORE_STORE_BACKEND", "json")
    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()
    mcp_bridge_store._store_bundle = None
    for proxy_name in (
        "role_store",
        "system_config_store",
        "project_chat_store",
    ):
        getattr(store_factory, proxy_name)._instance = None

    app = create_app()
    app.dependency_overrides[require_auth] = lambda: auth_payload
    return TestClient(app), store_factory


class _FakeLlmProviderService:
    def __init__(self):
        self.transcribe_calls = []
        self.generate_audio_speech_calls = []
        self.list_audio_voices_calls = []

    def list_providers(self, *args, **kwargs):
        return [
            {
                "id": "provider-system",
                "name": "全局助手对话供应商",
                "enabled": True,
                "default_model": "glm-test",
                "models": ["glm-test"],
                "model_configs": [{"name": "glm-test", "model_type": "text_generation"}],
                "is_default": True,
            },
            {
                "id": "provider-stt",
                "name": "语音转写供应商",
                "enabled": True,
                "default_model": "stt-model",
                "models": ["stt-model"],
                "model_configs": [{"name": "stt-model", "model_type": "audio_transcription"}],
                "is_default": False,
            },
            {
                "id": "provider-tts",
                "name": "语音播报供应商",
                "enabled": True,
                "default_model": "tts-model",
                "models": ["tts-model"],
                "model_configs": [{"name": "tts-model", "model_type": "audio_generation"}],
                "is_default": False,
            },
        ]

    def get_provider_raw(self, provider_id, **kwargs):
        if provider_id == "provider-stt":
            return {
                "id": "provider-stt",
                "name": "语音转写供应商",
                "enabled": True,
                "default_model": "stt-model",
                "model_configs": [{"name": "stt-model", "model_type": "audio_transcription"}],
            }
        if provider_id == "provider-tts":
            return {
                "id": "provider-tts",
                "name": "语音播报供应商",
                "enabled": True,
                "default_model": "tts-model",
                "model_configs": [{"name": "tts-model", "model_type": "audio_generation"}],
            }
        if provider_id == "provider-system":
            return {
                "id": "provider-system",
                "name": "全局助手对话供应商",
                "enabled": True,
                "default_model": "glm-test",
                "model_configs": [{"name": "glm-test", "model_type": "text_generation"}],
            }
        return None

    def get_model_config(self, provider, model_name):
        normalized_model_name = str(model_name or "").strip()
        if normalized_model_name == "stt-model":
            return {"name": "stt-model", "model_type": "audio_transcription"}
        if normalized_model_name == "tts-model":
            return {"name": "tts-model", "model_type": "audio_generation"}
        if normalized_model_name == "glm-test":
            return {"name": "glm-test", "model_type": "text_generation"}
        return {"name": normalized_model_name, "model_type": "text_generation"}

    async def transcribe_audio(self, provider_id, model_name, **kwargs):
        self.transcribe_calls.append(
            {
                "provider_id": provider_id,
                "model_name": model_name,
                **kwargs,
            }
        )
        return {"text": "系统状态正常"}

    async def generate_audio_speech(self, provider_id, model_name, **kwargs):
        self.generate_audio_speech_calls.append(
            {
                "provider_id": provider_id,
                "model_name": model_name,
                **kwargs,
            }
        )
        return {
            "audio_bytes": b"RIFFdemo-audio",
            "content_type": "audio/wav",
        }

    async def list_audio_voices(self, provider_id, **kwargs):
        self.list_audio_voices_calls.append(
            {
                "provider_id": provider_id,
                **kwargs,
            }
        )
        return [
            {
                "voice": "alloy",
                "voice_name": "Alloy",
                "voice_type": "system",
            }
        ]


def test_global_assistant_sessions_and_history_are_not_persisted(tmp_path, monkeypatch):
    from routers import projects as projects_router
    from stores.json.project_chat_store import ProjectChatMessage

    first_client, store_factory = _build_global_assistant_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )

    create_response = first_client.post("/api/projects/chat/global/sessions")
    assert create_response.status_code == 200
    session_id = create_response.json()["session"]["id"]

    store_factory.project_chat_store.append_message(
        ProjectChatMessage(
            project_id=projects_router._GLOBAL_ASSISTANT_STORE_PROJECT_ID,
            username="tester",
            role="user",
            content="监控状态怎么样",
            chat_session_id=session_id,
        )
    )

    session_response = first_client.get("/api/projects/chat/global/sessions")
    assert session_response.status_code == 200
    assert session_response.json()["sessions"] == []

    history_response = first_client.get(
        "/api/projects/chat/global/history",
        params={"chat_session_id": session_id},
    )
    assert history_response.status_code == 200
    assert history_response.json()["messages"] == []

    assert session_id.startswith("chat-session-")


class _FakeConversationRedis:
    def __init__(self):
        self.values: dict[str, str] = {}
        self.lists: dict[str, list[str]] = {}

    async def set(self, key, value, ex=None):
        self.values[key] = value

    async def get(self, key):
        return self.values.get(key)

    async def rpush(self, key, value):
        self.lists.setdefault(key, []).append(value)

    async def expire(self, key, ttl):
        return None

    async def lrange(self, key, start, end):
        return list(self.lists.get(key, []))

    async def delete(self, key):
        self.values.pop(key, None)
        self.lists.pop(key, None)


def test_global_assistant_ws_returns_fallback_text_when_done_content_is_empty(
    tmp_path, monkeypatch
):
    from core.auth import create_token
    from routers import projects as projects_router
    from services import llm_provider_service as llm_provider_service_module

    class _FakeAgentOrchestrator:
        def __init__(self, *args, **kwargs):
            pass

        async def run(self, **kwargs):
            yield {"type": "done", "content": ""}

    class _FakeTextLlmProviderService:
        pass

    async def _fake_get_redis_client():
        return _FakeConversationRedis()

    async def _fake_resolve_provider_runtime_target(provider_id, auth_payload):
        return (
            "provider",
            {
                "id": "provider-test",
                "default_model": "glm-test",
            },
            None,
        )

    client, store_factory = _build_global_assistant_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )

    monkeypatch.setattr(projects_router, "AgentOrchestrator", _FakeAgentOrchestrator)
    monkeypatch.setattr(projects_router, "get_redis_client", _fake_get_redis_client)
    monkeypatch.setattr(
        projects_router,
        "_resolve_provider_runtime_target",
        _fake_resolve_provider_runtime_target,
    )
    monkeypatch.setattr(
        llm_provider_service_module,
        "get_llm_provider_service",
        lambda: _FakeTextLlmProviderService(),
    )

    token = create_token("tester", role="admin", roles=["admin"])
    with client.websocket_connect(f"/api/projects/chat/global/ws?token={token}") as websocket:
        ready = websocket.receive_json()
        assert ready["type"] == "ready"

        websocket.send_json(
            {
                "request_id": "req-empty-done",
                "message": "当前系统状态如何",
                "chat_session_id": "ga-test-session",
                "assistant_message_id": "assistant-msg-1",
                "chat_mode": "system",
                "chat_surface": "global-assistant",
                "provider_id": "provider-test",
                "model_name": "glm-test",
            }
        )

        start = websocket.receive_json()
        assert start["type"] == "start"
        done = websocket.receive_json()
        assert done["type"] == "done"
        assert done["content"] == "模型未返回有效内容。"


def test_global_assistant_ws_injects_runtime_project_context_and_non_refusal_prompt(
    tmp_path, monkeypatch
):
    from core.auth import create_token
    from routers import projects as projects_router
    from services import llm_provider_service as llm_provider_service_module
    from stores.json.project_store import ProjectConfig

    captured_messages = []

    class _FakeAgentOrchestrator:
        def __init__(self, *args, **kwargs):
            pass

        async def run(self, **kwargs):
            captured_messages.extend(kwargs.get("messages") or [])
            yield {"type": "done", "content": "当前项目是 AI 设计规范。"}

    class _FakeTextLlmProviderService:
        pass

    async def _fake_get_redis_client():
        return _FakeConversationRedis()

    async def _fake_resolve_provider_runtime_target(provider_id, auth_payload):
        return (
            "provider",
            {
                "id": "provider-test",
                "default_model": "glm-test",
            },
            None,
        )

    client, store_factory = _build_global_assistant_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin", "roles": ["admin"]},
    )
    store_factory.project_store.save(
        ProjectConfig(id="proj-d16591a6", name="AI 设计规范")
    )

    monkeypatch.setattr(projects_router, "AgentOrchestrator", _FakeAgentOrchestrator)
    monkeypatch.setattr(projects_router, "get_redis_client", _fake_get_redis_client)
    monkeypatch.setattr(
        projects_router,
        "_resolve_provider_runtime_target",
        _fake_resolve_provider_runtime_target,
    )
    monkeypatch.setattr(
        llm_provider_service_module,
        "get_llm_provider_service",
        lambda: _FakeTextLlmProviderService(),
    )

    token = create_token("tester", role="admin", roles=["admin"])
    with client.websocket_connect(f"/api/projects/chat/global/ws?token={token}") as websocket:
        ready = websocket.receive_json()
        assert ready["type"] == "ready"

        websocket.send_json(
            {
                "request_id": "req-runtime-context",
                "message": "当前项目叫什么名字",
                "chat_session_id": "ga-test-session",
                "assistant_message_id": "assistant-msg-ctx",
                "chat_mode": "system",
                "chat_surface": "global-assistant",
                "route_path": "/ai/chat/settings/projects/proj-d16591a6",
                "route_title": "项目设置",
                "provider_id": "provider-test",
                "model_name": "glm-test",
            }
        )

        start = websocket.receive_json()
        assert start["type"] == "start"
        done = websocket.receive_json()
        assert done["type"] == "done"

    system_messages = [
        str(item.get("content") or "")
        for item in captured_messages
        if item.get("role") == "system"
    ]
    assert any("你是系统状态助手" in item for item in system_messages)
    assert any("禁止回答“我无法访问之前的对话历史”" in item for item in system_messages)
    assert any("当前项目：AI 设计规范 (proj-d16591a6)" in item for item in system_messages)


def test_global_assistant_ws_registers_system_guide_tool(tmp_path, monkeypatch):
    from core.auth import create_token
    from routers import projects as projects_router
    from services import llm_provider_service as llm_provider_service_module
    from services.global_assistant_service import GLOBAL_ASSISTANT_SYSTEM_GUIDE_TOOL_NAME

    captured_run_kwargs = {}

    class _FakeAgentOrchestrator:
        def __init__(self, *args, **kwargs):
            pass

        async def run(self, **kwargs):
            captured_run_kwargs.update(kwargs)
            yield {"type": "done", "content": "系统导览已就绪。"}

    class _FakeTextLlmProviderService:
        pass

    async def _fake_get_redis_client():
        return _FakeConversationRedis()

    async def _fake_resolve_provider_runtime_target(provider_id, auth_payload):
        return (
            "provider",
            {
                "id": "provider-test",
                "default_model": "glm-test",
            },
            None,
        )

    client, _ = _build_global_assistant_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin", "roles": ["admin"]},
    )

    monkeypatch.setattr(projects_router, "AgentOrchestrator", _FakeAgentOrchestrator)
    monkeypatch.setattr(projects_router, "get_redis_client", _fake_get_redis_client)
    monkeypatch.setattr(
        projects_router,
        "_resolve_provider_runtime_target",
        _fake_resolve_provider_runtime_target,
    )
    monkeypatch.setattr(
        llm_provider_service_module,
        "get_llm_provider_service",
        lambda: _FakeTextLlmProviderService(),
    )

    token = create_token("tester", role="admin", roles=["admin"])
    with client.websocket_connect(f"/api/projects/chat/global/ws?token={token}") as websocket:
        ready = websocket.receive_json()
        assert ready["type"] == "ready"

        websocket.send_json(
            {
                "request_id": "req-system-guide",
                "message": "这个系统有什么功能",
                "chat_session_id": "ga-test-session",
                "assistant_message_id": "assistant-msg-guide",
                "chat_mode": "system",
                "chat_surface": "global-assistant",
                "provider_id": "provider-test",
                "model_name": "glm-test",
            }
        )

        start = websocket.receive_json()
        assert start["type"] == "start"
        assert start["tools_enabled"] is True
        done = websocket.receive_json()
        assert done["type"] == "done"

    tool_names = [
        str(item.get("tool_name") or "").strip()
        for item in (captured_run_kwargs.get("tools") or [])
    ]
    assert GLOBAL_ASSISTANT_SYSTEM_GUIDE_TOOL_NAME in tool_names
    assert captured_run_kwargs.get("role_ids") == ["admin"]


@pytest.mark.asyncio
async def test_global_assistant_builtin_browser_tool_uses_bridge(tmp_path, monkeypatch):
    from services.global_assistant_service import GLOBAL_ASSISTANT_BROWSER_REQUESTS_TOOL_NAME
    from services.tool_executor import ToolExecutor

    captured_calls = []

    async def _fake_browser_bridge(tool_name, args):
        captured_calls.append((tool_name, args))
        return {
            "tool": tool_name,
            "items": [{"url": "/api/test", "status": 200}],
        }

    _build_global_assistant_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin", "roles": ["admin"]},
    )

    executor = ToolExecutor(
        "__global-assistant__",
        "",
        username="tester",
        role_ids=["admin"],
        global_assistant_bridge_handler=_fake_browser_bridge,
    )
    result = await executor._execute_tool(
        GLOBAL_ASSISTANT_BROWSER_REQUESTS_TOOL_NAME,
        {"limit": 1},
    )

    assert captured_calls == [
        (
            GLOBAL_ASSISTANT_BROWSER_REQUESTS_TOOL_NAME,
            {"limit": 1},
        )
    ]
    assert result["tool"] == GLOBAL_ASSISTANT_BROWSER_REQUESTS_TOOL_NAME
    assert result["items"][0]["url"] == "/api/test"


def test_global_assistant_browser_actions_schema_exposes_navigate():
    from services.global_assistant_service import (
        GLOBAL_ASSISTANT_BROWSER_ACTIONS_TOOL_NAME,
        build_global_assistant_builtin_tools,
    )

    tool = next(
        item
        for item in build_global_assistant_builtin_tools()
        if str(item.get("tool_name") or "").strip() == GLOBAL_ASSISTANT_BROWSER_ACTIONS_TOOL_NAME
    )

    schema = tool["parameters_schema"]["properties"]
    assert "navigate" in str(schema["action"]["description"] or "")
    assert "target" in schema
    assert "replace" in schema
    assert "wait_ms" in schema


def test_global_assistant_ws_registers_browser_tools(tmp_path, monkeypatch):
    from core.auth import create_token
    from routers import projects as projects_router
    from services import llm_provider_service as llm_provider_service_module
    from services.global_assistant_service import (
        GLOBAL_ASSISTANT_BROWSER_ACTIONS_TOOL_NAME,
        GLOBAL_ASSISTANT_BROWSER_REQUESTS_TOOL_NAME,
    )

    captured_run_kwargs = {}

    class _FakeAgentOrchestrator:
        def __init__(self, *args, **kwargs):
            pass

        async def run(self, **kwargs):
            captured_run_kwargs.update(kwargs)
            yield {"type": "done", "content": "浏览器工具已注册。"}

    class _FakeTextLlmProviderService:
        pass

    async def _fake_get_redis_client():
        return _FakeConversationRedis()

    async def _fake_resolve_provider_runtime_target(provider_id, auth_payload):
        return (
            "provider",
            {
                "id": "provider-test",
                "default_model": "glm-test",
            },
            None,
        )

    client, _ = _build_global_assistant_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin", "roles": ["admin"]},
    )

    monkeypatch.setattr(projects_router, "AgentOrchestrator", _FakeAgentOrchestrator)
    monkeypatch.setattr(projects_router, "get_redis_client", _fake_get_redis_client)
    monkeypatch.setattr(
        projects_router,
        "_resolve_provider_runtime_target",
        _fake_resolve_provider_runtime_target,
    )
    monkeypatch.setattr(
        llm_provider_service_module,
        "get_llm_provider_service",
        lambda: _FakeTextLlmProviderService(),
    )

    token = create_token("tester", role="admin", roles=["admin"])
    with client.websocket_connect(f"/api/projects/chat/global/ws?token={token}") as websocket:
        ready = websocket.receive_json()
        assert ready["type"] == "ready"

        websocket.send_json(
            {
                "request_id": "req-browser-bridge",
                "message": "帮我看最近的接口请求",
                "chat_session_id": "ga-test-session",
                "assistant_message_id": "assistant-msg-browser",
                "chat_mode": "system",
                "chat_surface": "global-assistant",
                "provider_id": "provider-test",
                "model_name": "glm-test",
            }
        )

        start = websocket.receive_json()
        assert start["type"] == "start"
        done = websocket.receive_json()
        assert done["type"] == "done"

    tool_names = [
        str(item.get("tool_name") or "").strip()
        for item in (captured_run_kwargs.get("tools") or [])
    ]
    assert GLOBAL_ASSISTANT_BROWSER_REQUESTS_TOOL_NAME in tool_names
    assert GLOBAL_ASSISTANT_BROWSER_ACTIONS_TOOL_NAME in tool_names
    assert callable(captured_run_kwargs.get("global_assistant_bridge_handler"))


def test_global_assistant_ws_allows_chat_when_user_cannot_manage_providers(tmp_path, monkeypatch):
    from core.auth import create_token
    from routers import projects as projects_router
    from services import llm_provider_service as llm_provider_service_module
    from stores.json.role_store import RoleConfig

    class _RestrictedProviderService:
        def list_providers(
            self,
            enabled_only=False,
            *,
            owner_username="",
            include_all=False,
            include_shared=False,
        ):
            if not include_all:
                return []
            return [
                {
                    "id": "provider-system",
                    "name": "System Provider",
                    "default_model": "glm-test",
                    "enabled": True,
                    "models": ["glm-test"],
                    "model_configs": [{"name": "glm-test", "model_type": "text_generation"}],
                    "is_default": True,
                }
            ]

    class _FakeAgentOrchestrator:
        def __init__(self, *args, **kwargs):
            pass

        async def run(self, **kwargs):
            assert kwargs["provider_id"] == "provider-system"
            assert kwargs["model_name"] == "glm-test"
            yield {"type": "done", "content": "普通用户也可使用系统默认模型。"}

    async def _fake_get_redis_client():
        return _FakeConversationRedis()

    client, store_factory = _build_global_assistant_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "chat-only", "roles": ["chat-only"]},
    )
    store_factory.role_store.save(
        RoleConfig(
            id="chat-only",
            name="Chat Only",
            description="Can use AI chat but cannot manage providers",
            permissions=["menu.ai.chat"],
            built_in=False,
        )
    )

    monkeypatch.setattr(projects_router, "AgentOrchestrator", _FakeAgentOrchestrator)
    monkeypatch.setattr(projects_router, "get_redis_client", _fake_get_redis_client)
    monkeypatch.setattr(
        llm_provider_service_module,
        "get_llm_provider_service",
        lambda: _RestrictedProviderService(),
    )

    token = create_token("tester", role="chat-only", roles=["chat-only"])
    with client.websocket_connect(f"/api/projects/chat/global/ws?token={token}") as websocket:
        ready = websocket.receive_json()
        assert ready["type"] == "ready"

        websocket.send_json(
            {
                "request_id": "req-provider-bypass",
                "message": "当前系统状态如何",
                "chat_session_id": "ga-test-session",
                "assistant_message_id": "assistant-msg-provider-bypass",
                "chat_mode": "system",
                "chat_surface": "global-assistant",
            }
        )

        start = websocket.receive_json()
        assert start["type"] == "start"
        assert start["provider_id"] == "provider-system"
        assert start["model_name"] == "glm-test"
        done = websocket.receive_json()
        assert done["type"] == "done"
        assert "系统默认模型" in done["content"]


def test_global_assistant_ws_prefers_configured_chat_model(tmp_path, monkeypatch):
    from core.auth import create_token
    from routers import projects as projects_router
    from services import llm_provider_service as llm_provider_service_module
    from stores.json.role_store import RoleConfig

    class _ConfiguredProviderService:
        def list_providers(
            self,
            enabled_only=False,
            *,
            owner_username="",
            include_all=False,
            include_shared=False,
        ):
            if not include_all:
                return []
            return [
                {
                    "id": "provider-default",
                    "name": "Default Provider",
                    "default_model": "default-model",
                    "enabled": True,
                    "models": ["default-model"],
                    "model_configs": [
                        {"name": "default-model", "model_type": "text_generation"}
                    ],
                    "is_default": True,
                },
                {
                    "id": "provider-system",
                    "name": "Configured Provider",
                    "default_model": "solver-v2",
                    "enabled": True,
                    "models": ["solver-v2"],
                    "model_configs": [
                        {"name": "solver-v2", "model_type": "text_generation"}
                    ],
                    "is_default": False,
                },
            ]

    class _FakeAgentOrchestrator:
        def __init__(self, *args, **kwargs):
            pass

        async def run(self, **kwargs):
            assert kwargs["provider_id"] == "provider-system"
            assert kwargs["model_name"] == "solver-v2"
            yield {"type": "done", "content": "已按系统配置切换到独立问题求解模型。"}

    async def _fake_get_redis_client():
        return _FakeConversationRedis()

    client, store_factory = _build_global_assistant_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "chat-only", "roles": ["chat-only"]},
    )
    store_factory.role_store.save(
        RoleConfig(
            id="chat-only",
            name="Chat Only",
            description="Can use AI chat but cannot manage providers",
            permissions=["menu.ai.chat"],
            built_in=False,
        )
    )
    store_factory.system_config_store.patch_global(
        {
            "global_assistant_chat_provider_id": "provider-system",
            "global_assistant_chat_model_name": "solver-v2",
        }
    )

    monkeypatch.setattr(projects_router, "AgentOrchestrator", _FakeAgentOrchestrator)
    monkeypatch.setattr(projects_router, "get_redis_client", _fake_get_redis_client)
    monkeypatch.setattr(
        llm_provider_service_module,
        "get_llm_provider_service",
        lambda: _ConfiguredProviderService(),
    )

    token = create_token("tester", role="chat-only", roles=["chat-only"])
    with client.websocket_connect(f"/api/projects/chat/global/ws?token={token}") as websocket:
        ready = websocket.receive_json()
        assert ready["type"] == "ready"

        websocket.send_json(
            {
                "request_id": "req-provider-config",
                "message": "帮我看下当前系统状态",
                "chat_session_id": "ga-config-session",
                "assistant_message_id": "assistant-msg-provider-config",
                "chat_mode": "system",
                "chat_surface": "global-assistant",
            }
        )

        start = websocket.receive_json()
        assert start["type"] == "start"
        assert start["provider_id"] == "provider-system"
        assert start["model_name"] == "solver-v2"
        done = websocket.receive_json()
        assert done["type"] == "done"
        assert "独立问题求解模型" in done["content"]


@pytest.mark.asyncio
async def test_global_assistant_builtin_tool_returns_system_guide(tmp_path, monkeypatch):
    from services.global_assistant_service import GLOBAL_ASSISTANT_SYSTEM_GUIDE_TOOL_NAME
    from services.tool_executor import ToolExecutor
    from stores.json.user_store import User

    _, store_factory = _build_global_assistant_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin", "roles": ["admin"]},
    )
    store_factory.user_store.save(
        User(
            username="tester",
            password_hash="hashed",
            role="admin",
            role_ids=["admin"],
        )
    )

    executor = ToolExecutor(
        "__global-assistant__",
        "",
        username="tester",
        role_ids=["admin"],
    )
    result = await executor._execute_tool(
        GLOBAL_ASSISTANT_SYSTEM_GUIDE_TOOL_NAME,
        {"focus": "系统配置"},
    )

    assert result["tool"] == GLOBAL_ASSISTANT_SYSTEM_GUIDE_TOOL_NAME
    assert "AI 对话中心" in result["guide_text"]
    assert any(
        str(item.get("name") or "").strip() == "系统配置"
        for item in (result.get("visible_modules") or [])
    )


def test_global_assistant_system_guide_filters_hidden_data_by_permission_scope(tmp_path, monkeypatch):
    from services.global_assistant_service import build_global_assistant_system_guide
    from stores.json.employee_store import EmployeeConfig
    from stores.json.project_store import ProjectConfig, ProjectUserMember
    from stores.json.role_store import RoleConfig
    from stores.json.user_store import User
    from stores.mcp_bridge import Rule, Skill, rule_store, skill_store

    _, store_factory = _build_global_assistant_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "limited", "roles": ["limited"]},
    )
    store_factory.role_store.save(
        RoleConfig(
            id="limited",
            name="Limited User",
            description="Can only access visible project/employee/skill/rule data",
            permissions=["menu.ai.chat", "menu.projects", "menu.employees", "menu.skills", "menu.rules"],
            built_in=False,
        )
    )
    store_factory.user_store.save(
        User(username="tester", password_hash="hashed", role="limited", role_ids=["limited"])
    )
    store_factory.user_store.save(
        User(username="other", password_hash="hashed", role="limited", role_ids=["limited"])
    )
    store_factory.project_store.save(ProjectConfig(id="proj-visible", name="可见项目", created_by="tester"))
    store_factory.project_store.save(ProjectConfig(id="proj-hidden", name="隐藏项目", created_by="other"))
    store_factory.project_store.upsert_user_member(
        ProjectUserMember(project_id="proj-visible", username="tester", role="owner", enabled=True)
    )
    store_factory.project_store.upsert_user_member(
        ProjectUserMember(project_id="proj-hidden", username="other", role="owner", enabled=True)
    )

    store_factory.employee_store.save(
        EmployeeConfig(id="emp-visible", name="可见员工", created_by="tester")
    )
    store_factory.employee_store.save(
        EmployeeConfig(id="emp-hidden", name="隐藏员工", created_by="other")
    )

    rule_store.save(
        Rule(id="rule-visible", domain="产品", title="可见规则", content="only visible", created_by="tester")
    )
    rule_store.save(
        Rule(id="rule-hidden", domain="产品", title="隐藏规则", content="hidden", created_by="other")
    )

    skill_store.save(
        Skill(
            id="skill-visible",
            version="1.0.0",
            name="可见技能",
            description="only visible",
            mcp_service="visible",
            created_by="tester",
        )
    )
    skill_store.save(
        Skill(
            id="skill-hidden",
            version="1.0.0",
            name="隐藏技能",
            description="hidden",
            mcp_service="hidden",
            created_by="other",
        )
    )

    guide = build_global_assistant_system_guide(username="tester", role_ids=["limited"])

    assert guide["data_scope"] == "visible_only"
    assert guide["system_counts"]["project_count"] == 1
    assert guide["system_counts"]["employee_count"] == 1
    assert all(item.get("available") is True for item in (guide.get("all_modules") or []))
    assert not any(
        str(item.get("name") or "").strip() == "系统配置"
        for item in (guide.get("visible_modules") or [])
    )


def test_global_assistant_system_guide_uses_configured_modules_and_public_entries(tmp_path, monkeypatch):
    from services.global_assistant_service import build_global_assistant_system_guide
    from stores.json.role_store import RoleConfig
    from stores.json.user_store import User

    _, store_factory = _build_global_assistant_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "limited", "roles": ["limited"]},
    )
    store_factory.role_store.save(
        RoleConfig(
            id="limited",
            name="Limited User",
            description="Can only access AI chat",
            permissions=["menu.ai.chat"],
            built_in=False,
        )
    )
    store_factory.user_store.save(
        User(username="tester", password_hash="hashed", role="limited", role_ids=["limited"])
    )
    store_factory.system_config_store.patch_global(
        {
            "global_assistant_guide_modules": [
                {
                    "id": "ops-console",
                    "name": "运维看板",
                    "summary": "查看运行态和系统级指标。",
                    "paths": ["/ops"],
                    "permission": "menu.system.config",
                    "enabled": True,
                    "is_public": False,
                    "sort_order": 10,
                },
                {
                    "id": "updates",
                    "name": "官网更新页",
                    "summary": "查看对外发布的版本更新。",
                    "paths": ["/updates"],
                    "permission": "",
                    "enabled": True,
                    "is_public": True,
                    "sort_order": 20,
                },
            ]
        }
    )

    guide = build_global_assistant_system_guide(username="tester", role_ids=["limited"])

    assert [item["id"] for item in guide["visible_modules"]] == ["updates"]
    assert guide["visible_modules"][0]["is_public"] is True
    assert "/updates" in guide["guide_text"]
    assert "运维看板" not in guide["guide_text"]


def test_global_assistant_runtime_snapshot_uses_visible_counts_only(tmp_path, monkeypatch):
    from routers import projects as projects_router
    from stores.json.employee_store import EmployeeConfig
    from stores.json.project_store import ProjectConfig, ProjectUserMember
    from stores.json.role_store import RoleConfig

    _client, store_factory = _build_global_assistant_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "limited", "roles": ["limited"]},
    )
    store_factory.role_store.save(
        RoleConfig(
            id="limited",
            name="Limited User",
            description="Can only access visible project/employee data",
            permissions=["menu.ai.chat", "menu.projects", "menu.employees"],
            built_in=False,
        )
    )

    store_factory.project_store.save(ProjectConfig(id="proj-visible", name="可见项目", created_by="tester"))
    store_factory.project_store.save(ProjectConfig(id="proj-hidden", name="隐藏项目", created_by="other"))
    store_factory.project_store.upsert_user_member(
        ProjectUserMember(project_id="proj-visible", username="tester", role="owner", enabled=True)
    )

    store_factory.employee_store.save(EmployeeConfig(id="emp-visible", name="可见员工", created_by="tester"))
    store_factory.employee_store.save(EmployeeConfig(id="emp-hidden", name="隐藏员工", created_by="other"))

    snapshot = asyncio.run(
        projects_router._build_global_assistant_runtime_snapshot(
            {"sub": "tester", "role": "limited", "roles": ["limited"]},
            route_path="/projects/proj-visible",
            route_title="项目详情",
        )
    )

    assert snapshot["visible_project_count"] == 1
    assert snapshot["employee_count"] == 1
    assert snapshot["current_project_id"] == "proj-visible"


@pytest.mark.asyncio
async def test_global_assistant_temp_session_can_be_deleted():
    from services.conversation_manager import ConversationManager

    redis_mock = _FakeConversationRedis()
    manager = ConversationManager(redis_mock)

    session_id = await manager.create_session("__global-assistant__", "")
    await manager.append_message(session_id, {"role": "user", "content": "监控状态"})

    assert f"session:{session_id}:meta" in redis_mock.values
    assert f"session:{session_id}:messages" in redis_mock.lists

    await manager.delete_session(session_id)

    assert f"session:{session_id}:meta" not in redis_mock.values
    assert f"session:{session_id}:messages" not in redis_mock.lists


def test_global_assistant_voice_runtime_accepts_allowed_multi_role_user(tmp_path, monkeypatch):
    from routers import projects as projects_router
    from stores.json.role_store import RoleConfig
    from services import llm_provider_service as llm_provider_service_module

    fake_llm_service = _FakeLlmProviderService()
    monkeypatch.setattr(llm_provider_service_module, "get_llm_provider_service", lambda: fake_llm_service)

    client, store_factory = _build_global_assistant_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "guest", "roles": ["guest", "voice-user"]},
    )
    store_factory.role_store.save(
        RoleConfig(
            id="voice-user",
            name="Voice User",
            description="Can use global assistant voice input",
            permissions=["menu.ai.chat", "button.ai.assistant.voice"],
            built_in=False,
        )
    )
    store_factory.system_config_store.patch_global(
        {
            "voice_input_enabled": True,
            "voice_input_provider_id": "provider-stt",
            "voice_input_model_name": "stt-model",
            "voice_input_allowed_role_ids": ["voice-user"],
        }
    )

    response = client.get("/api/projects/chat/global/voice-input/runtime")

    assert response.status_code == 200
    runtime = response.json()["runtime"]
    assert runtime["enabled"] is True
    assert runtime["available"] is True
    assert runtime["mode"] == "backend"
    assert runtime["provider_id"] == "provider-stt"
    assert runtime["model_name"] == "stt-model"


def test_system_config_patch_accepts_global_assistant_guide_modules(tmp_path, monkeypatch):
    client, _store_factory = _build_global_assistant_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin", "roles": ["admin"]},
    )

    response = client.patch(
        "/api/system-config",
        json={
            "global_assistant_guide_modules": [
                {
                    "id": "intro",
                    "name": "官网介绍页",
                    "summary": "查看产品介绍。",
                    "paths": ["/intro"],
                    "permission": "",
                    "enabled": True,
                    "is_public": True,
                    "sort_order": 5,
                }
            ]
        },
    )

    assert response.status_code == 200
    modules = response.json()["config"]["global_assistant_guide_modules"]
    assert len(modules) == 1
    assert modules[0]["id"] == "intro"
    assert modules[0]["is_public"] is True
    assert modules[0]["paths"] == ["/intro"]


def test_system_config_patch_accepts_global_assistant_greeting_fields(tmp_path, monkeypatch):
    from routers import system_config as system_config_router

    monkeypatch.setattr(
        system_config_router,
        "get_llm_provider_service",
        lambda: _FakeLlmProviderService(),
    )
    client, _store_factory = _build_global_assistant_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin", "roles": ["admin"]},
    )

    response = client.patch(
        "/api/system-config",
        json={
            "global_assistant_enabled": False,
            "global_assistant_greeting_enabled": False,
            "global_assistant_greeting_text": "你好，我来帮你处理当前页面。",
            "global_assistant_chat_provider_id": "provider-system",
            "global_assistant_chat_model_name": "glm-test",
            "global_assistant_system_prompt": "你是测试版系统助手。",
            "global_assistant_transcription_prompt": "只逐字转写。",
            "global_assistant_wake_phrase": "测试助手",
            "global_assistant_idle_timeout_sec": 9,
        },
    )

    assert response.status_code == 200
    config = response.json()["config"]
    assert config["global_assistant_enabled"] is False
    assert config["global_assistant_greeting_enabled"] is False
    assert config["global_assistant_greeting_text"] == "你好，我来帮你处理当前页面。"
    assert config["global_assistant_chat_provider_id"] == "provider-system"
    assert config["global_assistant_chat_model_name"] == "glm-test"
    assert config["global_assistant_system_prompt"] == "你是测试版系统助手。"
    assert config["global_assistant_transcription_prompt"] == "只逐字转写。"
    assert config["global_assistant_wake_phrase"] == "测试助手"
    assert config["global_assistant_idle_timeout_sec"] == 9


def test_global_assistant_voice_runtime_returns_disabled_when_global_assistant_is_off(
    tmp_path,
    monkeypatch,
):
    client, store_factory = _build_global_assistant_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin", "roles": ["admin"]},
    )
    store_factory.system_config_store.patch_global(
        {
            "global_assistant_enabled": False,
            "voice_input_enabled": True,
            "voice_input_provider_id": "provider-stt",
            "voice_input_model_name": "stt-model",
        }
    )

    response = client.get("/api/projects/chat/global/voice-input/runtime")

    assert response.status_code == 200
    runtime = response.json()["runtime"]
    assert runtime["global_assistant_enabled"] is False
    assert runtime["enabled"] is False
    assert runtime["available"] is False
    assert runtime["reason"] == "全局助手已关闭"


def test_system_config_global_assistant_chat_options_returns_text_models_only(
    tmp_path,
    monkeypatch,
):
    from routers import system_config as system_config_router

    fake_llm_service = _FakeLlmProviderService()
    monkeypatch.setattr(
        system_config_router,
        "get_llm_provider_service",
        lambda: fake_llm_service,
    )
    client, _store_factory = _build_global_assistant_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin", "roles": ["admin"]},
    )

    response = client.get("/api/system-config/global-assistant-chat/options")

    assert response.status_code == 200
    providers = response.json()["providers"]
    assert len(providers) == 1
    assert providers[0]["id"] == "provider-system"
    assert providers[0]["model_configs"] == [
        {"name": "glm-test", "model_type": "text_generation"}
    ]


def test_global_assistant_guide_modules_endpoint_requires_guide_permission(tmp_path, monkeypatch):
    from stores.json.role_store import RoleConfig
    from stores.json.user_store import User

    client, store_factory = _build_global_assistant_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "system-manager", "roles": ["system-manager"]},
    )
    store_factory.role_store.save(
        RoleConfig(
            id="system-manager",
            name="System Manager",
            description="Can manage system config but cannot manage guide modules",
            permissions=["menu.system.config"],
            built_in=False,
        )
    )
    store_factory.user_store.save(
        User(
            username="tester",
            password_hash="hashed",
            role="system-manager",
            role_ids=["system-manager"],
        )
    )

    get_response = client.get("/api/system-config/global-assistant-guide-modules")
    patch_response = client.patch(
        "/api/system-config/global-assistant-guide-modules",
        json={"global_assistant_guide_modules": []},
    )
    fallback_patch_response = client.patch(
        "/api/system-config",
        json={"global_assistant_guide_modules": []},
    )

    assert get_response.status_code == 403
    assert patch_response.status_code == 403
    assert fallback_patch_response.status_code == 403


def test_global_assistant_guide_modules_endpoint_allows_role_assigned_manager(tmp_path, monkeypatch):
    from stores.json.role_store import RoleConfig
    from stores.json.user_store import User

    client, store_factory = _build_global_assistant_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "guide-manager", "roles": ["guide-manager"]},
    )
    store_factory.role_store.save(
        RoleConfig(
            id="guide-manager",
            name="Guide Manager",
            description="Can manage assistant guide modules",
            permissions=["menu.system.assistant_guide"],
            built_in=False,
        )
    )
    store_factory.user_store.save(
        User(
            username="tester",
            password_hash="hashed",
            role="guide-manager",
            role_ids=["guide-manager"],
        )
    )
    store_factory.system_config_store.patch_global(
        {
            "global_assistant_guide_modules": [
                {
                    "id": "intro",
                    "name": "官网介绍页",
                    "summary": "查看产品介绍。",
                    "paths": ["/intro"],
                    "permission": "",
                    "enabled": True,
                    "is_public": True,
                    "sort_order": 5,
                }
            ]
        }
    )

    get_response = client.get("/api/system-config/global-assistant-guide-modules")

    assert get_response.status_code == 200
    assert get_response.json()["items"][0]["id"] == "intro"

    patch_response = client.patch(
        "/api/system-config/global-assistant-guide-modules",
        json={
            "global_assistant_guide_modules": [
                {
                    "id": "updates",
                    "name": "官网更新页",
                    "summary": "查看更新。",
                    "paths": ["/updates"],
                    "permission": "",
                    "enabled": True,
                    "is_public": True,
                    "sort_order": 10,
                }
            ]
        },
    )

    assert patch_response.status_code == 200
    assert patch_response.json()["items"][0]["id"] == "updates"


def test_system_config_patch_allows_guide_modules_when_both_permissions_present(tmp_path, monkeypatch):
    from stores.json.role_store import RoleConfig
    from stores.json.user_store import User

    client, store_factory = _build_global_assistant_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "system-guide-manager", "roles": ["system-guide-manager"]},
    )
    store_factory.role_store.save(
        RoleConfig(
            id="system-guide-manager",
            name="System Guide Manager",
            description="Can manage system config and assistant guide modules",
            permissions=["menu.system.config", "menu.system.assistant_guide"],
            built_in=False,
        )
    )
    store_factory.user_store.save(
        User(
            username="tester",
            password_hash="hashed",
            role="system-guide-manager",
            role_ids=["system-guide-manager"],
        )
    )

    response = client.patch(
        "/api/system-config",
        json={
            "global_assistant_guide_modules": [
                {
                    "id": "market",
                    "name": "官网市场页",
                    "summary": "查看市场能力。",
                    "paths": ["/market"],
                    "permission": "",
                    "enabled": True,
                    "is_public": True,
                    "sort_order": 20,
                }
            ]
        },
    )

    assert response.status_code == 200
    assert response.json()["config"]["global_assistant_guide_modules"][0]["id"] == "market"


def test_global_assistant_voice_runtime_uses_shared_scope_without_button_permission(tmp_path, monkeypatch):
    from services import llm_provider_service as llm_provider_service_module

    fake_llm_service = _FakeLlmProviderService()
    monkeypatch.setattr(llm_provider_service_module, "get_llm_provider_service", lambda: fake_llm_service)

    client, store_factory = _build_global_assistant_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "user", "roles": ["user"]},
    )
    store_factory.system_config_store.patch_global(
        {
            "voice_input_enabled": True,
            "voice_input_provider_id": "provider-stt",
            "voice_input_model_name": "stt-model",
        }
    )

    response = client.get("/api/projects/chat/global/voice-input/runtime")

    assert response.status_code == 200
    runtime = response.json()["runtime"]
    assert runtime["enabled"] is True
    assert runtime["available"] is True
    assert runtime["mode"] == "backend"
    assert runtime["reason"] == ""
    assert runtime["greeting_text"]
    assert runtime["transcription_prompt"]


def test_global_assistant_voice_transcription_uses_real_backend_route(tmp_path, monkeypatch):
    from stores.json.role_store import RoleConfig
    from services import llm_provider_service as llm_provider_service_module

    fake_llm_service = _FakeLlmProviderService()
    monkeypatch.setattr(llm_provider_service_module, "get_llm_provider_service", lambda: fake_llm_service)

    client, store_factory = _build_global_assistant_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "voice-user", "roles": ["voice-user"]},
    )
    store_factory.role_store.save(
        RoleConfig(
            id="voice-user",
            name="Voice User",
            description="Can use global assistant voice input",
            permissions=["menu.ai.chat", "button.ai.assistant.voice"],
            built_in=False,
        )
    )
    store_factory.system_config_store.patch_global(
        {
            "voice_input_enabled": True,
            "voice_input_provider_id": "provider-stt",
            "voice_input_model_name": "stt-model",
            "voice_input_allowed_usernames": ["tester"],
        }
    )

    response = client.post(
        "/api/projects/chat/global/voice-input/transcriptions",
        files={"audio": ("chunk.webm", b"fake-audio", "audio/webm")},
        data={"language": "zh", "is_final": "true"},
    )

    assert response.status_code == 200
    assert response.json()["text"] == "系统状态正常"
    assert response.json()["runtime"]["available"] is True
    assert fake_llm_service.transcribe_calls
    assert fake_llm_service.transcribe_calls[0]["provider_id"] == "provider-stt"
    assert fake_llm_service.transcribe_calls[0]["model_name"] == "stt-model"


def test_global_assistant_voice_transcription_denies_user_outside_shared_voice_scope(tmp_path, monkeypatch):
    from services import llm_provider_service as llm_provider_service_module

    fake_llm_service = _FakeLlmProviderService()
    monkeypatch.setattr(llm_provider_service_module, "get_llm_provider_service", lambda: fake_llm_service)

    client, store_factory = _build_global_assistant_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "user", "roles": ["user"]},
    )
    store_factory.system_config_store.patch_global(
        {
            "voice_input_enabled": True,
            "voice_input_provider_id": "provider-stt",
            "voice_input_model_name": "stt-model",
            "voice_input_allowed_usernames": ["voice-owner"],
        }
    )

    response = client.post(
        "/api/projects/chat/global/voice-input/transcriptions",
        files={"audio": ("chunk.webm", b"fake-audio", "audio/webm")},
        data={"language": "zh", "is_final": "true"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "当前账号未开通全局助手语音"
    assert not fake_llm_service.transcribe_calls


def test_global_assistant_speech_runtime_reports_backend_output_config(tmp_path, monkeypatch):
    from services import llm_provider_service as llm_provider_service_module

    fake_llm_service = _FakeLlmProviderService()
    monkeypatch.setattr(llm_provider_service_module, "get_llm_provider_service", lambda: fake_llm_service)

    client, store_factory = _build_global_assistant_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin", "roles": ["admin"]},
    )
    store_factory.system_config_store.patch_global(
        {
            "voice_output_enabled": True,
            "voice_output_provider_id": "provider-tts",
            "voice_output_model_name": "tts-model",
            "voice_output_voice": "alloy",
        }
    )

    response = client.get("/api/projects/chat/global/voice-output/runtime")

    assert response.status_code == 200
    runtime = response.json()["runtime"]
    assert runtime["enabled"] is True
    assert runtime["available"] is True
    assert runtime["mode"] == "backend"
    assert runtime["provider_id"] == "provider-tts"
    assert runtime["model_name"] == "tts-model"
    assert runtime["voice"] == "alloy"


def test_global_assistant_speech_runtime_respects_shared_voice_scope(tmp_path, monkeypatch):
    from services import llm_provider_service as llm_provider_service_module

    fake_llm_service = _FakeLlmProviderService()
    monkeypatch.setattr(llm_provider_service_module, "get_llm_provider_service", lambda: fake_llm_service)

    client, store_factory = _build_global_assistant_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "user", "roles": ["user"]},
    )
    store_factory.system_config_store.patch_global(
        {
            "voice_output_enabled": True,
            "voice_output_provider_id": "provider-tts",
            "voice_output_model_name": "tts-model",
            "voice_output_voice": "alloy",
            "voice_input_allowed_role_ids": ["voice-user"],
        }
    )

    response = client.get("/api/projects/chat/global/voice-output/runtime")

    assert response.status_code == 200
    runtime = response.json()["runtime"]
    assert runtime["enabled"] is True
    assert runtime["available"] is False
    assert runtime["reason"] == "当前账号未开通全局助手语音"


def test_global_assistant_speech_generation_uses_real_backend_route(tmp_path, monkeypatch):
    from services import llm_provider_service as llm_provider_service_module

    fake_llm_service = _FakeLlmProviderService()
    monkeypatch.setattr(llm_provider_service_module, "get_llm_provider_service", lambda: fake_llm_service)

    client, store_factory = _build_global_assistant_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin", "roles": ["admin"]},
    )
    store_factory.system_config_store.patch_global(
        {
            "voice_output_enabled": True,
            "voice_output_provider_id": "provider-tts",
            "voice_output_model_name": "tts-model",
            "voice_output_voice": "alloy",
        }
    )

    response = client.post(
        "/api/projects/chat/global/voice-output/speech",
        json={"text": "请播报当前系统状态"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")
    assert response.content == b"RIFFdemo-audio"
    assert fake_llm_service.generate_audio_speech_calls
    assert fake_llm_service.generate_audio_speech_calls[0]["provider_id"] == "provider-tts"
    assert fake_llm_service.generate_audio_speech_calls[0]["model_name"] == "tts-model"
    assert fake_llm_service.generate_audio_speech_calls[0]["voice"] == "alloy"


def test_global_assistant_speech_generation_denies_user_outside_shared_voice_scope(tmp_path, monkeypatch):
    from services import llm_provider_service as llm_provider_service_module

    fake_llm_service = _FakeLlmProviderService()
    monkeypatch.setattr(llm_provider_service_module, "get_llm_provider_service", lambda: fake_llm_service)

    client, store_factory = _build_global_assistant_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "user", "roles": ["user"]},
    )
    store_factory.system_config_store.patch_global(
        {
            "voice_output_enabled": True,
            "voice_output_provider_id": "provider-tts",
            "voice_output_model_name": "tts-model",
            "voice_output_voice": "alloy",
            "voice_input_allowed_usernames": ["voice-owner"],
        }
    )

    response = client.post(
        "/api/projects/chat/global/voice-output/speech",
        json={"text": "请播报当前系统状态"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "当前账号未开通全局助手语音"
    assert not fake_llm_service.generate_audio_speech_calls


def test_system_config_save_generates_global_greeting_audio_cache(tmp_path, monkeypatch):
    from routers import system_config as system_config_router
    from services import llm_provider_service as llm_provider_service_module

    fake_llm_service = _FakeLlmProviderService()
    monkeypatch.setattr(llm_provider_service_module, "get_llm_provider_service", lambda: fake_llm_service)
    monkeypatch.setattr(system_config_router, "get_llm_provider_service", lambda: fake_llm_service)

    client, _store_factory = _build_global_assistant_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin", "roles": ["admin"]},
    )

    response = client.patch(
        "/api/system-config",
        json={
            "voice_output_enabled": True,
            "voice_output_provider_id": "provider-tts",
            "voice_output_model_name": "tts-model",
            "voice_output_voice": "alloy",
            "global_assistant_greeting_enabled": True,
            "global_assistant_greeting_text": "欢迎使用系统状态助手",
        },
    )

    assert response.status_code == 200
    greeting_audio = response.json()["config"]["global_assistant_greeting_audio"]
    assert greeting_audio["signature"]
    assert greeting_audio["storage_path"].startswith("global-assistant/greeting-audio/")
    assert greeting_audio["content_type"] == "audio/wav"
    cached_file = tmp_path / "api-data" / greeting_audio["storage_path"]
    assert cached_file.is_file()
    assert cached_file.read_bytes() == b"RIFFdemo-audio"
    assert len(fake_llm_service.generate_audio_speech_calls) == 1
    assert fake_llm_service.generate_audio_speech_calls[0]["text"] == "欢迎使用系统状态助手"

    second_response = client.patch(
        "/api/system-config",
        json={
            "voice_output_enabled": True,
            "voice_output_provider_id": "provider-tts",
            "voice_output_model_name": "tts-model",
            "voice_output_voice": "alloy",
            "global_assistant_greeting_enabled": True,
            "global_assistant_greeting_text": "欢迎使用系统状态助手",
        },
    )

    assert second_response.status_code == 200
    assert len(fake_llm_service.generate_audio_speech_calls) == 1


def test_global_greeting_audio_route_returns_cached_audio_file(tmp_path, monkeypatch):
    from routers import system_config as system_config_router
    from services import llm_provider_service as llm_provider_service_module

    fake_llm_service = _FakeLlmProviderService()
    monkeypatch.setattr(llm_provider_service_module, "get_llm_provider_service", lambda: fake_llm_service)
    monkeypatch.setattr(system_config_router, "get_llm_provider_service", lambda: fake_llm_service)

    client, store_factory = _build_global_assistant_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin", "roles": ["admin"]},
    )
    patch_response = client.patch(
        "/api/system-config",
        json={
            "voice_output_enabled": True,
            "voice_output_provider_id": "provider-tts",
            "voice_output_model_name": "tts-model",
            "voice_output_voice": "alloy",
            "global_assistant_greeting_enabled": True,
            "global_assistant_greeting_text": "欢迎使用系统状态助手",
        },
    )
    assert patch_response.status_code == 200

    runtime_response = client.get("/api/projects/chat/global/voice-output/runtime")
    assert runtime_response.status_code == 200
    assert runtime_response.json()["runtime"]["greeting_audio_available"] is True
    assert runtime_response.json()["runtime"]["greeting_audio_signature"]

    response = client.get("/api/projects/chat/global/voice-output/greeting-audio")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")
    assert response.content == b"RIFFdemo-audio"

    clear_response = client.patch(
        "/api/system-config",
        json={"global_assistant_greeting_enabled": False},
    )
    assert clear_response.status_code == 200
    assert clear_response.json()["config"]["global_assistant_greeting_audio"] == {}
    storage_path = patch_response.json()["config"]["global_assistant_greeting_audio"]["storage_path"]
    assert not (tmp_path / "api-data" / storage_path).exists()
    assert store_factory.system_config_store.get_global().global_assistant_greeting_audio == {}


def test_global_assistant_voice_transcription_sanitizes_unsupported_format_error(tmp_path, monkeypatch):
    from stores.json.role_store import RoleConfig
    from services import llm_provider_service as llm_provider_service_module

    fake_llm_service = _FakeLlmProviderService()

    async def _raise_unsupported_format(*args, **kwargs):
        raise RuntimeError(
            'LLM request failed: HTTP 400 {"error":{"code":"1214","message":"transcriptions不支持当前文件格式"}}'
        )

    fake_llm_service.transcribe_audio = _raise_unsupported_format
    monkeypatch.setattr(llm_provider_service_module, "get_llm_provider_service", lambda: fake_llm_service)

    client, store_factory = _build_global_assistant_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "voice-user", "roles": ["voice-user"]},
    )
    store_factory.role_store.save(
        RoleConfig(
            id="voice-user",
            name="Voice User",
            description="Can use global assistant voice input",
            permissions=["menu.ai.chat", "button.ai.assistant.voice"],
            built_in=False,
        )
    )
    store_factory.system_config_store.patch_global(
        {
            "voice_input_enabled": True,
            "voice_input_provider_id": "provider-stt",
            "voice_input_model_name": "stt-model",
        }
    )

    response = client.post(
        "/api/projects/chat/global/voice-input/transcriptions",
        files={"audio": ("chunk.wav", b"fake-audio", "audio/wav")},
        data={"language": "zh", "is_final": "true"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "当前录音格式暂不支持，请重新录音后再试"


def test_global_assistant_voice_transcription_returns_empty_text_for_blank_chunk(tmp_path, monkeypatch):
    from stores.json.role_store import RoleConfig
    from services import llm_provider_service as llm_provider_service_module

    fake_llm_service = _FakeLlmProviderService()

    async def _raise_blank_chunk(*args, **kwargs):
        raise RuntimeError("语音转写结果为空")

    fake_llm_service.transcribe_audio = _raise_blank_chunk
    monkeypatch.setattr(llm_provider_service_module, "get_llm_provider_service", lambda: fake_llm_service)

    client, store_factory = _build_global_assistant_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "voice-user", "roles": ["voice-user"]},
    )
    store_factory.role_store.save(
        RoleConfig(
            id="voice-user",
            name="Voice User",
            description="Can use global assistant voice input",
            permissions=["menu.ai.chat", "button.ai.assistant.voice"],
            built_in=False,
        )
    )
    store_factory.system_config_store.patch_global(
        {
            "voice_input_enabled": True,
            "voice_input_provider_id": "provider-stt",
            "voice_input_model_name": "stt-model",
        }
    )

    response = client.post(
        "/api/projects/chat/global/voice-input/transcriptions",
        files={"audio": ("chunk.wav", b"fake-audio", "audio/wav")},
        data={"language": "zh", "is_final": "false"},
    )

    assert response.status_code == 200
    assert response.json()["text"] == ""


def test_global_assistant_voice_ws_stream_transcribes_incrementally(tmp_path, monkeypatch):
    from core.auth import create_token
    from stores.json.role_store import RoleConfig
    from services import llm_provider_service as llm_provider_service_module

    fake_llm_service = _FakeLlmProviderService()
    monkeypatch.setattr(llm_provider_service_module, "get_llm_provider_service", lambda: fake_llm_service)

    client, store_factory = _build_global_assistant_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "voice-user", "roles": ["voice-user"]},
    )
    store_factory.role_store.save(
        RoleConfig(
            id="voice-user",
            name="Voice User",
            description="Can use global assistant voice input",
            permissions=["menu.ai.chat", "button.ai.assistant.voice"],
            built_in=False,
        )
    )
    store_factory.system_config_store.patch_global(
        {
            "voice_input_enabled": True,
            "voice_input_provider_id": "provider-stt",
            "voice_input_model_name": "stt-model",
        }
    )

    token = create_token("tester", role="voice-user", roles=["voice-user"])
    with client.websocket_connect(f"/api/projects/chat/global/ws?token={token}") as websocket:
        ready = websocket.receive_json()
        assert ready["type"] == "ready"

        websocket.send_json(
            {
                "type": "voice_start",
                "request_id": "voice-req-1",
                "sample_rate": 16000,
                "language": "zh",
            }
        )
        started = websocket.receive_json()
        assert started["type"] == "voice_ready"
        assert started["request_id"] == "voice-req-1"

        websocket.send_json(
            {
                "type": "voice_chunk",
                "request_id": "voice-req-1",
                "sample_rate": 16000,
                "audio_base64": base64.b64encode(b"\x01\x02" * 4000).decode("ascii"),
                "is_final": True,
            }
        )
        websocket.send_json(
            {
                "type": "voice_stop",
                "request_id": "voice-req-1",
            }
        )

        status = websocket.receive_json()
        assert status["type"] == "voice_status"
        transcript = websocket.receive_json()
        assert transcript["type"] == "voice_transcript"
        assert transcript["text"] == "系统状态正常"
        stopped = websocket.receive_json()
        assert stopped["type"] == "voice_stopped"
        assert stopped["request_id"] == "voice-req-1"

    assert fake_llm_service.transcribe_calls
    assert fake_llm_service.transcribe_calls[0]["mime_type"] == "audio/wav"


def test_global_assistant_voice_ws_skips_tiny_recording_on_stop(tmp_path, monkeypatch):
    from core.auth import create_token
    from stores.json.role_store import RoleConfig
    from services import llm_provider_service as llm_provider_service_module

    fake_llm_service = _FakeLlmProviderService()
    monkeypatch.setattr(llm_provider_service_module, "get_llm_provider_service", lambda: fake_llm_service)

    client, store_factory = _build_global_assistant_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "voice-user", "roles": ["voice-user"]},
    )
    store_factory.role_store.save(
        RoleConfig(
            id="voice-user",
            name="Voice User",
            description="Can use global assistant voice input",
            permissions=["menu.ai.chat", "button.ai.assistant.voice"],
            built_in=False,
        )
    )
    store_factory.system_config_store.patch_global(
        {
            "voice_input_enabled": True,
            "voice_input_provider_id": "provider-stt",
            "voice_input_model_name": "stt-model",
        }
    )

    token = create_token("tester", role="voice-user", roles=["voice-user"])
    with client.websocket_connect(f"/api/projects/chat/global/ws?token={token}") as websocket:
        ready = websocket.receive_json()
        assert ready["type"] == "ready"

        websocket.send_json(
            {
                "type": "voice_start",
                "request_id": "voice-req-short",
                "sample_rate": 16000,
                "language": "zh",
            }
        )
        started = websocket.receive_json()
        assert started["type"] == "voice_ready"

        websocket.send_json(
            {
                "type": "voice_chunk",
                "request_id": "voice-req-short",
                "sample_rate": 16000,
                "audio_base64": base64.b64encode(b"\x01\x02\x03\x04").decode("ascii"),
                "is_final": True,
            }
        )
        websocket.send_json(
            {
                "type": "voice_stop",
                "request_id": "voice-req-short",
            }
        )

        stopped = websocket.receive_json()
        assert stopped["type"] == "voice_stopped"
        assert stopped["request_id"] == "voice-req-short"
        assert stopped["text"] == ""

    assert fake_llm_service.transcribe_calls == []


def test_global_assistant_voice_ws_uses_full_recording_on_stop_when_partial_is_blank(tmp_path, monkeypatch):
    from core.auth import create_token
    from stores.json.role_store import RoleConfig
    from services import llm_provider_service as llm_provider_service_module

    fake_llm_service = _FakeLlmProviderService()
    transcribe_results = ["", "系统状态恢复正常"]

    async def _transcribe_with_final_fallback(provider_id, model_name, **kwargs):
        fake_llm_service.transcribe_calls.append(
            {
                "provider_id": provider_id,
                "model_name": model_name,
                **kwargs,
            }
        )
        text = transcribe_results.pop(0)
        if not text:
            raise RuntimeError("语音转写结果为空")
        return {"text": text}

    fake_llm_service.transcribe_audio = _transcribe_with_final_fallback
    monkeypatch.setattr(llm_provider_service_module, "get_llm_provider_service", lambda: fake_llm_service)

    client, store_factory = _build_global_assistant_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "voice-user", "roles": ["voice-user"]},
    )
    store_factory.role_store.save(
        RoleConfig(
            id="voice-user",
            name="Voice User",
            description="Can use global assistant voice input",
            permissions=["menu.ai.chat", "button.ai.assistant.voice"],
            built_in=False,
        )
    )
    store_factory.system_config_store.patch_global(
        {
            "voice_input_enabled": True,
            "voice_input_provider_id": "provider-stt",
            "voice_input_model_name": "stt-model",
        }
    )

    token = create_token("tester", role="voice-user", roles=["voice-user"])
    with client.websocket_connect(f"/api/projects/chat/global/ws?token={token}") as websocket:
        ready = websocket.receive_json()
        assert ready["type"] == "ready"

        websocket.send_json(
            {
                "type": "voice_start",
                "request_id": "voice-req-final",
                "sample_rate": 16000,
                "language": "zh",
            }
        )
        started = websocket.receive_json()
        assert started["type"] == "voice_ready"

        websocket.send_json(
            {
                "type": "voice_chunk",
                "request_id": "voice-req-final",
                "sample_rate": 16000,
                "audio_base64": base64.b64encode(b"\x01\x02" * 30000).decode("ascii"),
                "is_final": False,
            }
        )
        status = websocket.receive_json()
        assert status["type"] == "voice_status"
        assert status["message"] == "正在识别语音..."

        websocket.send_json(
            {
                "type": "voice_chunk",
                "request_id": "voice-req-final",
                "sample_rate": 16000,
                "audio_base64": base64.b64encode(b"\x03\x04" * 8000).decode("ascii"),
                "is_final": True,
            }
        )
        websocket.send_json(
            {
                "type": "voice_stop",
                "request_id": "voice-req-final",
            }
        )

        final_status = websocket.receive_json()
        assert final_status["type"] == "voice_status"
        assert final_status["message"] == "正在整理完整语音..."
        transcript = websocket.receive_json()
        assert transcript["type"] == "voice_transcript"
        assert transcript["is_final"] is True
        assert transcript["text"] == "系统状态恢复正常"
        stopped = websocket.receive_json()
        assert stopped["type"] == "voice_stopped"
        assert stopped["text"] == "系统状态恢复正常"

    assert len(fake_llm_service.transcribe_calls) == 2
    assert fake_llm_service.transcribe_calls[-1]["mime_type"] == "audio/wav"


def test_global_assistant_voice_ws_sanitizes_repeated_partial_and_prefers_final_result(tmp_path, monkeypatch):
    from core.auth import create_token
    from stores.json.role_store import RoleConfig
    from services import llm_provider_service as llm_provider_service_module

    fake_llm_service = _FakeLlmProviderService()
    transcribe_results = [
        "当前的项目是什么名字？当前的项目是什么名字？",
        "当前项目叫什么名字",
    ]

    async def _transcribe_with_stable_final(provider_id, model_name, **kwargs):
        fake_llm_service.transcribe_calls.append(
            {
                "provider_id": provider_id,
                "model_name": model_name,
                **kwargs,
            }
        )
        return {"text": transcribe_results.pop(0)}

    fake_llm_service.transcribe_audio = _transcribe_with_stable_final
    monkeypatch.setattr(llm_provider_service_module, "get_llm_provider_service", lambda: fake_llm_service)

    client, store_factory = _build_global_assistant_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "voice-user", "roles": ["voice-user"]},
    )
    store_factory.role_store.save(
        RoleConfig(
            id="voice-user",
            name="Voice User",
            description="Can use global assistant voice input",
            permissions=["menu.ai.chat", "button.ai.assistant.voice"],
            built_in=False,
        )
    )
    store_factory.system_config_store.patch_global(
        {
            "voice_input_enabled": True,
            "voice_input_provider_id": "provider-stt",
            "voice_input_model_name": "stt-model",
        }
    )

    token = create_token("tester", role="voice-user", roles=["voice-user"])
    with client.websocket_connect(f"/api/projects/chat/global/ws?token={token}") as websocket:
        ready = websocket.receive_json()
        assert ready["type"] == "ready"

        websocket.send_json(
            {
                "type": "voice_start",
                "request_id": "voice-req-dedupe",
                "sample_rate": 16000,
                "language": "zh",
            }
        )
        started = websocket.receive_json()
        assert started["type"] == "voice_ready"

        websocket.send_json(
            {
                "type": "voice_chunk",
                "request_id": "voice-req-dedupe",
                "sample_rate": 16000,
                "audio_base64": base64.b64encode(b"\x01\x02" * 30000).decode("ascii"),
                "is_final": False,
            }
        )
        status = websocket.receive_json()
        assert status["type"] == "voice_status"
        transcript = websocket.receive_json()
        assert transcript["type"] == "voice_transcript"
        assert transcript["is_final"] is False
        assert transcript["text"] == "当前的项目是什么名字？"

        websocket.send_json(
            {
                "type": "voice_chunk",
                "request_id": "voice-req-dedupe",
                "sample_rate": 16000,
                "audio_base64": base64.b64encode(b"\x03\x04" * 8000).decode("ascii"),
                "is_final": True,
            }
        )
        websocket.send_json(
            {
                "type": "voice_stop",
                "request_id": "voice-req-dedupe",
            }
        )

        final_status = websocket.receive_json()
        assert final_status["type"] == "voice_status"
        assert final_status["message"] == "正在整理完整语音..."
        final_transcript = websocket.receive_json()
        assert final_transcript["type"] == "voice_transcript"
        assert final_transcript["is_final"] is True
        assert final_transcript["text"] == "当前项目叫什么名字"
        stopped = websocket.receive_json()
        assert stopped["type"] == "voice_stopped"
        assert stopped["text"] == "当前项目叫什么名字"

    assert len(fake_llm_service.transcribe_calls) == 2


def test_global_assistant_voice_ws_allows_scope_open_user_without_voice_button_permission(tmp_path, monkeypatch):
    from core.auth import create_token
    from stores.json.role_store import RoleConfig
    from services import llm_provider_service as llm_provider_service_module

    fake_llm_service = _FakeLlmProviderService()
    monkeypatch.setattr(llm_provider_service_module, "get_llm_provider_service", lambda: fake_llm_service)

    client, store_factory = _build_global_assistant_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "chat-only", "roles": ["chat-only"]},
    )
    store_factory.role_store.save(
        RoleConfig(
            id="chat-only",
            name="Chat Only",
            description="Can use global assistant chat only",
            permissions=["menu.ai.chat"],
            built_in=False,
        )
    )
    store_factory.system_config_store.patch_global(
        {
            "voice_input_enabled": True,
            "voice_input_provider_id": "provider-stt",
            "voice_input_model_name": "stt-model",
        }
    )

    token = create_token("tester", role="chat-only", roles=["chat-only"])
    with client.websocket_connect(f"/api/projects/chat/global/ws?token={token}") as websocket:
        ready = websocket.receive_json()
        assert ready["type"] == "ready"

        websocket.send_json(
            {
                "type": "voice_start",
                "request_id": "voice-req-denied",
                "sample_rate": 16000,
                "language": "zh",
            }
        )
        ready_payload = websocket.receive_json()
        assert ready_payload["type"] == "voice_ready"
        assert ready_payload["request_id"] == "voice-req-denied"
