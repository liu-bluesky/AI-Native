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


if __name__ == "__main__":
    asyncio.run(test_orchestrator_logic())
    asyncio.run(test_tool_executor_logic())
    asyncio.run(test_conversation_manager_logic())
    print("\n✅ 所有单元测试通过")
