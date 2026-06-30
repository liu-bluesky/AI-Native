"""外部 MCP 模块管理路由测试"""

from fastapi.testclient import TestClient


def _build_mcp_modules_api_test_client(tmp_path, monkeypatch):
    from core import config as core_config
    from core.deps import require_auth
    from core.server import create_app
    from stores import factory as store_factory

    monkeypatch.setenv("CORE_STORE_BACKEND", "json")
    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()
    for proxy_name in ("external_mcp_store", "user_store", "role_store", "system_config_store"):
        getattr(store_factory, proxy_name)._instance = None

    app = create_app()
    app.dependency_overrides[require_auth] = lambda: {"sub": "admin", "role": "admin"}
    return TestClient(app)


def test_create_external_mcp_module_preserves_stdio_json_config(tmp_path, monkeypatch):
    client = _build_mcp_modules_api_test_client(tmp_path, monkeypatch)
    raw_config = {
        "type": "stdio",
        "command": "/usr/local/bin/demo-mcp",
        "args": ["--headless", "--isolated"],
        "env": {"DEMO": "1"},
        "scope": "project",
        "enabled": True,
    }

    response = client.post(
        "/api/mcp/modules",
        json={
            "name": "demo-mcp",
            "transport_type": "stdio",
            "command": raw_config["command"],
            "args": raw_config["args"],
            "env": raw_config["env"],
            "config": raw_config,
            "project_id": "proj-1",
            "enabled": True,
        },
    )

    assert response.status_code == 200
    module = response.json()["module"]
    assert module["transport_type"] == "stdio"
    assert module["command"] == "/usr/local/bin/demo-mcp"
    assert module["args"] == ["--headless", "--isolated"]
    assert module["env"] == {"DEMO": "1"}
    assert module["config"] == raw_config
    assert module["endpoint_http"] == ""
    assert module["endpoint_sse"] == ""


def test_create_external_mcp_module_keeps_sse_config_url(tmp_path, monkeypatch):
    client = _build_mcp_modules_api_test_client(tmp_path, monkeypatch)
    raw_config = {
        "description": "统一查询 MCP 入口",
        "type": "sse",
        "url": "http://127.0.0.1:8000/mcp/query/sse?key=ak-demo",
    }

    response = client.post(
        "/api/mcp/modules",
        json={
            "name": "query-center",
            "description": raw_config["description"],
            "transport_type": "sse",
            "endpoint_sse": raw_config["url"],
            "config": raw_config,
            "project_id": "proj-1",
            "enabled": True,
        },
    )

    assert response.status_code == 200
    module = response.json()["module"]
    assert module["transport_type"] == "sse"
    assert module["endpoint_sse"] == raw_config["url"]
    assert module["description"] == "统一查询 MCP 入口"
    assert module["config"] == raw_config


def test_create_external_mcp_module_preserves_headers(tmp_path, monkeypatch):
    client = _build_mcp_modules_api_test_client(tmp_path, monkeypatch)
    raw_config = {
        "url": "https://pixso.cn/api/mcp/mcp",
        "headers": {"Token": "demo-token"},
    }

    response = client.post(
        "/api/mcp/modules",
        json={
            "name": "pixso-remote-mcp",
            "transport_type": "http",
            "endpoint_http": raw_config["url"],
            "headers": raw_config["headers"],
            "config": raw_config,
            "project_id": "proj-1",
            "enabled": True,
        },
    )

    assert response.status_code == 200
    module = response.json()["module"]
    assert module["transport_type"] == "http"
    assert module["endpoint_http"] == "https://pixso.cn/api/mcp/mcp"
    assert module["headers"] == {"Token": "demo-token"}
    assert module["config"] == raw_config
