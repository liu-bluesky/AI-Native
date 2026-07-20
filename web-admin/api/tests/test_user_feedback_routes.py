"""系统统一用户反馈中心路由测试。"""

from fastapi.testclient import TestClient


def _reset_stores(store_factory) -> None:
    for proxy_name in (
        "role_store",
        "bot_connector_store",
        "system_config_store",
        "project_store",
        "project_chat_store",
        "user_store",
        "user_feedback_store",
    ):
        getattr(store_factory, proxy_name)._instance = None


def _build_client(tmp_path, monkeypatch, auth_payload):
    from core import config as core_config
    from core.deps import require_auth
    from core.server import create_app
    from stores import factory as store_factory

    monkeypatch.setenv("CORE_STORE_BACKEND", "json")
    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()
    _reset_stores(store_factory)
    app = create_app()
    app.dependency_overrides[require_auth] = lambda: auth_payload
    return TestClient(app)


def test_user_feedback_supports_submit_mine_and_idempotency(tmp_path, monkeypatch):
    client = _build_client(tmp_path, monkeypatch, {"sub": "alice", "role": "user"})
    payload = {
        "category": "product_bug",
        "title": "系统没有用户反馈菜单",
        "description": "桌面启动器中找不到反馈入口。",
        "expected_result": "所有登录用户都能提交反馈。",
        "context": {"route_path": "/workbench"},
    }
    headers = {"Idempotency-Key": "feedback-test-1"}

    first_response = client.post("/api/user-feedback", json=payload, headers=headers)
    second_response = client.post("/api/user-feedback", json=payload, headers=headers)

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    first_item = first_response.json()["item"]
    assert second_response.json()["item"]["id"] == first_item["id"]

    mine_response = client.get("/api/user-feedback/mine")
    assert mine_response.status_code == 200
    assert mine_response.json()["total"] == 1
    assert mine_response.json()["items"][0]["reporter_id"] == "alice"

    detail_response = client.get(f"/api/user-feedback/{first_item['id']}")
    assert detail_response.status_code == 200
    assert detail_response.json()["item"]["context"]["route_path"] == "/workbench"


def test_ai_evidence_is_only_saved_for_ai_feedback(tmp_path, monkeypatch):
    client = _build_client(tmp_path, monkeypatch, {"sub": "alice", "role": "user"})
    evidence = {"assistant_message_id": "msg-1", "execution_id": "run-1"}

    normal_response = client.post(
        "/api/user-feedback",
        json={
            "category": "product_bug",
            "title": "普通问题",
            "description": "普通产品问题。",
            "ai_evidence": evidence,
        },
    )
    ai_response = client.post(
        "/api/user-feedback",
        json={
            "category": "ai_execution",
            "title": "执行失败",
            "description": "工具执行没有完成。",
            "ai_evidence": evidence,
        },
    )

    assert normal_response.json()["item"]["ai_evidence"] == {}
    assert ai_response.json()["item"]["ai_evidence"]["assistant_message_id"] == "msg-1"


def test_admin_can_assign_transition_reply_and_summarize(tmp_path, monkeypatch):
    user_client = _build_client(tmp_path, monkeypatch, {"sub": "alice", "role": "user"})
    create_response = user_client.post(
        "/api/user-feedback",
        json={
            "category": "ui_experience",
            "title": "按钮位置不清晰",
            "description": "主要操作入口不明显。",
        },
    )
    feedback_id = create_response.json()["item"]["id"]

    admin_client = _build_client(tmp_path, monkeypatch, {"sub": "admin", "role": "admin"})
    list_response = admin_client.get("/api/admin/user-feedback")
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1

    assign_response = admin_client.post(
        f"/api/admin/user-feedback/{feedback_id}/assign",
        json={"assignee_id": "operator"},
    )
    assert assign_response.json()["item"]["assignee_id"] == "operator"

    transition_response = admin_client.post(
        f"/api/admin/user-feedback/{feedback_id}/transition",
        json={"status": "processing", "priority": "high"},
    )
    assert transition_response.json()["item"]["status"] == "processing"
    assert transition_response.json()["item"]["priority"] == "high"

    reply_response = admin_client.post(
        f"/api/admin/user-feedback/{feedback_id}/reply",
        json={"content": "问题已进入修复流程。"},
    )
    assert reply_response.json()["item"]["public_reply"] == "问题已进入修复流程。"

    summary_response = admin_client.get("/api/admin/user-feedback/summary")
    assert summary_response.status_code == 200
    assert summary_response.json()["summary"]["total"] == 1


def test_normal_user_cannot_access_admin_feedback(tmp_path, monkeypatch):
    client = _build_client(tmp_path, monkeypatch, {"sub": "alice", "role": "user"})
    response = client.get("/api/admin/user-feedback")
    assert response.status_code == 403


