"""Project code repository route tests."""

import subprocess

from fastapi.testclient import TestClient


def _build_project_code_repository_test_client(tmp_path, monkeypatch, auth_payload):
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
    ):
        getattr(store_factory, proxy_name)._instance = None

    app = create_app()
    app.dependency_overrides[require_auth] = lambda: auth_payload
    return TestClient(app), store_factory


def test_project_code_repository_routes_crud(tmp_path, monkeypatch):
    from stores.json.project_store import ProjectConfig, ProjectUserMember

    client, store_factory = _build_project_code_repository_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(
        ProjectConfig(id="proj-1", name="项目一", created_by="tester")
    )
    store_factory.project_store.upsert_user_member(
        ProjectUserMember(project_id="proj-1", username="tester", role="owner")
    )

    create_response = client.post(
        "/api/projects/proj-1/code-repositories",
        json={
            "name": "PC 后台",
            "repo_url": "https://github.com/acme/pc-admin.git",
            "default_branch": "develop",
            "description": "后台管理端",
            "local_path": "/workspace/pc-admin",
            "credential_ref": "github-main-token",
            "enabled": True,
        },
    )
    assert create_response.status_code == 200
    repository = create_response.json()["repository"]
    assert repository["id"].startswith("repo-")
    assert repository["project_id"] == "proj-1"
    assert repository["name"] == "PC 后台"
    assert repository["repo_url"] == "https://github.com/acme/pc-admin.git"
    assert repository["default_branch"] == "develop"
    assert repository["credential_ref"] == "github-main-token"
    assert repository["created_by"] == "tester"

    list_response = client.get("/api/projects/proj-1/code-repositories")
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["total"] == 1
    assert list_payload["repositories"][0]["id"] == repository["id"]

    update_response = client.put(
        f"/api/projects/proj-1/code-repositories/{repository['id']}",
        json={
            "name": "移动端",
            "repo_url": "git@github.com:acme/mobile.git",
            "default_branch": "",
            "enabled": False,
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()["repository"]
    assert updated["name"] == "移动端"
    assert updated["repo_url"] == "git@github.com:acme/mobile.git"
    assert updated["default_branch"] == "main"
    assert updated["enabled"] is False

    delete_response = client.delete(
        f"/api/projects/proj-1/code-repositories/{repository['id']}"
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["repository_id"] == repository["id"]

    empty_response = client.get("/api/projects/proj-1/code-repositories")
    assert empty_response.status_code == 200
    assert empty_response.json()["repositories"] == []


def test_project_code_repository_rejects_invalid_url(tmp_path, monkeypatch):
    from stores.json.project_store import ProjectConfig

    client, store_factory = _build_project_code_repository_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    store_factory.project_store.save(
        ProjectConfig(id="proj-1", name="项目一", created_by="tester")
    )

    response = client.post(
        "/api/projects/proj-1/code-repositories",
        json={"name": "坏地址", "repo_url": "not-a-git-url"},
    )
    assert response.status_code == 400
    assert "Git 地址格式不正确" in response.json()["detail"]


def test_project_code_repository_initialize_from_workspace_git(tmp_path, monkeypatch):
    from stores.json.project_store import ProjectConfig, ProjectUserMember

    client, store_factory = _build_project_code_repository_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    workspace = tmp_path / "workspace" / "pc-admin"
    workspace.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "git@github.com:acme/pc-admin.git"],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "checkout", "-b", "develop"],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )
    store_factory.project_store.save(
        ProjectConfig(
            id="proj-1",
            name="项目一",
            created_by="tester",
            workspace_path=str(workspace),
        )
    )
    store_factory.project_store.upsert_user_member(
        ProjectUserMember(project_id="proj-1", username="tester", role="owner")
    )

    response = client.post(
        "/api/projects/proj-1/code-repositories/initialize",
        json={},
    )

    assert response.status_code == 200
    repository = response.json()["repository"]
    assert repository["name"] == "pc-admin"
    assert repository["repo_url"] == "git@github.com:acme/pc-admin.git"
    assert repository["default_branch"] == "develop"
    assert repository["local_path"] == str(workspace.resolve())
    assert repository["source"] == "local_git"
    assert response.json()["created_count"] == 1

    list_response = client.get("/api/projects/proj-1/code-repositories")
    assert list_response.status_code == 200
    assert [item["repo_url"] for item in list_response.json()["repositories"]] == [
        "git@github.com:acme/pc-admin.git"
    ]


