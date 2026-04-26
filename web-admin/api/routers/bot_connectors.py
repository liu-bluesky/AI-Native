"""Dedicated bot connector routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from core.deps import ensure_permission, require_auth, system_config_store
from models.requests import BotConnectorCollectionReq
from services.bot_connector_service import list_bot_connectors, replace_bot_connectors
from services.bot_connector_installer_service import (
    bot_connector_platform_manifests,
    diagnose_bot_connector,
)


def _require_bot_connector_permission(auth_payload: dict = Depends(require_auth)) -> None:
    ensure_permission(auth_payload, "menu.system.config")


router = APIRouter(
    prefix="/api/bot-connectors",
    dependencies=[Depends(require_auth), Depends(_require_bot_connector_permission)],
)


@router.get("")
async def get_bot_connectors():
    return {"items": list_bot_connectors()}


@router.put("")
async def put_bot_connectors(req: BotConnectorCollectionReq, request: Request):
    items = replace_bot_connectors(req.items)
    supervisor = getattr(request.app.state, "feishu_long_connection_supervisor", None)
    if (
        supervisor is not None
        and bool(getattr(system_config_store.get_global(), "feishu_bot_long_connection_worker_enabled", False))
    ):
        supervisor.restart()
    return {
        "status": "updated",
        "items": items,
        "feishu_long_connection": supervisor.status() if supervisor is not None else {},
    }


@router.get("/platforms")
async def get_bot_connector_platforms():
    return {"items": bot_connector_platform_manifests()}


@router.get("/workers")
async def get_bot_connector_workers(request: Request):
    supervisor = getattr(request.app.state, "feishu_long_connection_supervisor", None)
    return {"feishu_long_connection": supervisor.status() if supervisor is not None else {}}


@router.post("/workers/restart")
async def restart_bot_connector_workers(request: Request):
    supervisor = getattr(request.app.state, "feishu_long_connection_supervisor", None)
    if supervisor is not None:
        supervisor.restart()
    return {"status": "restarted", "feishu_long_connection": supervisor.status() if supervisor is not None else {}}


@router.post("/{connector_id}/diagnose")
async def diagnose_bot_connector_route(connector_id: str, request: Request):
    supervisor = getattr(request.app.state, "feishu_long_connection_supervisor", None)
    workers = supervisor.status() if supervisor is not None else {}
    return diagnose_bot_connector(connector_id, worker_status=workers.get(connector_id))
