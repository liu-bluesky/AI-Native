"""监控端点"""
from fastapi import APIRouter
from core.observability import metrics

router = APIRouter(prefix="/api/metrics")

@router.get("/stats")
async def get_metrics_stats():
    """获取指标统计"""
    return metrics.get_stats()

@router.post("/reset")
async def reset_metrics():
    """重置指标（仅用于测试）"""
    metrics._counters.clear()
    metrics._histograms.clear()
    return {"status": "ok", "message": "Metrics reset"}
