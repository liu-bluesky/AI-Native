"""Local connector pairing and management routes."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import io
from pathlib import Path
import re
import textwrap
from typing import Any
import zipfile

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse

from core.deps import local_connector_store, require_auth, role_store
from core.role_permissions import has_permission, resolve_role_permissions
from models.requests import (
    LocalConnectorHeartbeatReq,
    LocalConnectorPairActivateReq,
    LocalConnectorPairCodeCreateReq,
    LocalConnectorWorkspacePickConsumeReq,
)
from stores.json.local_connector_store import LocalConnectorRecord

router = APIRouter(prefix="/api/local-connectors")
_LOCAL_CONNECTOR_ROOT = Path(__file__).resolve().parents[3] / "local-connector"
_LOCAL_CONNECTOR_DESKTOP_DIST = _LOCAL_CONNECTOR_ROOT / "desktop" / "dist"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _current_username(auth_payload: dict) -> str:
    username = str(auth_payload.get("sub") or "").strip()
    return username or "unknown"


def _is_admin_like(auth_payload: dict) -> bool:
    role_id = str(auth_payload.get("role") or "").strip().lower()
    role = role_store.get(role_id)
    permissions = getattr(role, "permissions", [])
    resolved = resolve_role_permissions(permissions, role_id)
    return "*" in set(resolved)


def _ensure_permission(auth_payload: dict, permission_key: str) -> None:
    role_id = str(auth_payload.get("role") or "").strip().lower()
    role = role_store.get(role_id)
    permissions = getattr(role, "permissions", None)
    if not has_permission(permissions, permission_key, role_id=role_id):
        raise HTTPException(403, f"Permission denied: {permission_key}")


def _serialize_pair_code(item) -> dict[str, Any]:
    payload = asdict(item)
    payload["expired"] = bool(local_connector_store.is_pair_code_expired(item))
    payload["used"] = bool(str(item.used_at or "").strip())
    return payload


def _serialize_connector(item) -> dict[str, Any]:
    payload = asdict(item)
    last_seen_raw = str(item.last_seen_at or "").strip()
    online = False
    if last_seen_raw:
        try:
            last_seen = datetime.fromisoformat(last_seen_raw.replace("Z", "+00:00"))
            online = (datetime.now(timezone.utc) - last_seen).total_seconds() <= 90
        except ValueError:
            online = False
    payload["online"] = online
    return payload


def _extract_connector_token(
    x_connector_token: str | None = Header(None),
    token: str | None = Query(None),
) -> str:
    return str(x_connector_token or token or "").strip()


def _ensure_pair_code_access(item: Any, auth_payload: dict) -> None:
    username = _current_username(auth_payload)
    if _is_admin_like(auth_payload):
        return
    if str(getattr(item, "owner_username", "") or "").strip() != username:
        raise HTTPException(403, "Pair code access denied")


def _resolve_accessible_connector(connector_id: str, auth_payload: dict) -> LocalConnectorRecord:
    item = local_connector_store.get_connector(str(connector_id or "").strip())
    if item is None:
        raise HTTPException(404, "Connector not found")
    if _is_admin_like(auth_payload):
        return item
    if str(getattr(item, "owner_username", "") or "").strip() != _current_username(auth_payload):
        raise HTTPException(403, "Connector access denied")
    return item


def _normalize_installer_platform(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"mac", "macos", "darwin"}:
        return "macos"
    if normalized in {"windows", "win", "win32"}:
        return "windows"
    raise HTTPException(400, "Unsupported installer platform")


def _safe_archive_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "").strip()).strip("-") or "connector"


def _classify_desktop_artifact(path: Path) -> dict[str, str] | None:
    suffix = path.suffix.lower()
    name = path.name.lower()
    if suffix == ".exe" and "setup" in name:
        return {
            "platform": "windows",
            "variant": "setup",
            "label": "Windows 安装版",
            "description": "适合普通用户，双击安装后使用。",
            "sort_key": "1",
        }
    if suffix == ".exe":
        return {
            "platform": "windows",
            "variant": "portable",
            "label": "Windows 便携版",
            "description": "免安装版本，适合临时测试或直接运行。",
            "sort_key": "2",
        }
    if suffix == ".dmg":
        return {
            "platform": "macos",
            "variant": "dmg",
            "label": "macOS 安装包",
            "description": "适合 macOS 用户直接安装。",
            "sort_key": "3",
        }
    return None


def _list_desktop_artifacts() -> list[dict[str, Any]]:
    if not _LOCAL_CONNECTOR_DESKTOP_DIST.exists():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(_LOCAL_CONNECTOR_DESKTOP_DIST.iterdir()):
        if not path.is_file():
            continue
        if path.name.startswith("."):
            continue
        if path.suffix.lower() in {".blockmap", ".yml", ".yaml"}:
            continue
        meta = _classify_desktop_artifact(path)
        if meta is None:
            continue
        stat = path.stat()
        items.append(
            {
                "filename": path.name,
                "platform": meta["platform"],
                "variant": meta["variant"],
                "label": meta["label"],
                "description": meta["description"],
                "size_bytes": int(stat.st_size),
                "updated_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                "sort_key": meta["sort_key"],
            }
        )
    items.sort(key=lambda item: (str(item.get("sort_key") or ""), str(item.get("filename") or "").lower()))
    for item in items:
        item.pop("sort_key", None)
    return items


def _resolve_desktop_artifact(name: str) -> Path:
    normalized_name = str(name or "").strip()
    if not normalized_name:
        raise HTTPException(400, "Artifact name is required")
    for item in _list_desktop_artifacts():
        if str(item.get("filename") or "") == normalized_name:
            return _LOCAL_CONNECTOR_DESKTOP_DIST / normalized_name
    raise HTTPException(404, "Desktop artifact not found")


def _iter_connector_package_files() -> list[Path]:
    files: list[Path] = []
    if not _LOCAL_CONNECTOR_ROOT.exists():
        return files
    for path in _LOCAL_CONNECTOR_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in {"__pycache__", ".venv", "node_modules", "dist", "logs"} for part in path.parts):
            continue
        if path.name in {".connector-state.json", ".bootstrapped"}:
            continue
        if path.suffix == ".pyc":
            continue
        if path.name in {"connector_server.py", "launcher.py", "requirements.txt"}:
            continue
        files.append(path)
    return files


def _quickstart_text(platform: str, platform_url: str, pair_code: Any) -> str:
    launcher_name = "start-connector.command" if platform == "macos" else "start-connector.bat"
    status_url = "http://127.0.0.1:3931"
    note = str(getattr(pair_code, "note", "") or "").strip() or "未填写备注"
    expires_text = "永久有效" if bool(getattr(pair_code, "permanent", False)) else str(getattr(pair_code, "expires_at", "") or "").strip() or "-"
    return textwrap.dedent(
        f"""
        Local Connector Quick Start
        ===========================

        1. 解压整个压缩包到用户自己的电脑。
        2. 直接双击 `{launcher_name}`。
        3. 当前安装包是 Node 版本，不需要 Python 虚拟环境；如果电脑没装 Node.js，请先安装 Node.js 18 或更高版本。首次启动会自动安装运行依赖。
        4. 启动成功后，会自动打开本地状态页，可看到“是否已配对 / 是否在线 / 心跳是否正常”。
        5. 配对成功后，回到平台的 AI 对话中心，选择这个本地连接器即可。

        当前平台地址:
        {platform_url}

        本地状态页:
        {status_url}

        备注:
        {note}

        有效期:
        {expires_text}

        说明:
        - 安装包内已预写入本次激活信息，无需手动填写配对码。
        - 底层激活码仍然是单次使用，首次成功绑定后即失效。
        - 之后再次双击同一个启动文件，会复用本机已保存的连接器身份，不会重复占用配对码。
        - 如果提示找不到 Node.js，请先在该电脑安装 Node.js 18 或更高版本。
        - 首次启动时会自动执行一次 `npm install --omit=dev`，请保持网络可用。
        - 如果启动失败，请打开同目录下 `logs/bootstrap.log` 和 `logs/connector.log` 查看原因。
        """
    ).strip() + "\n"


def _macos_launcher(platform_url: str, pair_code: str) -> str:
    return textwrap.dedent(
        f"""#!/usr/bin/env bash
        set -euo pipefail

        ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
        cd "$ROOT_DIR"

        if ! command -v node >/dev/null 2>&1; then
          echo "未检测到 Node.js，请先安装 Node.js 18 或更高版本。"
          read -r -p "按回车键退出..."
          exit 1
        fi

        export LOCAL_CONNECTOR_PLATFORM_URL="{platform_url}"
        export LOCAL_CONNECTOR_PAIR_CODE="{pair_code}"
        export LOCAL_CONNECTOR_NAME="${{LOCAL_CONNECTOR_NAME:-$(scutil --get ComputerName 2>/dev/null || hostname)}}"

        echo "正在启动 Local Connector..."
        node launcher.js
        """
    )


def _windows_bat_launcher(platform_url: str, pair_code: str) -> str:
    return textwrap.dedent(
        f"""@echo off
        setlocal
        title Local Connector

        cd /d "%~dp0"

        where node >nul 2>nul
        if errorlevel 1 (
          echo 未检测到 Node.js，请先安装 Node.js 18 或更高版本。
          echo 下载地址：https://nodejs.org/
          pause
          exit /b 1
        )

        set "LOCAL_CONNECTOR_PLATFORM_URL={platform_url}"
        set "LOCAL_CONNECTOR_PAIR_CODE={pair_code}"
        if "%LOCAL_CONNECTOR_NAME%"=="" set "LOCAL_CONNECTOR_NAME=%COMPUTERNAME% Connector"
        if "%LOCAL_CONNECTOR_HOST%"=="" set "LOCAL_CONNECTOR_HOST=127.0.0.1"
        if "%LOCAL_CONNECTOR_PORT%"=="" set "LOCAL_CONNECTOR_PORT=3931"

        echo 正在启动 Local Connector...
        node launcher.js
        echo.
        echo Local Connector 已停止。
        echo 如需排查，请查看 logs\\bootstrap.log 和 logs\\connector.log
        pause
        """
    )


def _windows_ps1_launcher(platform_url: str, pair_code: str) -> str:
    return textwrap.dedent(
        f"""$ErrorActionPreference = "Stop"

        Set-Location $PSScriptRoot

        if (-not (Get-Command node -ErrorAction SilentlyContinue)) {{
          Write-Host "未检测到 Node.js，请先安装 Node.js 18 或更高版本。"
          Write-Host "下载地址：https://nodejs.org/"
          Read-Host "按回车键退出"
          exit 1
        }}

        $env:LOCAL_CONNECTOR_PLATFORM_URL = "{platform_url}"
        $env:LOCAL_CONNECTOR_PAIR_CODE = "{pair_code}"
        if (-not $env:LOCAL_CONNECTOR_NAME) {{
          $env:LOCAL_CONNECTOR_NAME = "$env:COMPUTERNAME Connector"
        }}
        $HostValue = if ($env:LOCAL_CONNECTOR_HOST) {{ $env:LOCAL_CONNECTOR_HOST }} else {{ "127.0.0.1" }}
        $PortValue = if ($env:LOCAL_CONNECTOR_PORT) {{ $env:LOCAL_CONNECTOR_PORT }} else {{ "3931" }}
        $env:LOCAL_CONNECTOR_HOST = $HostValue
        $env:LOCAL_CONNECTOR_PORT = $PortValue

        Write-Host "正在启动 Local Connector..."
        node .\launcher.js
        Write-Host ""
        Write-Host "Local Connector 已停止。"
        Write-Host "如需排查，请查看 logs/bootstrap.log 和 logs/connector.log"
        Read-Host "按回车键关闭窗口"
        """
    )


def _zip_writestr(
    archive: zipfile.ZipFile,
    arcname: str,
    content: str,
    *,
    executable: bool = False,
) -> None:
    info = zipfile.ZipInfo(arcname)
    info.compress_type = zipfile.ZIP_DEFLATED
    if executable:
        info.external_attr = 0o755 << 16
    archive.writestr(info, content)


def _build_installer_response(
    *,
    pair_code: Any,
    platform: str,
    platform_url: str,
) -> StreamingResponse:
    normalized_platform = _normalize_installer_platform(platform)
    if not _LOCAL_CONNECTOR_ROOT.exists():
        raise HTTPException(500, "local-connector package directory not found")

    package_name = _safe_archive_name(
        f"local-connector-{normalized_platform}-{getattr(pair_code, 'code', '')}".lower()
    )
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in _iter_connector_package_files():
            relative = file_path.relative_to(_LOCAL_CONNECTOR_ROOT).as_posix()
            archive.write(file_path, arcname=f"{package_name}/{relative}")
        _zip_writestr(
            archive,
            f"{package_name}/QUICKSTART.txt",
            _quickstart_text(normalized_platform, platform_url, pair_code),
        )
        if normalized_platform == "macos":
            _zip_writestr(
                archive,
                f"{package_name}/start-connector.command",
                _macos_launcher(platform_url, str(getattr(pair_code, "code", "") or "").strip()),
                executable=True,
            )
        else:
            _zip_writestr(
                archive,
                f"{package_name}/start-connector.bat",
                _windows_bat_launcher(platform_url, str(getattr(pair_code, "code", "") or "").strip()),
            )
            _zip_writestr(
                archive,
                f"{package_name}/start-connector.ps1",
                _windows_ps1_launcher(platform_url, str(getattr(pair_code, "code", "") or "").strip()),
            )

    memory.seek(0)
    return StreamingResponse(
        memory,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{package_name}.zip"',
        },
    )


@router.get("", dependencies=[Depends(require_auth)])
async def list_local_connectors(auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "menu.ai.chat")
    username = _current_username(auth_payload)
    if _is_admin_like(auth_payload):
        items = local_connector_store.list_connectors()
    else:
        items = local_connector_store.list_connectors(owner_username=username)
    return {"connectors": [_serialize_connector(item) for item in items]}


@router.get("/desktop-artifacts", dependencies=[Depends(require_auth)])
async def list_desktop_artifacts(auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "menu.ai.chat")
    return {"artifacts": _list_desktop_artifacts()}


@router.get("/desktop-artifacts/download", dependencies=[Depends(require_auth)])
async def download_desktop_artifact(
    name: str = Query(""),
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.ai.chat")
    artifact_path = _resolve_desktop_artifact(name)
    return FileResponse(
        artifact_path,
        media_type="application/octet-stream",
        filename=artifact_path.name,
    )


@router.get("/pair-codes", dependencies=[Depends(require_auth)])
async def list_pair_codes(auth_payload: dict = Depends(require_auth)):
    _ensure_permission(auth_payload, "menu.ai.chat")
    username = _current_username(auth_payload)
    if _is_admin_like(auth_payload):
        items = local_connector_store.list_pair_codes()
    else:
        items = local_connector_store.list_pair_codes(owner_username=username)
    return {"pair_codes": [_serialize_pair_code(item) for item in items]}


@router.post("/pair-codes", dependencies=[Depends(require_auth)])
async def create_pair_code(
    req: LocalConnectorPairCodeCreateReq,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.ai.chat")
    item = local_connector_store.create_pair_code(
        owner_username=_current_username(auth_payload),
        note=str(req.note or "").strip(),
        ttl_minutes=int(req.ttl_minutes if req.ttl_minutes is not None else 10),
        permanent=bool(req.permanent),
    )
    return {"pair_code": _serialize_pair_code(item)}


@router.get("/pair-codes/{code}/installer", dependencies=[Depends(require_auth)])
async def download_pair_code_installer(
    code: str,
    platform: str,
    request: Request,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.ai.chat")
    pair_code = local_connector_store.get_pair_code(str(code or "").strip())
    if pair_code is None:
        raise HTTPException(404, "Pair code not found")
    _ensure_pair_code_access(pair_code, auth_payload)
    platform_url = str(request.base_url).rstrip("/")
    return _build_installer_response(
        pair_code=pair_code,
        platform=platform,
        platform_url=platform_url,
    )


@router.get("/installer/quick", dependencies=[Depends(require_auth)])
async def download_quick_installer(
    platform: str,
    request: Request,
    note: str = Query(""),
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.ai.chat")
    username = _current_username(auth_payload)
    pair_code = local_connector_store.create_pair_code(
        owner_username=username,
        note=str(note or "").strip()[:200] or "浏览器快捷接入",
        ttl_minutes=24 * 60,
        permanent=False,
    )
    return _build_installer_response(
        pair_code=pair_code,
        platform=platform,
        platform_url=str(request.base_url).rstrip("/"),
    )


@router.post("/pair/browser-session", dependencies=[Depends(require_auth)])
async def create_browser_pair_session(
    request: Request,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.ai.chat")
    username = _current_username(auth_payload)
    pair_code = local_connector_store.create_pair_code(
        owner_username=username,
        note="浏览器发起配对",
        ttl_minutes=10,
        permanent=False,
    )
    return {
        "pairing": {
            "pair_code": pair_code.code,
            "expires_at": pair_code.expires_at,
            "platform_url": str(request.base_url).rstrip("/"),
            "owner_username": pair_code.owner_username,
        }
    }


@router.post("/{connector_id}/workspace-pick/session", dependencies=[Depends(require_auth)])
async def create_workspace_pick_session(
    connector_id: str,
    request: Request,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.ai.chat")
    connector = _resolve_accessible_connector(connector_id, auth_payload)
    session = local_connector_store.create_workspace_pick_session(
        owner_username=_current_username(auth_payload),
        connector_id=connector.id,
        ttl_seconds=60,
    )
    return {
        "workspace_pick": {
            "session_id": session.id,
            "session_token": session.token,
            "connector_id": connector.id,
            "expires_at": session.expires_at,
            "platform_url": str(request.base_url).rstrip("/"),
        }
    }


@router.post("/workspace-pick/consume")
async def consume_workspace_pick_session(
    req: LocalConnectorWorkspacePickConsumeReq,
    connector_token: str = Depends(_extract_connector_token),
):
    connector = local_connector_store.get_connector_by_token(connector_token)
    if connector is None:
        raise HTTPException(401, "Connector token invalid")
    session = local_connector_store.get_workspace_pick_session(str(req.session_id or "").strip())
    if session is None:
        raise HTTPException(404, "Workspace pick session not found")
    if bool(str(session.used_at or "").strip()):
        raise HTTPException(409, "Workspace pick session already used")
    if local_connector_store.is_workspace_pick_session_expired(session):
        raise HTTPException(410, "Workspace pick session expired")
    if str(session.token or "").strip() != str(req.session_token or "").strip():
        raise HTTPException(403, "Workspace pick session token invalid")
    if str(session.connector_id or "").strip() != str(connector.id or "").strip():
        raise HTTPException(403, "Workspace pick session does not match connector")
    if str(session.owner_username or "").strip() != str(connector.owner_username or "").strip():
        raise HTTPException(403, "Workspace pick session owner mismatch")
    consumed = local_connector_store.consume_workspace_pick_session(session.id)
    return {
        "workspace_pick": {
            "ok": True,
            "session_id": session.id,
            "connector_id": connector.id,
            "owner_username": connector.owner_username,
            "used_at": getattr(consumed, "used_at", ""),
        }
    }


@router.post("/pair/activate")
async def activate_pair(req: LocalConnectorPairActivateReq):
    pair_code = local_connector_store.get_pair_code(str(req.pair_code or "").strip())
    if pair_code is None:
        raise HTTPException(404, "Pair code not found")
    if bool(str(pair_code.used_at or "").strip()):
        raise HTTPException(409, "Pair code already used")
    if local_connector_store.is_pair_code_expired(pair_code):
        raise HTTPException(410, "Pair code expired")

    now = _now_iso()
    connector_id = local_connector_store.new_connector_id()
    connector_token = local_connector_store.new_connector_token()
    manifest = req.manifest if isinstance(req.manifest, dict) else {}
    health = req.health if isinstance(req.health, dict) else {}
    capabilities = manifest.get("capabilities") if isinstance(manifest.get("capabilities"), dict) else {}

    record = LocalConnectorRecord(
        id=connector_id,
        owner_username=pair_code.owner_username,
        connector_token=connector_token,
        connector_name=str(req.connector_name or "").strip() or "Local Connector",
        platform=str(req.platform or "").strip(),
        app_version=str(req.app_version or "").strip(),
        advertised_url=str(req.advertised_url or "").strip(),
        status="online",
        last_error="",
        capabilities=capabilities,
        manifest=manifest,
        health=health,
        paired_at=now,
        last_seen_at=now,
        created_at=now,
        updated_at=now,
    )
    local_connector_store.save_connector(record)
    local_connector_store.consume_pair_code(pair_code.code, connector_id)
    return {
        "connector_id": connector_id,
        "connector_token": connector_token,
        "owner_username": pair_code.owner_username,
        "heartbeat_interval_sec": 20,
    }


@router.post("/{connector_id}/heartbeat")
async def heartbeat_local_connector(
    connector_id: str,
    req: LocalConnectorHeartbeatReq,
    connector_token: str = Depends(_extract_connector_token),
):
    token = str(connector_token or "").strip()
    if not token:
        raise HTTPException(401, "Missing connector token")
    item = local_connector_store.get_connector(str(connector_id or "").strip())
    if item is None:
        raise HTTPException(404, "Connector not found")
    if str(item.connector_token or "").strip() != token:
        raise HTTPException(403, "Connector token mismatch")

    now = _now_iso()
    item.advertised_url = str(req.advertised_url or item.advertised_url or "").strip()
    item.manifest = req.manifest if isinstance(req.manifest, dict) else item.manifest
    item.health = req.health if isinstance(req.health, dict) else item.health
    item.capabilities = (
        item.manifest.get("capabilities")
        if isinstance(item.manifest, dict) and isinstance(item.manifest.get("capabilities"), dict)
        else item.capabilities
    )
    item.status = str(req.status or "online").strip() or "online"
    item.last_error = str(req.last_error or "").strip()
    item.last_seen_at = now
    item.updated_at = now
    local_connector_store.save_connector(item)
    return {"status": "ok", "server_time": now}


@router.delete("/{connector_id}", dependencies=[Depends(require_auth)])
async def delete_local_connector(
    connector_id: str,
    auth_payload: dict = Depends(require_auth),
):
    _ensure_permission(auth_payload, "menu.ai.chat")
    item = local_connector_store.get_connector(str(connector_id or "").strip())
    if item is None:
        raise HTTPException(404, "Connector not found")
    username = _current_username(auth_payload)
    if not _is_admin_like(auth_payload) and item.owner_username != username:
        raise HTTPException(403, "Connector access denied")
    ok = local_connector_store.delete_connector(connector_id)
    return {"status": "deleted" if ok else "not_found"}
