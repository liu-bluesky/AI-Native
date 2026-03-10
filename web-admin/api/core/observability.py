from __future__ import annotations

import time
from collections import defaultdict
from functools import wraps

import structlog

logger = structlog.get_logger()


class MetricsCollector:
    def __init__(self):
        self._counters = defaultdict(int)
        self._histograms = defaultdict(list)

    def inc_counter(self, name: str, labels: dict | None = None):
        key = f"{name}:{labels}" if labels else name
        self._counters[key] += 1

    def observe_histogram(self, name: str, value: float, labels: dict | None = None):
        key = f"{name}:{labels}" if labels else name
        self._histograms[key].append(value)

    def get_stats(self) -> dict:
        stats = {"counters": dict(self._counters), "histograms": {}}
        for key, values in self._histograms.items():
            if values:
                stats["histograms"][key] = {
                    "count": len(values),
                    "avg": sum(values) / len(values),
                    "min": min(values),
                    "max": max(values),
                }
        return stats


metrics = MetricsCollector()


def log_execution(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start = time.time()
        func_name = func.__name__
        try:
            result = await func(*args, **kwargs)
            duration = time.time() - start
            metrics.observe_histogram(f"{func_name}_duration", duration * 1000)
            metrics.inc_counter(f"{func_name}_success")
            logger.info(f"{func_name}_completed", duration_ms=int(duration * 1000))
            return result
        except Exception as error:
            duration = time.time() - start
            metrics.inc_counter(f"{func_name}_error")
            logger.error(
                f"{func_name}_failed",
                error=str(error),
                duration_ms=int(duration * 1000),
            )
            raise

    return wrapper
