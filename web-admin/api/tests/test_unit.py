"""模拟测试（无需 Redis）"""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError


@pytest.mark.asyncio
async def test_orchestrator_logic():
    """测试 AgentOrchestrator 逻辑"""
    from services.agent_orchestrator import AgentOrchestrator

    llm_service = MagicMock()
    conv_manager = MagicMock()
    conv_manager.get_context = AsyncMock(return_value=[])
    conv_manager.append_message = AsyncMock()

    orchestrator = AgentOrchestrator(llm_service, conv_manager)

    tools = [{"tool_name": "test_tool", "description": "测试工具"}]
    formatted = orchestrator._format_tools(tools)

    assert len(formatted) == 1
    assert formatted[0]["type"] == "function"
    assert formatted[0]["function"]["name"] == "test_tool"


@pytest.mark.asyncio
async def test_tool_executor_logic():
    """测试 ToolExecutor 逻辑"""
    from services.tool_executor import ToolExecutor

    executor = ToolExecutor("test-proj", "test-emp")
    assert executor._timeout == 60

def test_build_local_connector_file_tools_includes_coding_tools():
    from services.local_connector_service import build_local_connector_file_tools

    tool_names = {item["tool_name"] for item in build_local_connector_file_tools()}

    assert "local_connector_read_file" in tool_names
    assert "local_connector_write_file" in tool_names
    assert "local_connector_run_command" in tool_names


@pytest.mark.asyncio
async def test_tool_executor_routes_local_connector_tools(monkeypatch):
    from services import local_connector_service as connector_svc
    from services.tool_executor import ToolExecutor

    captured: dict = {}

    async def fake_read(connector, **kwargs):
        captured["connector"] = connector
        captured["kwargs"] = kwargs
        return {"ok": True, "path": kwargs["path"], "content": "demo"}

    monkeypatch.setattr(connector_svc, "read_connector_file", fake_read)

    connector = object()
    executor = ToolExecutor(
        "test-proj",
        "test-emp",
        local_connector=connector,
        local_connector_workspace_path="/tmp/workspace",
        local_connector_sandbox_mode="workspace-write",
    )

    result = await executor._execute_tool(
        "local_connector_read_file",
        {"path": "src/app.py", "start_line": 5, "end_line": 12},
    )

    assert result["ok"] is True
    assert captured["connector"] is connector
    assert captured["kwargs"]["workspace_path"] == "/tmp/workspace"
    assert captured["kwargs"]["path"] == "src/app.py"
    assert captured["kwargs"]["start_line"] == 5
    assert captured["kwargs"]["end_line"] == 12


def test_project_config_defaults_type_to_mixed_for_legacy_payload():
    from stores.json.project_store import ProjectConfig

    project = ProjectConfig(**{"id": "proj-legacy", "name": "旧项目"})

    assert project.type == "mixed"


def test_project_create_req_rejects_unknown_type():
    from models.requests import ProjectCreateReq

    with pytest.raises(ValidationError):
        ProjectCreateReq(name="测试项目", type="unknown")


def test_project_material_store_save_list_and_delete(tmp_path):
    from stores.json.project_material_store import ProjectMaterialAsset, ProjectMaterialStore

    store = ProjectMaterialStore(tmp_path / "data")
    asset = ProjectMaterialAsset(
        id=store.new_id(),
        project_id="proj-1",
        asset_type="image",
        group_type="image",
        title="海报主视觉",
        created_by="tester",
        source_message_id="chat-1",
    )

    store.save(asset)
    items = store.list_by_project("proj-1")

    assert len(items) == 1
    assert items[0].title == "海报主视觉"
    assert store.get("proj-1", asset.id) is not None
    assert store.delete("proj-1", asset.id) is True
    assert store.list_by_project("proj-1") == []


def test_project_studio_export_store_save_list_and_get(tmp_path):
    from stores.json.project_studio_export_store import (
        ProjectStudioExportJob,
        ProjectStudioExportStore,
    )

    store = ProjectStudioExportStore(tmp_path / "data")
    job = ProjectStudioExportJob(
        id=store.new_id(),
        project_id="proj-1",
        title="正式导出 1080p",
        export_format="mp4-h264",
        export_resolution="1080p",
        aspect_ratio="16:9",
        timeline_duration_seconds=18,
        clip_count=3,
        timeline_payload={"clips": [{"id": "clip-1", "durationSeconds": 6}]},
        error_details={"kind": "unit_test", "reason": "persisted"},
        created_by="tester",
    )

    store.save(job)
    items = store.list_by_project("proj-1")

    assert len(items) == 1
    assert items[0].title == "正式导出 1080p"
    assert items[0].error_details["kind"] == "unit_test"
    assert store.get("proj-1", job.id) is not None


def test_project_material_upload_route_stores_and_serves_file(tmp_path, monkeypatch):
    from core import config as core_config
    from core.deps import require_auth
    from core.server import create_app
    from stores import factory as store_factory
    from stores.json.project_store import ProjectConfig

    monkeypatch.setenv("CORE_STORE_BACKEND", "json")
    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()
    for proxy_name in ("project_store", "project_material_store", "role_store"):
        getattr(store_factory, proxy_name)._instance = None

    app = create_app()
    app.dependency_overrides[require_auth] = lambda: {"sub": "tester", "role": "admin"}
    store_factory.project_store.save(ProjectConfig(id="proj-upload", name="上传项目"))
    client = TestClient(app)

    response = client.post(
        "/api/projects/proj-upload/materials/upload",
        data={
            "asset_type": "image",
            "title": "主视觉海报",
            "summary": "首轮上传素材",
            "metadata": '{"source":"unit-test"}',
        },
        files={"file": ("poster.png", b"fake-png-bytes", "image/png")},
    )

    assert response.status_code == 200
    payload = response.json()
    item = payload["item"]
    assert item["title"] == "主视觉海报"
    assert item["source_type"] == "manual_upload"
    assert item["original_filename"] == "poster.png"
    assert item["file_size_bytes"] == len(b"fake-png-bytes")

    file_response = client.get(item["preview_url"])
    assert file_response.status_code == 200
    assert file_response.headers["content-type"].startswith("image/png")
    assert file_response.headers["content-disposition"].startswith("inline;")

    list_response = client.get("/api/projects/proj-upload/materials")
    assert list_response.status_code == 200
    assert len(list_response.json()["items"]) == 1

    file_response = client.get(item["content_url"])
    assert file_response.status_code == 200
    assert file_response.content == b"fake-png-bytes"
    assert file_response.headers["content-type"].startswith("image/png")

    delete_response = client.delete(f"/api/projects/proj-upload/materials/{item['id']}")
    assert delete_response.status_code == 200

    missing_response = client.get(item["content_url"])
    assert missing_response.status_code == 404


def test_project_material_file_route_supports_unicode_filename(tmp_path, monkeypatch):
    from core import config as core_config
    from core.deps import require_auth
    from core.server import create_app
    from stores import factory as store_factory
    from stores.json.project_store import ProjectConfig

    monkeypatch.setenv("CORE_STORE_BACKEND", "json")
    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()
    for proxy_name in ("project_store", "project_material_store", "role_store"):
        getattr(store_factory, proxy_name)._instance = None

    app = create_app()
    app.dependency_overrides[require_auth] = lambda: {"sub": "tester", "role": "admin"}
    store_factory.project_store.save(ProjectConfig(id="proj-audio", name="音频项目"))
    client = TestClient(app)

    upload_response = client.post(
        "/api/projects/proj-audio/materials/upload",
        data={
            "asset_type": "audio",
            "title": "中文文件名音频",
            "mime_type": "audio/mpeg",
        },
        files={"file": ("周杰伦 - 晴天.mp3", b"fake-mp3-bytes", "audio/mpeg")},
    )

    assert upload_response.status_code == 200
    item = upload_response.json()["item"]
    assert item["original_filename"] == "周杰伦 - 晴天.mp3"

    file_response = client.get(item["content_url"])
    assert file_response.status_code == 200
    assert file_response.content == b"fake-mp3-bytes"
    assert file_response.headers["content-type"].startswith("audio/mpeg")
    assert "filename*=UTF-8''%E5%91%A8%E6%9D%B0%E4%BC%A6%20-%20%E6%99%B4%E5%A4%A9.mp3" in (
        file_response.headers["content-disposition"]
    )


def test_project_material_video_upload_supports_cover_override(tmp_path, monkeypatch):
    from core import config as core_config
    from core.deps import require_auth
    from core.server import create_app
    from stores import factory as store_factory
    from stores.json.project_store import ProjectConfig

    monkeypatch.setenv("CORE_STORE_BACKEND", "json")
    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()
    for proxy_name in ("project_store", "project_material_store", "role_store"):
        getattr(store_factory, proxy_name)._instance = None

    app = create_app()
    app.dependency_overrides[require_auth] = lambda: {"sub": "tester", "role": "admin"}
    store_factory.project_store.save(ProjectConfig(id="proj-video", name="视频项目"))
    client = TestClient(app)

    response = client.post(
        "/api/projects/proj-video/materials/upload",
        data={
            "asset_type": "video",
            "title": "口播成片",
            "mime_type": "video/mp4",
            "cover_mime_type": "image/png",
            "metadata": '{"duration_seconds": 8}',
        },
        files={
            "file": ("clip.mp4", b"fake-video-bytes", "video/mp4"),
            "cover_file": ("cover.png", b"fake-cover-bytes", "image/png"),
        },
    )

    assert response.status_code == 200
    item = response.json()["item"]
    assert item["content_url"].endswith("/file")
    assert item["preview_url"].endswith("/cover")

    video_response = client.get(item["content_url"])
    assert video_response.status_code == 200
    assert video_response.content == b"fake-video-bytes"
    assert video_response.headers["content-type"].startswith("video/mp4")

    cover_response = client.get(item["preview_url"])
    assert cover_response.status_code == 200
    assert cover_response.content == b"fake-cover-bytes"
    assert cover_response.headers["content-type"].startswith("image/png")
    assert cover_response.headers["content-disposition"].startswith("inline;")

    replace_response = client.post(
        f"/api/projects/proj-video/materials/{item['id']}/cover",
        data={"cover_mime_type": "image/jpeg"},
        files={"cover_file": ("cover-2.jpg", b"second-cover", "image/jpeg")},
    )
    assert replace_response.status_code == 200
    updated_item = replace_response.json()["item"]
    assert updated_item["preview_url"].endswith("/cover")
    updated_cover_response = client.get(updated_item["preview_url"])
    assert updated_cover_response.status_code == 200
    assert updated_cover_response.content == b"second-cover"
    assert updated_cover_response.headers["content-type"].startswith("image/jpeg")


