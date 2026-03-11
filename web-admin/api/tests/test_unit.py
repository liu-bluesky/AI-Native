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


def test_prepare_external_agent_workspace_context_generates_gemini_settings(tmp_path, monkeypatch):
    """Gemini 外部 Agent 应生成工作区 settings 并镜像认证文件"""
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

    materialized_copies = list((context.get("materialization") or {}).get("copies") or [])
    assert any(str(item.get("target_path") or "").endswith("/gemini-home/.gemini/oauth_creds.json") for item in materialized_copies)


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


if __name__ == "__main__":
    asyncio.run(test_orchestrator_logic())
    asyncio.run(test_tool_executor_logic())
    asyncio.run(test_conversation_manager_logic())
    print("\n✅ 所有单元测试通过")
