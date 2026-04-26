"""项目聊天运行态快照路由测试"""

import json

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


def test_project_chat_session_update_and_feishu_manual_binding(tmp_path, monkeypatch):
    from routers import projects as projects_router
    from services.feishu_bot_service import _find_or_bind_feishu_manual_chat_session
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

    def fake_resolve(connector, chat_name):
        assert connector["id"] == "conn-feishu-1"
        assert chat_name == "产品研发群"
        return {"chat_id": "oc_real_group_1", "name": "产品研发群"}

    monkeypatch.setattr(
        "services.feishu_bot_service.resolve_feishu_chat_by_name",
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


def test_feishu_message_event_routes_by_project_chat_session_binding(tmp_path, monkeypatch):
    from services.feishu_bot_service import process_feishu_message_event
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
        "services.feishu_bot_service.run_project_chat_once",
        fake_run_project_chat_once,
    )
    monkeypatch.setattr(
        "services.feishu_bot_service._reply_feishu_text",
        fake_reply_feishu_text,
    )
    monkeypatch.setattr(
        "services.feishu_bot_service.enqueue_system_speech",
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
                mentions=[Obj(key="@_user_1")],
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
    assert req.system_prompt == "你是飞书群里的需求协作机器人，只回答和项目推进有关的问题。"
    assert req.source_context["external_chat_id"] == "oc_real_group_1"
    assert req.source_context["thread_key"] == "feishu:conn-feishu-1:chat:oc_real_group_1"
    assert speech_calls == []
    assert replies[0][1]["message_id"] == "om_message_1"


def test_feishu_non_text_message_event_is_recorded_without_group_reply(tmp_path, monkeypatch):
    from services.feishu_bot_service import process_feishu_message_event
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

    async def fake_run_project_chat_once(**kwargs):
        calls.append(kwargs)
        raise AssertionError("non-text feishu messages should not enter project chat")

    async def fake_reply_feishu_text(connector, **kwargs):
        replies.append((connector, kwargs))

    def fake_download_resource(connector, **kwargs):
        image_path = tmp_path / "img_v3_1.png"
        image_path.write_bytes(b"fake image")
        return {
            "file_key": kwargs["file_key"],
            "type": "image",
            "filename": "img_v3_1.png",
            "path": str(image_path),
            "url": "/api/bot-events/feishu/conn-feishu-1/resources/om_image_1/img_v3_1.png",
            "content_type": "image/png",
        }

    archive_merges = []

    def fake_append_archive_attachments(**kwargs):
        archive_merges.append(kwargs)
        return {"status": "updated", "record_id": "rec_1"}

    monkeypatch.setattr(
        "services.feishu_bot_service.run_project_chat_once",
        fake_run_project_chat_once,
    )
    monkeypatch.setattr(
        "services.feishu_bot_service._reply_feishu_text",
        fake_reply_feishu_text,
    )
    monkeypatch.setattr(
        "services.feishu_bot_service._download_feishu_message_resource",
        fake_download_resource,
    )
    monkeypatch.setattr(
        "services.feishu_bot_service.append_feishu_archive_attachments",
        fake_append_archive_attachments,
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
                mentions=[],
            ),
        )
    )

    import asyncio

    asyncio.run(process_feishu_message_event("conn-feishu-1", event))

    assert calls == []
    assert replies == []
    assert archive_merges == [
        {
            "source_context": {
                "source_type": "group_message",
                "platform": "feishu",
                "connector_id": "conn-feishu-1",
                "external_chat_id": "oc_real_group_1",
                "external_chat_name": "产品研发群",
                "external_message_id": "om_image_1",
                "sender_id": "ou_sender_1",
                "thread_key": "feishu:conn-feishu-1:chat:oc_real_group_1",
                "image_urls": [
                    "/api/bot-events/feishu/conn-feishu-1/resources/om_image_1/img_v3_1.png",
                ],
                "attachment_files": [
                    {
                        "file_key": "img_v3_1",
                        "type": "image",
                        "filename": "img_v3_1.png",
                        "path": str(tmp_path / "img_v3_1.png"),
                        "url": "/api/bot-events/feishu/conn-feishu-1/resources/om_image_1/img_v3_1.png",
                        "content_type": "image/png",
                    }
                ],
            },
            "attachment_urls": [
                "/api/bot-events/feishu/conn-feishu-1/resources/om_image_1/img_v3_1.png",
            ],
            "attachment_files": [
                {
                    "file_key": "img_v3_1",
                    "type": "image",
                    "filename": "img_v3_1.png",
                    "path": str(tmp_path / "img_v3_1.png"),
                    "url": "/api/bot-events/feishu/conn-feishu-1/resources/om_image_1/img_v3_1.png",
                    "content_type": "image/png",
                }
            ],
        }
    ]
    records = store_factory.project_chat_store.list_messages(
        "proj-1",
        "tester",
        limit=10,
        chat_session_id=session["id"],
    )
    assert [item.role for item in records] == ["user", "assistant"]
    assert records[0].images == [
        "/api/bot-events/feishu/conn-feishu-1/resources/om_image_1/img_v3_1.png",
    ]
    assert "飞书发送了图片" in records[0].content
    assert "合并到最近的飞书归档记录" in records[1].content


