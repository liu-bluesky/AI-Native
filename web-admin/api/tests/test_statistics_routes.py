"""统计路由测试"""

from fastapi.testclient import TestClient


def _build_statistics_test_client(tmp_path, monkeypatch, auth_payload):
    from core import config as core_config
    from core.deps import require_auth
    from core.server import create_app
    from stores import factory as store_factory

    monkeypatch.setenv("CORE_STORE_BACKEND", "json")
    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()
    for proxy_name in ("role_store", "bot_connector_store", "system_config_store", "user_store"):
        getattr(store_factory, proxy_name)._instance = None

    app = create_app()
    app.dependency_overrides[require_auth] = lambda: auth_payload
    return TestClient(app)


def test_statistics_overview_returns_aggregated_payload(tmp_path, monkeypatch):
    from routers import statistics as statistics_router

    client = _build_statistics_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "admin", "role": "admin"},
    )

    class _FakeUsageStore:
        def get_overview(self, days, project_id=""):
            return {
                "days": days,
                "summary": {
                    "total_events": 12,
                    "tool_calls": 10,
                    "connections": 2,
                    "model_calls": 3,
                    "active_developers": 3,
                    "active_employees": 1,
                    "active_tools": 4,
                    "active_scopes": 3,
                    "query_scope_events": 11,
                    "query_tool_calls": 9,
                    "total_tokens": 88,
                    "total_cost_usd": 1.2345,
                    "active_providers": 1,
                    "active_models": 2,
                    "active_prompt_versions": 1,
                    "prompt_version_records": 3,
                },
                "daily": [
                    {"date": "2026-04-21", "total_events": 5, "tool_calls": 4, "connections": 1},
                    {"date": "2026-04-22", "total_events": 7, "tool_calls": 6, "connections": 1},
                ],
                "top_tools": [{"tool_name": "bind_project_context", "cnt": 5}],
                "top_employees": [
                    {"employee_id": "mcp:query", "cnt": 11},
                    {"employee_id": "emp-1", "cnt": 7},
                ],
                "top_scopes": [
                    {"scope_id": "mcp:query", "cnt": 11, "tool_calls": 9, "attributed_employee_count": 1, "project_count": 1},
                    {"scope_id": "employee:emp-1", "cnt": 7, "tool_calls": 7, "attributed_employee_count": 1, "project_count": 1},
                ],
                "top_developers": [{"developer_name": "admin", "cnt": 12}],
                "top_providers": [{"provider_id": "openai", "cnt": 3, "total_tokens": 88, "total_cost_usd": 1.2345}],
                "top_models": [{"model_name": "gpt-4.1", "cnt": 2, "total_tokens": 64, "total_cost_usd": 0.9876}],
                "top_prompt_versions": [{"prompt_version": "planner-v2", "cnt": 3}],
                "top_projects": [{"project_id": "proj-1", "project_name": "", "cnt": 11, "avg_duration_ms": 53}],
                "recent": [],
            }

    class _FakeEvent:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class _FakeWorkSessionStore:
        def list_events(self, limit=500):
            return [
                _FakeEvent(
                    session_id="ws-1",
                    project_id="proj-1",
                    project_name="项目 A",
                    employee_id="emp-1",
                    phase="analysis",
                    step="梳理",
                    status="in_progress",
                    verification=["已进入分析"],
                    updated_at="2026-04-22T00:00:00+00:00",
                    created_at="2026-04-22T00:00:00+00:00",
                ),
                _FakeEvent(
                    session_id="ws-2",
                    project_id="proj-1",
                    project_name="项目 A",
                    employee_id="emp-2",
                    phase="verification",
                    step="验收",
                    status="completed",
                    verification=["已完成"],
                    updated_at="2026-04-22T00:10:00+00:00",
                    created_at="2026-04-22T00:10:00+00:00",
                ),
            ]

    class _FakeEmployeeStore:
        def get(self, employee_id):
            names = {
                "emp-1": "智能体 A",
                "emp-2": "智能体 B",
            }
            name = names.get(employee_id)
            if not name:
                return None
            return type("Employee", (), {"name": name})()

    class _FakeProjectStore:
        def get(self, project_id):
            names = {
                "proj-1": "项目 A",
            }
            name = names.get(project_id)
            if not name:
                return None
            return type("Project", (), {"name": name})()

    async def _fake_live_activity():
        return {
            "items": [
                {
                    "endpoint_type": "employee",
                    "entity_id": "emp-1",
                    "entity_name": "智能体 A",
                    "project_id": "proj-1",
                    "project_name": "项目 A",
                    "developer_name": "admin",
                    "last_seen_at": "2026-04-22T00:15:00+00:00",
                },
                {
                    "endpoint_type": "query",
                    "entity_id": "query-center",
                    "entity_name": "统一查询 MCP",
                    "project_id": "proj-1",
                    "project_name": "项目 A",
                    "developer_name": "admin",
                    "last_seen_at": "2026-04-22T00:16:00+00:00",
                },
                {
                    "endpoint_type": "project",
                    "entity_id": "proj-1",
                    "entity_name": "项目 A",
                    "project_id": "proj-1",
                    "project_name": "项目 A",
                    "developer_name": "admin",
                    "last_seen_at": "2026-04-22T00:17:00+00:00",
                },
            ],
            "ttl_seconds": 180,
            "summary": {
                "active_entries": 3,
                "active_endpoint_types": 3,
                "active_projects": 1,
                "active_developers": 1,
            },
        }

    monkeypatch.setattr(statistics_router, "usage_store", _FakeUsageStore())
    monkeypatch.setattr(statistics_router, "work_session_store", _FakeWorkSessionStore())
    monkeypatch.setattr(statistics_router, "employee_store", _FakeEmployeeStore())
    monkeypatch.setattr(statistics_router, "project_store", _FakeProjectStore())
    monkeypatch.setattr(statistics_router, "list_active_system_mcp_presence", _fake_live_activity)
    monkeypatch.setattr(
        statistics_router.metrics,
        "get_stats",
        lambda: {
            "counters": {"conversation_completed": 8},
            "histograms": {"conversation_duration": {"count": 2, "avg": 120.5, "min": 100.0, "max": 141.0}},
        },
    )

    response = client.get("/api/statistics/overview", params={"days": 7})
    assert response.status_code == 200
    payload = response.json()

    assert payload["days"] == 7
    assert payload["project_name"] == ""
    assert payload["scope"]["scope_type"] == "global"
    assert payload["usage"]["summary"]["tool_calls"] == 10
    assert payload["usage"]["summary"]["model_calls"] == 3
    assert payload["usage"]["summary"]["total_cost_usd"] == 1.2345
    assert payload["usage"]["summary"]["active_prompt_versions"] == 1
    assert payload["work_sessions"]["summary"]["total_sessions"] == 2
    assert payload["work_sessions"]["summary"]["completed_sessions"] == 1
    assert payload["work_sessions"]["summary"]["completion_rate"] == 50.0
    assert payload["work_sessions"]["summary"]["closure_gap_sessions"] == 0
    assert payload["work_sessions"]["summary"]["active_employees"] == 2
    assert any(item["completion_rate"] == 50.0 for item in payload["work_sessions"]["daily"])
    assert payload["work_sessions"]["top_projects"][0]["project_name"] == "项目 A"
    assert payload["work_sessions"]["top_projects"][0]["completion_rate"] == 50.0
    assert payload["work_sessions"]["top_employees"][0]["employee_name"] == "智能体 B"
    assert payload["live_activity"]["summary"]["active_entries"] == 3
    assert payload["live_activity"]["endpoint_breakdown"] == [
        {"endpoint_type": "employee", "count": 1},
        {"endpoint_type": "project", "count": 1},
        {"endpoint_type": "query", "count": 1},
    ]
    assert payload["live_activity"]["top_agents"][0]["employee_name"] == "智能体 A"
    assert payload["live_activity"]["summary"]["active_agents"] == 1
    assert payload["usage"]["top_employees"][0]["employee_name"] == "智能体 A"
    assert all(item["employee_id"] != "mcp:query" for item in payload["usage"]["top_employees"])
    assert payload["usage"]["top_scopes"][0]["scope_id"] == "mcp:query"
    assert payload["usage"]["top_scopes"][0]["scope_label"] == "统一查询 MCP"
    assert payload["usage"]["top_providers"][0]["provider_id"] == "openai"
    assert payload["usage"]["top_models"][0]["model_name"] == "gpt-4.1"
    assert payload["usage"]["top_prompt_versions"][0]["prompt_version"] == "planner-v2"
    assert payload["usage"]["top_projects"][0]["project_name"] == "项目 A"
    assert payload["runtime_metrics"]["counter_total"] == 1
    assert payload["insights"]["health_score"] > 0
    assert len(payload["insights"]["highlights"]) == 5
    assert payload["insights"]["highlights"][1]["value"] == "统一查询 MCP"
    assert payload["insights"]["highlights"][3]["value"] == "项目 A"
    assert payload["ai_report"]["version"] == "statistics-ai-report/v1"
    assert payload["ai_report"]["scope"]["display_name"] == "全局统计"
    assert payload["ai_report"]["top_entities"]["project_name"] == "项目 A"
    assert payload["ai_report"]["entity_leaders"]["project_name"] == "项目 A"
    assert payload["ai_report"]["measurement_position"]["mode"] == "roi-measurable"
    assert payload["ai_report"]["analysis_mode"]["mode"] == "roi-measurable"
    assert payload["ai_report"]["capability_coverage_percent"] > 0
    assert payload["ai_report"]["snapshot"]["completion_rate"] == 50.0
    assert payload["ai_report"]["key_metrics"]["completion_rate"] == 50.0
    assert payload["ai_report"]["snapshot"]["model_calls"] == 3
    assert payload["ai_report"]["snapshot"]["total_cost_usd"] == 1.2345
    assert len(payload["ai_report"]["required_metrics"]) == 8
    assert len(payload["ai_report"]["must_track_metrics"]) == 8
    assert len(payload["ai_report"]["recommended_dashboards"]) == 5
    assert len(payload["ai_report"]["dashboard_recommendations"]) == 5
    assert payload["ai_report"]["structured_payload"]["scope"]["display_name"] == "全局统计"
    assert payload["ai_report"]["structured_payload"]["entity_leaders"]["project_name"] == "项目 A"
    assert "AI 统计报表" in payload["ai_report"]["markdown"]
    assert "项目 A" in payload["ai_report"]["markdown"]
    flow_map = {item["label"]: item["value"] for item in payload["insights"]["flow"]}
    assert flow_map["Query 入口"] == "11"
    assert all(item["key"] != "token-cost" for item in payload["blind_spots"])


