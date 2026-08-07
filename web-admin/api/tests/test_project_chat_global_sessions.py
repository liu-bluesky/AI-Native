import asyncio


def test_json_store_lists_sessions_and_history_across_projects(tmp_path):
    from stores.json.project_chat_store import ProjectChatMessage, ProjectChatStore

    store = ProjectChatStore(tmp_path)
    first = store.create_session("project-a", "tester", "会话 A", session_id="session-a")
    second = store.create_session("project-b", "tester", "会话 B", session_id="session-b")
    store.append_message(
        ProjectChatMessage(
            project_id="project-a",
            username="tester",
            role="user",
            content="A 项目消息",
            chat_session_id=first.id,
        )
    )
    store.append_message(
        ProjectChatMessage(
            project_id="project-b",
            username="tester",
            role="user",
            content="B 项目消息",
            chat_session_id=second.id,
        )
    )

    assert {item.id for item in store.list_sessions_global("tester")} == {
        "session-a",
        "session-b",
    }
    assert [
        item.content
        for item in store.list_messages_global("tester", chat_session_id="session-a")
    ] == ["A 项目消息"]


def test_global_session_create_persists_before_first_message(tmp_path, monkeypatch):
    from models.requests import ProjectChatSessionCreateReq
    from routers import projects
    from stores.json.project_chat_store import ProjectChatStore

    store = ProjectChatStore(tmp_path)
    monkeypatch.setattr(projects, "project_chat_store", store)
    monkeypatch.setattr(projects, "_ensure_permission", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(projects, "_ensure_project_access", lambda *_args, **_kwargs: object())

    result = asyncio.run(
        projects.create_global_assistant_chat_session(
            req=ProjectChatSessionCreateReq(
                project_id="project-a",
                chat_session_id="session-created-immediately",
                title="创建即入库",
            ),
            auth_payload={"sub": "tester", "role": "admin"},
        )
    )

    assert result["session"]["id"] == "session-created-immediately"
    persisted = store.get_session("project-a", "tester", "session-created-immediately")
    assert persisted is not None
    assert persisted.title == "创建即入库"
    assert persisted.message_count == 0
