"""性能测试脚本"""

import asyncio
import time

import redis.asyncio as redis

from services.conversation_manager import ConversationManager


async def test_compression():
    """测试上下文压缩"""
    client = redis.Redis(host="localhost", port=6379, decode_responses=True)
    manager = ConversationManager(client)

    session_id = await manager.create_session("test-proj", "test-emp")

    for index in range(20):
        await manager.append_message(
            session_id,
            {"role": "user", "content": f"消息 {index}"},
        )

    start = time.time()
    context = await manager.get_context(session_id, 4000)
    duration = time.time() - start

    print(f"✅ 压缩测试: {len(context)} 条消息, 耗时 {duration * 1000:.2f}ms")
    await client.close()


async def test_concurrent_sessions():
    """测试并发会话"""
    client = redis.Redis(host="localhost", port=6379, decode_responses=True)
    manager = ConversationManager(client)

    async def create_session(index: int):
        session_id = await manager.create_session(f"proj-{index}", f"emp-{index}")
        await manager.append_message(
            session_id,
            {"role": "user", "content": f"测试 {index}"},
        )
        return session_id

    start = time.time()
    sessions = await asyncio.gather(*[create_session(index) for index in range(50)])
    duration = time.time() - start

    print(f"✅ 并发测试: 创建 {len(sessions)} 个会话, 耗时 {duration * 1000:.2f}ms")
    await client.close()


if __name__ == "__main__":
    asyncio.run(test_compression())
    asyncio.run(test_concurrent_sessions())
