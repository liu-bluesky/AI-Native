"""模拟测试（无需 Redis）"""

import asyncio
from contextvars import ContextVar
import json
from pathlib import Path
import re
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
                    "model_configs": [
                        {"name": "gpt-4.1", "model_type": "image_generation"},
                        {"name": "gpt-4o-mini", "model_type": "video_generation"},
                    ],
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
    assert sources_payload["providers"][0]["model_configs"] == [
        {"name": "gpt-4.1", "model_type": "image_generation"},
        {"name": "gpt-4o-mini", "model_type": "video_generation"},
    ]

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


class _FakeConversationRedis:
    def __init__(self):
        self.values: dict[str, str] = {}
        self.lists: dict[str, list[str]] = {}
        self.expire_calls: list[tuple[str, int]] = []

    async def set(self, key, value, ex=None):
        self.values[key] = value

    async def get(self, key):
        return self.values.get(key)

    async def rpush(self, key, value):
        self.lists.setdefault(key, []).append(value)

    async def expire(self, key, ttl):
        self.expire_calls.append((key, ttl))

    async def lrange(self, key, start, end):
        return list(self.lists.get(key, []))

    async def delete(self, key):
        self.values.pop(key, None)
        self.lists.pop(key, None)


@pytest.mark.asyncio
async def test_conversation_manager_append_refreshes_session_meta():
    from services.conversation_manager import ConversationManager

    redis_mock = _FakeConversationRedis()
    manager = ConversationManager(redis_mock)

    session_id = await manager.create_session("proj-1", "emp-1")
    meta_key = f"session:{session_id}:meta"
    initial_meta = json.loads(redis_mock.values[meta_key])

    await manager.append_message(session_id, {"role": "user", "content": "你好"})

    updated_meta = json.loads(redis_mock.values[meta_key])
    context = await manager.get_context(session_id, 4000)
    refreshed_meta = json.loads(redis_mock.values[meta_key])

    assert updated_meta["message_count"] == 1
    assert updated_meta["last_active_at"] != initial_meta["last_active_at"]
    assert refreshed_meta["message_count"] == 1
    assert refreshed_meta["last_active_at"] != updated_meta["last_active_at"]
    assert context == [{"role": "user", "content": "你好"}]
    assert (f"session:{session_id}:messages", manager._session_ttl) in redis_mock.expire_calls


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
    assert any(item["id"] == "audio_transcription" for item in definition["options"])


def test_dictionary_catalog_includes_llm_chat_parameter_dictionaries():
    from services.dictionary_catalog import get_dictionary_definition

    image_resolution = get_dictionary_definition("llm_image_resolutions")
    video_duration = get_dictionary_definition("llm_video_duration_seconds")

    assert image_resolution is not None
    assert image_resolution["default_value"] == "1080x1080"
    assert any(item["id"] == "2160x2160" for item in image_resolution["options"])
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


def test_permission_catalog_includes_work_session_management():
    from core.role_permissions import permission_catalog

    catalog = permission_catalog()
    menu_items = next(
        (group["items"] for group in catalog["groups"] if group["group"] == "menu"),
        [],
    )

    assert any(item["key"] == "menu.system.work_sessions" for item in menu_items)


def test_permission_catalog_includes_ai_assistant_voice_button():
    from core.role_permissions import permission_catalog

    catalog = permission_catalog()
    button_items = next(
        (group["items"] for group in catalog["groups"] if group["group"] == "button"),
        [],
    )

    assert any(item["key"] == "button.ai.assistant.voice" for item in button_items)


def test_project_manage_access_prefers_creator_over_later_owner(monkeypatch):
    from fastapi import HTTPException
    from routers import projects as projects_router
    from stores.json.project_store import ProjectConfig, ProjectUserMember

    project = ProjectConfig(id="proj-1", name="项目一")
    members = [
        ProjectUserMember(
            project_id="proj-1",
            username="alice",
            role="owner",
            enabled=True,
            joined_at="2026-03-01T00:00:00+00:00",
        ),
        ProjectUserMember(
            project_id="proj-1",
            username="bob",
            role="owner",
            enabled=True,
            joined_at="2026-03-02T00:00:00+00:00",
        ),
    ]

    class DummyProjectStore:
        @staticmethod
        def get(project_id):
            return project if project_id == "proj-1" else None

        @staticmethod
        def list_user_members(project_id):
            return members if project_id == "proj-1" else []

        @staticmethod
        def get_user_member(project_id, username):
            for item in members:
                if item.project_id == project_id and item.username == username:
                    return item
            return None

        @staticmethod
        def list_members(project_id):
            return []

    monkeypatch.setattr(projects_router, "project_store", DummyProjectStore())
    monkeypatch.setattr(projects_router, "_is_admin_like", lambda auth_payload: auth_payload.get("role") == "admin")
    monkeypatch.setattr(projects_router, "_ensure_project_access", lambda project_id, auth_payload: project)

    serialized_for_alice = projects_router._serialize_project(project, {"sub": "alice", "role": "user"})
    serialized_for_bob = projects_router._serialize_project(project, {"sub": "bob", "role": "user"})
    serialized_for_admin = projects_router._serialize_project(project, {"sub": "root", "role": "admin"})

    assert serialized_for_alice["created_by"] == "alice"
    assert serialized_for_alice["can_manage"] is True
    assert serialized_for_bob["can_manage"] is False
    assert serialized_for_admin["can_manage"] is True
    assert projects_router._can_manage_project("proj-1", {"sub": "admin", "role": "admin"}, project) is True

    projects_router._ensure_project_manage_access("proj-1", {"sub": "alice", "role": "user"})
    with pytest.raises(HTTPException):
        projects_router._ensure_project_manage_access("proj-1", {"sub": "bob", "role": "user"})


def test_serialize_project_includes_ui_rule_bindings(monkeypatch):
    from routers import projects as projects_router
    from stores.json.project_store import ProjectConfig, ProjectUserMember

    class DummyRule:
        def __init__(self, rule_id: str, title: str, domain: str, content: str = "") -> None:
            self.id = rule_id
            self.title = title
            self.domain = domain
            self.content = content

    project = ProjectConfig(
        id="proj-ui",
        name="UI 项目",
        created_by="alice",
        ui_rule_ids=["rule-ui", "rule-missing", "rule-ui"],
    )
    members = [
        ProjectUserMember(project_id="proj-ui", username="alice", role="owner", enabled=True),
    ]

    class DummyProjectStore:
        @staticmethod
        def get(project_id):
            return project if project_id == "proj-ui" else None

        @staticmethod
        def list_user_members(project_id):
            return members if project_id == "proj-ui" else []

        @staticmethod
        def get_user_member(project_id, username):
            for item in members:
                if item.project_id == project_id and item.username == username:
                    return item
            return None

        @staticmethod
        def list_members(project_id):
            return []

    class DummyRuleStore:
        @staticmethod
        def get(rule_id):
            if rule_id == "rule-ui":
                return DummyRule("rule-ui", "主视觉规范", "ui", "按钮圆角 12px")
            return None

    monkeypatch.setattr(projects_router, "project_store", DummyProjectStore())
    monkeypatch.setattr(projects_router, "rule_store", DummyRuleStore())

    serialized = projects_router._serialize_project(project, {"sub": "alice", "role": "user"})

    assert serialized["ui_rule_ids"] == ["rule-ui", "rule-missing"]
    assert serialized["ui_rule_bindings"] == [
        {"id": "rule-ui", "title": "主视觉规范", "domain": "ui"},
        {"id": "rule-missing", "title": "rule-missing（规则不存在）", "domain": ""},
    ]


def _build_project_api_test_client(tmp_path, monkeypatch, auth_payload):
    from core import config as core_config
    from core.deps import require_auth
    from core.server import create_app
    from stores import factory as store_factory

    monkeypatch.setenv("CORE_STORE_BACKEND", "json")
    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()
    for proxy_name in (
        "project_store",
        "role_store",
        "project_material_store",
        "project_studio_export_store",
        "employee_store",
        "system_config_store",
    ):
        getattr(store_factory, proxy_name)._instance = None

    app = create_app()
    app.dependency_overrides[require_auth] = lambda: auth_payload
    client = TestClient(app)
    return client, store_factory.project_store


def test_project_routes_include_created_by_for_create_list_and_detail(tmp_path, monkeypatch):
    client, project_store = _build_project_api_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "alice", "role": "admin"},
    )

    create_response = client.post(
        "/api/projects",
        json={
            "name": "创建人测试项目",
            "description": "验证项目管理接口返回创建人",
        },
    )

    assert create_response.status_code == 200
    created_project = create_response.json()["project"]
    project_id = created_project["id"]

    assert created_project["created_by"] == "alice"
    assert project_store.get(project_id).created_by == "alice"

    list_response = client.get("/api/projects")
    assert list_response.status_code == 200
    listed_project = next(item for item in list_response.json()["projects"] if item["id"] == project_id)
    assert listed_project["created_by"] == "alice"

    detail_response = client.get(f"/api/projects/{project_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["project"]["created_by"] == "alice"


def test_project_store_supports_project_membership_aggregates(tmp_path):
    from stores.json.project_store import ProjectConfig, ProjectStore, ProjectUserMember

    project_store = ProjectStore(tmp_path / "data")
    project_store.save(ProjectConfig(id="proj-a", name="项目 A"))
    project_store.save(ProjectConfig(id="proj-b", name="项目 B"))
    project_store.upsert_user_member(
        ProjectUserMember(
            project_id="proj-a",
            username="alice",
            role="owner",
            enabled=True,
            joined_at="2026-04-09T00:00:00+00:00",
        )
    )
    project_store.upsert_user_member(
        ProjectUserMember(
            project_id="proj-a",
            username="bob",
            role="member",
            enabled=True,
            joined_at="2026-04-10T00:00:00+00:00",
        )
    )
    project_store.upsert_user_member(
        ProjectUserMember(
            project_id="proj-b",
            username="alice",
            role="owner",
            enabled=False,
            joined_at="2026-04-08T00:00:00+00:00",
        )
    )

    memberships = project_store.list_user_memberships("alice", ["proj-a", "proj-b", "proj-missing"])

    assert memberships["proj-a"].username == "alice"
    assert memberships["proj-b"].enabled is False
    assert project_store.list_user_member_counts(["proj-a", "proj-b"]) == {"proj-a": 2, "proj-b": 1}
    assert project_store.list_owner_usernames(["proj-a", "proj-b"]) == {"proj-a": "alice"}


def test_project_memory_route_excludes_work_trajectory_records(tmp_path, monkeypatch):
    from core.deps import employee_store
    from routers import projects as projects_router
    from stores.json.employee_store import EmployeeConfig
    from stores.json.project_store import ProjectConfig, ProjectMember
    from stores.mcp_bridge import Classification, Memory, MemoryScope, MemoryType

    client, project_store = _build_project_api_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "admin", "role": "admin"},
    )
    project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    project_store.upsert_member(ProjectMember(project_id="proj-1", employee_id="emp-1", enabled=True))
    employee_store.save(EmployeeConfig(id="emp-1", name="员工一"))

    memories_by_employee = {
        "emp-1": [
            Memory(
                id="mem-keep",
                employee_id="emp-1",
                type=MemoryType.KEY_EVENT,
                content=(
                    "[用户问题] 调整记忆详情\n"
                    "[最终结论] 已完成\n"
                    "[关联会话] chat-123\n"
                    "[执行轨迹JSON] "
                    "{\"chat_session_id\":\"chat-123\",\"root_goal\":\"调整记忆详情\",\"task_node_id\":\"node-1\","
                    "\"task_node_title\":\"修复详情页\",\"task_tree_chat_session_id\":\"chat-123\","
                    "\"task_tree_session_id\":\"task-tree-123\"}"
                ),
                project_name="项目一",
                importance=0.8,
                scope=MemoryScope.TEAM_SHARED,
                classification=Classification.INTERNAL,
                purpose_tags=("query-mcp", "manual-write"),
                created_at="2026-04-03T06:00:00+00:00",
            ),
            Memory(
                id="mem-trajectory",
                employee_id="emp-1",
                type=MemoryType.LEARNED_PATTERN,
                content="[工作事实] 已补充工作轨迹",
                project_name="项目一",
                importance=0.7,
                scope=MemoryScope.TEAM_SHARED,
                classification=Classification.INTERNAL,
                purpose_tags=("work-facts", "chat-session:chat-1"),
                created_at="2026-04-03T06:01:00+00:00",
            ),
        ]
    }

    class FakeMemoryStore:
        @staticmethod
        def list_by_employee(employee_id):
            return list(memories_by_employee.get(employee_id, ()))

    monkeypatch.setattr(projects_router, "memory_store", FakeMemoryStore())

    response = client.get("/api/projects/proj-1/memories")
    assert response.status_code == 200
    payload = response.json()
    assert payload["project_id"] == "proj-1"
    assert payload["total"] == 1
    assert payload["limit"] == 50
    assert payload["has_more"] is False
    assert [item["id"] for item in payload["items"]] == ["mem-keep"]
    assert payload["items"][0]["chat_session_id"] == "chat-123"
    assert payload["items"][0]["task_tree_session_id"] == "task-tree-123"
    assert payload["items"][0]["task_tree_chat_session_id"] == "chat-123"
    assert payload["items"][0]["task_node_id"] == "node-1"
    assert payload["items"][0]["task_node_title"] == "修复详情页"
    assert payload["items"][0]["root_goal"] == "调整记忆详情"


