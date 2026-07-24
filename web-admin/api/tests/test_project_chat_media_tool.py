from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.deps import require_auth
from models.requests import ProjectChatMediaToolReq
from routers import projects
from services.providers import llm_provider_service


class _FakeMediaService:
    def __init__(self) -> None:
        self.image_urls: list[str] = []
        self.operation = ""

    def get_provider_raw(self, *_args, **_kwargs):
        return {"id": "provider-image", "enabled": True, "base_url": "https://example.test/v1"}

    def get_model_config(self, _provider, _model_name):
        return {"model_type": "image_generation"}

    async def generate_media_artifacts(self, _provider_id, _model_name, _prompt, **kwargs):
        self.operation = "generate"
        self.image_urls = list(kwargs.get("image_urls") or [])
        return [
            {
                "asset_type": "image",
                "title": "generated",
                "preview_url": "https://example.test/generated.png",
                "content_url": "https://example.test/generated.png",
                "mime_type": "image/png",
            }
        ]

    async def edit_image_artifacts(self, _provider_id, _model_name, _prompt, **kwargs):
        self.operation = "edit"
        self.image_urls = list(kwargs.get("image_references") or [])
        return [
            {
                "asset_type": "image",
                "title": "edited",
                "preview_url": "https://example.test/edited.png",
                "content_url": "https://example.test/edited.png",
                "mime_type": "image/png",
            }
        ]


@pytest.mark.asyncio
async def test_generate_image_uses_generation_operation(monkeypatch):
    service = _FakeMediaService()
    monkeypatch.setattr(llm_provider_service, "get_llm_provider_service", lambda: service)

    result = await projects._execute_project_chat_media_tool(
        req=ProjectChatMediaToolReq(
            tool_name="generate_image",
            provider_id="provider-image",
            model_name="image-model",
            prompt="生成一个金色葫芦",
        ),
        auth_payload={"username": "admin", "is_admin": True},
        username="admin",
    )

    assert service.operation == "generate"
    assert service.image_urls == []
    assert result["images"] == ["https://example.test/generated.png"]
    assert result["tool_name"] == "generate_image"


@pytest.mark.asyncio
async def test_edit_image_passes_selected_images_to_provider(monkeypatch):
    service = _FakeMediaService()
    monkeypatch.setattr(llm_provider_service, "get_llm_provider_service", lambda: service)

    result = await projects._execute_project_chat_media_tool(
        req=ProjectChatMediaToolReq(
            tool_name="edit_image",
            provider_id="provider-image",
            model_name="image-model",
            prompt="把葫芦身体改成绿色",
            reference_images=["https://example.test/gourd.png"],
        ),
        auth_payload={"username": "admin", "is_admin": True},
        username="admin",
    )

    assert service.image_urls == ["https://example.test/gourd.png"]
    assert service.operation == "edit"
    assert result["tool_name"] == "edit_image"
    assert result["images"] == ["https://example.test/edited.png"]


@pytest.mark.asyncio
async def test_generate_image_rejects_input_images(monkeypatch):
    service = _FakeMediaService()
    monkeypatch.setattr(llm_provider_service, "get_llm_provider_service", lambda: service)

    with pytest.raises(projects.HTTPException) as exc_info:
        await projects._execute_project_chat_media_tool(
            req=ProjectChatMediaToolReq(
                tool_name="generate_image",
                provider_id="provider-image",
                model_name="image-model",
                prompt="参考原图生成海报",
                reference_images=["data:image/png;base64,AAAA"],
            ),
            auth_payload={"username": "admin", "is_admin": True},
            username="admin",
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "generate_image does not accept input images; use edit_image instead"
    assert service.operation == ""


@pytest.mark.asyncio
async def test_edit_image_requires_an_input_image(monkeypatch):
    service = _FakeMediaService()
    monkeypatch.setattr(llm_provider_service, "get_llm_provider_service", lambda: service)

    with pytest.raises(projects.HTTPException) as exc_info:
        await projects._execute_project_chat_media_tool(
            req=ProjectChatMediaToolReq(
                tool_name="edit_image",
                provider_id="provider-image",
                model_name="image-model",
                prompt="把葫芦身体改成绿色",
            ),
            auth_payload={"username": "admin", "is_admin": True},
            username="admin",
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "edit_image requires at least one input image"


def test_media_tool_http_route_executes_generate_image(monkeypatch):
    service = _FakeMediaService()
    monkeypatch.setattr(llm_provider_service, "get_llm_provider_service", lambda: service)
    monkeypatch.setattr(projects, "_ensure_permission", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(projects, "_ensure_project_access", lambda *_args, **_kwargs: None)

    app = FastAPI()
    app.include_router(projects.router)
    app.dependency_overrides[require_auth] = lambda: {
        "sub": "admin",
        "username": "admin",
        "role": "admin",
        "roles": ["admin"],
        "is_admin": True,
    }

    response = TestClient(app).post(
        "/api/projects/proj-media/chat/media-tool",
        json={
            "tool_name": "generate_image",
            "provider_id": "provider-image",
            "model_name": "image-model",
            "prompt": "生成一个金色葫芦",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["tool_name"] == "generate_image"
    assert payload["images"] == ["https://example.test/generated.png"]
    assert service.operation == "generate"
    assert service.image_urls == []


def test_media_tool_http_route_executes_edit_image(monkeypatch):
    service = _FakeMediaService()
    monkeypatch.setattr(llm_provider_service, "get_llm_provider_service", lambda: service)
    monkeypatch.setattr(projects, "_ensure_permission", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(projects, "_ensure_project_access", lambda *_args, **_kwargs: None)

    app = FastAPI()
    app.include_router(projects.router)
    app.dependency_overrides[require_auth] = lambda: {
        "sub": "admin",
        "username": "admin",
        "role": "admin",
        "roles": ["admin"],
        "is_admin": True,
    }

    response = TestClient(app).post(
        "/api/projects/proj-media/chat/media-tool",
        json={
            "tool_name": "edit_image",
            "provider_id": "provider-image",
            "model_name": "image-model",
            "prompt": "把葫芦身体改成绿色",
            "reference_images": ["https://example.test/gourd.png"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["tool_name"] == "edit_image"
    assert payload["images"] == ["https://example.test/edited.png"]
    assert service.operation == "edit"
    assert service.image_urls == ["https://example.test/gourd.png"]
