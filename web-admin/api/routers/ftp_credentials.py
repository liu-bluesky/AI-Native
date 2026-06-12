"""Global FTP credential routes."""

from __future__ import annotations

import ftplib
import socket
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from core.data_scope import can_manage_username_data, can_view_username_data
from core.deps import ensure_any_permission, ftp_credential_store, require_auth
from core.ownership import current_username
from models.requests import FtpCredentialCreateReq, FtpCredentialTestReq, FtpCredentialUpdateReq
from stores.json.ftp_credential_store import FtpCredential, normalize_ftp_credential_payload


router = APIRouter(prefix="/api/ftp-credentials", dependencies=[Depends(require_auth)])

FTP_CONNECT_TIMEOUT_SECONDS = 8
ftp_client_factory = ftplib.FTP


def _require_ftp_credential_permission(auth_payload: dict) -> None:
    ensure_any_permission(auth_payload, ["menu.projects", "menu.system.config"])


def _serialize_ftp_credential(item: FtpCredential, auth_payload: dict) -> dict[str, Any]:
    data = asdict(item)
    data.pop("password", None)
    data["has_password"] = bool(item.password)
    data["can_manage"] = can_manage_username_data(auth_payload, item.created_by)
    data["is_owner"] = bool(current_username(auth_payload) and current_username(auth_payload) == item.created_by)
    return data


def _ensure_visible(item: FtpCredential | None, auth_payload: dict) -> FtpCredential:
    if item is None or not can_view_username_data(auth_payload, item.created_by):
        raise HTTPException(404, "FTP credential not found")
    return item


def _ensure_manageable(item: FtpCredential, auth_payload: dict) -> None:
    if can_manage_username_data(auth_payload, item.created_by):
        return
    raise HTTPException(403, "FTP 连接不是你创建的，仅可选择使用，不能编辑或删除")


def _validate_ftp_credential(item: FtpCredential) -> None:
    if not item.name:
        raise HTTPException(400, "FTP 连接名称必填")
    if not item.host:
        raise HTTPException(400, "FTP 服务器地址必填")
    if item.port:
        try:
            port_value = int(item.port)
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, "FTP 端口号必须是 1-65535，可不填") from exc
        if port_value < 1 or port_value > 65535:
            raise HTTPException(400, "FTP 端口号必须是 1-65535，可不填")
    if not item.username:
        raise HTTPException(400, "FTP 登录账号必填")
    if not item.password:
        raise HTTPException(400, "FTP 登录密码必填")


def _normalize_ftp_port(value: object) -> int:
    normalized = str(value or "").strip()
    if not normalized:
        return 21
    try:
        port_value = int(normalized)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "FTP 端口号必须是 1-65535，可不填") from exc
    if port_value < 1 or port_value > 65535:
        raise HTTPException(400, "FTP 端口号必须是 1-65535，可不填")
    return port_value


def _build_ftp_test_item(req: FtpCredentialTestReq, auth_payload: dict) -> FtpCredential:
    existing: FtpCredential | None = None
    credential_id = str(req.credential_id or "").strip()
    if credential_id:
        existing = _ensure_visible(ftp_credential_store.get(credential_id), auth_payload)
        _ensure_manageable(existing, auth_payload)
    item = normalize_ftp_credential_payload(req.model_dump(), existing=existing)
    if not item.host:
        raise HTTPException(400, "FTP 服务器地址必填")
    _normalize_ftp_port(item.port)
    if not item.username:
        raise HTTPException(400, "FTP 登录账号必填")
    if not item.password:
        raise HTTPException(400, "FTP 登录密码必填")
    return item


def _test_ftp_connection(item: FtpCredential) -> dict[str, Any]:
    host = str(item.host or "").strip()
    port = _normalize_ftp_port(item.port)
    ftp = ftp_client_factory(timeout=FTP_CONNECT_TIMEOUT_SECONDS)
    try:
        ftp.connect(host=host, port=port, timeout=FTP_CONNECT_TIMEOUT_SECONDS)
        ftp.login(user=item.username, passwd=item.password)
        try:
            welcome = str(ftp.getwelcome() or "").strip()
        except Exception:
            welcome = ""
        return {
            "ok": True,
            "message": f"FTP 连接成功：{host}:{port}",
            "host": host,
            "port": str(port),
            "welcome": welcome[:300],
        }
    except ftplib.error_perm as exc:
        return {
            "ok": False,
            "message": "FTP 账号或密码错误，请检查登录信息",
            "host": host,
            "port": str(port),
            "error": str(exc)[:300],
        }
    except (socket.timeout, TimeoutError) as exc:
        return {
            "ok": False,
            "message": "FTP 连接超时，请检查服务器地址、端口或网络",
            "host": host,
            "port": str(port),
            "error": str(exc)[:300],
        }
    except OSError as exc:
        return {
            "ok": False,
            "message": "FTP 服务器不可达，请检查地址和端口",
            "host": host,
            "port": str(port),
            "error": str(exc)[:300],
        }
    except Exception as exc:
        return {
            "ok": False,
            "message": "FTP 连接测试失败",
            "host": host,
            "port": str(port),
            "error": str(exc)[:300],
        }
    finally:
        try:
            ftp.quit()
        except Exception:
            try:
                ftp.close()
            except Exception:
                pass


@router.get("")
async def list_ftp_credentials(auth_payload: dict = Depends(require_auth)):
    _require_ftp_credential_permission(auth_payload)
    items = [
        item
        for item in ftp_credential_store.list_all()
        if can_view_username_data(auth_payload, item.created_by)
    ]
    return {"items": [_serialize_ftp_credential(item, auth_payload) for item in items]}


@router.post("")
async def create_ftp_credential(req: FtpCredentialCreateReq, auth_payload: dict = Depends(require_auth)):
    _require_ftp_credential_permission(auth_payload)
    item = normalize_ftp_credential_payload(
        req.model_dump(),
        created_by=current_username(auth_payload),
    )
    item.id = ftp_credential_store.new_id()
    _validate_ftp_credential(item)
    saved = ftp_credential_store.save(item)
    return {"status": "created", "item": _serialize_ftp_credential(saved, auth_payload)}


@router.put("/{credential_id}")
async def update_ftp_credential(
    credential_id: str,
    req: FtpCredentialUpdateReq,
    auth_payload: dict = Depends(require_auth),
):
    _require_ftp_credential_permission(auth_payload)
    existing = _ensure_visible(ftp_credential_store.get(credential_id), auth_payload)
    _ensure_manageable(existing, auth_payload)
    updates = {key: value for key, value in req.model_dump().items() if value is not None}
    item = normalize_ftp_credential_payload({**asdict(existing), **updates}, existing=existing)
    _validate_ftp_credential(item)
    saved = ftp_credential_store.save(item)
    return {"status": "updated", "item": _serialize_ftp_credential(saved, auth_payload)}


@router.post("/test")
async def test_ftp_credential(req: FtpCredentialTestReq, auth_payload: dict = Depends(require_auth)):
    _require_ftp_credential_permission(auth_payload)
    item = _build_ftp_test_item(req, auth_payload)
    return {"status": "tested", **_test_ftp_connection(item)}


@router.delete("/{credential_id}")
async def delete_ftp_credential(credential_id: str, auth_payload: dict = Depends(require_auth)):
    _require_ftp_credential_permission(auth_payload)
    existing = _ensure_visible(ftp_credential_store.get(credential_id), auth_payload)
    _ensure_manageable(existing, auth_payload)
    ftp_credential_store.delete(existing.id)
    return {"status": "deleted", "id": existing.id}