def test_project_studio_export_routes_create_list_cancel_and_retry(tmp_path, monkeypatch):
    from core import config as core_config
    from core.deps import require_auth
    from core.server import create_app
    from stores import factory as store_factory
    from stores.json.project_store import ProjectConfig
    from stores.json.project_studio_export_store import ProjectStudioExportJob

    monkeypatch.setenv("CORE_STORE_BACKEND", "json")
    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()
    for proxy_name in (
        "project_store",
        "project_material_store",
        "project_studio_export_store",
        "role_store",
    ):
        getattr(store_factory, proxy_name)._instance = None

    app = create_app()
    app.dependency_overrides[require_auth] = lambda: {"sub": "tester", "role": "admin"}
    store_factory.project_store.save(ProjectConfig(id="proj-studio", name="短片项目"))
    client = TestClient(app)

    create_response = client.post(
        "/api/projects/proj-studio/studio/exports",
        json={
            "title": "春季短片正式导出",
            "export_format": "mp4-h264",
            "export_resolution": "1080p",
            "aspect_ratio": "16:9",
            "timeline_payload": {
                "clips": [
                    {"id": "clip-1", "durationSeconds": 6},
                    {"id": "clip-2", "durationSeconds": 4},
                ],
                "summary": {"timelineDurationSeconds": 10, "clipCount": 2},
            },
            "audio_payload": {"tracks": []},
        },
    )

    assert create_response.status_code == 200
    create_payload = create_response.json()
    job = create_payload["job"]
    assert create_payload["status"] == "created"
    assert job["status"] == "queued"
    assert job["clip_count"] == 2
    assert job["timeline_duration_seconds"] == 10
    assert job["export_format_label"] == "MP4 (H.264)"
    assert job["timeline_payload"]["version"] == "studio-export-v2"
    assert job["timeline_payload"]["clips"][0]["duration_seconds"] == 6
    assert job["audio_payload"]["version"] == "studio-audio-v2"
    assert job["audio_payload"]["tracks"] == []

    list_response = client.get("/api/projects/proj-studio/studio/exports")
    assert list_response.status_code == 200
    assert len(list_response.json()["items"]) == 1

    store_factory.project_studio_export_store.save(
        ProjectStudioExportJob(
            id=store_factory.project_studio_export_store.new_id(),
            project_id="proj-studio",
            title="草稿记录",
            status="draft",
            source_type="studio_draft",
            export_format="mp4-h264",
            export_resolution="1080p",
            aspect_ratio="16:9",
            timeline_duration_seconds=10,
            clip_count=2,
            timeline_payload={"draft_snapshot": {"activeStep": "storyboard"}},
            created_by="tester",
        )
    )

    export_only_response = client.get(
        "/api/projects/proj-studio/studio/exports",
        params={"source_type": "studio_export"},
    )
    assert export_only_response.status_code == 200
    assert len(export_only_response.json()["items"]) == 1
    assert export_only_response.json()["items"][0]["source_type"] == "studio_export"

    draft_only_response = client.get(
        "/api/projects/proj-studio/studio/exports",
        params={"source_type": "studio_draft"},
    )
    assert draft_only_response.status_code == 200
    assert len(draft_only_response.json()["items"]) == 1
    assert draft_only_response.json()["items"][0]["source_type"] == "studio_draft"

    get_response = client.get(f"/api/projects/proj-studio/studio/exports/{job['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["job"]["id"] == job["id"]

    update_response = client.patch(
        f"/api/projects/proj-studio/studio/exports/{job['id']}",
        json={
            "status": "processing",
            "progress": 35,
            "started_at": "2026-03-21T10:00:00+00:00",
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["job"]["status"] == "processing"
    assert update_response.json()["job"]["progress"] == 35

    cancel_response = client.post(f"/api/projects/proj-studio/studio/exports/{job['id']}/cancel")
    assert cancel_response.status_code == 200
    assert cancel_response.json()["job"]["status"] == "canceled"

    delete_response = client.delete(f"/api/projects/proj-studio/studio/exports/{job['id']}")
    assert delete_response.status_code == 200
    assert delete_response.json()["status"] == "deleted"

    list_after_delete_response = client.get("/api/projects/proj-studio/studio/exports")
    assert list_after_delete_response.status_code == 200
    assert len(list_after_delete_response.json()["items"]) == 1
    assert list_after_delete_response.json()["items"][0]["source_type"] == "studio_draft"

    export_only_after_delete_response = client.get(
        "/api/projects/proj-studio/studio/exports",
        params={"source_type": "studio_export"},
    )
    assert export_only_after_delete_response.status_code == 200
    assert export_only_after_delete_response.json()["items"] == []

    failed_job = ProjectStudioExportJob(
        id=store_factory.project_studio_export_store.new_id(),
        project_id="proj-studio",
        title="失败任务",
        status="failed",
        export_format="mp4-h264",
        export_resolution="720p",
        aspect_ratio="16:9",
        timeline_duration_seconds=8,
        clip_count=1,
        timeline_payload={"clips": [{"id": "clip-failed", "durationSeconds": 8}]},
        attempt_count=1,
        created_by="tester",
    )
    store_factory.project_studio_export_store.save(failed_job)

    retry_response = client.post(
        f"/api/projects/proj-studio/studio/exports/{failed_job.id}/retry"
    )
    assert retry_response.status_code == 200
    retried_job = retry_response.json()["job"]
    assert retried_job["status"] == "queued"
    assert retried_job["retry_of_job_id"] == failed_job.id
    assert retried_job["attempt_count"] == 2


def test_project_studio_export_route_supports_v2_payload(tmp_path, monkeypatch):
    from core import config as core_config
    from core.deps import require_auth
    from core.server import create_app
    from stores import factory as store_factory
    from stores.json.project_store import ProjectConfig

    monkeypatch.setenv("CORE_STORE_BACKEND", "json")
    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()
    for proxy_name in (
        "project_store",
        "project_material_store",
        "project_studio_export_store",
        "role_store",
    ):
        getattr(store_factory, proxy_name)._instance = None

    app = create_app()
    app.dependency_overrides[require_auth] = lambda: {"sub": "tester", "role": "admin"}
    store_factory.project_store.save(ProjectConfig(id="proj-studio-v2", name="短片项目 V2"))
    client = TestClient(app)

    create_response = client.post(
        "/api/projects/proj-studio-v2/studio/exports",
        json={
            "title": "V2 导出",
            "export_format": "mp4-h264",
            "export_resolution": "1080p",
            "aspect_ratio": "16:9",
            "timeline_payload": {
                "version": "studio-export-v2",
                "summary": {"title": "V2 导出", "timelineDurationSeconds": 8, "clipCount": 1},
                "clips": [
                    {
                        "id": "clip-v2-1",
                        "type": "video",
                        "title": "开场",
                        "durationSeconds": 8,
                        "startSeconds": 0,
                        "asset_id": "asset-clip-v2",
                        "storage_path": "proj-studio-v2/asset-clip-v2/final.mp4",
                        "content_url": "/api/projects/proj-studio-v2/materials/asset-clip-v2/file",
                        "mime_type": "video/mp4",
                        "original_filename": "final.mp4",
                        "source_type": "project_material",
                    }
                ],
            },
            "audio_payload": {
                "version": "studio-audio-v2",
                "mixer": {
                    "video_volume": 0.25,
                    "voice_volume": 0.9,
                    "bgm_volume": 0.6,
                },
                "tracks": [
                    {
                        "id": "bgm-v2-1",
                        "kind": "bgm",
                        "title": "背景音乐",
                        "startSeconds": 0,
                        "durationSeconds": 8,
                        "storage_path": "proj-studio-v2/studio-audio/bgm.mp3",
                        "mime_type": "audio/mpeg",
                        "original_filename": "bgm.mp3",
                        "volume": 0.6,
                    }
                ],
            },
        },
    )

    assert create_response.status_code == 200
    job = create_response.json()["job"]
    assert job["timeline_payload"]["clips"][0]["asset_id"] == "asset-clip-v2"
    assert job["timeline_payload"]["clips"][0]["source_id"] == "asset-clip-v2"
    assert job["audio_payload"]["mixer"]["video_volume"] == 0.25
    assert job["audio_payload"]["mixer"]["voice_volume"] == 0.9
    assert job["audio_payload"]["mixer"]["bgm_volume"] == 0.6
    assert job["audio_payload"]["tracks"][0]["segments"][0]["duration_seconds"] == 8
    assert job["audio_payload"]["tracks"][0]["volume"] == 0.6


def test_project_studio_export_route_preserves_zero_audio_volume(tmp_path, monkeypatch):
    from core import config as core_config
    from core.deps import require_auth
    from core.server import create_app
    from stores import factory as store_factory
    from stores.json.project_store import ProjectConfig

    monkeypatch.setenv("CORE_STORE_BACKEND", "json")
    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()
    for proxy_name in (
        "project_store",
        "project_material_store",
        "project_studio_export_store",
        "role_store",
    ):
        getattr(store_factory, proxy_name)._instance = None

    app = create_app()
    app.dependency_overrides[require_auth] = lambda: {"sub": "tester", "role": "admin"}
    store_factory.project_store.save(ProjectConfig(id="proj-studio-zero-volume", name="短片项目静音测试"))
    client = TestClient(app)

    create_response = client.post(
        "/api/projects/proj-studio-zero-volume/studio/exports",
        json={
            "title": "静音导出",
            "timeline_payload": {
                "version": "studio-export-v2",
                "summary": {"title": "静音导出", "timelineDurationSeconds": 6, "clipCount": 1},
                "clips": [
                    {
                        "id": "clip-zero-volume",
                        "type": "video",
                        "title": "片段",
                        "durationSeconds": 6,
                        "startSeconds": 0,
                        "content_url": "https://cdn.example.com/clip.mp4",
                        "mime_type": "video/mp4",
                        "source_type": "external_url",
                    }
                ],
            },
            "audio_payload": {
                "version": "studio-audio-v2",
                "tracks": [
                    {
                        "id": "voice-zero-volume",
                        "kind": "voice",
                        "title": "旁白",
                        "startSeconds": 0,
                        "durationSeconds": 6,
                        "content_url": "https://cdn.example.com/voice.mp3",
                        "mime_type": "audio/mpeg",
                        "volume": 0,
                    }
                ],
            },
        },
    )

    assert create_response.status_code == 200
    job = create_response.json()["job"]
    assert job["audio_payload"]["tracks"][0]["volume"] == 0
    assert job["audio_payload"]["tracks"][0]["segments"][0]["volume"] == 0


def test_project_studio_model_sources_and_generation_routes(tmp_path, monkeypatch):
    from core import config as core_config
    from core.deps import require_auth
    from core.server import create_app
    from stores import factory as store_factory
    from stores.json.project_store import ProjectConfig

    class FakeLlmService:
        def __init__(self):
            self.responses = [
                {
                    "content": json.dumps(
                        {
                            "roles": [
                                {"name": "林夏", "status": "detected", "summary": "执行秘密任务的主角"}
                            ],
                            "scenes": [
                                {"name": "街角咖啡馆", "status": "detected", "summary": "清晨会面的关键场景"}
                            ],
                            "props": [
                                {"name": "旧录像带", "status": "pending", "summary": "推动剧情的线索道具"}
                            ],
                        },
                        ensure_ascii=False,
                    )
                },
                {
                    "content": json.dumps(
                        {
                            "storyboards": [
                                {
                                    "title": "咖啡馆外景建立",
                                    "duration_seconds": 8,
                                    "summary": "晨光下的城市与咖啡馆外观"
                                },
                                {
                                    "title": "主角入场特写",
                                    "duration_seconds": 7,
                                    "summary": "主角带着任务推门进入"
                                },
                            ]
                        },
                        ensure_ascii=False,
                    )
                },
            ]

        def list_providers(self, enabled_only=False, owner_username="", include_all=False, include_shared=False):
            return [
                {
                    "id": "provider-studio",
                    "name": "Studio Provider",
                    "models": ["gpt-4.1", "gpt-4o-mini"],
                    "default_model": "gpt-4.1",
                    "enabled": True,
                    "is_default": True,
                }
            ]

        def get_provider_raw(self, provider_id, owner_username="", include_all=False, include_shared=False):
            if provider_id != "provider-studio":
                return None
            return {
                "id": "provider-studio",
                "name": "Studio Provider",
                "models": ["gpt-4.1", "gpt-4o-mini"],
                "default_model": "gpt-4.1",
                "enabled": True,
                "base_url": "https://example.com/v1",
                "api_key": "test",
            }

        async def chat_completion(self, provider_id, model_name, messages, temperature=0.2, max_tokens=1024, timeout=45):
            assert provider_id == "provider-studio"
            assert model_name in {"gpt-4.1", "gpt-4o-mini"}
            assert isinstance(messages, list) and messages
            return self.responses.pop(0)

    monkeypatch.setenv("CORE_STORE_BACKEND", "json")
    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()
    for proxy_name in (
        "project_store",
        "project_material_store",
        "project_studio_export_store",
        "role_store",
    ):
        getattr(store_factory, proxy_name)._instance = None
    fake_llm_service = FakeLlmService()
    monkeypatch.setattr(
        "services.llm_provider_service.get_llm_provider_service",
        lambda: fake_llm_service,
    )

    app = create_app()
    app.dependency_overrides[require_auth] = lambda: {"sub": "tester", "role": "admin"}
    store_factory.project_store.save(ProjectConfig(id="proj-studio-models", name="短片模型项目"))
    client = TestClient(app)

    sources_response = client.get("/api/projects/proj-studio-models/studio/model-sources")
    assert sources_response.status_code == 200
    sources_payload = sources_response.json()
    assert sources_payload["default_provider_id"] == "provider-studio"
    assert sources_payload["default_model_name"] == "gpt-4.1"
    assert sources_payload["providers"][0]["models"] == ["gpt-4.1", "gpt-4o-mini"]

    extraction_response = client.post(
        "/api/projects/proj-studio-models/studio/extractions",
        json={
            "provider_id": "provider-studio",
            "model_name": "gpt-4.1",
            "focus_kind": "role",
            "duration": "5秒",
            "quality": "高清 (1080p)",
            "script_content": "主角在清晨前往咖啡馆执行秘密任务。",
            "styles": ["电影超写实"],
            "chapters": [
                {
                    "id": "chapter-1",
                    "title": "第一章",
                    "content": "主角在清晨前往咖啡馆执行秘密任务。",
                }
            ],
        },
    )
    assert extraction_response.status_code == 200
    extraction_payload = extraction_response.json()
    assert extraction_payload["provider_id"] == "provider-studio"
    assert extraction_payload["model_name"] == "gpt-4.1"
    assert {item["kind"] for item in extraction_payload["items"]} == {"role", "scene", "prop"}

    storyboard_response = client.post(
        "/api/projects/proj-studio-models/studio/storyboards/generate",
        json={
            "provider_id": "provider-studio",
            "model_name": "gpt-4.1",
            "chapter_id": "chapter-1",
            "chapter_title": "第一章",
            "chapter_content": "主角在清晨前往咖啡馆执行秘密任务。",
            "duration": "8秒",
            "quality": "高清 (1080p)",
            "sfx": False,
            "styles": ["电影超写实"],
            "elements": [
                {"kind": "role", "name": "林夏"},
                {"kind": "scene", "name": "街角咖啡馆"},
            ],
        },
    )
    assert storyboard_response.status_code == 200
    storyboard_payload = storyboard_response.json()
    assert storyboard_payload["provider_id"] == "provider-studio"
    assert storyboard_payload["model_name"] == "gpt-4.1"
    assert len(storyboard_payload["items"]) == 2
    assert storyboard_payload["items"][0]["chapterId"] == "chapter-1"
    assert storyboard_payload["items"][0]["durationLocked"] is True


def test_project_studio_export_route_rejects_duplicated_clip_ids(tmp_path, monkeypatch):
    from core import config as core_config
    from core.deps import require_auth
    from core.server import create_app
    from stores import factory as store_factory
    from stores.json.project_store import ProjectConfig

    monkeypatch.setenv("CORE_STORE_BACKEND", "json")
    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()
    for proxy_name in ("project_store", "project_studio_export_store", "role_store"):
        getattr(store_factory, proxy_name)._instance = None

    app = create_app()
    app.dependency_overrides[require_auth] = lambda: {"sub": "tester", "role": "admin"}
    store_factory.project_store.save(ProjectConfig(id="proj-studio-dup", name="短片项目重复"))
    client = TestClient(app)

    response = client.post(
        "/api/projects/proj-studio-dup/studio/exports",
        json={
            "timeline_payload": {
                "clips": [
                    {"id": "clip-1", "durationSeconds": 3},
                    {"id": "clip-1", "durationSeconds": 5},
                ]
            }
        },
    )

    assert response.status_code == 400
    assert "duplicated id" in response.json()["detail"]


def test_project_studio_export_route_rejects_unknown_audio_bind_clip_id(tmp_path, monkeypatch):
    from core import config as core_config
    from core.deps import require_auth
    from core.server import create_app
    from stores import factory as store_factory
    from stores.json.project_store import ProjectConfig

    monkeypatch.setenv("CORE_STORE_BACKEND", "json")
    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()
    for proxy_name in ("project_store", "project_studio_export_store", "role_store"):
        getattr(store_factory, proxy_name)._instance = None

    app = create_app()
    app.dependency_overrides[require_auth] = lambda: {"sub": "tester", "role": "admin"}
    store_factory.project_store.save(ProjectConfig(id="proj-studio-bind", name="短片项目绑定"))
    client = TestClient(app)

    response = client.post(
        "/api/projects/proj-studio-bind/studio/exports",
        json={
            "timeline_payload": {
                "version": "studio-export-v2",
                "clips": [{"id": "clip-1", "type": "video", "durationSeconds": 6}],
            },
            "audio_payload": {
                "version": "studio-audio-v2",
                "tracks": [
                    {
                        "id": "voice-1",
                        "kind": "voice",
                        "durationSeconds": 3,
                        "bind_clip_id": "clip-missing",
                    }
                ],
            },
        },
    )

    assert response.status_code == 400
    assert "bind_clip_id not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_studio_export_service_marks_job_failed_when_ffmpeg_missing(tmp_path, monkeypatch):
    from services import studio_export_service as export_service
    from stores.json.project_material_store import ProjectMaterialStore
    from stores.json.project_store import ProjectConfig, ProjectStore
    from stores.json.project_studio_export_store import (
        ProjectStudioExportJob,
        ProjectStudioExportStore,
    )

    project_store = ProjectStore(tmp_path / "data")
    material_store = ProjectMaterialStore(tmp_path / "data")
    export_store = ProjectStudioExportStore(tmp_path / "data")
    project_store.save(ProjectConfig(id="proj-export", name="正式导出项目"))
    job = ProjectStudioExportJob(
        id=export_store.new_id(),
        project_id="proj-export",
        title="缺少 FFmpeg",
        export_format="mp4-h264",
        export_resolution="1080p",
        aspect_ratio="16:9",
        timeline_duration_seconds=10,
        clip_count=2,
        timeline_payload={"clips": [{"id": "clip-1", "durationSeconds": 6}, {"id": "clip-2", "durationSeconds": 4}]},
        created_by="tester",
    )
    export_store.save(job)
    monkeypatch.setattr(export_service.shutil, "which", lambda name: None)

    service = export_service.StudioExportBackgroundService(
        project_store=project_store,
        project_studio_export_store=export_store,
        project_material_store=material_store,
        api_data_dir=tmp_path / "api-data",
        poll_interval_seconds=2,
    )

    await service.run_pending_once()

    updated = export_store.get("proj-export", job.id)
    assert updated is not None
    assert updated.status == "failed"
    assert "FFmpeg" in updated.error_message
    assert material_store.list_by_project("proj-export") == []


@pytest.mark.asyncio
async def test_studio_export_service_saves_material_after_render(tmp_path, monkeypatch):
    from services import studio_export_service as export_service
    from stores.json.project_material_store import ProjectMaterialStore
    from stores.json.project_store import ProjectConfig, ProjectStore
    from stores.json.project_studio_export_store import (
        ProjectStudioExportJob,
        ProjectStudioExportStore,
    )

    project_store = ProjectStore(tmp_path / "data")
    material_store = ProjectMaterialStore(tmp_path / "data")
    export_store = ProjectStudioExportStore(tmp_path / "data")
    project_store.save(ProjectConfig(id="proj-export", name="正式导出项目"))
    job = ProjectStudioExportJob(
        id=export_store.new_id(),
        project_id="proj-export",
        title="春季成片",
        export_format="mp4-h264",
        export_resolution="720p",
        aspect_ratio="16:9",
        timeline_duration_seconds=8,
        clip_count=2,
        timeline_payload={
            "clips": [
                {"id": "clip-1", "title": "镜头一", "durationSeconds": 5},
                {"id": "clip-2", "title": "镜头二", "durationSeconds": 3},
            ]
        },
        audio_payload={
            "tracks": [
                {
                    "id": "audio-track-bgm",
                    "kind": "bgm",
                    "label": "BGM",
                    "segments": [
                        {
                            "id": "bgm-main",
                            "label": "全局背景音乐",
                            "startSeconds": 0,
                            "durationSeconds": 8,
                        }
                    ],
                }
            ]
        },
        created_by="tester",
    )
    export_store.save(job)
    monkeypatch.setattr(export_service.shutil, "which", lambda name: "/usr/bin/ffmpeg")

    service = export_service.StudioExportBackgroundService(
        project_store=project_store,
        project_studio_export_store=export_store,
        project_material_store=material_store,
        api_data_dir=tmp_path / "api-data",
        poll_interval_seconds=2,
    )

    async def fake_render_video(ffmpeg_bin, current_job, clips, duration_seconds, width, height, video_path):
        assert ffmpeg_bin == "/usr/bin/ffmpeg"
        assert current_job.id == job.id
        assert duration_seconds == 8
        assert width == 1280
        assert height == 720
        video_path.parent.mkdir(parents=True, exist_ok=True)
        video_path.write_bytes(b"fake-video")

    async def fake_render_cover(ffmpeg_bin, current_job, video_path, cover_path):
        assert ffmpeg_bin == "/usr/bin/ffmpeg"
        assert video_path.exists()
        cover_path.write_bytes(b"fake-cover")

    async def fake_render_audio(
        *,
        ffmpeg_bin,
        job,
        audio_tracks,
        duration_seconds,
        input_video_path,
        output_video_path,
    ):
        assert ffmpeg_bin == "/usr/bin/ffmpeg"
        assert job.id == current_job_id
        assert duration_seconds == 8
        assert len(audio_tracks) == 1
        assert input_video_path.exists()
        output_video_path.write_bytes(input_video_path.read_bytes())

    current_job_id = job.id
    monkeypatch.setattr(service, "_render_job_video", fake_render_video)
    monkeypatch.setattr(service, "_render_job_audio", fake_render_audio)
    monkeypatch.setattr(service, "_render_job_cover", fake_render_cover)

    await service.run_pending_once()

    updated = export_store.get("proj-export", job.id)
    assert updated is not None
    assert updated.status == "succeeded"
    assert updated.result_asset_id

    assets = material_store.list_by_project("proj-export")
    assert len(assets) == 1
    asset = assets[0]
    assert asset.id == updated.result_asset_id
    assert asset.source_type == "studio_export"
    assert asset.metadata["artifact_source"] == "studio-export-final"
    assert asset.metadata["render_backend"] == "ffmpeg"
    assert asset.metadata["render_mode"] == "timeline_local_media_v2"
    assert asset.metadata["render_audio_track_count"] == 1
    assert asset.metadata["render_audio_mode"] == "procedural_v1"
    assert asset.preview_url.endswith("/cover")
    assert asset.content_url.endswith("/file")
    assert (tmp_path / "api-data" / "project-material-files" / asset.metadata["storage_path"]).exists()

@pytest.mark.asyncio
async def test_studio_export_service_prefers_local_material_files_for_render(tmp_path):
    from services import studio_export_service as export_service
    from stores.json.project_material_store import ProjectMaterialAsset, ProjectMaterialStore
    from stores.json.project_studio_export_store import ProjectStudioExportStore
    from stores.json.project_store import ProjectStore

    material_store = ProjectMaterialStore(tmp_path / "data")
    export_store = ProjectStudioExportStore(tmp_path / "data")
    project_store = ProjectStore(tmp_path / "data")
    api_data_dir = tmp_path / "api-data"
    material_root = api_data_dir / "project-material-files" / "proj-export" / "asset-video"
    material_root.mkdir(parents=True, exist_ok=True)
    video_path = material_root / "clip.mp4"
    video_path.write_bytes(b"video-bytes")
    image_root = api_data_dir / "project-material-files" / "proj-export" / "asset-image"
    image_root.mkdir(parents=True, exist_ok=True)
    image_path = image_root / "frame.png"
    image_path.write_bytes(b"image-bytes")
    material_store.save(
        ProjectMaterialAsset(
            id="asset-video",
            project_id="proj-export",
            asset_type="video",
            group_type="storyboard_video",
            title="视频素材",
            mime_type="video/mp4",
            created_by="tester",
            metadata={"storage_path": "proj-export/asset-video/clip.mp4"},
        )
    )
    material_store.save(
        ProjectMaterialAsset(
            id="asset-image",
            project_id="proj-export",
            asset_type="image",
            group_type="image",
            title="图片素材",
            mime_type="image/png",
            created_by="tester",
            metadata={"storage_path": "proj-export/asset-image/frame.png"},
        )
    )

    service = export_service.StudioExportBackgroundService(
        project_store=project_store,
        project_studio_export_store=export_store,
        project_material_store=material_store,
        api_data_dir=api_data_dir,
        poll_interval_seconds=2,
    )

    temp_dir = tmp_path / "render-temp"
    video_source = await service._resolve_clip_render_source(
        "proj-export",
        {"source_type": "material", "source_id": "asset-video"},
        0,
        temp_dir,
    )
    image_source = await service._resolve_clip_render_source(
        "proj-export",
        {"source_type": "material", "source_id": "asset-image"},
        1,
        temp_dir,
    )
    fallback_source = await service._resolve_clip_render_source(
        "proj-export",
        {"source_type": "storyboard", "source_id": "storyboard-1"},
        2,
        temp_dir,
    )

    assert video_source["mode"] == "video"
    assert video_source["asset_id"] == "asset-video"
    assert video_source["path"] == str(video_path)
    assert image_source["mode"] == "image"
    assert image_source["asset_id"] == "asset-image"
    assert image_source["path"] == str(image_path)
    assert fallback_source["mode"] == "color"
    assert fallback_source["fallback"] is True


@pytest.mark.asyncio
async def test_studio_export_service_supports_data_url_material_render_source(tmp_path):
    from services import studio_export_service as export_service
    from stores.json.project_material_store import ProjectMaterialAsset, ProjectMaterialStore
    from stores.json.project_studio_export_store import ProjectStudioExportStore
    from stores.json.project_store import ProjectStore

    material_store = ProjectMaterialStore(tmp_path / "data")
    export_store = ProjectStudioExportStore(tmp_path / "data")
    project_store = ProjectStore(tmp_path / "data")
    api_data_dir = tmp_path / "api-data"
    material_store.save(
        ProjectMaterialAsset(
            id="asset-remote-image",
            project_id="proj-export",
            asset_type="image",
            group_type="image",
            title="远端图片素材",
            mime_type="image/png",
            created_by="tester",
            content_url="data:image/png;base64,aW1hZ2UtYnl0ZXM=",
        )
    )

    service = export_service.StudioExportBackgroundService(
        project_store=project_store,
        project_studio_export_store=export_store,
        project_material_store=material_store,
        api_data_dir=api_data_dir,
        poll_interval_seconds=2,
    )

    temp_dir = tmp_path / "render-temp"
    source = await service._resolve_clip_render_source(
        "proj-export",
        {"id": "clip-remote", "source_type": "material", "source_id": "asset-remote-image"},
        0,
        temp_dir,
    )

    assert source["mode"] == "image"
    assert source["asset_id"] == "asset-remote-image"
    assert source["remote"] is True
    assert source["url"].startswith("data:image/png")
    assert Path(source["path"]).exists()
    assert Path(source["path"]).read_bytes() == b"image-bytes"


@pytest.mark.asyncio
async def test_studio_export_service_marks_missing_project_material_as_unresolved(tmp_path):
    from services import studio_export_service as export_service
    from stores.json.project_material_store import ProjectMaterialStore
    from stores.json.project_studio_export_store import ProjectStudioExportStore
    from stores.json.project_store import ProjectStore

    service = export_service.StudioExportBackgroundService(
        project_store=ProjectStore(tmp_path / "data"),
        project_studio_export_store=ProjectStudioExportStore(tmp_path / "data"),
        project_material_store=ProjectMaterialStore(tmp_path / "data"),
        api_data_dir=tmp_path / "api-data",
        poll_interval_seconds=2,
    )

    source = await service._resolve_clip_render_source(
        "proj-export",
        {
            "id": "clip-missing-material",
            "title": "缺失素材片段",
            "type": "video",
            "source_type": "project_material",
            "asset_id": "asset-missing",
        },
        0,
        tmp_path / "render-temp",
    )

    assert source["mode"] == "color"
    assert source["fallback"] is True
    assert source["unresolved_source"] is True
    assert "asset-missing" in source["reason"]


@pytest.mark.asyncio
async def test_studio_export_service_prefers_asset_source_over_direct_storage_path(tmp_path):
    from services import studio_export_service as export_service
    from stores.json.project_material_store import ProjectMaterialAsset, ProjectMaterialStore
    from stores.json.project_studio_export_store import ProjectStudioExportStore
    from stores.json.project_store import ProjectStore

    material_store = ProjectMaterialStore(tmp_path / "data")
    export_store = ProjectStudioExportStore(tmp_path / "data")
    project_store = ProjectStore(tmp_path / "data")
    api_data_dir = tmp_path / "api-data"

    asset_path = (
        api_data_dir
        / "project-material-files"
        / "proj-export"
        / "asset-video"
        / "asset.mp4"
    )
    direct_path = (
        api_data_dir
        / "project-material-files"
        / "proj-export"
        / "direct"
        / "direct.mp4"
    )
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    direct_path.parent.mkdir(parents=True, exist_ok=True)
    asset_path.write_bytes(b"asset-video")
    direct_path.write_bytes(b"direct-video")

    material_store.save(
        ProjectMaterialAsset(
            id="asset-video",
            project_id="proj-export",
            asset_type="video",
            group_type="storyboard_video",
            title="素材视频",
            mime_type="video/mp4",
            created_by="tester",
            metadata={"storage_path": "proj-export/asset-video/asset.mp4"},
        )
    )

    service = export_service.StudioExportBackgroundService(
        project_store=project_store,
        project_studio_export_store=export_store,
        project_material_store=material_store,
        api_data_dir=api_data_dir,
        poll_interval_seconds=2,
    )

    source = await service._resolve_clip_render_source(
        "proj-export",
        {
            "id": "clip-priority",
            "type": "video",
            "source_type": "project_material",
            "asset_id": "asset-video",
            "storage_path": "proj-export/direct/direct.mp4",
            "mime_type": "video/mp4",
            "original_filename": "asset.mp4",
        },
        0,
        tmp_path / "render-temp",
    )

    assert source["mode"] == "video"
    assert source["asset_id"] == "asset-video"
    assert source["path"] == str(asset_path.resolve())


@pytest.mark.asyncio
async def test_studio_export_service_prefers_content_url_over_preview_url(tmp_path):
    from services import studio_export_service as export_service
    from stores.json.project_material_store import ProjectMaterialStore
    from stores.json.project_studio_export_store import ProjectStudioExportStore
    from stores.json.project_store import ProjectStore

    service = export_service.StudioExportBackgroundService(
        project_store=ProjectStore(tmp_path / "data"),
        project_studio_export_store=ProjectStudioExportStore(tmp_path / "data"),
        project_material_store=ProjectMaterialStore(tmp_path / "data"),
        api_data_dir=tmp_path / "api-data",
        poll_interval_seconds=2,
    )

    content_url = "data:image/png;base64,Y29udGVudC1ieXRlcw=="
    preview_url = "data:image/png;base64,cHJldmlldy1ieXRlcw=="
    source = await service._resolve_clip_render_source(
        "proj-export",
        {
            "id": "clip-direct-urls",
            "type": "image",
            "source_type": "external_url",
            "content_url": content_url,
            "preview_url": preview_url,
            "mime_type": "image/png",
            "original_filename": "frame.png",
        },
        0,
        tmp_path / "render-temp",
    )

    assert source["mode"] == "image"
    assert source["remote"] is True
    assert source["url"] == content_url
    assert Path(source["path"]).read_bytes() == b"content-bytes"


@pytest.mark.asyncio
async def test_studio_export_service_fails_job_when_required_material_source_is_missing(tmp_path, monkeypatch):
    from services import studio_export_service as export_service
    from stores.json.project_material_store import ProjectMaterialStore
    from stores.json.project_studio_export_store import (
        ProjectStudioExportJob,
        ProjectStudioExportStore,
    )
    from stores.json.project_store import ProjectConfig, ProjectStore

    project_store = ProjectStore(tmp_path / "data")
    material_store = ProjectMaterialStore(tmp_path / "data")
    export_store = ProjectStudioExportStore(tmp_path / "data")
    project_store.save(ProjectConfig(id="proj-export", name="正式导出项目"))
    job = ProjectStudioExportJob(
        id=export_store.new_id(),
        project_id="proj-export",
        title="缺失真实素材",
        export_format="mp4-h264",
        export_resolution="1080p",
        aspect_ratio="16:9",
        timeline_duration_seconds=6,
        clip_count=1,
        timeline_payload={
            "clips": [
                {
                    "id": "clip-missing-material",
                    "title": "主镜头",
                    "durationSeconds": 6,
                    "type": "video",
                    "source_type": "project_material",
                    "asset_id": "asset-missing",
                }
            ]
        },
        created_by="tester",
    )
    export_store.save(job)
    monkeypatch.setattr(export_service.shutil, "which", lambda name: "/usr/bin/ffmpeg")

    service = export_service.StudioExportBackgroundService(
        project_store=project_store,
        project_studio_export_store=export_store,
        project_material_store=material_store,
        api_data_dir=tmp_path / "api-data",
        poll_interval_seconds=2,
    )

    await service.run_pending_once()

    updated = export_store.get("proj-export", job.id)
    assert updated is not None
    assert updated.status == "failed"
    assert "主镜头" in updated.error_message
    assert "asset-missing" in updated.error_message
    assert updated.error_details["kind"] == "unresolved_visual_source"
    assert updated.error_details["clip_id"] == "clip-missing-material"
    assert updated.error_details["asset_id"] == "asset-missing"


def test_normalize_audio_tracks_filters_invalid_segments():
    from services.studio_export_service import _normalize_audio_tracks
    from stores.json.project_studio_export_store import ProjectStudioExportJob

    job = ProjectStudioExportJob(
        id="studio-export-audio",
        project_id="proj-export",
        title="音轨测试",
        audio_payload={
            "tracks": [
                {
                    "id": "audio-track-voice",
                    "kind": "voice",
                    "label": "人声",
                    "segments": [
                        {
                            "id": "voice-1",
                            "startSeconds": 0,
                            "durationSeconds": 4,
                            "storage_path": "proj-export/studio-audio/voice-1.mp3",
                            "mime_type": "audio/mpeg",
                            "original_filename": "voice-1.mp3",
                        },
                        {"id": "voice-2", "startSeconds": 5, "durationSeconds": 0},
                    ],
                },
                {
                    "id": "audio-track-bgm",
                    "kind": "bgm",
                    "label": "背景音乐",
                    "segments": [
                        {"id": "bgm-1", "startSeconds": 0, "durationSeconds": 10},
                    ],
                },
            ]
        },
    )

    tracks = _normalize_audio_tracks(job)

    assert len(tracks) == 2
    assert tracks[0]["kind"] == "voice"
    assert len(tracks[0]["segments"]) == 1
    assert tracks[0]["segments"][0]["storage_path"] == "proj-export/studio-audio/voice-1.mp3"
    assert tracks[0]["segments"][0]["mime_type"] == "audio/mpeg"
    assert tracks[1]["kind"] == "bgm"
    assert tracks[1]["segments"][0]["duration_seconds"] == 10


def test_normalize_timeline_clips_preserves_direct_source_fields():
    from services.studio_export_service import _normalize_timeline_clips
    from stores.json.project_studio_export_store import ProjectStudioExportJob

    job = ProjectStudioExportJob(
        id="studio-export-video",
        project_id="proj-export",
        title="片段源测试",
        timeline_payload={
            "clips": [
                {
                    "id": "clip-1",
                    "title": "真实视频片段",
                    "durationSeconds": 6,
                    "sourceType": "storyboard",
                    "contentUrl": "https://cdn.example.com/final.mp4",
                    "mimeType": "video/mp4",
                    "storagePath": "proj-export/storyboards/final.mp4",
                    "originalFilename": "final.mp4",
                }
            ]
        },
    )

    clips = _normalize_timeline_clips(job)

    assert len(clips) == 1
    assert clips[0]["source_url"] == "https://cdn.example.com/final.mp4"
    assert clips[0]["mime_type"] == "video/mp4"
    assert clips[0]["storage_path"] == "proj-export/storyboards/final.mp4"
    assert clips[0]["original_filename"] == "final.mp4"


def test_normalize_audio_tracks_supports_v2_flat_tracks():
    from services.studio_export_service import _normalize_audio_tracks
    from stores.json.project_studio_export_store import ProjectStudioExportJob

    job = ProjectStudioExportJob(
        id="studio-export-audio-v2",
        project_id="proj-export",
        title="音轨 V2 测试",
        audio_payload={
            "version": "studio-audio-v2",
            "tracks": [
                {
                    "id": "bgm-v2",
                    "kind": "bgm",
                    "title": "背景音乐",
                    "startSeconds": 0,
                    "durationSeconds": 12,
                    "storage_path": "proj-export/studio-audio/bgm.mp3",
                    "mime_type": "audio/mpeg",
                    "original_filename": "bgm.mp3",
                    "volume": 0.6,
                }
            ],
        },
    )

    tracks = _normalize_audio_tracks(job)

    assert len(tracks) == 1
    assert tracks[0]["kind"] == "bgm"
    assert tracks[0]["segments"][0]["duration_seconds"] == 12
    assert tracks[0]["segments"][0]["storage_path"] == "proj-export/studio-audio/bgm.mp3"
    assert tracks[0]["volume"] == 0.6


def test_normalize_audio_tracks_preserves_zero_volume():
    from services.studio_export_service import _normalize_audio_tracks
    from stores.json.project_studio_export_store import ProjectStudioExportJob

    job = ProjectStudioExportJob(
        id="studio-export-audio-zero-volume",
        project_id="proj-export",
        title="音轨静音测试",
        audio_payload={
            "version": "studio-audio-v2",
            "tracks": [
                {
                    "id": "voice-zero",
                    "kind": "voice",
                    "title": "旁白",
                    "startSeconds": 0,
                    "durationSeconds": 10,
                    "content_url": "https://cdn.example.com/voice.mp3",
                    "mime_type": "audio/mpeg",
                    "volume": 0,
                }
            ],
        },
    )

    tracks = _normalize_audio_tracks(job)

    assert len(tracks) == 1
    assert tracks[0]["volume"] == 0
    assert tracks[0]["segments"][0]["volume"] == 0


def test_normalize_audio_tracks_uses_mixer_volume_fallback():
    from services.studio_export_service import _normalize_audio_tracks
    from stores.json.project_studio_export_store import ProjectStudioExportJob

    job = ProjectStudioExportJob(
        id="studio-export-audio-mixer-fallback",
        project_id="proj-export",
        title="音轨 mixer 兜底测试",
        audio_payload={
            "version": "studio-audio-v2",
            "mixer": {
                "voice_volume": 0.35,
            },
            "tracks": [
                {
                    "id": "voice-mixer",
                    "kind": "voice",
                    "title": "旁白",
                    "startSeconds": 0,
                    "durationSeconds": 10,
                    "content_url": "https://cdn.example.com/voice.mp3",
                    "mime_type": "audio/mpeg",
                }
            ],
        },
    )

    tracks = _normalize_audio_tracks(job)

    assert len(tracks) == 1
    assert tracks[0]["volume"] == 0.35
    assert tracks[0]["segments"][0]["volume"] == 0.35


@pytest.mark.asyncio
async def test_render_job_audio_uses_video_mixer_volume(tmp_path, monkeypatch):
    from services import studio_export_service as export_service
    from stores.json.project_material_store import ProjectMaterialStore
    from stores.json.project_studio_export_store import ProjectStudioExportJob, ProjectStudioExportStore
    from stores.json.project_store import ProjectStore

    service = export_service.StudioExportBackgroundService(
        project_store=ProjectStore(tmp_path / "data"),
        project_studio_export_store=ProjectStudioExportStore(tmp_path / "data"),
        project_material_store=ProjectMaterialStore(tmp_path / "data"),
        api_data_dir=tmp_path / "api-data",
        poll_interval_seconds=2,
    )

    job = ProjectStudioExportJob(
        id="studio-export-video-mixer",
        project_id="proj-export",
        title="视频音量 mixer 测试",
        audio_payload={
            "version": "studio-audio-v2",
            "mixer": {
                "video_volume": 0.2,
                "voice_volume": 0.7,
            },
        },
    )

    captured: dict[str, list[str]] = {}

    async def fake_resolve_audio_segment_source(**kwargs):
        return {"kind": "file", "value": str(tmp_path / "voice.mp3")}

    async def fake_run_ffmpeg_command(_job, command):
        captured["command"] = command

    monkeypatch.setattr(service, "_resolve_audio_segment_source", fake_resolve_audio_segment_source)
    monkeypatch.setattr(service, "_run_ffmpeg_command", fake_run_ffmpeg_command)

    await service._render_job_audio(
        ffmpeg_bin="ffmpeg",
        job=job,
        audio_tracks=[
            {
                "kind": "voice",
                "segments": [
                    {
                        "id": "voice-1",
                        "start_seconds": 0,
                        "duration_seconds": 5,
                        "volume": 0.7,
                    }
                ],
            }
        ],
        duration_seconds=5,
        input_video_path=tmp_path / "input.mp4",
        output_video_path=tmp_path / "output.mp4",
    )

    filter_index = captured["command"].index("-filter_complex") + 1
    assert "[0:a:0]aresample=44100,volume=0.2[base]" in captured["command"][filter_index]


@pytest.mark.asyncio
async def test_resolve_audio_segment_source_prefers_segment_level_voice_file(tmp_path):
    from services import studio_export_service as export_service
    from stores.json.project_material_store import ProjectMaterialStore
    from stores.json.project_studio_export_store import ProjectStudioExportStore
    from stores.json.project_store import ProjectStore

    api_data_dir = tmp_path / "api-data"
    track_audio_path = (
        api_data_dir
        / "project-material-files"
        / "proj-export"
        / "studio-audio"
        / "track.mp3"
    )
    segment_audio_path = (
        api_data_dir
        / "project-material-files"
        / "proj-export"
        / "studio-audio"
        / "segment.mp3"
    )
    track_audio_path.parent.mkdir(parents=True, exist_ok=True)
    track_audio_path.write_bytes(b"track-audio")
    segment_audio_path.write_bytes(b"segment-audio")

    service = export_service.StudioExportBackgroundService(
        project_store=ProjectStore(tmp_path / "data"),
        project_studio_export_store=ProjectStudioExportStore(tmp_path / "data"),
        project_material_store=ProjectMaterialStore(tmp_path / "data"),
        api_data_dir=api_data_dir,
        poll_interval_seconds=2,
    )

    source = await service._resolve_audio_segment_source(
        track={
            "kind": "voice",
            "storage_path": "proj-export/studio-audio/track.mp3",
            "mime_type": "audio/mpeg",
            "original_filename": "track.mp3",
        },
        segment={
            "id": "voice-1",
            "storage_path": "proj-export/studio-audio/segment.mp3",
            "mime_type": "audio/mpeg",
            "original_filename": "segment.mp3",
        },
        kind="voice",
        track_index=1,
        segment_index=1,
        temp_dir=tmp_path / "render-temp",
    )

    assert source["kind"] == "file"
    assert source["value"] == str(segment_audio_path.resolve())


@pytest.mark.asyncio
async def test_resolve_audio_segment_source_supports_internal_audio_api_url(tmp_path):
    from services import studio_export_service as export_service
    from stores.json.project_material_store import ProjectMaterialStore
    from stores.json.project_studio_export_store import ProjectStudioExportStore
    from stores.json.project_store import ProjectStore

    api_data_dir = tmp_path / "api-data"
    audio_path = (
        api_data_dir
        / "project-material-files"
        / "proj-export"
        / "studio-audio"
        / "voice-1"
        / "voice.mp3"
    )
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"voice-audio")

    service = export_service.StudioExportBackgroundService(
        project_store=ProjectStore(tmp_path / "data"),
        project_studio_export_store=ProjectStudioExportStore(tmp_path / "data"),
        project_material_store=ProjectMaterialStore(tmp_path / "data"),
        api_data_dir=api_data_dir,
        poll_interval_seconds=2,
    )

    source = await service._resolve_audio_segment_source(
        track={
            "kind": "voice",
            "mime_type": "audio/mpeg",
            "original_filename": "voice.mp3",
        },
        segment={
            "id": "voice-1",
            "source_url": "http://localhost:5173/api/projects/proj-export/studio/audio/voice-1/file?token=test",
            "mime_type": "audio/mpeg",
            "original_filename": "voice.mp3",
        },
        kind="voice",
        track_index=1,
        segment_index=1,
        temp_dir=tmp_path / "render-temp",
    )

    assert source["kind"] == "file"
    assert source["value"] == str(audio_path.resolve())


@pytest.mark.asyncio
async def test_studio_export_service_supports_direct_clip_storage_path(tmp_path):
    from services import studio_export_service as export_service
    from stores.json.project_material_store import ProjectMaterialStore
    from stores.json.project_studio_export_store import ProjectStudioExportStore
    from stores.json.project_store import ProjectStore

    api_data_dir = tmp_path / "api-data"
    clip_path = (
        api_data_dir
        / "project-material-files"
        / "proj-export"
        / "storyboards"
        / "clip.mp4"
    )
    clip_path.parent.mkdir(parents=True, exist_ok=True)
    clip_path.write_bytes(b"video-bytes")

    service = export_service.StudioExportBackgroundService(
        project_store=ProjectStore(tmp_path / "data"),
        project_studio_export_store=ProjectStudioExportStore(tmp_path / "data"),
        project_material_store=ProjectMaterialStore(tmp_path / "data"),
        api_data_dir=api_data_dir,
        poll_interval_seconds=2,
    )

    source = await service._resolve_clip_render_source(
        "proj-export",
        {
            "id": "clip-direct-local",
            "source_type": "storyboard",
            "storage_path": "proj-export/storyboards/clip.mp4",
            "mime_type": "video/mp4",
            "original_filename": "clip.mp4",
        },
        0,
        tmp_path / "render-temp",
    )

    assert source["mode"] == "video"
    assert source["path"] == str(clip_path.resolve())
    assert source["fallback"] is False


@pytest.mark.asyncio
async def test_studio_export_service_supports_direct_clip_remote_source(tmp_path):
    from pathlib import Path

    from services import studio_export_service as export_service
    from stores.json.project_material_store import ProjectMaterialStore
    from stores.json.project_studio_export_store import ProjectStudioExportStore
    from stores.json.project_store import ProjectStore

    service = export_service.StudioExportBackgroundService(
        project_store=ProjectStore(tmp_path / "data"),
        project_studio_export_store=ProjectStudioExportStore(tmp_path / "data"),
        project_material_store=ProjectMaterialStore(tmp_path / "data"),
        api_data_dir=tmp_path / "api-data",
        poll_interval_seconds=2,
    )

    source = await service._resolve_clip_render_source(
        "proj-export",
        {
            "id": "clip-direct-remote",
            "source_type": "storyboard",
            "source_url": "data:image/png;base64,aW1hZ2UtYnl0ZXM=",
            "mime_type": "image/png",
            "original_filename": "frame.png",
        },
        0,
        tmp_path / "render-temp",
    )

    assert source["mode"] == "image"
    assert source["remote"] is True
    assert source["url"].startswith("data:image/png")
    assert Path(source["path"]).read_bytes() == b"image-bytes"


@pytest.mark.asyncio
async def test_studio_export_service_supports_internal_material_api_url(tmp_path):
    from services import studio_export_service as export_service
    from stores.json.project_material_store import ProjectMaterialAsset, ProjectMaterialStore
    from stores.json.project_studio_export_store import ProjectStudioExportStore
    from stores.json.project_store import ProjectStore

    api_data_dir = tmp_path / "api-data"
    material_store = ProjectMaterialStore(tmp_path / "data")
    video_path = (
        api_data_dir
        / "project-material-files"
        / "proj-export"
        / "asset-video"
        / "clip.mp4"
    )
    video_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(b"video-bytes")
    material_store.save(
        ProjectMaterialAsset(
            id="asset-video",
            project_id="proj-export",
            asset_type="video",
            group_type="storyboard_video",
            title="素材视频",
            mime_type="video/mp4",
            created_by="tester",
            metadata={"storage_path": "proj-export/asset-video/clip.mp4"},
        )
    )

    service = export_service.StudioExportBackgroundService(
        project_store=ProjectStore(tmp_path / "data"),
        project_studio_export_store=ProjectStudioExportStore(tmp_path / "data"),
        project_material_store=material_store,
        api_data_dir=api_data_dir,
        poll_interval_seconds=2,
    )

    source = await service._resolve_clip_render_source(
        "proj-export",
        {
            "id": "clip-internal-url",
            "source_type": "storyboard",
            "content_url": "http://127.0.0.1:5173/api/projects/proj-export/materials/asset-video/file?token=test",
            "mime_type": "video/mp4",
            "original_filename": "clip.mp4",
        },
        0,
        tmp_path / "render-temp",
    )

    assert source["mode"] == "video"
    assert source["fallback"] is False
    assert source["path"] == str(video_path.resolve())


def test_agent_orchestrator_extract_media_artifacts_supports_video_results():
    from services import agent_orchestrator as orchestrator

    artifacts = orchestrator._extract_media_artifacts(
        {
            "assets": [
                {
                    "asset_type": "video",
                    "title": "短片结果",
                    "preview_url": "https://cdn.example.com/cover.png",
                    "content_url": "https://cdn.example.com/final.mp4",
                    "mime_type": "video/mp4",
                }
            ]
        },
        default_title="视频工具",
    )

    assert len(artifacts) == 1
    assert artifacts[0]["asset_type"] == "video"
    assert artifacts[0]["preview_url"] == "https://cdn.example.com/cover.png"
    assert artifacts[0]["content_url"] == "https://cdn.example.com/final.mp4"
    assert artifacts[0]["mime_type"] == "video/mp4"


def test_save_chat_media_artifacts_to_materials_supports_video(tmp_path, monkeypatch):
    from routers import projects as projects_router
    from stores.json.project_material_store import ProjectMaterialStore

    store = ProjectMaterialStore(tmp_path / "data")
    monkeypatch.setattr(projects_router, "project_material_store", store)

    saved = projects_router._save_chat_media_artifacts_to_materials(
        project_id="proj-media",
        username="tester",
        chat_session_id="chat-session-1",
        source_message_id="msg-1",
        artifacts=[
            {
                "asset_type": "video",
                "title": "AI 成片",
                "preview_url": "https://cdn.example.com/cover.png",
                "content_url": "https://cdn.example.com/final.mp4",
                "mime_type": "video/mp4",
            }
        ],
        tool_name="video_tool",
    )

    assert len(saved) == 1
    assert saved[0].asset_type == "video"
    assert saved[0].group_type == "storyboard_video"
    assert saved[0].source_type == "ai_generated"
    assert saved[0].preview_url == "https://cdn.example.com/cover.png"
    assert saved[0].content_url == "https://cdn.example.com/final.mp4"

    duplicated = projects_router._save_chat_media_artifacts_to_materials(
        project_id="proj-media",
        username="tester",
        chat_session_id="chat-session-1",
        source_message_id="msg-1",
        artifacts=[
            {
                "asset_type": "video",
                "title": "AI 成片",
                "preview_url": "https://cdn.example.com/cover.png",
                "content_url": "https://cdn.example.com/final.mp4",
                "mime_type": "video/mp4",
            }
        ],
        tool_name="video_tool",
    )

    assert duplicated == []


@pytest.mark.asyncio
async def test_local_connector_llm_adapter_streams_chunks(monkeypatch):
    from services import local_connector_service as connector_svc

    async def fake_stream(connector, **kwargs):
        assert connector == "connector-1"
        assert kwargs["model_name"] == "local-model"
        yield {"content": "A"}
        yield {"tool_calls": [{"id": "call-1"}]}

    monkeypatch.setattr(connector_svc, "chat_completion_stream_via_connector", fake_stream)

    adapter = connector_svc.LocalConnectorLlmAdapter("connector-1")
    chunks = []
    async for chunk in adapter.chat_completion_stream(
        provider_id="local-connector:test",
        model_name="local-model",
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.2,
        max_tokens=256,
        timeout=30,
        tools=[{"type": "function"}],
    ):
        chunks.append(chunk)

    assert chunks == [{"content": "A"}, {"tool_calls": [{"id": "call-1"}]}]


@pytest.mark.asyncio
async def test_tool_executor_routes_local_connector_run_command(monkeypatch):
    from services import local_connector_service as connector_svc
    from services.tool_executor import ToolExecutor

    captured: dict = {}

    async def fake_run(connector, **kwargs):
        captured["connector"] = connector
        captured["kwargs"] = kwargs
        return {"ok": True, "stdout": "PASS"}

    monkeypatch.setattr(connector_svc, "run_connector_command", fake_run)

    connector = object()
    executor = ToolExecutor(
        "test-proj",
        "test-emp",
        local_connector=connector,
        local_connector_workspace_path="/tmp/workspace",
        local_connector_sandbox_mode="workspace-write",
    )

    result = await executor._execute_tool(
        "local_connector_run_command",
        {"command": "pytest -q", "cwd": "web-admin/api", "timeout_sec": 30},
    )

    assert result["ok"] is True
    assert captured["connector"] is connector
    assert captured["kwargs"]["workspace_path"] == "/tmp/workspace"
    assert captured["kwargs"]["command"] == "pytest -q"
    assert captured["kwargs"]["cwd"] == "web-admin/api"
    assert captured["kwargs"]["timeout_sec"] == 30


@pytest.mark.asyncio
async def test_conversation_manager_logic():
    """测试 ConversationManager 压缩逻辑"""
    from services.conversation_manager import ConversationManager

    redis_mock = MagicMock()
    manager = ConversationManager(redis_mock)

    messages = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好，有什么可以帮助你的？"},
    ]
    summary = await manager._generate_summary(messages)

    assert "user:" in summary
    assert "assistant:" in summary


def test_usage_key_delete_compatibility_allows_legacy_owners():
    from routers.usage import _can_delete_key_record

    assert _can_delete_key_record({"created_by": "tester"}, "tester") is True
    assert _can_delete_key_record({"created_by": ""}, "tester") is True
    assert _can_delete_key_record({"created_by": "unknown"}, "tester") is True
    assert _can_delete_key_record({"created_by": "system-external-agent"}, "tester") is True
    assert _can_delete_key_record({"created_by": "someone-else"}, "tester") is False
    assert _can_delete_key_record(None, "tester") is False


def test_llm_provider_service_allows_shared_users_on_enabled_list(monkeypatch):
    from services.llm_provider_service import LlmProviderService
    import stores.factory as factory_mod

    class DummyStore:
        def __init__(self):
            self.providers = [
                {
                    "id": "p-owned",
                    "name": "Owned Provider",
                    "enabled": True,
                    "models": ["gpt-4.1"],
                    "default_model": "gpt-4.1",
                    "owner_username": "alice",
                    "shared_usernames": [],
                },
                {
                    "id": "p-shared",
                    "name": "Shared Provider",
                    "enabled": True,
                    "models": ["gpt-4.1-mini"],
                    "default_model": "gpt-4.1-mini",
                    "owner_username": "alice",
                    "shared_usernames": ["bob"],
                },
                {
                    "id": "p-disabled",
                    "name": "Disabled Provider",
                    "enabled": False,
                    "models": ["gpt-4o"],
                    "default_model": "gpt-4o",
                    "owner_username": "alice",
                    "shared_usernames": ["bob"],
                },
            ]

        def delete_provider(self, provider_id):
            return True

        def list_providers(self, include_secret=False, enabled_only=False):
            providers = self.providers
            if enabled_only:
                providers = [item for item in providers if bool(item.get("enabled", True))]
            return [dict(item) for item in providers]

        def get_provider(self, provider_id, include_secret=False):
            for item in self.providers:
                if item["id"] == provider_id:
                    return dict(item)
            return None

    service = LlmProviderService(DummyStore())
    monkeypatch.setattr(
        factory_mod,
        "user_store",
        type(
            "DummyUserStore",
            (),
            {"get": staticmethod(lambda username: type("User", (), {"default_ai_provider_id": ""})())},
        )(),
    )

    manageable = service.list_providers(
        enabled_only=False,
        owner_username="bob",
        include_all=False,
        include_shared=False,
    )
    visible = service.list_providers(
        enabled_only=True,
        owner_username="bob",
        include_all=False,
        include_shared=True,
    )

    assert manageable == []
    assert [item["id"] for item in visible] == ["p-shared"]
    assert visible[0]["is_default"] is True


def test_llm_provider_service_blocks_shared_user_from_editing_provider():
    from services.llm_provider_service import LlmProviderService

    class DummyStore:
        def __init__(self):
            self.providers = {
                "p-shared": {
                    "id": "p-shared",
                    "name": "Shared Provider",
                    "enabled": True,
                    "models": ["gpt-4.1-mini"],
                    "default_model": "gpt-4.1-mini",
                    "owner_username": "alice",
                    "shared_usernames": ["bob"],
                }
            }

        def delete_provider(self, provider_id):
            return provider_id in self.providers

        def list_providers(self, include_secret=False, enabled_only=False):
            return [dict(item) for item in self.providers.values()]

        def get_provider(self, provider_id, include_secret=False):
            item = self.providers.get(provider_id)
            return dict(item) if item else None

        def patch_provider(self, provider_id, updates):
            item = self.providers.get(provider_id)
            if item is None:
                return None
            item.update(updates)
            return dict(item)

    service = LlmProviderService(DummyStore())

    with pytest.raises(LookupError):
        service.update_provider(
            "p-shared",
            {"name": "Mutated"},
            owner_username="bob",
            include_all=False,
        )


def test_llm_provider_service_normalizes_model_configs(monkeypatch):
    from services.llm_provider_service import LlmProviderService
    import stores.factory as factory_mod

    class DummyStore:
        def __init__(self):
            self.providers = {}

        def delete_provider(self, provider_id):
            return self.providers.pop(provider_id, None) is not None

        def create_provider(self, payload):
            provider = {
                "id": "p-model-config",
                **payload,
                "created_at": "2026-03-24T00:00:00Z",
                "updated_at": "2026-03-24T00:00:00Z",
            }
            self.providers[provider["id"]] = dict(provider)
            return dict(provider)

        def get_provider(self, provider_id, include_secret=False):
            provider = self.providers.get(provider_id)
            if provider is None:
                return None
            result = dict(provider)
            if not include_secret:
                result["api_key_masked"] = "sk-***"
                result["api_key"] = ""
            return result

        def patch_provider(self, provider_id, updates):
            current = self.providers.get(provider_id)
            if current is None:
                return None
            current.update(updates)
            self.providers[provider_id] = current
            return dict(current)

        def list_providers(self, include_secret=False, enabled_only=False):
            items = list(self.providers.values())
            if enabled_only:
                items = [item for item in items if bool(item.get("enabled", True))]
            results = []
            for item in items:
                provider = dict(item)
                if not include_secret:
                    provider["api_key_masked"] = "sk-***"
                    provider["api_key"] = ""
                results.append(provider)
            return results

    monkeypatch.setattr(
        factory_mod,
        "user_store",
        type(
            "DummyUserStore",
            (),
            {"get": staticmethod(lambda username: type("User", (), {"default_ai_provider_id": ""})())},
        )(),
    )

    service = LlmProviderService(DummyStore())
    created = service.create_provider(
        {
            "name": "Structured Provider",
            "base_url": "https://example.com/v1",
            "api_key": "sk-test",
            "model_configs": [
                {"name": "gpt-4o", "model_type": "multimodal_chat"},
                {"name": "seedream-3.0", "model_type": "image_generation"},
            ],
            "default_model": "seedream-3.0",
            "enabled": True,
        },
        owner_username="alice",
    )

    assert created["models"] == ["gpt-4o", "seedream-3.0"]
    assert created["model_configs"] == [
        {"name": "gpt-4o", "model_type": "multimodal_chat"},
        {"name": "seedream-3.0", "model_type": "image_generation"},
    ]
    assert service.get_model_config(created, "seedream-3.0")["chat_parameter_mode"] == "image"

    updated = service.update_provider(
        "p-model-config",
        {
            "model_configs": [
                {"name": "wanx2.1", "model_type": "video_generation"},
            ],
            "default_model": "wanx2.1",
        },
        owner_username="alice",
        include_all=False,
    )

    assert updated["models"] == ["wanx2.1"]
    assert updated["model_configs"] == [
        {"name": "wanx2.1", "model_type": "video_generation"},
    ]


def test_dictionary_catalog_includes_llm_model_types():
    from services.dictionary_catalog import get_dictionary_definition

    definition = get_dictionary_definition("llm_model_types")

    assert definition is not None
    assert definition["default_value"] == "text_generation"
    assert any(item["id"] == "image_generation" for item in definition["options"])


def test_dictionary_catalog_includes_llm_chat_parameter_dictionaries():
    from services.dictionary_catalog import get_dictionary_definition

    image_resolution = get_dictionary_definition("llm_image_resolutions")
    video_duration = get_dictionary_definition("llm_video_duration_seconds")

    assert image_resolution is not None
    assert image_resolution["default_value"] == "1024x1024"
    assert any(item["id"] == "1536x1024" for item in image_resolution["options"])
    assert any(item["route"] == "/projects/chat" for item in image_resolution["usage_refs"])

    assert video_duration is not None
    assert video_duration["default_value"] == "5"
    assert any(item["id"] == "10" for item in video_duration["options"])


def test_permission_catalog_includes_dictionary_management():
    from core.role_permissions import permission_catalog

    catalog = permission_catalog()
    menu_items = next(
        (group["items"] for group in catalog["groups"] if group["group"] == "menu"),
        [],
    )

    assert any(item["key"] == "menu.system.dictionaries" for item in menu_items)


def test_dictionary_catalog_applies_system_override(monkeypatch):
    import services.dictionary_catalog as catalog

    class DummyConfig:
        dictionaries = {
            "llm_model_types": {
                "key": "llm_model_types",
                "label": "模型能力类型",
                "default_value": "image_generation",
                "options": [
                    {
                        "id": "image_generation",
                        "label": "图片生成",
                        "description": "图片能力",
                        "chat_parameter_mode": "image",
                    }
                ],
            }
        }

    monkeypatch.setattr(
        catalog,
        "system_config_store",
        type("DummyStore", (), {"get_global": staticmethod(lambda: DummyConfig())})(),
    )

    definition = catalog.get_dictionary_definition("llm_model_types")

    assert definition is not None
    assert definition["label"] == "模型能力类型"
    assert definition["default_value"] == "image_generation"
    assert definition["options"] == [
        {
            "id": "image_generation",
            "label": "图片生成",
            "description": "图片能力",
            "chat_parameter_mode": "image",
        }
    ]


def test_dictionary_catalog_lists_custom_dictionary(monkeypatch):
    import services.dictionary_catalog as catalog

    class DummyConfig:
        dictionaries = {
            "image_styles": {
                "key": "image_styles",
                "label": "图片风格",
                "description": "用于图片风格切换",
                "default_value": "photorealistic",
                "options": [
                    {
                        "id": "photorealistic",
                        "label": "写实",
                        "description": "逼真照片风格",
                    }
                ],
            }
        }

    monkeypatch.setattr(
        catalog,
        "system_config_store",
        type("DummyStore", (), {"get_global": staticmethod(lambda: DummyConfig())})(),
    )

    items = catalog.list_dictionaries()
    custom = next((item for item in items if item["key"] == "image_styles"), None)
    definition = catalog.get_dictionary_definition("image_styles")

    assert custom is not None
    assert custom["builtin"] is False
    assert custom["option_count"] == 1
    assert definition is not None
    assert definition["builtin"] is False
    assert definition["default_value"] == "photorealistic"


def test_llm_chat_parameter_catalog_applies_dictionary_overrides(monkeypatch):
    import services.llm_chat_parameter_catalog as catalog

    dictionary_defaults = {
        "llm_image_resolutions": "2048x2048",
        "llm_video_duration_seconds": "12",
    }
    dictionary_options = {
        "llm_image_resolutions": [
            {"id": "1024x1024", "label": "标准"},
            {"id": "2048x2048", "label": "超清"},
        ],
        "llm_video_duration_seconds": [
            {"id": "5", "label": "5 秒"},
            {"id": "12", "label": "12 秒"},
        ],
    }

    monkeypatch.setattr(
        catalog,
        "get_dictionary_default_value",
        lambda dictionary_key, fallback="": dictionary_defaults.get(dictionary_key, fallback),
    )
    monkeypatch.setattr(
        catalog,
        "list_dictionary_options",
        lambda dictionary_key: dictionary_options.get(dictionary_key, []),
    )

    assert catalog.get_chat_parameter_default_value("image_resolution") == "2048x2048"
    assert catalog.normalize_chat_parameter_value("image_resolution", "bad-value") == "2048x2048"
    assert catalog.get_chat_parameter_default_value("video_duration_seconds") == 12
    assert catalog.normalize_chat_parameter_value("video_duration_seconds", "12") == 12
    assert catalog.normalize_chat_parameter_value("video_duration_seconds", "999") == 12


def test_dictionary_routes_support_custom_dictionary_crud(tmp_path, monkeypatch):
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
    ):
        getattr(store_factory, proxy_name)._instance = None

    app = create_app()
    app.dependency_overrides[require_auth] = lambda: {"sub": "tester", "role": "admin"}
    client = TestClient(app)

    create_response = client.post(
        "/api/dictionaries",
        json={
            "key": "image_styles",
            "label": "图片风格",
            "description": "图片生成风格字典",
            "default_value": "photorealistic",
            "options": [
                {
                    "id": "photorealistic",
                    "label": "写实",
                    "description": "逼真照片风格",
                }
            ],
        },
    )

    assert create_response.status_code == 200
    created = create_response.json()["dictionary"]
    assert created["key"] == "image_styles"
    assert created["builtin"] is False
    assert created["default_value"] == "photorealistic"

    list_response = client.get("/api/dictionaries")
    assert list_response.status_code == 200
    assert any(
        item["key"] == "image_styles" and item["builtin"] is False
        for item in list_response.json()["items"]
    )

    update_response = client.put(
        "/api/dictionaries/image_styles",
        json={
            "label": "图片风格",
            "description": "更新后的图片风格字典",
            "default_value": "anime",
            "options": [
                {
                    "id": "photorealistic",
                    "label": "写实",
                    "description": "逼真照片风格",
                },
                {
                    "id": "anime",
                    "label": "动漫",
                    "description": "二次元插画风格",
                },
            ],
        },
    )

    assert update_response.status_code == 200
    updated = update_response.json()["dictionary"]
    assert updated["default_value"] == "anime"
    assert len(updated["options"]) == 2

    detail_response = client.get("/api/dictionaries/image_styles")
    assert detail_response.status_code == 200
    assert detail_response.json()["description"] == "更新后的图片风格字典"

    delete_response = client.delete("/api/dictionaries/image_styles")
    assert delete_response.status_code == 200
    assert delete_response.json()["status"] == "deleted"

    missing_response = client.get("/api/dictionaries/image_styles")
    assert missing_response.status_code == 404