def test_feishu_post_message_with_image_routes_text_to_project_chat(tmp_path, monkeypatch):
    from services.feishu_bot_service import process_feishu_message_event
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
        "services.feishu_bot_service.run_project_chat_once",
        fake_run_project_chat_once,
    )
    monkeypatch.setattr(
        "services.feishu_bot_service._reply_feishu_text",
        fake_reply_feishu_text,
    )
    monkeypatch.setattr(
        "services.feishu_bot_service._download_feishu_message_resource",
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
                mentions=[Obj(key="@_user_1")],
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


def test_feishu_archive_attachment_append_updates_latest_bitable_record(tmp_path, monkeypatch):
    from core import config as core_config
    from services import feishu_archive_writer_service as writer

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
    image_path = tmp_path / "image.png"
    image_path.write_bytes(b"fake image")

    def fake_run_lark_cli_json(args, *, timeout=90):
        commands.append(args)
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
                        {"name": "图片/附件", "type": "attachment"},
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
    assert commands[1][:2] == ["base", "+record-upload-attachment"]
    assert commands[1][commands[1].index("--field-id") + 1] == "图片/附件"
    assert commands[1][commands[1].index("--file") + 1] == str(image_path)
    assert commands[1][commands[1].index("--name") + 1] == "image.png"
    state = json.loads(archive_path.read_text(encoding="utf-8"))
    assert state["archives"]["archive-1"]["last_external_message_id"] == "om_image_1"
    assert state["archives"]["archive-1"]["last_attachment_upload_count"] == 1


def test_feishu_archive_attachment_append_creates_attachment_field_for_legacy_text_field(tmp_path, monkeypatch):
    from core import config as core_config
    from services import feishu_archive_writer_service as writer

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
    image_path = tmp_path / "legacy-image.png"
    image_path.write_bytes(b"fake image")
    commands = []

    def fake_run_lark_cli_json(args, *, timeout=90):
        commands.append(args)
        if args[:2] == ["base", "+field-list"]:
            return {"data": {"fields": [{"name": "图片/附件", "type": "text"}]}}
        if args[:2] == ["base", "+field-create"]:
            return {"field": {"id": "fld_attachment"}, "created": True}
        if args[:2] == ["base", "+record-upload-attachment"]:
            return {"ok": True}
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
    upload_calls = [args for args in commands if args[:2] == ["base", "+record-upload-attachment"]]
    assert result["status"] == "updated"
    assert created_attachment_fields[0] == {"name": "图片附件", "type": "attachment"}
    assert upload_calls[0][upload_calls[0].index("--field-id") + 1] == "图片附件"
    state = json.loads(archive_path.read_text(encoding="utf-8"))
    assert state["archives"]["archive-1"]["attachment_field_name"] == "图片附件"


def test_feishu_message_event_queues_speech_only_when_task_listener_matches(tmp_path, monkeypatch):
    from services.feishu_bot_service import process_feishu_message_event
    from services.global_assistant_task_service import upsert_global_assistant_task
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
        "services.feishu_bot_service.run_project_chat_once",
        fake_run_project_chat_once,
    )
    monkeypatch.setattr(
        "services.feishu_bot_service._reply_feishu_text",
        fake_reply_feishu_text,
    )
    monkeypatch.setattr(
        "services.feishu_bot_service.enqueue_system_speech",
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
                mentions=[Obj(key="@_user_1")],
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

    from services.global_assistant_task_service import (
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


def test_global_assistant_task_infers_system_speech_action_for_reminder(tmp_path, monkeypatch):
    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services.global_assistant_task_service import upsert_global_assistant_task

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

    assert task["actions"][0]["type"] == "system_speech"


def test_global_assistant_task_engine_records_event_execution(tmp_path, monkeypatch):
    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services.global_assistant_task_service import (
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

    from services.global_assistant_task_service import (
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

    from services.global_assistant_task_service import (
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

    from services.global_assistant_task_service import (
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


def test_feishu_archive_writer_creates_once_then_appends(tmp_path, monkeypatch):
    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services import feishu_archive_writer_service as writer

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
    assert first["archive_key"] == "feishu-main|oc-1|bug"
    assert first["document_title"] == "aitest-bug文档【飞书机器人】"


def test_feishu_archive_writer_sheet_creates_once_then_appends(tmp_path, monkeypatch):
    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services import feishu_archive_writer_service as writer

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

    from services import feishu_archive_writer_service as writer

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
            "writer_type": "bitable",
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

    from services import feishu_archive_writer_service as writer

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

    from services import feishu_archive_writer_service as writer

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

    from services import feishu_archive_writer_service as writer

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
    attachment_fields = [item for item in table_field_payloads[0] if item["name"] == "图片/附件"]
    assert attachment_fields == [{"name": "图片/附件", "type": "attachment"}]
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

    from services import feishu_archive_writer_service as writer

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
    assert "图片/附件" not in record_payloads[0]
    assert record_payloads[0]["消息链接"] == "https://tenant.feishu.cn/message/om-1"
    assert "复现步骤" in record_payloads[0]["详细内容"]
    assert "聊天记录" in record_payloads[0]
    assert "external_chat_id" not in record_payloads[0]


def test_feishu_archive_writer_cli_user_bitable_parses_inline_numbered_markdown(tmp_path, monkeypatch):
    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services import feishu_archive_writer_service as writer

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


def test_feishu_archive_writer_cli_user_bitable_existing_table_adds_friendly_fields(tmp_path, monkeypatch):
    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services import feishu_archive_writer_service as writer

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
        message_text="新增bug：登录页报错",
        source_context={"connector_id": "feishu-main", "external_chat_id": "oc-1", "external_chat_name": "aitest"},
    )

    assert result["created"] is False
    created_field_names = [item["name"] for item in created_fields]
    assert "标题" in created_field_names
    assert "摘要" in created_field_names
    assert {"name": "图片/附件", "type": "attachment"} in created_fields
    assert "external_chat_id" not in created_field_names


def test_global_assistant_archive_action_returns_saved(tmp_path, monkeypatch):
    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services import global_assistant_task_service as tasks

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


def test_feishu_confirmed_archive_reply_overrides_model_text():
    from services.feishu_bot_service import _build_confirmed_archive_reply

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
    from services.feishu_bot_service import _build_feishu_archive_truth_prompt

    prompt = _build_feishu_archive_truth_prompt(
        {"agent_name": "飞书机器人"},
        {"external_chat_name": "aitest"},
    )

    assert "飞书机器人" in prompt
    assert "aitest" in prompt
    assert "当前群 + 当前机器人 + 分类" in prompt
    assert "禁止回复“已归档”" in prompt


def test_feishu_structured_pending_archive_reply_executes_archive_task(tmp_path, monkeypatch):
    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services import global_assistant_task_service as tasks
    from services.feishu_bot_service import _process_feishu_archive_tasks_after_reply

    monkeypatch.setattr(
        tasks,
        "archive_feishu_task_message",
        lambda **kwargs: {
            "status": "saved",
            "archive_key": "feishu-main|oc-1|bug",
            "category": "bug",
            "writer_type": "docx",
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
        message_text="CRM 登录页在微信浏览器顶部导航丢失",
        reply_content="【待归档类型】\nbug\n\n【待归档状态】\n已整理，尚未写入群文档\n\n【结构化内容】\n- 标题：CRM 登录页在微信浏览器顶部导航丢失",
        source_context={"platform": "feishu", "connector_id": "feishu-main", "external_chat_id": "oc-1"},
        already_matched_tasks=[],
    )

    assert [item["id"] for item in processed] == ["task-archive"]
    result = processed[0]["latest_execution"]["action_results"][0]
    assert result["status"] == "saved"
    assert result["document_title"] == "aitest-bug文档【飞书机器人】"


def test_feishu_failed_archive_reply_reports_failure():
    from services.feishu_bot_service import _build_failed_archive_reply

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


def test_feishu_structured_pending_archive_reruns_after_failed_pre_match(tmp_path, monkeypatch):
    from core import config as core_config

    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()

    from services import global_assistant_task_service as tasks
    from services.feishu_bot_service import _process_feishu_archive_tasks_after_reply

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


def test_feishu_unconfirmed_archive_reply_is_downgraded():
    from services.feishu_bot_service import _downgrade_unconfirmed_archive_reply

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

    assert "尚未真实写入飞书群文档" in reply
    assert "已归档" not in reply
    assert "保存到" not in reply
    assert "待归档" in reply


def test_feishu_message_event_without_session_binding_is_ignored(tmp_path, monkeypatch):
    from services.feishu_bot_service import process_feishu_message_event
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

    async def fake_run_project_chat_once(**kwargs):
        calls.append(kwargs)
        raise AssertionError("unbound feishu messages must not run project chat")

    async def fake_reply_feishu_text(connector, **kwargs):
        raise AssertionError("unbound feishu messages must not reply")

    monkeypatch.setattr(
        "services.feishu_bot_service.run_project_chat_once",
        fake_run_project_chat_once,
    )
    monkeypatch.setattr(
        "services.feishu_bot_service._reply_feishu_text",
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

    assert calls == []


def test_resolve_feishu_chat_by_name_reads_search_meta_data(monkeypatch):
    from services.feishu_bot_service import resolve_feishu_chat_by_name

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

    monkeypatch.setattr("services.feishu_bot_service.requests.post", fake_post)

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
