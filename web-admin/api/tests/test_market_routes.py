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


def test_market_cli_plugin_catalog_includes_my_profile(tmp_path, monkeypatch):
    from routers import market as market_router

    client = _build_market_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin", "roles": ["admin"]},
    )
    monkeypatch.setattr(
        market_router,
        "list_cli_plugins",
        lambda: [{"id": "feishu-cli", "name": "飞书 CLI", "install_command": "npx install"}],
    )
    monkeypatch.setattr(
        market_router,
        "serialize_cli_plugin_profile",
        lambda plugin_id, owner_username, auth_payload=None: {
            "plugin_id": plugin_id,
            "owner_username": owner_username,
            "status": "ready",
            "status_label": "已初始化",
            "home_dir": f"/runtime/{owner_username}/{plugin_id}",
        },
    )

    response = client.get("/api/market/cli-plugins")

    assert response.status_code == 200
    payload = response.json()["items"][0]
    assert payload["id"] == "feishu-cli"
    assert payload["my_profile"]["owner_username"] == "tester"
    assert payload["my_profile"]["status"] == "ready"
    assert payload["runtime_diagnostics"]["mode"] == "shared_toolchain_per_user_runtime"
    assert payload["runtime_diagnostics"]["runtime_root"] == ""


def test_market_cli_plugin_catalog_includes_runtime_diagnostics(tmp_path, monkeypatch):
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
                "install_command": "npx install",
                "install_status": {
                    "status": "installed",
                    "status_label": "已安装",
                    "installed": True,
                    "installed_version": "1.2.3",
                    "locked_version": "1.2.3",
                    "lock_source": "install-receipt",
                    "toolchain": {
                        "toolchain_root": "/srv/app/.ai-employee/cli-toolchain",
                        "toolchain_bin_dir": "/srv/app/.ai-employee/cli-toolchain/bin",
                        "plugin_binary_path": "/srv/app/.ai-employee/cli-toolchain/bin/lark-cli",
                    },
                    "health": {
                        "status": "healthy",
                        "status_label": "健康",
                        "checks": [
                            {
                                "key": "node",
                                "label": "Node.js",
                                "ok": True,
                                "value": "/usr/local/bin/node",
                                "required": True,
                            },
                            {
                                "key": "version_lock",
                                "label": "版本锁定",
                                "ok": True,
                                "value": "1.2.3",
                                "required": True,
                            },
                        ],
                        "missing_required": [],
                    },
                },
            }
        ],
    )
    monkeypatch.setattr(
        market_router,
        "serialize_cli_plugin_profile",
        lambda plugin_id, owner_username, auth_payload=None: {
            "plugin_id": plugin_id,
            "owner_username": owner_username,
            "status": "ready",
            "status_label": "已初始化",
            "runtime_root": f"/srv/app/.ai-employee/cli-runtime/users/{owner_username}/{plugin_id}",
            "home_dir": f"/srv/app/.ai-employee/cli-runtime/users/{owner_username}/{plugin_id}/home",
            "config_dir": f"/srv/app/.ai-employee/cli-runtime/users/{owner_username}/{plugin_id}/home/.config",
            "cache_dir": f"/srv/app/.ai-employee/cli-runtime/users/{owner_username}/{plugin_id}/home/.cache",
        },
    )

    response = client.get("/api/market/cli-plugins")

    assert response.status_code == 200
    payload = response.json()["items"][0]
    assert payload["runtime_diagnostics"]["mode_label"] == "共享安装 + 用户隔离"
    assert payload["runtime_diagnostics"]["toolchain_root"] == "/srv/app/.ai-employee/cli-toolchain"
    assert payload["runtime_diagnostics"]["runtime_root"] == "/srv/app/.ai-employee/cli-runtime/users/tester/feishu-cli"
    assert payload["runtime_diagnostics"]["locked_version"] == "1.2.3"
    assert payload["runtime_diagnostics"]["lock_source"] == "install-receipt"
    assert payload["runtime_diagnostics"]["health_status"] == "healthy"
    assert payload["runtime_diagnostics"]["health_checks"][1]["key"] == "version_lock"
    assert "共享工具链目录" in payload["runtime_diagnostics"]["summary"]
    assert "锁定版本 1.2.3" in payload["runtime_diagnostics"]["summary"]