def test_project_work_session_routes_list_and_detail(tmp_path, monkeypatch):
    from core.deps import employee_store
    from routers import projects as projects_router
    from stores.json.employee_store import EmployeeConfig
    from stores.json.project_store import ProjectConfig, ProjectMember
    from stores.json.work_session_store import WorkSessionEvent

    client, project_store = _build_project_api_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "admin", "role": "admin"},
    )
    project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    project_store.upsert_member(ProjectMember(project_id="proj-1", employee_id="emp-1", enabled=True))
    employee_store.save(EmployeeConfig(id="emp-1", name="员工一"))

    events = [
        WorkSessionEvent(
            id="wse-1",
            project_id="proj-1",
            project_name="项目一",
            employee_id="emp-1",
            session_id="ws-1",
            source_kind="work-facts",
            event_type="implementation",
            phase="实现",
            step="拆分项目记忆与工作轨迹",
            status="in_progress",
            goal="拆清项目详情页的数据来源",
            facts=["已新增项目级聚合接口"],
            changed_files=["web-admin/api/routers/projects.py"],
            verification=["python -m py_compile"],
            created_at="2026-04-03T06:00:00+00:00",
            updated_at="2026-04-03T06:00:00+00:00",
        ),
        WorkSessionEvent(
            id="wse-2",
            project_id="proj-1",
            project_name="项目一",
            employee_id="emp-1",
            session_id="ws-1",
            source_kind="session-event",
            event_type="verification",
            phase="验证",
            step="跑回归",
            status="completed",
            content="接口与前端已联通",
            verification=["uv run pytest test_unit.py -k project_work_session_routes"],
            next_steps=["补前端构建验证"],
            created_at="2026-04-03T06:05:00+00:00",
            updated_at="2026-04-03T06:05:00+00:00",
        ),
    ]

    class FakeWorkSessionStore:
        @staticmethod
        def list_events(project_id="", employee_id="", session_id="", query="", limit=200):
            keyword = str(query or "").strip().lower()
            filtered = []
            for item in events:
                if project_id and item.project_id != project_id:
                    continue
                if employee_id and item.employee_id != employee_id:
                    continue
                if session_id and item.session_id != session_id:
                    continue
                if keyword:
                    haystack = "\n".join(
                        [
                            item.project_name,
                            item.phase,
                            item.step,
                            item.goal,
                            item.content,
                            *item.verification,
                            *item.changed_files,
                        ]
                    ).lower()
                    if keyword not in haystack:
                        continue
                filtered.append(item)
            filtered.sort(key=lambda entry: (entry.created_at, entry.id), reverse=True)
            return filtered[:limit]

    monkeypatch.setattr(projects_router, "work_session_store", FakeWorkSessionStore())

    list_response = client.get("/api/projects/proj-1/work-sessions")
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert len(list_payload["items"]) == 1
    assert list_payload["items"][0]["session_id"] == "ws-1"
    assert list_payload["items"][0]["employee_name"] == "员工一"
    assert list_payload["items"][0]["latest_status"] == "completed"
    assert list_payload["items"][0]["verification"] == [
        "uv run pytest test_unit.py -k project_work_session_routes",
        "python -m py_compile",
    ]

    detail_response = client.get("/api/projects/proj-1/work-sessions/ws-1")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["session"]["session_id"] == "ws-1"
    assert detail_payload["session"]["employee_name"] == "员工一"
    assert detail_payload["items"][0]["event_type"] == "verification"
    assert detail_payload["items"][1]["facts"] == ["已新增项目级聚合接口"]

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
        "llm_image_resolutions": "720x720",
        "llm_image_styles": "illustration",
        "llm_video_duration_seconds": "12",
    }
    dictionary_options = {
        "llm_image_resolutions": [
            {"id": "720x720", "label": "720x720"},
            {"id": "1080x1080", "label": "1080x1080"},
            {"id": "2160x2160", "label": "2160x2160"},
        ],
        "llm_image_styles": [
            {"id": "auto", "label": "自动"},
            {"id": "illustration", "label": "插画"},
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

    assert catalog.get_chat_parameter_default_value("image_resolution") == "720x720"
    assert catalog.normalize_chat_parameter_value("image_resolution", "720x720") == "720x720"
    assert catalog.normalize_chat_parameter_value("image_resolution", "bad-value") == "720x720"
    assert catalog.get_chat_parameter_default_value("image_style") == "illustration"
    assert catalog.normalize_chat_parameter_value("image_style", "bad-value") == "illustration"
    assert catalog.get_chat_parameter_default_value("video_duration_seconds") == 12
    assert catalog.normalize_chat_parameter_value("video_duration_seconds", "12") == 12
    assert catalog.normalize_chat_parameter_value("video_duration_seconds", "999") == 12


def test_project_chat_image_resolution_converts_to_concrete_size():
    from routers import projects as projects_router

    assert projects_router._resolve_project_chat_image_size("720x720", "16:9") == "720x406"
    assert projects_router._resolve_project_chat_image_size("1080x1080", "9:16") == "608x1080"
    assert projects_router._resolve_project_chat_image_size("2160x2160", "1:1") == "2160x2160"
    assert projects_router._resolve_project_chat_image_size("1280x720", "1:1") == "1280x720"
    assert projects_router._resolve_project_chat_image_size("2160p", "16:9") == "3840x2160"
    assert projects_router._resolve_project_chat_image_size("1536x1024", "3:4") == "1536x1024"


def test_normalize_dictionaries_migrates_legacy_image_resolution_values():
    from stores.json.system_config_store import normalize_dictionaries

    normalized = normalize_dictionaries(
        {
            "llm_image_resolutions": {
                "key": "llm_image_resolutions",
                "label": "图片分辨率",
                "default_value": "1080p",
                "options": [
                    {"id": "720p", "label": "720p"},
                    {"id": "1080p", "label": "1080p"},
                    {"id": "4K", "label": "4K"},
                ],
            }
        }
    )

    image_resolution = normalized["llm_image_resolutions"]
    assert image_resolution["default_value"] == "1080x1080"
    assert [item["id"] for item in image_resolution["options"]] == [
        "720x720",
        "1080x1080",
        "2160x2160",
    ]


def test_json_system_config_store_persists_migrated_dictionaries(tmp_path):
    from stores.json.system_config_store import SystemConfigStore

    data_dir = tmp_path / "api-data"
    data_dir.mkdir(parents=True, exist_ok=True)
    system_config_path = data_dir / "system-config.json"
    system_config_path.write_text(
        json.dumps(
            {
                "id": "global",
                "dictionaries": {
                    "llm_image_resolutions": {
                        "key": "llm_image_resolutions",
                        "label": "图片分辨率",
                        "default_value": "1080p",
                        "options": [
                            {"id": "720p", "label": "720p"},
                            {"id": "1080p", "label": "1080p"},
                            {"id": "4K", "label": "4K"},
                        ],
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    store = SystemConfigStore(data_dir)
    config = store.get_global()
    persisted = json.loads(system_config_path.read_text(encoding="utf-8"))

    assert config.dictionaries["llm_image_resolutions"]["default_value"] == "1080x1080"
    assert persisted["dictionaries"]["llm_image_resolutions"]["default_value"] == "1080x1080"
    assert persisted["dictionaries"]["llm_image_resolutions"]["options"][2]["id"] == "2160x2160"


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


def test_system_config_redacts_voice_allowlists_for_non_admin_readers(tmp_path, monkeypatch):
    from core import config as core_config
    from core.deps import require_auth
    from core.server import create_app
    from stores import factory as store_factory
    from stores.json.role_store import RoleConfig

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

    store_factory.system_config_store.patch_global(
        {
            "voice_input_enabled": True,
            "voice_input_provider_id": "provider-stt",
            "voice_input_model_name": "stt-model",
            "voice_input_allowed_usernames": ["alice", "bob"],
            "voice_input_allowed_role_ids": ["user"],
        }
    )
    store_factory.role_store.save(
        RoleConfig(
            id="chat-reader",
            name="Chat Reader",
            description="Can read AI chat runtime config only",
            permissions=["menu.ai.chat"],
            built_in=False,
        )
    )

    app = create_app()
    app.dependency_overrides[require_auth] = lambda: {
        "sub": "reader",
        "role": "chat-reader",
        "roles": ["chat-reader"],
    }
    client = TestClient(app)

    response = client.get("/api/system-config")

    assert response.status_code == 200
    config = response.json()["config"]
    assert config["voice_input_enabled"] is True
    assert config["voice_input_provider_id"] == "provider-stt"
    assert config["voice_input_model_name"] == "stt-model"
    assert config["voice_input_allowed_usernames"] == []
    assert config["voice_input_allowed_role_ids"] == []


def test_public_contact_channels_endpoint_returns_enabled_items(tmp_path, monkeypatch):
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

    patch_response = client.patch(
        "/api/system-config",
        json={
            "public_contact_channels": [
                {
                    "id": "group-disabled",
                    "enabled": False,
                    "type": "qq_group",
                    "title": "隐藏群",
                    "qq_group_number": "999999",
                },
                {
                    "id": "group-main",
                    "enabled": True,
                    "type": "qq_group",
                    "title": "加入用户交流群",
                    "description": "产品答疑与版本通知",
                    "qq_group_number": "123 456 789",
                    "button_text": "复制群号",
                    "guide_text": "打开 QQ 搜索群号加入",
                    "join_link": "https://qm.qq.com/example",
                    "qr_image_url": "https://example.com/qq.png",
                    "sort_order": 20,
                },
            ]
        },
    )

    assert patch_response.status_code == 200
    config_payload = patch_response.json()["config"]["public_contact_channels"]
    assert len(config_payload) == 2
    assert config_payload[1]["qq_group_number"] == "123456789"

    response = client.get("/api/system-config/public-contact-channels")

    assert response.status_code == 200
    assert response.json()["items"] == [
        {
            "id": "group-main",
            "type": "qq_group",
            "title": "加入用户交流群",
            "description": "产品答疑与版本通知",
            "qq_group_number": "123456789",
            "button_text": "复制群号",
            "guide_text": "打开 QQ 搜索群号加入",
            "join_link": "https://qm.qq.com/example",
            "qr_image_url": "https://example.com/qq.png",
            "sort_order": 20,
        }
    ]


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


def test_extract_user_questions_from_rpc_payload_skips_internal_progress_tools():
    from services.dynamic_mcp_audit import extract_user_questions_from_rpc_payload

    payload = {
        "method": "tools/call",
        "params": {
            "name": "append_session_event",
            "arguments": {
                "project_id": "proj-1",
                "chat_session_id": "chat-123",
                "content": "已完成构建验证",
                "title": "构建验证",
            },
        },
    }

    method_name, tool_name, questions, context = extract_user_questions_from_rpc_payload(payload)

    assert method_name == "tools/call"
    assert tool_name == "append_session_event"
    assert questions == []
    assert context["project_id"] == "proj-1"
    assert context["chat_session_id"] == "chat-123"


def test_save_auto_query_memory_writes_single_team_shared_project_record(tmp_path, monkeypatch):
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
        chat_session_id="chat-123",
    )

    assert len(saved_memories) == 1
    assert saved_memories[0].employee_id == "emp-1"
    assert saved_memories[0].project_name == "项目一"
    assert saved_memories[0].scope.value == "team-shared"
    assert "[关联会话] chat-123" in saved_memories[0].content
    assert saved_memories[0].purpose_tags == (
        "auto-capture",
        "user-question",
        "mcp:tools/call:get_manual_content",
        "chat-session:chat-123",
    )


def test_save_auto_query_result_memory_writes_structured_shared_record(tmp_path, monkeypatch):
    from services import dynamic_mcp_audit as audit_svc
    from stores.json.employee_store import EmployeeConfig, EmployeeStore
    from stores.json.project_store import ProjectConfig, ProjectMember, ProjectStore

    data_dir = tmp_path / "data"
    employee_store = EmployeeStore(data_dir)
    project_store = ProjectStore(data_dir)
    employee_store.save(EmployeeConfig(id="emp-1", name="员工一", created_by="tester"))
    project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    project_store.upsert_member(ProjectMember(project_id="proj-1", employee_id="emp-1", enabled=True))

    saved_memories = []
    memory_store = MagicMock()
    memory_store.recent.side_effect = lambda employee_id, limit: []
    memory_store.new_id.side_effect = ["mem-1"]
    memory_store.save.side_effect = saved_memories.append

    monkeypatch.setattr(audit_svc, "employee_store", employee_store)
    monkeypatch.setattr(audit_svc, "project_store", project_store)
    monkeypatch.setattr(audit_svc, "memory_store", memory_store)

    audit_svc.save_auto_query_result_memory(
        "当前项目几个员工",
        "通过项目成员列表查询当前项目的有效成员，并汇总人数与成员名称后返回。",
        "已获取项目成员列表，共 3 名。",
        "mcp:tools/call:list_project_members",
        project_id="proj-1",
        chat_session_id="chat-123",
    )

    assert len(saved_memories) == 1
    saved_memory = saved_memories[0]
    assert saved_memory.employee_id == "emp-1"
    assert saved_memory.project_name == "项目一"
    assert saved_memory.scope.value == "team-shared"
    assert "[用户问题] 当前项目几个员工" in saved_memory.content
    assert "[解决方案] 通过项目成员列表查询当前项目的有效成员，并汇总人数与成员名称后返回。" in saved_memory.content
    assert "[最终结论] 已获取项目成员列表，共 3 名。" in saved_memory.content
    assert "[关联会话] chat-123" in saved_memory.content
    assert saved_memory.purpose_tags == (
        "auto-capture",
        "query-result",
        "mcp:tools/call:list_project_members",
        "workflow:final-summary",
        "chat-session:chat-123",
    )


def test_save_auto_query_result_memory_in_progress_stores_requirement_record(tmp_path, monkeypatch):
    from services import dynamic_mcp_audit as audit_svc
    from stores.json.employee_store import EmployeeConfig, EmployeeStore
    from stores.json.project_store import ProjectConfig, ProjectMember, ProjectStore

    data_dir = tmp_path / "data"
    employee_store = EmployeeStore(data_dir)
    project_store = ProjectStore(data_dir)
    employee_store.save(EmployeeConfig(id="emp-1", name="员工一", created_by="tester"))
    project_store.save(ProjectConfig(id="proj-1", name="项目一"))
    project_store.upsert_member(ProjectMember(project_id="proj-1", employee_id="emp-1", enabled=True))

    saved_memories = []
    memory_store = MagicMock()
    memory_store.recent.side_effect = lambda employee_id, limit: []
    memory_store.new_id.side_effect = ["mem-1"]
    memory_store.save.side_effect = saved_memories.append

    monkeypatch.setattr(audit_svc, "employee_store", employee_store)
    monkeypatch.setattr(audit_svc, "project_store", project_store)
    monkeypatch.setattr(audit_svc, "memory_store", memory_store)

    audit_svc.save_auto_query_result_memory(
        "修复 /mcp/query/sse 的项目记忆闭环",
        "通过统一查询 MCP 查询上下文并逐步推进任务树。",
        "已定位到自动结果记忆会提前写最终结论。",
        "mcp:tools/call:execute_project_collaboration",
        project_id="proj-1",
        chat_session_id="chat-456",
        task_tree_payload={
            "id": "task-tree-456",
            "chat_session_id": "chat-456",
            "source_chat_session_id": "chat-456",
            "root_goal": "修复 /mcp/query/sse 的项目记忆闭环",
            "status": "in_progress",
            "progress_percent": 50,
            "current_node": {
                "id": "node-2",
                "title": "改写自动结果记忆",
                "status": "in_progress",
            },
            "nodes": [
                {"id": "root", "level": 0, "title": "修复 /mcp/query/sse 的项目记忆闭环", "status": "in_progress"},
                {"id": "node-1", "level": 1, "title": "梳理统一查询入口", "status": "done", "verification_result": "已确认代理链路"},
                {"id": "node-2", "level": 1, "title": "改写自动结果记忆", "status": "in_progress", "verification_result": ""},
            ],
            "stats": {"leaf_total": 2, "done_leaf_total": 1},
        },
    )

    assert len(saved_memories) == 1
    saved_memory = saved_memories[0]
    assert "[用户问题] 修复 /mcp/query/sse 的项目记忆闭环" in saved_memory.content
    assert "[任务计划]" in saved_memory.content
    assert "[解决方案]" not in saved_memory.content
    assert "[最终结论]" not in saved_memory.content
    assert "[完成条件] 只有所有计划项完成并写入验证结果后，当前需求才算结束。" in saved_memory.content
    assert "workflow:requirement-record" in saved_memory.purpose_tags
    assert "task-tree-session:task-tree-456" in saved_memory.purpose_tags
    matched = re.search(r"\[执行轨迹JSON\]\s*([^\n]+)", saved_memory.content)
    assert matched
    assert json.loads(matched.group(1)) == {
        "chat_session_id": "chat-456",
        "root_goal": "修复 /mcp/query/sse 的项目记忆闭环",
        "task_node_id": "node-2",
        "task_node_title": "改写自动结果记忆",
        "task_tree_chat_session_id": "chat-456",
        "task_tree_session_id": "task-tree-456",
    }

def test_memory_store_recall_filters_project_before_limit(tmp_path):
    from stores import mcp_bridge as bridge

    store = bridge._memory_mod.MemoryStore(tmp_path / "memories.db")
    for index in range(120):
        store.save(
            bridge.Memory(
                id=f"mem-other-{index}",
                employee_id="emp-1",
                type=bridge.MemoryType.PROJECT_CONTEXT,
                content="query hit from other project",
                project_name="其他项目",
                importance=1.0 - (index * 0.001),
            )
        )
    store.save(
        bridge.Memory(
            id="mem-target",
            employee_id="emp-1",
            type=bridge.MemoryType.PROJECT_CONTEXT,
            content="query hit from target project",
            project_name="目标项目",
            importance=0.1,
        )
    )

    recalled = store.recall("emp-1", "query hit", 100, project_name="目标项目")

    assert [item.id for item in recalled] == ["mem-target"]


def test_save_project_memory_entries_defaults_to_single_team_shared_record(monkeypatch):
    from services import dynamic_mcp_apps_query as query_mcp_svc
    from stores.mcp_bridge import MemoryScope, MemoryType

    saved_memories = []

    monkeypatch.setattr(
        query_mcp_svc,
        "project_store",
        type(
            "DummyProjectStore",
            (),
            {
                "get": staticmethod(lambda project_id: type("DummyProject", (), {"id": project_id, "name": "项目一"})()),
            },
        )(),
    )
    monkeypatch.setattr(query_mcp_svc, "_active_project_employee_ids", lambda project_id: ["emp-1", "emp-2", "emp-3"])
    monkeypatch.setattr(
        query_mcp_svc,
        "memory_store",
        type(
            "DummyMemoryStore",
            (),
            {
                "new_id": staticmethod(lambda: f"mem-{len(saved_memories) + 1}"),
                "save": staticmethod(lambda memory: saved_memories.append(memory)),
            },
        )(),
    )

    result = query_mcp_svc._save_project_memory_entries(
        project_id="proj-1",
        content="问题：提交代码到远程仓库\n结论：远程大文件阻塞",
        memory_type=MemoryType.KEY_EVENT,
        purpose_tags=("query-mcp", "manual-write", "project-id"),
    )

    assert result["status"] == "saved"
    assert result["saved_count"] == 1
    assert result["employee_ids"] == ["emp-1"]
    assert result["scope"] == MemoryScope.TEAM_SHARED.value
    assert saved_memories[0].employee_id == "emp-1"
    assert saved_memories[0].scope == MemoryScope.TEAM_SHARED
    assert saved_memories[0].type == MemoryType.KEY_EVENT
    assert saved_memories[0].purpose_tags[:3] == ("query-mcp", "manual-write", "project-id")
    assert "project-id:proj-1" in saved_memories[0].purpose_tags
    assert any(tag.startswith("fp:") for tag in saved_memories[0].purpose_tags)
    assert "[项目ID] proj-1" in saved_memories[0].content
    assert "[项目名称] 项目一" in saved_memories[0].content


def test_save_project_memory_entries_skips_duplicate_manual_write(monkeypatch):
    from services import dynamic_mcp_apps_query as query_mcp_svc
    from stores.mcp_bridge import Classification, Memory, MemoryScope, MemoryType

    saved_memories = []
    existing_memory = Memory(
        id="mem-existing",
        employee_id="emp-1",
        type=MemoryType.KEY_EVENT,
        content="问题：提交代码到远程仓库\n结论：远程大文件阻塞",
        project_name="项目一",
        importance=0.6,
        scope=MemoryScope.TEAM_SHARED,
        classification=Classification.INTERNAL,
        purpose_tags=("query-mcp", "manual-write", "project-id", "project-id:proj-1"),
    )

    monkeypatch.setattr(
        query_mcp_svc,
        "project_store",
        type(
            "DummyProjectStore",
            (),
            {
                "get": staticmethod(lambda project_id: type("DummyProject", (), {"id": project_id, "name": "项目一"})()),
            },
        )(),
    )
    monkeypatch.setattr(query_mcp_svc, "_active_project_employee_ids", lambda project_id: ["emp-1", "emp-2"])
    monkeypatch.setattr(
        query_mcp_svc,
        "memory_store",
        type(
            "DummyMemoryStore",
            (),
            {
                "new_id": staticmethod(lambda: f"mem-{len(saved_memories) + 1}"),
                "save": staticmethod(lambda memory: saved_memories.append(memory)),
                "recent": staticmethod(lambda employee_id, limit: [existing_memory]),
            },
        )(),
    )

    result = query_mcp_svc._save_project_memory_entries(
        project_id="proj-1",
        content="问题：提交代码到远程仓库\n结论：远程大文件阻塞",
        memory_type=MemoryType.KEY_EVENT,
        purpose_tags=("query-mcp", "manual-write", "project-id"),
    )

    assert result["status"] == "skipped"
    assert result["saved_count"] == 0
    assert result["duplicate_skipped"] is True
    assert result["skipped_employee_ids"] == ["emp-1"]
    assert saved_memories == []


def test_collect_project_memories_filters_explicit_other_project_binding(monkeypatch):
    from services import dynamic_mcp_apps_query as query_mcp_svc
    from stores.mcp_bridge import Classification, Memory, MemoryScope, MemoryType

    target_memory = Memory(
        id="mem-target",
        employee_id="emp-1",
        type=MemoryType.PROJECT_CONTEXT,
        content="[项目ID] proj-1\n[项目名称] 项目一\n问题：目标项目",
        project_name="项目一",
        importance=0.6,
        scope=MemoryScope.TEAM_SHARED,
        classification=Classification.INTERNAL,
        purpose_tags=("query-mcp", "manual-write", "project-id:proj-1"),
    )
    wrong_memory = Memory(
        id="mem-wrong",
        employee_id="emp-1",
        type=MemoryType.PROJECT_CONTEXT,
        content="[项目ID] proj-2\n[项目名称] 项目一\n问题：串项目数据",
        project_name="项目一",
        importance=0.9,
        scope=MemoryScope.TEAM_SHARED,
        classification=Classification.INTERNAL,
        purpose_tags=("query-mcp", "manual-write", "project-id:proj-2"),
    )

    monkeypatch.setattr(query_mcp_svc, "_active_project_employee_ids", lambda project_id: ["emp-1"])
    monkeypatch.setattr(query_mcp_svc, "_resolve_project_name", lambda project_id, project_name="": "项目一")
    monkeypatch.setattr(
        query_mcp_svc,
        "memory_store",
        type(
            "DummyMemoryStore",
            (),
            {
                "recent": staticmethod(lambda employee_id, limit, project_name="": [wrong_memory, target_memory]),
            },
        )(),
    )

    collected = query_mcp_svc._collect_project_memories(project_id="proj-1", employee_id="emp-1", limit=10)

    assert [item["id"] for item in collected] == ["mem-target"]


def test_save_project_chat_memory_snapshot_defaults_to_single_team_shared_record(monkeypatch):
    from routers import projects as projects_router
    from stores.mcp_bridge import MemoryScope

    saved_memories = []

    monkeypatch.setattr(
        projects_router,
        "project_store",
        type(
            "DummyProjectStore",
            (),
            {
                "get": staticmethod(lambda project_id: type("DummyProject", (), {"id": project_id, "name": "项目一"})()),
                "list_members": staticmethod(
                    lambda project_id: [
                        type("DummyMember", (), {"employee_id": "emp-1", "enabled": True})(),
                        type("DummyMember", (), {"employee_id": "emp-2", "enabled": True})(),
                        type("DummyMember", (), {"employee_id": "emp-3", "enabled": True})(),
                    ]
                ),
            },
        )(),
    )
    monkeypatch.setattr(
        projects_router,
        "employee_store",
        type(
            "DummyEmployeeStore",
            (),
            {
                "get": staticmethod(lambda employee_id: object() if employee_id in {"emp-1", "emp-2", "emp-3"} else None),
            },
        )(),
    )
    monkeypatch.setattr(
        projects_router,
        "memory_store",
        type(
            "DummyMemoryStore",
            (),
            {
                "new_id": staticmethod(lambda: f"mem-{len(saved_memories) + 1}"),
                "save": staticmethod(lambda memory: saved_memories.append(memory)),
            },
        )(),
    )

    projects_router._save_project_chat_memory_snapshot(
        project_id="proj-1",
        user_message="为什么每次都全员写记忆？",
        answer="因为默认空选人被扩成了项目全员。",
        chat_session_id="chat-123",
        selected_employee_ids=[],
        source="project-chat-test",
    )

    assert len(saved_memories) == 1
    assert saved_memories[0].employee_id == "emp-1"
    assert saved_memories[0].scope == MemoryScope.TEAM_SHARED
    assert saved_memories[0].purpose_tags[:5] == (
        "auto-capture",
        "project-chat",
        "project-chat-test",
        "workflow:final-summary",
        "project-id:proj-1",
    )
    assert "chat-session:chat-123" in saved_memories[0].purpose_tags
    assert any(tag.startswith("fp:") for tag in saved_memories[0].purpose_tags)
    assert "[处理过程]" in saved_memories[0].content
    assert "[解决方案] 因为默认空选人被扩成了项目全员。" in saved_memories[0].content
    assert "[解决状态] 已给出方案" in saved_memories[0].content
    assert "[项目ID] proj-1" in saved_memories[0].content
    assert "[项目名称] 项目一" in saved_memories[0].content
    assert "[关联会话] chat-123" in saved_memories[0].content


def test_save_project_chat_memory_snapshot_skips_exact_duplicate_record(monkeypatch):
    from routers import projects as projects_router
    from stores.mcp_bridge import Classification, Memory, MemoryScope, MemoryType

    saved_memories = []
    existing_content = (
        "[用户问题] 为什么每次都全员写记忆？\n"
        "[处理过程] 已在当前会话完成问题处理并给出结论，可结合关联任务树回看执行节点与验证结果。\n"
        "[解决方案] 因为默认空选人被扩成了项目全员。\n"
        "[最终结论] 因为默认空选人被扩成了项目全员。\n"
        "[解决状态] 已给出方案\n"
        "[关联会话] chat-123"
    )
    existing_memory = Memory(
        id="mem-existing",
        employee_id="emp-1",
        type=MemoryType.PROJECT_CONTEXT,
        content=existing_content,
        project_name="项目一",
        importance=0.6,
        scope=MemoryScope.TEAM_SHARED,
        classification=Classification.INTERNAL,
        purpose_tags=(
            "auto-capture",
            "project-chat",
            "project-chat-test",
            "workflow:final-summary",
            "project-id:proj-1",
            "chat-session:chat-123",
        ),
    )

    monkeypatch.setattr(
        projects_router,
        "project_store",
        type(
            "DummyProjectStore",
            (),
            {
                "get": staticmethod(lambda project_id: type("DummyProject", (), {"id": project_id, "name": "项目一"})()),
                "list_members": staticmethod(
                    lambda project_id: [type("DummyMember", (), {"employee_id": "emp-1", "enabled": True})()]
                ),
            },
        )(),
    )
    monkeypatch.setattr(
        projects_router,
        "employee_store",
        type(
            "DummyEmployeeStore",
            (),
            {
                "get": staticmethod(lambda employee_id: object() if employee_id == "emp-1" else None),
            },
        )(),
    )
    monkeypatch.setattr(
        projects_router,
        "memory_store",
        type(
            "DummyMemoryStore",
            (),
            {
                "new_id": staticmethod(lambda: f"mem-{len(saved_memories) + 1}"),
                "save": staticmethod(lambda memory: saved_memories.append(memory)),
                "recent": staticmethod(lambda employee_id, limit: [existing_memory]),
            },
        )(),
    )

    projects_router._save_project_chat_memory_snapshot(
        project_id="proj-1",
        user_message="为什么每次都全员写记忆？",
        answer="因为默认空选人被扩成了项目全员。",
        chat_session_id="chat-123",
        selected_employee_ids=["emp-1"],
        source="project-chat-test",
    )

    assert saved_memories == []


def test_save_project_chat_memory_snapshot_with_multiple_selected_employees_stays_single_team_shared(monkeypatch):
    from routers import projects as projects_router
    from stores.mcp_bridge import MemoryScope

    saved_memories = []

    monkeypatch.setattr(
        projects_router,
        "project_store",
        type(
            "DummyProjectStore",
            (),
            {
                "get": staticmethod(lambda project_id: type("DummyProject", (), {"id": project_id, "name": "项目一"})()),
                "list_members": staticmethod(
                    lambda project_id: [
                        type("DummyMember", (), {"employee_id": "emp-1", "enabled": True})(),
                        type("DummyMember", (), {"employee_id": "emp-2", "enabled": True})(),
                        type("DummyMember", (), {"employee_id": "emp-3", "enabled": True})(),
                    ]
                ),
            },
        )(),
    )
    monkeypatch.setattr(
        projects_router,
        "employee_store",
        type(
            "DummyEmployeeStore",
            (),
            {
                "get": staticmethod(lambda employee_id: object() if employee_id in {"emp-1", "emp-2", "emp-3"} else None),
            },
        )(),
    )
    monkeypatch.setattr(
        projects_router,
        "memory_store",
        type(
            "DummyMemoryStore",
            (),
            {
                "new_id": staticmethod(lambda: f"mem-{len(saved_memories) + 1}"),
                "save": staticmethod(lambda memory: saved_memories.append(memory)),
            },
        )(),
    )

    projects_router._save_project_chat_memory_snapshot(
        project_id="proj-1",
        user_message="多人协作时不要给每个员工各写一条重复记忆。",
        answer="多人场景现在只保留一条团队共享记录，由首个选中员工作为锚点存储。",
        selected_employee_ids=["emp-2", "emp-3"],
        source="project-chat-test",
    )

    assert len(saved_memories) == 1
    assert saved_memories[0].employee_id == "emp-2"
    assert saved_memories[0].scope == MemoryScope.TEAM_SHARED


def test_save_project_chat_memory_snapshot_persists_task_tree_binding(monkeypatch):
    from routers import projects as projects_router

    saved_memories = []

    monkeypatch.setattr(
        projects_router,
        "project_store",
        type(
            "DummyProjectStore",
            (),
            {
                "get": staticmethod(lambda project_id: type("DummyProject", (), {"id": project_id, "name": "项目一"})()),
                "list_members": staticmethod(
                    lambda project_id: [
                        type("DummyMember", (), {"employee_id": "emp-1", "enabled": True})(),
                    ]
                ),
            },
        )(),
    )
    monkeypatch.setattr(
        projects_router,
        "employee_store",
        type(
            "DummyEmployeeStore",
            (),
            {
                "get": staticmethod(lambda employee_id: object() if employee_id == "emp-1" else None),
            },
        )(),
    )
    monkeypatch.setattr(
        projects_router,
        "memory_store",
        type(
            "DummyMemoryStore",
            (),
            {
                "new_id": staticmethod(lambda: f"mem-{len(saved_memories) + 1}"),
                "save": staticmethod(lambda memory: saved_memories.append(memory)),
            },
        )(),
    )

    projects_router._save_project_chat_memory_snapshot(
        project_id="proj-1",
        user_message="你好项目里面有几个员工",
        answer="当前项目共有 3 名员工。",
        chat_session_id="chat-123",
        task_tree_payload={
            "id": "task-tree-123",
            "chat_session_id": "chat-123",
            "source_chat_session_id": "chat-123",
            "root_goal": "你好项目里面有几个员工",
            "current_node": {
                "id": "node-1",
                "title": "返回员工数量",
            },
        },
        selected_employee_ids=["emp-1"],
        source="project-chat-test",
    )

    assert len(saved_memories) == 1
    saved_memory = saved_memories[0]
    assert "task-tree-session:task-tree-123" in saved_memory.purpose_tags
    matched = re.search(r"\[执行轨迹JSON\]\s*([^\n]+)", saved_memory.content)
    assert matched
    binding = json.loads(matched.group(1))
    assert binding == {
        "chat_session_id": "chat-123",
        "root_goal": "你好项目里面有几个员工",
        "task_node_id": "node-1",
        "task_node_title": "返回员工数量",
        "task_tree_chat_session_id": "chat-123",
        "task_tree_session_id": "task-tree-123",
    }


def test_save_project_chat_memory_snapshot_in_progress_stores_requirement_record(monkeypatch):
    from routers import projects as projects_router

    saved_memories = []

    monkeypatch.setattr(
        projects_router,
        "project_store",
        type(
            "DummyProjectStore",
            (),
            {
                "get": staticmethod(lambda project_id: type("DummyProject", (), {"id": project_id, "name": "项目一"})()),
                "list_members": staticmethod(
                    lambda project_id: [
                        type("DummyMember", (), {"employee_id": "emp-1", "enabled": True})(),
                    ]
                ),
            },
        )(),
    )
    monkeypatch.setattr(
        projects_router,
        "employee_store",
        type(
            "DummyEmployeeStore",
            (),
            {
                "get": staticmethod(lambda employee_id: object() if employee_id == "emp-1" else None),
            },
        )(),
    )
    monkeypatch.setattr(
        projects_router,
        "memory_store",
        type(
            "DummyMemoryStore",
            (),
            {
                "new_id": staticmethod(lambda: f"mem-{len(saved_memories) + 1}"),
                "save": staticmethod(lambda memory: saved_memories.append(memory)),
                "recent": staticmethod(lambda employee_id, limit: []),
            },
        )(),
    )

    projects_router._save_project_chat_memory_snapshot(
        project_id="proj-1",
        user_message="修复项目详情页记忆工作流",
        answer="先拆清当前工作流，再逐步修改。",
        chat_session_id="chat-123",
        task_tree_payload={
            "id": "task-tree-123",
            "chat_session_id": "chat-123",
            "source_chat_session_id": "chat-123",
            "root_goal": "修复项目详情页记忆工作流",
            "status": "in_progress",
            "progress_percent": 33,
            "current_node": {
                "id": "node-1",
                "title": "梳理现有工作流",
                "status": "in_progress",
            },
            "nodes": [
                {"id": "root", "level": 0, "title": "修复项目详情页记忆工作流", "status": "in_progress"},
                {"id": "node-1", "level": 1, "title": "梳理现有工作流", "status": "in_progress", "verification_result": ""},
                {"id": "node-2", "level": 1, "title": "改写自动记忆语义", "status": "pending", "verification_result": ""},
            ],
        },
        selected_employee_ids=["emp-1"],
        source="project-chat-test",
    )

    assert len(saved_memories) == 1
    saved_memory = saved_memories[0]
    assert "workflow:requirement-record" in saved_memory.purpose_tags
    assert "[任务计划]" in saved_memory.content
    assert "[解决方案]" not in saved_memory.content
    assert "[最终结论]" not in saved_memory.content
    assert "[完成条件] 只有所有计划项完成并写入验证结果后，当前需求才算结束。" in saved_memory.content


def test_save_project_chat_memory_snapshot_in_progress_can_skip_requirement_record(monkeypatch):
    from routers import projects as projects_router

    saved_memories = []

    monkeypatch.setattr(
        projects_router,
        "project_store",
        type(
            "DummyProjectStore",
            (),
            {
                "get": staticmethod(lambda project_id: type("DummyProject", (), {"id": project_id, "name": "项目一"})()),
                "list_members": staticmethod(
                    lambda project_id: [
                        type("DummyMember", (), {"employee_id": "emp-1", "enabled": True})(),
                    ]
                ),
            },
        )(),
    )
    monkeypatch.setattr(
        projects_router,
        "employee_store",
        type(
            "DummyEmployeeStore",
            (),
            {
                "get": staticmethod(lambda employee_id: object() if employee_id == "emp-1" else None),
            },
        )(),
    )
    monkeypatch.setattr(
        projects_router,
        "memory_store",
        type(
            "DummyMemoryStore",
            (),
            {
                "new_id": staticmethod(lambda: f"mem-{len(saved_memories) + 1}"),
                "save": staticmethod(lambda memory: saved_memories.append(memory)),
                "recent": staticmethod(lambda employee_id, limit: []),
            },
        )(),
    )

    projects_router._save_project_chat_memory_snapshot(
        project_id="proj-1",
        user_message="这条普通聊天不该落成需求记录",
        answer="这里是一次普通对话回复。",
        chat_session_id="chat-123",
        task_tree_payload={
            "id": "task-tree-123",
            "chat_session_id": "chat-123",
            "source_chat_session_id": "chat-123",
            "root_goal": "这条普通聊天不该落成需求记录",
            "status": "in_progress",
            "current_node": {
                "id": "node-1",
                "title": "仅普通交流",
                "status": "in_progress",
            },
        },
        selected_employee_ids=["emp-1"],
        source="project-chat-test",
        allow_requirement_record=False,
    )

    assert saved_memories == []


def test_save_project_chat_memory_snapshot_completed_stores_final_summary(monkeypatch):
    from routers import projects as projects_router

    saved_memories = []

    monkeypatch.setattr(
        projects_router,
        "project_store",
        type(
            "DummyProjectStore",
            (),
            {
                "get": staticmethod(lambda project_id: type("DummyProject", (), {"id": project_id, "name": "项目一"})()),
                "list_members": staticmethod(
                    lambda project_id: [
                        type("DummyMember", (), {"employee_id": "emp-1", "enabled": True})(),
                    ]
                ),
            },
        )(),
    )
    monkeypatch.setattr(
        projects_router,
        "employee_store",
        type(
            "DummyEmployeeStore",
            (),
            {
                "get": staticmethod(lambda employee_id: object() if employee_id == "emp-1" else None),
            },
        )(),
    )
    monkeypatch.setattr(
        projects_router,
        "memory_store",
        type(
            "DummyMemoryStore",
            (),
            {
                "new_id": staticmethod(lambda: f"mem-{len(saved_memories) + 1}"),
                "save": staticmethod(lambda memory: saved_memories.append(memory)),
                "recent": staticmethod(lambda employee_id, limit: []),
            },
        )(),
    )

    projects_router._save_project_chat_memory_snapshot(
        project_id="proj-1",
        user_message="修复项目详情页记忆工作流",
        answer="已改成执行中只保留需求记录，全部完成并验证后才生成最终结论。",
        chat_session_id="chat-123",
        task_tree_payload={
            "id": "task-tree-123",
            "chat_session_id": "chat-123",
            "source_chat_session_id": "chat-123",
            "root_goal": "修复项目详情页记忆工作流",
            "status": "done",
            "is_archived": True,
            "progress_percent": 100,
            "current_node": None,
            "nodes": [
                {"id": "root", "level": 0, "title": "修复项目详情页记忆工作流", "status": "done", "verification_result": "整体回归通过"},
                {"id": "node-1", "level": 1, "title": "梳理现有工作流", "status": "done", "verification_result": "已核对写入侧与展示侧链路"},
                {"id": "node-2", "level": 1, "title": "改写自动记忆语义", "status": "done", "verification_result": "相关 pytest 与 build 通过"},
            ],
        },
        selected_employee_ids=["emp-1"],
        source="project-chat-test",
    )

    assert len(saved_memories) == 1
    saved_memory = saved_memories[0]
    assert "workflow:final-summary" in saved_memory.purpose_tags
    assert "[解决方案] 已改成执行中只保留需求记录，全部完成并验证后才生成最终结论。" in saved_memory.content
    assert "[最终结论] 已改成执行中只保留需求记录，全部完成并验证后才生成最终结论。" in saved_memory.content
    assert "[验证结果]" in saved_memory.content


def test_save_project_chat_memory_snapshot_completed_still_saves_final_summary_when_requirement_record_disabled(monkeypatch):
    from routers import projects as projects_router

    saved_memories = []

    monkeypatch.setattr(
        projects_router,
        "project_store",
        type(
            "DummyProjectStore",
            (),
            {
                "get": staticmethod(lambda project_id: type("DummyProject", (), {"id": project_id, "name": "项目一"})()),
                "list_members": staticmethod(
                    lambda project_id: [
                        type("DummyMember", (), {"employee_id": "emp-1", "enabled": True})(),
                    ]
                ),
            },
        )(),
    )
    monkeypatch.setattr(
        projects_router,
        "employee_store",
        type(
            "DummyEmployeeStore",
            (),
            {
                "get": staticmethod(lambda employee_id: object() if employee_id == "emp-1" else None),
            },
        )(),
    )
    monkeypatch.setattr(
        projects_router,
        "memory_store",
        type(
            "DummyMemoryStore",
            (),
            {
                "new_id": staticmethod(lambda: f"mem-{len(saved_memories) + 1}"),
                "save": staticmethod(lambda memory: saved_memories.append(memory)),
                "recent": staticmethod(lambda employee_id, limit: []),
            },
        )(),
    )

    projects_router._save_project_chat_memory_snapshot(
        project_id="proj-1",
        user_message="这轮工作已经完成",
        answer="已完成需求实现，并补充了验证结果。",
        chat_session_id="chat-123",
        task_tree_payload={
            "id": "task-tree-123",
            "chat_session_id": "chat-123",
            "source_chat_session_id": "chat-123",
            "root_goal": "这轮工作已经完成",
            "status": "done",
            "is_archived": True,
            "progress_percent": 100,
            "nodes": [
                {"id": "root", "level": 0, "title": "这轮工作已经完成", "status": "done", "verification_result": "整体通过"},
                {"id": "node-1", "level": 1, "title": "收尾验证", "status": "done", "verification_result": "单测通过"},
            ],
        },
        selected_employee_ids=["emp-1"],
        source="project-chat-test",
        allow_requirement_record=False,
    )

    assert len(saved_memories) == 1
    assert "workflow:final-summary" in saved_memories[0].purpose_tags


def test_save_project_chat_memory_snapshot_incomplete_task_tree_with_completed_verified_answer_still_saves_final_summary(
    monkeypatch,
):
    from routers import projects as projects_router

    saved_memories = []

    monkeypatch.setattr(
        projects_router,
        "project_store",
        type(
            "DummyProjectStore",
            (),
            {
                "get": staticmethod(lambda project_id: type("DummyProject", (), {"id": project_id, "name": "项目一"})()),
                "list_members": staticmethod(
                    lambda project_id: [
                        type("DummyMember", (), {"employee_id": "emp-1", "enabled": True})(),
                    ]
                ),
            },
        )(),
    )
    monkeypatch.setattr(
        projects_router,
        "employee_store",
        type(
            "DummyEmployeeStore",
            (),
            {
                "get": staticmethod(lambda employee_id: object() if employee_id == "emp-1" else None),
            },
        )(),
    )
    monkeypatch.setattr(
        projects_router,
        "memory_store",
        type(
            "DummyMemoryStore",
            (),
            {
                "new_id": staticmethod(lambda: f"mem-{len(saved_memories) + 1}"),
                "save": staticmethod(lambda memory: saved_memories.append(memory)),
                "recent": staticmethod(lambda employee_id, limit: []),
            },
        )(),
    )

    projects_router._save_project_chat_memory_snapshot(
        project_id="proj-1",
        user_message="优化 /ai/chat/settings/system/config 页面内容布局 现在太乱了",
        answer="已完成页面布局优化，npm run build 构建通过，人工验证通过。",
        chat_session_id="chat-123",
        task_tree_payload={
            "id": "task-tree-123",
            "chat_session_id": "chat-123",
            "source_chat_session_id": "chat-123",
            "root_goal": "优化 /ai/chat/settings/system/config 页面内容布局 现在太乱了",
            "status": "in_progress",
            "progress_percent": 67,
            "current_node": {
                "id": "node-2",
                "title": "验证布局调整",
                "status": "verifying",
            },
            "nodes": [
                {"id": "root", "level": 0, "title": "优化 /ai/chat/settings/system/config 页面内容布局 现在太乱了", "status": "in_progress"},
                {"id": "node-1", "level": 1, "title": "整理页面结构", "status": "done", "verification_result": "DOM 结构已按模块拆分"},
                {"id": "node-2", "level": 1, "title": "验证布局调整", "status": "verifying", "verification_result": ""},
            ],
        },
        selected_employee_ids=["emp-1"],
        source="project-chat-test",
        allow_requirement_record=False,
    )

    assert len(saved_memories) == 1
    saved_memory = saved_memories[0]
    assert "workflow:final-summary" in saved_memory.purpose_tags
    assert "[最终结论] 已完成页面布局优化，npm run build 构建通过，人工验证通过。" in saved_memory.content
    assert "[解决状态]" in saved_memory.content


def test_save_project_chat_memory_snapshot_allows_multiple_requirement_records_in_same_chat_session(monkeypatch):
    from routers import projects as projects_router
    from stores.mcp_bridge import Classification, Memory, MemoryScope, MemoryType

    saved_memories = []
    existing_memory = Memory(
        id="mem-existing",
        employee_id="emp-1",
        type=MemoryType.PROJECT_CONTEXT,
        content=(
            "[用户问题] 先前的问题\n"
            "[处理过程] 已生成执行计划，当前只记录需求与计划状态。\n"
            "[解决状态] 执行中\n"
            "[完成条件] 只有所有计划项完成并写入验证结果后，当前需求才算结束。\n"
            "[关联会话] chat-123\n"
            "[执行轨迹JSON] "
            "{\"chat_session_id\":\"chat-123\",\"task_tree_session_id\":\"task-tree-old\","
            "\"task_tree_chat_session_id\":\"chat-123\",\"root_goal\":\"先前的问题\"}"
        ),
        project_name="项目一",
        importance=0.6,
        scope=MemoryScope.TEAM_SHARED,
        classification=Classification.INTERNAL,
        purpose_tags=(
            "auto-capture",
            "project-chat",
            "project-chat-test",
            "workflow:requirement-record",
            "chat-session:chat-123",
            "task-tree-session:task-tree-old",
        ),
    )

    monkeypatch.setattr(
        projects_router,
        "project_store",
        type(
            "DummyProjectStore",
            (),
            {
                "get": staticmethod(lambda project_id: type("DummyProject", (), {"id": project_id, "name": "项目一"})()),
                "list_members": staticmethod(
                    lambda project_id: [
                        type("DummyMember", (), {"employee_id": "emp-1", "enabled": True})(),
                    ]
                ),
            },
        )(),
    )
    monkeypatch.setattr(
        projects_router,
        "employee_store",
        type(
            "DummyEmployeeStore",
            (),
            {
                "get": staticmethod(lambda employee_id: object() if employee_id == "emp-1" else None),
            },
        )(),
    )
    monkeypatch.setattr(
        projects_router,
        "memory_store",
        type(
            "DummyMemoryStore",
            (),
            {
                "new_id": staticmethod(lambda: f"mem-{len(saved_memories) + 1}"),
                "save": staticmethod(lambda memory: saved_memories.append(memory)),
                "recent": staticmethod(lambda employee_id, limit: [existing_memory]),
            },
        )(),
    )

    projects_router._save_project_chat_memory_snapshot(
        project_id="proj-1",
        user_message="当前这个新问题应该单独显示",
        answer="先记录需求，再按计划推进。",
        chat_session_id="chat-123",
        task_tree_payload={
            "id": "task-tree-new",
            "chat_session_id": "chat-123",
            "source_chat_session_id": "chat-123",
            "root_goal": "当前这个新问题应该单独显示",
            "status": "in_progress",
            "current_node": {
                "id": "node-2",
                "title": "梳理新问题",
                "status": "in_progress",
            },
        },
        selected_employee_ids=["emp-1"],
        source="project-chat-test",
    )

    assert len(saved_memories) == 1
    assert "task-tree-session:task-tree-new" in saved_memories[0].purpose_tags
    assert "[用户问题] 当前这个新问题应该单独显示" in saved_memories[0].content


def test_save_project_chat_memory_snapshot_single_selected_employee_stays_private(monkeypatch):
    from routers import projects as projects_router
    from stores.mcp_bridge import MemoryScope

    saved_memories = []

    monkeypatch.setattr(
        projects_router,
        "project_store",
        type(
            "DummyProjectStore",
            (),
            {
                "get": staticmethod(lambda project_id: type("DummyProject", (), {"id": project_id, "name": "项目一"})()),
                "list_members": staticmethod(
                    lambda project_id: [
                        type("DummyMember", (), {"employee_id": "emp-1", "enabled": True})(),
                        type("DummyMember", (), {"employee_id": "emp-2", "enabled": True})(),
                    ]
                ),
            },
        )(),
    )
    monkeypatch.setattr(
        projects_router,
        "employee_store",
        type(
            "DummyEmployeeStore",
            (),
            {
                "get": staticmethod(lambda employee_id: object() if employee_id in {"emp-1", "emp-2"} else None),
            },
        )(),
    )
    monkeypatch.setattr(
        projects_router,
        "memory_store",
        type(
            "DummyMemoryStore",
            (),
            {
                "new_id": staticmethod(lambda: f"mem-{len(saved_memories) + 1}"),
                "save": staticmethod(lambda memory: saved_memories.append(memory)),
            },
        )(),
    )

    projects_router._save_project_chat_memory_snapshot(
        project_id="proj-1",
        user_message="单员工执行时保留明确归属。",
        answer="现在只写到 emp-2 的私有记忆。",
        selected_employee_ids=["emp-2"],
        source="project-chat-test",
    )

    assert len(saved_memories) == 1
    assert saved_memories[0].employee_id == "emp-2"
    assert saved_memories[0].scope == MemoryScope.EMPLOYEE_PRIVATE


def test_save_project_chat_memory_snapshot_all_members_selected_stays_team_shared(monkeypatch):
    from routers import projects as projects_router
    from stores.mcp_bridge import MemoryScope

    saved_memories = []

    monkeypatch.setattr(
        projects_router,
        "project_store",
        type(
            "DummyProjectStore",
            (),
            {
                "get": staticmethod(
                    lambda project_id: type(
                        "DummyProject",
                        (),
                        {"id": project_id, "name": "项目一"},
                    )()
                ),
                "list_members": staticmethod(
                    lambda project_id: [
                        type(
                            "DummyMember",
                            (),
                            {"employee_id": "emp-1", "enabled": True},
                        )(),
                        type(
                            "DummyMember",
                            (),
                            {"employee_id": "emp-2", "enabled": True},
                        )(),
                        type(
                            "DummyMember",
                            (),
                            {"employee_id": "emp-3", "enabled": True},
                        )(),
                    ]
                ),
            },
        )(),
    )
    monkeypatch.setattr(
        projects_router,
        "employee_store",
        type(
            "DummyEmployeeStore",
            (),
            {
                "get": staticmethod(
                    lambda employee_id: object()
                    if employee_id in {"emp-1", "emp-2", "emp-3"}
                    else None
                ),
            },
        )(),
    )
    monkeypatch.setattr(
        projects_router,
        "memory_store",
        type(
            "DummyMemoryStore",
            (),
            {
                "new_id": staticmethod(lambda: f"mem-{len(saved_memories) + 1}"),
                "save": staticmethod(lambda memory: saved_memories.append(memory)),
            },
        )(),
    )

    projects_router._save_project_chat_memory_snapshot(
        project_id="proj-1",
        user_message="不要把同一条问题写进所有员工私有记忆。",
        answer="当 selected_employee_ids 覆盖项目全员时，应退回团队共享记录。",
        selected_employee_ids=["emp-1", "emp-2", "emp-3"],
        source="project-chat-test",
    )

    assert len(saved_memories) == 1
    assert saved_memories[0].employee_id == "emp-1"
    assert saved_memories[0].scope == MemoryScope.TEAM_SHARED


def test_serialize_project_work_session_summary_without_employee_uses_team_label():
    from routers import projects as projects_router

    payload = projects_router._serialize_project_work_session_summary(
        {
            "session_id": "sess-1",
            "employee_id": "",
            "latest_status": "in_progress",
        },
        {},
    )

    assert payload["employee_id"] == ""
    assert payload["employee_name"] == "团队协作"


def test_query_mcp_save_project_memory_without_employee_id_stays_single_shared(monkeypatch):
    from services import dynamic_mcp_apps_query as query_mcp_svc
    from stores.mcp_bridge import MemoryScope, MemoryType

    registered_tools = {}
    registered_resources = {}

    class DummyMCP:
        def tool(self, *args, **kwargs):
            def decorator(fn):
                registered_tools[fn.__name__] = fn
                return fn
            return decorator

        def resource(self, uri: str, *args, **kwargs):
            def decorator(fn):
                registered_resources[uri] = fn
                return fn
            return decorator

    saved_memories = []

    monkeypatch.setattr(query_mcp_svc, "FastMCP", lambda *args, **kwargs: DummyMCP())
    monkeypatch.setattr(
        query_mcp_svc,
        "project_store",
        type(
            "DummyProjectStore",
            (),
            {
                "get": staticmethod(lambda project_id: type("DummyProject", (), {"id": project_id, "name": "项目一"})()),
                "list_all": staticmethod(lambda: []),
                "list_members": staticmethod(
                    lambda project_id: [
                        type("DummyMember", (), {"employee_id": "emp-1", "enabled": True})(),
                        type("DummyMember", (), {"employee_id": "emp-2", "enabled": True})(),
                    ]
                ),
            },
        )(),
    )
    monkeypatch.setattr(
        query_mcp_svc,
        "employee_store",
        type(
            "DummyEmployeeStore",
            (),
            {
                "get": staticmethod(lambda employee_id: object() if employee_id in {"emp-1", "emp-2"} else None),
                "list_all": staticmethod(lambda: []),
            },
        )(),
    )
    monkeypatch.setattr(query_mcp_svc, "list_project_member_profiles_runtime", lambda *args, **kwargs: [])
    monkeypatch.setattr(query_mcp_svc, "query_project_rules_runtime", lambda *args, **kwargs: [])
    monkeypatch.setattr(query_mcp_svc, "project_ui_rule_summary", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        query_mcp_svc,
        "memory_store",
        type(
            "DummyMemoryStore",
            (),
            {
                "new_id": staticmethod(lambda: f"mem-{len(saved_memories) + 1}"),
                "save": staticmethod(lambda memory: saved_memories.append(memory)),
            },
        )(),
    )

    query_mcp_svc.create_query_mcp()

    result = registered_tools["save_project_memory"](
        "proj-1",
        "问题：项目级记忆不该扇出到所有员工\n结论：统一入口应只写一条共享记忆",
    )

    assert result["status"] == "saved"
    assert result["saved_count"] == 1
    assert result["employee_ids"] == ["emp-1"]
    assert result["scope"] == MemoryScope.TEAM_SHARED.value
    assert saved_memories[0].employee_id == "emp-1"
    assert saved_memories[0].scope == MemoryScope.TEAM_SHARED
    assert saved_memories[0].type == MemoryType.PROJECT_CONTEXT


def test_query_mcp_bind_project_context_stores_session_context_and_task_tree(monkeypatch):
    import services.project_chat_task_tree as task_tree_svc
    from contextvars import ContextVar
    from services import dynamic_mcp_apps_query as query_mcp_svc

    registered_tools = {}
    registered_resources = {}
    session_contexts = {}
    ensure_calls = []

    class DummyMCP:
        def tool(self, *args, **kwargs):
            def decorator(fn):
                registered_tools[fn.__name__] = fn
                return fn

            return decorator

        def resource(self, uri: str, *args, **kwargs):
            def decorator(fn):
                registered_resources[uri] = fn
                return fn

            return decorator

    monkeypatch.setattr(query_mcp_svc, "FastMCP", lambda *args, **kwargs: DummyMCP())
    monkeypatch.setattr(
        query_mcp_svc,
        "project_store",
        type(
            "DummyProjectStore",
            (),
            {
                "get": staticmethod(lambda project_id: type("DummyProject", (), {"id": project_id, "name": "项目一"})()),
                "list_all": staticmethod(lambda: []),
                "list_members": staticmethod(lambda project_id: []),
            },
        )(),
    )
    monkeypatch.setattr(
        query_mcp_svc,
        "_resolve_relevant_context_payload",
        lambda task, project_id="", employee_id="", limit=5: {
            "task": task,
            "project_id": project_id,
            "employee_id": employee_id,
            "limit": limit,
            "matched_projects": [],
            "matched_employees": [],
            "matched_rules": [],
            "matched_members": [],
            "matched_tools": [],
        },
    )
    monkeypatch.setattr(
        query_mcp_svc,
        "_generate_execution_plan_payload",
        lambda task, project_id="", employee_id="", max_steps=6: {
            "task": task,
            "project_id": project_id,
            "employee_id": employee_id,
            "plan_steps": [{"step": "先统一检索项目上下文"}],
            "plan_step_count": 1,
            "max_steps": max_steps,
        },
    )
    monkeypatch.setattr(
        task_tree_svc,
        "ensure_task_tree",
        lambda **kwargs: ensure_calls.append(kwargs) or kwargs,
    )
    monkeypatch.setattr(
        task_tree_svc,
        "serialize_task_tree",
        lambda session: {
            "root_goal": session["root_goal"],
            "chat_session_id": session["chat_session_id"],
        },
    )

    username_ctx = ContextVar("query_user", default="")
    session_ctx = ContextVar("query_session", default="")
    username_ctx.set("admin")
    session_ctx.set("transport-123")

    query_mcp_svc.create_query_mcp(
        current_key_owner_username_ctx=username_ctx,
        current_mcp_session_id_ctx=session_ctx,
        session_contexts=session_contexts,
    )

    result = registered_tools["bind_project_context"](
        "proj-1",
        chat_session_id="chat-123",
        root_goal="修复 CLI 对话任务树",
    )

    assert result["status"] == "bound"
    assert result["chat_session_id"] == "chat-123"
    assert result["task_tree"]["root_goal"] == "修复 CLI 对话任务树"
    assert session_contexts["transport-123"]["project_id"] == "proj-1"
    assert session_contexts["transport-123"]["chat_session_id"] == "chat-123"
    assert ensure_calls[0]["username"] == "admin"
    assert ensure_calls[0]["chat_session_id"] == "chat-123"


def test_query_mcp_bind_project_context_without_active_session_creates_detached_task_tree(monkeypatch):
    import services.project_chat_task_tree as task_tree_svc
    from services import dynamic_mcp_apps_query as query_mcp_svc

    registered_tools = {}
    ensure_calls = []

    class DummyMCP:
        def tool(self, *args, **kwargs):
            def decorator(fn):
                registered_tools[fn.__name__] = fn
                return fn

            return decorator

        def resource(self, uri: str, *args, **kwargs):
            def decorator(fn):
                return fn

            return decorator

    monkeypatch.setattr(query_mcp_svc, "FastMCP", lambda *args, **kwargs: DummyMCP())
    monkeypatch.setattr(
        query_mcp_svc,
        "project_store",
        type(
            "DummyProjectStore",
            (),
            {
                "get": staticmethod(lambda project_id: type("DummyProject", (), {"id": project_id, "name": "项目一"})()),
                "list_all": staticmethod(lambda: []),
                "list_members": staticmethod(lambda project_id: []),
            },
        )(),
    )
    monkeypatch.setattr(
        task_tree_svc,
        "ensure_task_tree",
        lambda **kwargs: ensure_calls.append(kwargs) or kwargs,
    )
    monkeypatch.setattr(
        task_tree_svc,
        "serialize_task_tree",
        lambda session: {
            "root_goal": session["root_goal"],
            "chat_session_id": session["chat_session_id"],
        },
    )

    query_mcp_svc.create_query_mcp()

    result = registered_tools["bind_project_context"](
        "proj-1",
        chat_session_id="chat-123",
        root_goal="修复 CLI 对话任务树",
    )

    assert result["status"] == "bound_detached"
    assert result["binding_mode"] == "detached"
    assert result["chat_session_id"] == "chat-123"
    assert result["task_tree"]["root_goal"] == "修复 CLI 对话任务树"
    assert ensure_calls[0]["username"] == "mcp-user"
    assert ensure_calls[0]["chat_session_id"] == "chat-123"


def test_query_mcp_search_ids_does_not_bootstrap_task_tree_from_active_session(monkeypatch):
    import services.project_chat_task_tree as task_tree_svc
    from contextvars import ContextVar
    from services import dynamic_mcp_apps_query as query_mcp_svc

    registered_tools = {}
    ensure_calls = []
    session_contexts = {}

    class DummyMCP:
        def tool(self, *args, **kwargs):
            def decorator(fn):
                registered_tools[fn.__name__] = fn
                return fn

            return decorator

        def resource(self, uri: str, *args, **kwargs):
            def decorator(fn):
                return fn

            return decorator

    monkeypatch.setattr(query_mcp_svc, "FastMCP", lambda *args, **kwargs: DummyMCP())
    monkeypatch.setattr(
        task_tree_svc,
        "ensure_task_tree",
        lambda **kwargs: ensure_calls.append(kwargs) or kwargs,
    )
    username_ctx = ContextVar("query_user_search_ids", default="")
    session_ctx = ContextVar("query_session_search_ids", default="")
    username_ctx.set("admin")
    session_ctx.set("transport-456")

    query_mcp_svc.create_query_mcp(
        current_key_owner_username_ctx=username_ctx,
        current_mcp_session_id_ctx=session_ctx,
        session_contexts=session_contexts,
    )

    result = registered_tools["search_ids"](
        "当前项目员工都有谁",
        project_id="proj-1",
    )

    assert "task_tree" not in result
    assert session_contexts == {}
    assert ensure_calls == []


def test_query_mcp_save_project_memory_audits_lookup_task_tree(monkeypatch):
    import services.project_chat_task_tree as task_tree_svc
    from contextvars import ContextVar
    from services import dynamic_mcp_apps_query as query_mcp_svc
    from stores.mcp_bridge import MemoryType

    registered_tools = {}
    save_calls = []
    lookup_calls = []

    class DummyMCP:
        def tool(self, *args, **kwargs):
            def decorator(fn):
                registered_tools[fn.__name__] = fn
                return fn

            return decorator

        def resource(self, uri: str, *args, **kwargs):
            def decorator(fn):
                return fn

            return decorator

    monkeypatch.setattr(query_mcp_svc, "FastMCP", lambda *args, **kwargs: DummyMCP())
    monkeypatch.setattr(
        query_mcp_svc,
        "project_store",
        type(
            "DummyProjectStore",
            (),
            {
                "get": staticmethod(lambda project_id: type("DummyProject", (), {"id": project_id, "name": "项目一"})()),
                "list_all": staticmethod(lambda: []),
                "list_members": staticmethod(lambda project_id: []),
            },
        )(),
    )
    monkeypatch.setattr(query_mcp_svc, "_active_project_employee_ids", lambda project_id: ["emp-1"])
    monkeypatch.setattr(
        query_mcp_svc,
        "_save_project_memory_entries",
        lambda **kwargs: save_calls.append(kwargs) or {
            "status": "saved",
            "project_id": kwargs["project_id"],
            "type": kwargs["memory_type"].value if isinstance(kwargs["memory_type"], MemoryType) else str(kwargs["memory_type"]),
        },
    )
    monkeypatch.setattr(
        task_tree_svc,
        "get_task_tree_for_chat_session",
        lambda project_id, username, chat_session_id: lookup_calls.append(
            {
                "project_id": project_id,
                "username": username,
                "chat_session_id": chat_session_id,
            }
        )
        or {
            "project_id": project_id,
            "username": username,
            "chat_session_id": chat_session_id,
            "root_goal": "当前项目员工都有谁",
        },
    )
    monkeypatch.setattr(
        task_tree_svc,
        "serialize_task_tree",
        lambda session: {
            "id": "task-tree-lookup",
            "root_goal": session["root_goal"],
            "chat_session_id": session["chat_session_id"],
            "source_chat_session_id": session["chat_session_id"],
            "project_id": session["project_id"],
        },
    )
    monkeypatch.setattr(
        task_tree_svc,
        "audit_task_tree_round",
        lambda **kwargs: {
            "code": "lookup_query_auto_completed",
            "chat_session_id": kwargs["chat_session_id"],
            "project_id": kwargs["project_id"],
        },
    )

    username_ctx = ContextVar("query_user_save_memory", default="")
    session_ctx = ContextVar("query_session_save_memory", default="")
    username_ctx.set("admin")
    session_ctx.set("transport-789")
    session_contexts = {
        "transport-789": {
            "project_id": "proj-1",
            "project_name": "项目一",
            "employee_id": "",
            "chat_session_id": "chat-789",
        }
    }

    query_mcp_svc.create_query_mcp(
        current_key_owner_username_ctx=username_ctx,
        current_mcp_session_id_ctx=session_ctx,
        session_contexts=session_contexts,
    )

    result = registered_tools["save_project_memory"](
        project_id="proj-1",
        content="问题：当前项目员工都有谁\n结论：共有 3 名成员。",
        type="key-event",
    )

    assert result["status"] == "saved"
    assert result["task_tree"]["root_goal"] == "当前项目员工都有谁"
    assert result["task_tree"]["chat_session_id"] == "chat-789"
    assert result["task_tree_audit"]["code"] == "lookup_query_auto_completed"
    assert result["task_tree_audit"]["chat_session_id"] == "chat-789"
    assert result["task_tree_audit"]["project_id"] == "proj-1"
    assert lookup_calls == [
        {
            "project_id": "proj-1",
            "username": "admin",
            "chat_session_id": "chat-789",
        }
    ]
    assert "[关联会话] chat-789" in save_calls[0]["content"]
    matched = re.search(r"\[执行轨迹JSON\]\s*([^\n]+)", save_calls[0]["content"])
    assert matched
    assert json.loads(matched.group(1)) == {
        "chat_session_id": "chat-789",
        "root_goal": "当前项目员工都有谁",
        "task_tree_chat_session_id": "chat-789",
        "task_tree_session_id": "task-tree-lookup",
    }
    assert "chat-session:chat-789" in save_calls[0]["purpose_tags"]
    assert "task-tree-session:task-tree-lookup" in save_calls[0]["purpose_tags"]


def test_query_mcp_list_project_members_audits_lookup_task_tree_on_direct_call(monkeypatch):
    import services.project_chat_task_tree as task_tree_svc
    from contextvars import ContextVar
    from services import dynamic_mcp_apps_query as query_mcp_svc

    registered_tools = {}
    audit_calls = []

    class DummyMCP:
        def tool(self, *args, **kwargs):
            def decorator(fn):
                registered_tools[fn.__name__] = fn
                return fn

            return decorator

        def resource(self, uri: str, *args, **kwargs):
            def decorator(fn):
                return fn

            return decorator

    monkeypatch.setattr(query_mcp_svc, "FastMCP", lambda *args, **kwargs: DummyMCP())
    monkeypatch.setattr(
        query_mcp_svc,
        "project_store",
        type(
            "DummyProjectStore",
            (),
            {
                "get": staticmethod(lambda project_id: type("DummyProject", (), {"id": project_id, "name": "项目一"})()),
                "list_all": staticmethod(lambda: []),
                "list_members": staticmethod(lambda project_id: []),
            },
        )(),
    )
    monkeypatch.setattr(
        query_mcp_svc,
        "list_project_member_profiles_runtime",
        lambda project_id, include_disabled=False, include_missing=False, rule_limit=30: [
            {"employee_id": "emp-1", "name": "产品专员"},
            {"employee_id": "emp-2", "name": "后端工程师"},
        ]
        if project_id == "proj-1"
        else [],
    )
    monkeypatch.setattr(
        task_tree_svc,
        "audit_task_tree_round",
        lambda **kwargs: audit_calls.append(kwargs)
        or {
            "code": "lookup_query_auto_completed",
            "chat_session_id": kwargs["chat_session_id"],
            "project_id": kwargs["project_id"],
        },
    )

    username_ctx = ContextVar("query_user_members_audit", default="")
    session_ctx = ContextVar("query_session_members_audit", default="")
    username_ctx.set("admin")
    session_ctx.set("transport-members-1")
    session_contexts = {
        "transport-members-1": {
            "project_id": "proj-1",
            "project_name": "项目一",
            "employee_id": "",
            "chat_session_id": "chat-members-1",
        }
    }

    query_mcp_svc.create_query_mcp(
        current_key_owner_username_ctx=username_ctx,
        current_mcp_session_id_ctx=session_ctx,
        session_contexts=session_contexts,
    )

    result = registered_tools["list_project_members"]("proj-1")

    assert result["project_id"] == "proj-1"
    assert result["total"] == 2
    assert result["task_tree_audit"]["code"] == "lookup_query_auto_completed"
    assert result["task_tree_audit"]["chat_session_id"] == "chat-members-1"
    assert audit_calls == [
        {
            "project_id": "proj-1",
            "username": "admin",
            "chat_session_id": "chat-members-1",
            "assistant_content": "已获取项目成员列表，共 2 名。 成员包括：产品专员、后端工程师。",
            "successful_tool_names": ["list_project_members"],
        }
    ]


def test_query_mcp_work_session_tools_sync_task_tree_progress(monkeypatch):
    import services.project_chat_task_tree as task_tree_svc
    from contextvars import ContextVar
    from services import dynamic_mcp_apps_query as query_mcp_svc
    from stores.mcp_bridge import MemoryType

    registered_tools = {}
    save_calls = []
    update_calls = []

    class DummyMCP:
        def tool(self, *args, **kwargs):
            def decorator(fn):
                registered_tools[fn.__name__] = fn
                return fn

            return decorator

        def resource(self, uri: str, *args, **kwargs):
            def decorator(fn):
                return fn

            return decorator

    monkeypatch.setattr(query_mcp_svc, "FastMCP", lambda *args, **kwargs: DummyMCP())
    monkeypatch.setattr(
        query_mcp_svc,
        "project_store",
        type(
            "DummyProjectStore",
            (),
            {
                "get": staticmethod(lambda project_id: type("DummyProject", (), {"id": project_id, "name": "项目一"})()),
                "list_all": staticmethod(lambda: []),
                "list_members": staticmethod(lambda project_id: []),
            },
        )(),
    )
    monkeypatch.setattr(query_mcp_svc, "_active_project_employee_ids", lambda project_id: ["emp-1"])
    monkeypatch.setattr(
        query_mcp_svc,
        "_save_project_memory_entries",
        lambda **kwargs: save_calls.append(kwargs) or {
            "status": "saved",
            "project_id": kwargs["project_id"],
            "type": kwargs["memory_type"].value if isinstance(kwargs["memory_type"], MemoryType) else str(kwargs["memory_type"]),
        },
    )
    monkeypatch.setattr(
        query_mcp_svc,
        "_save_work_session_event_record",
        lambda **kwargs: {"status": "saved", "event_id": "wse-1"},
    )

    session_state = {
        "id": "task-tree-1",
        "project_id": "proj-1",
        "chat_session_id": "chat-456",
        "root_goal": "修复任务树展示与进度同步问题",
        "current_node_id": "node-impl",
        "nodes": [
            {
                "id": "node-root",
                "parent_id": "",
                "stage_key": "goal",
                "title": "修复任务树展示与进度同步问题",
                "status": "in_progress",
                "verification_result": "",
                "sort_order": 0,
                "level": 0,
            },
            {
                "id": "node-analysis",
                "parent_id": "node-root",
                "stage_key": "analysis",
                "title": "定位当前问题",
                "status": "done",
                "verification_result": "已确认触发条件和影响范围。",
                "sort_order": 1,
                "level": 1,
            },
            {
                "id": "node-impl",
                "parent_id": "node-root",
                "stage_key": "implementation",
                "title": "修复核心问题",
                "status": "pending",
                "verification_result": "",
                "sort_order": 2,
                "level": 1,
            },
            {
                "id": "node-verify",
                "parent_id": "node-root",
                "stage_key": "verification",
                "title": "验证结果并完成本轮收尾",
                "status": "pending",
                "verification_result": "",
                "sort_order": 3,
                "level": 1,
            },
        ],
    }

    def recompute_state():
        leaf_nodes = [node for node in session_state["nodes"] if node["parent_id"]]
        done_leaf_nodes = [node for node in leaf_nodes if node["status"] == "done"]
        session_state["progress_percent"] = int(round((len(done_leaf_nodes) / max(len(leaf_nodes), 1)) * 100))
        root_node = next(node for node in session_state["nodes"] if not node["parent_id"])
        if root_node["status"] == "done":
            pass
        elif any(node["status"] in {"in_progress", "verifying", "done"} for node in leaf_nodes):
            root_node["status"] = "in_progress"
        else:
            root_node["status"] = "pending"
        current = next((node for node in session_state["nodes"] if node["id"] == session_state["current_node_id"]), None)
        if current is None or current["status"] == "done":
            next_node = next((node for node in leaf_nodes if node["status"] != "done"), root_node)
            session_state["current_node_id"] = next_node["id"]

    recompute_state()

    def fake_get_task_tree_for_chat_session(project_id, username, chat_session_id):
        _ = (project_id, username, chat_session_id)
        recompute_state()
        current_node = next(node for node in session_state["nodes"] if node["id"] == session_state["current_node_id"])
        return {
            **session_state,
            "status": next(node for node in session_state["nodes"] if node["id"] == "node-root")["status"],
            "current_node": dict(current_node),
        }

    def fake_ensure_task_tree(**kwargs):
        _ = kwargs
        recompute_state()
        current_node = next(node for node in session_state["nodes"] if node["id"] == session_state["current_node_id"])
        return {
            **session_state,
            "status": next(node for node in session_state["nodes"] if node["id"] == "node-root")["status"],
            "current_node": dict(current_node),
        }

    def fake_update_task_node(**kwargs):
        update_calls.append(kwargs)
        target = next(node for node in session_state["nodes"] if node["id"] == kwargs["node_id"])
        if kwargs.get("status"):
            target["status"] = kwargs["status"]
        if kwargs.get("verification_result") is not None:
            target["verification_result"] = kwargs["verification_result"]
        if kwargs.get("summary_for_model") is not None:
            target["summary_for_model"] = kwargs["summary_for_model"]
        if kwargs.get("is_current") is True:
            session_state["current_node_id"] = target["id"]
        elif kwargs.get("is_current") is False and session_state["current_node_id"] == target["id"]:
            session_state["current_node_id"] = ""
        recompute_state()
        current_node = next(node for node in session_state["nodes"] if node["id"] == session_state["current_node_id"])
        return {
            **session_state,
            "status": next(node for node in session_state["nodes"] if node["id"] == "node-root")["status"],
            "current_node": dict(current_node),
        }

    monkeypatch.setattr(task_tree_svc, "ensure_task_tree", fake_ensure_task_tree)
    monkeypatch.setattr(task_tree_svc, "get_task_tree_for_chat_session", fake_get_task_tree_for_chat_session)
    monkeypatch.setattr(task_tree_svc, "update_task_node", fake_update_task_node)
    monkeypatch.setattr(task_tree_svc, "serialize_task_tree", lambda session: dict(session) if isinstance(session, dict) else None)

    username_ctx = ContextVar("query_user_work_facts", default="")
    session_ctx = ContextVar("query_session_work_facts", default="")
    username_ctx.set("admin")
    session_ctx.set("transport-456")
    session_contexts = {
        "transport-456": {
            "project_id": "proj-1",
            "project_name": "项目一",
            "employee_id": "",
            "chat_session_id": "chat-456",
        }
    }

    query_mcp_svc.create_query_mcp(
        current_key_owner_username_ctx=username_ctx,
        current_mcp_session_id_ctx=session_ctx,
        session_contexts=session_contexts,
    )

    save_result = registered_tools["save_work_facts"](
        "proj-1",
        facts=["已定位任务树展示层编号问题"],
        employee_id="emp-1",
        session_id="ws-1",
        phase="implementation",
        step="修复核心问题",
        status="in_progress",
        goal="修复任务树展示与进度同步问题",
        verification=["静态检查通过"],
    )
    event_result = registered_tools["append_session_event"](
        "proj-1",
        session_id="ws-1",
        event_type="verification",
        content="已完成任务树同步修复",
        employee_id="emp-1",
        phase="verification",
        step="验证结果并完成本轮收尾",
        status="completed",
        verification=["npm run build 通过"],
    )

    assert save_result["status"] == "saved"
    assert save_result["task_tree"]["chat_session_id"] == "chat-456"
    assert save_result["task_tree"]["current_node"]["status"] == "in_progress"
    assert save_result["trajectory"]["task_tree_session_id"] == "task-tree-1"
    assert save_result["trajectory"]["task_node_id"] == "node-impl"
    assert save_result["trajectory"]["task_node_title"] == "修复核心问题"
    assert event_result["status"] == "saved"
    assert event_result["task_tree"]["progress_percent"] == 100
    assert event_result["task_tree"]["status"] == "done"
    assert event_result["task_tree"]["current_node"]["id"] == "node-root"
    assert event_result["trajectory"]["task_tree_session_id"] == "task-tree-1"
    assert event_result["trajectory"]["task_node_id"] == "node-verify"
    assert update_calls[0]["status"] == "in_progress"
    assert update_calls[0]["node_id"] == "node-impl"
    assert update_calls[1]["status"] == "done"
    assert update_calls[1]["node_id"] == "node-impl"
    assert "静态检查通过" in update_calls[1]["verification_result"]
    assert update_calls[2]["status"] == "done"
    assert update_calls[2]["node_id"] == "node-verify"
    assert "npm run build 通过" in update_calls[2]["verification_result"]
    assert update_calls[3]["status"] == "done"
    assert update_calls[3]["node_id"] == "node-root"
    assert save_calls[0]["content"].endswith("[关联会话] chat-456")
    assert save_calls[1]["content"].endswith("[关联会话] chat-456")


def test_query_mcp_phase_switch_auto_completes_previous_node_without_explicit_verification(monkeypatch):
    import services.project_chat_task_tree as task_tree_svc
    from contextvars import ContextVar
    from services import dynamic_mcp_apps_query as query_mcp_svc
    from stores.mcp_bridge import MemoryType

    registered_tools = {}
    update_calls = []

    class DummyMCP:
        def tool(self, *args, **kwargs):
            def decorator(fn):
                registered_tools[fn.__name__] = fn
                return fn

            return decorator

        def resource(self, uri: str, *args, **kwargs):
            def decorator(fn):
                return fn

            return decorator

    monkeypatch.setattr(query_mcp_svc, "FastMCP", lambda *args, **kwargs: DummyMCP())
    monkeypatch.setattr(
        query_mcp_svc,
        "project_store",
        type(
            "DummyProjectStore",
            (),
            {
                "get": staticmethod(lambda project_id: type("DummyProject", (), {"id": project_id, "name": "项目一"})()),
                "list_all": staticmethod(lambda: []),
                "list_members": staticmethod(lambda project_id: []),
            },
        )(),
    )
    monkeypatch.setattr(query_mcp_svc, "_active_project_employee_ids", lambda project_id: ["emp-1"])
    monkeypatch.setattr(
        query_mcp_svc,
        "_save_project_memory_entries",
        lambda **kwargs: {
            "status": "saved",
            "project_id": kwargs["project_id"],
            "type": kwargs["memory_type"].value if isinstance(kwargs["memory_type"], MemoryType) else str(kwargs["memory_type"]),
        },
    )
    monkeypatch.setattr(
        query_mcp_svc,
        "_save_work_session_event_record",
        lambda **kwargs: {"status": "saved", "event_id": "wse-1"},
    )

    session_state = {
        "id": "task-tree-2",
        "project_id": "proj-1",
        "chat_session_id": "chat-789",
        "root_goal": "修复切步骤时任务树不收口的问题",
        "current_node_id": "node-analysis",
        "nodes": [
            {
                "id": "node-root",
                "parent_id": "",
                "stage_key": "goal",
                "title": "修复切步骤时任务树不收口的问题",
                "status": "in_progress",
                "verification_result": "",
                "sort_order": 0,
                "level": 0,
            },
            {
                "id": "node-analysis",
                "parent_id": "node-root",
                "stage_key": "analysis",
                "title": "定位当前问题",
                "status": "in_progress",
                "verification_result": "",
                "summary_for_model": "",
                "sort_order": 1,
                "level": 1,
            },
            {
                "id": "node-impl",
                "parent_id": "node-root",
                "stage_key": "implementation",
                "title": "修复核心问题",
                "status": "pending",
                "verification_result": "",
                "summary_for_model": "",
                "sort_order": 2,
                "level": 1,
            },
            {
                "id": "node-verify",
                "parent_id": "node-root",
                "stage_key": "verification",
                "title": "验证结果并完成本轮收尾",
                "status": "pending",
                "verification_result": "",
                "summary_for_model": "",
                "sort_order": 3,
                "level": 1,
            },
        ],
    }

    def recompute_state():
        leaf_nodes = [node for node in session_state["nodes"] if node["parent_id"]]
        done_leaf_nodes = [node for node in leaf_nodes if node["status"] == "done"]
        session_state["progress_percent"] = int(round((len(done_leaf_nodes) / max(len(leaf_nodes), 1)) * 100))
        root_node = next(node for node in session_state["nodes"] if not node["parent_id"])
        if root_node["status"] == "done":
            pass
        elif any(node["status"] in {"in_progress", "verifying", "done"} for node in leaf_nodes):
            root_node["status"] = "in_progress"
        else:
            root_node["status"] = "pending"
        current = next((node for node in session_state["nodes"] if node["id"] == session_state["current_node_id"]), None)
        if current is None or current["status"] == "done":
            next_node = next((node for node in leaf_nodes if node["status"] != "done"), root_node)
            session_state["current_node_id"] = next_node["id"]

    recompute_state()

    def fake_get_task_tree_for_chat_session(project_id, username, chat_session_id):
        _ = (project_id, username, chat_session_id)
        recompute_state()
        current_node = next(node for node in session_state["nodes"] if node["id"] == session_state["current_node_id"])
        return {
            **session_state,
            "status": next(node for node in session_state["nodes"] if node["id"] == "node-root")["status"],
            "current_node": dict(current_node),
        }

    def fake_ensure_task_tree(**kwargs):
        _ = kwargs
        recompute_state()
        current_node = next(node for node in session_state["nodes"] if node["id"] == session_state["current_node_id"])
        return {
            **session_state,
            "status": next(node for node in session_state["nodes"] if node["id"] == "node-root")["status"],
            "current_node": dict(current_node),
        }

    def fake_update_task_node(**kwargs):
        update_calls.append(kwargs)
        target = next(node for node in session_state["nodes"] if node["id"] == kwargs["node_id"])
        if kwargs.get("status"):
            target["status"] = kwargs["status"]
        if kwargs.get("verification_result") is not None:
            target["verification_result"] = kwargs["verification_result"]
        if kwargs.get("summary_for_model") is not None:
            target["summary_for_model"] = kwargs["summary_for_model"]
        if kwargs.get("is_current") is True:
            session_state["current_node_id"] = target["id"]
        elif kwargs.get("is_current") is False and session_state["current_node_id"] == target["id"]:
            session_state["current_node_id"] = ""
        recompute_state()
        current_node = next(node for node in session_state["nodes"] if node["id"] == session_state["current_node_id"])
        return {
            **session_state,
            "status": next(node for node in session_state["nodes"] if node["id"] == "node-root")["status"],
            "current_node": dict(current_node),
        }

    monkeypatch.setattr(task_tree_svc, "ensure_task_tree", fake_ensure_task_tree)
    monkeypatch.setattr(task_tree_svc, "get_task_tree_for_chat_session", fake_get_task_tree_for_chat_session)
    monkeypatch.setattr(task_tree_svc, "update_task_node", fake_update_task_node)
    monkeypatch.setattr(task_tree_svc, "serialize_task_tree", lambda session: dict(session) if isinstance(session, dict) else None)

    username_ctx = ContextVar("query_user_work_facts_phase_switch", default="")
    session_ctx = ContextVar("query_session_work_facts_phase_switch", default="")
    username_ctx.set("admin")
    session_ctx.set("transport-789")
    session_contexts = {
        "transport-789": {
            "project_id": "proj-1",
            "project_name": "项目一",
            "employee_id": "",
            "chat_session_id": "chat-789",
        }
    }

    query_mcp_svc.create_query_mcp(
        current_key_owner_username_ctx=username_ctx,
        current_mcp_session_id_ctx=session_ctx,
        session_contexts=session_contexts,
    )

    result = registered_tools["save_work_facts"](
        "proj-1",
        facts=["开始进入修复阶段"],
        employee_id="emp-1",
        session_id="ws-2",
        phase="implementation",
        step="修复核心问题",
        status="in_progress",
        goal="修复切步骤时任务树不收口的问题",
    )

    assert result["status"] == "saved"
    assert result["trajectory"]["task_node_id"] == "node-impl"
    assert update_calls[0]["node_id"] == "node-analysis"
    assert update_calls[0]["status"] == "done"
    assert "已进入“修复核心问题”" in update_calls[0]["verification_result"]
    assert update_calls[1]["node_id"] == "node-impl"
    assert update_calls[1]["status"] == "in_progress"


def test_query_mcp_planning_tools_attach_task_tree(monkeypatch):
    import services.project_chat_task_tree as task_tree_svc
    from contextvars import ContextVar
    from services import dynamic_mcp_apps_query as query_mcp_svc

    registered_tools = {}
    ensure_calls = []
    session_contexts = {
        "transport-321": {
            "project_id": "proj-1",
            "project_name": "项目一",
            "employee_id": "",
            "chat_session_id": "chat-321",
        }
    }

    class DummyMCP:
        def tool(self, *args, **kwargs):
            def decorator(fn):
                registered_tools[fn.__name__] = fn
                return fn

            return decorator

        def resource(self, uri: str, *args, **kwargs):
            def decorator(fn):
                return fn

            return decorator

    monkeypatch.setattr(query_mcp_svc, "FastMCP", lambda *args, **kwargs: DummyMCP())
    monkeypatch.setattr(
        query_mcp_svc,
        "project_store",
        type(
            "DummyProjectStore",
            (),
            {
                "get": staticmethod(lambda project_id: type("DummyProject", (), {"id": project_id, "name": "项目一"})()),
                "list_all": staticmethod(lambda: []),
                "list_members": staticmethod(lambda project_id: []),
            },
        )(),
    )
    monkeypatch.setattr(
        query_mcp_svc,
        "_resolve_relevant_context_payload",
        lambda task, project_id="", employee_id="", limit=5: {
            "task": task,
            "project_id": project_id,
            "employee_id": employee_id,
            "limit": limit,
            "matched_projects": [],
            "matched_employees": [],
            "matched_rules": [],
            "matched_members": [],
            "matched_tools": [],
        },
    )
    monkeypatch.setattr(
        query_mcp_svc,
        "_generate_execution_plan_payload",
        lambda task, project_id="", employee_id="", max_steps=6: {
            "task": task,
            "project_id": project_id,
            "employee_id": employee_id,
            "plan_steps": [{"step": "先统一检索项目上下文"}],
            "plan_step_count": 1,
            "max_steps": max_steps,
        },
    )
    monkeypatch.setattr(
        task_tree_svc,
        "ensure_task_tree",
        lambda **kwargs: ensure_calls.append(kwargs) or kwargs,
    )
    monkeypatch.setattr(
        task_tree_svc,
        "serialize_task_tree",
        lambda session: {
            "root_goal": session["root_goal"],
            "chat_session_id": session["chat_session_id"],
            "project_id": session["project_id"],
            "max_steps": session.get("max_steps", 6),
            "forced": bool(session.get("force")),
        },
    )

    username_ctx = ContextVar("query_user_planning_tools", default="")
    session_ctx = ContextVar("query_session_planning_tools", default="")
    username_ctx.set("admin")
    session_ctx.set("transport-321")

    query_mcp_svc.create_query_mcp(
        current_key_owner_username_ctx=username_ctx,
        current_mcp_session_id_ctx=session_ctx,
        session_contexts=session_contexts,
    )

    analyze_result = registered_tools["analyze_task"](
        "根据项目 UI 规则优化记忆详情弹框内容",
        project_id="proj-1",
    )
    context_result = registered_tools["resolve_relevant_context"](
        "根据项目 UI 规则优化记忆详情弹框内容",
        project_id="proj-1",
    )
    plan_result = registered_tools["generate_execution_plan"](
        "根据项目 UI 规则优化记忆详情弹框内容",
        project_id="proj-1",
        max_steps=8,
    )

    assert analyze_result["task_tree"]["root_goal"] == "根据项目 UI 规则优化记忆详情弹框内容"
    assert analyze_result["task_tree"]["chat_session_id"] == "chat-321"
    assert context_result["task_tree"]["project_id"] == "proj-1"
    assert plan_result["task_tree"]["max_steps"] == 8
    assert plan_result["task_tree"]["forced"] is True
    assert ensure_calls == [
        {
            "project_id": "proj-1",
            "username": "admin",
            "chat_session_id": "chat-321",
            "root_goal": "根据项目 UI 规则优化记忆详情弹框内容",
        },
        {
            "project_id": "proj-1",
            "username": "admin",
            "chat_session_id": "chat-321",
            "root_goal": "根据项目 UI 规则优化记忆详情弹框内容",
        },
        {
            "project_id": "proj-1",
            "username": "admin",
            "chat_session_id": "chat-321",
            "root_goal": "根据项目 UI 规则优化记忆详情弹框内容",
            "max_steps": 8,
            "force": True,
        },
    ]


class _FakeMemoryStore:
    def __init__(self, memories):
        self._memories = {item.id: item for item in memories}

    def list_by_employee(self, employee_id: str):
        return [item for item in self._memories.values() if item.employee_id == employee_id]

    def get(self, memory_id: str):
        return self._memories.get(memory_id)

    def delete(self, memory_id: str) -> bool:
        return self._memories.pop(memory_id, None) is not None


def _build_memory_test_client(tmp_path, monkeypatch, auth_payload):
    from core import config as core_config
    from core.deps import require_auth
    from core.server import create_app
    from routers import memory as memory_router
    from stores import factory as store_factory
    from stores.json.employee_store import EmployeeStore
    from stores.json.project_store import ProjectStore

    monkeypatch.setenv("CORE_STORE_BACKEND", "json")
    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()
    for proxy_name in ("employee_store", "project_store", "role_store"):
        getattr(store_factory, proxy_name)._instance = None

    employee_store = EmployeeStore(tmp_path / "data")
    project_store = ProjectStore(tmp_path / "data")
    monkeypatch.setattr(memory_router, "employee_store", employee_store)
    monkeypatch.setattr(memory_router, "project_store", project_store)

    app = create_app()
    app.dependency_overrides[require_auth] = lambda: auth_payload
    client = TestClient(app)
    return client, employee_store, project_store, memory_router


def test_memory_routes_filter_memories_by_project_membership(tmp_path, monkeypatch):
    from routers import memory as memory_router
    from stores.json.employee_store import EmployeeConfig
    from stores.json.project_store import ProjectConfig, ProjectUserMember
    from stores.mcp_bridge import Classification, Memory, MemoryScope, MemoryType

    client, employee_store, project_store, _ = _build_memory_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "alice", "role": "user"},
    )
    employee_store.save(
        EmployeeConfig(
            id="emp-1",
            name="员工一",
            created_by="owner",
            share_scope="all_users",
        )
    )
    project_store.save(ProjectConfig(id="proj-1", name="可见项目"))
    project_store.save(ProjectConfig(id="proj-2", name="隐藏项目"))
    project_store.upsert_user_member(
        ProjectUserMember(project_id="proj-1", username="alice", role="member", enabled=True)
    )
    monkeypatch.setattr(
        memory_router,
        "memory_store",
        _FakeMemoryStore(
            [
                Memory(
                    id="mem-visible",
                    employee_id="emp-1",
                    type=MemoryType.PROJECT_CONTEXT,
                    content="可见项目记忆",
                    project_name="可见项目",
                    importance=0.9,
                    scope=MemoryScope.EMPLOYEE_PRIVATE,
                    classification=Classification.INTERNAL,
                    created_at="2026-03-26T10:00:00+00:00",
                ),
                Memory(
                    id="mem-hidden",
                    employee_id="emp-1",
                    type=MemoryType.PROJECT_CONTEXT,
                    content="隐藏项目记忆",
                    project_name="隐藏项目",
                    importance=0.8,
                    scope=MemoryScope.EMPLOYEE_PRIVATE,
                    classification=Classification.INTERNAL,
                    created_at="2026-03-26T09:00:00+00:00",
                ),
                Memory(
                    id="mem-legacy",
                    employee_id="emp-1",
                    type=MemoryType.KEY_EVENT,
                    content="未绑定项目的旧记忆",
                    project_name="",
                    importance=0.4,
                    scope=MemoryScope.EMPLOYEE_PRIVATE,
                    classification=Classification.INTERNAL,
                    created_at="2026-03-26T08:00:00+00:00",
                ),
            ]
        ),
    )

    response = client.get("/api/memory/emp-1")

    assert response.status_code == 200
    payload = response.json()["memories"]
    assert {item["id"] for item in payload} == {"mem-visible", "mem-legacy"}

    filtered_response = client.get("/api/memory/emp-1", params={"project_name": "可见项目"})

    assert filtered_response.status_code == 200
    filtered_payload = filtered_response.json()["memories"]
    assert [item["id"] for item in filtered_payload] == ["mem-visible"]


def test_memory_delete_returns_404_without_project_access(tmp_path, monkeypatch):
    from stores.json.employee_store import EmployeeConfig
    from stores.json.project_store import ProjectConfig
    from stores.mcp_bridge import Classification, Memory, MemoryScope, MemoryType

    client, employee_store, project_store, memory_router = _build_memory_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "alice", "role": "user"},
    )
    employee_store.save(
        EmployeeConfig(
            id="emp-1",
            name="员工一",
            created_by="owner",
            share_scope="all_users",
        )
    )
    project_store.save(ProjectConfig(id="proj-2", name="隐藏项目"))
    fake_store = _FakeMemoryStore(
        [
            Memory(
                id="mem-hidden",
                employee_id="emp-1",
                type=MemoryType.PROJECT_CONTEXT,
                content="隐藏项目记忆",
                project_name="隐藏项目",
                importance=0.8,
                scope=MemoryScope.EMPLOYEE_PRIVATE,
                classification=Classification.INTERNAL,
                created_at="2026-03-26T09:00:00+00:00",
            )
        ]
    )
    monkeypatch.setattr(memory_router, "memory_store", fake_store)

    response = client.delete("/api/memory/item/mem-hidden")

    assert response.status_code == 404
    assert fake_store.get("mem-hidden") is not None


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
        "invoke_project_builtin_tool",
        lambda project_id, tool_name, employee_id="", args=None, args_json="{}": (
            {"tool_name": "get_project_detail", "id": project_id, "chat_settings": {"auto_use_tools": True}}
            if tool_name == "get_project_detail"
            else {
                "tool_name": "get_project_employee_detail",
                "employee_id": "emp-9",
                "employee_exists": True,
            }
            if tool_name == "get_project_employee_detail"
            else None
        ),
    )
    monkeypatch.setattr(
        runtime_svc,
        "execute_project_collaboration_runtime",
        lambda **kwargs: {
            "tool_name": "execute_project_collaboration",
            "task": kwargs["task"],
            "selected_employee_ids": ["emp-9"],
        },
    )

    project_result = runtime_svc.invoke_project_skill_tool_runtime("proj-test", "get_project_detail")
    employee_result = runtime_svc.invoke_project_skill_tool_runtime(
        "proj-test",
        "get_project_employee_detail",
        args={"employee_id": "emp-9"},
    )
    collaboration_result = runtime_svc.invoke_project_skill_tool_runtime(
        "proj-test",
        "execute_project_collaboration",
        args={"task": "实现一个新页面"},
    )

    assert "get_project_detail" in tool_names
    assert "get_project_employee_detail" in tool_names
    assert "execute_project_collaboration" in tool_names
    assert project_result["tool_name"] == "get_project_detail"
    assert project_result["id"] == "proj-test"
    assert project_result["chat_settings"]["auto_use_tools"] is True
    assert employee_result["tool_name"] == "get_project_employee_detail"
    assert employee_result["employee_id"] == "emp-9"
    assert employee_result["employee_exists"] is True
    assert collaboration_result["tool_name"] == "execute_project_collaboration"
    assert collaboration_result["task"] == "实现一个新页面"
    assert collaboration_result["selected_employee_ids"] == ["emp-9"]


def test_project_collaboration_runtime_selects_members_and_executes_safe_tools(monkeypatch):
    from services import dynamic_mcp_collaboration as collab_svc

    class DummyProject:
        id = "proj-1"
        name = "项目一"

    monkeypatch.setattr(
        collab_svc,
        "project_store",
        type("DummyProjectStore", (), {"get": staticmethod(lambda project_id: DummyProject() if project_id == "proj-1" else None)})(),
    )
    monkeypatch.setattr(
        collab_svc,
        "list_project_member_profiles_runtime",
        lambda project_id, include_disabled=False, include_missing=False, rule_limit=30: [
            {
                "employee_id": "emp-ui",
                "id": "emp-ui",
                "name": "前端开发",
                "goal": "负责页面实现",
                "skill_names": ["vue", "ui"],
                "rule_bindings": [{"id": "rule-ui", "title": "UI 规范", "domain": "ui"}],
            },
            {
                "employee_id": "emp-pm",
                "id": "emp-pm",
                "name": "产品经理",
                "goal": "负责需求拆解",
                "skill_names": ["prd"],
                "rule_bindings": [{"id": "rule-prd", "title": "需求追踪", "domain": "product"}],
            },
        ] if project_id == "proj-1" else [],
    )
    monkeypatch.setattr(
        collab_svc,
        "list_project_proxy_tools_runtime",
        lambda project_id, employee_id="": [
            {
                "tool_name": "emp_ui__skill_vue__page",
                "employee_id": "emp-ui",
                "skill_name": "Vue",
                "description": "实现前端页面",
            }
        ] if project_id == "proj-1" else [],
    )
    monkeypatch.setattr(
        collab_svc,
        "list_project_external_tools_runtime",
        lambda project_id: [
            {
                "tool_name": "ext_plan_task",
                "module_name": "planner",
                "remote_tool_name": "planTask",
                "description": "根据 task 输出执行计划",
                "parameters_schema": {
                    "type": "object",
                    "properties": {"task": {"type": "string"}},
                    "required": ["task"],
                },
            }
        ] if project_id == "proj-1" else [],
    )

    captured_calls: list[dict] = []

    def fake_invoke(**kwargs):
        captured_calls.append(kwargs)
        return {"status": "ok", "tool_name": kwargs["tool_name"]}

    result = collab_svc.execute_project_collaboration_runtime(
        "proj-1",
        "请实现一个新的前端页面并整理方案",
        invoke_tool=fake_invoke,
    )

    assert result["tool_name"] == "execute_project_collaboration"
    assert result["selected_employee_ids"][0] == "emp-ui"
    assert any(item["tool_name"] == "search_project_context" for item in result["executed_calls"])
    assert any(item["tool_name"] == "query_project_rules" for item in result["executed_calls"])
    assert any(item["tool_name"] == "ext_plan_task" for item in result["executed_calls"])
    assert any(item["tool_name"] == "emp_ui__skill_vue__page" for item in result["skipped_calls"])
    assert any(call["tool_name"] == "search_project_context" for call in captured_calls)


def test_project_collaboration_runtime_prefers_external_executor_and_stops_after_success(monkeypatch):
    from services import dynamic_mcp_collaboration as collab_svc

    class DummyProject:
        id = "proj-1"
        name = "项目一"

    monkeypatch.setattr(
        collab_svc,
        "project_store",
        type("DummyProjectStore", (), {"get": staticmethod(lambda project_id: DummyProject() if project_id == "proj-1" else None)})(),
    )
    monkeypatch.setattr(
        collab_svc,
        "list_project_member_profiles_runtime",
        lambda project_id, include_disabled=False, include_missing=False, rule_limit=30: [
            {
                "employee_id": "emp-ui",
                "id": "emp-ui",
                "name": "前端开发",
                "goal": "负责页面实现",
                "skill_names": ["vue", "ui"],
                "rule_bindings": [{"id": "rule-ui", "title": "UI 规范", "domain": "ui"}],
            },
            {
                "employee_id": "emp-api",
                "id": "emp-api",
                "name": "后端开发",
                "goal": "负责接口实现",
                "skill_names": ["python", "api"],
                "rule_bindings": [{"id": "rule-api", "title": "接口规范", "domain": "api"}],
            },
        ] if project_id == "proj-1" else [],
    )
    monkeypatch.setattr(
        collab_svc,
        "list_project_proxy_tools_runtime",
        lambda project_id, employee_id="": [
            {
                "tool_name": "emp_ui__skill_vue__page",
                "employee_id": "emp-ui",
                "skill_name": "Vue",
                "description": "实现前端页面",
                "parameters_schema": {
                    "type": "object",
                    "properties": {"task": {"type": "string"}},
                    "required": ["task"],
                },
            }
        ] if project_id == "proj-1" else [],
    )
    monkeypatch.setattr(
        collab_svc,
        "list_project_external_tools_runtime",
        lambda project_id: [
            {
                "tool_name": "external__coder__execute_task",
                "module_name": "coder",
                "remote_tool_name": "execute_task",
                "description": "代码 Agent，接收任务后自动执行仓库修改",
                "parameters_schema": {
                    "type": "object",
                    "properties": {
                        "task": {"type": "string"},
                        "project_name": {"type": "string"},
                        "employee_ids": {"type": "array"},
                        "selected_members": {"type": "array"},
                    },
                    "required": ["task", "project_name", "employee_ids"],
                },
            },
            {
                "tool_name": "external__files__read_file",
                "module_name": "files",
                "remote_tool_name": "read_file",
                "description": "读取文件",
                "parameters_schema": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        ] if project_id == "proj-1" else [],
    )

    captured_calls: list[dict] = []

    def fake_invoke(**kwargs):
        captured_calls.append(kwargs)
        return {"status": "ok", "tool_name": kwargs["tool_name"]}

    result = collab_svc.execute_project_collaboration_runtime(
        "proj-1",
        "请修复前端页面样式并同步调整接口交互",
        max_tool_calls=8,
        invoke_tool=fake_invoke,
    )

    assert result["candidate_tools"][0]["tool_name"] == "external__coder__execute_task"
    assert result["execution_halt_reason"] == "external_executor_completed"
    assert any(item["tool_name"] == "external__coder__execute_task" for item in result["executed_calls"])
    assert not any(call["tool_name"] == "emp_ui__skill_vue__page" for call in captured_calls)
    external_call = next(call for call in captured_calls if call["tool_name"] == "external__coder__execute_task")
    assert external_call["args"]["task"] == "请修复前端页面样式并同步调整接口交互"
    assert external_call["args"]["project_name"] == "项目一"
    assert external_call["args"]["employee_ids"] == ["emp-ui", "emp-api"]
    assert len(external_call["args"]["selected_members"]) == 2


def test_project_collaboration_runtime_syncs_task_tree_during_execution(monkeypatch):
    from copy import deepcopy
    from services import dynamic_mcp_collaboration as collab_svc

    class DummyProject:
        id = "proj-1"
        name = "项目一"

    monkeypatch.setattr(
        collab_svc,
        "project_store",
        type("DummyProjectStore", (), {"get": staticmethod(lambda project_id: DummyProject() if project_id == "proj-1" else None)})(),
    )
    monkeypatch.setattr(
        collab_svc,
        "list_project_member_profiles_runtime",
        lambda project_id, include_disabled=False, include_missing=False, rule_limit=30: [
            {
                "employee_id": "emp-ui",
                "id": "emp-ui",
                "name": "前端开发",
                "goal": "负责页面实现",
                "skill_names": ["vue", "ui"],
                "rule_bindings": [{"id": "rule-ui", "title": "UI 规范", "domain": "ui"}],
            },
            {
                "employee_id": "emp-api",
                "id": "emp-api",
                "name": "后端开发",
                "goal": "负责接口实现",
                "skill_names": ["python", "api"],
                "rule_bindings": [{"id": "rule-api", "title": "接口规范", "domain": "api"}],
            },
        ] if project_id == "proj-1" else [],
    )
    monkeypatch.setattr(
        collab_svc,
        "list_project_proxy_tools_runtime",
        lambda project_id, employee_id="": [
            {
                "tool_name": "emp_ui__skill_vue__page",
                "employee_id": "emp-ui",
                "skill_name": "Vue",
                "description": "实现前端页面",
                "parameters_schema": {
                    "type": "object",
                    "properties": {"task": {"type": "string"}},
                    "required": ["task"],
                },
            }
        ] if project_id == "proj-1" else [],
    )
    monkeypatch.setattr(
        collab_svc,
        "list_project_external_tools_runtime",
        lambda project_id: [
            {
                "tool_name": "external__coder__execute_task",
                "module_name": "coder",
                "remote_tool_name": "execute_task",
                "description": "代码 Agent，接收任务后自动执行仓库修改",
                "parameters_schema": {
                    "type": "object",
                    "properties": {
                        "task": {"type": "string"},
                        "project_name": {"type": "string"},
                        "employee_ids": {"type": "array"},
                        "selected_members": {"type": "array"},
                    },
                    "required": ["task", "project_name", "employee_ids"],
                },
            }
        ] if project_id == "proj-1" else [],
    )

    step_titles = [
        "先统一检索项目上下文、成员、规则和 MCP 能力。",
        "先检索 前端开发 相关规则，避免协作执行偏离约束。",
        "先检索 后端开发 相关规则，避免协作执行偏离约束。",
        "代码 Agent，接收任务后自动执行仓库修改",
    ]
    state = {
        "task_tree": {
            "id": "tts-1",
            "project_id": "proj-1",
            "username": "tester",
            "chat_session_id": "chat-1",
            "status": "pending",
            "progress_percent": 0,
            "current_node_id": "node-1",
            "current_node": None,
            "nodes": [
                {
                    "id": "root-1",
                    "parent_id": "",
                    "level": 0,
                    "sort_order": 0,
                    "title": "请修复前端页面样式并同步调整接口交互",
                    "status": "pending",
                    "verification_result": "",
                },
                *[
                    {
                        "id": f"node-{index}",
                        "parent_id": "root-1",
                        "level": 1,
                        "sort_order": index,
                        "title": title,
                        "status": "pending",
                        "verification_result": "",
                    }
                    for index, title in enumerate(step_titles, start=1)
                ],
            ],
        },
        "history_task_tree": None,
    }
    event_order: list[tuple[str, str]] = []

    def refresh_current_tree():
        task_tree = state["task_tree"]
        if task_tree is None:
            return None
        nodes = task_tree["nodes"]
        children = [item for item in nodes if item["level"] > 0]
        done_count = len([item for item in children if item["status"] == "done"])
        task_tree["progress_percent"] = int(round((done_count / max(len(children), 1)) * 100))
        root = nodes[0]
        if children and all(item["status"] == "done" for item in children) and root["verification_result"]:
            root["status"] = "done"
            task_tree["status"] = "done"
            task_tree["current_node_id"] = ""
            task_tree["current_node"] = None
        elif any(item["status"] == "blocked" for item in children):
            task_tree["status"] = "blocked"
        elif any(item["status"] in {"in_progress", "verifying"} for item in children):
            task_tree["status"] = "in_progress"
        else:
            task_tree["status"] = "pending"
        if task_tree["status"] != "done":
            current = next((item for item in children if item["status"] != "done"), None)
            task_tree["current_node_id"] = current["id"] if current else ""
            task_tree["current_node"] = current
        return task_tree

    refresh_current_tree()

    monkeypatch.setattr(
        collab_svc,
        "ensure_project_execution_task_tree",
        lambda **kwargs: deepcopy(refresh_current_tree()),
    )

    def fake_update_task_tree_node_tool_payload(**kwargs):
        event_order.append(("start", kwargs["node_id"]))
        for node in state["task_tree"]["nodes"]:
            if node["id"] == kwargs["node_id"]:
                node["status"] = kwargs["status"]
                break
        return deepcopy(refresh_current_tree())

    def fake_complete_task_tree_node_tool_payload(**kwargs):
        event_order.append(("complete", kwargs["node_id"]))
        for node in state["task_tree"]["nodes"]:
            if node["id"] == kwargs["node_id"]:
                node["status"] = "done"
                node["verification_result"] = kwargs["verification_result"]
                break
        current_tree = refresh_current_tree()
        if kwargs["node_id"] == "root-1":
            archived = deepcopy(current_tree)
            state["history_task_tree"] = archived
            state["task_tree"] = None
            return {
                "task_tree": None,
                "history_task_tree": archived,
            }
        return deepcopy(current_tree)

    monkeypatch.setattr(collab_svc, "update_task_tree_node_tool_payload", fake_update_task_tree_node_tool_payload)
    monkeypatch.setattr(collab_svc, "complete_task_tree_node_tool_payload", fake_complete_task_tree_node_tool_payload)

    def fake_invoke(**kwargs):
        event_order.append(("invoke", kwargs["tool_name"]))
        return {"status": "ok", "tool_name": kwargs["tool_name"]}

    result = collab_svc.execute_project_collaboration_runtime(
        "proj-1",
        "请修复前端页面样式并同步调整接口交互",
        username="tester",
        chat_session_id="chat-1",
        max_tool_calls=8,
        invoke_tool=fake_invoke,
    )

    assert result["execution_halt_reason"] == "external_executor_completed"
    assert result["task_tree"] is None
    assert result["history_task_tree"]["status"] == "done"
    assert result["history_task_tree"]["progress_percent"] == 100
    assert event_order[:6] == [
        ("start", "node-1"),
        ("invoke", "search_project_context"),
        ("complete", "node-1"),
        ("start", "node-2"),
        ("invoke", "query_project_rules"),
        ("complete", "node-2"),
    ]
    assert ("complete", "node-4") in event_order
    assert event_order[-1] == ("complete", "root-1")


def test_project_mcp_proxy_tool_invocation_passes_project_root_and_api_key(monkeypatch, tmp_path):
    from services import dynamic_mcp_apps_project as project_mcp_svc

    registered_tools: dict[str, object] = {}
    registered_resources: dict[str, object] = {}
    captured: dict = {}

    class FakeMcp:
        def tool(self, name=None, description=None):
            def decorator(fn):
                registered_tools[name or fn.__name__] = fn
                return fn

            return decorator

        def resource(self, uri, **_kwargs):
            def decorator(fn):
                registered_resources[uri] = fn
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
        "project_store",
        type(
            "DummyProjectStore",
            (),
            {
                "get": staticmethod(
                    lambda project_id: type(
                        "DummyProject",
                        (),
                        {
                            "id": "proj-1",
                            "name": "项目一",
                            "description": "测试项目",
                            "mcp_enabled": True,
                            "feedback_upgrade_enabled": False,
                        },
                    )()
                    if project_id == "proj-1"
                    else None
                )
            },
        )(),
    )
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
    monkeypatch.setattr(
        project_mcp_svc,
        "execute_project_collaboration_runtime",
        lambda **kwargs: {
            "tool_name": "execute_project_collaboration",
            "task": kwargs["task"],
            "selected_employee_ids": list(kwargs["employee_ids"]),
            "auto_execute": kwargs["auto_execute"],
        },
    )
    monkeypatch.setattr(
        project_mcp_svc,
        "project_ui_rule_summary",
        lambda project_id, limit=20: [{"id": "rule-ui", "title": "项目 UI 规则", "domain": "ui"}]
        if project_id == "proj-1"
        else [],
    )

    project_mcp_svc.create_project_mcp(
        "proj-1",
        current_api_key_ctx=FakeCtx("api-key-123"),
        current_developer_name_ctx=FakeCtx("tester"),
        project_root=tmp_path,
        recall_limit=20,
    )

    result = registered_tools[spec["scoped_tool_name"]](args={"sql": "show tables"}, timeout_sec=15)
    collaboration_result = registered_tools["execute_project_collaboration"](
        "完成前端页面",
        employee_ids=["emp-1"],
        auto_execute=False,
    )

    assert result["status"] == "ok"
    assert captured["spec"] == spec
    assert captured["kwargs"]["project_root"] == tmp_path
    assert captured["kwargs"]["current_api_key"] == "api-key-123"
    assert captured["kwargs"]["employee_id"] == "emp-1"
    assert captured["kwargs"]["args"] == {"sql": "show tables"}
    assert captured["kwargs"]["timeout_sec"] == 15
    assert collaboration_result["tool_name"] == "execute_project_collaboration"
    assert collaboration_result["selected_employee_ids"] == ["emp-1"]
    assert collaboration_result["auto_execute"] is False
    assert "project://proj-1/usage-guide" in registered_resources
    usage_guide = registered_resources["project://proj-1/usage-guide"]()
    assert "execute_project_collaboration" in usage_guide
    assert "自主判断单人主责或多人协作" in usage_guide
    assert "项目级 UI 规则" in usage_guide
    assert "优先级高于员工个人规则" in usage_guide


def test_query_mcp_exposes_project_execution_proxy_tools(monkeypatch):
    from services import dynamic_mcp_apps_query as query_mcp_svc
    from stores.mcp_bridge import Classification, MemoryScope, MemoryType

    registered_tools: dict[str, object] = {}
    registered_resources: dict[str, object] = {}

    class FakeMcp:
        def tool(self, name=None, description=None):
            def decorator(fn):
                registered_tools[name or fn.__name__] = fn
                return fn

            return decorator

        def resource(self, uri, **_kwargs):
            def decorator(fn):
                registered_resources[uri] = fn
                return fn

            return decorator

    class DummyProject:
        id = "proj-1"
        name = "项目一"

    monkeypatch.setattr(query_mcp_svc, "_new_mcp", lambda _service_name: FakeMcp())
    monkeypatch.setattr(
        query_mcp_svc,
        "project_store",
        type(
            "DummyProjectStore",
            (),
            {
                "get": staticmethod(lambda project_id: DummyProject() if project_id == "proj-1" else None),
                "list_members": staticmethod(
                    lambda project_id: [
                        type("DummyMember", (), {"employee_id": "emp-1", "enabled": True})()
                    ]
                    if project_id == "proj-1"
                    else []
                ),
            },
        )(),
    )
    monkeypatch.setattr(
        query_mcp_svc,
        "employee_store",
        type("DummyEmployeeStore", (), {"get": staticmethod(lambda employee_id: object() if employee_id == "emp-1" else None)})(),
    )
    monkeypatch.setattr(
        query_mcp_svc,
        "list_project_member_profiles_runtime",
        lambda project_id, include_disabled=False, include_missing=False, rule_limit=30: [
            {"employee_id": "emp-1", "name": "员工一"}
        ] if project_id == "proj-1" else [],
    )
    monkeypatch.setattr(
        query_mcp_svc,
        "query_project_rules_runtime",
        lambda project_id, keyword="", employee_id="": [{"id": "rule-1"}] if project_id == "proj-1" else [],
    )
    monkeypatch.setattr(
        query_mcp_svc,
        "project_ui_rule_summary",
        lambda project_id, limit=30: [{"id": "rule-ui", "title": "项目 UI 规则", "domain": "ui"}]
        if project_id == "proj-1"
        else [],
    )
    saved_memories = []
    monkeypatch.setattr(
        query_mcp_svc,
        "memory_store",
        type(
            "DummyMemoryStore",
            (),
            {
                "new_id": staticmethod(lambda: f"mem-{len(saved_memories) + 1}"),
                "save": staticmethod(lambda memory: saved_memories.append(memory)),
            },
        )(),
    )

    query_mcp_svc.create_query_mcp()

    assert "save_project_memory" in registered_tools
    assert "list_project_members" in registered_tools
    assert "get_project_runtime_context" in registered_tools
    assert "list_project_proxy_tools" in registered_tools
    assert "invoke_project_skill_tool" in registered_tools
    assert "execute_project_collaboration" in registered_tools
    assert "query://usage-guide" in registered_resources
    query_usage_guide = registered_resources["query://usage-guide"]()
    assert "execute_project_collaboration" in query_usage_guide
    assert "统一编排入口" in query_usage_guide
    assert "不预设固定行业分工模板" in query_usage_guide
    assert "save_project_memory" in query_usage_guide
    assert "任务树节点必须直接描述面向用户目标的工作步骤" in query_usage_guide
    assert "Auto inferred proxy entry from scripts/..." in query_usage_guide

    import sys
    import types

    runtime_module = types.SimpleNamespace(
        list_project_proxy_tools_runtime=lambda project_id, employee_id="": [
            {"tool_name": "skill_db__query_db", "employee_id": "emp-1"}
        ] if project_id == "proj-1" else [],
        invoke_project_skill_tool_runtime=lambda **kwargs: {
            "tool_name": kwargs["tool_name"],
            "employee_id": kwargs["employee_id"] or "emp-1",
            "status": "ok",
        },
        execute_project_collaboration_runtime=lambda **kwargs: {
            "tool_name": "execute_project_collaboration",
            "task": kwargs["task"],
            "selected_employee_ids": kwargs["employee_ids"] or ["emp-1"],
            "status": "ok",
        },
    )
    original_runtime_module = sys.modules.get("services.dynamic_mcp_runtime")
    sys.modules["services.dynamic_mcp_runtime"] = runtime_module
    try:
        save_result = registered_tools["save_project_memory"](
            "proj-1",
            "问题：统一入口要补项目级记忆写入\n结论：新增 save_project_memory",
        )
        members = registered_tools["list_project_members"]("proj-1")
        context = registered_tools["get_project_runtime_context"]("proj-1")
        tools = registered_tools["list_project_proxy_tools"]("proj-1", "emp-1")
        invoke_result = registered_tools["invoke_project_skill_tool"](
            "proj-1",
            "skill_db__query_db",
            "emp-1",
            args={"sql": "show tables"},
            timeout_sec=20,
        )
        collaboration_result = registered_tools["execute_project_collaboration"](
            "proj-1",
            "完成页面协作",
            employee_ids=["emp-1"],
            auto_execute=False,
            timeout_sec=20,
        )
    finally:
        if original_runtime_module is None:
            sys.modules.pop("services.dynamic_mcp_runtime", None)
        else:
            sys.modules["services.dynamic_mcp_runtime"] = original_runtime_module

    assert members["project_id"] == "proj-1"
    assert members["total"] == 1
    assert members["items"][0]["employee_id"] == "emp-1"

    assert save_result["status"] == "saved"
    assert save_result["project_id"] == "proj-1"
    assert save_result["employee_ids"] == ["emp-1"]
    assert save_result["saved_count"] == 1
    assert saved_memories[0].employee_id == "emp-1"
    assert saved_memories[0].project_name == "项目一"
    assert saved_memories[0].type == MemoryType.PROJECT_CONTEXT
    assert saved_memories[0].scope == MemoryScope.TEAM_SHARED
    assert saved_memories[0].classification == Classification.INTERNAL
    assert saved_memories[0].purpose_tags[:3] == ("query-mcp", "manual-write", "project-id")
    assert any(tag.startswith("fp:") for tag in saved_memories[0].purpose_tags)

    assert context["project_id"] == "proj-1"
    assert context["member_count"] == 1
    assert context["scoped_proxy_tool_count"] == 1
    assert context["rule_count"] == 1
    assert context["ui_rule_count"] == 1
    assert context["ui_rules"][0]["id"] == "rule-ui"

    assert tools["project_id"] == "proj-1"
    assert tools["employee_id"] == "emp-1"
    assert tools["total"] == 1
    assert tools["items"][0]["tool_name"] == "skill_db__query_db"

    assert invoke_result["project_id"] == "proj-1"
    assert invoke_result["project_name"] == "项目一"
    assert invoke_result["tool_name"] == "skill_db__query_db"
    assert invoke_result["employee_id"] == "emp-1"
    assert invoke_result["status"] == "ok"
    assert collaboration_result["project_id"] == "proj-1"
    assert collaboration_result["tool_name"] == "execute_project_collaboration"
    assert collaboration_result["task"] == "完成页面协作"
    assert collaboration_result["selected_employee_ids"] == ["emp-1"]


def test_query_mcp_proxy_app_handles_sse_and_streamable_routes(monkeypatch):
    from fastapi import FastAPI, Request
    from services.dynamic_mcp_proxy_apps import QueryMcpProxyApp
    from services.dynamic_mcp_transports import replace_path_suffix

    captured_connections = []
    captured_memories = []
    api_key_ctx: ContextVar[str] = ContextVar("query_test_api_key", default="")
    developer_ctx: ContextVar[str] = ContextVar("query_test_developer", default="")

    class DummyUsageStore:
        @staticmethod
        def validate_key(api_key: str):
            return "tester" if api_key == "valid-key" else ""

        @staticmethod
        def record_event(scope_id, api_key, developer_name, event_type, client_ip=""):
            captured_connections.append(
                {
                    "scope_id": scope_id,
                    "api_key": api_key,
                    "developer_name": developer_name,
                    "event_type": event_type,
                    "client_ip": client_ip,
                }
            )

    downstream = FastAPI()

    @downstream.api_route("/{full_path:path}", methods=["GET", "POST"])
    async def echo(request: Request, full_path: str):
        body = await request.body()
        return {
            "path": request.scope["path"],
            "method": request.method,
            "full_path": full_path,
            "api_key": api_key_ctx.get(""),
            "developer_name": developer_ctx.get(""),
            "body": body.decode("utf-8"),
        }

    proxy_app = QueryMcpProxyApp(
        usage_store=DummyUsageStore(),
        current_api_key_ctx=api_key_ctx,
        current_developer_name_ctx=developer_ctx,
        session_keys={},
        session_contexts={},
        query_app=downstream,
        save_auto_query_memory=lambda questions, source, project_id="", employee_id="", project_name="", chat_session_id="": captured_memories.append(
            {
                "questions": questions,
                "source": source,
                "project_id": project_id,
                "employee_id": employee_id,
                "project_name": project_name,
                "chat_session_id": chat_session_id,
            }
        ),
        replace_path_suffix=replace_path_suffix,
    )

    monkeypatch.setattr("services.dynamic_mcp_proxy_apps.create_tracking_send", lambda send, **kwargs: send)
    monkeypatch.setattr("services.dynamic_mcp_proxy_apps.create_tracking_receive", lambda receive, **kwargs: receive)
    monkeypatch.setattr("services.dynamic_mcp_proxy_apps.get_client_ip", lambda scope: "127.0.0.1")

    app = FastAPI()
    app.mount("/mcp/query", proxy_app)
    client = TestClient(app)

    missing_key = client.get("/mcp/query/sse")
    sse_get = client.get("/mcp/query/sse?key=valid-key")
    sse_post = client.post(
        "/mcp/query/sse?key=valid-key",
        json={"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "search_ids"}},
    )
    streamable_post = client.post(
        "/mcp/query/mcp?key=valid-key",
        json={"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "search_ids"}},
    )

    assert missing_key.status_code == 401

    assert sse_get.status_code == 200
    assert sse_get.json()["method"] == "GET"
    assert sse_get.json()["path"].endswith("/sse")
    assert sse_get.json()["api_key"] == "valid-key"
    assert sse_get.json()["developer_name"] == "tester"

    assert sse_post.status_code == 200
    assert sse_post.json()["method"] == "POST"
    assert sse_post.json()["path"].endswith("/mcp")
    assert sse_post.json()["api_key"] == "valid-key"

    assert streamable_post.status_code == 200
    assert streamable_post.json()["path"].endswith("/mcp")
    assert streamable_post.json()["developer_name"] == "tester"

    assert captured_connections == [
        {
            "scope_id": "mcp:query",
            "api_key": "valid-key",
            "developer_name": "tester",
            "event_type": "connection",
            "client_ip": "127.0.0.1",
        }
    ]
    assert captured_memories == []


def test_query_mcp_proxy_app_restores_chat_session_id_for_followup_messages(monkeypatch):
    from fastapi import FastAPI, Request, Response
    from services.dynamic_mcp_proxy_apps import QueryMcpProxyApp
    from services.dynamic_mcp_transports import replace_path_suffix

    api_key_ctx: ContextVar[str] = ContextVar("query_ctx_api_key", default="")
    developer_ctx: ContextVar[str] = ContextVar("query_ctx_developer", default="")
    task_tree_session_ctx: ContextVar[str] = ContextVar("query_ctx_task_tree_session", default="")
    session_keys: dict[str, tuple[str, str]] = {}
    session_contexts: dict[str, dict[str, str]] = {}

    class DummyUsageStore:
        @staticmethod
        def validate_key(api_key: str):
            return "tester" if api_key == "valid-key" else ""

        @staticmethod
        def get_key(api_key: str):
            if api_key == "valid-key":
                return {"created_by": "owner-tester"}
            return None

        @staticmethod
        def record_event(*args, **kwargs):
            return None

    downstream = FastAPI()

    @downstream.api_route("/{full_path:path}", methods=["GET", "POST"])
    async def echo(request: Request, full_path: str):
        if request.method == "GET":
            return Response(
                content="event: endpoint\ndata: /mcp/query/messages/?session_id=transport-123\n\n",
                media_type="text/event-stream",
            )
        payload = await request.json()
        return {
            "path": request.scope["path"],
            "full_path": full_path,
            "query_string": request.scope.get("query_string", b"").decode("utf-8"),
            "task_tree_session_id": task_tree_session_ctx.get(""),
            "api_key": api_key_ctx.get(""),
            "developer_name": developer_ctx.get(""),
            "payload": payload,
        }

    proxy_app = QueryMcpProxyApp(
        usage_store=DummyUsageStore(),
        current_api_key_ctx=api_key_ctx,
        current_developer_name_ctx=developer_ctx,
        current_mcp_session_id_ctx=task_tree_session_ctx,
        session_keys=session_keys,
        session_contexts=session_contexts,
        query_app=downstream,
        save_auto_query_memory=lambda *args, **kwargs: None,
        replace_path_suffix=replace_path_suffix,
    )

    monkeypatch.setattr("services.dynamic_mcp_proxy_apps.get_client_ip", lambda scope: "127.0.0.1")

    app = FastAPI()
    app.mount("/mcp/query", proxy_app)
    client = TestClient(app)

    sse_response = client.get(
        "/mcp/query/sse?key=valid-key&project_id=proj-1&chat_session_id=chat-123"
    )
    assert sse_response.status_code == 200
    assert session_keys["transport-123"] == ("valid-key", "tester")
    assert session_contexts["transport-123"]["project_id"] == "proj-1"
    assert session_contexts["transport-123"]["chat_session_id"] == "chat-123"

    followup = client.post(
        "/mcp/query/messages?session_id=transport-123",
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "invoke_project_skill_tool",
                "arguments": {
                    "project_id": "proj-1",
                    "tool_name": "search_project_context",
                },
            },
        },
    )
    assert followup.status_code == 200
    assert followup.json()["task_tree_session_id"] == "chat-123"
    assert followup.json()["api_key"] == "valid-key"
    assert followup.json()["developer_name"] == "tester"


def test_query_mcp_proxy_app_bootstraps_task_tree_from_unified_query(monkeypatch):
    from fastapi import FastAPI, Request
    from services.dynamic_mcp_proxy_apps import QueryMcpProxyApp
    from services.dynamic_mcp_transports import replace_path_suffix

    captured_task_tree_calls = []
    api_key_ctx: ContextVar[str] = ContextVar("query_bootstrap_api_key", default="")
    developer_ctx: ContextVar[str] = ContextVar("query_bootstrap_developer", default="")

    class DummyUsageStore:
        @staticmethod
        def validate_key(api_key: str):
            return "tester" if api_key == "valid-key" else ""

        @staticmethod
        def get_key(api_key: str):
            if api_key == "valid-key":
                return {"created_by": "owner-tester"}
            return None

        @staticmethod
        def record_event(*args, **kwargs):
            return None

    downstream = FastAPI()

    @downstream.api_route("/{full_path:path}", methods=["POST"])
    async def echo(request: Request, full_path: str):
        payload = await request.json()
        return {"full_path": full_path, "payload": payload}

    monkeypatch.setattr(
        "services.dynamic_mcp_proxy_apps.ensure_task_tree",
        lambda **kwargs: captured_task_tree_calls.append(kwargs) or {"id": "tts-demo"},
    )
    monkeypatch.setattr("services.dynamic_mcp_proxy_apps.get_client_ip", lambda scope: "127.0.0.1")

    proxy_app = QueryMcpProxyApp(
        usage_store=DummyUsageStore(),
        current_api_key_ctx=api_key_ctx,
        current_developer_name_ctx=developer_ctx,
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
        "/mcp/query/mcp?key=valid-key&project_id=proj-1&chat_session_id=chat-123",
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "search_ids",
                "arguments": {"keyword": "修复统一查询 MCP 的任务树自动推进"},
            },
        },
    )

    assert response.status_code == 200
    assert captured_task_tree_calls == [
        {
            "project_id": "proj-1",
            "username": "owner-tester",
            "chat_session_id": "chat-123",
            "root_goal": "修复统一查询 MCP 的任务树自动推进",
        }
    ]