def test_project_code_repository_initialize_uses_connector_workspace_path(tmp_path, monkeypatch):
    from stores.json.project_store import ProjectConfig, ProjectUserMember

    client, store_factory = _build_project_code_repository_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    workspace = tmp_path / "connector-workspace" / "mobile"
    workspace.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/acme/mobile.git"],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )
    store_factory.project_store.save(
        ProjectConfig(
            id="proj-1",
            name="项目一",
            created_by="tester",
            workspace_path="",
            chat_settings={"connector_workspace_path": str(workspace)},
        )
    )
    store_factory.project_store.upsert_user_member(
        ProjectUserMember(project_id="proj-1", username="tester", role="owner")
    )

    response = client.post(
        "/api/projects/proj-1/code-repositories/initialize",
        json={},
    )

    assert response.status_code == 200
    repository = response.json()["repository"]
    assert repository["name"] == "mobile"
    assert repository["repo_url"] == "https://github.com/acme/mobile.git"
    assert repository["local_path"] == str(workspace.resolve())


def test_project_code_repository_initialize_saves_multiple_workspace_repositories(tmp_path, monkeypatch):
    from stores.json.project_store import ProjectConfig, ProjectUserMember

    client, store_factory = _build_project_code_repository_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    workspace = tmp_path / "workspace"
    api_repo = workspace / "api"
    web_repo = workspace / "web"
    api_repo.mkdir(parents=True)
    web_repo.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=api_repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "init"], cwd=web_repo, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "git@github.com:acme/api.git"],
        cwd=api_repo,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/acme/web.git"],
        cwd=web_repo,
        check=True,
        capture_output=True,
        text=True,
    )
    store_factory.project_store.save(
        ProjectConfig(
            id="proj-1",
            name="项目一",
            created_by="tester",
            workspace_path=str(workspace),
        )
    )
    store_factory.project_store.upsert_user_member(
        ProjectUserMember(project_id="proj-1", username="tester", role="owner")
    )

    response = client.post(
        "/api/projects/proj-1/code-repositories/initialize",
        json={},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["selection_required"] is False
    assert payload["created_count"] == 2
    assert payload["skipped_count"] == 0
    assert payload["repository"]["name"] == "api"
    assert [item["name"] for item in payload["repositories"]] == ["api", "web"]
    assert payload["repositories"][0]["repo_url"] == "git@github.com:acme/api.git"
    assert payload["repositories"][1]["repo_url"] == "https://github.com/acme/web.git"

    list_response = client.get("/api/projects/proj-1/code-repositories")
    assert list_response.status_code == 200
    saved_urls = [item["repo_url"] for item in list_response.json()["repositories"]]
    assert saved_urls == [
        "git@github.com:acme/api.git",
        "https://github.com/acme/web.git",
    ]


def test_project_code_repository_initialize_saves_multiple_remotes_once(tmp_path, monkeypatch):
    from stores.json.project_store import ProjectConfig, ProjectUserMember

    client, store_factory = _build_project_code_repository_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    workspace = tmp_path / "workspace" / "service"
    workspace.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "git@github.com:acme/service.git"],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "remote", "add", "mirror", "https://git.example.com/acme/service.git"],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )
    store_factory.project_store.save(
        ProjectConfig(
            id="proj-1",
            name="项目一",
            created_by="tester",
            workspace_path=str(workspace),
        )
    )
    store_factory.project_store.upsert_user_member(
        ProjectUserMember(project_id="proj-1", username="tester", role="owner")
    )

    first_response = client.post(
        "/api/projects/proj-1/code-repositories/initialize",
        json={},
    )
    second_response = client.post(
        "/api/projects/proj-1/code-repositories/initialize",
        json={},
    )

    assert first_response.status_code == 200
    assert first_response.json()["created_count"] == 2
    assert first_response.json()["skipped_count"] == 0
    assert second_response.status_code == 200
    assert second_response.json()["created_count"] == 0
    assert second_response.json()["skipped_count"] == 2
    list_response = client.get("/api/projects/proj-1/code-repositories")
    assert list_response.status_code == 200
    saved_urls = sorted(item["repo_url"] for item in list_response.json()["repositories"])
    assert saved_urls == [
        "git@github.com:acme/service.git",
        "https://git.example.com/acme/service.git",
    ]


def test_project_code_repository_initialize_does_not_save_local_path_without_remote(tmp_path, monkeypatch):
    from stores.json.project_store import ProjectConfig, ProjectUserMember

    client, store_factory = _build_project_code_repository_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    workspace = tmp_path / "workspace" / "local-only"
    workspace.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=workspace, check=True, capture_output=True, text=True)
    store_factory.project_store.save(
        ProjectConfig(
            id="proj-1",
            name="项目一",
            created_by="tester",
            workspace_path=str(workspace),
        )
    )
    store_factory.project_store.upsert_user_member(
        ProjectUserMember(project_id="proj-1", username="tester", role="owner")
    )

    response = client.post(
        "/api/projects/proj-1/code-repositories/initialize",
        json={},
    )

    assert response.status_code == 200
    assert response.json()["created_count"] == 0
    assert response.json()["skipped_count"] == 0
    assert response.json()["repositories"] == []
    list_response = client.get("/api/projects/proj-1/code-repositories")
    assert list_response.status_code == 200
    assert list_response.json()["repositories"] == []
