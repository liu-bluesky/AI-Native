"""模拟测试（无需 Redis）"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_orchestrator_logic():
    """测试 AgentOrchestrator 逻辑"""
    from services.agent_orchestrator import AgentOrchestrator

    llm_service = MagicMock()
    conv_manager = MagicMock()
    conv_manager.get_context = AsyncMock(return_value=[])
    conv_manager.append_message = AsyncMock()

    orchestrator = AgentOrchestrator(llm_service, conv_manager)

    tools = [{"tool_name": "test_tool", "description": "测试工具"}]
    formatted = orchestrator._format_tools(tools)

    assert len(formatted) == 1
    assert formatted[0]["type"] == "function"
    assert formatted[0]["function"]["name"] == "test_tool"


@pytest.mark.asyncio
async def test_tool_executor_logic():
    """测试 ToolExecutor 逻辑"""
    from services.tool_executor import ToolExecutor

    executor = ToolExecutor("test-proj", "test-emp")
    assert executor._timeout == 60

def test_build_local_connector_file_tools_includes_coding_tools():
    from services.local_connector_service import build_local_connector_file_tools

    tool_names = {item["tool_name"] for item in build_local_connector_file_tools()}

    assert "local_connector_read_file" in tool_names
    assert "local_connector_write_file" in tool_names
    assert "local_connector_run_command" in tool_names


@pytest.mark.asyncio
async def test_tool_executor_routes_local_connector_tools(monkeypatch):
    from services import local_connector_service as connector_svc
    from services.tool_executor import ToolExecutor

    captured: dict = {}

    async def fake_read(connector, **kwargs):
        captured["connector"] = connector
        captured["kwargs"] = kwargs
        return {"ok": True, "path": kwargs["path"], "content": "demo"}

    monkeypatch.setattr(connector_svc, "read_connector_file", fake_read)

    connector = object()
    executor = ToolExecutor(
        "test-proj",
        "test-emp",
        local_connector=connector,
        local_connector_workspace_path="/tmp/workspace",
        local_connector_sandbox_mode="workspace-write",
    )

    result = await executor._execute_tool(
        "local_connector_read_file",
        {"path": "src/app.py", "start_line": 5, "end_line": 12},
    )

    assert result["ok"] is True
    assert captured["connector"] is connector
    assert captured["kwargs"]["workspace_path"] == "/tmp/workspace"
    assert captured["kwargs"]["path"] == "src/app.py"
    assert captured["kwargs"]["start_line"] == 5
    assert captured["kwargs"]["end_line"] == 12


@pytest.mark.asyncio
async def test_local_connector_llm_adapter_streams_chunks(monkeypatch):
    from services import local_connector_service as connector_svc

    async def fake_stream(connector, **kwargs):
        assert connector == "connector-1"
        assert kwargs["model_name"] == "local-model"
        yield {"content": "A"}
        yield {"tool_calls": [{"id": "call-1"}]}

    monkeypatch.setattr(connector_svc, "chat_completion_stream_via_connector", fake_stream)

    adapter = connector_svc.LocalConnectorLlmAdapter("connector-1")
    chunks = []
    async for chunk in adapter.chat_completion_stream(
        provider_id="local-connector:test",
        model_name="local-model",
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.2,
        max_tokens=256,
        timeout=30,
        tools=[{"type": "function"}],
    ):
        chunks.append(chunk)

    assert chunks == [{"content": "A"}, {"tool_calls": [{"id": "call-1"}]}]


@pytest.mark.asyncio
async def test_tool_executor_routes_local_connector_run_command(monkeypatch):
    from services import local_connector_service as connector_svc
    from services.tool_executor import ToolExecutor

    captured: dict = {}

    async def fake_run(connector, **kwargs):
        captured["connector"] = connector
        captured["kwargs"] = kwargs
        return {"ok": True, "stdout": "PASS"}

    monkeypatch.setattr(connector_svc, "run_connector_command", fake_run)

    connector = object()
    executor = ToolExecutor(
        "test-proj",
        "test-emp",
        local_connector=connector,
        local_connector_workspace_path="/tmp/workspace",
        local_connector_sandbox_mode="workspace-write",
    )

    result = await executor._execute_tool(
        "local_connector_run_command",
        {"command": "pytest -q", "cwd": "web-admin/api", "timeout_sec": 30},
    )

    assert result["ok"] is True
    assert captured["connector"] is connector
    assert captured["kwargs"]["workspace_path"] == "/tmp/workspace"
    assert captured["kwargs"]["command"] == "pytest -q"
    assert captured["kwargs"]["cwd"] == "web-admin/api"
    assert captured["kwargs"]["timeout_sec"] == 30


@pytest.mark.asyncio
async def test_conversation_manager_logic():
    """测试 ConversationManager 压缩逻辑"""
    from services.conversation_manager import ConversationManager

    redis_mock = MagicMock()
    manager = ConversationManager(redis_mock)

    messages = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好，有什么可以帮助你的？"},
    ]
    summary = await manager._generate_summary(messages)

    assert "user:" in summary
    assert "assistant:" in summary


def test_usage_key_delete_compatibility_allows_legacy_owners():
    from routers.usage import _can_delete_key_record

    assert _can_delete_key_record({"created_by": "tester"}, "tester") is True
    assert _can_delete_key_record({"created_by": ""}, "tester") is True
    assert _can_delete_key_record({"created_by": "unknown"}, "tester") is True
    assert _can_delete_key_record({"created_by": "system-external-agent"}, "tester") is True
    assert _can_delete_key_record({"created_by": "someone-else"}, "tester") is False
    assert _can_delete_key_record(None, "tester") is False


def test_llm_provider_service_allows_shared_users_on_enabled_list(monkeypatch):
    from services.llm_provider_service import LlmProviderService
    import stores.factory as factory_mod

    class DummyStore:
        def __init__(self):
            self.providers = [
                {
                    "id": "p-owned",
                    "name": "Owned Provider",
                    "enabled": True,
                    "models": ["gpt-4.1"],
                    "default_model": "gpt-4.1",
                    "owner_username": "alice",
                    "shared_usernames": [],
                },
                {
                    "id": "p-shared",
                    "name": "Shared Provider",
                    "enabled": True,
                    "models": ["gpt-4.1-mini"],
                    "default_model": "gpt-4.1-mini",
                    "owner_username": "alice",
                    "shared_usernames": ["bob"],
                },
                {
                    "id": "p-disabled",
                    "name": "Disabled Provider",
                    "enabled": False,
                    "models": ["gpt-4o"],
                    "default_model": "gpt-4o",
                    "owner_username": "alice",
                    "shared_usernames": ["bob"],
                },
            ]

        def delete_provider(self, provider_id):
            return True

        def list_providers(self, include_secret=False, enabled_only=False):
            providers = self.providers
            if enabled_only:
                providers = [item for item in providers if bool(item.get("enabled", True))]
            return [dict(item) for item in providers]

        def get_provider(self, provider_id, include_secret=False):
            for item in self.providers:
                if item["id"] == provider_id:
                    return dict(item)
            return None

    service = LlmProviderService(DummyStore())
    monkeypatch.setattr(
        factory_mod,
        "user_store",
        type(
            "DummyUserStore",
            (),
            {"get": staticmethod(lambda username: type("User", (), {"default_ai_provider_id": ""})())},
        )(),
    )

    manageable = service.list_providers(
        enabled_only=False,
        owner_username="bob",
        include_all=False,
        include_shared=False,
    )
    visible = service.list_providers(
        enabled_only=True,
        owner_username="bob",
        include_all=False,
        include_shared=True,
    )

    assert manageable == []
    assert [item["id"] for item in visible] == ["p-shared"]
    assert visible[0]["is_default"] is True


def test_llm_provider_service_blocks_shared_user_from_editing_provider():
    from services.llm_provider_service import LlmProviderService

    class DummyStore:
        def __init__(self):
            self.providers = {
                "p-shared": {
                    "id": "p-shared",
                    "name": "Shared Provider",
                    "enabled": True,
                    "models": ["gpt-4.1-mini"],
                    "default_model": "gpt-4.1-mini",
                    "owner_username": "alice",
                    "shared_usernames": ["bob"],
                }
            }

        def delete_provider(self, provider_id):
            return provider_id in self.providers

        def list_providers(self, include_secret=False, enabled_only=False):
            return [dict(item) for item in self.providers.values()]

        def get_provider(self, provider_id, include_secret=False):
            item = self.providers.get(provider_id)
            return dict(item) if item else None

        def patch_provider(self, provider_id, updates):
            item = self.providers.get(provider_id)
            if item is None:
                return None
            item.update(updates)
            return dict(item)

    service = LlmProviderService(DummyStore())

    with pytest.raises(LookupError):
        service.update_provider(
            "p-shared",
            {"name": "Mutated"},
            owner_username="bob",
            include_all=False,
        )


def test_filter_project_tools_by_names_keeps_tools_when_empty_selection():
    from routers.projects import _filter_project_tools_by_names

    tools = [
        {"tool_name": "query_project_members"},
        {"tool_name": "search_project_context"},
    ]

    assert _filter_project_tools_by_names(tools, [], explicit_filter=True) == tools
    assert _filter_project_tools_by_names(tools, None, explicit_filter=True) == tools
    assert _filter_project_tools_by_names(
        tools,
        ["query_project_members"],
        explicit_filter=True,
    ) == [{"tool_name": "query_project_members"}]


def test_project_detail_runtime_includes_full_config_and_member_lists(tmp_path, monkeypatch):
    from services import dynamic_mcp_context as context_svc
    from stores.json.employee_store import EmployeeConfig, EmployeeStore
    from stores.json.project_store import ProjectConfig, ProjectMember, ProjectStore, ProjectUserMember

    data_dir = tmp_path / "data"
    employee_store = EmployeeStore(data_dir)
    project_store = ProjectStore(data_dir)

    employee_store.save(
        EmployeeConfig(
            id="emp-1",
            name="员工一",
            created_by="tester",
            style_hints=["严谨"],
            auto_evolve=False,
        )
    )
    project_store.save(
        ProjectConfig(
            id="proj-1",
            name="项目一",
            workspace_path="/tmp/workspace",
            chat_settings={"auto_use_tools": False, "model_name": "demo-model"},
        )
    )
    project_store.upsert_member(
        ProjectMember(project_id="proj-1", employee_id="emp-1", role="owner", enabled=True)
    )
    project_store.upsert_user_member(
        ProjectUserMember(project_id="proj-1", username="tester", role="owner", enabled=True)
    )

    monkeypatch.setattr(context_svc, "employee_store", employee_store)
    monkeypatch.setattr(context_svc, "project_store", project_store)

    project_detail = context_svc.get_project_detail_runtime("proj-1")
    employee_detail = context_svc.get_project_employee_detail_runtime("proj-1", "emp-1")

    assert project_detail["id"] == "proj-1"
    assert project_detail["chat_settings"]["auto_use_tools"] is False
    assert project_detail["member_count"] == 1
    assert project_detail["user_count"] == 1
    assert project_detail["members"][0]["employee_id"] == "emp-1"
    assert project_detail["user_members"][0]["username"] == "tester"

    assert employee_detail["project_id"] == "proj-1"
    assert employee_detail["member"]["role"] == "owner"
    assert employee_detail["employee_exists"] is True
    assert employee_detail["employee"]["id"] == "emp-1"
    assert employee_detail["employee"]["style_hints"] == ["严谨"]
    assert employee_detail["employee"]["auto_evolve"] is False
    assert "rule_ids" in employee_detail["employee"]


def test_project_runtime_builtin_tools_include_and_invoke_full_detail_helpers(monkeypatch):
    from services import dynamic_mcp_runtime as runtime_svc

    monkeypatch.setattr(runtime_svc, "_build_project_proxy_specs", lambda project_id: ({}, {}))

    tool_names = {
        item["tool_name"]
        for item in runtime_svc.list_project_proxy_tools_runtime("proj-test", "")
    }

    monkeypatch.setattr(
        runtime_svc,
        "get_project_detail_runtime",
        lambda project_id: {"id": project_id, "chat_settings": {"auto_use_tools": True}},
    )
    monkeypatch.setattr(
        runtime_svc,
        "get_project_employee_detail_runtime",
        lambda project_id, employee_id: {
            "project_id": project_id,
            "employee_id": employee_id,
            "employee_exists": True,
        },
    )

    project_result = runtime_svc.invoke_project_skill_tool_runtime("proj-test", "get_project_detail")
    employee_result = runtime_svc.invoke_project_skill_tool_runtime(
        "proj-test",
        "get_project_employee_detail",
        args={"employee_id": "emp-9"},
    )

    assert "get_project_detail" in tool_names
    assert "get_project_employee_detail" in tool_names
    assert project_result["tool_name"] == "get_project_detail"
    assert project_result["id"] == "proj-test"
    assert project_result["chat_settings"]["auto_use_tools"] is True
    assert employee_result["tool_name"] == "get_project_employee_detail"
    assert employee_result["employee_id"] == "emp-9"
    assert employee_result["employee_exists"] is True


def test_project_mcp_proxy_tool_invocation_passes_project_root_and_api_key(monkeypatch, tmp_path):
    from services import dynamic_mcp_apps_project as project_mcp_svc

    registered_tools: dict[str, object] = {}
    captured: dict = {}

    class FakeMcp:
        def tool(self, name=None, description=None):
            def decorator(fn):
                registered_tools[name or fn.__name__] = fn
                return fn

            return decorator

        def resource(self, *_args, **_kwargs):
            def decorator(fn):
                return fn

            return decorator

        def sse_app(self):
            return "sse-app"

        def streamable_http_app(self):
            return "http-app"

    class FakeCtx:
        def __init__(self, value):
            self.value = value

        def get(self, default=""):
            return self.value if self.value is not None else default

    spec = {
        "employee_id": "emp-1",
        "skill_id": "skill-db",
        "skill_name": "数据库助手",
        "entry_name": "query-db",
        "script_type": "py",
        "script_path": "/tmp/query-db.py",
        "base_tool_name": "skill_db__query_db",
        "scoped_tool_name": "emp_1__skill_db__query_db",
        "description": "Proxy tool for skill-db:query-db",
    }

    monkeypatch.setattr(project_mcp_svc, "_new_mcp", lambda _service_name: FakeMcp())
    monkeypatch.setattr(project_mcp_svc, "_apply_mcp_arguments_compat", lambda app: app)
    monkeypatch.setattr(project_mcp_svc, "_DualTransportMcpApp", lambda sse_app, http_app: (sse_app, http_app))
    monkeypatch.setattr(
        project_mcp_svc,
        "_build_project_proxy_specs",
        lambda _project_id: ({spec["scoped_tool_name"]: spec}, {"emp-1": {spec["base_tool_name"]: spec}}),
    )
    monkeypatch.setattr(project_mcp_svc, "list_project_external_tools_runtime", lambda _project_id: [])

    def fake_execute(spec_item, **kwargs):
        captured["spec"] = spec_item
        captured["kwargs"] = kwargs
        return {"status": "ok"}

    monkeypatch.setattr(project_mcp_svc, "_execute_skill_proxy", fake_execute)

    project_mcp_svc.create_project_mcp(
        "proj-1",
        current_api_key_ctx=FakeCtx("api-key-123"),
        current_developer_name_ctx=FakeCtx("tester"),
        project_root=tmp_path,
        recall_limit=20,
    )

    result = registered_tools[spec["scoped_tool_name"]](args={"sql": "show tables"}, timeout_sec=15)

    assert result["status"] == "ok"
    assert captured["spec"] == spec
    assert captured["kwargs"]["project_root"] == tmp_path
    assert captured["kwargs"]["current_api_key"] == "api-key-123"
    assert captured["kwargs"]["employee_id"] == "emp-1"
    assert captured["kwargs"]["args"] == {"sql": "show tables"}
    assert captured["kwargs"]["timeout_sec"] == 15


def test_project_chat_store_truncate_messages_updates_session_snapshot(tmp_path):
    """截断聊天记录后应同步更新会话快照与消息计数"""
    from stores.json.project_chat_store import ProjectChatMessage, ProjectChatStore

    store = ProjectChatStore(tmp_path / "data")
    session = store.create_session("proj-test", "tester", title="新对话")

    store.append_message(
        ProjectChatMessage(
            id="msg-user-1",
            project_id="proj-test",
            username="tester",
            role="user",
            content="第一条问题",
            chat_session_id=session.id,
        )
    )
    store.append_message(
        ProjectChatMessage(
            id="msg-assistant-1",
            project_id="proj-test",
            username="tester",
            role="assistant",
            content="第一条回答",
            chat_session_id=session.id,
        )
    )
    store.append_message(
        ProjectChatMessage(
            id="msg-user-2",
            project_id="proj-test",
            username="tester",
            role="user",
            content="第二条问题",
            chat_session_id=session.id,
        )
    )
    store.append_message(
        ProjectChatMessage(
            id="msg-assistant-2",
            project_id="proj-test",
            username="tester",
            role="assistant",
            content="第二条回答",
            chat_session_id=session.id,
        )
    )

    removed = store.truncate_messages(
        "proj-test",
        "tester",
        "msg-user-2",
        session.id,
    )

    assert removed == 2
    messages = store.list_messages("proj-test", "tester", chat_session_id=session.id)
    assert [item.id for item in messages] == ["msg-user-1", "msg-assistant-1"]

    sessions = store.list_sessions("proj-test", "tester")
    assert len(sessions) == 1
    assert sessions[0].id == session.id
    assert sessions[0].preview == "第一条回答"
    assert sessions[0].message_count == 2


def test_project_chat_store_keeps_full_history_without_auto_trim(tmp_path):
    """聊天记录不应因为条数过多被自动裁掉"""
    from stores.json.project_chat_store import ProjectChatMessage, ProjectChatStore

    store = ProjectChatStore(tmp_path / "data")
    session = store.create_session("proj-test", "tester", title="新对话")

    for index in range(1005):
        store.append_message(
            ProjectChatMessage(
                id=f"msg-{index}",
                project_id="proj-test",
                username="tester",
                role="user" if index % 2 == 0 else "assistant",
                content=f"消息 {index}",
                chat_session_id=session.id,
            )
        )

    messages = store.list_messages(
        "proj-test",
        "tester",
        limit=0,
        chat_session_id=session.id,
    )
    assert len(messages) == 1005
    assert messages[0].id == "msg-0"
    assert messages[-1].id == "msg-1004"


def test_project_chat_store_list_messages_supports_offset_pagination(tmp_path):
    """聊天记录应支持按最新消息向前分页读取"""
    from stores.json.project_chat_store import ProjectChatMessage, ProjectChatStore

    store = ProjectChatStore(tmp_path / "data")
    session = store.create_session("proj-test", "tester", title="新对话")

    for index in range(6):
        store.append_message(
            ProjectChatMessage(
                id=f"msg-{index}",
                project_id="proj-test",
                username="tester",
                role="user",
                content=f"消息 {index}",
                chat_session_id=session.id,
            )
        )

    latest = store.list_messages(
        "proj-test",
        "tester",
        limit=2,
        offset=0,
        chat_session_id=session.id,
    )
    previous = store.list_messages(
        "proj-test",
        "tester",
        limit=2,
        offset=2,
        chat_session_id=session.id,
    )
    oldest = store.list_messages(
        "proj-test",
        "tester",
        limit=2,
        offset=4,
        chat_session_id=session.id,
    )

    assert [item.id for item in latest] == ["msg-4", "msg-5"]
    assert [item.id for item in previous] == ["msg-2", "msg-3"]
    assert [item.id for item in oldest] == ["msg-0", "msg-1"]


def test_public_project_chat_settings_preserves_connector_configuration():
    """对话设置标准化后应保留连接器工作区配置。"""
    from routers import projects as projects_router

    settings = projects_router._public_project_chat_settings(
        {
            "chat_mode": "system",
            "connector_sandbox_mode": "workspace-write",
            "local_connector_id": "connector-1",
            "connector_workspace_path": "/tmp/workspace",
        }
    )

    assert settings["chat_mode"] == "system"
    assert settings["connector_sandbox_mode"] == "workspace-write"
    assert settings["local_connector_id"] == "connector-1"
    assert settings["connector_workspace_path"] == "/tmp/workspace"


def test_merge_project_chat_settings_overrides_keeps_persisted_connector_when_query_empty():
    """providers 接口在没有覆盖参数时，应保留已保存的连接器和工作区"""
    from routers import projects as projects_router

    merged = projects_router._merge_project_chat_settings_overrides(
        {
            "chat_mode": "system",
            "connector_sandbox_mode": "workspace-write",
            "local_connector_id": "connector-1",
            "connector_workspace_path": "/tmp/workspace",
        },
        local_connector_id="",
        connector_workspace_path="",
    )

    assert merged["chat_mode"] == "system"
    assert merged["connector_sandbox_mode"] == "workspace-write"
    assert merged["local_connector_id"] == "connector-1"
    assert merged["connector_workspace_path"] == "/tmp/workspace"


@pytest.mark.asyncio
async def test_delete_employee_removes_project_memberships(tmp_path, monkeypatch):
    """删除员工时应同步移除其所有项目成员记录"""
    from routers import employees as employees_router
    from stores.json.employee_store import EmployeeConfig, EmployeeStore
    from stores.json.project_store import ProjectConfig, ProjectMember, ProjectStore

    data_dir = tmp_path / "data"
    employee_store = EmployeeStore(data_dir)
    project_store = ProjectStore(data_dir)

    employee_store.save(EmployeeConfig(id="emp-1", name="员工一", created_by="tester"))
    employee_store.save(EmployeeConfig(id="emp-2", name="员工二", created_by="tester"))

    project_store.save(ProjectConfig(id="proj-a", name="项目A"))
    project_store.save(ProjectConfig(id="proj-b", name="项目B"))
    project_store.upsert_member(ProjectMember(project_id="proj-a", employee_id="emp-1"))
    project_store.upsert_member(ProjectMember(project_id="proj-a", employee_id="emp-2"))
    project_store.upsert_member(ProjectMember(project_id="proj-b", employee_id="emp-1"))

    monkeypatch.setattr(employees_router, "employee_store", employee_store)
    monkeypatch.setattr(employees_router, "project_store", project_store)

    result = await employees_router.delete_employee("emp-1", {"sub": "tester"})

    assert result["status"] == "deleted"
    assert result["employee_id"] == "emp-1"
    assert result["removed_project_member_count"] == 2
    assert set(result["removed_project_ids"]) == {"proj-a", "proj-b"}
    assert employee_store.get("emp-1") is None
    assert project_store.get_member("proj-a", "emp-1") is None
    assert project_store.get_member("proj-b", "emp-1") is None
    assert project_store.get_member("proj-a", "emp-2") is not None


@pytest.mark.asyncio
async def test_create_employee_from_draft_auto_creates_missing_skill_and_rule(tmp_path, monkeypatch):
    """员工草稿创建应自动补齐缺失技能和规则，再完成员工创建"""
    from routers import employees as employees_router
    from models.requests import EmployeeDraftCreateReq
    from stores import mcp_bridge
    from stores.json.employee_store import EmployeeStore
    from stores.json.project_store import ProjectStore

    data_dir = tmp_path / "data"
    employee_store = EmployeeStore(data_dir)
    project_store = ProjectStore(data_dir)
    skill_store = mcp_bridge._skills_mod.SkillStore(data_dir / "skills-runtime")
    rule_store = mcp_bridge._rules_mod.RuleStore(data_dir / "rules-runtime")

    monkeypatch.setattr(employees_router, "employee_store", employee_store)
    monkeypatch.setattr(employees_router, "project_store", project_store)
    monkeypatch.setattr(employees_router, "skill_store", skill_store)
    monkeypatch.setattr(employees_router, "rule_store", rule_store)

    req = EmployeeDraftCreateReq(
        name="产品经理助手",
        description="负责 PRD 拆解与评审建议",
        goal="输出结构化需求分析和改进建议",
        skills=["PRD 拆解"],
        rule_titles=["需求澄清优先"],
        rule_domains=["product"],
        style_hints=["先结论后展开"],
    )

    result = await employees_router.create_employee_from_draft(req, {"sub": "tester"})

    assert result["status"] == "created"
    assert len(result["created_skills"]) == 1
    assert len(result["created_rules"]) == 1

    employee = employee_store.get(result["employee"]["id"])
    assert employee is not None
    assert employee.skills == [result["created_skills"][0]["id"]]
    assert employee.rule_ids == [result["created_rules"][0]["id"]]

    created_skill = skill_store.get(result["created_skills"][0]["id"])
    assert created_skill is not None
    skill_package = skill_store.package_path(created_skill.id)
    assert skill_package.exists()
    assert (skill_package / "SKILL.md").exists()

    created_rule = rule_store.get(result["created_rules"][0]["id"])
    assert created_rule is not None
    assert created_rule.domain == "product"
    assert "需求澄清优先" in created_rule.title


if __name__ == "__main__":
    asyncio.run(test_orchestrator_logic())
    asyncio.run(test_tool_executor_logic())
    asyncio.run(test_conversation_manager_logic())
    print("\n✅ 所有单元测试通过")
