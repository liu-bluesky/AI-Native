"""LLM provider management routes."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException

from core.deps import require_auth
from services.llm_provider_service import get_llm_provider_service
from models.requests import LlmProviderCreateReq, LlmProviderTestReq, LlmProviderUpdateReq

router = APIRouter(prefix="/api/llm", dependencies=[Depends(require_auth)])


@router.get("/providers")
async def list_llm_providers(enabled_only: bool = False):
    providers = get_llm_provider_service().list_providers(enabled_only=enabled_only)
    return {"providers": providers}


@router.get("/providers/options")
async def list_reflection_options():
    return get_llm_provider_service().list_reflection_options()


@router.post("/providers")
async def create_llm_provider(req: LlmProviderCreateReq):
    try:
        provider = get_llm_provider_service().create_provider(req.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"status": "created", "provider": provider}


@router.patch("/providers/{provider_id}")
async def update_llm_provider(provider_id: str, req: LlmProviderUpdateReq):
    updates = req.model_dump(exclude_unset=True)
    try:
        provider = get_llm_provider_service().update_provider(provider_id, updates)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"status": "updated", "provider": provider}


@router.delete("/providers/{provider_id}")
async def delete_llm_provider(provider_id: str):
    if not get_llm_provider_service().delete_provider(provider_id):
        raise HTTPException(404, f"LLM provider {provider_id} not found")
    return {"status": "deleted", "provider_id": provider_id}


@router.post("/providers/{provider_id}/test")
async def test_llm_provider(provider_id: str, req: LlmProviderTestReq):
    try:
        result = get_llm_provider_service().test_provider_connection(
            provider_id=provider_id,
            model_name=req.model_name,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        return {
            "status": "failed",
            "result": {
                "provider_id": provider_id,
                "reachable": False,
                "message": str(exc),
                "tested_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
        }
    return {"status": "ok", "result": result}