def test_query_mcp_proxy_app_bootstraps_task_tree_for_direct_cli_without_chat_session_id(monkeypatch):
    from fastapi import FastAPI, Request
    from services.dynamic_mcp_proxy_apps import QueryMcpProxyApp
    from services.dynamic_mcp_transports import replace_path_suffix

    captured_task_tree_calls = []
    api_key_ctx: ContextVar[str] = ContextVar("query_direct_cli_api_key", default="")
    developer_ctx: ContextVar[str] = ContextVar("query_direct_cli_developer", default="")

    class DummyUsageStore:
        @staticmethod
        def validate_key(api_key: str):
            return "tester" if api_key == "valid-key" else ""

        @staticmethod
        def get_key(api_key: str):
            if api_key == "valid-key":
                return {"created_by": "owner-tester"}
            return None

        @staticmethod
        def record_event(*args, **kwargs):
            return None

    downstream = FastAPI()

    @downstream.api_route("/{full_path:path}", methods=["POST"])
    async def echo(request: Request, full_path: str):
        payload = await request.json()
        return {"full_path": full_path, "payload": payload}

    monkeypatch.setattr(
        "services.dynamic_mcp_proxy_apps.ensure_task_tree",
        lambda **kwargs: captured_task_tree_calls.append(kwargs) or {"id": "tts-demo"},
    )
    monkeypatch.setattr("services.dynamic_mcp_proxy_apps.get_client_ip", lambda scope: "127.0.0.1")

    proxy_app = QueryMcpProxyApp(
        usage_store=DummyUsageStore(),
        current_api_key_ctx=api_key_ctx,
        current_developer_name_ctx=developer_ctx,
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
        "/mcp/query/mcp?key=valid-key&project_id=proj-1",
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "search_ids",
                "arguments": {"keyword": "direct cli 也要自动创建任务树"},
            },
        },
    )

    assert response.status_code == 200
    assert len(captured_task_tree_calls) == 1
    assert captured_task_tree_calls[0]["project_id"] == "proj-1"
    assert captured_task_tree_calls[0]["username"] == "owner-tester"
    assert captured_task_tree_calls[0]["root_goal"] == "direct cli 也要自动创建任务树"
    assert str(captured_task_tree_calls[0]["chat_session_id"]).startswith("query-cli.proj-1.owner-tester.")


