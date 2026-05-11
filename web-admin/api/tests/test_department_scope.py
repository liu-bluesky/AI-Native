"""Department hierarchy and data-scope tests."""

from fastapi.testclient import TestClient


def _reset_store_factory(store_factory):
    for proxy_name in (
        "role_store",
        "user_store",
        "department_store",
        "project_store",
        "mcp_bridge_store",
        "system_config_store",
        "bot_connector_store",
    ):
        proxy = getattr(store_factory, proxy_name, None)
        if proxy is not None and hasattr(proxy, "_instance"):
            proxy._instance = None


def _build_department_test_client(tmp_path, monkeypatch, auth_payload):
    from core import config as core_config
    from core.deps import require_auth
    from core.server import create_app
    from stores import mcp_bridge as mcp_bridge_bundle
    from stores import factory as store_factory

    monkeypatch.setenv("CORE_STORE_BACKEND", "json")
    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()
    mcp_bridge_bundle._store_bundle = None
    _reset_store_factory(store_factory)

    app = create_app()
    app.dependency_overrides[require_auth] = lambda: auth_payload
    return TestClient(app), store_factory


def _seed_department_scope(store_factory):
    from stores.json.department_store import Department
    from stores.json.role_store import RoleConfig
    from stores.json.user_store import User, hash_password

    store_factory.role_store.save(
        RoleConfig(
            id="scope",
            name="Scoped viewer",
            permissions=["menu.users", "menu.departments"],
        )
    )
    store_factory.role_store.save(
        RoleConfig(
            id="invite_admin",
            name="Invite admin",
            permissions=[
                "button.users.create",
                "button.departments.assign_users",
                "menu.departments",
            ],
        )
    )

    for username in ("lead", "child", "peer", "boss"):
        store_factory.user_store.save(
            User(
                username=username,
                password_hash=hash_password("secret123"),
                role="scope",
                created_by="admin",
            )
        )

    store_factory.department_store.save_department(
        Department(id="dept-root", name="Root", manager_username="boss")
    )
    store_factory.department_store.save_department(
        Department(
            id="dept-team-a",
            name="Team A",
            parent_id="dept-root",
            manager_username="lead",
        )
    )
    store_factory.department_store.save_department(
        Department(id="dept-team-b", name="Team B", parent_id="dept-root")
    )
    store_factory.department_store.set_user_memberships("boss", ["dept-root"])
    store_factory.department_store.set_user_memberships("lead", ["dept-team-a"])
    store_factory.department_store.set_user_memberships("child", ["dept-team-a"])
    store_factory.department_store.set_user_memberships("peer", ["dept-team-b"])


def test_department_store_prevents_hierarchy_cycle(tmp_path):
    from stores.json.department_store import Department, DepartmentStore

    store = DepartmentStore(tmp_path / "api-data")
    store.save_department(Department(id="dept-a", name="A"))
    store.save_department(Department(id="dept-b", name="B", parent_id="dept-a"))

    try:
        store.save_department(Department(id="dept-a", name="A", parent_id="dept-b"))
        assert False, "cycle should be rejected"
    except ValueError as exc:
        assert "cycle" in str(exc).lower()


def test_visible_usernames_follow_department_hierarchy(tmp_path, monkeypatch):
    client, store_factory = _build_department_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "lead", "role": "scope", "roles": ["scope"]},
    )
    _seed_department_scope(store_factory)

    response = client.get("/api/users")

    assert response.status_code == 200
    usernames = {item["username"] for item in response.json()["users"]}
    assert usernames == {"lead", "child"}
    assert response.json()["scope"]["visible_usernames"] == ["child", "lead"]


def test_department_list_hides_peer_members_for_scoped_user(tmp_path, monkeypatch):
    client, store_factory = _build_department_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "lead", "role": "scope", "roles": ["scope"]},
    )
    _seed_department_scope(store_factory)

    response = client.get("/api/departments")

    assert response.status_code == 200
    departments = response.json()["departments"]
    assert {item["id"] for item in departments} == {"dept-team-a"}
    assert departments[0]["usernames"] == ["child", "lead"]
    assert "peer" not in departments[0]["usernames"]


def test_department_user_options_do_not_require_users_menu(tmp_path, monkeypatch):
    client, store_factory = _build_department_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "lead", "role": "department_only", "roles": ["department_only"]},
    )
    from stores.json.role_store import RoleConfig

    _seed_department_scope(store_factory)
    store_factory.role_store.save(
        RoleConfig(
            id="department_only",
            name="Department only",
            permissions=["menu.departments"],
        )
    )
    user = store_factory.user_store.get("lead")
    store_factory.user_store.save(
        type(user)(
            username=user.username,
            password_hash=user.password_hash,
            role="department_only",
            default_ai_provider_id=user.default_ai_provider_id,
            created_by=user.created_by,
            created_at=user.created_at,
        )
    )

    response = client.get("/api/departments/user-options")

    assert response.status_code == 200
    usernames = {item["username"] for item in response.json()["users"]}
    assert usernames == {"lead", "child"}