def test_statistics_overview_uses_work_sessions_for_agent_activity_when_usage_and_live_are_empty(tmp_path, monkeypatch):
    from routers import statistics as statistics_router

    client = _build_statistics_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "admin", "role": "admin"},
    )

    class _FakeUsageStore:
        def get_overview(self, days, project_id=""):
            return {
                "days": days,
                "summary": {
                    "total_events": 4,
                    "tool_calls": 4,
                    "connections": 0,
                    "active_developers": 1,
                    "active_employees": 0,
                    "active_tools": 2,
                    "active_scopes": 1,
                    "query_scope_events": 4,
                    "query_tool_calls": 4,
                },
                "daily": [{"date": "2026-04-22", "total_events": 4, "tool_calls": 4, "connections": 0}],
                "top_tools": [{"tool_name": "bind_project_context", "cnt": 4}],
                "top_employees": [],
                "top_scopes": [{"scope_id": "mcp:query", "cnt": 4, "tool_calls": 4, "attributed_employee_count": 0, "project_count": 1}],
                "top_developers": [{"developer_name": "admin", "cnt": 4}],
                "recent": [],
            }

    class _FakeEvent:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class _FakeWorkSessionStore:
        def list_events(self, limit=500):
            return [
                _FakeEvent(
                    session_id="ws-1",
                    project_id="proj-1",
                    project_name="项目 A",
                    employee_id="emp-1",
                    phase="analysis",
                    step="梳理",
                    status="in_progress",
                    verification=["已进入分析"],
                    updated_at="2026-04-22T00:00:00+00:00",
                    created_at="2026-04-22T00:00:00+00:00",
                ),
                _FakeEvent(
                    session_id="ws-1",
                    project_id="proj-1",
                    project_name="项目 A",
                    employee_id="emp-1",
                    phase="implementation",
                    step="修复",
                    status="in_progress",
                    verification=["已进入实现"],
                    updated_at="2026-04-22T00:05:00+00:00",
                    created_at="2026-04-22T00:05:00+00:00",
                ),
            ]

    class _FakeEmployeeStore:
        def get(self, employee_id):
            if employee_id != "emp-1":
                return None
            return type("Employee", (), {"name": "智能体 A"})()

    class _FakeProjectStore:
        def get(self, project_id):
            if project_id != "proj-1":
                return None
            return type("Project", (), {"name": "项目 A"})()

    async def _fake_live_activity():
        return {
            "items": [
                {
                    "endpoint_type": "query",
                    "entity_id": "query-center",
                    "entity_name": "统一查询 MCP",
                    "project_id": "proj-1",
                    "project_name": "项目 A",
                    "developer_name": "admin",
                    "last_seen_at": "2026-04-22T00:16:00+00:00",
                }
            ],
            "ttl_seconds": 180,
            "summary": {
                "active_entries": 1,
                "active_endpoint_types": 1,
                "active_projects": 1,
                "active_developers": 1,
            },
        }

    monkeypatch.setattr(statistics_router, "usage_store", _FakeUsageStore())
    monkeypatch.setattr(statistics_router, "work_session_store", _FakeWorkSessionStore())
    monkeypatch.setattr(statistics_router, "employee_store", _FakeEmployeeStore())
    monkeypatch.setattr(statistics_router, "project_store", _FakeProjectStore())
    monkeypatch.setattr(statistics_router, "list_active_system_mcp_presence", _fake_live_activity)
    monkeypatch.setattr(
        statistics_router.metrics,
        "get_stats",
        lambda: {"counters": {}, "histograms": {}},
    )

    response = client.get("/api/statistics/overview", params={"days": 7})
    assert response.status_code == 200
    payload = response.json()

    assert payload["work_sessions"]["summary"]["active_employees"] == 1
    assert payload["work_sessions"]["summary"]["completion_rate"] == 0.0
    assert payload["work_sessions"]["top_employees"] == [
        {
            "employee_id": "emp-1",
            "employee_name": "智能体 A",
            "session_count": 1,
            "event_count": 2,
            "project_count": 1,
            "latest_updated_at": "2026-04-22T00:05:00+00:00",
        }
    ]
    flow_map = {item["label"]: item["value"] for item in payload["insights"]["flow"]}
    assert flow_map["活跃智能体"] == "1"
    assert flow_map["Query 入口"] == "4"
    highlight_map = {item["label"]: item["value"] for item in payload["insights"]["highlights"]}
    assert highlight_map["最活跃入口"] == "统一查询 MCP"
    assert highlight_map["最活跃智能体"] == "智能体 A"
    assert payload["ai_report"]["snapshot"]["active_agents"] == 1
    assert payload["ai_report"]["snapshot"]["completion_rate"] == 0.0
    assert payload["ai_report"]["focus_points"]
    assert payload["ai_report"]["priority_focus"]
    assert payload["ai_report"]["suggested_questions"]
    assert payload["ai_report"]["next_questions"]
    assert payload["ai_report"]["measurement_position"]["mode"] == "coverage-first"