def test_system_config_patch_supports_dictionaries(tmp_path, monkeypatch):
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
    ):
        getattr(store_factory, proxy_name)._instance = None

    app = create_app()
    app.dependency_overrides[require_auth] = lambda: {"sub": "tester", "role": "admin"}
    client = TestClient(app)

    response = client.patch(
        "/api/system-config",
        json={
            "dictionaries": {
                "llm_image_styles": {
                    "key": "llm_image_styles",
                    "label": "图片风格",
                    "description": "图片生成风格字典",
                    "default_value": "anime",
                    "options": [
                        {
                            "id": "anime",
                            "label": "动漫",
                            "description": "二次元插画风格",
                        },
                        {
                            "id": "realistic",
                            "label": "写实",
                            "description": "真实摄影风格",
                        },
                    ],
                }
            }
        },
    )

    assert response.status_code == 200
    payload = response.json()["config"]["dictionaries"]
    assert payload["llm_image_styles"]["default_value"] == "anime"
    assert len(payload["llm_image_styles"]["options"]) == 2

    detail_response = client.get("/api/dictionaries/llm_image_styles")
    assert detail_response.status_code == 200
    assert detail_response.json()["default_value"] == "anime"


def test_filter_project_tools_by_names_keeps_tools_when_empty_selection():
    from routers.projects import _filter_project_tools_by_names

    tools = [
        {"tool_name": "query_project_members"},
        {"tool_name": "search_project_context"},
    ]

    assert _filter_project_tools_by_names(tools, [], explicit_filter=True) == tools
    assert _filter_project_tools_by_names(tools, None, explicit_filter=True) == tools
    assert _filter_project_tools_by_names(
        tools,
        ["query_project_members"],
        explicit_filter=True,
    ) == [{"tool_name": "query_project_members"}]


