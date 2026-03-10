"""测试监控功能"""
import asyncio
from observability import metrics, logger

async def test_metrics():
    """测试指标收集"""
    # 模拟计数器
    metrics.inc_counter("test_counter")
    metrics.inc_counter("test_counter")
    metrics.inc_counter("test_counter", {"label": "value"})

    # 模拟直方图
    metrics.observe_histogram("test_duration", 100.5)
    metrics.observe_histogram("test_duration", 200.3)
    metrics.observe_histogram("test_duration", 150.7)

    # 获取统计
    stats = metrics.get_stats()

    print("✅ 指标统计:")
    print(f"  计数器: {stats['counters']}")
    print(f"  直方图: {stats['histograms']}")

    assert stats['counters']['test_counter'] == 2
    assert 'test_duration' in stats['histograms']
    assert stats['histograms']['test_duration']['count'] == 3

    print("\n✅ 监控功能测试通过")

if __name__ == "__main__":
    asyncio.run(test_metrics())