def test_query_mcp_proxy_app_direct_cli_reuses_stable_chat_session(monkeypatch):
    from fastapi import FastAPI, Request
    from services.dynamic_mcp_proxy_apps import QueryMcpProxyApp
    from services.dynamic_mcp_transports import replace_path_suffix

    captured_task_tree_calls = []
    api_key_ctx: ContextVar[str] = ContextVar("query_direct_cli_new_session_api_key", default="")
    developer_ctx: ContextVar[str] = ContextVar("query_direct_cli_new_session_developer", default="")

    class DummyUsageStore:
        @staticmethod
        def validate_key(api_key: str):
            return "tester" if api_key == "valid-key" else ""

        @staticmethod
        def get_key(api_key: str):
            if api_key == "valid-key":
                return {"created_by": "owner-tester"}
            return None

        @staticmethod
        def record_event(*args, **kwargs):
            return None

    downstream = FastAPI()

    @downstream.api_route("/{full_path:path}", methods=["POST"])
    async def echo(request: Request, full_path: str):
        payload = await request.json()
        return {"full_path": full_path, "payload": payload}

    monkeypatch.setattr(
        "services.dynamic_mcp_proxy_apps.ensure_task_tree",
        lambda **kwargs: captured_task_tree_calls.append(kwargs) or {"id": "tts-demo"},
    )
    monkeypatch.setattr("services.dynamic_mcp_proxy_apps.get_client_ip", lambda scope: "127.0.0.1")

    proxy_app = QueryMcpProxyApp(
        usage_store=DummyUsageStore(),
        current_api_key_ctx=api_key_ctx,
        current_developer_name_ctx=developer_ctx,
        session_keys={},
        session_contexts={},
        query_app=downstream,
        save_auto_query_memory=lambda *args, **kwargs: None,
        replace_path_suffix=replace_path_suffix,
    )

    app = FastAPI()
    app.mount("/mcp/query", proxy_app)
    client = TestClient(app)

    for keyword in ("第一次 CLI 任务", "第二次 CLI 任务"):
        response = client.post(
            "/mcp/query/mcp?key=valid-key&project_id=proj-1",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "search_ids",
                    "arguments": {"keyword": keyword},
                },
            },
        )
        assert response.status_code == 200

    assert len(captured_task_tree_calls) == 2
    assert captured_task_tree_calls[0]["root_goal"] == "第一次 CLI 任务"
    assert captured_task_tree_calls[1]["root_goal"] == "第二次 CLI 任务"
    assert str(captured_task_tree_calls[0]["chat_session_id"]).startswith("query-cli.proj-1.owner-tester.")
    assert str(captured_task_tree_calls[1]["chat_session_id"]).startswith("query-cli.proj-1.owner-tester.")
    assert captured_task_tree_calls[0]["chat_session_id"] == captured_task_tree_calls[1]["chat_session_id"]


