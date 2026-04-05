"""项目聊天回答前任务树保护测试"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient


def _build_project_chat_guard_test_client(tmp_path, monkeypatch, auth_payload):
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
        "system_config_store",
        "project_store",
        "project_chat_store",
        "project_chat_task_store",
    ):
        getattr(store_factory, proxy_name)._instance = None

    app = create_app()
    app.dependency_overrides[require_auth] = lambda: auth_payload
    return TestClient(app), store_factory


def _extract_project_chat_sse_messages(response_text: str) -> list[dict]:
    import json

    payloads: list[dict] = []
    for line in response_text.splitlines():
        if line.startswith("data: "):
            payloads.append(json.loads(line[len("data: ") :]))
    return payloads


def test_require_project_chat_session_id_rejects_empty():
    from routers import projects as projects_router

    with pytest.raises(ValueError, match="chat_session_id is required for project chat"):
        projects_router._require_project_chat_session_id("  ")


def test_resolve_project_chat_task_tree_context_requires_task_tree(monkeypatch):
    from routers import projects as projects_router

    captured_calls = []
    monkeypatch.setattr(
        projects_router,
        "get_task_tree_for_chat_session",
        lambda project_id, username, chat_session_id: captured_calls.append(
            {
                "project_id": project_id,
                "username": username,
                "chat_session_id": chat_session_id,
            }
        )
        or None,
    )
    monkeypatch.setattr(projects_router, "serialize_task_tree", lambda session: None)

    with pytest.raises(ValueError, match="task tree must be available before answering"):
        projects_router._resolve_project_chat_task_tree_context(
            "proj-1",
            "tester",
            " chat-1 ",
            {"task_tree_enabled": False, "task_tree_auto_generate": False},
            "当前项目做什么的",
        )

    assert captured_calls == [
        {
            "project_id": "proj-1",
            "username": "tester",
            "chat_session_id": "chat-1",
        }
    ]


@pytest.mark.asyncio
async def test_generate_project_chat_media_done_payload_attaches_task_tree_audit(monkeypatch):
    from routers import projects as projects_router

    llm_service = MagicMock()
    llm_service.generate_media_artifacts = AsyncMock(
        return_value=[
            {
                "asset_type": "image",
                "preview_url": "https://cdn.example.com/preview.png",
                "content_url": "https://cdn.example.com/result.png",
                "mime_type": "image/png",
            }
        ]
    )

    monkeypatch.setattr(projects_router, "is_admin_like", lambda auth_payload: False)
    monkeypatch.setattr(projects_router, "_save_chat_media_artifacts_to_materials", lambda **kwargs: [])
    monkeypatch.setattr(projects_router, "_append_chat_record", lambda **kwargs: None)
    monkeypatch.setattr(projects_router, "_save_project_chat_memory_snapshot", lambda **kwargs: None)
    monkeypatch.setattr(
        projects_router,
        "audit_task_tree_round",
        lambda **kwargs: {
            "code": "lookup_query_auto_completed",
            "task_tree": None,
            "history_task_tree": {
                "chat_session_id": kwargs["chat_session_id"],
                "status": "done",
                "is_archived": True,
            },
        },
    )

    payload = await projects_router._generate_project_chat_media_done_payload(
        llm_service=llm_service,
        auth_payload={"sub": "tester", "role": "admin"},
        project_id="proj-1",
        username="tester",
        chat_session_id="chat-1",
        assistant_message_id="msg-1",
        effective_user_message="生成当前项目封面图",
        selected_employee_ids=[],
        provider_id="provider-1",
        model_name="model-1",
        runtime_settings={
            "image_resolution": "1080x1080",
            "image_aspect_ratio": "1:1",
            "video_aspect_ratio": "16:9",
            "video_duration_seconds": 5,
        },
        memory_source="project-chat-media-test",
    )

    assert payload["type"] == "done"
    assert payload["artifacts"][0]["asset_type"] == "image"
    assert "https://cdn.example.com/result.png" in payload["images"]
    assert payload["task_tree_audit"]["code"] == "lookup_query_auto_completed"
    assert payload["history_task_tree"]["chat_session_id"] == "chat-1"


def test_project_chat_stream_requires_task_tree_before_answering(tmp_path, monkeypatch):
    from stores.json.project_store import ProjectConfig

    client, store_factory = _build_project_chat_guard_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))

    response = client.post(
        "/api/projects/proj-1/chat/stream",
        json={
            "message": "当前项目做什么的",
            "chat_session_id": "chat-1",
            "task_tree_enabled": False,
            "task_tree_auto_generate": False,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "task tree must be available before answering"


def test_project_chat_stream_direct_reply_emits_task_tree_before_done(tmp_path, monkeypatch):
    from routers import projects as projects_router
    from stores.json.project_store import ProjectConfig

    client, store_factory = _build_project_chat_guard_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(
        ProjectConfig(id="proj-1", name="项目一", description="用于验证任务树顺序")
    )

    monkeypatch.setattr(projects_router, "_is_project_meta_query", lambda message: True)
    monkeypatch.setattr(
        projects_router,
        "_build_project_meta_reply",
        lambda project, selected_employee, candidates: "项目一用于验证先起任务树再结束回答。",
    )
    monkeypatch.setattr(projects_router, "_save_project_chat_memory_snapshot", lambda **kwargs: None)
    monkeypatch.setattr(
        projects_router,
        "audit_task_tree_round",
        lambda **kwargs: {
            "code": "lookup_query_auto_completed",
            "task_tree": None,
            "history_task_tree": {
                "chat_session_id": kwargs["chat_session_id"],
                "status": "done",
                "is_archived": True,
            },
        },
    )

    response = client.post(
        "/api/projects/proj-1/chat/stream",
        json={
            "message": "当前项目做什么的",
            "chat_session_id": "chat-1",
            "assistant_message_id": "msg-1",
        },
        headers={"Accept": "text/event-stream"},
    )

    assert response.status_code == 200
    payloads = _extract_project_chat_sse_messages(response.text)
    assert len(payloads) >= 3

    start_payload = payloads[0]
    done_payload = payloads[-1]

    assert start_payload["type"] == "start"
    assert start_payload["task_tree"]["chat_session_id"] == "chat-1"
    assert start_payload["task_tree"]["root_goal"] == "当前项目做什么的"
    assert done_payload["type"] == "done"
    assert done_payload["task_tree_audit"]["code"] == "lookup_query_auto_completed"
    assert done_payload["history_task_tree"]["chat_session_id"] == "chat-1"
