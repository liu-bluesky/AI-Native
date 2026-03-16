"""LLM provider management routes."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException

from core.deps import ensure_any_permission, ensure_permission, is_admin_like, require_auth
from services.llm_provider_service import get_llm_provider_service
from models.requests import LlmProviderCreateReq, LlmProviderTestReq, LlmProviderUpdateReq

def _require_llm_provider_permission(auth_payload: dict = Depends(require_auth)) -> None:
    ensure_permission(auth_payload, "menu.llm.providers")


def _require_llm_provider_read_permission(auth_payload: dict = Depends(require_auth)) -> None:
    ensure_any_permission(auth_payload, ["menu.llm.providers", "menu.ai.chat"])


router = APIRouter(prefix="/api/llm", dependencies=[Depends(require_auth)])


@router.get("/providers")
async def list_llm_providers(
    enabled_only: bool = False,
    auth_payload: dict = Depends(require_auth),
):
    if enabled_only:
        _require_llm_provider_read_permission(auth_payload)
    else:
        _require_llm_provider_permission(auth_payload)
    providers = get_llm_provider_service().list_providers(
        enabled_only=enabled_only,
        owner_username=str(auth_payload.get("sub") or "").strip(),
        include_all=is_admin_like(auth_payload),
    )
    return {"providers": providers}


@router.get("/providers/options")
async def list_reflection_options(
    auth_payload: dict = Depends(require_auth),
):
    _require_llm_provider_permission(auth_payload)
    return get_llm_provider_service().list_reflection_options(
        owner_username=str(auth_payload.get("sub") or "").strip(),
        include_all=is_admin_like(auth_payload),
    )


@router.post("/providers")
async def create_llm_provider(
    req: LlmProviderCreateReq,
    auth_payload: dict = Depends(require_auth),
):
    _require_llm_provider_permission(auth_payload)
    try:
        provider = get_llm_provider_service().create_provider(
            req.model_dump(),
            owner_username=str(auth_payload.get("sub") or "").strip(),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"status": "created", "provider": provider}


@router.patch("/providers/{provider_id}")
async def update_llm_provider(
    provider_id: str,
    req: LlmProviderUpdateReq,
    auth_payload: dict = Depends(require_auth),
):
    _require_llm_provider_permission(auth_payload)
    updates = req.model_dump(exclude_unset=True)
    try:
        provider = get_llm_provider_service().update_provider(
            provider_id,
            updates,
            owner_username=str(auth_payload.get("sub") or "").strip(),
            include_all=is_admin_like(auth_payload),
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"status": "updated", "provider": provider}


@router.delete("/providers/{provider_id}")
async def delete_llm_provider(
    provider_id: str,
    auth_payload: dict = Depends(require_auth),
):
    _require_llm_provider_permission(auth_payload)
    if not get_llm_provider_service().delete_provider(
        provider_id,
        owner_username=str(auth_payload.get("sub") or "").strip(),
        include_all=is_admin_like(auth_payload),
    ):
        raise HTTPException(404, f"LLM provider {provider_id} not found")
    return {"status": "deleted", "provider_id": provider_id}


@router.post("/providers/{provider_id}/test")
async def test_llm_provider(
    provider_id: str,
    req: LlmProviderTestReq,
    auth_payload: dict = Depends(require_auth),
):
    _require_llm_provider_permission(auth_payload)
    try:
        result = get_llm_provider_service().test_provider_connection(
            provider_id=provider_id,
            model_name=req.model_name,
            owner_username=str(auth_payload.get("sub") or "").strip(),
            include_all=is_admin_like(auth_payload),
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
