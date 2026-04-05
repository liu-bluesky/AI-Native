"""Project MCP online presence tests."""

from types import SimpleNamespace

from fastapi.testclient import TestClient


class _FakePresenceRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.sets: dict[str, set[str]] = {}

    async def get(self, key: str):
        return self.values.get(key)

    async def set(self, key: str, value: str, ex: int | None = None):
        _ = ex
        self.values[key] = value

    async def sadd(self, key: str, *values: str):
        self.sets.setdefault(key, set()).update(str(item) for item in values if str(item).strip())

    async def smembers(self, key: str):
        return set(self.sets.get(key, set()))

    async def mget(self, keys: list[str]):
        return [self.values.get(key) for key in keys]

    async def srem(self, key: str, *values: str):
        bucket = self.sets.setdefault(key, set())
        for item in values:
            bucket.discard(str(item))


def _build_project_mcp_monitor_client(tmp_path, monkeypatch, auth_payload):
    from core import config as core_config
    from core.deps import require_auth
    from core.server import create_app
    from stores import factory as store_factory
    from services import project_mcp_presence as project_mcp_presence_service

    monkeypatch.setenv("CORE_STORE_BACKEND", "json")
    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()
    for proxy_name in ("role_store", "system_config_store", "user_store"):
        getattr(store_factory, proxy_name)._instance = None

    fake_redis = _FakePresenceRedis()

    async def _get_fake_redis():
        return fake_redis

    monkeypatch.setattr(project_mcp_presence_service, "get_redis_client", _get_fake_redis)

    app = create_app()
    app.dependency_overrides[require_auth] = lambda: auth_payload
    return TestClient(app), fake_redis, project_mcp_presence_service


def test_project_mcp_activity_lists_recent_presence(tmp_path, monkeypatch):
    client, _, project_mcp_presence_service = _build_project_mcp_monitor_client(
        tmp_path,
        monkeypatch,
        {"sub": "admin", "role": "admin"},
    )

    import asyncio

    asyncio.run(
        project_mcp_presence_service.touch_project_mcp_presence(
            endpoint_type="project",
            entity_id="proj-1",
            entity_name="项目一",
            project_id="proj-1",
            project_name="项目一",
            developer_name="alice",
            key_owner_username="owner-alice",
            api_key="key-alice-12345678",
            client_ip="127.0.0.1",
            transport="sse",
            method="GET",
            path="/mcp/projects/proj-1/sse",
            session_id="sess-1",
        )
    )

    response = client.get("/api/system/mcp-monitor/project-activity")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ttl_seconds"] == 180
    assert payload["summary"] == {
        "active_projects": 1,
        "active_developers": 1,
        "active_sessions": 1,
    }
    assert payload["items"][0]["endpoint_type"] == "project"
    assert payload["items"][0]["entity_id"] == "proj-1"
    assert payload["items"][0]["project_id"] == "proj-1"
    assert payload["items"][0]["project_name"] == "项目一"
    assert payload["items"][0]["developer_name"] == "alice"
    assert payload["items"][0]["key_owner_username"] == "owner-alice"
    assert payload["items"][0]["transport"] == "sse"
    assert payload["items"][0]["session_id"] == "sess-1"