def test_query_mcp_project_state_persists_under_project_hidden_dir(tmp_path, monkeypatch):
    from services import query_mcp_project_state as state_service

    workspace = tmp_path / "demo-workspace"
    workspace.mkdir()

    class DummyProjectStore:
        @staticmethod
        def get(project_id: str):
            if project_id != "proj-1":
                return None
            return type(
                "Project",
                (),
                {
                    "workspace_path": str(workspace),
                    "chat_settings": {},
                },
            )()

    monkeypatch.setattr(state_service, "project_store", DummyProjectStore())

    saved = state_service.save_query_mcp_project_state(
        project_id="proj-1",
        project_name="项目一",
        chat_session_id="chat-1",
        session_id="ws-proj-1",
        root_goal="继续任务",
        latest_status="in_progress",
        phase="implementation",
        step="开始恢复",
        source="test",
    )

    active_path = workspace / ".ai-employee" / "query-mcp" / "active" / "proj-1.json"
    history_path = workspace / ".ai-employee" / "query-mcp" / "session-history" / "proj-1__chat-1.json"

    assert saved["chat_session_id"] == "chat-1"
    assert saved["session_id"] == "ws-proj-1"
    assert active_path.exists() is True
    assert history_path.exists() is True
    assert state_service.load_query_mcp_project_state("proj-1")["session_id"] == "ws-proj-1"
    assert state_service.load_resumable_query_mcp_project_state("proj-1")["chat_session_id"] == "chat-1"

    state_service.save_query_mcp_project_state(
        project_id="proj-1",
        chat_session_id="chat-1",
        latest_status="done",
    )

    assert state_service.load_resumable_query_mcp_project_state("proj-1") == {}


def test_query_mcp_proxy_app_direct_cli_reuses_persisted_project_chat_session_across_instances(
    tmp_path,
    monkeypatch,
):
    from fastapi import FastAPI, Request
    from services.dynamic_mcp_proxy_apps import QueryMcpProxyApp
    from services.dynamic_mcp_transports import replace_path_suffix
    from services import query_mcp_project_state as state_service

    workspace = tmp_path / "shared-workspace"
    workspace.mkdir()
    captured_task_tree_calls = []
    api_key_ctx: ContextVar[str] = ContextVar("query_direct_cli_persisted_api_key", default="")
    developer_ctx: ContextVar[str] = ContextVar("query_direct_cli_persisted_developer", default="")

    class DummyProjectStore:
        @staticmethod
        def get(project_id: str):
            if project_id != "proj-1":
                return None
            return type(
                "Project",
                (),
                {
                    "workspace_path": str(workspace),
                    "chat_settings": {},
                },
            )()

    class DummyUsageStore:
        @staticmethod
        def validate_key(api_key: str):
            return "tester" if api_key == "valid-key" else ""

        @staticmethod
        def get_key(api_key: str):
            if api_key == "valid-key":
                return {"created_by": "owner-tester"}
            return None

        @staticmethod
        def record_event(*args, **kwargs):
            return None

    monkeypatch.setattr(state_service, "project_store", DummyProjectStore())
    monkeypatch.setattr(
        "services.dynamic_mcp_proxy_apps.ensure_task_tree",
        lambda **kwargs: captured_task_tree_calls.append(kwargs) or {"id": "tts-demo"},
    )
    monkeypatch.setattr("services.dynamic_mcp_proxy_apps.get_client_ip", lambda scope: "127.0.0.1")

    downstream = FastAPI()

    @downstream.api_route("/{full_path:path}", methods=["POST"])
    async def echo(request: Request, full_path: str):
        payload = await request.json()
        return {"full_path": full_path, "payload": payload}

    def build_client():
        proxy_app = QueryMcpProxyApp(
            usage_store=DummyUsageStore(),
            current_api_key_ctx=api_key_ctx,
            current_developer_name_ctx=developer_ctx,
            session_keys={},
            session_contexts={},
            query_app=downstream,
            save_auto_query_memory=lambda *args, **kwargs: None,
            replace_path_suffix=replace_path_suffix,
        )
        app = FastAPI()
        app.mount("/mcp/query", proxy_app)
        return TestClient(app)

    first_client = build_client()
    first = first_client.post(
        "/mcp/query/mcp?key=valid-key&project_id=proj-1",
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "search_ids",
                "arguments": {"keyword": "第一次跨工具续跑"},
            },
        },
    )
    assert first.status_code == 200
    first_chat_session_id = captured_task_tree_calls[-1]["chat_session_id"]

    captured_task_tree_calls.clear()
    second_client = build_client()
    second = second_client.post(
        "/mcp/query/mcp?key=valid-key&project_id=proj-1",
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "search_ids",
                "arguments": {"keyword": "第二次跨工具续跑"},
            },
        },
    )
    assert second.status_code == 200
    second_chat_session_id = captured_task_tree_calls[-1]["chat_session_id"]

    assert first_chat_session_id == second_chat_session_id
    assert state_service.load_query_mcp_project_state("proj-1")["chat_session_id"] == first_chat_session_id


def test_query_mcp_proxy_app_persists_work_session_id_into_project_state(tmp_path, monkeypatch):
    from fastapi import FastAPI, Request
    from services.dynamic_mcp_proxy_apps import QueryMcpProxyApp
    from services.dynamic_mcp_transports import replace_path_suffix
    from services import query_mcp_project_state as state_service

    workspace = tmp_path / "persist-session-workspace"
    workspace.mkdir()
    api_key_ctx: ContextVar[str] = ContextVar("query_direct_cli_session_file_api_key", default="")
    developer_ctx: ContextVar[str] = ContextVar("query_direct_cli_session_file_developer", default="")

    class DummyProjectStore:
        @staticmethod
        def get(project_id: str):
            if project_id != "proj-1":
                return None
            return type(
                "Project",
                (),
                {
                    "workspace_path": str(workspace),
                    "chat_settings": {},
                },
            )()

    class DummyUsageStore:
        @staticmethod
        def validate_key(api_key: str):
            return "tester" if api_key == "valid-key" else ""

        @staticmethod
        def get_key(api_key: str):
            if api_key == "valid-key":
                return {"created_by": "owner-tester"}
            return None

        @staticmethod
        def record_event(*args, **kwargs):
            return None

    downstream = FastAPI()

    @downstream.api_route("/{full_path:path}", methods=["POST"])
    async def emit_start_work_session(request: Request, full_path: str):
        _ = full_path
        payload = await request.json()
        return {
            "jsonrpc": "2.0",
            "id": payload.get("id"),
            "result": {
                "structuredContent": {
                    "status": "started",
                    "project_id": "proj-1",
                    "project_name": "项目一",
                    "chat_session_id": "chat-persisted-1",
                    "session_id": "ws_proj-1_team_20260414T060000Z_abcd",
                    "goal": "继续任务",
                    "phase": "implementation",
                    "step": "开始",
                }
            },
        }

    monkeypatch.setattr(state_service, "project_store", DummyProjectStore())
    monkeypatch.setattr("services.dynamic_mcp_proxy_apps.get_client_ip", lambda scope: "127.0.0.1")

    proxy_app = QueryMcpProxyApp(
        usage_store=DummyUsageStore(),
        current_api_key_ctx=api_key_ctx,
        current_developer_name_ctx=developer_ctx,
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
        "/mcp/query/mcp?key=valid-key&project_id=proj-1",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "start_work_session",
                "arguments": {
                    "project_id": "proj-1",
                    "chat_session_id": "chat-persisted-1",
                    "goal": "继续任务",
                },
            },
        },
    )

    assert response.status_code == 200
    payload = state_service.load_query_mcp_project_state("proj-1")
    assert payload["chat_session_id"] == "chat-persisted-1"
    assert payload["session_id"] == "ws_proj-1_team_20260414T060000Z_abcd"
    assert payload["latest_status"] == "started"


def test_query_mcp_proxy_app_direct_cli_internal_progress_tools_reuse_existing_chat_without_new_memory(monkeypatch):
    from contextvars import ContextVar
    from fastapi import FastAPI, Request
    from services.dynamic_mcp_proxy_apps import QueryMcpProxyApp
    from services.dynamic_mcp_transports import replace_path_suffix

    captured_task_tree_calls = []
    captured_memories = []
    api_key_ctx: ContextVar[str] = ContextVar("query_direct_cli_progress_api_key", default="")
    developer_ctx: ContextVar[str] = ContextVar("query_direct_cli_progress_developer", default="")
    task_tree_session_ctx: ContextVar[str] = ContextVar("query_direct_cli_progress_session", default="")

    class DummyUsageStore:
        @staticmethod
        def validate_key(api_key: str):
            return "tester" if api_key == "valid-key" else ""

        @staticmethod
        def get_key(api_key: str):
            if api_key == "valid-key":
                return {"created_by": "owner-tester"}
            return None

        @staticmethod
        def record_event(*args, **kwargs):
            return None

    downstream = FastAPI()

    @downstream.api_route("/{full_path:path}", methods=["POST"])
    async def echo(request: Request, full_path: str):
        payload = await request.json()
        return {
            "full_path": full_path,
            "payload": payload,
            "task_tree_session_id": task_tree_session_ctx.get(""),
        }

    monkeypatch.setattr(
        "services.dynamic_mcp_proxy_apps.ensure_task_tree",
        lambda **kwargs: captured_task_tree_calls.append(kwargs) or {"id": "tts-demo"},
    )
    monkeypatch.setattr("services.dynamic_mcp_proxy_apps.get_client_ip", lambda scope: "127.0.0.1")

    proxy_app = QueryMcpProxyApp(
        usage_store=DummyUsageStore(),
        current_api_key_ctx=api_key_ctx,
        current_developer_name_ctx=developer_ctx,
        current_mcp_session_id_ctx=task_tree_session_ctx,
        session_keys={},
        session_contexts={},
        query_app=downstream,
        save_auto_query_memory=lambda *args, **kwargs: captured_memories.append(
            {"args": args, "kwargs": kwargs}
        ),
        replace_path_suffix=replace_path_suffix,
    )

    app = FastAPI()
    app.mount("/mcp/query", proxy_app)
    client = TestClient(app)

    first = client.post(
        "/mcp/query/mcp?key=valid-key&project_id=proj-1",
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "search_ids",
                "arguments": {"keyword": "修复任务树和记忆绑定"},
            },
        },
    )
    assert first.status_code == 200
    first_chat_session_id = first.json()["task_tree_session_id"]

    second = client.post(
        "/mcp/query/mcp?key=valid-key&project_id=proj-1",
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "append_session_event",
                "arguments": {
                    "project_id": "proj-1",
                    "content": "已完成构建验证",
                    "title": "构建验证",
                },
            },
        },
    )
    assert second.status_code == 200

    assert len(captured_task_tree_calls) == 1
    assert len(captured_memories) == 1
    assert second.json()["task_tree_session_id"] == first_chat_session_id


def test_query_mcp_proxy_app_audits_task_tree_from_successful_tool_response(monkeypatch):
    from contextvars import ContextVar
    from fastapi import FastAPI, Request, Response
    from services.dynamic_mcp_proxy_apps import QueryMcpProxyApp
    from services.dynamic_mcp_transports import replace_path_suffix

    captured_audit_calls = []
    captured_result_memories = []
    captured_ensure_calls = []
    api_key_ctx: ContextVar[str] = ContextVar("query_direct_cli_audit_api_key", default="")
    developer_ctx: ContextVar[str] = ContextVar("query_direct_cli_audit_developer", default="")

    class DummyUsageStore:
        @staticmethod
        def validate_key(api_key: str):
            return "tester" if api_key == "valid-key" else ""

        @staticmethod
        def get_key(api_key: str):
            if api_key == "valid-key":
                return {"created_by": "owner-tester"}
            return None

        @staticmethod
        def record_event(*args, **kwargs):
            return None

    downstream = FastAPI()

    @downstream.api_route("/{full_path:path}", methods=["POST"])
    async def tool_result(request: Request, full_path: str):
        _ = full_path
        await request.json()
        rpc_body = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                {
                                    "keyword": "当前项目员工都有谁",
                                    "project_id": "proj-1",
                                    "employees": [
                                        {"id": "emp-1", "name": "前端架构与跨端攻坚专家"},
                                        {"id": "emp-2", "name": "多语言后端开发工程师"},
                                    ],
                                    "projects": [],
                                    "rules": [],
                                },
                                ensure_ascii=False,
                            ),
                        }
                    ]
                },
            },
            ensure_ascii=False,
        )
        return Response(
            content=f"event: message\ndata: {rpc_body}\n\n",
            media_type="text/event-stream",
        )

    monkeypatch.setattr(
        "services.dynamic_mcp_proxy_apps.audit_task_tree_round",
        lambda **kwargs: captured_audit_calls.append(kwargs) or {"code": "lookup_query_auto_completed"},
    )
    monkeypatch.setattr(
        "services.dynamic_mcp_proxy_apps.save_auto_query_result_memory",
        lambda question, solution, conclusion, source, **kwargs: captured_result_memories.append(
            {
                "question": question,
                "solution": solution,
                "conclusion": conclusion,
                "source": source,
                **kwargs,
            }
        ),
    )
    monkeypatch.setattr(
        "services.dynamic_mcp_proxy_apps.ensure_task_tree",
        lambda **kwargs: captured_ensure_calls.append(kwargs) or kwargs,
    )
    monkeypatch.setattr("services.dynamic_mcp_proxy_apps.get_client_ip", lambda scope: "127.0.0.1")

    proxy_app = QueryMcpProxyApp(
        usage_store=DummyUsageStore(),
        current_api_key_ctx=api_key_ctx,
        current_developer_name_ctx=developer_ctx,
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
        "/mcp/query/mcp?key=valid-key&project_id=proj-1",
        headers={"Accept": "application/json, text/event-stream"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "search_ids",
                "arguments": {"keyword": "当前项目员工都有谁"},
            },
        },
    )

    assert response.status_code == 200
    assert len(captured_audit_calls) == 1
    assert captured_audit_calls[0]["project_id"] == "proj-1"
    assert captured_audit_calls[0]["username"] == "owner-tester"
    assert captured_audit_calls[0]["successful_tool_names"] == ["search_ids"]
    assert "前端架构与跨端攻坚专家" in captured_audit_calls[0]["assistant_content"]
    assert captured_result_memories == []
    assert captured_ensure_calls == []


def test_query_mcp_proxy_app_bootstraps_task_tree_from_transport_session(monkeypatch):
    from fastapi import FastAPI, Request, Response
    from services.dynamic_mcp_proxy_apps import QueryMcpProxyApp
    from services.dynamic_mcp_transports import replace_path_suffix

    captured_task_tree_calls = []
    api_key_ctx: ContextVar[str] = ContextVar("query_transport_api_key", default="")
    developer_ctx: ContextVar[str] = ContextVar("query_transport_developer", default="")
    session_keys: dict[str, tuple[str, str]] = {}
    session_contexts: dict[str, dict[str, str]] = {}

    class DummyUsageStore:
        @staticmethod
        def validate_key(api_key: str):
            return "tester" if api_key == "valid-key" else ""

        @staticmethod
        def get_key(api_key: str):
            if api_key == "valid-key":
                return {"created_by": "owner-tester"}
            return None

        @staticmethod
        def record_event(*args, **kwargs):
            return None

    downstream = FastAPI()

    @downstream.api_route("/{full_path:path}", methods=["GET", "POST"])
    async def echo(request: Request, full_path: str):
        if request.method == "GET":
            return Response(
                content="event: endpoint\ndata: /mcp/query/messages/?session_id=transport-xyz\n\n",
                media_type="text/event-stream",
            )
        payload = await request.json()
        return {"full_path": full_path, "payload": payload}

    monkeypatch.setattr(
        "services.dynamic_mcp_proxy_apps.ensure_task_tree",
        lambda **kwargs: captured_task_tree_calls.append(kwargs) or {"id": "tts-demo"},
    )
    monkeypatch.setattr("services.dynamic_mcp_proxy_apps.get_client_ip", lambda scope: "127.0.0.1")

    proxy_app = QueryMcpProxyApp(
        usage_store=DummyUsageStore(),
        current_api_key_ctx=api_key_ctx,
        current_developer_name_ctx=developer_ctx,
        session_keys=session_keys,
        session_contexts=session_contexts,
        query_app=downstream,
        save_auto_query_memory=lambda *args, **kwargs: None,
        replace_path_suffix=replace_path_suffix,
    )

    app = FastAPI()
    app.mount("/mcp/query", proxy_app)
    client = TestClient(app)

    sse_response = client.get("/mcp/query/sse?key=valid-key&project_id=proj-1")
    assert sse_response.status_code == 200
    assert session_keys["transport-xyz"] == ("valid-key", "tester")

    followup = client.post(
        "/mcp/query/messages?session_id=transport-xyz",
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "search_ids",
                "arguments": {"keyword": "通过 transport session 自动创建任务树"},
            },
        },
    )

    assert followup.status_code == 200
    assert captured_task_tree_calls == [
        {
            "project_id": "proj-1",
            "username": "owner-tester",
            "chat_session_id": "transport-xyz",
            "root_goal": "通过 transport session 自动创建任务树",
        }
    ]


def test_query_mcp_proxy_app_passes_task_tree_payload_to_auto_result_memory(monkeypatch):
    from contextvars import ContextVar
    from fastapi import FastAPI, Request, Response
    from services.dynamic_mcp_proxy_apps import QueryMcpProxyApp
    from services.dynamic_mcp_transports import replace_path_suffix

    captured_result_memories = []
    api_key_ctx: ContextVar[str] = ContextVar("query_result_api_key", default="")
    developer_ctx: ContextVar[str] = ContextVar("query_result_developer", default="")
    session_contexts = {
        "transport-1": {
            "project_id": "proj-1",
            "project_name": "项目一",
            "employee_id": "",
            "chat_session_id": "chat-123",
        }
    }

    class DummyUsageStore:
        @staticmethod
        def validate_key(api_key: str):
            return "tester" if api_key == "valid-key" else ""

        @staticmethod
        def get_key(api_key: str):
            if api_key == "valid-key":
                return {"created_by": "owner-tester"}
            return None

        @staticmethod
        def record_event(*args, **kwargs):
            return None

    downstream = FastAPI()

    @downstream.api_route("/{full_path:path}", methods=["POST"])
    async def emit_tool_result(request: Request, full_path: str):
        await request.body()
        rpc_body = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                {
                                    "items": [
                                        {"employee_id": "emp-1", "name": "员工一"},
                                        {"employee_id": "emp-2", "name": "员工二"},
                                    ]
                                },
                                ensure_ascii=False,
                            ),
                        }
                    ]
                },
            },
            ensure_ascii=False,
        )
        return Response(
            content=f"event: message\ndata: {rpc_body}\n\n",
            media_type="text/event-stream",
        )

    monkeypatch.setattr(
        "services.dynamic_mcp_proxy_apps.audit_task_tree_round",
        lambda **kwargs: {
            "code": "task_tree_updated",
            "task_tree": {
                "id": "task-tree-123",
                "chat_session_id": "chat-123",
                "source_chat_session_id": "chat-123",
                "root_goal": "修复 /mcp/query/sse 自动结果记忆",
                "status": "in_progress",
                "progress_percent": 50,
                "current_node": {
                    "id": "node-2",
                    "title": "改写自动结果记忆",
                    "status": "in_progress",
                },
                "nodes": [
                    {"id": "root", "level": 0, "title": "修复 /mcp/query/sse 自动结果记忆", "status": "in_progress"},
                    {"id": "node-1", "level": 1, "title": "梳理统一查询入口", "status": "done", "verification_result": "已核对代理链路"},
                    {"id": "node-2", "level": 1, "title": "改写自动结果记忆", "status": "in_progress", "verification_result": ""},
                ],
                "stats": {"leaf_total": 2, "done_leaf_total": 1},
            },
        },
    )
    monkeypatch.setattr(
        "services.dynamic_mcp_proxy_apps.save_auto_query_result_memory",
        lambda question, solution, conclusion, source, **kwargs: captured_result_memories.append(
            {
                "question": question,
                "solution": solution,
                "conclusion": conclusion,
                "source": source,
                **kwargs,
            }
        ),
    )
    monkeypatch.setattr("services.dynamic_mcp_proxy_apps.get_client_ip", lambda scope: "127.0.0.1")

    proxy_app = QueryMcpProxyApp(
        usage_store=DummyUsageStore(),
        current_api_key_ctx=api_key_ctx,
        current_developer_name_ctx=developer_ctx,
        session_keys={"transport-1": ("valid-key", "tester")},
        session_contexts=session_contexts,
        query_app=downstream,
        save_auto_query_memory=lambda *args, **kwargs: None,
        replace_path_suffix=replace_path_suffix,
    )

    app = FastAPI()
    app.mount("/mcp/query", proxy_app)
    client = TestClient(app)

    response = client.post(
        "/mcp/query/messages?session_id=transport-1",
        headers={"Accept": "application/json, text/event-stream"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "list_project_members",
                "arguments": {
                    "project_id": "proj-1",
                },
                "messages": [
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": "修复 /mcp/query/sse 自动结果记忆"}],
                    }
                ],
            },
        },
    )

    assert response.status_code == 200
    assert len(captured_result_memories) == 1
    assert captured_result_memories[0]["project_id"] == "proj-1"
    assert captured_result_memories[0]["chat_session_id"] == "chat-123"
    assert captured_result_memories[0]["question"] == "修复 /mcp/query/sse 自动结果记忆"
    assert captured_result_memories[0]["task_tree_payload"]["id"] == "task-tree-123"
    assert captured_result_memories[0]["task_tree_payload"]["current_node"]["id"] == "node-2"