def test_extract_user_questions_from_query_payload_includes_context():
    from services.dynamic_mcp_audit import extract_user_questions_from_rpc_payload

    payload = {
        "method": "tools/call",
        "params": {
            "name": "search_ids",
            "arguments": {
                "keyword": "当前项目",
                "project_id": "proj-1",
                "employee_id": "emp-1",
            },
        },
    }

    method_name, tool_name, questions, context = extract_user_questions_from_rpc_payload(payload)

    assert method_name == "tools/call"
    assert tool_name == "search_ids"
    assert questions == ["当前项目"]
    assert context["project_id"] == "proj-1"
    assert context["employee_id"] == "emp-1"


def test_extract_user_questions_from_lookup_only_query_payload_skips_fallback():
    from services.dynamic_mcp_audit import extract_user_questions_from_rpc_payload

    payload = {
        "method": "tools/call",
        "params": {
            "name": "get_manual_content",
            "arguments": {
                "project_id": "proj-1",
            },
        },
    }

    method_name, tool_name, questions, context = extract_user_questions_from_rpc_payload(payload)

    assert method_name == "tools/call"
    assert tool_name == "get_manual_content"
    assert questions == []
    assert context["project_id"] == "proj-1"


def test_save_auto_query_memory_writes_to_active_project_members(tmp_path, monkeypatch):
    from services import dynamic_mcp_audit as audit_svc
    from stores.json.employee_store import EmployeeConfig, EmployeeStore
    from stores.json.project_store import ProjectConfig, ProjectMember, ProjectStore

    data_dir = tmp_path / "data"
    employee_store = EmployeeStore(data_dir)
    project_store = ProjectStore(data_dir)
    employee_store.save(EmployeeConfig(id="emp-1", name="员工一", created_by="tester"))
    employee_store.save(EmployeeConfig(id="emp-2", name="员工二", created_by="tester"))
    project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    project_store.upsert_member(ProjectMember(project_id="proj-1", employee_id="emp-1", enabled=True))
    project_store.upsert_member(ProjectMember(project_id="proj-1", employee_id="emp-2", enabled=False))

    saved_memories = []
    memory_store = MagicMock()
    memory_store.recent.side_effect = lambda employee_id, limit: []
    memory_store.new_id.side_effect = ["mem-1", "mem-2"]
    memory_store.save.side_effect = saved_memories.append

    monkeypatch.setattr(audit_svc, "employee_store", employee_store)
    monkeypatch.setattr(audit_svc, "project_store", project_store)
    monkeypatch.setattr(audit_svc, "memory_store", memory_store)

    audit_svc.save_auto_query_memory(
        ["查询项目手册 proj-1"],
        "mcp:tools/call:get_manual_content",
        project_id="proj-1",
    )

    assert len(saved_memories) == 1
    assert saved_memories[0].employee_id == "emp-1"
    assert saved_memories[0].project_name == "项目一"
    assert saved_memories[0].purpose_tags == (
        "auto-capture",
        "user-question",
        "mcp:tools/call:get_manual_content",
    )


