"""更新日志路由测试"""

from fastapi.testclient import TestClient


def _build_changelog_api_test_client(tmp_path, monkeypatch, auth_payload):
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
        "bot_connector_store",
        "system_config_store",
        "project_store",
        "project_material_store",
        "project_studio_export_store",
        "changelog_entry_store",
    ):
        getattr(store_factory, proxy_name)._instance = None

    app = create_app()
    app.dependency_overrides[require_auth] = lambda: auth_payload
    return TestClient(app)


def test_changelog_routes_support_crud(tmp_path, monkeypatch):
    client = _build_changelog_api_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )

    create_response = client.post(
        "/api/changelog-entries",
        json={
            "version": "v1.0.0",
            "title": "发布更新日志管理",
            "summary": "新增独立菜单和独立表。",
            "content": "- 支持增删改查\n- 支持官网展示",
            "release_date": "2026-03-31",
            "published": False,
            "sort_order": 20,
        },
    )

    assert create_response.status_code == 200
    created = create_response.json()["item"]
    entry_id = created["id"]
    assert created["created_by"] == "tester"
    assert created["title"] == "发布更新日志管理"
    assert created["published"] is False

    list_response = client.get("/api/changelog-entries")
    assert list_response.status_code == 200
    assert any(item["id"] == entry_id for item in list_response.json()["items"])

    detail_response = client.get(f"/api/changelog-entries/{entry_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["item"]["summary"] == "新增独立菜单和独立表。"

    update_response = client.put(
        f"/api/changelog-entries/{entry_id}",
        json={
            "title": "发布独立更新日志中心",
            "published": True,
            "sort_order": 10,
        },
    )

    assert update_response.status_code == 200
    updated = update_response.json()["item"]
    assert updated["title"] == "发布独立更新日志中心"
    assert updated["published"] is True
    assert updated["sort_order"] == 10

    delete_response = client.delete(f"/api/changelog-entries/{entry_id}")
    assert delete_response.status_code == 200
    assert delete_response.json()["status"] == "deleted"

    missing_response = client.get(f"/api/changelog-entries/{entry_id}")
    assert missing_response.status_code == 404


def test_public_changelog_endpoint_returns_only_published_items(tmp_path, monkeypatch):
    client = _build_changelog_api_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )

    draft_response = client.post(
        "/api/changelog-entries",
        json={
            "version": "v1.0.1",
            "title": "草稿版本",
            "content": "- 仅后台可见",
            "release_date": "2026-03-30",
            "published": False,
            "sort_order": 30,
        },
    )
    assert draft_response.status_code == 200

    published_response = client.post(
        "/api/changelog-entries",
        json={
            "version": "v1.1.0",
            "title": "公开版本",
            "summary": "官网显示这一条。",
            "content": "- 独立菜单\n- 独立数据源",
            "release_date": "2026-03-31",
            "published": True,
            "sort_order": 10,
        },
    )
    assert published_response.status_code == 200

    public_response = client.get("/api/changelog-entries/public")
    assert public_response.status_code == 200

    items = public_response.json()["items"]
    assert len(items) == 1
    assert items[0]["title"] == "公开版本"
    assert items[0]["published"] is True