def test_query_mcp_proxy_app_sse_bridge_generates_fallback_task_tree_session(monkeypatch):
    from contextvars import ContextVar
    from fastapi import FastAPI, Request
    from services.dynamic_mcp_proxy_apps import QueryMcpProxyApp
    from services.dynamic_mcp_transports import replace_path_suffix

    captured_task_tree_calls = []
    api_key_ctx: ContextVar[str] = ContextVar("query_sse_bridge_api_key", default="")
    developer_ctx: ContextVar[str] = ContextVar("query_sse_bridge_developer", default="")
    task_tree_session_ctx: ContextVar[str] = ContextVar(
        "query_sse_bridge_task_tree_session",
        default="",
    )

    class DummyUsageStore:
        @staticmethod
        def validate_key(api_key: str):
            return "tester" if api_key == "valid-key" else ""

        @staticmethod
        def get_key(api_key: str):
            if api_key == "valid-key":
                return {"created_by": "owner-tester"}
            return None

        @staticmethod
        def record_event(*args, **kwargs):
            return None

    downstream = FastAPI()

    @downstream.api_route("/{full_path:path}", methods=["POST"])
    async def echo(request: Request, full_path: str):
        payload = await request.json()
        return {
            "full_path": full_path,
            "payload": payload,
            "task_tree_session_id": task_tree_session_ctx.get(""),
        }

    monkeypatch.setattr(
        "services.dynamic_mcp_proxy_apps.ensure_task_tree",
        lambda **kwargs: captured_task_tree_calls.append(kwargs) or {"id": "tts-demo"},
    )
    monkeypatch.setattr("services.dynamic_mcp_proxy_apps.get_client_ip", lambda scope: "127.0.0.1")

    proxy_app = QueryMcpProxyApp(
        usage_store=DummyUsageStore(),
        current_api_key_ctx=api_key_ctx,
        current_developer_name_ctx=developer_ctx,
        current_mcp_session_id_ctx=task_tree_session_ctx,
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
        "/mcp/query/sse?key=valid-key",
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "search_ids",
                "arguments": {
                    "keyword": "sse bridge 也要自动创建任务树",
                    "project_id": "proj-1",
                },
            },
        },
    )

    assert response.status_code == 200
    generated_chat_session_id = str(response.json()["task_tree_session_id"])
    assert generated_chat_session_id.startswith("query-cli.proj-1.owner-tester.")
    assert captured_task_tree_calls == [
        {
            "project_id": "proj-1",
            "username": "owner-tester",
            "chat_session_id": generated_chat_session_id,
            "root_goal": "sse bridge 也要自动创建任务树",
        }
    ]


def test_query_mcp_mount_handles_real_jsonrpc_over_http_and_sse_bridge(monkeypatch):
    from core.server import create_app
    from services import dynamic_mcp_runtime as runtime

    captured_memories = []

    class DummyUsageStore:
        @staticmethod
        def validate_key(api_key: str):
            return "tester" if api_key == "valid-key" else ""

        @staticmethod
        def record_event(*args, **kwargs):
            return None

    def extract_sse_payload(response_text: str) -> dict:
        for line in response_text.splitlines():
            if line.startswith("data: "):
                return json.loads(line[len("data: "):])
        raise AssertionError(f"Missing SSE data line: {response_text}")

    monkeypatch.setattr(runtime.query_mcp_proxy_app, "_usage_store", DummyUsageStore())
    monkeypatch.setattr(runtime.query_mcp_proxy_app, "_current_api_key_ctx", ContextVar("query_mount_api", default=""))
    monkeypatch.setattr(runtime.query_mcp_proxy_app, "_current_developer_name_ctx", ContextVar("query_mount_dev", default=""))
    monkeypatch.setattr(
        runtime.query_mcp_proxy_app,
        "_save_auto_query_memory",
        lambda *args, **kwargs: captured_memories.append({"args": args, "kwargs": kwargs}),
    )
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "analyze_task",
            "arguments": {
                "raw_request": "继续升级 /mcp/query/sse，并补一条 create_app 集成测试",
            },
        },
    }
    headers = {"Accept": "application/json, text/event-stream"}

    def post_jsonrpc(path: str, *, request_headers: dict[str, str] | None = None):
        monkeypatch.setattr(runtime.query_mcp_proxy_app, "_query_app", runtime._create_query_mcp())
        app = create_app()
        with TestClient(app) as client:
            return client.post(path, headers=request_headers, json=payload)

    missing_accept = post_jsonrpc("/mcp/query/mcp?key=valid-key")
    http_response = post_jsonrpc("/mcp/query/mcp?key=valid-key", request_headers=headers)
    sse_bridge_response = post_jsonrpc("/mcp/query/sse?key=valid-key", request_headers=headers)

    assert missing_accept.status_code == 406
    assert "text/event-stream" in missing_accept.text

    assert http_response.status_code == 200
    assert http_response.headers["content-type"].startswith("text/event-stream")
    http_rpc = extract_sse_payload(http_response.text)
    http_result = json.loads(http_rpc["result"]["content"][0]["text"])

    assert http_rpc["jsonrpc"] == "2.0"
    assert http_rpc["id"] == 1
    assert http_result["raw_request"] == "继续升级 /mcp/query/sse，并补一条 create_app 集成测试"
    assert "/mcp/query/sse" in http_result["mentioned_paths"]
    assert "mcp-upgrade" in http_result["task_types"]
    assert http_result["analysis_mode"] == "heuristic"

    assert sse_bridge_response.status_code == 200
    assert sse_bridge_response.headers["content-type"].startswith("text/event-stream")
    sse_rpc = extract_sse_payload(sse_bridge_response.text)
    sse_result = json.loads(sse_rpc["result"]["content"][0]["text"])

    assert sse_rpc["jsonrpc"] == "2.0"
    assert sse_rpc["id"] == 1
    assert sse_result == http_result
    assert captured_memories == []


def test_query_mcp_mount_lists_tools_and_reads_resources(monkeypatch):
    from core.server import create_app
    from services import dynamic_mcp_runtime as runtime

    class DummyUsageStore:
        @staticmethod
        def validate_key(api_key: str):
            return "tester" if api_key == "valid-key" else ""

        @staticmethod
        def record_event(*args, **kwargs):
            return None

    def extract_sse_payload(response_text: str) -> dict:
        for line in response_text.splitlines():
            if line.startswith("data: "):
                return json.loads(line[len("data: "):])
        raise AssertionError(f"Missing SSE data line: {response_text}")

    def post_jsonrpc(payload: dict):
        monkeypatch.setattr(runtime.query_mcp_proxy_app, "_usage_store", DummyUsageStore())
        monkeypatch.setattr(runtime.query_mcp_proxy_app, "_current_api_key_ctx", ContextVar("query_meta_api", default=""))
        monkeypatch.setattr(runtime.query_mcp_proxy_app, "_current_developer_name_ctx", ContextVar("query_meta_dev", default=""))
        monkeypatch.setattr(runtime.query_mcp_proxy_app, "_save_auto_query_memory", lambda *args, **kwargs: None)
        monkeypatch.setattr(runtime.query_mcp_proxy_app, "_query_app", runtime._create_query_mcp())
        app = create_app()
        with TestClient(app) as client:
            return client.post(
                "/mcp/query/mcp?key=valid-key",
                headers={"Accept": "application/json, text/event-stream"},
                json=payload,
            )

    tools_response = post_jsonrpc({"jsonrpc": "2.0", "id": 11, "method": "tools/list", "params": {}})
    resources_response = post_jsonrpc({"jsonrpc": "2.0", "id": 12, "method": "resources/list", "params": {}})
    usage_read_response = post_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 13,
            "method": "resources/read",
            "params": {"uri": "query://usage-guide"},
        }
    )
    codex_read_response = post_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 14,
            "method": "resources/read",
            "params": {"uri": "query://client-profile/codex"},
        }
    )

    assert tools_response.status_code == 200
    tools_rpc = extract_sse_payload(tools_response.text)
    tools = tools_rpc["result"]["tools"]
    tool_names = {item["name"] for item in tools}
    assert "bind_project_context" in tool_names
    assert "analyze_task" in tool_names
    assert "resolve_relevant_context" in tool_names
    assert "generate_execution_plan" in tool_names
    assert "build_delivery_report" in tool_names
    assert "generate_release_note_entry" in tool_names

    assert resources_response.status_code == 200
    resources_rpc = extract_sse_payload(resources_response.text)
    resources = resources_rpc["result"]["resources"]
    resource_uris = {item["uri"] for item in resources}
    assert "query://usage-guide" in resource_uris
    assert "query://client-profile/claude-code" in resource_uris
    assert "query://client-profile/codex" in resource_uris
    assert "query://client-profile/generic-cli" in resource_uris

    assert usage_read_response.status_code == 200
    usage_rpc = extract_sse_payload(usage_read_response.text)
    usage_contents = usage_rpc["result"]["contents"]
    assert usage_contents[0]["uri"] == "query://usage-guide"
    assert "Recommended tools" not in usage_contents[0]["text"]
    assert "bind_project_context" in usage_contents[0]["text"]
    assert "analyze_task" in usage_contents[0]["text"]
    assert "execute_project_collaboration" in usage_contents[0]["text"]
    assert "优先使用项目绑定员工、规则和技能" in usage_contents[0]["text"]
    assert "重新获取与当前任务直接相关的规则正文" in usage_contents[0]["text"]

    assert codex_read_response.status_code == 200
    codex_rpc = extract_sse_payload(codex_read_response.text)
    codex_contents = codex_rpc["result"]["contents"]
    assert codex_contents[0]["uri"] == "query://client-profile/codex"
    assert "Codex" in codex_contents[0]["text"]
    assert "search_ids" in codex_contents[0]["text"]
    assert "get_manual_content" in codex_contents[0]["text"]
    assert "build_delivery_report" in codex_contents[0]["text"]
    assert "优先使用项目绑定员工、规则和技能" in codex_contents[0]["text"]


def _extract_query_mcp_sse_payload(response_text: str) -> dict:
    for line in response_text.splitlines():
        if line.startswith("data: "):
            return json.loads(line[len("data: "):])
    raise AssertionError(f"Missing SSE data line: {response_text}")


def _extract_query_mcp_tool_result(response_text: str) -> dict:
    rpc = _extract_query_mcp_sse_payload(response_text)
    return json.loads(rpc["result"]["content"][0]["text"])


def _configure_query_mcp_standard_project_chain_env(monkeypatch):
    import sys
    import types

    from core.server import create_app
    from routers import projects as projects_router
    from services import dynamic_mcp_apps_query as query_mcp_svc
    from services import dynamic_mcp_runtime as runtime

    class DummyProject:
        id = "proj-1"
        name = "项目一"
        description = "统一查询 MCP 标准链路测试项目"

    class DummyEmployee:
        id = "emp-1"
        name = "员工一"
        description = "负责 query MCP 升级"
        goal = "补齐联调测试"

    class DummyUsageStore:
        @staticmethod
        def validate_key(api_key: str):
            return "tester" if api_key == "valid-key" else ""

        @staticmethod
        def record_event(*args, **kwargs):
            return None

    monkeypatch.setattr(
        query_mcp_svc,
        "project_store",
        type(
            "DummyProjectStore",
            (),
            {
                "get": staticmethod(lambda project_id: DummyProject() if project_id == "proj-1" else None),
                "list_all": staticmethod(lambda: [DummyProject()]),
                "list_members": staticmethod(
                    lambda project_id: [
                        type("DummyMember", (), {"employee_id": "emp-1", "enabled": True})()
                    ]
                    if project_id == "proj-1"
                    else []
                ),
            },
        )(),
    )
    monkeypatch.setattr(
        query_mcp_svc,
        "employee_store",
        type(
            "DummyEmployeeStore",
            (),
            {
                "get": staticmethod(lambda employee_id: DummyEmployee() if employee_id == "emp-1" else None),
                "list_all": staticmethod(lambda: [DummyEmployee()]),
            },
        )(),
    )
    monkeypatch.setattr(
        query_mcp_svc,
        "get_project_detail_runtime",
        lambda project_id: {
            "id": "proj-1",
            "name": "项目一",
            "description": "统一查询 MCP 标准链路测试项目",
            "workspace_path": "/workspace/demo",
            "chat_settings": {
                "connector_workspace_path": "/workspace/demo",
                "connector_sandbox_mode": "workspace-write",
                "high_risk_tool_confirm": True,
            },
        }
        if project_id == "proj-1"
        else {"error": f"Project {project_id} not found"},
    )
    monkeypatch.setattr(
        query_mcp_svc,
        "list_project_member_profiles_runtime",
        lambda project_id, include_disabled=False, include_missing=False, rule_limit=30: [
            {
                "employee_id": "emp-1",
                "name": "员工一",
                "description": "负责 query MCP 升级",
                "goal": "补齐联调测试",
                "skill_names": ["query-mcp", "python"],
            }
        ]
        if project_id == "proj-1"
        else [],
    )
    monkeypatch.setattr(
        query_mcp_svc,
        "query_project_rules_runtime",
        lambda project_id, keyword="", employee_id="": [
            {
                "id": "rule-mcp",
                "title": "统一查询 MCP 规则",
                "domain": "mcp",
                "content": "先保留用户原始问题，再读取项目手册并生成执行计划。",
            }
        ]
        if project_id == "proj-1"
        else [],
    )
    monkeypatch.setattr(
        query_mcp_svc,
        "project_ui_rule_summary",
        lambda project_id, limit=30: [
            {"id": "rule-ui", "title": "项目 UI 规则", "domain": "ui"}
        ]
        if project_id == "proj-1"
        else [],
    )
    monkeypatch.setattr(
        projects_router,
        "_build_project_manual_template_payload",
        lambda project_id: {
            "manual": "# 项目一 使用手册\n\n- 先读取项目手册\n- 再执行 resolve_relevant_context 与 generate_execution_plan"
        }
        if project_id == "proj-1"
        else {"manual": ""},
    )

    runtime_module = types.SimpleNamespace(
        list_project_proxy_tools_runtime=lambda project_id, employee_id="": [
            {
                "tool_name": "skill_query__upgrade_mcp",
                "employee_id": "emp-1",
                "employee_name": "员工一",
                "entry_name": "upgrade_query_mcp",
                "description": "升级 /mcp/query/sse 标准链路。",
            }
        ]
        if project_id == "proj-1"
        else [],
        invoke_project_skill_tool_runtime=lambda **kwargs: {
            "tool_name": kwargs["tool_name"],
            "employee_id": kwargs["employee_id"] or "emp-1",
            "status": "ok",
        },
        execute_project_collaboration_runtime=lambda **kwargs: {
            "tool_name": "execute_project_collaboration",
            "task": kwargs["task"],
            "selected_employee_ids": kwargs["employee_ids"] or ["emp-1"],
            "selected_members": [{"employee_id": "emp-1", "name": "员工一"}],
            "candidate_tools": [{"tool_name": "skill_query__upgrade_mcp", "employee_id": "emp-1"}],
            "plan_steps": [
                {"step": "读取项目手册", "tool": "get_manual_content"},
                {"step": "聚合相关上下文", "tool": "resolve_relevant_context"},
                {"step": "生成执行计划", "tool": "generate_execution_plan"},
            ],
            "status": "ok",
        },
    )
    collaboration_module = types.SimpleNamespace(
        execute_project_collaboration_runtime=lambda **kwargs: {
            "selected_employee_ids": kwargs["employee_ids"] or ["emp-1"],
            "selected_members": [{"employee_id": "emp-1", "name": "员工一"}],
            "candidate_tools": [{"tool_name": "skill_query__upgrade_mcp", "employee_id": "emp-1"}],
            "plan_steps": [
                {"step": "读取项目手册", "tool": "get_manual_content"},
                {"step": "聚合相关上下文", "tool": "resolve_relevant_context"},
                {"step": "生成执行计划", "tool": "generate_execution_plan"},
            ],
        }
    )
    monkeypatch.setitem(sys.modules, "services.dynamic_mcp_runtime", runtime_module)
    monkeypatch.setitem(sys.modules, "services.dynamic_mcp_collaboration", collaboration_module)

    def post_jsonrpc(payload: dict, path: str = "/mcp/query/mcp?key=valid-key"):
        monkeypatch.setattr(runtime.query_mcp_proxy_app, "_usage_store", DummyUsageStore())
        monkeypatch.setattr(runtime.query_mcp_proxy_app, "_current_api_key_ctx", ContextVar("query_chain_api", default=""))
        monkeypatch.setattr(runtime.query_mcp_proxy_app, "_current_developer_name_ctx", ContextVar("query_chain_dev", default=""))
        monkeypatch.setattr(runtime.query_mcp_proxy_app, "_save_auto_query_memory", lambda *args, **kwargs: None)
        monkeypatch.setattr(runtime.query_mcp_proxy_app, "_query_app", runtime._create_query_mcp())
        app = create_app()
        with TestClient(app) as client:
            return client.post(
                path,
                headers={"Accept": "application/json, text/event-stream"},
                json=payload,
            )

    return post_jsonrpc


def _configure_query_mcp_memory_chain_env(monkeypatch):
    from services import dynamic_mcp_apps_query as query_mcp_svc

    saved_memories = []
    saved_work_session_events = []

    class DummyMemoryStore:
        def new_id(self):
            return f"mem-{len(saved_memories) + 1}"

        def save(self, memory):
            saved_memories.append(memory)

        def recall(self, employee_id, query, limit, project_name=""):
            matches = [
                item
                for item in saved_memories
                if item.employee_id == employee_id
                and (not project_name or item.project_name == project_name)
                and query in item.content
            ]
            return list(reversed(matches))[:limit]

        def recent(self, employee_id, limit, project_name=""):
            matches = [
                item
                for item in saved_memories
                if item.employee_id == employee_id
                and (not project_name or item.project_name == project_name)
            ]
            return list(reversed(matches))[:limit]

    class DummyWorkSessionStore:
        def new_id(self):
            return f"wse-{len(saved_work_session_events) + 1}"

        def save(self, event):
            saved_work_session_events.append(event)

        def list_events(
            self,
            *,
            project_id="",
            employee_id="",
            session_id="",
            task_tree_session_id="",
            task_tree_chat_session_id="",
            task_node_id="",
            query="",
            limit=200,
        ):
            matches = []
            keyword = str(query or "").strip().lower()
            for item in reversed(saved_work_session_events):
                if project_id and item.project_id != project_id:
                    continue
                if employee_id and item.employee_id != employee_id:
                    continue
                if session_id and item.session_id != session_id:
                    continue
                if task_tree_session_id and getattr(item, "task_tree_session_id", "") != task_tree_session_id:
                    continue
                if (
                    task_tree_chat_session_id
                    and getattr(item, "task_tree_chat_session_id", "") != task_tree_chat_session_id
                ):
                    continue
                if task_node_id and getattr(item, "task_node_id", "") != task_node_id:
                    continue
                if keyword:
                    haystack = "\n".join(
                        [
                            str(item.project_name or ""),
                            str(item.session_id or ""),
                            str(getattr(item, "task_tree_session_id", "") or ""),
                            str(getattr(item, "task_tree_chat_session_id", "") or ""),
                            str(getattr(item, "task_node_id", "") or ""),
                            str(getattr(item, "task_node_title", "") or ""),
                            str(item.event_type or ""),
                            str(item.phase or ""),
                            str(item.step or ""),
                            str(item.status or ""),
                            str(item.goal or ""),
                            str(item.content or ""),
                            *list(item.facts or []),
                            *list(item.changed_files or []),
                            *list(item.verification or []),
                            *list(item.risks or []),
                            *list(item.next_steps or []),
                        ]
                    ).lower()
                    if keyword not in haystack:
                        continue
                matches.append(item)
                if len(matches) >= limit:
                    break
            return matches

    monkeypatch.setattr(query_mcp_svc, "memory_store", DummyMemoryStore())
    monkeypatch.setattr(query_mcp_svc, "work_session_store", DummyWorkSessionStore())
    return _configure_query_mcp_standard_project_chain_env(monkeypatch), saved_memories, saved_work_session_events


def test_query_mcp_mount_runs_standard_project_chain(monkeypatch):
    post_jsonrpc = _configure_query_mcp_standard_project_chain_env(monkeypatch)

    search_response = post_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 21,
            "method": "tools/call",
            "params": {
                "name": "search_ids",
                "arguments": {
                    "keyword": "项目一",
                    "limit": 10,
                },
            },
        }
    )
    search_result = _extract_query_mcp_tool_result(search_response.text)
    project_id = search_result["projects"][0]["id"]

    manual_response = post_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 22,
            "method": "tools/call",
            "params": {
                "name": "get_manual_content",
                "arguments": {
                    "project_id": project_id,
                },
            },
        }
    )
    context_response = post_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 23,
            "method": "tools/call",
            "params": {
                "name": "resolve_relevant_context",
                "arguments": {
                    "task": "继续升级项目一 的 query MCP 标准链路",
                    "project_id": project_id,
                },
            },
        }
    )
    plan_response = post_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 24,
            "method": "tools/call",
            "params": {
                "name": "generate_execution_plan",
                "arguments": {
                    "task": "继续升级项目一 的 query MCP 标准链路",
                    "project_id": project_id,
                },
            },
        }
    )
    collaboration_response = post_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 25,
            "method": "tools/call",
            "params": {
                "name": "execute_project_collaboration",
                "arguments": {
                    "project_id": project_id,
                    "task": "继续升级项目一 的 query MCP 标准链路",
                    "auto_execute": False,
                    "max_employees": 3,
                    "max_tool_calls": 6,
                },
            },
        }
    )

    manual_result = _extract_query_mcp_tool_result(manual_response.text)
    context_result = _extract_query_mcp_tool_result(context_response.text)
    plan_result = _extract_query_mcp_tool_result(plan_response.text)
    collaboration_result = _extract_query_mcp_tool_result(collaboration_response.text)

    assert search_response.status_code == 200
    assert search_result["projects"][0]["id"] == "proj-1"
    assert search_result["projects"][0]["name"] == "项目一"

    assert manual_response.status_code == 200
    assert manual_result["entity_type"] == "project"
    assert manual_result["entity_id"] == "proj-1"
    assert "项目一 使用手册" in manual_result["manual"]

    assert context_response.status_code == 200
    assert context_result["project"]["summary"]["name"] == "项目一"
    assert context_result["matched_members"][0]["employee_id"] == "emp-1"
    assert context_result["matched_rules"][0]["id"] == "rule-mcp"
    assert context_result["matched_tools"][0]["tool_name"] == "skill_query__upgrade_mcp"

    assert plan_response.status_code == 200
    assert plan_result["planning_mode"] == "project-collaboration-runtime"
    assert plan_result["selected_employee_ids"] == ["emp-1"]
    assert plan_result["plan_step_count"] == 3
    assert [item["tool"] for item in plan_result["plan_steps"]] == [
        "get_manual_content",
        "resolve_relevant_context",
        "generate_execution_plan",
    ]

    assert collaboration_response.status_code == 200
    assert collaboration_result["project_id"] == "proj-1"
    assert collaboration_result["project_name"] == "项目一"
    assert collaboration_result["tool_name"] == "execute_project_collaboration"
    assert collaboration_result["selected_employee_ids"] == ["emp-1"]
    assert collaboration_result["candidate_tools"][0]["tool_name"] == "skill_query__upgrade_mcp"
    assert collaboration_result["plan_steps"][0]["tool"] == "get_manual_content"


def test_query_mcp_sse_bridge_runs_standard_project_chain_and_collaboration(monkeypatch):
    post_jsonrpc = _configure_query_mcp_standard_project_chain_env(monkeypatch)
    sse_path = "/mcp/query/sse?key=valid-key"

    search_response = post_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 31,
            "method": "tools/call",
            "params": {
                "name": "search_ids",
                "arguments": {
                    "keyword": "项目一",
                    "limit": 10,
                },
            },
        },
        path=sse_path,
    )
    search_result = _extract_query_mcp_tool_result(search_response.text)
    project_id = search_result["projects"][0]["id"]

    manual_response = post_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 32,
            "method": "tools/call",
            "params": {
                "name": "get_manual_content",
                "arguments": {
                    "project_id": project_id,
                },
            },
        },
        path=sse_path,
    )
    context_response = post_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 33,
            "method": "tools/call",
            "params": {
                "name": "resolve_relevant_context",
                "arguments": {
                    "task": "继续升级项目一 的 query MCP 标准链路",
                    "project_id": project_id,
                },
            },
        },
        path=sse_path,
    )
    plan_response = post_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 34,
            "method": "tools/call",
            "params": {
                "name": "generate_execution_plan",
                "arguments": {
                    "task": "继续升级项目一 的 query MCP 标准链路",
                    "project_id": project_id,
                },
            },
        },
        path=sse_path,
    )
    collaboration_response = post_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 35,
            "method": "tools/call",
            "params": {
                "name": "execute_project_collaboration",
                "arguments": {
                    "project_id": project_id,
                    "task": "继续升级项目一 的 query MCP 标准链路",
                    "auto_execute": False,
                    "max_employees": 3,
                    "max_tool_calls": 6,
                },
            },
        },
        path=sse_path,
    )

    manual_result = _extract_query_mcp_tool_result(manual_response.text)
    context_result = _extract_query_mcp_tool_result(context_response.text)
    plan_result = _extract_query_mcp_tool_result(plan_response.text)
    collaboration_result = _extract_query_mcp_tool_result(collaboration_response.text)

    assert search_response.status_code == 200
    assert search_result["projects"][0]["id"] == "proj-1"

    assert manual_response.status_code == 200
    assert manual_result["entity_type"] == "project"
    assert "项目一 使用手册" in manual_result["manual"]

    assert context_response.status_code == 200
    assert context_result["matched_tools"][0]["tool_name"] == "skill_query__upgrade_mcp"

    assert plan_response.status_code == 200
    assert plan_result["planning_mode"] == "project-collaboration-runtime"
    assert plan_result["selected_employee_ids"] == ["emp-1"]

    assert collaboration_response.status_code == 200
    assert collaboration_result["project_id"] == "proj-1"
    assert collaboration_result["selected_members"][0]["employee_id"] == "emp-1"
    assert collaboration_result["plan_steps"][1]["tool"] == "resolve_relevant_context"


def test_query_mcp_mount_runs_memory_chain(monkeypatch):
    from stores.mcp_bridge import MemoryType

    post_jsonrpc, saved_memories, saved_work_session_events = _configure_query_mcp_memory_chain_env(monkeypatch)

    save_project_response = post_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 41,
            "method": "tools/call",
            "params": {
                "name": "save_project_memory",
                "arguments": {
                    "project_id": "proj-1",
                    "content": "问题：需要补统一查询 MCP 记忆链路\n结论：先打通挂载级验证",
                    "employee_id": "emp-1",
                },
            },
        }
    )
    facts_response = post_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 42,
            "method": "tools/call",
            "params": {
                "name": "save_work_facts",
                "arguments": {
                    "project_id": "proj-1",
                    "employee_id": "emp-1",
                    "session_id": "sess-1",
                    "phase": "Phase 3",
                    "step": "Step 1",
                    "status": "in_progress",
                    "facts": ["已补 query MCP 挂载级记忆测试", "已更新联调文档"],
                    "changed_files": ["web-admin/api/tests/test_unit.py"],
                    "verification": ["pytest mounted memory chain"],
                    "next_steps": ["写入会话事件并恢复检查点"],
                },
            },
        }
    )
    event_response = post_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 43,
            "method": "tools/call",
            "params": {
                "name": "append_session_event",
                "arguments": {
                    "project_id": "proj-1",
                    "employee_id": "emp-1",
                    "session_id": "sess-1",
                    "event_type": "verification",
                    "content": "已运行 mounted memory chain test",
                    "phase": "Phase 3",
                    "step": "Step 2",
                    "status": "completed",
                    "verification": ["mounted memory chain test"],
                    "risks": ["仍需 SSE bridge 回归"],
                },
            },
        }
    )
    resume_response = post_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 44,
            "method": "tools/call",
            "params": {
                "name": "resume_work_session",
                "arguments": {
                    "project_id": "proj-1",
                    "employee_id": "emp-1",
                    "session_id": "sess-1",
                },
            },
        }
    )
    checkpoint_response = post_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 45,
            "method": "tools/call",
            "params": {
                "name": "summarize_checkpoint",
                "arguments": {
                    "project_id": "proj-1",
                    "employee_id": "emp-1",
                    "session_id": "sess-1",
                },
            },
        }
    )

    save_project_result = _extract_query_mcp_tool_result(save_project_response.text)
    facts_result = _extract_query_mcp_tool_result(facts_response.text)
    event_result = _extract_query_mcp_tool_result(event_response.text)
    resume_result = _extract_query_mcp_tool_result(resume_response.text)
    checkpoint_result = _extract_query_mcp_tool_result(checkpoint_response.text)

    assert save_project_response.status_code == 200
    assert save_project_result["status"] == "saved"
    assert save_project_result["type"] == MemoryType.PROJECT_CONTEXT.value
    assert save_project_result["employee_ids"] == ["emp-1"]

    assert facts_response.status_code == 200
    assert facts_result["status"] == "saved"
    assert facts_result["type"] == MemoryType.LEARNED_PATTERN.value

    assert event_response.status_code == 200
    assert event_result["status"] == "saved"
    assert event_result["type"] == MemoryType.KEY_EVENT.value

    assert len(saved_memories) == 3
    assert saved_memories[0].project_name == "项目一"
    assert saved_memories[1].purpose_tags == ("query-mcp", "work-facts", "phase3", "session:sess-1", "phase:phase-3", "step:step-1")
    assert saved_memories[2].purpose_tags == ("query-mcp", "session-event", "verification", "phase3", "session:sess-1", "phase:phase-3", "step:step-2")
    assert len(saved_work_session_events) == 2
    assert saved_work_session_events[0].session_id == "sess-1"
    assert saved_work_session_events[1].event_type == "verification"

    assert resume_response.status_code == 200
    assert resume_result["project_id"] == "proj-1"
    assert resume_result["project_name"] == "项目一"
    assert resume_result["session_id"] == "sess-1"
    assert resume_result["total"] == 2
    assert resume_result["phases"] == ["Phase 3"]
    assert resume_result["steps"] == ["Step 2", "Step 1"]
    assert resume_result["latest_status"] == "completed"
    assert resume_result["items"][0]["trajectory"]["event_type"] == "verification"
    assert resume_result["items"][1]["trajectory"]["facts"][0] == "已补 query MCP 挂载级记忆测试"
    assert "Step 2" in resume_result["checkpoint_summary"]

    assert checkpoint_response.status_code == 200
    assert checkpoint_result["project_id"] == "proj-1"
    assert checkpoint_result["fact_count"] == 1
    assert checkpoint_result["event_count"] == 1
    assert checkpoint_result["phases"] == ["Phase 3"]
    assert checkpoint_result["changed_files"][0] == "web-admin/api/tests/test_unit.py"
    assert checkpoint_result["verification"][0] == "mounted memory chain test"
    assert checkpoint_result["risks"][0] == "仍需 SSE bridge 回归"
    assert checkpoint_result["events"][0]["type"] == MemoryType.KEY_EVENT.value
    assert "项目：项目一" in checkpoint_result["summary"]


def test_query_mcp_sse_bridge_runs_memory_chain(monkeypatch):
    from stores.mcp_bridge import MemoryType

    post_jsonrpc, _saved_memories, saved_work_session_events = _configure_query_mcp_memory_chain_env(monkeypatch)
    sse_path = "/mcp/query/sse?key=valid-key"

    facts_response = post_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 51,
            "method": "tools/call",
            "params": {
                "name": "save_work_facts",
                "arguments": {
                    "project_id": "proj-1",
                    "employee_id": "emp-1",
                    "facts": ["SSE bridge 已打通记忆事实写入"],
                },
            },
        },
        path=sse_path,
    )
    event_response = post_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 52,
            "method": "tools/call",
            "params": {
                "name": "append_session_event",
                "arguments": {
                    "project_id": "proj-1",
                    "employee_id": "emp-1",
                    "session_id": "sess-sse",
                    "event_type": "handoff",
                    "content": "SSE bridge 已写入会话事件",
                },
            },
        },
        path=sse_path,
    )
    checkpoint_response = post_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 53,
            "method": "tools/call",
            "params": {
                "name": "summarize_checkpoint",
                "arguments": {
                    "project_id": "proj-1",
                    "employee_id": "emp-1",
                    "session_id": "sess-sse",
                },
            },
        },
        path=sse_path,
    )

    facts_result = _extract_query_mcp_tool_result(facts_response.text)
    event_result = _extract_query_mcp_tool_result(event_response.text)
    checkpoint_result = _extract_query_mcp_tool_result(checkpoint_response.text)

    assert facts_response.status_code == 200
    assert facts_result["type"] == MemoryType.LEARNED_PATTERN.value
    assert facts_result["session_id"].startswith("ws_proj-1_emp-1_")
    assert facts_result["work_session_event"]["status"] == "saved"

    assert event_response.status_code == 200
    assert event_result["type"] == MemoryType.KEY_EVENT.value

    assert checkpoint_response.status_code == 200
    assert checkpoint_result["project_id"] == "proj-1"
    assert checkpoint_result["session_id"] == "sess-sse"
    assert checkpoint_result["event_count"] == 1
    assert checkpoint_result["events"][0]["type"] == MemoryType.KEY_EVENT.value
    assert len(saved_work_session_events) == 2


def _setup_query_mcp_agent_capability_env(monkeypatch):
    import sys
    import types

    from services import dynamic_mcp_apps_query as query_mcp_svc

    registered_tools: dict[str, object] = {}
    registered_resources: dict[str, object] = {}
    saved_memories = []
    saved_work_session_events = []

    class FakeMcp:
        def tool(self, name=None, description=None):
            def decorator(fn):
                registered_tools[name or fn.__name__] = fn
                return fn

            return decorator

        def resource(self, uri, **_kwargs):
            def decorator(fn):
                registered_resources[uri] = fn
                return fn

            return decorator

    class DummyProject:
        id = "proj-1"
        name = "项目一"
        description = "统一查询 MCP 升级验证项目"

    class DummyEmployee:
        id = "emp-1"
        name = "员工一"
        description = "负责统一查询 MCP 升级"
        goal = "补工具、补测试、补文档"

    class DummyMemoryStore:
        def new_id(self):
            return f"mem-{len(saved_memories) + 1}"

        def save(self, memory):
            saved_memories.append(memory)

        def recall(self, employee_id, query, limit, project_name=""):
            matches = [
                item
                for item in saved_memories
                if item.employee_id == employee_id
                and (not project_name or item.project_name == project_name)
                and query in item.content
            ]
            return list(reversed(matches))[:limit]

        def recent(self, employee_id, limit, project_name=""):
            matches = [
                item
                for item in saved_memories
                if item.employee_id == employee_id
                and (not project_name or item.project_name == project_name)
            ]
            return list(reversed(matches))[:limit]

    class DummyWorkSessionStore:
        def new_id(self):
            return f"wse-{len(saved_work_session_events) + 1}"

        def save(self, event):
            saved_work_session_events.append(event)

        def list_events(self, *, project_id="", employee_id="", session_id="", query="", limit=200):
            matches = []
            keyword = str(query or "").strip().lower()
            for item in reversed(saved_work_session_events):
                if project_id and item.project_id != project_id:
                    continue
                if employee_id and item.employee_id != employee_id:
                    continue
                if session_id and item.session_id != session_id:
                    continue
                if keyword:
                    haystack = "\n".join(
                        [
                            str(item.project_name or ""),
                            str(item.session_id or ""),
                            str(item.event_type or ""),
                            str(item.phase or ""),
                            str(item.step or ""),
                            str(item.status or ""),
                            str(item.goal or ""),
                            str(item.content or ""),
                            *list(item.facts or []),
                            *list(item.changed_files or []),
                            *list(item.verification or []),
                            *list(item.risks or []),
                            *list(item.next_steps or []),
                        ]
                    ).lower()
                    if keyword not in haystack:
                        continue
                matches.append(item)
                if len(matches) >= limit:
                    break
            return matches

    monkeypatch.setattr(query_mcp_svc, "_new_mcp", lambda _service_name: FakeMcp())
    monkeypatch.setattr(
        query_mcp_svc,
        "project_store",
        type(
            "DummyProjectStore",
            (),
            {
                "get": staticmethod(lambda project_id: DummyProject() if project_id == "proj-1" else None),
                "list_all": staticmethod(lambda: [DummyProject()]),
                "list_members": staticmethod(
                    lambda project_id: [
                        type("DummyMember", (), {"employee_id": "emp-1", "enabled": True})()
                    ]
                    if project_id == "proj-1"
                    else []
                ),
            },
        )(),
    )
    monkeypatch.setattr(
        query_mcp_svc,
        "employee_store",
        type(
            "DummyEmployeeStore",
            (),
            {
                "get": staticmethod(lambda employee_id: DummyEmployee() if employee_id == "emp-1" else None),
                "list_all": staticmethod(lambda: [DummyEmployee()]),
            },
        )(),
    )
    monkeypatch.setattr(
        query_mcp_svc,
        "get_project_detail_runtime",
        lambda project_id: {
            "id": "proj-1",
            "name": "项目一",
            "workspace_path": "/workspace/demo",
            "description": "统一查询 MCP 升级验证项目",
            "chat_settings": {
                "connector_workspace_path": "/workspace/demo",
                "connector_sandbox_mode": "workspace-write",
                "high_risk_tool_confirm": True,
            },
        }
        if project_id == "proj-1"
        else {"error": f"Project {project_id} not found"},
    )
    monkeypatch.setattr(
        query_mcp_svc,
        "get_project_employee_detail_runtime",
        lambda project_id, employee_id: {
            "project_id": project_id,
            "employee_id": employee_id,
            "role": "member",
        },
    )
    monkeypatch.setattr(
        query_mcp_svc,
        "list_project_member_profiles_runtime",
        lambda project_id, include_disabled=False, include_missing=False, rule_limit=30: [
            {
                "employee_id": "emp-1",
                "name": "员工一",
                "description": "负责统一查询 MCP 升级与测试补齐",
                "goal": "补工具、补测试、补文档",
                "skill_names": ["query-mcp", "python"],
            }
        ]
        if project_id == "proj-1"
        else [],
    )
    monkeypatch.setattr(
        query_mcp_svc,
        "query_project_rules_runtime",
        lambda project_id, keyword="", employee_id="": [
            {
                "id": "rule-mcp",
                "title": "统一查询 MCP 升级规则",
                "domain": "mcp",
                "content": "通过 /mcp/query/sse 升级工具、资源和验证链路。",
            }
        ]
        if project_id == "proj-1"
        else [],
    )
    monkeypatch.setattr(
        query_mcp_svc,
        "project_ui_rule_summary",
        lambda project_id, limit=30: [
            {"id": "rule-ui", "title": "项目 UI 规则", "domain": "ui"}
        ]
        if project_id == "proj-1"
        else [],
    )
    monkeypatch.setattr(query_mcp_svc, "memory_store", DummyMemoryStore())
    monkeypatch.setattr(query_mcp_svc, "work_session_store", DummyWorkSessionStore())

    runtime_module = types.SimpleNamespace(
        list_project_proxy_tools_runtime=lambda project_id, employee_id="": [
            {
                "tool_name": "skill_query__upgrade_mcp",
                "employee_id": "emp-1",
                "employee_name": "员工一",
                "entry_name": "upgrade_query_mcp",
                "description": "升级 /mcp/query/sse 统一查询 MCP 工具与测试。",
            }
        ]
        if project_id == "proj-1"
        else [],
        invoke_project_skill_tool_runtime=lambda **kwargs: {
            "tool_name": kwargs["tool_name"],
            "employee_id": kwargs["employee_id"] or "emp-1",
            "status": "ok",
        },
        execute_project_collaboration_runtime=lambda **kwargs: {
            "tool_name": "execute_project_collaboration",
            "task": kwargs["task"],
            "selected_employee_ids": kwargs["employee_ids"] or ["emp-1"],
            "selected_members": [{"employee_id": "emp-1", "name": "员工一"}],
            "candidate_tools": [{"tool_name": "skill_query__upgrade_mcp", "employee_id": "emp-1"}],
            "plan_steps": [
                {"step": "分析任务", "tool": "analyze_task"},
                {"step": "聚合上下文", "tool": "resolve_relevant_context"},
                {"step": "执行验证", "tool": "build_delivery_report"},
            ],
            "status": "ok",
        },
    )
    collaboration_module = types.SimpleNamespace(
        execute_project_collaboration_runtime=lambda **kwargs: {
            "selected_employee_ids": kwargs["employee_ids"] or ["emp-1"],
            "selected_members": [{"employee_id": "emp-1", "name": "员工一"}],
            "candidate_tools": [{"tool_name": "skill_query__upgrade_mcp", "employee_id": "emp-1"}],
            "plan_steps": [
                {"step": "分析任务", "tool": "analyze_task"},
                {"step": "聚合上下文", "tool": "resolve_relevant_context"},
                {"step": "执行验证", "tool": "build_delivery_report"},
            ],
        }
    )
    monkeypatch.setitem(sys.modules, "services.dynamic_mcp_runtime", runtime_module)
    monkeypatch.setitem(sys.modules, "services.dynamic_mcp_collaboration", collaboration_module)

    query_mcp_svc.create_query_mcp()
    return registered_tools, registered_resources, saved_memories, saved_work_session_events


def test_query_mcp_exposes_agent_capability_tools_resources_and_policies(monkeypatch):
    registered_tools, registered_resources, _saved_memories, _saved_work_session_events = _setup_query_mcp_agent_capability_env(monkeypatch)

    assert "analyze_task" in registered_tools
    assert "resolve_relevant_context" in registered_tools
    assert "generate_execution_plan" in registered_tools
    assert "classify_command_risk" in registered_tools
    assert "check_workspace_scope" in registered_tools
    assert "resolve_execution_mode" in registered_tools
    assert "check_operation_policy" in registered_tools
    assert "start_work_session" in registered_tools
    assert "build_delivery_report" in registered_tools
    assert "generate_release_note_entry" in registered_tools

    assert "query://client-profile/claude-code" in registered_resources
    assert "query://client-profile/codex" in registered_resources
    assert "query://client-profile/generic-cli" in registered_resources

    usage_guide = registered_resources["query://usage-guide"]()
    claude_profile = registered_resources["query://client-profile/claude-code"]()
    codex_profile = registered_resources["query://client-profile/codex"]()
    generic_profile = registered_resources["query://client-profile/generic-cli"]()

    assert "build_delivery_report" in usage_guide
    assert "generate_release_note_entry" in usage_guide
    assert "check_operation_policy" in usage_guide
    assert "start_work_session" in usage_guide
    assert "任务树节点必须直接描述面向用户目标的工作步骤" in usage_guide
    assert "优先使用项目绑定员工、规则和技能" in usage_guide
    assert "重新获取与当前任务直接相关的规则正文" in usage_guide
    assert "save_work_facts" in claude_profile
    assert "任务树节点必须描述面向用户目标的真实工作步骤" in claude_profile
    assert "优先使用项目绑定员工、规则和技能" in claude_profile
    assert "search_ids" in codex_profile
    assert "get_manual_content" in codex_profile
    assert "build_delivery_report" in codex_profile
    assert "Auto inferred proxy entry from scripts/..." in codex_profile
    assert "优先使用项目绑定员工、规则和技能" in codex_profile
    assert "重新获取与当前任务直接相关的规则正文" in codex_profile
    assert "analyze_task" in generic_profile
    assert "节点必须直接对应用户目标" in generic_profile
    assert "优先使用项目绑定员工、规则和技能" in generic_profile

    analysis = registered_tools["analyze_task"](
        "继续升级 /mcp/query/sse，必须补测试并更新 docs/总结文档.md",
        project_id="proj-1",
    )
    context = registered_tools["resolve_relevant_context"](
        "升级 /mcp/query/sse 的 query MCP 工具与测试",
        project_id="proj-1",
    )
    plan = registered_tools["generate_execution_plan"](
        "升级 /mcp/query/sse 的 query MCP 工具与测试",
        project_id="proj-1",
    )
    risk = registered_tools["classify_command_risk"](
        command="git push origin feature/mcp-upgrade",
        tool_name="local_connector_run_command",
        project_id="proj-1",
    )
    scope = registered_tools["check_workspace_scope"](
        "/workspace/demo/docs/总结文档.md",
        project_id="proj-1",
    )
    mode = registered_tools["resolve_execution_mode"](
        project_id="proj-1",
        command="sed -n '1,20p' docs/总结文档.md",
    )
    policy = registered_tools["check_operation_policy"](
        project_id="proj-1",
        tool_name="unknown_tool",
        path="/workspace/demo/docs/总结文档.md",
    )
    delivery_report = registered_tools["build_delivery_report"](
        title="统一查询 MCP 升级",
        project_id="proj-1",
        summary="已补齐 query MCP 能力单测",
        changed_files=[
            "web-admin/api/tests/test_unit.py",
            "docs/总结文档.md",
        ],
        verification=["uv run pytest web-admin/api/tests/test_unit.py -k query_mcp"],
        risks=["仍需真实 SSE 联调"],
        next_steps=["继续补真实链路验证"],
    )
    release_note = registered_tools["generate_release_note_entry"](
        version="v0.2.0",
        release_date="2026-04-01",
        key_changes=[
            "新增 query MCP Phase 1-4 能力单测",
            "补充交付报告与更新日志条目生成能力验证",
        ],
        project_id="proj-1",
    )

    assert analysis["project_id"] == "proj-1"
    assert "mcp-upgrade" in analysis["task_types"]
    assert "/mcp/query/sse" in analysis["mentioned_paths"]
    assert any("必须补测试并更新 docs/总结文档.md" in item for item in analysis["constraints"])
    assert "统一查询 MCP 新工具或资源能力" in analysis["deliverables"]

    assert context["project"]["summary"]["name"] == "项目一"
    assert context["matched_members"][0]["employee_id"] == "emp-1"
    assert context["matched_rules"][0]["id"] == "rule-mcp"
    assert context["matched_tools"][0]["tool_name"] == "skill_query__upgrade_mcp"

    assert plan["planning_mode"] == "project-collaboration-runtime"
    assert plan["selected_employee_ids"] == ["emp-1"]
    assert plan["plan_step_count"] == 3

    assert risk["risk_level"] == "high"
    assert risk["requires_confirmation"] is True
    assert "high_risk_command" in risk["indicators"]

    assert scope["allowed"] is True
    assert scope["within_workspace"] is True
    assert scope["reason"] == "inside_workspace"

    assert mode["mode"] == "local_connector"
    assert mode["sandbox_mode"] == "workspace-write"

    assert policy["allowed"] is False
    assert "tool_not_in_project_scope" in policy["policy_reasons"]
    assert policy["workspace_scope"]["within_workspace"] is True

    assert delivery_report["project_name"] == "项目一"
    assert "web-admin/api/tests/test_unit.py" in delivery_report["report_markdown"]
    assert "uv run pytest web-admin/api/tests/test_unit.py -k query_mcp" in delivery_report["report_markdown"]

    assert release_note["project_name"] == "项目一"
    assert "2026-04-01" in release_note["entry_markdown"]
    assert "新增 query MCP Phase 1-4 能力单测" in release_note["entry_markdown"]


def test_query_mcp_work_session_tools_roundtrip(monkeypatch):
    from stores.mcp_bridge import MemoryType

    registered_tools, _registered_resources, saved_memories, saved_work_session_events = _setup_query_mcp_agent_capability_env(monkeypatch)

    started = registered_tools["start_work_session"](
        "proj-1",
        employee_id="emp-1",
        title="统一查询 MCP 轨迹升级",
        goal="把记忆升级成可恢复执行轨迹",
        phase="Phase 3",
        step="Step 0",
    )
    session_id = started["session_id"]

    save_result = registered_tools["save_work_facts"](
        "proj-1",
        facts=["已补 query MCP 单测", "已更新 docs/总结文档.md"],
        employee_id="emp-1",
        session_id=session_id,
        phase="Phase 3",
        step="Step 1",
        status="in_progress",
        goal="把记忆升级成可恢复执行轨迹",
        changed_files=[
            "web-admin/api/services/dynamic_mcp_apps_query.py",
            "web-admin/api/tests/test_unit.py",
        ],
        verification=["python -m py_compile web-admin/api/services/dynamic_mcp_apps_query.py"],
        risks=["仍需 mounted JSON-RPC 回归"],
        next_steps=["补挂载级与 SSE bridge 测试"],
    )
    event_result = registered_tools["append_session_event"](
        "proj-1",
        session_id=session_id,
        event_type="verification",
        content="已运行 query MCP 定向测试",
        employee_id="emp-1",
        phase="Phase 3",
        step="Step 2",
        status="completed",
        changed_files=["web-admin/api/tests/test_unit.py"],
        verification=["uv run pytest web-admin/api/tests/test_unit.py -k query_mcp"],
        next_steps=["更新 docs/总结文档.md"],
    )
    registered_tools["append_session_event"](
        "proj-1",
        session_id="sess-2",
        event_type="notes",
        content="其他会话内容",
        employee_id="emp-1",
    )
    resumed = registered_tools["resume_work_session"](
        "proj-1",
        session_id=session_id,
        employee_id="emp-1",
    )
    checkpoint = registered_tools["summarize_checkpoint"](
        "proj-1",
        session_id=session_id,
        employee_id="emp-1",
    )

    assert started["status"] == "started"
    assert started["project_id"] == "proj-1"
    assert started["employee_id"] == "emp-1"
    assert session_id.startswith("ws_proj-1_emp-1_")
    assert started["trajectory"]["event_type"] == "start"
    assert started["work_session_event"]["status"] == "saved"
    assert started["recommended_next_tool"] == "save_work_facts"

    assert save_result["status"] == "saved"
    assert save_result["saved_count"] == 1
    assert save_result["type"] == MemoryType.LEARNED_PATTERN.value
    assert save_result["session_id"] == session_id
    assert save_result["work_session_event"]["status"] == "saved"

    assert event_result["status"] == "saved"
    assert event_result["saved_count"] == 1
    assert event_result["type"] == MemoryType.KEY_EVENT.value

    assert len(saved_memories) == 3
    first_session_tag = next(tag for tag in saved_memories[0].purpose_tags if tag.startswith("session:"))
    second_session_tag = next(tag for tag in saved_memories[1].purpose_tags if tag.startswith("session:"))
    assert first_session_tag.startswith("session:ws-proj-1-emp-1-")
    assert second_session_tag == first_session_tag
    assert saved_memories[0].purpose_tags[:3] == ("query-mcp", "work-facts", "phase3")
    assert saved_memories[0].purpose_tags[-2:] == ("phase:phase-3", "step:step-1")
    assert saved_memories[1].purpose_tags[:4] == ("query-mcp", "session-event", "verification", "phase3")
    assert saved_memories[1].purpose_tags[-2:] == ("phase:phase-3", "step:step-2")
    assert saved_memories[2].purpose_tags == ("query-mcp", "session-event", "notes", "phase3", "session:sess-2")
    assert len(saved_work_session_events) == 4
    assert saved_work_session_events[0].source_kind == "session-start"
    assert saved_work_session_events[0].event_type == "start"
    assert saved_work_session_events[1].source_kind == "work-facts"
    assert saved_work_session_events[2].event_type == "verification"
    assert saved_work_session_events[3].session_id == "sess-2"

    assert resumed["project_id"] == "proj-1"
    assert resumed["session_id"] == session_id
    assert resumed["total"] == 3
    assert resumed["phases"] == ["Phase 3"]
    assert resumed["steps"] == ["Step 2", "Step 1", "Step 0"]
    assert resumed["changed_files"][0] == "web-admin/api/tests/test_unit.py"
    assert resumed["items"][0]["trajectory"]["event_type"] == "verification"
    assert resumed["items"][1]["trajectory"]["facts"][0] == "已补 query MCP 单测"
    assert resumed["items"][2]["trajectory"]["event_type"] == "start"
    assert resumed["timeline"][0]["status"] == "completed"
    assert "Step 2" in resumed["checkpoint_summary"]

    assert checkpoint["project_name"] == "项目一"
    assert checkpoint["session_id"] == session_id
    assert checkpoint["fact_count"] == 1
    assert checkpoint["event_count"] == 2
    assert checkpoint["phases"] == ["Phase 3"]
    assert checkpoint["steps"] == ["Step 2", "Step 1", "Step 0"]
    assert checkpoint["latest_status"] == "completed"
    assert checkpoint["verification"][0] == "uv run pytest web-admin/api/tests/test_unit.py -k query_mcp"
    assert checkpoint["risks"][0] == "仍需 mounted JSON-RPC 回归"
    assert checkpoint["next_steps"][0] == "更新 docs/总结文档.md"
    assert checkpoint["events"][0]["type"] == MemoryType.KEY_EVENT.value
    assert checkpoint["events"][1]["trajectory"]["event_type"] == "start"
    assert checkpoint["facts"][0]["trajectory"]["goal"] == "把记忆升级成可恢复执行轨迹"
    assert "项目：项目一" in checkpoint["summary"]


def test_query_mcp_save_work_facts_autogenerates_session_id(monkeypatch):
    from stores.mcp_bridge import MemoryType
    import services.project_chat_task_tree as task_tree_svc

    registered_tools, _registered_resources, saved_memories, saved_work_session_events = _setup_query_mcp_agent_capability_env(monkeypatch)
    task_tree_state = {}

    def fake_ensure_task_tree(**kwargs):
      session = task_tree_state.get(kwargs["chat_session_id"])
      if session is None:
          session = {
              "id": "tts-1",
              "root_goal": kwargs["root_goal"],
              "chat_session_id": kwargs["chat_session_id"],
              "source_chat_session_id": kwargs["chat_session_id"],
              "current_node": {
                  "id": "ttn-1",
                  "title": "计划节点",
                  "status": "pending",
              },
          }
          task_tree_state[kwargs["chat_session_id"]] = session
      return session

    def fake_get_task_tree_for_chat_session(project_id, username, chat_session_id):
        _ = (project_id, username)
        return task_tree_state.get(chat_session_id)

    def fake_update_task_node(project_id, username, chat_session_id, node_id, status="", verification_result="", summary_for_model="", **kwargs):
        _ = (project_id, username, node_id, kwargs)
        session = task_tree_state[chat_session_id]
        session["current_node"] = {
            **session.get("current_node", {}),
            "id": session.get("current_node", {}).get("id", "ttn-1"),
            "title": session.get("current_node", {}).get("title", "计划节点"),
            "status": status or session.get("current_node", {}).get("status", "pending"),
            "verification_result": verification_result,
            "summary_for_model": summary_for_model,
        }
        return session

    monkeypatch.setattr(task_tree_svc, "ensure_task_tree", fake_ensure_task_tree)
    monkeypatch.setattr(task_tree_svc, "get_task_tree_for_chat_session", fake_get_task_tree_for_chat_session)
    monkeypatch.setattr(task_tree_svc, "update_task_node", fake_update_task_node)
    monkeypatch.setattr(task_tree_svc, "serialize_task_tree", lambda session: dict(session))

    result = registered_tools["save_work_facts"](
        "proj-1",
        facts=["未显式传 session_id 也要建立正式工作轨迹"],
        employee_id="emp-1",
        phase="Phase 4",
        step="Step 1",
        status="in_progress",
    )

    assert result["status"] == "saved"
    assert result["type"] == MemoryType.LEARNED_PATTERN.value
    assert result["session_id"].startswith("ws_proj-1_emp-1_")
    assert result["chat_session_id"] == result["session_id"]
    assert result["trajectory"]["session_id"] == result["session_id"]
    assert result["trajectory"]["task_tree_chat_session_id"] == result["session_id"]
    assert result["work_session_event"]["status"] == "saved"
    assert result["task_tree"]["chat_session_id"] == result["session_id"]
    assert len(saved_memories) == 1
    assert len(saved_work_session_events) == 1
    assert saved_work_session_events[0].session_id == result["session_id"]
    assert saved_work_session_events[0].task_tree_chat_session_id == result["session_id"]


def test_query_mcp_work_session_tools_accept_string_list_fields(monkeypatch):
    registered_tools, _registered_resources, _saved_memories, saved_work_session_events = _setup_query_mcp_agent_capability_env(monkeypatch)

    started = registered_tools["start_work_session"](
        "proj-1",
        employee_id="emp-1",
        goal="修复统一 MCP 轨迹字段单字符串报错",
    )
    session_id = started["session_id"]

    save_result = registered_tools["save_work_facts"](
        "proj-1",
        facts="已定位 save_work_facts 的列表字段 schema 过严",
        employee_id="emp-1",
        session_id=session_id,
        changed_files="web-admin/api/services/dynamic_mcp_apps_query.py",
        verification="python -m py_compile web-admin/api/services/dynamic_mcp_apps_query.py",
        next_steps="补回归测试",
    )
    event_result = registered_tools["append_session_event"](
        "proj-1",
        session_id=session_id,
        event_type="verification",
        content="已兼容单字符串输入",
        employee_id="emp-1",
        changed_files="web-admin/api/tests/test_unit.py",
        verification="uv run pytest web-admin/api/tests/test_unit.py -k string_list_fields",
        next_steps="检查 query sse 真实调用",
    )
    report = registered_tools["build_delivery_report"](
        title="统一 MCP 列表字段兼容",
        project_id="proj-1",
        summary="已兼容字符串形式的 changed_files / verification / next_steps",
        changed_files="web-admin/api/services/dynamic_mcp_apps_query.py",
        verification="python -m py_compile web-admin/api/services/dynamic_mcp_apps_query.py",
        next_steps="补充 transport 层回归",
    )

    assert save_result["status"] == "saved"
    assert event_result["status"] == "saved"
    assert "web-admin/api/services/dynamic_mcp_apps_query.py" in report["report_markdown"]
    assert "python -m py_compile web-admin/api/services/dynamic_mcp_apps_query.py" in report["report_markdown"]
    assert saved_work_session_events[1].changed_files == ["web-admin/api/services/dynamic_mcp_apps_query.py"]
    assert saved_work_session_events[1].verification == ["python -m py_compile web-admin/api/services/dynamic_mcp_apps_query.py"]
    assert saved_work_session_events[2].next_steps == ["检查 query sse 真实调用"]


def test_query_mcp_list_recent_project_requirements_supports_recent_and_date_filters(monkeypatch):
    registered_tools, _registered_resources, _saved_memories, saved_work_session_events = _setup_query_mcp_agent_capability_env(monkeypatch)

    session_a = registered_tools["start_work_session"](
        "proj-1",
        employee_id="emp-1",
        goal="恢复统一查询 MCP 地址配置",
        phase="排查",
        step="定位原因",
    )["session_id"]
    registered_tools["save_work_facts"](
        "proj-1",
        employee_id="emp-1",
        session_id=session_a,
        goal="恢复统一查询 MCP 地址配置",
        phase="实现",
        step="恢复配置",
        facts=["已恢复统一查询 MCP 地址配置"],
        status="in_progress",
        changed_files=["web-admin/api/services/dynamic_mcp_apps_query.py"],
    )
    registered_tools["append_session_event"](
        "proj-1",
        employee_id="emp-1",
        session_id=session_a,
        event_type="verification",
        content="已验证地址配置恢复完成",
        phase="验证",
        step="回归检查",
        status="completed",
        verification=["uv run pytest web-admin/api/tests/test_unit.py -k requirement_history"],
    )

    session_b = registered_tools["start_work_session"](
        "proj-1",
        employee_id="emp-1",
        goal="补回全局语音助手配置",
        phase="排查",
        step="检查丢失项",
    )["session_id"]
    registered_tools["append_session_event"](
        "proj-1",
        employee_id="emp-1",
        session_id=session_b,
        event_type="notes",
        content="已确认语音助手配置项缺失",
        phase="排查",
        step="检查丢失项",
        status="in_progress",
    )

    timestamps = [
        "2026-04-09T09:00:00+00:00",
        "2026-04-10T07:20:00+00:00",
        "2026-04-10T08:30:00+00:00",
        "2026-04-08T11:00:00+00:00",
        "2026-04-08T11:30:00+00:00",
    ]
    for event, timestamp in zip(saved_work_session_events, timestamps):
        event.created_at = timestamp
        event.updated_at = timestamp

    recent = registered_tools["list_recent_project_requirements"]("proj-1", employee_id="emp-1", limit=5)

    assert recent["source"] == "work-session"
    assert recent["total"] == 2
    assert [item["requirement_title"] for item in recent["requirements"]] == [
        "恢复统一查询 MCP 地址配置",
        "补回全局语音助手配置",
    ]
    assert recent["requirements"][0]["latest_modified_at"] == "2026-04-10T08:30:00+00:00"
    assert recent["requirements"][0]["first_seen_at"] == "2026-04-09T09:00:00+00:00"
    assert recent["requirements"][0]["history_count"] == 3
    assert recent["requirements"][1]["latest_status"] == "in_progress"

    filtered = registered_tools["list_recent_project_requirements"](
        "proj-1",
        employee_id="emp-1",
        date_from="2026-04-10",
        date_to="2026-04-10",
        limit=5,
    )

    assert filtered["total"] == 1
    assert filtered["requirements"][0]["requirement_title"] == "恢复统一查询 MCP 地址配置"


def test_query_mcp_get_requirement_history_returns_latest_modified_time(monkeypatch):
    registered_tools, _registered_resources, _saved_memories, saved_work_session_events = _setup_query_mcp_agent_capability_env(monkeypatch)

    session_id = registered_tools["start_work_session"](
        "proj-1",
        employee_id="emp-1",
        goal="恢复统一查询 MCP 地址配置",
        phase="排查",
        step="定位原因",
    )["session_id"]
    registered_tools["save_work_facts"](
        "proj-1",
        employee_id="emp-1",
        session_id=session_id,
        goal="恢复统一查询 MCP 地址配置",
        phase="实现",
        step="恢复配置",
        facts=["已恢复统一查询 MCP 地址配置"],
        status="in_progress",
    )
    registered_tools["append_session_event"](
        "proj-1",
        employee_id="emp-1",
        session_id=session_id,
        event_type="verification",
        content="已验证地址配置恢复完成",
        phase="验证",
        step="回归检查",
        status="completed",
        verification=["uv run pytest web-admin/api/tests/test_unit.py -k requirement_history"],
    )

    timestamps = [
        "2026-04-09T09:00:00+00:00",
        "2026-04-10T07:20:00+00:00",
        "2026-04-10T08:30:00+00:00",
    ]
    for event, timestamp in zip(saved_work_session_events, timestamps):
        event.created_at = timestamp
        event.updated_at = timestamp

    result = registered_tools["get_requirement_history"](
        "proj-1",
        keyword="地址配置",
        employee_id="emp-1",
        limit=5,
    )

    assert result["source"] == "work-session"
    assert result["total"] == 1
    assert result["latest_modified_at"] == "2026-04-10T08:30:00+00:00"
    assert result["first_seen_at"] == "2026-04-09T09:00:00+00:00"
    assert result["matched_requirement"]["requirement_title"] == "恢复统一查询 MCP 地址配置"
    assert result["matched_requirement"]["history"][0]["event_type"] == "verification"
    assert result["matched_requirement"]["history"][0]["status"] == "completed"


def test_query_mcp_get_requirement_history_falls_back_to_project_memory(monkeypatch):
    registered_tools, _registered_resources, saved_memories, _saved_work_session_events = _setup_query_mcp_agent_capability_env(monkeypatch)

    registered_tools["save_project_memory"](
        "proj-1",
        employee_id="emp-1",
        content="问题：恢复统一查询 MCP 地址配置\n结论：已去掉默认 project_id 并保留提示词绑定建议",
    )

    object.__setattr__(saved_memories[0], "created_at", "2026-04-07T09:00:00+00:00")

    result = registered_tools["get_requirement_history"](
        "proj-1",
        keyword="地址配置",
        employee_id="emp-1",
        limit=5,
    )

    assert result["source"] == "project-memory"
    assert result["total"] == 1
    assert result["latest_modified_at"] == "2026-04-07T09:00:00+00:00"
    assert result["matched_requirement"]["requirement_title"] == "恢复统一查询 MCP 地址配置"
    assert result["matched_requirement"]["source_kinds"] == ["project-memory"]
    assert result["matched_requirement"]["history"][0]["summary"].startswith("问题：恢复统一查询 MCP 地址配置")


def test_query_project_rules_runtime_includes_project_ui_rules(monkeypatch):
    from services import dynamic_mcp_profiles as profiles_svc

    class DummyProject:
        ui_rule_ids = ["rule-ui"]

    class DummyMember:
        employee_id = "emp-1"

    class DummyEmployee:
        rule_ids = ["rule-emp"]
        rule_domains = []

    class DummyRule:
        def __init__(self, rule_id: str, title: str, domain: str, content: str) -> None:
            self.id = rule_id
            self.title = title
            self.domain = domain
            self.content = content

    monkeypatch.setattr(
        profiles_svc,
        "project_store",
        type(
            "DummyProjectStore",
            (),
            {
                "get": staticmethod(lambda project_id: DummyProject() if project_id == "proj-1" else None),
                "list_members": staticmethod(lambda project_id: [DummyMember()] if project_id == "proj-1" else []),
            },
        )(),
    )
    monkeypatch.setattr(
        profiles_svc,
        "employee_store",
        type("DummyEmployeeStore", (), {"get": staticmethod(lambda employee_id: DummyEmployee() if employee_id == "emp-1" else None)})(),
    )
    monkeypatch.setattr(
        profiles_svc,
        "rule_store",
        type(
            "DummyRuleStore",
            (),
            {
                "get": staticmethod(
                    lambda rule_id: {
                        "rule-ui": DummyRule("rule-ui", "项目 UI 规则", "ui", "按钮圆角 12px"),
                        "rule-emp": DummyRule("rule-emp", "员工规则", "frontend", "组件命名统一"),
                    }.get(rule_id)
                ),
                "list_all": staticmethod(lambda: []),
            },
        )(),
    )
    monkeypatch.setattr(
        profiles_svc,
        "serialize_rule",
        lambda rule: {"id": rule.id, "title": rule.title, "domain": rule.domain, "content": rule.content},
    )

    results = profiles_svc.query_project_rules_runtime("proj-1")

    assert [item["id"] for item in results] == ["rule-ui", "rule-emp"]
    assert results[0]["binding_scope"] == "project_ui"
    assert results[1]["binding_scope"] == "employee"


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


def test_project_memory_matches_project_prefers_explicit_project_id_binding():
    from routers import projects as projects_router
    from stores.json.project_store import ProjectConfig

    project = ProjectConfig(id="proj-1", name="项目一")
    wrong_memory = type(
        "DummyMemory",
        (),
        {
            "project_name": "项目一",
            "content": "[项目ID] proj-2\n[项目名称] 项目一\n问题：串项目",
            "purpose_tags": ("project-id:proj-2",),
        },
    )()
    right_memory = type(
        "DummyMemory",
        (),
        {
            "project_name": "项目一",
            "content": "[项目ID] proj-1\n[项目名称] 项目一\n问题：正确项目",
            "purpose_tags": ("project-id:proj-1",),
        },
    )()

    assert projects_router._project_memory_matches_project(wrong_memory, project) is False
    assert projects_router._project_memory_matches_project(right_memory, project) is True


def test_resolve_project_workspace_for_chat_prefers_connector_workspace():
    from routers import projects as projects_router
    from stores.json.project_store import ProjectConfig

    project = ProjectConfig(
        id="proj-1",
        name="项目一",
        workspace_path="/tmp/project-workspace",
    )

    resolved = projects_router._resolve_project_workspace_for_chat(
        project,
        {"connector_workspace_path": "/tmp/connector-workspace"},
    )

    assert resolved == "/tmp/connector-workspace"


def test_resolve_local_connector_coding_tools_returns_registered_tools(monkeypatch):
    from routers import projects as projects_router

    connector = object()

    tools, selected_connector, sandbox_mode = projects_router._resolve_local_connector_coding_tools(
        {"sub": "tester", "role": "admin"},
        {
            "local_connector_id": "connector-1",
            "connector_workspace_path": "/tmp/connector-workspace",
            "connector_sandbox_mode": "workspace-write",
        },
        "/tmp/project-workspace",
    )

    assert selected_connector is None
    assert tools == []
    assert sandbox_mode == "workspace-write"

    selected_connector = connector

    def fake_resolve(connector_id, auth_payload):
        assert connector_id == "connector-1"
        assert auth_payload["sub"] == "tester"
        return selected_connector

    monkeypatch.setattr(projects_router, "_resolve_accessible_local_connector", fake_resolve)
    tools, selected_connector, sandbox_mode = projects_router._resolve_local_connector_coding_tools(
        {"sub": "tester", "role": "admin"},
        {
            "local_connector_id": "connector-1",
            "connector_workspace_path": "/tmp/connector-workspace",
            "connector_sandbox_mode": "workspace-write",
        },
        "/tmp/project-workspace",
    )

    tool_names = {item["tool_name"] for item in tools}
    assert selected_connector is connector
    assert sandbox_mode == "workspace-write"
    assert "local_connector_read_file" in tool_names
    assert "local_connector_run_command" in tool_names
    assert all(item["workspace_path"] == "/tmp/connector-workspace" for item in tools)


def test_project_chat_providers_route_returns_connector_workspace_path(tmp_path, monkeypatch):
    from routers import projects as projects_router
    from services import dynamic_mcp_runtime
    from stores.json.project_store import ProjectConfig

    client, project_store = _build_project_api_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "tester", "role": "admin"},
    )
    project_store.save(
        ProjectConfig(
            id="proj-1",
            name="项目一",
            workspace_path="/tmp/project-workspace",
            chat_settings={
                "local_connector_id": "connector-1",
                "connector_workspace_path": "/tmp/connector-workspace",
                "connector_sandbox_mode": "workspace-write",
            },
        )
    )
    monkeypatch.setattr(
        projects_router,
        "_pick_chat_provider",
        lambda provider_id, auth_payload: (
            {"id": "provider-1", "default_model": "glm-test"},
            [{"id": "provider-1", "default_model": "glm-test"}],
        ),
    )
    monkeypatch.setattr(projects_router, "_build_chat_mcp_modules", lambda project_id: {})
    monkeypatch.setattr(dynamic_mcp_runtime, "list_project_external_tools_runtime", lambda project_id: [])

    response = client.get("/api/projects/proj-1/chat/providers")

    assert response.status_code == 200
    payload = response.json()
    assert payload["workspace_path"] == "/tmp/connector-workspace"
    assert payload["project_workspace_path"] == "/tmp/project-workspace"
    assert payload["chat_settings"]["connector_workspace_path"] == "/tmp/connector-workspace"


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

    result = await employees_router.create_employee_from_draft(req, {"sub": "tester", "role": "admin"})

    assert result["status"] == "created"
    assert len(result["created_skills"]) == 1
    assert len(result["created_rules"]) >= 1

    employee = employee_store.get(result["employee"]["id"])
    assert employee is not None
    assert employee.skills == [result["created_skills"][0]["id"]]
    assert result["created_rules"][0]["id"] in employee.rule_ids

    created_skill = skill_store.get(result["created_skills"][0]["id"])
    assert created_skill is not None
    skill_package = skill_store.package_path(created_skill.id)
    assert skill_package.exists()
    assert (skill_package / "SKILL.md").exists()

    created_rule = rule_store.get(result["created_rules"][-1]["id"])
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


def test_build_skill_record_from_package_dir_reads_proxy_entries(tmp_path):
    import json

    from services import skill_import_service as import_svc

    package_dir = tmp_path / "skill-packages" / "proxy-skill"
    (package_dir / "scripts").mkdir(parents=True)
    (package_dir / "scripts" / "validate.py").write_text("print('ok')\n", encoding="utf-8")
    (package_dir / "manifest.json").write_text(
        json.dumps(
            {
                "name": "Proxy Skill",
                "description": "skill with explicit proxy entries",
                "proxy_entries": [
                    {
                        "name": "validate",
                        "path": "scripts/validate.py",
                        "runtime": "python",
                        "description": "Validate current project",
                        "args_schema": {
                            "type": "object",
                            "properties": {"target": {"type": "string"}},
                        },
                        "employee_id_flag": "",
                        "api_key_flag": "--token",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    skill = import_svc.build_skill_record_from_package_dir(package_dir, created_by="tester")

    assert len(skill.proxy_entries) == 1
    assert skill.proxy_entries[0].name == "validate"
    assert skill.proxy_entries[0].path == "scripts/validate.py"
    assert skill.proxy_entries[0].runtime == "python"
    assert skill.proxy_entries[0].employee_id_flag == ""
    assert skill.proxy_entries[0].api_key_flag == "--token"
    assert len(skill.tools) == 1
    assert skill.tools[0].name == "validate"
    assert skill.tools[0].parameters["type"] == "object"


def test_build_skill_record_from_package_dir_infers_proxy_entries_when_missing_declaration(tmp_path):
    from services import skill_import_service as import_svc

    package_dir = tmp_path / "skill-packages" / "auto-proxy-skill"
    (package_dir / "scripts").mkdir(parents=True)
    (package_dir / "scripts" / "run.py").write_text("print('ok')\n", encoding="utf-8")
    (package_dir / "SKILL.md").write_text(
        "---\nname: auto-proxy-skill\ndescription: inferred proxy entries\n---\n",
        encoding="utf-8",
    )

    skill = import_svc.build_skill_record_from_package_dir(package_dir, created_by="tester")

    assert len(skill.proxy_entries) == 1
    assert skill.proxy_entries[0].name == "run"
    assert skill.proxy_entries[0].path == "scripts/run.py"
    assert skill.proxy_entries[0].runtime == "python"
    assert skill.proxy_entries[0].source == "inferred"


def test_discover_skill_proxy_specs_prefers_manifest_proxy_entries(tmp_path):
    from services import dynamic_mcp_skill_proxies as proxy_svc
    from stores import mcp_bridge

    package_dir = tmp_path / "skill-packages" / "proxy-skill"
    (package_dir / "scripts").mkdir(parents=True)
    (package_dir / "tools").mkdir(parents=True)
    (package_dir / "scripts" / "validate.py").write_text("print('validate')\n", encoding="utf-8")
    (package_dir / "tools" / "legacy.py").write_text("print('legacy')\n", encoding="utf-8")

    skill = mcp_bridge.Skill(
        id="proxy-skill",
        version="1.0.0",
        name="Proxy Skill",
        description="",
        mcp_service="",
        created_by="tester",
        package_dir=str(package_dir),
        proxy_entries=(
            mcp_bridge.ProxyEntryDef(
                name="validate",
                path="scripts/validate.py",
                runtime="python",
                description="Validate current project",
                source="declared",
                args_schema={
                    "type": "object",
                    "properties": {"target": {"type": "string"}},
                },
            ),
        ),
    )

    specs = proxy_svc.discover_skill_proxy_specs(skill)

    assert len(specs) == 1
    assert specs[0]["entry_name"] == "validate"
    assert specs[0]["runtime"] == "python"
    assert specs[0]["script_type"] == "py"
    assert specs[0]["parameters_schema"]["type"] == "object"
    assert "legacy" not in {item["entry_name"] for item in specs}


def test_execute_skill_proxy_supports_command_entries_and_custom_flags(tmp_path):
    import json
    import sys

    from services import dynamic_mcp_skill_executor as executor_svc

    script_path = tmp_path / "runner.py"
    script_path.write_text(
        "\n".join(
            [
                "import argparse",
                "import json",
                "import os",
                "",
                "parser = argparse.ArgumentParser()",
                "parser.add_argument('--message')",
                "parser.add_argument('--worker')",
                "args = parser.parse_args()",
                "print(json.dumps({'message': args.message, 'worker': args.worker, 'cwd': os.getcwd()}))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = executor_svc.execute_skill_proxy(
        {
            "script_path": str(script_path),
            "runtime": "command",
            "command": [sys.executable],
            "employee_id_flag": "--worker",
            "api_key_flag": "",
            "cwd": str(tmp_path),
        },
        project_root=tmp_path / "workspace",
        args={"message": "hello"},
        employee_id="emp-42",
    )

    payload = json.loads(result["stdout"])

    assert result["status"] == "ok"
    assert result["command"][0] == sys.executable
    assert payload["message"] == "hello"
    assert payload["worker"] == "emp-42"
    assert payload["cwd"] == str(tmp_path.resolve())


@pytest.mark.asyncio
async def test_skill_list_payload_includes_proxy_status(tmp_path, monkeypatch):
    from routers import skills as skills_router
    from stores import mcp_bridge

    package_dir = tmp_path / "skill-packages" / "auto-proxy-skill"
    (package_dir / "scripts").mkdir(parents=True)
    (package_dir / "scripts" / "run.py").write_text("print('ok')\n", encoding="utf-8")
    (package_dir / "SKILL.md").write_text(
        "---\nname: auto-proxy-skill\ndescription: inferred proxy entries\n---\n",
        encoding="utf-8",
    )

    skill = mcp_bridge.Skill(
        id="auto-proxy-skill",
        version="1.0.0",
        name="Auto Proxy Skill",
        description="",
        mcp_service="",
        created_by="tester",
        package_dir=str(package_dir),
    )

    class StubSkillStore:
        def list_all(self):
            return [skill]

        def get(self, skill_id):
            return skill if skill_id == "auto-proxy-skill" else None

    monkeypatch.setattr(skills_router, "skill_store", StubSkillStore())
    monkeypatch.setattr(skills_router, "_ensure_historical_skills_registered", lambda: None)

    payload = await skills_router.list_skills({"sub": "tester"})

    assert len(payload["skills"]) == 1
    item = payload["skills"][0]
    assert item["proxy_status"]["declaration_status"] == "auto_inferred"
    assert item["proxy_status"]["effective_count"] == 1
    assert item["proxy_entries"][0]["name"] == "run"
    assert item["proxy_entries"][0]["source"] == "inferred"
    assert item["proxy_status"]["diagnostics"]["candidate_files"] == ["scripts/run.py"]


@pytest.mark.asyncio
async def test_refresh_skill_proxy_entries_persists_inferred_entries(tmp_path, monkeypatch):
    from routers import skills as skills_router
    from stores import mcp_bridge

    package_dir = tmp_path / "skill-packages" / "auto-proxy-skill"
    (package_dir / "scripts").mkdir(parents=True)
    (package_dir / "scripts" / "run.py").write_text("print('ok')\n", encoding="utf-8")
    (package_dir / "SKILL.md").write_text(
        "---\nname: auto-proxy-skill\ndescription: inferred proxy entries\n---\n",
        encoding="utf-8",
    )

    stored_skill = mcp_bridge.Skill(
        id="auto-proxy-skill",
        version="1.0.0",
        name="Auto Proxy Skill",
        description="",
        mcp_service="",
        created_by="tester",
        package_dir=str(package_dir),
        proxy_entries=(),
    )
    saved: dict[str, object] = {}

    class StubSkillStore:
        def get(self, skill_id):
            return stored_skill if skill_id == "auto-proxy-skill" else None

        def save(self, skill):
            saved["skill"] = skill

    monkeypatch.setattr(skills_router, "skill_store", StubSkillStore())
    monkeypatch.setattr(skills_router, "_ensure_historical_skills_registered", lambda: None)
    monkeypatch.setattr(skills_router, "assert_can_manage_record", lambda *args, **kwargs: None)

    payload = await skills_router.refresh_skill_proxy_entries("auto-proxy-skill", {"sub": "tester"})

    assert payload["status"] == "updated"
    assert payload["skill"]["proxy_status"]["declaration_status"] == "auto_inferred"
    assert payload["skill"]["proxy_entries"][0]["name"] == "run"
    assert saved["skill"].proxy_entries[0].source == "inferred"


@pytest.mark.asyncio
async def test_install_skill_syncs_employee_skills_and_defaults_enabled_tools(tmp_path, monkeypatch):
    from routers import skills as skills_router
    from stores import mcp_bridge
    from stores.json.employee_store import EmployeeConfig, EmployeeStore

    employee_store = EmployeeStore(tmp_path)
    employee_store.save(EmployeeConfig(id="emp-1", name="员工一", skills=[]))

    skill = mcp_bridge.Skill(
        id="skill-1",
        version="1.0.0",
        name="Skill One",
        description="",
        mcp_service="",
        tools=(
            mcp_bridge.ToolDef(name="lookup", description=""),
            mcp_bridge.ToolDef(name="analyze", description=""),
        ),
    )

    class StubSkillStore:
        def get(self, skill_id):
            return skill if skill_id == "skill-1" else None

    class StubBindingStore:
        def __init__(self):
            self.saved = []

        def add(self, binding):
            self.saved = [item for item in self.saved if item.skill_id != binding.skill_id]
            self.saved.append(binding)

        def get_bindings(self, employee_id):
            return [item for item in self.saved if item.employee_id == employee_id]

    binding_store = StubBindingStore()

    monkeypatch.setattr(skills_router, "employee_store", employee_store)
    monkeypatch.setattr(skills_router, "skill_store", StubSkillStore())
    monkeypatch.setattr(skills_router, "binding_store", binding_store)

    payload = await skills_router.install_skill(
        "emp-1",
        skills_router.SkillInstallReq(skill_id="skill-1", enabled_tools=[]),
    )

    employee = employee_store.get("emp-1")
    assert payload["status"] == "installed"
    assert payload["enabled_tools"] == ["lookup", "analyze"]
    assert employee is not None
    assert employee.skills == ["skill-1"]
    assert binding_store.get_bindings("emp-1")[0].enabled_tools == ("lookup", "analyze")


@pytest.mark.asyncio
async def test_employee_skills_merges_employee_profile_and_bindings(tmp_path, monkeypatch):
    from routers import skills as skills_router
    from stores import mcp_bridge
    from stores.json.employee_store import EmployeeConfig, EmployeeStore

    employee_store = EmployeeStore(tmp_path)
    employee_store.save(EmployeeConfig(id="emp-1", name="员工一", skills=["skill-profile", "skill-binding"]))

    class StubSkillStore:
        def get(self, skill_id):
            return mcp_bridge.Skill(
                id=skill_id,
                version="1.0.0",
                name=f"Name {skill_id}",
                description="",
                mcp_service="",
                tools=(mcp_bridge.ToolDef(name="run", description=""),) if skill_id == "skill-profile" else (),
            )

    class StubBindingStore:
        def get_bindings(self, employee_id):
            return [
                mcp_bridge.EmployeeSkillBinding(
                    employee_id=employee_id,
                    skill_id="skill-binding",
                    enabled_tools=("proxy",),
                )
            ]

    monkeypatch.setattr(skills_router, "employee_store", employee_store)
    monkeypatch.setattr(skills_router, "skill_store", StubSkillStore())
    monkeypatch.setattr(skills_router, "binding_store", StubBindingStore())

    payload = await skills_router.employee_skills("emp-1")

    assert payload["bindings"] == [
        {
            "skill_id": "skill-profile",
            "skill_name": "Name skill-profile",
            "enabled_tools": ["run"],
            "installed_at": "",
            "source": "employee_profile",
        },
        {
            "skill_id": "skill-binding",
            "skill_name": "Name skill-binding",
            "enabled_tools": ["proxy"],
            "installed_at": payload["bindings"][1]["installed_at"],
            "source": "binding",
        },
    ]
    assert payload["bindings"][1]["installed_at"]


@pytest.mark.asyncio
async def test_uninstall_skill_removes_binding_and_employee_skill(tmp_path, monkeypatch):
    from routers import skills as skills_router
    from stores.json.employee_store import EmployeeConfig, EmployeeStore

    employee_store = EmployeeStore(tmp_path)
    employee_store.save(EmployeeConfig(id="emp-1", name="员工一", skills=["skill-1"]))

    class StubBindingStore:
        def __init__(self):
            self.skill_ids = {"skill-1"}

        def remove(self, employee_id, skill_id):
            if skill_id not in self.skill_ids:
                return False
            self.skill_ids.remove(skill_id)
            return True

    monkeypatch.setattr(skills_router, "employee_store", employee_store)
    monkeypatch.setattr(skills_router, "binding_store", StubBindingStore())

    payload = await skills_router.uninstall_skill("emp-1", "skill-1")

    employee = employee_store.get("emp-1")
    assert payload["status"] == "uninstalled"
    assert payload["removed_binding"] is True
    assert payload["removed_employee_skill"] is True
    assert employee is not None
    assert employee.skills == []


def test_normalize_project_chat_settings_supports_employee_coordination_mode():
    from routers.projects import _normalize_project_chat_settings

    default_settings = _normalize_project_chat_settings({})
    manual_settings = _normalize_project_chat_settings(
        {"employee_coordination_mode": "manual"}
    )
    invalid_settings = _normalize_project_chat_settings(
        {"employee_coordination_mode": "planner-workers"}
    )

    assert default_settings["employee_coordination_mode"] == "auto"
    assert manual_settings["employee_coordination_mode"] == "manual"
    assert invalid_settings["employee_coordination_mode"] == "auto"


def test_build_project_chat_messages_includes_multi_employee_coordination_prompt():
    from routers.projects import _build_project_chat_messages
    from stores.json.project_store import ProjectConfig

    project = ProjectConfig(id="proj-1", name="项目一", description="测试项目")
    selected_employees = [
        {
            "id": "emp-1",
            "name": "产品经理",
            "goal": "负责需求拆解",
            "skill_names": ["prd", "planning"],
            "rule_bindings": [{"id": "rule-1", "title": "需求追踪", "domain": "product"}],
            "default_workflow": ["澄清需求", "拆解任务"],
            "tool_usage_policy": "先检索规则，再调用技能",
        },
        {
            "id": "emp-2",
            "name": "前端开发",
            "goal": "负责页面实现",
            "skill_names": ["vue", "ui"],
            "rule_bindings": [{"id": "rule-2", "title": "UI 规范", "domain": "ui"}],
            "default_workflow": ["分析现状", "编码实现"],
        },
    ]
    tools = [
        {"tool_name": "emp_1__prd__draft", "employee_id": "emp-1"},
        {"tool_name": "emp_2__vue__page", "employee_id": "emp-2"},
        {"tool_name": "query_project_rules", "employee_id": ""},
    ]

    messages = _build_project_chat_messages(
        project,
        "请协作完成一个新页面",
        [],
        selected_employees=selected_employees,
        tools=tools,
        employee_coordination_mode="auto",
    )
    system_prompt = str(messages[0]["content"])

    assert "多员工自动协作" in system_prompt
    assert "产品经理 (emp-1)" in system_prompt
    assert "前端开发 (emp-2)" in system_prompt
    assert "emp_1__prd__draft" in system_prompt
    assert "emp_2__vue__page" in system_prompt
    assert "共享/全局工具" in system_prompt
    assert "项目手册、员工手册、规则和工具" in system_prompt
    assert "不要预设固定行业分工模板" in system_prompt

    manual_messages = _build_project_chat_messages(
        project,
        "请协作完成一个新页面",
        [],
        selected_employees=selected_employees,
        tools=tools,
        employee_coordination_mode="manual",
    )
    assert "多员工自动协作" not in str(manual_messages[0]["content"])


def test_build_project_chat_messages_prefers_project_ui_rules(monkeypatch):
    from routers import projects as projects_router
    from stores.json.project_store import ProjectConfig

    class DummyRule:
        def __init__(self, rule_id: str, title: str, domain: str, content: str) -> None:
            self.id = rule_id
            self.title = title
            self.domain = domain
            self.content = content

    class DummyRuleStore:
        @staticmethod
        def get(rule_id):
            if rule_id == "rule-ui":
                return DummyRule(
                    "rule-ui",
                    "项目 UI 规则",
                    "ui",
                    "按钮采用圆角 12px，主按钮使用品牌色，列表卡片保持 16px 留白。",
                )
            return None

    monkeypatch.setattr(projects_router, "rule_store", DummyRuleStore())

    project = ProjectConfig(
        id="proj-1",
        name="项目一",
        description="测试项目",
        ui_rule_ids=["rule-ui"],
    )
    selected_employee = {
        "id": "emp-1",
        "name": "前端开发",
        "goal": "负责页面实现",
        "skill_names": ["vue", "ui"],
        "rule_bindings": [{"id": "rule-emp", "title": "员工规则", "domain": "frontend"}],
        "default_workflow": ["分析现状", "编码实现"],
    }

    messages = projects_router._build_project_chat_messages(
        project,
        "请实现一个项目首页",
        [],
        selected_employee=selected_employee,
    )
    system_prompt = str(messages[0]["content"])

    assert "当前项目已绑定 UI 规则" in system_prompt
    assert "优先级高于员工个人规则" in system_prompt
    assert "按钮采用圆角 12px" in system_prompt
    assert "当前执行员工" in system_prompt
    assert "优先使用当前项目已绑定的员工、规则和技能" in system_prompt
    assert "重新获取与当前问题直接相关的规则正文" in system_prompt
    assert system_prompt.index("当前项目已绑定 UI 规则") < system_prompt.index("当前执行员工")


def test_build_project_manual_template_payload_prefers_ai_decided_collaboration(monkeypatch):
    from routers import employees as employees_router
    from routers import projects as projects_router

    class DummyProject:
        id = "proj-1"
        name = "项目一"
        description = "测试项目"
        type = "mixed"
        feedback_upgrade_enabled = True
        ui_rule_ids = ["rule-ui"]

    class DummyEmployee:
        id = "emp-1"
        name = "通用员工"

    class DummyMember:
        role = "member"

    class DummyRule:
        id = "rule-ui"
        title = "项目 UI 规则"
        domain = "ui"
        content = "按钮统一圆角 12px。"

    monkeypatch.setattr(
        projects_router,
        "project_store",
        type("DummyProjectStore", (), {"get": staticmethod(lambda project_id: DummyProject() if project_id == "proj-1" else None)})(),
    )
    monkeypatch.setattr(
        projects_router,
        "_project_member_details",
        lambda project_id: [
            {
                "employee": DummyEmployee(),
                "member": DummyMember(),
                "skills": [],
                "rule_bindings": [],
            }
        ] if project_id == "proj-1" else [],
    )
    monkeypatch.setattr(
        employees_router,
        "_build_employee_manual_payload",
        lambda employee_id: {"manual": f"# {employee_id} 手册\n\n- 默认按规则与工具自主判断是否协作"},
    )
    monkeypatch.setattr(
        projects_router,
        "rule_store",
        type("DummyRuleStore", (), {"get": staticmethod(lambda rule_id: DummyRule() if rule_id == "rule-ui" else None)})(),
    )

    payload = projects_router._build_project_manual_template_payload("proj-1")
    manual = str(payload["manual"])

    assert "自主判断单人主责还是多人协作" in manual
    assert "execute_project_collaboration" in manual
    assert "不要默认多员工并行" in manual
    assert "项目级 UI 规则" in manual
    assert "高于员工个人规则" in manual
    assert "按钮统一圆角 12px" in manual
    assert "优先依赖项目绑定的员工、规则和技能" in manual
    assert "每次新请求都要重新调用 `query_project_rules`" in manual
    assert "只有项目绑定员工、规则、技能都无法覆盖时，才由 AI 自行补足" in manual


def test_can_view_record_supports_private_selected_and_all_users():
    from core.ownership import can_manage_record, can_view_record
    from stores.json.employee_store import EmployeeConfig

    private_employee = EmployeeConfig(id="emp-private", name="私有员工", created_by="alice")
    selected_employee = EmployeeConfig(
        id="emp-selected",
        name="定向共享员工",
        created_by="alice",
        share_scope="selected_users",
        shared_with_usernames=["bob"],
    )
    all_users_employee = EmployeeConfig(
        id="emp-all",
        name="全员共享员工",
        created_by="alice",
        share_scope="all_users",
    )

    assert can_view_record(private_employee, {"sub": "alice", "role": "user"}) is True
    assert can_view_record(private_employee, {"sub": "bob", "role": "user"}) is False
    assert can_view_record(selected_employee, {"sub": "bob", "role": "user"}) is True
    assert can_view_record(selected_employee, {"sub": "charlie", "role": "user"}) is False
    assert can_view_record(all_users_employee, {"sub": "charlie", "role": "user"}) is True
    assert can_view_record(private_employee, {"sub": "root", "role": "admin"}) is True
    assert can_manage_record(private_employee, {"sub": "root", "role": "admin"}) is True


@pytest.mark.asyncio
async def test_list_employees_filters_private_records(tmp_path, monkeypatch):
    from routers import employees as employees_router
    from stores.json.employee_store import EmployeeConfig, EmployeeStore

    store = EmployeeStore(tmp_path / "data")
    store.save(EmployeeConfig(id="emp-1", name="Alice 私有", created_by="alice"))
    store.save(
        EmployeeConfig(
            id="emp-2",
            name="Alice 定向共享",
            created_by="alice",
            share_scope="selected_users",
            shared_with_usernames=["bob"],
        )
    )
    store.save(
        EmployeeConfig(
            id="emp-3",
            name="Alice 全员共享",
            created_by="alice",
            share_scope="all_users",
        )
    )

    monkeypatch.setattr(employees_router, "employee_store", store)

    result = await employees_router.list_employees({"sub": "bob", "role": "user"})
    employee_ids = {item["id"] for item in result["employees"]}

    assert employee_ids == {"emp-2", "emp-3"}


@pytest.mark.asyncio
async def test_list_rules_includes_private_rule_shared_via_employee(tmp_path, monkeypatch):
    from routers import rules as rules_router
    from stores import mcp_bridge
    from stores.json.employee_store import EmployeeConfig, EmployeeStore

    employee_store = EmployeeStore(tmp_path / "data")
    rule_store = mcp_bridge._rules_mod.RuleStore(tmp_path / "rules-runtime")

    employee_store.save(
        EmployeeConfig(
            id="emp-1",
            name="共享员工",
            created_by="alice",
            share_scope="selected_users",
            shared_with_usernames=["bob"],
            rule_ids=["rule-1"],
        )
    )
    employee_store.save(EmployeeConfig(id="emp-2", name="未共享员工", created_by="alice", rule_ids=["rule-2"]))
    rule_store.save(
        mcp_bridge._rules_mod.Rule(
            id="rule-1",
            domain="security",
            title="可通过员工继承的私有规则",
            content="demo",
            created_by="alice",
        )
    )
    rule_store.save(
        mcp_bridge._rules_mod.Rule(
            id="rule-2",
            domain="security",
            title="完全私有规则",
            content="hidden",
            created_by="alice",
        )
    )

    monkeypatch.setattr(rules_router, "employee_store", employee_store)
    monkeypatch.setattr(rules_router, "rule_store", rule_store)

    result = await rules_router.list_rules({"sub": "bob", "role": "user"})
    rule_ids = {item["id"] for item in result["rules"]}

    assert rule_ids == {"rule-1"}
    assert result["rules"][0]["shared_via_employees"][0]["id"] == "emp-1"


@pytest.mark.asyncio
async def test_list_skills_includes_private_skill_shared_via_employee(tmp_path, monkeypatch):
    from routers import skills as skills_router
    from stores import mcp_bridge
    from stores.json.employee_store import EmployeeConfig, EmployeeStore

    employee_store = EmployeeStore(tmp_path / "data")
    skill_store = mcp_bridge._skills_mod.SkillStore(tmp_path / "skills-runtime")
    binding_store = mcp_bridge._skills_mod.BindingStore(tmp_path / "skills-runtime")

    employee_store.save(
        EmployeeConfig(
            id="emp-1",
            name="共享员工",
            created_by="alice",
            share_scope="selected_users",
            shared_with_usernames=["bob"],
            skills=["skill-1"],
        )
    )
    employee_store.save(EmployeeConfig(id="emp-2", name="未共享员工", created_by="alice", skills=["skill-2"]))
    skill_store.save(
        mcp_bridge._skills_mod.Skill(
            id="skill-1",
            version="1.0.0",
            name="共享链路技能",
            description="demo",
            mcp_service="",
            created_by="alice",
        )
    )
    skill_store.save(
        mcp_bridge._skills_mod.Skill(
            id="skill-2",
            version="1.0.0",
            name="完全私有技能",
            description="hidden",
            mcp_service="",
            created_by="alice",
        )
    )

    monkeypatch.setattr(skills_router, "employee_store", employee_store)
    monkeypatch.setattr(skills_router, "skill_store", skill_store)
    monkeypatch.setattr(skills_router, "binding_store", binding_store)
    monkeypatch.setattr(skills_router, "_ensure_historical_skills_registered", lambda: None)

    result = await skills_router.list_skills({"sub": "bob", "role": "user"})
    skill_ids = {item["id"] for item in result["skills"]}

    assert skill_ids == {"skill-1"}
    assert result["skills"][0]["shared_via_employees"][0]["id"] == "emp-1"


def _build_user_account_test_client(tmp_path, monkeypatch, auth_payload):
    from core import config as core_config
    from core.deps import require_auth
    from core.server import create_app
    from stores import factory as store_factory
    from stores.json.user_store import User, hash_password

    monkeypatch.setenv("CORE_STORE_BACKEND", "json")
    monkeypatch.setenv("API_DATA_DIR", str(tmp_path / "api-data"))
    core_config.get_settings.cache_clear()
    core_config._file_env_values.cache_clear()
    for proxy_name in ("user_store", "role_store"):
        getattr(store_factory, proxy_name)._instance = None

    store_factory.user_store.save(User(username="alice", password_hash=hash_password("alice-old"), role="user"))
    store_factory.user_store.save(User(username="bob", password_hash=hash_password("bob-old"), role="user"))
    store_factory.user_store.save(User(username="admin", password_hash=hash_password("admin-old"), role="admin"))

    app = create_app()
    app.dependency_overrides[require_auth] = lambda: auth_payload
    return TestClient(app), store_factory.user_store


def test_user_can_update_own_account_without_user_update_permission(tmp_path, monkeypatch):
    from stores.json.user_store import verify_password

    client, user_store = _build_user_account_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "alice", "role": "user"},
    )

    response = client.put(
        "/api/users/alice",
        json={"role": "user", "password": "alice-new-password"},
    )

    assert response.status_code == 200
    updated = user_store.get("alice")
    assert updated is not None
    assert updated.role == "user"
    assert verify_password("alice-new-password", updated.password_hash)


def test_user_cannot_update_other_account_without_user_update_permission(tmp_path, monkeypatch):
    client, _user_store = _build_user_account_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "alice", "role": "user"},
    )

    response = client.put(
        "/api/users/bob",
        json={"role": "user", "password": "bob-new-password"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Permission denied: button.users.update"


def test_admin_can_update_other_account(tmp_path, monkeypatch):
    from stores.json.user_store import verify_password

    client, user_store = _build_user_account_test_client(
        tmp_path,
        monkeypatch,
        {"sub": "admin", "role": "admin"},
    )

    response = client.put(
        "/api/users/bob",
        json={"role": "user", "password": "bob-new-password"},
    )

    assert response.status_code == 200
    updated = user_store.get("bob")
    assert updated is not None
    assert verify_password("bob-new-password", updated.password_hash)


if __name__ == "__main__":
    asyncio.run(test_orchestrator_logic())
    asyncio.run(test_tool_executor_logic())
    asyncio.run(test_conversation_manager_logic())
    print("\n✅ 所有单元测试通过")