def test_assign_department_users_accepts_email_username(tmp_path, monkeypatch):
    client, store_factory = _build_department_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "admin", "role": "admin", "roles": ["admin"]},
    )
    _seed_department_scope(store_factory)

    from stores.json.user_store import User, hash_password

    store_factory.user_store.save(
        User(
            username="418428286@qq.com",
            password_hash=hash_password("secret123"),
            role="scope",
            created_by="admin",
        )
    )

    response = client.put(
        "/api/departments/dept-team-a/users",
        json={"usernames": ["lead", "418428286@qq.com"]},
    )

    assert response.status_code == 200
    memberships = response.json()["memberships"]
    assert {item["username"] for item in memberships} == {"lead", "418428286@qq.com"}
    assert {
        item.username
        for item in store_factory.department_store.list_department_memberships("dept-team-a")
    } == {"lead", "418428286@qq.com"}


def test_user_department_detail_hides_peer_for_scoped_user(tmp_path, monkeypatch):
    client, store_factory = _build_department_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "lead", "role": "scope", "roles": ["scope"]},
    )
    _seed_department_scope(store_factory)

    response = client.get("/api/departments/users/peer")

    assert response.status_code == 404


def test_admin_department_scope_is_unrestricted(tmp_path, monkeypatch):
    client, store_factory = _build_department_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "admin", "role": "admin", "roles": ["admin"]},
    )
    _seed_department_scope(store_factory)

    response = client.get("/api/users")

    assert response.status_code == 200
    usernames = {item["username"] for item in response.json()["users"]}
    assert {"boss", "lead", "child", "peer"}.issubset(usernames)
    assert response.json()["scope"]["unrestricted"] is True


def test_register_invitation_assigns_invited_departments(tmp_path, monkeypatch):
    client, store_factory = _build_department_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "admin", "role": "admin", "roles": ["admin"]},
    )
    _seed_department_scope(store_factory)

    invite_response = client.post(
        "/api/auth/invitations",
        json={
            "department_ids": ["dept-team-a"],
            "primary_department_id": "dept-team-a",
            "expires_in_hours": 24,
        },
    )

    assert invite_response.status_code == 200
    token = invite_response.json()["token"]
    code = invite_response.json()["code"]
    assert token
    assert token == code
    assert len(token) <= 16
    assert "." not in token
    assert "dept-team-a" not in token
    assert invite_response.json()["register_path"] == f"/register?invite={code}"

    register_response = client.post(
        "/api/auth/register",
        json={
            "email": "invite-user@example.com",
            "password": "secret123",
            "invite_token": token,
        },
    )

    assert register_response.status_code == 200
    assert register_response.json()["department_ids"] == ["dept-team-a"]
    memberships = store_factory.department_store.list_user_memberships("invite-user@example.com")
    assert [item.department_id for item in memberships] == ["dept-team-a"]
    assert memberships[0].is_primary is True


def test_register_rejects_tampered_invite_token(tmp_path, monkeypatch):
    client, store_factory = _build_department_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "admin", "role": "admin", "roles": ["admin"]},
    )
    _seed_department_scope(store_factory)

    invite_response = client.post(
        "/api/auth/invitations",
        json={"department_ids": ["dept-team-a"], "expires_in_hours": 24},
    )
    assert invite_response.status_code == 200
    token = invite_response.json()["token"]
    tampered = f"{token[:-1]}x"

    register_response = client.post(
        "/api/auth/register",
        json={
            "email": "tampered-invite@example.com",
            "password": "secret123",
            "invite_token": tampered,
        },
    )

    assert register_response.status_code == 400
    assert store_factory.user_store.get("tampered-invite@example.com") is None


def test_legacy_long_invite_token_still_registers(tmp_path, monkeypatch):
    client, store_factory = _build_department_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "admin", "role": "admin", "roles": ["admin"]},
    )
    _seed_department_scope(store_factory)

    from routers import init_auth

    now = 1_800_000_000
    legacy_token = init_auth._encode_register_invite(
        {
            "v": 1,
            "typ": "register_invite",
            "department_ids": ["dept-team-a"],
            "primary_department_id": "dept-team-a",
            "iat": now,
            "exp": now + 3600,
            "nonce": "legacy-test",
            "created_by": "admin",
        }
    )

    register_response = client.post(
        "/api/auth/register",
        json={
            "email": "legacy-invite@example.com",
            "password": "secret123",
            "invite_token": legacy_token,
        },
    )

    assert register_response.status_code == 200
    memberships = store_factory.department_store.list_user_memberships("legacy-invite@example.com")
    assert [item.department_id for item in memberships] == ["dept-team-a"]


def test_scoped_user_cannot_invite_to_invisible_department(tmp_path, monkeypatch):
    client, store_factory = _build_department_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "lead", "role": "invite_admin", "roles": ["invite_admin"]},
    )
    _seed_department_scope(store_factory)

    response = client.post(
        "/api/auth/invitations",
        json={"department_ids": ["dept-team-b"], "expires_in_hours": 24},
    )

    assert response.status_code == 403