def test_statistics_overview_accepts_project_scope(tmp_path, monkeypatch):
    from routers import statistics as statistics_router

    client = _build_statistics_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "admin", "role": "admin"},
    )
    captured = {"project_id": ""}

    class _FakeUsageStore:
        def get_overview(self, days, project_id=""):
            captured["project_id"] = project_id
            return {
                "days": days,
                "summary": {
                    "total_events": 6,
                    "tool_calls": 4,
                    "connections": 2,
                    "active_developers": 1,
                    "active_employees": 1,
                    "active_tools": 2,
                    "active_projects": 1 if project_id else 2,
                    "active_scopes": 2,
                    "query_scope_events": 3,
                    "query_tool_calls": 2,
                },
                "daily": [{"date": "2026-04-22", "total_events": 6, "tool_calls": 4, "connections": 2}],
                "top_tools": [{"tool_name": "bind_project_context", "cnt": 4}],
                "top_employees": [{"employee_id": "emp-1", "employee_name": "智能体 A", "cnt": 4}],
                "top_scopes": [{"scope_id": "mcp:query", "cnt": 3, "tool_calls": 2, "attributed_employee_count": 1, "project_count": 1}],
                "top_developers": [{"developer_name": "admin", "cnt": 6}],
                "top_projects": [{"project_id": "proj-1", "project_name": "项目 A", "cnt": 6, "avg_duration_ms": 45}],
                "recent": [],
            }

    class _FakeEvent:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class _FakeWorkSessionStore:
        def list_events(self, limit=500):
            return [
                _FakeEvent(
                    session_id="ws-1",
                    project_id="proj-1",
                    project_name="项目 A",
                    employee_id="emp-1",
                    phase="analysis",
                    step="梳理",
                    status="in_progress",
                    verification=["已进入分析"],
                    updated_at="2026-04-22T00:00:00+00:00",
                    created_at="2026-04-22T00:00:00+00:00",
                ),
                _FakeEvent(
                    session_id="ws-2",
                    project_id="proj-2",
                    project_name="项目 B",
                    employee_id="emp-2",
                    phase="verification",
                    step="验收",
                    status="completed",
                    verification=["已完成"],
                    updated_at="2026-04-22T00:10:00+00:00",
                    created_at="2026-04-22T00:10:00+00:00",
                ),
            ]

    class _FakeEmployeeStore:
        def get(self, employee_id):
            names = {
                "emp-1": "智能体 A",
                "emp-2": "智能体 B",
            }
            name = names.get(employee_id)
            if not name:
                return None
            return type("Employee", (), {"name": name})()

    class _FakeProjectStore:
        def get(self, project_id):
            names = {
                "proj-1": "项目 A",
                "proj-2": "项目 B",
            }
            name = names.get(project_id)
            if not name:
                return None
            return type("Project", (), {"name": name})()

    async def _fake_live_activity():
        return {
            "items": [
                {
                    "endpoint_type": "query",
                    "entity_id": "query-center",
                    "entity_name": "统一查询 MCP",
                    "project_id": "proj-1",
                    "project_name": "项目 A",
                    "developer_name": "admin",
                    "last_seen_at": "2026-04-22T00:16:00+00:00",
                },
                {
                    "endpoint_type": "employee",
                    "entity_id": "emp-2",
                    "entity_name": "智能体 B",
                    "project_id": "proj-2",
                    "project_name": "项目 B",
                    "developer_name": "admin",
                    "last_seen_at": "2026-04-22T00:18:00+00:00",
                },
            ],
            "ttl_seconds": 180,
            "summary": {
                "active_entries": 2,
                "active_endpoint_types": 2,
                "active_projects": 2,
                "active_developers": 1,
            },
        }

    monkeypatch.setattr(statistics_router, "usage_store", _FakeUsageStore())
    monkeypatch.setattr(statistics_router, "work_session_store", _FakeWorkSessionStore())
    monkeypatch.setattr(statistics_router, "employee_store", _FakeEmployeeStore())
    monkeypatch.setattr(statistics_router, "project_store", _FakeProjectStore())
    monkeypatch.setattr(statistics_router, "list_active_system_mcp_presence", _fake_live_activity)
    monkeypatch.setattr(
        statistics_router.metrics,
        "get_stats",
        lambda: {"counters": {}, "histograms": {}},
    )

    response = client.get(
        "/api/statistics/overview",
        params={"days": 7, "project_id": "proj-1"},
    )
    assert response.status_code == 200
    payload = response.json()

    assert captured["project_id"] == "proj-1"
    assert payload["project_id"] == "proj-1"
    assert payload["project_name"] == "项目 A"
    assert payload["scope"]["display_name"] == "项目 A"
    assert payload["work_sessions"]["summary"]["active_projects"] == 1
    assert payload["live_activity"]["summary"]["active_projects"] == 1
    assert payload["live_activity"]["top_projects"] == [
        {
            "project_id": "proj-1",
            "project_name": "项目 A",
            "active_entries": 1,
            "developer_count": 1,
            "endpoint_type_count": 1,
            "latest_seen_at": "2026-04-22T00:16:00+00:00",
        }
    ]
    assert payload["ai_report"]["top_entities"]["project_name"] == "项目 A"
    assert payload["ai_report"]["scope"]["project_name"] == "项目 A"
    assert payload["ai_report"]["structured_payload"]["scope"]["project_name"] == "项目 A"