def test_project_answer_feedback_stores_local_evidence_without_diagnosis(tmp_path, monkeypatch):
    client = _build_client(tmp_path, monkeypatch, {"sub": "admin", "role": "admin"})

    from stores.factory import project_store
    from stores.json.project_store import ProjectConfig

    project_store.save(ProjectConfig(id="proj-feedback", name="反馈诊断项目", created_by="admin"))

    response = client.post(
        "/api/projects/proj-feedback/user-feedback/from-answer",
        json={
            "answer_id": "ans_chat-local-answer-1",
            "assistant_message_id": "chat-local-answer-1",
            "chat_session_id": "chat-session-1",
            "answer_snapshot": "文件已经成功生成。",
            "description": "回复说文件已生成，但工具执行失败，目录里没有文件。",
            "supervision_snapshot": {
                "answer_id": "ans_chat-local-answer-1",
                "steps": [
                    {
                        "id": "tool-step-1",
                        "type": "tool",
                        "status": "failed",
                        "title": "写入文件",
                        "summary": "目标目录不可写",
                        "tool_name": "write_file",
                    }
                ],
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "diagnosis" not in data
    assert data["item"]["category"] == "ai_answer"
    assert data["item"]["subcategory"] == ""
    assert data["item"]["ai_evidence"]["assistant_message_id"] == "chat-local-answer-1"
    assert data["item"]["ai_evidence"]["answer_origin"] == "desktop_local"
    assert data["item"]["ai_evidence"]["answer_snapshot"] == "文件已经成功生成。"
    assert "diagnosis" not in data["item"]["ai_evidence"]


def test_project_answer_feedback_rejects_non_local_answer(tmp_path, monkeypatch):
    client = _build_client(tmp_path, monkeypatch, {"sub": "admin", "role": "admin"})

    from stores.factory import project_store
    from stores.json.project_store import ProjectConfig

    project_store.save(ProjectConfig(id="proj-feedback", name="反馈诊断项目", created_by="admin"))
    response = client.post(
        "/api/projects/proj-feedback/user-feedback/from-answer",
        json={
            "answer_id": "ans_chat-server-answer",
            "assistant_message_id": "chat-server-answer",
            "chat_session_id": "chat-session-1",
            "answer_snapshot": "服务端回答不应进入本地反馈链路。",
            "description": "非本地回答。",
        },
    )

    assert response.status_code == 400


def test_project_answer_feedback_accepts_verified_local_answer_snapshot(tmp_path, monkeypatch):
    client = _build_client(tmp_path, monkeypatch, {"sub": "admin", "role": "admin"})

    from stores.factory import project_store
    from stores.json.project_store import ProjectConfig

    project_store.save(ProjectConfig(id="proj-feedback", name="反馈诊断项目", created_by="admin"))
    response = client.post(
        "/api/projects/proj-feedback/user-feedback/from-answer",
        json={
            "answer_id": "ans_chat-local-1784276474622-x4ubpr",
            "assistant_message_id": "chat-local-1784276474622-x4ubpr",
            "chat_session_id": "chat-session-local-1",
            "answer_snapshot": "本地桌面 Agent 已完成任务，但没有生成目标文件。",
            "description": "回复显示成功，实际没有产物。",
            "supervision_snapshot": {
                "answer_id": "ans_chat-local-1784276474622-x4ubpr",
                "steps": [{"type": "tool", "status": "failed", "summary": "写入目录失败"}],
            },
        },
    )

    assert response.status_code == 200
    item = response.json()["item"]
    assert item["ai_evidence"]["assistant_message_id"] == "chat-local-1784276474622-x4ubpr"
    assert item["ai_evidence"]["answer_origin"] == "desktop_local"
    assert item["ai_evidence"]["answer_snapshot"] == "本地桌面 Agent 已完成任务，但没有生成目标文件。"


def test_project_answer_feedback_rejects_mismatched_local_answer_snapshot(tmp_path, monkeypatch):
    client = _build_client(tmp_path, monkeypatch, {"sub": "admin", "role": "admin"})

    from stores.factory import project_store
    from stores.json.project_store import ProjectConfig

    project_store.save(ProjectConfig(id="proj-feedback", name="反馈诊断项目", created_by="admin"))
    response = client.post(
        "/api/projects/proj-feedback/user-feedback/from-answer",
        json={
            "answer_id": "ans_chat-local-one",
            "assistant_message_id": "chat-local-two",
            "chat_session_id": "chat-session-local-1",
            "answer_snapshot": "不应被接受的本地回答快照。",
            "description": "回答 ID 与消息 ID 不匹配。",
        },
    )

    assert response.status_code == 400
