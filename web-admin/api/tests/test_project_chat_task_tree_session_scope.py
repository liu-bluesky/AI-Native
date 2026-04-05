"""项目聊天任务树会话隔离测试"""

from fastapi.testclient import TestClient


def _build_project_chat_task_tree_test_client(tmp_path, monkeypatch, auth_payload):
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


def test_project_chat_task_tree_does_not_fallback_to_latest_when_chat_session_is_explicit(
    tmp_path,
    monkeypatch,
):
    from stores.json.project_store import ProjectConfig

    client, store_factory = _build_project_chat_task_tree_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(ProjectConfig(id="proj-1", name="项目一"))

    first_session = client.post("/api/projects/proj-1/chat/sessions")
    assert first_session.status_code == 200
    first_chat_session_id = first_session.json()["session"]["id"]

    generate_response = client.post(
        "/api/projects/proj-1/chat/task-tree/generate",
        json={
            "chat_session_id": first_chat_session_id,
            "message": "第一个会话里的执行任务",
        },
    )
    assert generate_response.status_code == 200

    second_session = client.post("/api/projects/proj-1/chat/sessions")
    assert second_session.status_code == 200
    second_chat_session_id = second_session.json()["session"]["id"]
    assert second_chat_session_id != first_chat_session_id

    explicit_response = client.get(
        "/api/projects/proj-1/chat/task-tree",
        params={"chat_session_id": second_chat_session_id},
    )
    assert explicit_response.status_code == 200
    assert explicit_response.json()["task_tree"] is None

    fallback_response = client.get("/api/projects/proj-1/chat/task-tree")
    assert fallback_response.status_code == 200
    assert fallback_response.json()["task_tree"]["chat_session_id"] == first_chat_session_id
