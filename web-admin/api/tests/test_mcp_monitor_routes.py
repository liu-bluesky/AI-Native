"""MCP 监控路由测试"""

from fastapi.testclient import TestClient


def _build_mcp_monitor_api_test_client(tmp_path, monkeypatch, auth_payload):
    from core import config as core_config
    from core.deps import require_auth
    from core.server import create_app
    from stores import factory as store_factory

    monkeypatch.setenv("CORE_STORE_BACKEND", "json")
    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()
    for proxy_name in ("role_store", "system_config_store", "external_mcp_store", "user_store"):
        getattr(store_factory, proxy_name)._instance = None

    app = create_app()
    app.dependency_overrides[require_auth] = lambda: auth_payload
    return TestClient(app), store_factory.external_mcp_store


def test_mcp_monitor_routes_list_modules_for_super_admin(tmp_path, monkeypatch):
    from stores.json.external_mcp_store import ExternalMcpModule

    client, external_mcp_store = _build_mcp_monitor_api_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "admin", "role": "admin"},
    )

    external_mcp_store.save(
        ExternalMcpModule(
            id="xmcp-global",
            name="Global MCP",
            endpoint_http="https://example.com/global",
            enabled=True,
        )
    )
    external_mcp_store.save(
        ExternalMcpModule(
            id="xmcp-project",
            name="Project MCP",
            endpoint_sse="https://example.com/project-sse",
            project_id="proj-1",
            enabled=False,
        )
    )

    response = client.get("/api/system/mcp-monitor/modules")
    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"] == {
        "total": 2,
        "enabled_total": 1,
        "disabled_total": 1,
        "global_total": 1,
        "project_total": 1,
    }
    assert [item["id"] for item in payload["items"]] == ["xmcp-global", "xmcp-project"]
    assert payload["items"][0]["scope"] == "global"
    assert payload["items"][1]["scope"] == "project"
    assert payload["items"][1]["transport_types"] == ["sse"]


def test_mcp_monitor_routes_filter_and_block_non_admin(tmp_path, monkeypatch):
    from stores.json.external_mcp_store import ExternalMcpModule

    admin_client, external_mcp_store = _build_mcp_monitor_api_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "admin", "role": "admin"},
    )
    external_mcp_store.save(
        ExternalMcpModule(
            id="xmcp-global",
            name="Global MCP",
            endpoint_http="https://example.com/global",
            enabled=True,
        )
    )
    external_mcp_store.save(
        ExternalMcpModule(
            id="xmcp-project",
            name="Project MCP",
            endpoint_http="https://example.com/project",
            project_id="proj-1",
            enabled=False,
        )
    )

    filtered_response = admin_client.get(
        "/api/system/mcp-monitor/modules",
        params={"project_id": "proj-1", "include_disabled": False},
    )
    assert filtered_response.status_code == 200
    filtered_items = filtered_response.json()["items"]
    assert len(filtered_items) == 1
    assert filtered_items[0]["id"] == "xmcp-global"

    blocked_client, _ = _build_mcp_monitor_api_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "alice", "role": "user"},
    )
    blocked_response = blocked_client.get("/api/system/mcp-monitor/modules")
    assert blocked_response.status_code == 403


def test_mcp_monitor_routes_test_single_module(tmp_path, monkeypatch):
    from routers import mcp_monitor as mcp_monitor_router
    from stores.json.external_mcp_store import ExternalMcpModule

    client, external_mcp_store = _build_mcp_monitor_api_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "admin", "role": "admin"},
    )
    external_mcp_store.save(
        ExternalMcpModule(
            id="xmcp-project",
            name="Project MCP",
            endpoint_http="https://example.com/project",
            endpoint_sse="https://example.com/project-sse",
            project_id="proj-1",
            enabled=True,
        )
    )

    def _fake_run_external_mcp_connection_test(endpoint_http, endpoint_sse, timeout_sec=8):
        return {
            "ok": True,
            "summary": "连接测试通过：已测试 2 个端点，成功 2 个",
            "tested_at": "2026-04-02T09:00:00+00:00",
            "results": [
                {"transport": "http", "url": endpoint_http, "ok": True, "message": "HTTP ok"},
                {"transport": "sse", "url": endpoint_sse, "ok": True, "message": "SSE ok"},
            ],
            "timeout_sec": timeout_sec,
        }

    monkeypatch.setattr(
        mcp_monitor_router,
        "run_external_mcp_connection_test",
        _fake_run_external_mcp_connection_test,
    )

    response = client.post("/api/system/mcp-monitor/modules/xmcp-project/test", params={"timeout_sec": 12})
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["module"]["id"] == "xmcp-project"
    assert payload["module"]["scope"] == "project"
    assert payload["results"][0]["url"] == "https://example.com/project"
    assert payload["results"][1]["url"] == "https://example.com/project-sse"