def test_project_detail_runtime_includes_full_config_and_member_lists(tmp_path, monkeypatch):
    from services import dynamic_mcp_context as context_svc
    from stores.json.employee_store import EmployeeConfig, EmployeeStore
    from stores.json.project_store import ProjectConfig, ProjectMember, ProjectStore, ProjectUserMember

    data_dir = tmp_path / "data"
    employee_store = EmployeeStore(data_dir)
    project_store = ProjectStore(data_dir)

    employee_store.save(
        EmployeeConfig(
            id="emp-1",
            name="员工一",
            created_by="tester",
            style_hints=["严谨"],
            auto_evolve=False,
        )
    )
    project_store.save(
        ProjectConfig(
            id="proj-1",
            name="项目一",
            workspace_path="/tmp/workspace",
            chat_settings={"auto_use_tools": False, "model_name": "demo-model"},
        )
    )
    project_store.upsert_member(
        ProjectMember(project_id="proj-1", employee_id="emp-1", role="owner", enabled=True)
    )
    project_store.upsert_user_member(
        ProjectUserMember(project_id="proj-1", username="tester", role="owner", enabled=True)
    )

    monkeypatch.setattr(context_svc, "employee_store", employee_store)
    monkeypatch.setattr(context_svc, "project_store", project_store)

    project_detail = context_svc.get_project_detail_runtime("proj-1")
    employee_detail = context_svc.get_project_employee_detail_runtime("proj-1", "emp-1")

    assert project_detail["id"] == "proj-1"
    assert project_detail["chat_settings"]["auto_use_tools"] is False
    assert project_detail["member_count"] == 1
    assert project_detail["user_count"] == 1
    assert project_detail["members"][0]["employee_id"] == "emp-1"
    assert project_detail["user_members"][0]["username"] == "tester"

    assert employee_detail["project_id"] == "proj-1"
    assert employee_detail["member"]["role"] == "owner"
    assert employee_detail["employee_exists"] is True
    assert employee_detail["employee"]["id"] == "emp-1"
    assert employee_detail["employee"]["style_hints"] == ["严谨"]
    assert employee_detail["employee"]["auto_evolve"] is False
    assert "rule_ids" in employee_detail["employee"]


