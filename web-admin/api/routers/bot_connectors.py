"""Dedicated bot connector routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from core.deps import ensure_permission, require_auth
from models.requests import BotConnectorCollectionReq
from services.connectors.bot_connector_service import list_bot_connectors, replace_bot_connectors, scan_bot_connector_chats
from services.connectors.bot_connector_installer_service import (
    bot_connector_platform_manifests,
    diagnose_bot_connector,
)


def _require_bot_connector_permission(auth_payload: dict = Depends(require_auth)) -> None:
    ensure_permission(auth_payload, "menu.system.config")


router = APIRouter(
    prefix="/api/bot-connectors",
    dependencies=[Depends(require_auth), Depends(_require_bot_connector_permission)],
)


def _disabled_feishu_worker_status() -> dict:
    return {
        "status": "disabled",
        "runtime": "desktop_tauri_sidecar",
        "message": "飞书机器人消息监听和业务执行已迁移到桌面 Tauri，本后端不再启动长连接 worker。",
        "items": {},
    }


def _current_username(auth_payload: dict | None) -> str:
    payload = auth_payload if isinstance(auth_payload, dict) else {}
    return str(payload.get("sub") or payload.get("username") or "").strip()


@router.get("")
async def get_bot_connectors():
    return {"items": list_bot_connectors()}


@router.put("")
async def put_bot_connectors(
    req: BotConnectorCollectionReq,
    request: Request,
    auth_payload: dict = Depends(require_auth),
):
    items = replace_bot_connectors(req.items, owner_username=_current_username(auth_payload))
    return {
        "status": "updated",
        "items": items,
        "feishu_long_connection": _disabled_feishu_worker_status(),
    }


@router.get("/platforms")
async def get_bot_connector_platforms():
    return {"items": bot_connector_platform_manifests()}


@router.get("/workers")
async def get_bot_connector_workers(request: Request):
    return {"feishu_long_connection": _disabled_feishu_worker_status()}


@router.post("/workers/restart")
async def restart_bot_connector_workers(request: Request):
    return {"status": "disabled", "feishu_long_connection": _disabled_feishu_worker_status()}


@router.post("/{connector_id}/diagnose")
async def diagnose_bot_connector_route(connector_id: str, request: Request):
    return diagnose_bot_connector(connector_id, worker_status=None)


@router.post("/{connector_id}/chats/scan")
async def scan_bot_connector_chats_route(connector_id: str):
    return scan_bot_connector_chats(connector_id)