def test_project_mcp_activity_blocks_non_admin_and_prunes_stale(tmp_path, monkeypatch):
    admin_client, fake_redis, _ = _build_project_mcp_monitor_client(
        tmp_path,
        monkeypatch,
        {"sub": "admin", "role": "admin"},
    )
    fake_redis.sets.setdefault("system-mcp:presence:members", set()).update(
        {
            "system-mcp:presence:item:alive",
            "system-mcp:presence:item:stale",
        }
    )
    fake_redis.values["system-mcp:presence:item:alive"] = (
        '{"endpoint_type":"project","entity_id":"proj-1","entity_name":"项目一","project_id":"proj-1","project_name":"项目一","developer_name":"alice","api_key":"key...5678",'
        '"key_owner_username":"owner-alice",'
        '"client_ip":"127.0.0.1","transport":"sse","method":"GET","path":"/mcp/projects/proj-1/sse",'
        '"session_id":"sess-1","first_seen_at":"2026-04-02T00:00:00+00:00","last_seen_at":"2026-04-02T00:01:00+00:00","request_count":3}'
    )

    list_response = admin_client.get("/api/system/mcp-monitor/project-activity")
    assert list_response.status_code == 200
    items = list_response.json()["items"]
    assert len(items) == 1
    assert items[0]["project_id"] == "proj-1"
    assert "system-mcp:presence:item:stale" not in fake_redis.sets["system-mcp:presence:members"]

    blocked_client, _, _ = _build_project_mcp_monitor_client(
        tmp_path,
        monkeypatch,
        {"sub": "bob", "role": "user"},
    )
    blocked_response = blocked_client.get("/api/system/mcp-monitor/project-activity")
    assert blocked_response.status_code == 403


def test_project_mcp_proxy_tracks_runtime_presence(monkeypatch):
    import asyncio

    from services import dynamic_mcp_proxy_apps as proxy_apps

    captured: list[dict] = []

    async def _fake_touch_project_mcp_presence(**kwargs):
        captured.append(kwargs)
        return {"status": "ok"}

    monkeypatch.setattr(proxy_apps, "_touch_project_mcp_presence", _fake_touch_project_mcp_presence)

    class _UsageStore:
        @staticmethod
        def validate_key(api_key: str):
            return "alice" if api_key == "test-key" else ""

        @staticmethod
        def get_key(api_key: str):
            if api_key != "test-key":
                return None
            return {"created_by": "owner-alice"}

        @staticmethod
        def record_event(*args, **kwargs):
            _ = args, kwargs

    class _ProjectStore:
        @staticmethod
        def get(project_id: str):
            if project_id != "proj-1":
                return None
            return SimpleNamespace(id="proj-1", name="项目一", mcp_enabled=True, updated_at="2026-04-02T00:00:00+00:00")

        @staticmethod
        def list_members(project_id: str):
            _ = project_id
            return []

    class _EmployeeStore:
        @staticmethod
        def get(employee_id: str):
            _ = employee_id
            return None

    class _DummyTransportApp:
        async def __call__(self, scope, receive, send):
            _ = scope, receive
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok", "more_body": False})

    app = proxy_apps.ProjectMcpProxyApp(
        project_store=_ProjectStore(),
        employee_store=_EmployeeStore(),
        usage_store=_UsageStore(),
        current_api_key_ctx=SimpleNamespace(set=lambda value: value),
        current_developer_name_ctx=SimpleNamespace(set=lambda value: value),
        session_keys={},
        session_contexts={},
        project_apps={},
        project_app_signatures={},
        create_project_mcp=lambda project_id: _DummyTransportApp(),
        list_visible_external_mcp_modules=lambda project_id: [],
        replace_path_suffix=lambda path, old, new: path.replace(old, new),
        dual_transport_app_type=_DummyTransportApp,
        project_mcp_app_rev="test-rev",
    )

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/mcp/projects/proj-1/sse",
        "query_string": b"key=test-key&session_id=sess-1",
        "headers": [],
        "client": ("127.0.0.1", 8080),
        "path_params": {"project_id": "proj-1"},
    }
    sent_messages = []

    async def _receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def _send(message):
        sent_messages.append(message)

    asyncio.run(app(scope, _receive, _send))

    assert captured
    assert captured[0]["project_id"] == "proj-1"
    assert captured[0]["endpoint_type"] == "project"
    assert captured[0]["project_name"] == "项目一"
    assert captured[0]["developer_name"] == "alice"
    assert captured[0]["key_owner_username"] == "owner-alice"
    assert captured[0]["transport"] == "sse"
    assert captured[0]["session_id"] == "sess-1"
    assert sent_messages[-1]["type"] == "http.response.body"


def test_system_mcp_activity_lists_multiple_endpoint_types(tmp_path, monkeypatch):
    client, _, project_mcp_presence_service = _build_project_mcp_monitor_client(
        tmp_path,
        monkeypatch,
        {"sub": "admin", "role": "admin"},
    )

    import asyncio

    asyncio.run(
        project_mcp_presence_service.touch_project_mcp_presence(
            endpoint_type="query",
            entity_id="query-center",
            entity_name="统一查询 MCP",
            project_id="proj-1",
            project_name="项目一",
            developer_name="alice",
            key_owner_username="owner-alice",
            api_key="key-alice-12345678",
            client_ip="127.0.0.1",
            transport="sse",
            method="GET",
            path="/mcp/query/sse",
            session_id="sess-q1",
        )
    )
    asyncio.run(
        project_mcp_presence_service.touch_project_mcp_presence(
            endpoint_type="employee",
            entity_id="emp-1",
            entity_name="员工一",
            project_id="proj-1",
            project_name="项目一",
            developer_name="alice",
            key_owner_username="owner-alice",
            api_key="key-alice-12345678",
            client_ip="127.0.0.1",
            transport="streamable-http",
            method="POST",
            path="/mcp/employees/emp-1/mcp",
            session_id="sess-e1",
        )
    )

    response = client.get("/api/system/mcp-monitor/activity")
    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["active_entries"] == 2
    assert payload["summary"]["active_endpoint_types"] == 2
    assert payload["summary"]["active_projects"] == 1
    assert payload["summary"]["active_developers"] == 2
    assert {item["endpoint_type"] for item in payload["items"]} == {"query", "employee"}


def test_query_mcp_proxy_backfills_project_from_request_context(monkeypatch):
    from fastapi import FastAPI, Request

    from services import dynamic_mcp_proxy_apps as proxy_apps
    from services.dynamic_mcp_transports import replace_path_suffix

    captured: list[dict] = []

    async def _fake_touch_project_mcp_presence(**kwargs):
        captured.append(kwargs)
        return {"status": "ok"}

    monkeypatch.setattr(proxy_apps, "_touch_project_mcp_presence", _fake_touch_project_mcp_presence)
    monkeypatch.setattr(proxy_apps, "get_client_ip", lambda scope: "127.0.0.1")

    class _UsageStore:
        @staticmethod
        def validate_key(api_key: str):
            return "alice" if api_key == "test-key" else ""

        @staticmethod
        def get_key(api_key: str):
            if api_key != "test-key":
                return None
            return {"created_by": "owner-alice"}

        @staticmethod
        def record_event(*args, **kwargs):
            _ = args, kwargs

    downstream = FastAPI()

    @downstream.api_route("/{full_path:path}", methods=["GET", "POST"])
    async def _echo(request: Request, full_path: str):
        _ = full_path
        await request.body()
        return {"ok": True}

    proxy_app = proxy_apps.QueryMcpProxyApp(
        usage_store=_UsageStore(),
        current_api_key_ctx=SimpleNamespace(set=lambda value: value),
        current_developer_name_ctx=SimpleNamespace(set=lambda value: value),
        session_keys={},
        session_contexts={},
        query_app=downstream,
        save_auto_query_memory=lambda *args, **kwargs: None,
        replace_path_suffix=replace_path_suffix,
    )

    app = FastAPI()
    app.mount("/mcp/query", proxy_app)
    client = TestClient(app)

    response = client.post(
        "/mcp/query/mcp?key=test-key&session_id=sess-q1",
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "get_manual_content",
                "arguments": {
                    "project_id": "proj-1",
                    "project_name": "项目一",
                },
            },
        },
    )

    assert response.status_code == 200
    assert captured
    assert captured[-1]["endpoint_type"] == "query"
    assert captured[-1]["project_id"] == "proj-1"
    assert captured[-1]["project_name"] == "项目一"
    assert captured[-1]["key_owner_username"] == "owner-alice"
    assert captured[-1]["session_id"] == "sess-q1"
