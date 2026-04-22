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
    for proxy_name in ("role_store", "system_config_store", "user_store"):
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
        def get_overview(self, days):
            return {
                "days": days,
                "summary": {
                    "total_events": 12,
                    "tool_calls": 10,
                    "connections": 2,
                    "active_developers": 3,
                    "active_employees": 1,
                    "active_tools": 4,
                    "active_scopes": 3,
                    "query_scope_events": 11,
                    "query_tool_calls": 9,
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
    assert payload["usage"]["summary"]["tool_calls"] == 10
    assert payload["work_sessions"]["summary"]["total_sessions"] == 2
    assert payload["work_sessions"]["summary"]["completed_sessions"] == 1
    assert payload["work_sessions"]["summary"]["active_employees"] == 2
    assert payload["work_sessions"]["top_projects"][0]["project_name"] == "项目 A"
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
    assert payload["runtime_metrics"]["counter_total"] == 1
    assert payload["insights"]["health_score"] > 0
    assert len(payload["insights"]["highlights"]) == 5
    assert payload["insights"]["highlights"][1]["value"] == "统一查询 MCP"
    flow_map = {item["label"]: item["value"] for item in payload["insights"]["flow"]}
    assert flow_map["Query 入口"] == "11"
    assert payload["blind_spots"][0]["key"] == "token-cost"


def test_statistics_overview_uses_work_sessions_for_agent_activity_when_usage_and_live_are_empty(tmp_path, monkeypatch):
    from routers import statistics as statistics_router

    client = _build_statistics_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "admin", "role": "admin"},
    )

    class _FakeUsageStore:
        def get_overview(self, days):
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