def test_market_cli_plugin_profile_init_route(tmp_path, monkeypatch):
    from routers import market as market_router

    client = _build_market_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin", "roles": ["admin"]},
    )
    monkeypatch.setattr(
        market_router,
        "ensure_cli_plugin_profile",
        lambda plugin_id, owner_username, actor_username="": {
            "plugin_id": plugin_id,
            "owner_username": owner_username,
            "created_by": actor_username,
        },
    )
    monkeypatch.setattr(
        market_router,
        "serialize_cli_plugin_profile",
        lambda plugin_id, owner_username, auth_payload=None: {
            "plugin_id": plugin_id,
            "owner_username": owner_username,
            "status": "ready",
            "status_label": "已初始化",
        },
    )

    response = client.post(
        "/api/market/cli-plugins/feishu-cli/profiles/me/init",
        json={"plugin_id": "feishu-cli"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "initialized"
    assert response.json()["profile"]["plugin_id"] == "feishu-cli"


def test_market_cli_plugin_profile_login_route(tmp_path, monkeypatch):
    from routers import market as market_router

    client = _build_market_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin", "roles": ["admin"]},
    )
    monkeypatch.setattr(
        market_router,
        "create_login_task",
        lambda plugin_id, username, login_command="", metadata=None, timeout_sec=120: {
            "task_id": "cli-plugin-login-accepted",
            "plugin_id": plugin_id,
            "created_by": username,
            "status": "queued",
            "status_label": "排队中",
            "command": login_command,
        },
    )

    response = client.post(
        "/api/market/cli-plugins/feishu-cli/profiles/me/login",
        json={"plugin_id": "feishu-cli", "login_command": "lark-cli auth login"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert response.json()["task"]["task_id"] == "cli-plugin-login-accepted"
    assert response.json()["task"]["created_by"] == "tester"


def test_market_cli_plugin_profile_login_route_returns_pending_user_action(tmp_path, monkeypatch):
    from routers import market as market_router

    client = _build_market_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin", "roles": ["admin"]},
    )
    monkeypatch.setattr(
        market_router,
        "create_login_task",
        lambda plugin_id, username, login_command="", metadata=None, timeout_sec=120: {
            "task_id": "cli-plugin-login-waiting",
            "plugin_id": plugin_id,
            "created_by": username,
            "status": "waiting_user_action",
            "status_label": "等待授权",
            "status_reason": "请在浏览器完成授权",
            "command": login_command,
        },
    )

    response = client.post(
        "/api/market/cli-plugins/feishu-cli/profiles/me/login",
        json={"plugin_id": "feishu-cli", "login_command": "lark-cli auth login --recommend"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert response.json()["task"]["status"] == "waiting_user_action"
    assert response.json()["task"]["task_id"] == "cli-plugin-login-waiting"


def test_market_cli_plugin_profile_test_route(tmp_path, monkeypatch):
    from routers import market as market_router

    client = _build_market_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin", "roles": ["admin"]},
    )
    monkeypatch.setattr(
        market_router,
        "execute_cli_plugin_profile_command",
        lambda plugin_id, owner_username, command, timeout_sec=120: {
            "ok": True,
            "command": command,
            "stdout": "user auth active",
            "stderr": "",
            "exit_code": 0,
        },
    )
    monkeypatch.setattr(
        market_router,
        "update_cli_plugin_profile",
        lambda plugin_id, owner_username, **kwargs: {
            "plugin_id": plugin_id,
            "owner_username": owner_username,
            **kwargs,
        },
    )
    monkeypatch.setattr(
        market_router,
        "serialize_cli_plugin_profile",
        lambda plugin_id, owner_username, auth_payload=None: {
            "plugin_id": plugin_id,
            "owner_username": owner_username,
            "status": "authenticated",
            "status_label": "可用",
        },
    )

    response = client.post("/api/market/cli-plugins/feishu-cli/profiles/me/test")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["execution"]["stdout"] == "user auth active"


def test_market_cli_plugin_login_task_create_and_list(tmp_path, monkeypatch):
    from routers import market as market_router

    client = _build_market_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin", "roles": ["admin"]},
    )
    task_payload = {
        "task_id": "cli-plugin-login-123",
        "plugin_id": "feishu-cli",
        "status": "running",
        "status_label": "执行中",
        "created_by": "tester",
    }
    monkeypatch.setattr(
        market_router,
        "create_login_task",
        lambda plugin_id, username, login_command="", metadata=None, timeout_sec=120: {
            **task_payload,
            "plugin_id": plugin_id,
            "created_by": username,
            "command": login_command or "lark-cli auth login --recommend",
        },
    )
    monkeypatch.setattr(
        market_router,
        "list_login_tasks",
        lambda username, limit=20: [{**task_payload, "created_by": username}],
    )

    create_response = client.post(
        "/api/market/cli-plugins/login-tasks",
        json={"plugin_id": "feishu-cli", "login_command": ""},
    )

    assert create_response.status_code == 202
    assert create_response.json()["status"] == "accepted"
    assert create_response.json()["task"]["task_id"] == "cli-plugin-login-123"
    assert create_response.json()["task"]["created_by"] == "tester"

    list_response = client.get("/api/market/cli-plugins/login-tasks")

    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["task_id"] == "cli-plugin-login-123"


def test_market_cli_plugin_login_task_detail_enforces_owner(tmp_path, monkeypatch):
    from routers import market as market_router

    client = _build_market_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin", "roles": ["admin"]},
    )
    monkeypatch.setattr(
        market_router,
        "get_login_task",
        lambda task_id: {
            "task_id": task_id,
            "plugin_id": "feishu-cli",
            "created_by": "other-user",
            "status": "running",
        },
    )

    response = client.get("/api/market/cli-plugins/login-tasks/cli-plugin-login-123")

    assert response.status_code == 403
