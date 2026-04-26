"""Public bot platform event callbacks."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse

from services.feishu_bot_service import (
    build_feishu_event_handler,
    get_feishu_message_resource_file,
    get_feishu_connector,
    get_feishu_sdk_error_message,
    is_feishu_sdk_available,
)


public_router = APIRouter(prefix="/api/bot-events")
router = APIRouter(prefix="/api/bot-events-internal", include_in_schema=False)


@public_router.post("/feishu/{connector_id}/event")
async def feishu_event_callback(connector_id: str, request: Request):
    connector = get_feishu_connector(connector_id)
    if connector is None or not bool(connector.get("enabled", True)):
        raise HTTPException(404, "Feishu connector not found or disabled")
    if not is_feishu_sdk_available():
        raise HTTPException(503, get_feishu_sdk_error_message())

    from lark_oapi.core.model import RawRequest

    raw_req = RawRequest()
    raw_req.uri = str(request.url.path)
    raw_req.headers = dict(request.headers)
    for key, value in request.headers.items():
        normalized_key = "-".join(part.capitalize() for part in str(key).split("-"))
        raw_req.headers[normalized_key] = value
    raw_req.body = await request.body()

    handler = build_feishu_event_handler(connector, loop=asyncio.get_running_loop())
    raw_resp = handler.do(raw_req)
    return Response(
        content=raw_resp.content or b"",
        status_code=int(raw_resp.status_code or 200),
        media_type=str((raw_resp.headers or {}).get("Content-Type") or "application/json"),
    )


@public_router.get("/feishu/{connector_id}/resources/{message_id}/{filename}")
async def get_feishu_message_resource(connector_id: str, message_id: str, filename: str):
    try:
        file_path, mime_type = get_feishu_message_resource_file(connector_id, message_id, filename)
    except FileNotFoundError as exc:
        raise HTTPException(404, "Feishu message resource not found") from exc
    return FileResponse(
        file_path,
        media_type=mime_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )
