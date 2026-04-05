"""在线用户路由测试"""

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


def _build_online_user_api_test_client(tmp_path, monkeypatch, auth_payload):
    from core import config as core_config
    from core.deps import require_auth
    from core.server import create_app
    from routers import online_users as online_users_router
    from stores import factory as store_factory

    monkeypatch.setenv("CORE_STORE_BACKEND", "json")
    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()
    for proxy_name in ("role_store", "system_config_store", "user_store"):
        getattr(store_factory, proxy_name)._instance = None

    fake_redis = _FakePresenceRedis()

    async def _get_fake_redis():
        return fake_redis

    monkeypatch.setattr(online_users_router, "get_redis_client", _get_fake_redis)

    app = create_app()
    app.dependency_overrides[require_auth] = lambda: auth_payload
    return TestClient(app), fake_redis


def test_online_user_routes_track_presence_and_list_for_admin(tmp_path, monkeypatch):
    client, fake_redis = _build_online_user_api_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "admin", "role": "admin"},
    )

    heartbeat_response = client.post(
        "/api/system/online-users/heartbeat",
        json={"current_path": "/ai/chat/settings/online-users"},
        headers={"user-agent": "codex-test"},
    )
    assert heartbeat_response.status_code == 200
    heartbeat_payload = heartbeat_response.json()
    assert heartbeat_payload["status"] == "ok"
    assert heartbeat_payload["item"]["username"] == "admin"
    assert heartbeat_payload["item"]["current_path"] == "/ai/chat/settings/online-users"

    list_response = client.get("/api/system/online-users")
    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["ttl_seconds"] == 150
    assert len(payload["items"]) == 1
    assert payload["items"][0]["username"] == "admin"
    assert payload["items"][0]["role"] == "admin"
    assert payload["items"][0]["user_agent"] == "codex-test"
    assert "online-users:user:admin" in fake_redis.values


def test_online_user_routes_allow_heartbeat_but_block_non_admin_list(tmp_path, monkeypatch):
    client, _ = _build_online_user_api_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "alice", "role": "user"},
    )

    heartbeat_response = client.post(
        "/api/system/online-users/heartbeat",
        json={"current_path": "/ai/chat"},
    )
    assert heartbeat_response.status_code == 200

    list_response = client.get("/api/system/online-users")
    assert list_response.status_code == 403


def test_online_user_routes_prune_stale_entries(tmp_path, monkeypatch):
    client, fake_redis = _build_online_user_api_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "admin", "role": "admin"},
    )
    awaitable_set = fake_redis.sets.setdefault("online-users:members", set())
    awaitable_set.update({"active-user", "stale-user"})
    fake_redis.values["online-users:user:active-user"] = (
        '{"username":"active-user","role":"user","current_path":"/ai/chat","client_ip":"127.0.0.1",'
        '"user_agent":"browser","first_seen_at":"2026-04-02T00:00:00+00:00","last_seen_at":"2026-04-02T00:01:00+00:00"}'
    )

    list_response = client.get("/api/system/online-users")
    assert list_response.status_code == 200
    items = list_response.json()["items"]
    assert len(items) == 1
    assert items[0]["username"] == "active-user"
    assert "stale-user" not in fake_redis.sets["online-users:members"]
