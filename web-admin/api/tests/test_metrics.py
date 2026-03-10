"""测试监控功能"""

import asyncio

from core.observability import logger, metrics


async def test_metrics():
    """测试指标收集"""
    metrics.inc_counter("test_counter")
    metrics.inc_counter("test_counter")
    metrics.inc_counter("test_counter", {"label": "value"})

    metrics.observe_histogram("test_duration", 100.5)
    metrics.observe_histogram("test_duration", 200.3)
    metrics.observe_histogram("test_duration", 150.7)

    stats = metrics.get_stats()

    logger.info("metrics_test_snapshot", counters=stats["counters"], histograms=stats["histograms"])

    assert stats["counters"]["test_counter"] == 2
    assert "test_duration" in stats["histograms"]
    assert stats["histograms"]["test_duration"]["count"] == 3


if __name__ == "__main__":
    asyncio.run(test_metrics())
    print("\n✅ 监控功能测试通过")