def test_project_runtime_builtin_tools_include_and_invoke_full_detail_helpers(monkeypatch):
    from services import dynamic_mcp_runtime as runtime_svc

    monkeypatch.setattr(runtime_svc, "_build_project_proxy_specs", lambda project_id: ({}, {}))

    tool_names = {
        item["tool_name"]
        for item in runtime_svc.list_project_proxy_tools_runtime("proj-test", "")
    }

    monkeypatch.setattr(
        runtime_svc,
        "get_project_detail_runtime",
        lambda project_id: {"id": project_id, "chat_settings": {"auto_use_tools": True}},
    )
    monkeypatch.setattr(
        runtime_svc,
        "get_project_employee_detail_runtime",
        lambda project_id, employee_id: {
            "project_id": project_id,
            "employee_id": employee_id,
            "employee_exists": True,
        },
    )

    project_result = runtime_svc.invoke_project_skill_tool_runtime("proj-test", "get_project_detail")
    employee_result = runtime_svc.invoke_project_skill_tool_runtime(
        "proj-test",
        "get_project_employee_detail",
        args={"employee_id": "emp-9"},
    )

    assert "get_project_detail" in tool_names
    assert "get_project_employee_detail" in tool_names
    assert project_result["tool_name"] == "get_project_detail"
    assert project_result["id"] == "proj-test"
    assert project_result["chat_settings"]["auto_use_tools"] is True
    assert employee_result["tool_name"] == "get_project_employee_detail"
    assert employee_result["employee_id"] == "emp-9"
    assert employee_result["employee_exists"] is True


