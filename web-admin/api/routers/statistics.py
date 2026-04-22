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
    return {
        **usage,
        "top_employees": top_employees,
        "top_scopes": top_scopes,
    }


def _build_work_session_overview(*, days: int, limit: int = 500) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    grouped: dict[str, dict] = {}
    for event in work_session_store.list_events(limit=limit):
        updated_at = _parse_iso_datetime(getattr(event, "updated_at", "") or getattr(event, "created_at", ""))
        if updated_at is not None and updated_at < cutoff:
            continue
        session_id = _normalize_text(getattr(event, "session_id", ""), 80)
        if not session_id:
            continue
        bucket = grouped.setdefault(
            session_id,
            {
                "session_id": session_id,
                "project_id": _normalize_text(getattr(event, "project_id", ""), 80),
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

    project_activity: dict[str, dict] = {}
    employee_activity: dict[str, dict] = {}
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

    return {
        "days": days,
        "summary": summary,
        "recent": sessions[:10],
        "top_projects": sorted(
            project_activity.values(),
            key=lambda row: (
                _safe_int(row.get("event_count")),
                _safe_int(row.get("session_count")),
                _normalize_text(row.get("latest_updated_at", ""), 40),
                _normalize_text(row.get("project_name", ""), 160),
            ),
            reverse=True,
        )[:8],
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
    active_projects = _safe_int(usage_summary.get("active_projects")) or _safe_int(live_summary.get("active_projects"))
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


def _build_live_activity_overview(raw_live_activity: dict) -> dict:
    endpoint_breakdown: list[dict] = []
    endpoint_counts: dict[str, int] = {}
    project_activity: dict[str, dict] = {}
    agent_activity: dict[str, dict] = {}

    for item in raw_live_activity.get("items", []) or []:
        endpoint_type = _normalize_text(item.get("endpoint_type", ""), 40) or "unknown"
        endpoint_counts[endpoint_type] = endpoint_counts.get(endpoint_type, 0) + 1

        project_id = _normalize_text(item.get("project_id", ""), 80)
        project_name = _resolve_project_name(project_id, item.get("project_name", ""))
        developer_name = _normalize_text(item.get("developer_name", ""), 160)
        latest_seen_at = _normalize_text(item.get("last_seen_at", ""), 40)
        if project_id or project_name:
            project_key = project_id or project_name
            bucket = project_activity.setdefault(
                project_key,
                {
                    "project_id": project_id,
                    "project_name": project_name or project_id or "未标记项目",
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
        if project_id or project_name:
            agent_bucket["projects"].add(project_id or project_name)
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
            **(raw_live_activity.get("summary", {}) or {}),
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
    auth_payload: dict = Depends(_require_statistics_permission),
):
    normalized_days = _coerce_days(days)
    usage = _decorate_usage_overview(usage_store.get_overview(normalized_days))
    work_sessions = _build_work_session_overview(days=normalized_days)
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

    live_overview = _build_live_activity_overview(live_activity)
    insights, blind_spots = _build_statistics_insights(
        days=normalized_days,
        usage=usage,
        work_sessions=work_sessions,
        live_activity=live_overview,
    )

    return {
        "generated_at": _now_iso(),
        "days": normalized_days,
        "viewer": {
            "username": _normalize_text(auth_payload.get("sub", ""), 80),
            "role": _normalize_text(auth_payload.get("role", ""), 40),
        },
        "usage": usage,
        "work_sessions": work_sessions,
        "live_activity": live_overview,
        "runtime_metrics": runtime_metrics,
        "insights": insights,
        "blind_spots": blind_spots,
    }
