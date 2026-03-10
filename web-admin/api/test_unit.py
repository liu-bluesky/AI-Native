"""模拟测试（无需 Redis）"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.mark.asyncio
async def test_orchestrator_logic():
    """测试 AgentOrchestrator 逻辑"""
    from agent_orchestrator import AgentOrchestrator

    # Mock 依赖
    llm_service = MagicMock()
    conv_manager = MagicMock()
    conv_manager.get_context = AsyncMock(return_value=[])
    conv_manager.append_message = AsyncMock()

    orchestrator = AgentOrchestrator(llm_service, conv_manager)

    # 测试工具格式化
    tools = [{"tool_name": "test_tool", "description": "测试工具"}]
    formatted = orchestrator._format_tools(tools)

    assert len(formatted) == 1
    assert formatted[0]["type"] == "function"
    assert formatted[0]["function"]["name"] == "test_tool"

    print("✅ AgentOrchestrator 逻辑测试通过")

@pytest.mark.asyncio
async def test_tool_executor_logic():
    """测试 ToolExecutor 逻辑"""
    from tool_executor import ToolExecutor

    executor = ToolExecutor("test-proj", "test-emp")

    # 测试超时参数
    assert executor._timeout == 60  # 默认值

    print("✅ ToolExecutor 逻辑测试通过")

@pytest.mark.asyncio
async def test_conversation_manager_logic():
    """测试 ConversationManager 压缩逻辑"""
    from conversation_manager import ConversationManager

    # Mock Redis
    redis_mock = MagicMock()
    manager = ConversationManager(redis_mock)

    # 测试摘要生成
    messages = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好，有什么可以帮助你的？"}
    ]
    summary = await manager._generate_summary(messages)

    assert "user:" in summary
    assert "assistant:" in summary

    print("✅ ConversationManager 逻辑测试通过")

if __name__ == "__main__":
    asyncio.run(test_orchestrator_logic())
    asyncio.run(test_tool_executor_logic())
    asyncio.run(test_conversation_manager_logic())
    print("\n✅ 所有单元测试通过")
