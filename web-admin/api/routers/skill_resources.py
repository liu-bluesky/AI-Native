"""External skill resource routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from core.deps import ensure_permission, require_auth
from models.requests import SkillResourceInstallReq, SkillResourceResolveReq
from services.skill_resource_service import SkillResourceService

def _require_skill_resource_permission(auth_payload: dict = Depends(require_auth)) -> None:
    ensure_permission(auth_payload, "menu.skills")


router = APIRouter(
    prefix="/api/skill-resources",
    dependencies=[Depends(require_auth), Depends(_require_skill_resource_permission)],
)
service = SkillResourceService()


@router.get("")
async def list_skill_resources(
    source: str = Query("vett"),
    q: str = Query(""),
    risk: str = Query(""),
    sort_by: str = Query("installs"),
    limit: int = Query(20, ge=1, le=250),
    offset: int = Query(0, ge=0),
):
    return await service.search(
        source=source,
        q=q,
        risk=risk,
        sort_by=sort_by,
        limit=limit,
        offset=offset,
    )


@router.post("/{source}/resolve")
async def resolve_skill_resource(source: str, req: SkillResourceResolveReq):
    return await service.resolve(source=source, input_value=req.input)


@router.get("/{source}/jobs/{job_id}")
async def get_skill_resource_job(source: str, job_id: str):
    return await service.get_job(source=source, job_id=job_id)


@router.post("/{source}/{slug:path}/install")
async def install_skill_resource(
    source: str,
    slug: str,
    req: SkillResourceInstallReq,
    auth_payload: dict = Depends(require_auth),
):
    return await service.install(
        source=source,
        slug=slug,
        version=req.version,
        install_dir=req.install_dir,
        import_to_library=req.import_to_library,
        auth_payload=auth_payload,
    )


@router.get("/{source}/{slug:path}")
async def get_skill_resource_detail(source: str, slug: str):
    return await service.get_detail(source=source, slug=slug)