def test_project_mcp_proxy_tool_invocation_passes_project_root_and_api_key(monkeypatch, tmp_path):
    from services import dynamic_mcp_apps_project as project_mcp_svc

    registered_tools: dict[str, object] = {}
    captured: dict = {}

    class FakeMcp:
        def tool(self, name=None, description=None):
            def decorator(fn):
                registered_tools[name or fn.__name__] = fn
                return fn

            return decorator

        def resource(self, *_args, **_kwargs):
            def decorator(fn):
                return fn

            return decorator

        def sse_app(self):
            return "sse-app"

        def streamable_http_app(self):
            return "http-app"

    class FakeCtx:
        def __init__(self, value):
            self.value = value

        def get(self, default=""):
            return self.value if self.value is not None else default

    spec = {
        "employee_id": "emp-1",
        "skill_id": "skill-db",
        "skill_name": "数据库助手",
        "entry_name": "query-db",
        "script_type": "py",
        "script_path": "/tmp/query-db.py",
        "base_tool_name": "skill_db__query_db",
        "scoped_tool_name": "emp_1__skill_db__query_db",
        "description": "Proxy tool for skill-db:query-db",
    }

    monkeypatch.setattr(project_mcp_svc, "_new_mcp", lambda _service_name: FakeMcp())
    monkeypatch.setattr(project_mcp_svc, "_apply_mcp_arguments_compat", lambda app: app)
    monkeypatch.setattr(project_mcp_svc, "_DualTransportMcpApp", lambda sse_app, http_app: (sse_app, http_app))
    monkeypatch.setattr(
        project_mcp_svc,
        "_build_project_proxy_specs",
        lambda _project_id: ({spec["scoped_tool_name"]: spec}, {"emp-1": {spec["base_tool_name"]: spec}}),
    )
    monkeypatch.setattr(project_mcp_svc, "list_project_external_tools_runtime", lambda _project_id: [])

    def fake_execute(spec_item, **kwargs):
        captured["spec"] = spec_item
        captured["kwargs"] = kwargs
        return {"status": "ok"}

    monkeypatch.setattr(project_mcp_svc, "_execute_skill_proxy", fake_execute)

    project_mcp_svc.create_project_mcp(
        "proj-1",
        current_api_key_ctx=FakeCtx("api-key-123"),
        current_developer_name_ctx=FakeCtx("tester"),
        project_root=tmp_path,
        recall_limit=20,
    )

    result = registered_tools[spec["scoped_tool_name"]](args={"sql": "show tables"}, timeout_sec=15)

    assert result["status"] == "ok"
    assert captured["spec"] == spec
    assert captured["kwargs"]["project_root"] == tmp_path
    assert captured["kwargs"]["current_api_key"] == "api-key-123"
    assert captured["kwargs"]["employee_id"] == "emp-1"
    assert captured["kwargs"]["args"] == {"sql": "show tables"}
    assert captured["kwargs"]["timeout_sec"] == 15


