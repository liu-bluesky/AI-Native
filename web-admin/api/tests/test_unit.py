"""模拟测试（无需 Redis）"""

import asyncio
import json
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


def test_prepare_external_agent_workspace_context_generates_gemini_settings(tmp_path, monkeypatch):
    """Gemini 外部 Agent 应生成工作区 settings，并且不再依赖 .ai-employee 目录"""
    from services import external_agent_service as svc

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    host_gemini_dir = tmp_path / "host-home" / ".gemini"
    host_gemini_dir.mkdir(parents=True)
    (host_gemini_dir / "oauth_creds.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(svc, "_gemini_host_user_dir", lambda: host_gemini_dir)

    context = svc.prepare_external_agent_workspace_context(
        project_id="proj-test",
        project_name="Test",
        project_description="",
        workspace_path=str(workspace),
        sandbox_mode="workspace-write",
        agent_type="gemini_cli",
        selected_employee_names=[],
        candidate_preview=[],
        system_prompt="",
        mcp_bridge={
            "enabled": True,
            "server_name": "project_proj_test",
            "url": "http://127.0.0.1:8000/mcp/projects/proj-test/sse?key=test-key",
        },
        write_files=False,
    )

    materialized_files = list((context.get("materialization") or {}).get("files") or [])
    gemini_settings = next(
        item for item in materialized_files if item.get("kind") == "generated_gemini_workspace_settings"
    )
    gemini_settings_payload = json.loads(str(gemini_settings.get("content") or "{}"))
    assert gemini_settings_payload["mcpServers"]["project_proj_test"]["type"] == "sse"

    support_files = list(context.get("support_files") or [])
    assert any(item.get("kind") == "generated_gemini_workspace_settings" for item in support_files)
    assert not any(str(item.get("path") or "").startswith(".ai-employee/") for item in support_files)
    assert context.get("support_dir") == ""

    materialized_copies = list((context.get("materialization") or {}).get("copies") or [])
    materialized_files = list((context.get("materialization") or {}).get("files") or [])
    assert any(str(item.get("target_path") or "").endswith("/.gemini-home/.gemini/oauth_creds.json") for item in materialized_copies)
    assert not any(".ai-employee" in str(item.get("path") or "") for item in materialized_files)


def test_detect_gemini_auth_mode_from_user_env_file(tmp_path, monkeypatch):
    """Gemini 认证模式应能从用户 .env 探测到 API Key"""
    from services import external_agent_service as svc

    host_gemini_dir = tmp_path / "host-home" / ".gemini"
    host_gemini_dir.mkdir(parents=True)
    (host_gemini_dir / ".env").write_text("GEMINI_API_KEY=test-key\n", encoding="utf-8")
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    monkeypatch.setattr(svc, "_gemini_host_user_dir", lambda: host_gemini_dir)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    assert svc._detect_gemini_auth_mode(str(workspace)) == "gemini-api-key"


def test_resolve_gemini_passthrough_env_from_user_env_file(tmp_path, monkeypatch):
    """Gemini 运行时应透传自定义 base url 和 model"""
    from services import external_agent_service as svc

    host_gemini_dir = tmp_path / "host-home" / ".gemini"
    host_gemini_dir.mkdir(parents=True)
    (host_gemini_dir / ".env").write_text(
        "GOOGLE_GEMINI_BASE_URL=https://example-proxy.invalid\nGEMINI_MODEL=gemini-2.5-pro\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(svc, "_gemini_host_user_dir", lambda: host_gemini_dir)
    monkeypatch.delenv("GOOGLE_GEMINI_BASE_URL", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)

    env = svc._resolve_gemini_passthrough_env()
    assert env["GOOGLE_GEMINI_BASE_URL"] == "https://example-proxy.invalid"
    assert env["GEMINI_MODEL"] == "gemini-2.5-pro"


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
