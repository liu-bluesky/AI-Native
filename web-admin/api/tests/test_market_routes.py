"""市场路由测试"""

from fastapi.testclient import TestClient


def _build_market_test_client(tmp_path, monkeypatch, auth_payload):
    from core import config as core_config
    from core.deps import require_auth
    from core.server import create_app
    from stores import mcp_bridge as mcp_bridge_store
    from stores import factory as store_factory

    monkeypatch.setenv("CORE_STORE_BACKEND", "json")
    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()
    mcp_bridge_store._store_bundle = None
    for proxy_name in (
        "role_store",
        "bot_connector_store",
        "system_config_store",
        "user_store",
    ):
        getattr(store_factory, proxy_name)._instance = None

    app = create_app()
    app.dependency_overrides[require_auth] = lambda: auth_payload
    return TestClient(app)


def test_market_catalog_includes_cli_plugins(tmp_path, monkeypatch):
    from routers import market as market_router

    client = _build_market_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin", "roles": ["admin"]},
    )
    monkeypatch.setattr(
        market_router,
        "list_cli_plugins",
        lambda: [
            {
                "id": "feishu-cli",
                "name": "飞书 CLI",
                "install_command": "npx @larksuite/cli@latest install",
                "install_status": {
                    "status": "installed",
                    "status_label": "已安装",
                    "status_reason": "当前已是最新版本 1.2.3",
                    "installed": True,
                    "installed_version": "1.2.3",
                    "latest_version": "1.2.3",
                    "update_available": False,
                },
            }
        ],
    )

    response = client.get("/api/market/catalog")

    assert response.status_code == 200
    cli_plugins = response.json()["catalog"]["cli_plugins"]
    assert len(cli_plugins) >= 1
    assert cli_plugins[0]["id"] == "feishu-cli"
    assert "install_command" in cli_plugins[0]
    assert cli_plugins[0]["install_status"]["status"] == "installed"
    assert response.json()["meta"]["cli_plugin_count"] >= 1


def test_market_cli_plugin_install_executes_curated_installer(tmp_path, monkeypatch):
    from routers import market as market_router

    client = _build_market_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin", "roles": ["admin"]},
    )
    monkeypatch.setattr(
        market_router,
        "install_cli_plugin",
        lambda plugin_id, timeout_sec=180: {
            "plugin": {
                "id": plugin_id,
                "name": "飞书 CLI",
            },
            "command": "npx @larksuite/cli@latest install",
            "exit_code": 0,
            "ok": True,
            "stdout": "installed",
            "stderr": "",
            "install_status": {
                "status": "installed",
                "status_label": "已安装",
                "installed": True,
                "installed_version": "1.2.3",
                "latest_version": "1.2.3",
                "update_available": False,
            },
        },
    )

    response = client.post(
        "/api/market/cli-plugins/install",
        json={"plugin_id": "feishu-cli"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "installed"
    assert payload["plugin"]["id"] == "feishu-cli"
    assert payload["command"] == "npx @larksuite/cli@latest install"
    assert payload["stdout"] == "installed"
    assert payload["install_status"]["status"] == "installed"


def test_market_cli_plugin_install_task_create_and_list(tmp_path, monkeypatch):
    from routers import market as market_router

    client = _build_market_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin", "roles": ["admin"]},
    )
    task_payload = {
        "task_id": "cli-plugin-install-123",
        "plugin_id": "feishu-cli",
        "status": "running",
        "status_label": "安装中",
        "created_by": "tester",
    }
    monkeypatch.setattr(
        market_router,
        "create_install_task",
        lambda plugin_id, username, timeout_sec=1800: {
            **task_payload,
            "plugin_id": plugin_id,
            "created_by": username,
            "timeout_sec": timeout_sec,
        },
    )
    monkeypatch.setattr(
        market_router,
        "list_install_tasks",
        lambda username, limit=20: [{**task_payload, "created_by": username}],
    )

    create_response = client.post(
        "/api/market/cli-plugins/install-tasks",
        json={"plugin_id": "feishu-cli"},
    )

    assert create_response.status_code == 202
    assert create_response.json()["status"] == "accepted"
    assert create_response.json()["task"]["task_id"] == "cli-plugin-install-123"
    assert create_response.json()["task"]["created_by"] == "tester"

    list_response = client.get("/api/market/cli-plugins/install-tasks")

    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["task_id"] == "cli-plugin-install-123"


def test_market_cli_plugin_install_task_detail_enforces_owner(tmp_path, monkeypatch):
    from routers import market as market_router

    client = _build_market_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin", "roles": ["admin"]},
    )
    monkeypatch.setattr(
        market_router,
        "get_install_task",
        lambda task_id: {
            "task_id": task_id,
            "plugin_id": "feishu-cli",
            "created_by": "other-user",
            "status": "running",
        },
    )

    response = client.get("/api/market/cli-plugins/install-tasks/cli-plugin-install-123")

    assert response.status_code == 403