def test_project_chat_store_truncate_messages_updates_session_snapshot(tmp_path):
    """截断聊天记录后应同步更新会话快照与消息计数"""
    from stores.json.project_chat_store import ProjectChatMessage, ProjectChatStore

    store = ProjectChatStore(tmp_path / "data")
    session = store.create_session("proj-test", "tester", title="新对话")

    store.append_message(
        ProjectChatMessage(
            id="msg-user-1",
            project_id="proj-test",
            username="tester",
            role="user",
            content="第一条问题",
            chat_session_id=session.id,
        )
    )
    store.append_message(
        ProjectChatMessage(
            id="msg-assistant-1",
            project_id="proj-test",
            username="tester",
            role="assistant",
            content="第一条回答",
            chat_session_id=session.id,
        )
    )
    store.append_message(
        ProjectChatMessage(
            id="msg-user-2",
            project_id="proj-test",
            username="tester",
            role="user",
            content="第二条问题",
            chat_session_id=session.id,
        )
    )
    store.append_message(
        ProjectChatMessage(
            id="msg-assistant-2",
            project_id="proj-test",
            username="tester",
            role="assistant",
            content="第二条回答",
            chat_session_id=session.id,
        )
    )

    removed = store.truncate_messages(
        "proj-test",
        "tester",
        "msg-user-2",
        session.id,
    )

    assert removed == 2
    messages = store.list_messages("proj-test", "tester", chat_session_id=session.id)
    assert [item.id for item in messages] == ["msg-user-1", "msg-assistant-1"]

    sessions = store.list_sessions("proj-test", "tester")
    assert len(sessions) == 1
    assert sessions[0].id == session.id
    assert sessions[0].preview == "第一条回答"
    assert sessions[0].message_count == 2


def test_project_chat_store_persists_videos_field(tmp_path):
    from stores.json.project_chat_store import ProjectChatMessage, ProjectChatStore

    store = ProjectChatStore(tmp_path / "data")
    session = store.create_session("proj-test", "tester", title="新对话")
    store.append_message(
        ProjectChatMessage(
            id="msg-video-1",
            project_id="proj-test",
            username="tester",
            role="assistant",
            content="已生成视频",
            chat_session_id=session.id,
            videos=["https://cdn.example.com/final.mp4"],
        )
    )

    messages = store.list_messages("proj-test", "tester", chat_session_id=session.id)
    assert len(messages) == 1
    assert messages[0].videos == ["https://cdn.example.com/final.mp4"]


def test_project_chat_store_keeps_full_history_without_auto_trim(tmp_path):
    """聊天记录不应因为条数过多被自动裁掉"""
    from stores.json.project_chat_store import ProjectChatMessage, ProjectChatStore

    store = ProjectChatStore(tmp_path / "data")
    session = store.create_session("proj-test", "tester", title="新对话")

    for index in range(1005):
        store.append_message(
            ProjectChatMessage(
                id=f"msg-{index}",
                project_id="proj-test",
                username="tester",
                role="user" if index % 2 == 0 else "assistant",
                content=f"消息 {index}",
                chat_session_id=session.id,
            )
        )

    messages = store.list_messages(
        "proj-test",
        "tester",
        limit=0,
        chat_session_id=session.id,
    )
    assert len(messages) == 1005
    assert messages[0].id == "msg-0"
    assert messages[-1].id == "msg-1004"


def test_project_chat_store_list_messages_supports_offset_pagination(tmp_path):
    """聊天记录应支持按最新消息向前分页读取"""
    from stores.json.project_chat_store import ProjectChatMessage, ProjectChatStore

    store = ProjectChatStore(tmp_path / "data")
    session = store.create_session("proj-test", "tester", title="新对话")

    for index in range(6):
        store.append_message(
            ProjectChatMessage(
                id=f"msg-{index}",
                project_id="proj-test",
                username="tester",
                role="user",
                content=f"消息 {index}",
                chat_session_id=session.id,
            )
        )

    latest = store.list_messages(
        "proj-test",
        "tester",
        limit=2,
        offset=0,
        chat_session_id=session.id,
    )
    previous = store.list_messages(
        "proj-test",
        "tester",
        limit=2,
        offset=2,
        chat_session_id=session.id,
    )
    oldest = store.list_messages(
        "proj-test",
        "tester",
        limit=2,
        offset=4,
        chat_session_id=session.id,
    )

    assert [item.id for item in latest] == ["msg-4", "msg-5"]
    assert [item.id for item in previous] == ["msg-2", "msg-3"]
    assert [item.id for item in oldest] == ["msg-0", "msg-1"]


def test_public_project_chat_settings_preserves_connector_configuration():
    """对话设置标准化后应保留连接器工作区配置。"""
    from routers import projects as projects_router

    settings = projects_router._public_project_chat_settings(
        {
            "chat_mode": "system",
            "connector_sandbox_mode": "workspace-write",
            "local_connector_id": "connector-1",
            "connector_workspace_path": "/tmp/workspace",
        }
    )

    assert settings["chat_mode"] == "system"
    assert settings["connector_sandbox_mode"] == "workspace-write"
    assert settings["local_connector_id"] == "connector-1"
    assert settings["connector_workspace_path"] == "/tmp/workspace"


def test_merge_project_chat_settings_overrides_keeps_persisted_connector_when_query_empty():
    """providers 接口在没有覆盖参数时，应保留已保存的连接器和工作区"""
    from routers import projects as projects_router

    merged = projects_router._merge_project_chat_settings_overrides(
        {
            "chat_mode": "system",
            "connector_sandbox_mode": "workspace-write",
            "local_connector_id": "connector-1",
            "connector_workspace_path": "/tmp/workspace",
        },
        local_connector_id="",
        connector_workspace_path="",
    )

    assert merged["chat_mode"] == "system"
    assert merged["connector_sandbox_mode"] == "workspace-write"
    assert merged["local_connector_id"] == "connector-1"
    assert merged["connector_workspace_path"] == "/tmp/workspace"


@pytest.mark.asyncio
async def test_delete_employee_removes_project_memberships(tmp_path, monkeypatch):
    """删除员工时应同步移除其所有项目成员记录"""
    from routers import employees as employees_router
    from stores.json.employee_store import EmployeeConfig, EmployeeStore
    from stores.json.project_store import ProjectConfig, ProjectMember, ProjectStore

    data_dir = tmp_path / "data"
    employee_store = EmployeeStore(data_dir)
    project_store = ProjectStore(data_dir)

    employee_store.save(EmployeeConfig(id="emp-1", name="员工一", created_by="tester"))
    employee_store.save(EmployeeConfig(id="emp-2", name="员工二", created_by="tester"))

    project_store.save(ProjectConfig(id="proj-a", name="项目A"))
    project_store.save(ProjectConfig(id="proj-b", name="项目B"))
    project_store.upsert_member(ProjectMember(project_id="proj-a", employee_id="emp-1"))
    project_store.upsert_member(ProjectMember(project_id="proj-a", employee_id="emp-2"))
    project_store.upsert_member(ProjectMember(project_id="proj-b", employee_id="emp-1"))

    monkeypatch.setattr(employees_router, "employee_store", employee_store)
    monkeypatch.setattr(employees_router, "project_store", project_store)

    result = await employees_router.delete_employee("emp-1", {"sub": "tester"})

    assert result["status"] == "deleted"
    assert result["employee_id"] == "emp-1"
    assert result["removed_project_member_count"] == 2
    assert set(result["removed_project_ids"]) == {"proj-a", "proj-b"}
    assert employee_store.get("emp-1") is None
    assert project_store.get_member("proj-a", "emp-1") is None
    assert project_store.get_member("proj-b", "emp-1") is None
    assert project_store.get_member("proj-a", "emp-2") is not None


@pytest.mark.asyncio
async def test_create_employee_from_draft_auto_creates_missing_skill_and_rule(tmp_path, monkeypatch):
    """员工草稿创建应自动补齐缺失技能和规则，再完成员工创建"""
    from routers import employees as employees_router
    from models.requests import EmployeeDraftCreateReq
    from stores import mcp_bridge
    from stores.json.employee_store import EmployeeStore
    from stores.json.project_store import ProjectStore

    data_dir = tmp_path / "data"
    employee_store = EmployeeStore(data_dir)
    project_store = ProjectStore(data_dir)
    skill_store = mcp_bridge._skills_mod.SkillStore(data_dir / "skills-runtime")
    rule_store = mcp_bridge._rules_mod.RuleStore(data_dir / "rules-runtime")

    monkeypatch.setattr(employees_router, "employee_store", employee_store)
    monkeypatch.setattr(employees_router, "project_store", project_store)
    monkeypatch.setattr(employees_router, "skill_store", skill_store)
    monkeypatch.setattr(employees_router, "rule_store", rule_store)

    req = EmployeeDraftCreateReq(
        name="产品经理助手",
        description="负责 PRD 拆解与评审建议",
        goal="输出结构化需求分析和改进建议",
        skills=["PRD 拆解"],
        rule_titles=["需求澄清优先"],
        rule_domains=["product"],
        style_hints=["先结论后展开"],
    )

    result = await employees_router.create_employee_from_draft(req, {"sub": "tester"})

    assert result["status"] == "created"
    assert len(result["created_skills"]) == 1
    assert len(result["created_rules"]) == 1

    employee = employee_store.get(result["employee"]["id"])
    assert employee is not None
    assert employee.skills == [result["created_skills"][0]["id"]]
    assert employee.rule_ids == [result["created_rules"][0]["id"]]

    created_skill = skill_store.get(result["created_skills"][0]["id"])
    assert created_skill is not None
    skill_package = skill_store.package_path(created_skill.id)
    assert skill_package.exists()
    assert (skill_package / "SKILL.md").exists()

    created_rule = rule_store.get(result["created_rules"][0]["id"])
    assert created_rule is not None
    assert created_rule.domain == "product"
    assert "需求澄清优先" in created_rule.title


@pytest.mark.asyncio
async def test_skill_package_tree_and_file_preview(tmp_path, monkeypatch):
    from routers import skills as skills_router
    from stores import mcp_bridge

    package_dir = tmp_path / "skill-packages" / "skill-demo"
    (package_dir / "tools").mkdir(parents=True)
    (package_dir / "assets").mkdir(parents=True)
    (package_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")
    (package_dir / "tools" / "run.py").write_text("print('hello')\n", encoding="utf-8")
    (package_dir / ".db-config-secret.json").write_text('{"password":"secret"}', encoding="utf-8")
    (package_dir / "assets" / "logo.bin").write_bytes(b"\x00\x01\x02\x03")

    skill = mcp_bridge.Skill(
        id="skill-demo",
        version="1.0.0",
        name="Skill Demo",
        description="",
        mcp_service="",
        created_by="tester",
        package_dir=str(package_dir.relative_to(tmp_path)),
    )

    class StubSkillStore:
        def get(self, skill_id):
            return skill if skill_id == "skill-demo" else None

    monkeypatch.setattr(skills_router, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(skills_router, "skill_store", StubSkillStore())
    monkeypatch.setattr(skills_router, "_ensure_historical_skills_registered", lambda: None)

    tree_result = await skills_router.get_skill_package_tree("skill-demo")
    root_names = [item["label"] for item in tree_result["tree"]]

    assert "SKILL.md" in root_names
    assert "tools" in root_names
    assert ".db-config-secret.json" not in root_names

    file_result = await skills_router.get_skill_package_file("skill-demo", "tools/run.py")
    assert file_result["file"]["path"] == "tools/run.py"
    assert "print('hello')" in file_result["file"]["content"]
    assert file_result["file"]["is_binary"] is False

    binary_result = await skills_router.get_skill_package_file("skill-demo", "assets/logo.bin")
    assert binary_result["file"]["is_binary"] is True
    assert binary_result["file"]["content"] == ""


def test_backfill_existing_skill_packages_registers_history(tmp_path, monkeypatch):
    from services import skill_import_service as import_svc
    from stores import mcp_bridge

    skill_store = mcp_bridge._skills_mod.SkillStore(tmp_path)
    css_dir = tmp_path / "skill-packages" / "css"
    css_dir.mkdir(parents=True)
    (css_dir / "SKILL.md").write_text(
        "---\nname: CSS\nslug: css\nversion: 1.0.1\ndescription: CSS helper\n---\n",
        encoding="utf-8",
    )
    system_dir = tmp_path / "skill-packages" / "system-mcp-prompts-chat"
    system_dir.mkdir(parents=True)
    (system_dir / "manifest.json").write_text(
        '{"name":"系统MCP · prompts.chat","version":"1.0.0","description":"system skill"}',
        encoding="utf-8",
    )

    monkeypatch.setattr(import_svc, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(import_svc, "skill_store", skill_store)

    result = import_svc.backfill_existing_skill_packages()

    assert [skill.id for skill in result.created] == ["css", "system-mcp-prompts-chat"]
    assert skill_store.get("css") is not None
    assert skill_store.get("system-mcp-prompts-chat") is not None


if __name__ == "__main__":
    asyncio.run(test_orchestrator_logic())
    asyncio.run(test_tool_executor_logic())
    asyncio.run(test_conversation_manager_logic())
    print("\n✅ 所有单元测试通过")
