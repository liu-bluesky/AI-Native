"""平台统计聚合路由"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query

from core.deps import (
    employee_store,
    ensure_permission,
    project_store,
    require_auth,
    usage_store,
    work_session_store,
)
from core.observability import metrics
from services.project_mcp_presence import list_active_system_mcp_presence


router = APIRouter(prefix="/api/statistics")
public_router = None


def _require_statistics_permission(auth_payload: dict = Depends(require_auth)) -> dict:
    ensure_permission(auth_payload, "menu.statistics")
    return auth_payload


def _normalize_text(value: object, limit: int = 400) -> str:
    return str(value or "").strip()[:limit]


def _safe_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _format_percentage(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0%"
    return f"{round((numerator / denominator) * 100)}%"


def _percentage_value(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100, 1)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_days(value: int | None, *, default: int = 7, minimum: int = 1, maximum: int = 90) -> int:
    try:
        return max(minimum, min(int(value or default), maximum))
    except (TypeError, ValueError):
        return default


def _parse_iso_datetime(value: object) -> datetime | None:
    raw = _normalize_text(value, 40)
    if not raw:
        return None
    normalized = raw.replace(" ", "T").replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _resolve_employee_name(employee_id: object) -> str:
    normalized_id = _normalize_text(employee_id, 80)
    if not normalized_id:
        return ""
    try:
        employee = employee_store.get(normalized_id)
    except Exception:
        employee = None
    return _normalize_text(getattr(employee, "name", ""), 120) or normalized_id


def _is_ai_employee_id(employee_id: object) -> bool:
    return _normalize_text(employee_id, 80).startswith("emp-")


def _resolve_project_name(project_id: object, fallback_name: object = "") -> str:
    normalized_id = _normalize_text(project_id, 80)
    fallback = _normalize_text(fallback_name, 160)
    if normalized_id:
        try:
            project = project_store.get(normalized_id)
        except Exception:
            project = None
        resolved = _normalize_text(getattr(project, "name", ""), 160)
        if resolved:
            return resolved
    return fallback or normalized_id


def _build_statistics_scope(project_id: object) -> dict:
    normalized_project_id = _normalize_text(project_id, 80)
    if normalized_project_id:
        project_name = _resolve_project_name(normalized_project_id)
        display_name = project_name or normalized_project_id
        return {
            "scope_type": "project",
            "project_id": normalized_project_id,
            "project_name": display_name,
            "display_name": display_name,
        }
    return {
        "scope_type": "global",
        "project_id": "",
        "project_name": "",
        "display_name": "全局统计",
    }


def _resolve_scope_label(scope_id: object) -> str:
    normalized_id = _normalize_text(scope_id, 120)
    if not normalized_id:
        return ""
    if normalized_id == "mcp:query":
        return "统一查询 MCP"
    if normalized_id.startswith("project:"):
        return f"项目入口 · {normalized_id.split(':', 1)[1] or normalized_id}"
    if normalized_id.startswith("employee:"):
        employee_id = normalized_id.split(":", 1)[1]
        employee_name = _resolve_employee_name(employee_id)
        return f"员工入口 · {employee_name or employee_id or normalized_id}"
    return normalized_id


def _resolve_scope_kind(scope_id: object) -> str:
    normalized_id = _normalize_text(scope_id, 120)
    if normalized_id == "mcp:query":
        return "query"
    if normalized_id.startswith("project:"):
        return "project"
    if normalized_id.startswith("employee:"):
        return "employee"
    if normalized_id.startswith("mcp:"):
        return "system"
    return "other"


def _decorate_usage_overview(usage: dict) -> dict:
    top_employees = []
    for row in usage.get("top_employees") or []:
        employee_id = _normalize_text(row.get("employee_id", ""), 80)
        if not _is_ai_employee_id(employee_id):
            continue
        employee_name = _resolve_employee_name(employee_id)
        top_employees.append(
            {
                **row,
                "employee_id": employee_id,
                "employee_name": employee_name,
                "label": employee_name or employee_id or "未知智能体",
            }
        )
    top_scopes = []
    for row in usage.get("top_scopes") or []:
        scope_id = _normalize_text(row.get("scope_id", ""), 120)
        if not scope_id:
            continue
        top_scopes.append(
            {
                **row,
                "scope_id": scope_id,
                "scope_label": _resolve_scope_label(scope_id) or scope_id,
                "scope_kind": _resolve_scope_kind(scope_id),
                "is_query_scope": scope_id == "mcp:query",
            }
        )
    top_projects = []
    for row in usage.get("top_projects") or []:
        project_id = _normalize_text(row.get("project_id", ""), 80)
        project_name = _resolve_project_name(project_id, row.get("project_name", ""))
        if not (project_id or project_name):
            continue
        top_projects.append(
            {
                **row,
                "project_id": project_id,
                "project_name": project_name or project_id or "未标记项目",
            }
        )
    return {
        **usage,
        "top_employees": top_employees,
        "top_scopes": top_scopes,
        "top_projects": top_projects,
    }


def _build_work_session_overview(*, days: int, limit: int = 500, project_id: str = "") -> dict:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    normalized_project_id = _normalize_text(project_id, 80)
    grouped: dict[str, dict] = {}
    for event in work_session_store.list_events(limit=limit):
        updated_at = _parse_iso_datetime(getattr(event, "updated_at", "") or getattr(event, "created_at", ""))
        if updated_at is not None and updated_at < cutoff:
            continue
        event_project_id = _normalize_text(getattr(event, "project_id", ""), 80)
        if normalized_project_id and event_project_id != normalized_project_id:
            continue
        session_id = _normalize_text(getattr(event, "session_id", ""), 80)
        if not session_id:
            continue
        bucket = grouped.setdefault(
            session_id,
            {
                "session_id": session_id,
                "project_id": event_project_id,
                "project_name": _normalize_text(getattr(event, "project_name", ""), 120),
                "employee_id": _normalize_text(getattr(event, "employee_id", ""), 80),
                "latest_status": "",
                "latest_updated_at": "",
                "event_count": 0,
                "phases": [],
                "steps": [],
                "verification": [],
            },
        )
        bucket["event_count"] += 1
        phase = _normalize_text(getattr(event, "phase", ""), 80)
        if phase and phase not in bucket["phases"]:
            bucket["phases"].append(phase)
        step = _normalize_text(getattr(event, "step", ""), 120)
        if step and step not in bucket["steps"]:
            bucket["steps"].append(step)
        for item in getattr(event, "verification", []) or []:
            normalized_item = _normalize_text(item, 240)
            if normalized_item and normalized_item not in bucket["verification"]:
                bucket["verification"].append(normalized_item)
        updated_token = _normalize_text(getattr(event, "updated_at", "") or getattr(event, "created_at", ""), 40)
        if updated_token >= bucket["latest_updated_at"]:
            bucket["latest_updated_at"] = updated_token
            bucket["latest_status"] = _normalize_text(getattr(event, "status", ""), 40) or bucket["latest_status"]

    sessions = sorted(
        grouped.values(),
        key=lambda item: (item.get("latest_updated_at") or "", item.get("session_id") or ""),
        reverse=True,
    )
    summary = {
        "total_sessions": len(sessions),
        "in_progress_sessions": 0,
        "completed_sessions": 0,
        "blocked_sessions": 0,
        "recent_active_sessions": len([item for item in sessions if item.get("latest_updated_at")]),
    }
    for item in sessions:
        status = _normalize_text(item.get("latest_status", ""), 40).lower()
        if status == "completed":
            summary["completed_sessions"] += 1
        elif status in {"blocked", "failed"}:
            summary["blocked_sessions"] += 1
        else:
            summary["in_progress_sessions"] += 1
    summary["completion_rate"] = _percentage_value(
        summary["completed_sessions"],
        summary["total_sessions"],
    )
    summary["in_progress_rate"] = _percentage_value(
        summary["in_progress_sessions"],
        summary["total_sessions"],
    )
    summary["blocked_rate"] = _percentage_value(
        summary["blocked_sessions"],
        summary["total_sessions"],
    )
    summary["closure_gap_sessions"] = max(
        summary["in_progress_sessions"] - summary["completed_sessions"],
        0,
    )

    project_activity: dict[str, dict] = {}
    employee_activity: dict[str, dict] = {}
    daily_activity: dict[str, dict] = {}
    for item in sessions:
        project_id = _normalize_text(item.get("project_id", ""), 80)
        project_name = _resolve_project_name(project_id, item.get("project_name", ""))
        project_key = project_id or project_name or "unknown-project"
        bucket = project_activity.setdefault(
            project_key,
            {
                "project_id": project_id,
                "project_name": project_name or project_id or "未标记项目",
                "session_count": 0,
                "event_count": 0,
                "completed_sessions": 0,
                "in_progress_sessions": 0,
                "blocked_sessions": 0,
                "latest_updated_at": "",
            },
        )
        bucket["session_count"] += 1
        bucket["event_count"] += _safe_int(item.get("event_count"))
        status = _normalize_text(item.get("latest_status", ""), 40).lower()
        if status == "completed":
            bucket["completed_sessions"] += 1
        elif status in {"blocked", "failed"}:
            bucket["blocked_sessions"] += 1
        else:
            bucket["in_progress_sessions"] += 1
        latest_updated_at = _normalize_text(item.get("latest_updated_at", ""), 40)
        if latest_updated_at >= bucket["latest_updated_at"]:
            bucket["latest_updated_at"] = latest_updated_at
        latest_updated_dt = _parse_iso_datetime(latest_updated_at)
        if latest_updated_dt is not None:
            daily_key = latest_updated_dt.date().isoformat()
            daily_bucket = daily_activity.setdefault(
                daily_key,
                {
                    "date": daily_key,
                    "total_sessions": 0,
                    "completed_sessions": 0,
                    "in_progress_sessions": 0,
                    "blocked_sessions": 0,
                },
            )
            daily_bucket["total_sessions"] += 1
            if status == "completed":
                daily_bucket["completed_sessions"] += 1
            elif status in {"blocked", "failed"}:
                daily_bucket["blocked_sessions"] += 1
            else:
                daily_bucket["in_progress_sessions"] += 1

        employee_id = _normalize_text(item.get("employee_id", ""), 80)
        if _is_ai_employee_id(employee_id):
            employee_key = employee_id
            employee_bucket = employee_activity.setdefault(
                employee_key,
                {
                    "employee_id": employee_id,
                    "employee_name": _resolve_employee_name(employee_id),
                    "session_count": 0,
                    "event_count": 0,
                    "project_ids": set(),
                    "project_count": 0,
                    "latest_updated_at": "",
                },
            )
            employee_bucket["session_count"] += 1
            employee_bucket["event_count"] += _safe_int(item.get("event_count"))
            if project_id:
                employee_bucket["project_ids"].add(project_id)
                employee_bucket["project_count"] = len(employee_bucket["project_ids"])
            if latest_updated_at >= employee_bucket["latest_updated_at"]:
                employee_bucket["latest_updated_at"] = latest_updated_at

    summary["active_employees"] = len(employee_activity)
    summary["active_projects"] = len(project_activity)

    daily = []
    start_date = cutoff.date()
    end_date = now.date()
    current_date = start_date
    while current_date <= end_date:
        date_key = current_date.isoformat()
        item = daily_activity.get(
            date_key,
            {
                "date": date_key,
                "total_sessions": 0,
                "completed_sessions": 0,
                "in_progress_sessions": 0,
                "blocked_sessions": 0,
            },
        )
        daily.append(
            {
                **item,
                "completion_rate": _percentage_value(
                    _safe_int(item.get("completed_sessions")),
                    _safe_int(item.get("total_sessions")),
                ),
            }
        )
        current_date += timedelta(days=1)

    top_employees = [
        {
            "employee_id": row["employee_id"],
            "employee_name": row["employee_name"] or row["employee_id"] or "未知智能体",
            "session_count": row["session_count"],
            "event_count": row["event_count"],
            "project_count": row["project_count"],
            "latest_updated_at": row["latest_updated_at"],
        }
        for row in sorted(
            employee_activity.values(),
            key=lambda row: (
                _safe_int(row.get("event_count")),
                _safe_int(row.get("session_count")),
                _safe_int(row.get("project_count")),
                _normalize_text(row.get("latest_updated_at", ""), 40),
                _normalize_text(row.get("employee_name", ""), 160),
            ),
            reverse=True,
        )[:8]
    ]
    top_projects = []
    for row in sorted(
        project_activity.values(),
        key=lambda row: (
            _safe_int(row.get("event_count")),
            _safe_int(row.get("session_count")),
            _normalize_text(row.get("latest_updated_at", ""), 40),
            _normalize_text(row.get("project_name", ""), 160),
        ),
        reverse=True,
    )[:8]:
        top_projects.append(
            {
                **row,
                "completion_rate": _percentage_value(
                    _safe_int(row.get("completed_sessions")),
                    _safe_int(row.get("session_count")),
                ),
                "blocked_rate": _percentage_value(
                    _safe_int(row.get("blocked_sessions")),
                    _safe_int(row.get("session_count")),
                ),
            }
        )

    return {
        "days": days,
        "summary": summary,
        "daily": daily,
        "recent": sessions[:10],
        "top_projects": top_projects,
        "top_employees": top_employees,
    }


def _build_runtime_metric_overview() -> dict:
    metric_stats = metrics.get_stats()
    counter_items = sorted(
        (
            {"key": key, "value": int(value or 0)}
            for key, value in (metric_stats.get("counters") or {}).items()
        ),
        key=lambda item: (item["value"], item["key"]),
        reverse=True,
    )
    histogram_items = sorted(
        (
            {
                "key": key,
                "count": int(value.get("count") or 0),
                "avg": float(value.get("avg") or 0),
                "min": float(value.get("min") or 0),
                "max": float(value.get("max") or 0),
            }
            for key, value in (metric_stats.get("histograms") or {}).items()
        ),
        key=lambda item: (item["count"], item["key"]),
        reverse=True,
    )
    return {
        "counter_total": len(counter_items),
        "histogram_total": len(histogram_items),
        "top_counters": counter_items[:10],
        "top_histograms": histogram_items[:10],
    }


def _build_statistics_insights(*, days: int, usage: dict, work_sessions: dict, live_activity: dict) -> tuple[dict, list[dict]]:
    usage_summary = usage.get("summary") or {}
    usage_tool_health = usage.get("tool_health") or {}
    work_session_summary = work_sessions.get("summary") or {}
    live_summary = live_activity.get("summary") or {}
    daily_rows = usage.get("daily") or []
    active_days = len([item for item in daily_rows if _safe_int(item.get("total_events")) > 0])
    peak_day = max(daily_rows, key=lambda item: _safe_int(item.get("total_events")), default=None)

    total_events = _safe_int(usage_summary.get("total_events"))
    tool_calls = _safe_int(usage_summary.get("tool_calls"))
    connections = _safe_int(usage_summary.get("connections"))
    finalized_tool_calls = _safe_int(usage_summary.get("finalized_tool_calls"))
    successful_tool_calls = _safe_int(usage_summary.get("successful_tool_calls"))
    failed_tool_calls = _safe_int(usage_summary.get("failed_tool_calls"))
    timeout_tool_calls = _safe_int(usage_summary.get("timeout_tool_calls"))
    tool_success_rate = _safe_float(usage_summary.get("tool_success_rate") or usage_tool_health.get("success_rate"))
    avg_tool_duration_ms = _safe_float(usage_summary.get("avg_tool_duration_ms") or usage_tool_health.get("avg_duration_ms"))
    active_projects = (
        _safe_int(usage_summary.get("active_projects"))
        or _safe_int(live_summary.get("active_projects"))
        or _safe_int(work_session_summary.get("active_projects"))
    )
    active_agents = (
        _safe_int(usage_summary.get("active_employees"))
        or _safe_int(live_summary.get("active_agents"))
        or _safe_int(work_session_summary.get("active_employees"))
    )
    active_developers = _safe_int(usage_summary.get("active_developers")) or _safe_int(live_summary.get("active_developers"))
    active_entries = _safe_int(live_summary.get("active_entries"))
    query_scope_events = _safe_int(usage_summary.get("query_scope_events"))
    query_tool_calls = _safe_int(usage_summary.get("query_tool_calls"))

    avg_daily_events = round(total_events / max(active_days, 1), 1) if active_days else 0.0

    top_tool = (usage.get("top_tools") or [{}])[0]
    top_developer = (usage.get("top_developers") or [{}])[0]
    top_agent = (usage.get("top_employees") or live_activity.get("top_agents") or work_sessions.get("top_employees") or [{}])[0]
    top_scope = (usage.get("top_scopes") or [{}])[0]
    top_project = (usage.get("top_projects") or work_sessions.get("top_projects") or live_activity.get("top_projects") or [{}])[0]

    alerts: list[dict] = []
    if total_events <= 0:
        alerts.append(
            {
                "tone": "critical",
                "title": "近窗口内没有 MCP 交互记录",
                "description": "统计页无法给出趋势判断，因为 usage_records 在当前窗口内为空。",
            }
        )
    elif days >= 7 and active_days <= 1:
        alerts.append(
            {
                "tone": "warning",
                "title": "活跃天数偏少",
                "description": f"近 {days} 天只有 {active_days} 天存在交互，趋势判断容易失真。",
            }
        )
    if tool_calls > 0 and finalized_tool_calls <= 0:
        alerts.append(
            {
                "tone": "warning",
                "title": "工具完成态仍不完整",
                "description": "当前窗口内已经有工具调用，但完成态样本仍不足，成功率与时延会继续随新数据收敛。",
            }
        )
    if connections <= 0:
        alerts.append(
            {
                "tone": "warning",
                "title": "只有工具调用，没有连接事件",
                "description": "说明当前统计更像调用日志，而不是完整接入漏斗。",
            }
        )
    if active_agents <= 0:
        if query_scope_events > 0:
            alerts.append(
                {
                    "tone": "warning",
                    "title": "当前还没有归因到真实 AI 员工",
                    "description": "当前窗口内已经有 mcp:query 入口流量，但 usage 主链还没有稳定归因到 emp-* 级别。",
                }
            )
        else:
            alerts.append(
                {
                    "tone": "warning",
                    "title": "当前没有真实 AI 员工调用",
                    "description": "已排除 mcp:query 这类系统作用域后，当前窗口内没有命中真实 AI 员工调用记录。",
                }
            )
    if total_events > 0 and active_projects <= 0:
        alerts.append(
            {
                "tone": "warning",
                "title": "项目归因仍然偏弱",
                "description": "当前窗口内已有调用记录，但 project_id 尚未稳定落到 usage 主链。",
            }
        )
    if active_entries <= 0:
        alerts.append(
            {
                "tone": "neutral",
                "title": "当前没有在线 MCP 入口",
                "description": "实时状态为空时，只能依赖历史记录看趋势，无法确认现在是否仍有入口在线。",
            }
        )

    health_score = 100
    if total_events <= 0:
        health_score -= 45
    elif days >= 7 and active_days <= 1:
        health_score -= 12
    if tool_calls > 0 and finalized_tool_calls <= 0:
        health_score -= 10
    if connections <= 0:
        health_score -= 15
    if active_agents <= 0:
        health_score -= 20
    if total_events > 0 and active_projects <= 0:
        health_score -= 10
    if active_entries <= 0:
        health_score -= 10
    health_score = max(12, min(100, health_score))

    blind_spots = []
    if (
        _safe_int(usage_summary.get("total_tokens")) <= 0
        and _safe_int(usage_summary.get("active_providers")) <= 0
        and _safe_int(usage_summary.get("active_models")) <= 0
    ):
        blind_spots.append(
            {
                "key": "token-cost",
                "title": "token / 成本 采集仍待补齐",
                "description": "usage 主链已补工具状态、项目归因与时延，但模型 token、费用、provider、model_name 还没有稳定来源。",
            }
        )
    if _safe_int(usage_summary.get("total_tokens")) > 0 and _safe_float(usage_summary.get("total_cost_usd")) <= 0:
        blind_spots.append(
            {
                "key": "cost-coverage",
                "title": "token 已有，但成本仍未覆盖",
                "description": "当前已经记录到 token 消耗，但还没有把成本稳定换算到 usage 主链。",
            }
        )
    if _safe_int(usage_summary.get("model_calls")) > 0 and _safe_int(usage_summary.get("active_prompt_versions")) <= 0:
        blind_spots.append(
            {
                "key": "prompt-version",
                "title": "Prompt 版本还没有稳定落盘",
                "description": "模型调用已经开始可见，但 prompt_version 仍为空，无法做回归或 A/B 分析。",
            }
        )
    if tool_calls > 0 and finalized_tool_calls <= 0:
        blind_spots.append(
            {
                "key": "success-rate",
                "title": "工具完成态仍在补样本",
                "description": "新链路已经记录 success / failed / timeout，但当前窗口内完成态数据还不够多。",
            }
        )
    if total_events > 0 and active_projects <= 0:
        blind_spots.append(
            {
                "key": "business-outcome",
                "title": "业务归因仍不完整",
                "description": "部分历史记录还没有 project_id / chat_session_id，项目活跃度仍会回退到工作会话与在线入口。",
            }
        )
    if query_scope_events > 0 and active_agents <= 0:
        blind_spots.append(
            {
                "key": "agent-attribution",
                "title": "Query 到真实员工的归因仍不完整",
                "description": "当前已经能看到 mcp:query 主入口流量，但还没有把足够多的调用稳定归因到 emp-* 级别。",
            }
        )
    if tool_calls > 0 and avg_tool_duration_ms <= 0:
        blind_spots.append(
            {
                "key": "latency",
                "title": "调用时延样本还不稳定",
                "description": "新链路已经开始记录单次工具时延，但当前窗口内还没有形成可靠平均值。",
            }
        )

    highlights = [
        {
            "label": "最高频工具",
            "value": _normalize_text(top_tool.get("tool_name", "") or "暂无数据", 80),
            "meta": (
                f"{_safe_int(top_tool.get('cnt'))} 次调用"
                if _safe_int(top_tool.get("cnt")) <= 0 or _safe_float(top_tool.get("success_rate")) <= 0
                else f"{_safe_int(top_tool.get('cnt'))} 次调用 · 成功率 {_safe_float(top_tool.get('success_rate')):.1f}%"
            ),
            "tone": "warm",
        },
        {
            "label": "最活跃入口",
            "value": _normalize_text(top_scope.get("scope_label", "") or top_scope.get("scope_id", "") or "暂无数据", 80),
            "meta": (
                f"{_safe_int(top_scope.get('cnt'))} 次入口事件"
                if _safe_int(top_scope.get("tool_calls")) <= 0
                else f"{_safe_int(top_scope.get('cnt'))} 次入口事件 · 工具 {_safe_int(top_scope.get('tool_calls'))}"
            ),
            "tone": "neutral",
        },
        {
            "label": "最活跃智能体",
            "value": _normalize_text(
                top_agent.get("employee_name", "") or top_agent.get("label", "") or top_agent.get("employee_id", "") or "暂无数据",
                80,
            ),
            "meta": f"{_safe_int(top_agent.get('cnt') or top_agent.get('active_entries'))} 次 AI 员工调用",
            "tone": "cool",
        },
        {
            "label": "最活跃项目",
            "value": _normalize_text(
                top_project.get("project_name", "") or top_project.get("project_id", "") or "暂无数据",
                80,
            ),
            "meta": (
                f"{_safe_int(top_project.get('cnt') or top_project.get('session_count') or top_project.get('active_entries'))} 条归因记录"
                if _safe_float(top_project.get("avg_duration_ms")) <= 0
                else f"{_safe_int(top_project.get('cnt') or top_project.get('session_count') or top_project.get('active_entries'))} 条归因记录 · 平均 {round(_safe_float(top_project.get('avg_duration_ms')))}ms"
            ),
            "tone": "neutral",
        },
        {
            "label": "最活跃开发者",
            "value": _normalize_text(top_developer.get("developer_name", "") or "暂无数据", 80),
            "meta": f"{_safe_int(top_developer.get('cnt'))} 次交互",
            "tone": "neutral",
        },
    ]

    flow = [
        {
            "label": "工具调用占比",
            "value": _format_percentage(tool_calls, total_events),
            "meta": f"{tool_calls} / {total_events} 事件",
        },
        {
            "label": "工具成功率",
            "value": f"{tool_success_rate:.0f}%",
            "meta": f"{successful_tool_calls} 成功 / {failed_tool_calls + timeout_tool_calls} 异常",
        },
        {
            "label": "平均工具时延",
            "value": f"{round(avg_tool_duration_ms)}ms" if avg_tool_duration_ms > 0 else "暂无",
            "meta": f"{finalized_tool_calls} 条完成态样本",
        },
        {
            "label": "活跃智能体",
            "value": str(active_agents),
            "meta": "只统计真实 AI 员工 ID",
        },
        {
            "label": "Query 入口",
            "value": str(query_scope_events),
            "meta": f"工具 {query_tool_calls} · 通过 `mcp:query` 进入",
        },
        {
            "label": "活跃项目",
            "value": str(active_projects),
            "meta": f"在线入口 {active_entries} · 日均交互 {avg_daily_events:.1f}",
        },
    ]

    return (
        {
            "health_score": health_score,
            "alerts": alerts,
            "highlights": highlights,
            "flow": flow,
        },
        blind_spots,
    )


def _build_statistics_ai_report(
    *,
    generated_at: str,
    days: int,
    viewer: dict,
    usage: dict,
    work_sessions: dict,
    live_activity: dict,
    runtime_metrics: dict,
    insights: dict,
    blind_spots: list[dict],
    scope: dict,
) -> dict:
    usage_summary = usage.get("summary") or {}
    work_summary = work_sessions.get("summary") or {}
    live_summary = live_activity.get("summary") or {}
    tool_health = usage.get("tool_health") or {}
    top_tool = (usage.get("top_tools") or [{}])[0]
    top_scope = (usage.get("top_scopes") or [{}])[0]
    top_agent = (usage.get("top_employees") or live_activity.get("top_agents") or work_sessions.get("top_employees") or [{}])[0]
    top_project = (usage.get("top_projects") or work_sessions.get("top_projects") or live_activity.get("top_projects") or [{}])[0]

    total_events = _safe_int(usage_summary.get("total_events"))
    tool_calls = _safe_int(usage_summary.get("tool_calls"))
    query_scope_events = _safe_int(usage_summary.get("query_scope_events"))
    active_agents = (
        _safe_int(usage_summary.get("active_employees"))
        or _safe_int(live_summary.get("active_agents"))
        or _safe_int(work_summary.get("active_employees"))
    )
    active_projects = (
        _safe_int(usage_summary.get("active_projects"))
        or _safe_int(live_summary.get("active_projects"))
        or _safe_int(work_summary.get("active_projects"))
    )
    in_progress_sessions = _safe_int(work_summary.get("in_progress_sessions"))
    completed_sessions = _safe_int(work_summary.get("completed_sessions"))
    blocked_sessions = _safe_int(work_summary.get("blocked_sessions"))
    completion_rate = _safe_float(work_summary.get("completion_rate"))
    finalized_tool_calls = _safe_int(usage_summary.get("finalized_tool_calls") or tool_health.get("finalized_calls"))
    tool_success_rate = _safe_float(usage_summary.get("tool_success_rate") or tool_health.get("success_rate"))
    avg_tool_duration_ms = _safe_float(usage_summary.get("avg_tool_duration_ms") or tool_health.get("avg_duration_ms"))
    health_score = _safe_int(insights.get("health_score"))
    total_tokens = _safe_int(usage_summary.get("total_tokens"))
    total_cost_usd = _safe_float(usage_summary.get("total_cost_usd"))
    model_calls = _safe_int(usage_summary.get("model_calls"))
    active_providers = _safe_int(usage_summary.get("active_providers"))
    active_models = _safe_int(usage_summary.get("active_models"))
    active_prompt_versions = _safe_int(usage_summary.get("active_prompt_versions"))
    top_project_events = _safe_int(top_project.get("cnt") or top_project.get("event_count") or top_project.get("active_entries"))
    project_concentration_percent = _percentage_value(top_project_events, total_events)

    focus_points: list[dict] = []

    def add_focus_point(
        key: str,
        title: str,
        status: str,
        evidence: str,
        recommended_action: str,
        impact: str,
    ) -> None:
        focus_points.append(
            {
                "key": key,
                "title": title,
                "status": status,
                "evidence": evidence,
                "recommended_action": recommended_action,
                "impact": impact,
            }
        )

    if query_scope_events > 0 and active_agents <= 0:
        add_focus_point(
            "agent_attribution",
            "Query 流量还没有稳定归因到真实 AI 员工",
            "warning",
            f"近 {days} 天 Query 入口 {query_scope_events} 次，但真实 AI 员工数为 {active_agents}。",
            "优先补齐 query -> employee_id 的归因链路，并按入口、员工、项目同时落盘。",
            "否则 AI 只能看到入口热度，无法判断哪类智能体最值得继续训练和扩容。",
        )
    if tool_calls > 0 and finalized_tool_calls <= 0:
        add_focus_point(
            "tool_final_state",
            "工具完成态样本不足",
            "warning",
            f"工具调用 {tool_calls} 次，但完成态样本只有 {finalized_tool_calls}。",
            "补齐 success / failed / timeout / cancelled 的统一状态写入，再让 AI 分析失败结构。",
            "没有完成态，AI 无法区分高频工具到底是稳定高产还是高频出错。",
        )
    if blocked_sessions > 0:
        add_focus_point(
            "blocked_sessions",
            "存在阻塞中的工作会话",
            "warning",
            f"当前窗口内阻塞会话 {blocked_sessions} 个，进行中 {in_progress_sessions} 个。",
            "把阻塞原因拆成缺规则、缺数据、缺工具、缺归因四类，沉淀成 AI 可回看的阻塞标签。",
            "这能直接告诉 AI 当前系统升级优先级应该落在流程、能力还是数据链路。",
        )
    if in_progress_sessions > completed_sessions:
        add_focus_point(
            "delivery_closure",
            "会话推进多于完成闭环",
            "neutral",
            f"进行中 {in_progress_sessions} 个，会话完成 {completed_sessions} 个。",
            "加强 verification 写回和完成判定，先把“做了”与“做完了”分开。",
            "AI 需要完成闭环样本，才能学习哪些路径真正产出结果。",
        )
    if total_events > 0 and active_projects > 0:
        top_project_name = _normalize_text(top_project.get("project_name", "") or top_project.get("project_id", ""), 160) or "未标记项目"
        top_project_events = _safe_int(top_project.get("cnt") or top_project.get("event_count") or top_project.get("active_entries"))
        if top_project_events > 0 and total_events > 0 and (top_project_events / max(total_events, 1)) >= 0.5:
            add_focus_point(
                "project_concentration",
                "流量高度集中在少数项目",
                "neutral",
                f"最活跃项目 {top_project_name} 占到当前窗口主要样本（{top_project_events}/{total_events}）。",
                "把项目类型、需求类型和完成结果一起纳入报表，区分“高频项目”与“高价值项目”。",
                "否则 AI 会默认把热度最高的项目当成最重要方向，容易误判资源投入顺序。",
            )
    if tool_success_rate > 0 and tool_success_rate < 85:
        add_focus_point(
            "tool_reliability",
            "高频工具稳定性还不够",
            "warning",
            f"当前工具成功率 {tool_success_rate:.1f}% ，平均时延 {round(avg_tool_duration_ms) if avg_tool_duration_ms > 0 else 0}ms。",
            "先锁定高频失败工具，补参数校验、重试策略和超时可解释性。",
            "AI 可以基于失败率和时延一起判断是能力问题、接口问题还是编排问题。",
        )
    if model_calls > 0 and active_prompt_versions <= 0:
        add_focus_point(
            "prompt_version",
            "模型调用已经可见，但 Prompt 版本还不可追踪",
            "warning",
            f"模型调用 {model_calls} 次，但 prompt_version 记录仍为 {active_prompt_versions}。",
            "给运行时 prompt 增加显式版本号，并和模型调用一起写入 usage_records。",
            "没有 Prompt 版本，AI 无法确认是模型变化还是提示词变化带来的效果波动。",
        )
    if total_tokens > 0 and total_cost_usd <= 0:
        add_focus_point(
            "cost_chain",
            "token 主链已出现，但成本链还没有打通",
            "neutral",
            f"当前已记录 token {total_tokens}，但总成本仍为 {total_cost_usd:.4f} USD。",
            "补 provider 定价或上游 cost_usd 回传，让 ROI 从“消耗规模”升级到“真实成本”。",
            "这会直接决定 AI 能否判断优化动作是在省 token 还是在省钱。",
        )
    if not focus_points:
        add_focus_point(
            "stable_observation",
            "统计主链已具备基础分析条件",
            "good",
            f"健康分 {health_score}，活跃项目 {active_projects}，活跃智能体 {active_agents}。",
            "下一步优先补业务结果指标，例如完成率、返工率和升级工单率。",
            "这能让 AI 从“系统有没有运行”升级到“系统是否持续创造价值”的判断层。",
        )

    top_focus = focus_points[:3]
    capability_layers = [
        {
            "key": "traffic_visibility",
            "title": "流量观测",
            "status": "ready" if total_events > 0 else "missing",
            "evidence": f"MCP 交互 {total_events} 次。",
        },
        {
            "key": "attribution",
            "title": "项目/智能体归因",
            "status": (
                "ready"
                if active_projects > 0 and active_agents > 0
                else "partial"
                if active_projects > 0 or query_scope_events > 0
                else "missing"
            ),
            "evidence": f"活跃项目 {active_projects}，活跃智能体 {active_agents}，Query 入口 {query_scope_events}。",
        },
        {
            "key": "tool_observability",
            "title": "工具稳定性观测",
            "status": (
                "ready"
                if tool_calls > 0 and finalized_tool_calls > 0 and tool_success_rate > 0 and avg_tool_duration_ms > 0
                else "partial"
                if tool_calls > 0
                else "missing"
            ),
            "evidence": f"工具调用 {tool_calls}，完成态 {finalized_tool_calls}，成功率 {tool_success_rate:.1f}%，时延 {round(avg_tool_duration_ms) if avg_tool_duration_ms > 0 else 0}ms。",
        },
        {
            "key": "workflow_closure",
            "title": "工作闭环观测",
            "status": (
                "ready"
                if (completed_sessions + in_progress_sessions + blocked_sessions) > 0
                else "missing"
            ),
            "evidence": f"工作会话 完成 {completed_sessions} / 进行中 {in_progress_sessions} / 阻塞 {blocked_sessions}。",
        },
        {
            "key": "roi_measurement",
            "title": "ROI / 结果度量",
            "status": (
                "ready"
                if total_tokens > 0 and active_providers > 0 and active_models > 0 and total_cost_usd > 0
                else "partial"
                if model_calls > 0 or total_tokens > 0 or active_providers > 0 or active_models > 0
                else "missing"
            ),
            "evidence": (
                f"模型调用 {model_calls}，token {total_tokens}，成本 {round(total_cost_usd, 4)} USD，"
                f"provider {active_providers}，model {active_models}，prompt_version {active_prompt_versions}。"
            ),
        },
    ]
    coverage_score = 0.0
    for item in capability_layers:
        if item["status"] == "ready":
            coverage_score += 1
        elif item["status"] == "partial":
            coverage_score += 0.5
    capability_coverage_percent = round((coverage_score / max(len(capability_layers), 1)) * 100)
    measurement_position = {
        "mode": "roi-measurable" if capability_layers[-1]["status"] == "ready" else "coverage-first",
        "label": (
            "可以开始量化 ROI / 效果提升"
            if capability_layers[-1]["status"] == "ready"
            else "当前更适合评估 AI 工程能力覆盖率"
        ),
        "reason": (
            "成本、模型和结果度量链路已具备，AI 可以进一步尝试估算质量/效率/ROI 变化。"
            if capability_layers[-1]["status"] == "ready"
            else "当前核心缺口仍在成本、Prompt 版本或结果度量层，直接给出“提升了多少 %”会失真。"
        ),
    }
    required_metrics = [
        {"key": "total_tokens", "title": "总 token 消耗", "reason": "量化模型消耗与调用成本。"},
        {"key": "total_cost", "title": "总成本", "reason": "把能力建设和 ROI 联系起来。"},
        {"key": "provider_id", "title": "模型供应商", "reason": "区分不同供应商的成本与稳定性。"},
        {"key": "model_name", "title": "模型名称", "reason": "比较模型切换前后的质量与效率。"},
        {"key": "tool_success_rate", "title": "工具成功率", "reason": "判断高频链路是产出还是噪音。"},
        {"key": "per_tool_latency_ms", "title": "工具级时延", "reason": "定位瓶颈是在模型、工具还是编排。"},
        {"key": "prompt_version", "title": "Prompt 版本", "reason": "支持回归分析、A/B 和可审计。"},
        {"key": "schema_version", "title": "输出 Schema 版本", "reason": "保证输出结构可追踪、可回放。"},
    ]
    recommended_dashboards = [
        {"key": "capability_coverage", "title": "AI 能力覆盖看板", "goal": "看系统已具备哪些工程化能力层。"},
        {"key": "attribution_funnel", "title": "入口到归因漏斗", "goal": "看 Query 流量如何沉淀到员工、项目和任务。"},
        {"key": "tool_reliability", "title": "工具稳定性看板", "goal": "看成功率、失败率、时延与重试结构。"},
        {"key": "delivery_outcome", "title": "交付结果看板", "goal": "看完成率、阻塞率、返工率和升级工单率。"},
        {"key": "roi_observability", "title": "ROI 主链", "goal": "看模型、token、成本和 Prompt 版本是否同时可追踪。"},
    ]
    conclusion = (
        f"当前更适合把 AI 提升理解为“工程能力覆盖率”，而不是直接给出“效果提升了多少 %”。"
        f" 按当前统计主链估算，能力覆盖约 {capability_coverage_percent}% 。"
        f" 其中 ROI / 结果度量仍是主要缺口，补齐成本、模型版本、Prompt 版本和结果指标后，才适合进入 ROI 量化。"
    )
    summary = (
        f"近 {days} 天统计显示：MCP 交互 {total_events} 次，工具调用 {tool_calls} 次，"
        f"真实 AI 员工 {active_agents} 个，项目归因 {active_projects} 个，"
        f"工作会话完成 {completed_sessions} / 进行中 {in_progress_sessions} / 阻塞 {blocked_sessions}，"
        f"模型调用 {model_calls} 次，token {total_tokens}，成本 {round(total_cost_usd, 4)} USD。"
        " 当前报表已经能支撑 AI 判断流量、归因、闭环和稳定性，但仍需补齐完成质量与业务结果信号。"
    )

    suggested_questions = [
        "基于 focus_points，给出未来两周最值得投入的 3 条系统进化方向，并按收益/成本排序。",
        "结合 snapshot 和 top_entities，判断当前系统更该优先补归因链路、工具稳定性，还是交付闭环。",
        "如果只允许新增 3 个统计字段，哪些字段最能提升 AI 对优化方向的判断质量？",
    ]

    snapshot = {
        "health_score": health_score,
        "total_events": total_events,
        "tool_calls": tool_calls,
        "query_scope_events": query_scope_events,
        "active_projects": active_projects,
        "active_agents": active_agents,
        "tool_success_rate": round(tool_success_rate, 1),
        "avg_tool_duration_ms": round(avg_tool_duration_ms) if avg_tool_duration_ms > 0 else 0,
        "model_calls": model_calls,
        "total_tokens": total_tokens,
        "total_cost_usd": round(total_cost_usd, 4),
        "active_providers": active_providers,
        "active_models": active_models,
        "active_prompt_versions": active_prompt_versions,
        "completed_sessions": completed_sessions,
        "in_progress_sessions": in_progress_sessions,
        "blocked_sessions": blocked_sessions,
        "completion_rate": round(completion_rate, 1),
        "project_concentration_percent": round(project_concentration_percent, 1),
        "runtime_counter_total": _safe_int(runtime_metrics.get("counter_total")),
        "runtime_histogram_total": _safe_int(runtime_metrics.get("histogram_total")),
    }
    top_entities = {
        "tool_name": _normalize_text(top_tool.get("tool_name", ""), 120),
        "scope_label": _normalize_text(top_scope.get("scope_label", "") or top_scope.get("scope_id", ""), 160),
        "project_name": _normalize_text(top_project.get("project_name", "") or top_project.get("project_id", ""), 160),
        "employee_name": _normalize_text(
            top_agent.get("employee_name", "") or top_agent.get("label", "") or top_agent.get("employee_id", ""),
            160,
        ),
    }
    structured_payload = {
        "scope": scope,
        "generated_at": generated_at,
        "window_days": days,
        "analysis_mode": measurement_position,
        "executive_summary": summary,
        "final_conclusion": conclusion,
        "key_metrics": snapshot,
        "entity_leaders": top_entities,
        "priority_focus": focus_points,
        "blind_spots": blind_spots,
        "must_track_metrics": required_metrics,
        "dashboard_recommendations": recommended_dashboards,
        "next_questions": suggested_questions,
    }

    markdown_lines = [
        "# AI 统计报表",
        f"- 生成时间：{generated_at}",
        f"- 统计窗口：近 {days} 天",
        f"- 统计范围：{_normalize_text(scope.get('display_name', ''), 160) or '全局统计'}",
        f"- 查看人：{_normalize_text(viewer.get('username', ''), 80) or '-'}",
        "",
        "## 执行摘要",
        summary,
        "",
        "## 结论",
        conclusion,
        "",
        "## 判断口径",
        f"- 当前判断模式：{measurement_position['label']}",
        f"- 原因：{measurement_position['reason']}",
        f"- 能力覆盖率：约 {capability_coverage_percent}%",
        "",
        "## 核心快照",
        f"- 健康分：{health_score}",
        f"- MCP 交互：{total_events}",
        f"- 工具调用：{tool_calls}",
        f"- 工具成功率：{tool_success_rate:.1f}%",
        f"- 平均工具时延：{round(avg_tool_duration_ms)}ms" if avg_tool_duration_ms > 0 else "- 平均工具时延：暂无稳定样本",
        f"- 活跃项目：{active_projects}",
        f"- 活跃智能体：{active_agents}",
        f"- 工作会话：完成 {completed_sessions} / 进行中 {in_progress_sessions} / 阻塞 {blocked_sessions}",
        f"- 工作完成率：{completion_rate:.1f}%",
        f"- 项目集中度：{project_concentration_percent:.1f}%",
        "",
        "## Top 实体",
        f"- 高频工具：{_normalize_text(top_tool.get('tool_name', ''), 120) or '暂无数据'}",
        f"- 主入口：{_normalize_text(top_scope.get('scope_label', '') or top_scope.get('scope_id', ''), 160) or '暂无数据'}",
        f"- 主项目：{_normalize_text(top_project.get('project_name', '') or top_project.get('project_id', ''), 160) or '暂无数据'}",
        f"- 主智能体：{_normalize_text(top_agent.get('employee_name', '') or top_agent.get('label', '') or top_agent.get('employee_id', ''), 160) or '暂无数据'}",
        "",
        "## AI 应重点关注",
    ]
    for item in top_focus:
        markdown_lines.extend(
            [
                f"- {item['title']} [{item['status']}]",
                f"  证据：{item['evidence']}",
                f"  建议：{item['recommended_action']}",
                f"  价值：{item['impact']}",
            ]
        )
    if blind_spots:
        markdown_lines.extend(["", "## 当前统计盲区"])
        for item in blind_spots[:4]:
            markdown_lines.append(f"- {item.get('title', '未命名盲区')}：{_normalize_text(item.get('description', ''), 240)}")
    markdown_lines.extend(["", "## 必须补的统计字段"])
    for item in required_metrics:
        markdown_lines.append(f"- {item['title']}（{item['key']}）：{item['reason']}")
    markdown_lines.extend(["", "## 推荐看板"])
    for item in recommended_dashboards:
        markdown_lines.append(f"- {item['title']}：{item['goal']}")
    markdown_lines.extend(["", "## 建议 AI 下一步提问"])
    markdown_lines.extend([f"- {question}" for question in suggested_questions])

    return {
        "version": "statistics-ai-report/v1",
        "generated_at": generated_at,
        "window_days": days,
        "scope": scope,
        "conclusion": conclusion,
        "summary": summary,
        "executive_summary": summary,
        "final_conclusion": conclusion,
        "capability_layers": capability_layers,
        "capability_coverage_percent": capability_coverage_percent,
        "measurement_position": measurement_position,
        "analysis_mode": measurement_position,
        "focus_points": focus_points,
        "priority_focus": focus_points,
        "required_metrics": required_metrics,
        "must_track_metrics": required_metrics,
        "recommended_dashboards": recommended_dashboards,
        "dashboard_recommendations": recommended_dashboards,
        "suggested_questions": suggested_questions,
        "next_questions": suggested_questions,
        "snapshot": snapshot,
        "key_metrics": snapshot,
        "top_entities": top_entities,
        "entity_leaders": top_entities,
        "structured_payload": structured_payload,
        "markdown": "\n".join(markdown_lines),
    }


def _build_live_activity_overview(raw_live_activity: dict, *, project_id: str = "") -> dict:
    normalized_project_id = _normalize_text(project_id, 80)
    endpoint_breakdown: list[dict] = []
    endpoint_counts: dict[str, int] = {}
    project_activity: dict[str, dict] = {}
    agent_activity: dict[str, dict] = {}
    active_developers: set[str] = set()
    active_entries = 0

    for item in raw_live_activity.get("items", []) or []:
        project_id_value = _normalize_text(item.get("project_id", ""), 80)
        if normalized_project_id and project_id_value != normalized_project_id:
            continue
        active_entries += 1
        endpoint_type = _normalize_text(item.get("endpoint_type", ""), 40) or "unknown"
        endpoint_counts[endpoint_type] = endpoint_counts.get(endpoint_type, 0) + 1

        project_name = _resolve_project_name(project_id_value, item.get("project_name", ""))
        developer_name = _normalize_text(item.get("developer_name", ""), 160)
        latest_seen_at = _normalize_text(item.get("last_seen_at", ""), 40)
        if developer_name:
            active_developers.add(developer_name)
        if project_id_value or project_name:
            project_key = project_id_value or project_name
            bucket = project_activity.setdefault(
                project_key,
                {
                    "project_id": project_id_value,
                    "project_name": project_name or project_id_value or "未标记项目",
                    "active_entries": 0,
                    "developer_count": 0,
                    "endpoint_types": set(),
                    "developers": set(),
                    "latest_seen_at": "",
                },
            )
            bucket["active_entries"] += 1
            bucket["endpoint_types"].add(endpoint_type)
            if developer_name:
                bucket["developers"].add(developer_name)
                bucket["developer_count"] = len(bucket["developers"])
            if latest_seen_at >= bucket["latest_seen_at"]:
                bucket["latest_seen_at"] = latest_seen_at

        if endpoint_type != "employee":
            continue
        employee_id = _normalize_text(item.get("entity_id", ""), 80)
        if not _is_ai_employee_id(employee_id):
            continue
        employee_name = _normalize_text(item.get("entity_name", ""), 120) or _resolve_employee_name(employee_id)
        agent_key = employee_id or employee_name or "unknown-agent"
        agent_bucket = agent_activity.setdefault(
            agent_key,
            {
                "employee_id": employee_id,
                "employee_name": employee_name or employee_id or "未知智能体",
                "active_entries": 0,
                "developer_count": 0,
                "project_count": 0,
                "developers": set(),
                "projects": set(),
                "latest_seen_at": "",
            },
        )
        agent_bucket["active_entries"] += 1
        if developer_name:
            agent_bucket["developers"].add(developer_name)
            agent_bucket["developer_count"] = len(agent_bucket["developers"])
        if project_id_value or project_name:
            agent_bucket["projects"].add(project_id_value or project_name)
            agent_bucket["project_count"] = len(agent_bucket["projects"])
        if latest_seen_at >= agent_bucket["latest_seen_at"]:
            agent_bucket["latest_seen_at"] = latest_seen_at

    for endpoint_type, count in sorted(endpoint_counts.items(), key=lambda pair: (-pair[1], pair[0])):
        endpoint_breakdown.append({"endpoint_type": endpoint_type, "count": count})

    normalized_projects = []
    for row in project_activity.values():
        normalized_projects.append(
            {
                "project_id": row["project_id"],
                "project_name": row["project_name"],
                "active_entries": row["active_entries"],
                "developer_count": row["developer_count"],
                "endpoint_type_count": len(row["endpoint_types"]),
                "latest_seen_at": row["latest_seen_at"],
            }
        )
    normalized_agents = []
    for row in agent_activity.values():
        normalized_agents.append(
            {
                "employee_id": row["employee_id"],
                "employee_name": row["employee_name"],
                "active_entries": row["active_entries"],
                "developer_count": row["developer_count"],
                "project_count": row["project_count"],
                "latest_seen_at": row["latest_seen_at"],
            }
        )

    normalized_projects.sort(
        key=lambda row: (
            _safe_int(row.get("active_entries")),
            _safe_int(row.get("developer_count")),
            _normalize_text(row.get("latest_seen_at", ""), 40),
            _normalize_text(row.get("project_name", ""), 160),
        ),
        reverse=True,
    )
    normalized_agents.sort(
        key=lambda row: (
            _safe_int(row.get("active_entries")),
            _safe_int(row.get("project_count")),
            _normalize_text(row.get("latest_seen_at", ""), 40),
            _normalize_text(row.get("employee_name", ""), 120),
        ),
        reverse=True,
    )

    return {
        "summary": {
            "active_entries": active_entries,
            "active_endpoint_types": len(endpoint_counts),
            "active_projects": len(normalized_projects),
            "active_developers": len(active_developers),
            "active_agents": len(normalized_agents),
        },
        "ttl_seconds": int(raw_live_activity.get("ttl_seconds") or 180),
        "endpoint_breakdown": endpoint_breakdown,
        "top_projects": normalized_projects[:8],
        "top_agents": normalized_agents[:8],
    }


@router.get("/overview")
async def statistics_overview(
    days: int = Query(7, description="统计时间窗口（天）"),
    project_id: str = Query("", description="可选：按项目过滤统计"),
    auth_payload: dict = Depends(_require_statistics_permission),
):
    normalized_days = _coerce_days(days)
    normalized_project_id = _normalize_text(project_id, 80)
    scope = _build_statistics_scope(normalized_project_id)
    generated_at = _now_iso()
    viewer = {
        "username": _normalize_text(auth_payload.get("sub", ""), 80),
        "role": _normalize_text(auth_payload.get("role", ""), 40),
    }
    usage = _decorate_usage_overview(
        usage_store.get_overview(normalized_days, project_id=normalized_project_id)
    )
    work_sessions = _build_work_session_overview(
        days=normalized_days,
        project_id=normalized_project_id,
    )
    runtime_metrics = _build_runtime_metric_overview()
    try:
        live_activity = await list_active_system_mcp_presence()
    except Exception:
        live_activity = {
            "items": [],
            "ttl_seconds": 180,
            "summary": {
                "active_entries": 0,
                "active_endpoint_types": 0,
                "active_projects": 0,
                "active_developers": 0,
            },
        }

    live_overview = _build_live_activity_overview(
        live_activity,
        project_id=normalized_project_id,
    )
    insights, blind_spots = _build_statistics_insights(
        days=normalized_days,
        usage=usage,
        work_sessions=work_sessions,
        live_activity=live_overview,
    )
    ai_report = _build_statistics_ai_report(
        generated_at=generated_at,
        days=normalized_days,
        viewer=viewer,
        usage=usage,
        work_sessions=work_sessions,
        live_activity=live_overview,
        runtime_metrics=runtime_metrics,
        insights=insights,
        blind_spots=blind_spots,
        scope=scope,
    )

    return {
        "generated_at": generated_at,
        "days": normalized_days,
        "project_id": normalized_project_id,
        "project_name": _normalize_text(scope.get("project_name", ""), 160),
        "scope": scope,
        "viewer": viewer,
        "usage": usage,
        "work_sessions": work_sessions,
        "live_activity": live_overview,
        "runtime_metrics": runtime_metrics,
        "insights": insights,
        "blind_spots": blind_spots,
        "ai_report": ai_report,
    }
