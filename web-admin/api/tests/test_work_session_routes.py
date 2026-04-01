"""工作轨迹查看路由测试"""

from fastapi.testclient import TestClient


def _build_work_session_api_test_client(tmp_path, monkeypatch, auth_payload):
    from core import config as core_config
    from core.deps import require_auth
    from core.server import create_app
    from stores import factory as store_factory

    monkeypatch.setenv("CORE_STORE_BACKEND", "json")
    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()
    for proxy_name in (
        "role_store",
        "system_config_store",
        "project_store",
        "project_material_store",
        "project_studio_export_store",
        "work_session_store",
    ):
        getattr(store_factory, proxy_name)._instance = None

    app = create_app()
    app.dependency_overrides[require_auth] = lambda: auth_payload
    return TestClient(app), store_factory.work_session_store


def test_work_session_routes_list_and_detail(tmp_path, monkeypatch):
    from stores.json.work_session_store import WorkSessionEvent

    client, work_session_store = _build_work_session_api_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )

    work_session_store.save(
        WorkSessionEvent(
            id=work_session_store.new_id(),
            project_id="proj-1",
            project_name="项目一",
            employee_id="emp-1",
            session_id="sess-1",
            source_kind="work-facts",
            phase="Phase 3",
            step="Step 1",
            status="in_progress",
            goal="补独立工作轨迹存储",
            facts=["已保存工作事实"],
            changed_files=["web-admin/api/services/dynamic_mcp_apps_query.py"],
            verification=["python -m py_compile"],
            next_steps=["追加 verification 事件"],
        )
    )
    work_session_store.save(
        WorkSessionEvent(
            id=work_session_store.new_id(),
            project_id="proj-1",
            project_name="项目一",
            employee_id="emp-1",
            session_id="sess-1",
            source_kind="session-event",
            event_type="verification",
            phase="Phase 3",
            step="Step 2",
            status="completed",
            content="已通过 query_mcp 回归",
            verification=["uv run pytest web-admin/api/tests/test_unit.py -k query_mcp"],
            risks=["仍需真实 API Key 联调"],
        )
    )

    list_response = client.get("/api/work-sessions", params={"project_id": "proj-1"})
    assert list_response.status_code == 200
    items = list_response.json()["items"]
    assert len(items) == 1
    assert items[0]["session_id"] == "sess-1"
    assert items[0]["latest_status"] == "completed"
    assert items[0]["phases"] == ["Phase 3"]
    assert "web-admin/api/services/dynamic_mcp_apps_query.py" in items[0]["changed_files"]

    detail_response = client.get("/api/work-sessions/sess-1", params={"project_id": "proj-1"})
    assert detail_response.status_code == 200
    payload = detail_response.json()
    assert payload["session"]["session_id"] == "sess-1"
    assert payload["session"]["event_count"] == 2
    assert payload["items"][0]["event_type"] == "verification"
    assert payload["items"][1]["facts"] == ["已保存工作事实"]


def test_work_session_routes_support_keyword_filter(tmp_path, monkeypatch):
    from stores.json.work_session_store import WorkSessionEvent

    client, work_session_store = _build_work_session_api_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )

    work_session_store.save(
        WorkSessionEvent(
            id=work_session_store.new_id(),
            project_id="proj-1",
            project_name="项目一",
            employee_id="emp-1",
            session_id="sess-alpha",
            source_kind="session-event",
            event_type="verification",
            phase="Phase 3",
            step="Step 2",
            status="completed",
            content="完成 query MCP 回归",
        )
    )
    work_session_store.save(
        WorkSessionEvent(
            id=work_session_store.new_id(),
            project_id="proj-2",
            project_name="项目二",
            employee_id="emp-2",
            session_id="sess-beta",
            source_kind="session-event",
            event_type="notes",
            phase="Phase 4",
            step="Step 1",
            status="in_progress",
            content="准备前端管理页",
        )
    )

    filtered_response = client.get("/api/work-sessions", params={"query": "前端管理页"})
    assert filtered_response.status_code == 200
    items = filtered_response.json()["items"]
    assert len(items) == 1
    assert items[0]["session_id"] == "sess-beta"


def test_work_session_routes_meta_returns_all_projects_and_employees(tmp_path, monkeypatch):
    from stores.json.employee_store import EmployeeConfig
    from stores.json.project_store import ProjectConfig

    client, _ = _build_work_session_api_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )

    from core.deps import employee_store, project_store

    project_store.save(ProjectConfig(id="proj-2", name="项目二"))
    project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    employee_store.save(EmployeeConfig(id="emp-2", name="员工二"))
    employee_store.save(EmployeeConfig(id="emp-1", name="员工一"))

    response = client.get("/api/work-sessions/meta")
    assert response.status_code == 200
    payload = response.json()
    assert payload["projects"] == [
        {"id": "proj-1", "name": "项目一"},
        {"id": "proj-2", "name": "项目二"},
    ]
    assert payload["employees"] == [
        {"id": "emp-1", "name": "员工一"},
        {"id": "emp-2", "name": "员工二"},
    ]
