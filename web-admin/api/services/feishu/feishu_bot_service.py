"""Feishu bot webhook integration."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import mimetypes
import os
import re
import subprocess
import time
import uuid
from datetime import datetime, timedelta, timezone
from email.message import Message
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import quote, unquote, urlparse

import requests

try:
    import lark_oapi as lark
    from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
    from lark_oapi.event.callback.model.p2_card_action_trigger import P2CardActionTriggerResponse
except ModuleNotFoundError as exc:
    lark = None
    P2ImMessageReceiveV1 = Any
    P2CardActionTriggerResponse = None
    ReplyMessageRequest = Any
    ReplyMessageRequestBody = Any
    _LARK_IMPORT_ERROR: ModuleNotFoundError | None = exc
else:
    _LARK_IMPORT_ERROR = None

if TYPE_CHECKING:
    import lark_oapi as _lark_module

from core.config import get_api_data_dir
from models.requests import ProjectChatReq
from services.assistant.assistant_workflow_state_service import (
    assistant_workflow_from_context,
    evolve_assistant_workflow_state,
    with_assistant_workflow_state,
)
from services.chat.archive_workflow_state_service import (
    archive_message_reply_content as _archive_message_reply_content,
    archive_workflow_state_from_context as _archive_workflow_state_from_context,
    archive_workflow_status as _archive_workflow_status,
    build_archive_workflow_state as _build_archive_workflow_state,
    message_has_closed_archive_state as _message_has_closed_archive_state,
    message_has_pending_archive_state as _message_has_pending_archive_state,
    reply_claims_archive_success as _shared_reply_claims_archive_success,
    reply_contains_structured_pending_archive as _shared_reply_contains_structured_pending_archive,
    with_archive_workflow_state as _with_archive_workflow_state,
)
from services.connectors.bot_connector_service import list_bot_connectors
from services.feishu.feishu_archive_writer_service import (
    append_direct_bitable_record_attachments,
    archive_feishu_task_message,
    is_feishu_auto_archive_action,
)
from services.chat.project_chat_execution_service import run_project_chat_once
from services.assistant.global_assistant_task_service import (
    execute_global_assistant_task,
    list_global_assistant_tasks,
    process_global_assistant_tasks_for_event,
)
from services.feishu.feishu_scheduled_reminder_service import create_feishu_meeting_reminder_task
from services.providers.system_speech_service import enqueue_system_speech

logger = logging.getLogger(__name__)

_FEISHU_REPLY_CHAR_LIMIT = 4000
_FEISHU_OPEN_API_BASE_URL = "https://open.feishu.cn"
_FEISHU_RESOURCE_DIR = "feishu-message-resources"
_FEISHU_RESOURCE_PUBLIC_PREFIX = "/api/bot-events/feishu"
_LOG_RECORD_RESERVED_KEYS = frozenset(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}
_FEISHU_BOT_INFO_CACHE_TTL_SECONDS = 300
_FEISHU_BOT_INFO_CACHE: dict[str, tuple[float, dict[str, str]]] = {}


def is_feishu_sdk_available() -> bool:
    return _LARK_IMPORT_ERROR is None


def get_feishu_sdk_error_message() -> str:
    return "Feishu bot integration requires optional dependency 'lark_oapi' to be installed."


def _require_feishu_sdk() -> None:
    if _LARK_IMPORT_ERROR is not None:
        raise RuntimeError(get_feishu_sdk_error_message()) from _LARK_IMPORT_ERROR


def get_feishu_connector(connector_id: str) -> dict[str, Any] | None:
    normalized_connector_id = str(connector_id or "").strip()
    if not normalized_connector_id:
        return None
    for item in list_bot_connectors():
        if str(item.get("id") or "").strip() != normalized_connector_id:
            continue
        if str(item.get("platform") or "").strip().lower() != "feishu":
            continue
        return dict(item)
    return None


def _feishu_open_api_url(path: str) -> str:
    normalized = "/" + str(path or "").lstrip("/")
    return f"{_FEISHU_OPEN_API_BASE_URL}{normalized}"


def _safe_resource_token(value: Any, *, max_len: int = 160) -> str:
    token = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())
    token = token.strip("._-")
    return (token or "resource")[:max_len]


def _extension_from_content_type(content_type: str) -> str:
    mime = str(content_type or "").split(";", 1)[0].strip().lower()
    if not mime or mime == "application/octet-stream":
        return ""
    extension = mimetypes.guess_extension(mime) or ""
    if extension == ".jpe":
        return ".jpg"
    return extension


def _filename_from_content_disposition(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    message = Message()
    message["content-disposition"] = raw
    filename = message.get_filename() or ""
    return Path(str(filename)).name.strip()


def _feishu_resource_root() -> Path:
    return get_api_data_dir() / _FEISHU_RESOURCE_DIR


def _feishu_resource_public_base_url(connector: dict[str, Any]) -> str:
    raw = (
        connector.get("resource_public_base_url")
        or connector.get("public_base_url")
        or connector.get("server_public_base_url")
        or os.environ.get("FEISHU_RESOURCE_PUBLIC_BASE_URL")
        or os.environ.get("API_PUBLIC_BASE_URL")
        or os.environ.get("PUBLIC_BASE_URL")
        or ""
    )
    return str(raw or "").strip().rstrip("/")


def _build_feishu_resource_url(
    connector: dict[str, Any],
    *,
    connector_id: str,
    message_id: str,
    filename: str,
) -> str:
    path = (
        f"{_FEISHU_RESOURCE_PUBLIC_PREFIX}/{quote(_safe_resource_token(connector_id))}"
        f"/resources/{quote(_safe_resource_token(message_id))}/{quote(Path(filename).name)}"
    )
    base_url = _feishu_resource_public_base_url(connector)
    return f"{base_url}{path}" if base_url else path


def _parse_feishu_resource_url(value: str) -> dict[str, str]:
    raw = str(value or "").strip()
    if not raw:
        return {}
    path = urlparse(raw).path if "://" in raw else raw
    marker = f"{_FEISHU_RESOURCE_PUBLIC_PREFIX}/"
    if marker not in path:
        return {}
    tail = path.split(marker, 1)[1].strip("/")
    parts = [unquote(item) for item in tail.split("/") if item]
    if len(parts) < 4 or parts[1] != "resources":
        return {}
    filename = Path(parts[3]).name
    file_key = Path(filename).stem.strip()
    if not parts[0] or not parts[2] or not file_key:
        return {}
    return {
        "connector_id": parts[0],
        "message_id": parts[2],
        "file_key": file_key,
        "filename": filename,
        "type": "image",
    }


def get_feishu_message_resource_file(connector_id: str, message_id: str, filename: str) -> tuple[Path, str]:
    safe_connector_id = _safe_resource_token(connector_id)
    safe_message_id = _safe_resource_token(message_id)
    safe_filename = Path(_safe_resource_token(filename, max_len=240)).name
    if not safe_connector_id or not safe_message_id or not safe_filename:
        raise FileNotFoundError("invalid resource path")
    root = (_feishu_resource_root() / safe_connector_id / safe_message_id).resolve()
    path = (root / safe_filename).resolve()
    if root not in path.parents or not path.is_file():
        raise FileNotFoundError("resource not found")
    mime_type, _ = mimetypes.guess_type(path.name)
    return path, (mime_type or "application/octet-stream")


def _sanitize_log_extra(extra: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(extra, dict):
        return {}
    sanitized: dict[str, Any] = {}
    for raw_key, value in extra.items():
        key = str(raw_key or "").strip() or "extra"
        if key in _LOG_RECORD_RESERVED_KEYS:
            key = f"log_{key}"
        while key in sanitized or key in _LOG_RECORD_RESERVED_KEYS:
            key = f"log_{key}"
        sanitized[key] = value
    return sanitized


def _parse_feishu_message_content(message: Any) -> dict[str, Any]:
    raw_content = str(getattr(message, "content", "") or "").strip()
    if not raw_content:
        return {}
    try:
        payload = json.loads(raw_content)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _iter_feishu_post_nodes(value: Any) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    if isinstance(value, dict):
        nodes.append(value)
        for item in value.values():
            nodes.extend(_iter_feishu_post_nodes(item))
    elif isinstance(value, list):
        for item in value:
            nodes.extend(_iter_feishu_post_nodes(item))
    return nodes


def _extract_feishu_post_text(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    for node in _iter_feishu_post_nodes(payload.get("content")):
        tag = str(node.get("tag") or "").strip().lower()
        if tag in {"text", "a"}:
            text = str(node.get("text") or "").strip()
            if text:
                parts.append(text)
    return " ".join(" ".join(parts).split())


def _append_feishu_message_resource(
    resources: list[dict[str, str]],
    *,
    file_key: Any,
    resource_type: str,
    label: str,
) -> None:
    normalized_file_key = str(file_key or "").strip()
    if not normalized_file_key:
        return
    resources.append(
        {
            "file_key": normalized_file_key,
            "type": str(resource_type or "file").strip().lower() or "file",
            "label": str(label or "附件").strip() or "附件",
        }
    )


def _infer_feishu_resource_type_from_node(node: dict[str, Any], key_name: str) -> tuple[str, str]:
    tag = str(node.get("tag") or node.get("msg_type") or node.get("message_type") or node.get("type") or "").strip().lower()
    if key_name in {"image_key", "imageKey"} or tag in {"img", "image", "media"}:
        return "image", "图片"
    if tag == "audio":
        return "file", "音频"
    if tag in {"video", "media"}:
        return "file", "视频"
    return "file", "附件"


def _collect_feishu_message_resources_from_payload(value: Any, resources: list[dict[str, str]]) -> None:
    if isinstance(value, dict):
        for key_name in ("image_key", "imageKey", "file_key", "fileKey"):
            if key_name not in value:
                continue
            resource_type, label = _infer_feishu_resource_type_from_node(value, key_name)
            _append_feishu_message_resource(
                resources,
                file_key=value.get(key_name),
                resource_type=resource_type,
                label=label,
            )
        for item in value.values():
            _collect_feishu_message_resources_from_payload(item, resources)
    elif isinstance(value, list):
        for item in value:
            _collect_feishu_message_resources_from_payload(item, resources)


def _extract_feishu_message_resources(message: Any) -> list[dict[str, str]]:
    message_type = str(getattr(message, "message_type", "") or "").strip().lower()
    payload = _parse_feishu_message_content(message)
    resources: list[dict[str, str]] = []
    _collect_feishu_message_resources_from_payload(payload, resources)
    if message_type in {"audio", "video", "file"}:
        for item in resources:
            if str(item.get("type") or "").strip().lower() != "file":
                continue
            item["label"] = {"audio": "音频", "video": "视频"}.get(message_type, "附件")
    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, str]] = []
    for item in resources:
        key = (str(item.get("type") or ""), str(item.get("file_key") or ""))
        if not key[1] or key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _extract_feishu_message_resource(message: Any) -> dict[str, str]:
    resources = _extract_feishu_message_resources(message)
    return resources[0] if resources else {}


def _download_feishu_message_resource(
    connector: dict[str, Any],
    *,
    connector_id: str,
    message_id: str,
    file_key: str,
    resource_type: str,
) -> dict[str, str]:
    normalized_message_id = str(message_id or "").strip()
    normalized_file_key = str(file_key or "").strip()
    if not normalized_message_id or not normalized_file_key:
        return {}
    safe_connector_id = _safe_resource_token(connector_id)
    safe_message_id = _safe_resource_token(normalized_message_id)
    resource_dir = _feishu_resource_root() / safe_connector_id / safe_message_id
    resource_dir.mkdir(parents=True, exist_ok=True)

    token = _get_feishu_tenant_access_token(connector)
    response = requests.get(
        _feishu_open_api_url(
            f"/open-apis/im/v1/messages/{quote(normalized_message_id)}/resources/{quote(normalized_file_key)}"
        ),
        headers={"Authorization": f"Bearer {token}"},
        params={"type": str(resource_type or "image").strip() or "image"},
        timeout=30,
    )
    content_type = str(response.headers.get("Content-Type") or "").strip()
    if response.status_code >= 400:
        detail = ""
        try:
            payload = response.json()
        except Exception:
            payload = {}
        if isinstance(payload, dict):
            code = payload.get("code")
            msg = str(payload.get("msg") or payload.get("message") or "").strip()
            if code is not None or msg:
                detail = f" code={code} msg={msg}".strip()
        if not detail:
            detail = str(getattr(response, "text", "") or "").strip()[:300]
        raise RuntimeError(
            "飞书资源下载失败："
            f"HTTP {response.status_code}; message_id={normalized_message_id}; "
            f"file_key={normalized_file_key}; type={str(resource_type or 'image').strip() or 'image'}"
            + (f"; {detail}" if detail else "")
        )
    if content_type.startswith("application/json"):
        try:
            payload = response.json()
        except Exception:
            payload = {}
        code = payload.get("code") if isinstance(payload, dict) else None
        msg = str(payload.get("msg") or payload.get("message") or "").strip() if isinstance(payload, dict) else ""
        raise RuntimeError(
            "飞书资源下载失败："
            f"message_id={normalized_message_id}; file_key={normalized_file_key}; "
            f"type={str(resource_type or 'image').strip() or 'image'}"
            + (f"; code={code}" if code is not None else "")
            + (f"; msg={msg}" if msg else "")
        )

    original_filename = _filename_from_content_disposition(str(response.headers.get("Content-Disposition") or ""))
    extension = Path(original_filename).suffix or _extension_from_content_type(content_type)
    filename = f"{_safe_resource_token(normalized_file_key, max_len=180)}{extension or ''}"
    file_path = resource_dir / filename
    if not file_path.exists():
        file_path.write_bytes(response.content)
    return {
        "file_key": normalized_file_key,
        "type": str(resource_type or "image").strip() or "image",
        "filename": filename,
        "path": str(file_path),
        "url": _build_feishu_resource_url(
            connector,
            connector_id=connector_id,
            message_id=normalized_message_id,
            filename=filename,
        ),
        "content_type": content_type,
    }


def _cleanup_downloaded_feishu_resources(resources: list[dict[str, str]]) -> None:
    root = _feishu_resource_root().resolve()
    touched_dirs: list[Path] = []
    for item in resources:
        raw_path = str(item.get("path") or "").strip()
        if not raw_path:
            continue
        try:
            path = Path(raw_path).resolve()
            if root not in path.parents or not path.is_file():
                continue
            touched_dirs.append(path.parent)
            path.unlink()
        except Exception:
            logger.warning("failed to cleanup downloaded feishu resource: %s", raw_path, exc_info=True)

    for directory in sorted(set(touched_dirs), key=lambda value: len(value.parts), reverse=True):
        current = directory
        while root in current.parents:
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent


def _get_feishu_tenant_access_token(connector: dict[str, Any]) -> str:
    app_id = str(connector.get("app_id") or "").strip()
    app_secret = str(connector.get("app_secret") or "").strip()
    if not app_id or not app_secret:
        raise RuntimeError("飞书机器人缺少 app_id 或 app_secret")
    response = requests.post(
        _feishu_open_api_url("/open-apis/auth/v3/tenant_access_token/internal"),
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()
    if int(payload.get("code") or 0) != 0:
        raise RuntimeError(str(payload.get("msg") or "获取飞书 tenant_access_token 失败"))
    token = str(payload.get("tenant_access_token") or "").strip()
    if not token:
        raise RuntimeError("飞书没有返回 tenant_access_token")
    return token


def _get_feishu_runtime_bot_identity(connector: dict[str, Any]) -> dict[str, str]:
    connector_id = str(connector.get("id") or "").strip()
    app_id = str(connector.get("app_id") or "").strip()
    cache_key = f"{connector_id}:{app_id}"
    if cache_key:
        cached = _FEISHU_BOT_INFO_CACHE.get(cache_key)
        now = time.monotonic()
        if cached is not None and now - cached[0] < _FEISHU_BOT_INFO_CACHE_TTL_SECONDS:
            return dict(cached[1])
    try:
        token = _get_feishu_tenant_access_token(connector)
        response = requests.get(
            _feishu_open_api_url("/open-apis/bot/v3/info"),
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception:
        logger.debug(
            "failed to resolve runtime feishu bot identity",
            extra={"connector_id": connector_id},
            exc_info=True,
        )
        return {}
    if int(payload.get("code") or 0) != 0:
        return {}
    raw_bot = payload.get("bot")
    if not isinstance(raw_bot, dict):
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        raw_bot = data.get("bot") if isinstance(data.get("bot"), dict) else data
    bot = raw_bot if isinstance(raw_bot, dict) else {}
    identity = {
        "bot_open_id": str(bot.get("open_id") or "").strip(),
        "bot_name": str(bot.get("app_name") or bot.get("name") or "").strip(),
    }
    if cache_key:
        _FEISHU_BOT_INFO_CACHE[cache_key] = (time.monotonic(), identity)
    return dict(identity)


def _normalize_feishu_chat_search_item(raw: Any) -> dict[str, str]:
    item = raw if isinstance(raw, dict) else {}
    meta_data = item.get("meta_data") if isinstance(item.get("meta_data"), dict) else {}
    return {
        "chat_id": str(
            item.get("chat_id")
            or item.get("chatId")
            or meta_data.get("chat_id")
            or meta_data.get("chatId")
            or ""
        ).strip(),
        "name": str(
            item.get("name")
            or item.get("chat_name")
            or item.get("chatName")
            or meta_data.get("name")
            or meta_data.get("chat_name")
            or meta_data.get("chatName")
            or ""
        ).strip(),
        "description": str(
            item.get("description") or meta_data.get("description") or ""
        ).strip(),
    }


def check_feishu_connector_credentials(connector: dict[str, Any]) -> dict[str, Any]:
    token = _get_feishu_tenant_access_token(connector)
    return {"ok": bool(token), "message": "飞书应用凭证有效"}


def _normalize_feishu_chat_resolve_identity(raw: Any) -> str:
    value = str(raw or "bot").strip().lower()
    if value in {"user", "user_access_token", "lark_cli_user"}:
        return "user"
    return "bot"


def _extract_feishu_chat_search_items(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    for container in (payload, data):
        for key in ("items", "chats", "chatters", "groups", "results"):
            raw_items = container.get(key)
            if isinstance(raw_items, list):
                return raw_items
    return []


def _select_feishu_chat_search_candidate(items: list[dict[str, str]], query: str, *, identity: str) -> dict[str, str]:
    exact = [item for item in items if item.get("name") == query]
    candidates = exact or items
    if not candidates:
        subject = "当前登录用户可见" if identity == "user" else "机器人可见"
        raise RuntimeError(
            f"没有搜索到{subject}的飞书群，请确认"
            + (
                "已完成 lark-cli 用户授权、用户在群内"
                if identity == "user"
                else "机器人在群内、应用权限已开通 im:chat:read"
            )
            + "，或换更精确的群名"
        )
    if len(candidates) > 1:
        preview = "、".join(f"{item.get('name') or '未命名'}({item.get('chat_id')})" for item in candidates[:5])
        raise RuntimeError(f"搜索到多个飞书群，请把群名称填得更精确：{preview}")
    return candidates[0]


def _normalize_feishu_chat_list_item(raw: Any) -> dict[str, str]:
    item = raw if isinstance(raw, dict) else {}
    return {
        "chat_id": str(item.get("chat_id") or item.get("chatId") or "").strip(),
        "chat_name": str(item.get("name") or item.get("chat_name") or item.get("chatName") or "").strip(),
        "description": str(item.get("description") or "").strip(),
        "owner_id": str(item.get("owner_id") or item.get("ownerId") or "").strip(),
        "chat_mode": str(item.get("chat_mode") or item.get("chatMode") or "").strip(),
        "chat_type": str(item.get("chat_type") or item.get("chatType") or "").strip(),
        "external": str(item.get("external") or "").strip(),
    }


def list_feishu_bot_joined_chats(connector: dict[str, Any], *, page_size: int = 100) -> dict[str, Any]:
    normalized_page_size = max(1, min(int(page_size or 100), 100))
    token = _get_feishu_tenant_access_token(connector)
    page_token = ""
    chats: list[dict[str, str]] = []
    while True:
        params: dict[str, Any] = {
            "user_id_type": "open_id",
            "page_size": normalized_page_size,
        }
        if page_token:
            params["page_token"] = page_token
        response = requests.get(
            _feishu_open_api_url("/open-apis/im/v1/chats"),
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        if int(payload.get("code") or 0) != 0:
            raise RuntimeError(str(payload.get("msg") or "飞书群列表获取失败"))
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        for raw in data.get("items") or []:
            item = _normalize_feishu_chat_list_item(raw)
            if item.get("chat_id"):
                chats.append(item)
        if not bool(data.get("has_more")):
            break
        page_token = str(data.get("page_token") or "").strip()
        if not page_token:
            break
    return {
        "status": "scanned",
        "platform": "feishu",
        "source": "feishu.im.v1.chats",
        "items": chats,
        "count": len(chats),
    }


def _format_lark_cli_chat_search_error(output: str, *, identity: str) -> str:
    text = str(output or "").strip()
    try:
        payload = json.loads(text or "{}")
    except json.JSONDecodeError:
        payload = {}
    error = payload.get("error") if isinstance(payload, dict) and isinstance(payload.get("error"), dict) else {}
    error_type = str(error.get("type") or "").strip()
    message = str(error.get("message") or "").strip()
    update = payload.get("_notice", {}).get("update", {}) if isinstance(payload, dict) else {}
    update_hint = ""
    if isinstance(update, dict) and update.get("latest") and update.get("current"):
        update_hint = f"；检测到 lark-cli 可更新：当前 {update.get('current')}，最新 {update.get('latest')}"
    if identity == "user" and ("need_user_authorization" in message or error_type == "api_error"):
        return (
            "用户身份搜索飞书群需要先完成 lark-cli 用户授权。"
            "请在 API 服务运行环境执行：lark-cli auth login --scope \"im:chat:read\"，"
            "并用当前报错里的用户完成授权后再重试。"
            f"{update_hint}"
        )
    if message:
        return f"lark-cli 搜索飞书群失败：{message}{update_hint}"
    return f"lark-cli 搜索飞书群失败：{text[:800]}"


def _resolve_feishu_chat_by_name_with_lark_cli(chat_name: str, *, identity: str) -> dict[str, Any]:
    command = [
        "lark-cli",
        "im",
        "+chat-search",
        "--as",
        identity,
        "--query",
        chat_name,
        "--search-types",
        "private,public_joined",
        "--page-size",
        "20",
        "--format",
        "json",
        "--disable-search-by-user",
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
    except FileNotFoundError as exc:
        raise RuntimeError("未找到 lark-cli，请先安装 @larksuite/cli 并重新启动服务") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("lark-cli 搜索飞书群超时，请检查飞书授权或网络状态") from exc
    if completed.returncode != 0:
        output = (completed.stderr or completed.stdout or "").strip()[:800]
        raise RuntimeError(_format_lark_cli_chat_search_error(output, identity=identity))
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        output = (completed.stdout or "").strip()[:800]
        raise RuntimeError(f"lark-cli 搜索飞书群返回了非 JSON 内容：{output}") from exc
    items = [
        item
        for item in (_normalize_feishu_chat_search_item(raw) for raw in _extract_feishu_chat_search_items(payload) if isinstance(raw, dict))
        if item.get("chat_id")
    ]
    return _select_feishu_chat_search_candidate(items, chat_name, identity=identity)


def resolve_feishu_chat_by_name(connector: dict[str, Any], chat_name: str, *, identity: str = "bot") -> dict[str, Any]:
    query = str(chat_name or "").strip()
    if not query:
        raise RuntimeError("请先填写群名称")
    normalized_identity = _normalize_feishu_chat_resolve_identity(identity)
    if normalized_identity == "user":
        return _resolve_feishu_chat_by_name_with_lark_cli(query, identity=normalized_identity)
    token = _get_feishu_tenant_access_token(connector)
    response = requests.post(
        _feishu_open_api_url("/open-apis/im/v2/chats/search"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"},
        json={
            "query": query,
            "search_types": ["private", "public_joined"],
            "page_size": 20,
        },
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()
    if int(payload.get("code") or 0) != 0:
        raise RuntimeError(str(payload.get("msg") or "飞书群搜索失败"))
    items = [
        item
        for item in (_normalize_feishu_chat_search_item(raw) for raw in _extract_feishu_chat_search_items(payload) if isinstance(raw, dict))
        if item.get("chat_id")
    ]
    return _select_feishu_chat_search_candidate(items, query, identity=normalized_identity)


def build_feishu_event_handler(
    connector: dict[str, Any],
    *,
    loop: asyncio.AbstractEventLoop,
) -> "_lark_module.EventDispatcherHandler":
    _require_feishu_sdk()
    connector_id = str(connector.get("id") or "").strip()
    encrypt_key = str(connector.get("encrypt_key") or "").strip()
    verification_token = str(connector.get("verification_token") or "").strip()

    def _on_message(data: P2ImMessageReceiveV1) -> None:
        task = loop.create_task(process_feishu_message_event(connector_id, data))
        task.add_done_callback(_log_background_task)

    def _on_card_action(data: Any) -> Any:
        task = loop.create_task(process_feishu_card_action_event(connector_id, data))
        task.add_done_callback(_log_background_task)
        if P2CardActionTriggerResponse is None:
            return None
        return P2CardActionTriggerResponse()

    def _on_ignored_event(data: Any) -> None:
        event_type = str(getattr(getattr(data, "header", None), "event_type", "") or "").strip()
        logger.debug(
            "feishu long-connection event ignored",
            extra={"connector_id": connector_id, "event_type": event_type},
        )

    return (
        lark.EventDispatcherHandler.builder(encrypt_key, verification_token)
        .register_p2_im_message_receive_v1(_on_message)
        .register_p2_card_action_trigger(_on_card_action)
        .register_p2_customized_event("im.message.message_read_v1", _on_ignored_event)
        .build()
    )


def _log_background_task(task: asyncio.Task[Any]) -> None:
    try:
        task.result()
    except Exception:
        logger.exception("feishu bot background task failed")


def _project_chat_username(project: Any) -> str:
    created_by = str(getattr(project, "created_by", "") or "").strip()
    return created_by or "admin"


async def process_feishu_card_action_event(connector_id: str, data: Any) -> None:
    connector = get_feishu_connector(connector_id)
    if connector is None or not bool(connector.get("enabled", True)):
        return
    event = getattr(data, "event", None)
    action = getattr(event, "action", None)
    action_value = getattr(action, "value", None) or {}
    if not isinstance(action_value, dict):
        return
    if str(action_value.get("ai_employee_action") or "").strip() != "external_agent_permission":
        return
    logger.info(
        "feishu external agent approval action ignored because external agent feature is removed",
        extra={
            "connector_id": connector_id,
            "task_id": str(action_value.get("task_id") or "").strip(),
            "approval_id": str(action_value.get("approval_id") or "").strip(),
        },
    )


def _resolve_feishu_project_chat_session_id(
    *,
    connector_id: str,
    chat_type: str,
    chat_id: str,
    thread_id: str,
    sender_open_id: str,
) -> str:
    seed = "||".join(
        [
            "feishu",
            str(connector_id or "").strip(),
            str(chat_type or "").strip(),
            str(chat_id or "").strip(),
            str(thread_id or "").strip(),
            str(sender_open_id or "").strip() if str(chat_type or "").strip() == "p2p" else "",
        ]
    )
    return f"chat-session-bot-{hashlib.sha1(seed.encode('utf-8')).hexdigest()[:20]}"


def _feishu_chat_source_type(chat_type: str) -> str:
    return "private_message" if str(chat_type or "").strip().lower() == "p2p" else "group_message"


def _candidate_project_chat_usernames(project: Any, project_store: Any) -> list[str]:
    project_id = str(getattr(project, "id", "") or "").strip()
    usernames: list[str] = []
    seen: set[str] = set()

    def _add(value: Any) -> None:
        username = str(value or "").strip()
        if not username or username in seen:
            return
        seen.add(username)
        usernames.append(username)

    _add(getattr(project, "created_by", "") or "")
    try:
        user_members = project_store.list_user_members(project_id)
    except Exception:
        user_members = []
    for member in user_members:
        if not bool(getattr(member, "enabled", True)):
            continue
        _add(getattr(member, "username", "") or "")
    _add("admin")
    return usernames


def _is_feishu_chat_session_candidate(
    item: Any,
    *,
    connector_id: str,
    source_type: str,
) -> bool:
    return (
        str(getattr(item, "platform", "") or "").strip().lower() == "feishu"
        and str(getattr(item, "connector_id", "") or "").strip() == connector_id
        and str(getattr(item, "source_type", "") or "").strip() == source_type
    )


def _find_feishu_project_chat_session_binding(
    *,
    connector_id: str,
    chat_id: str,
    chat_type: str,
    projects_router: Any,
) -> tuple[str, str, str, dict[str, str]] | None:
    normalized_connector_id = str(connector_id or "").strip()
    normalized_chat_id = str(chat_id or "").strip()
    if not normalized_connector_id or not normalized_chat_id:
        return None

    source_type = _feishu_chat_source_type(chat_type)
    exact_matches: list[tuple[str, str, Any]] = []
    unresolved_matches: list[tuple[str, str, Any]] = []
    for project in projects_router.project_store.list_all():
        project_id = str(getattr(project, "id", "") or "").strip()
        if not project_id:
            continue
        for username in _candidate_project_chat_usernames(project, projects_router.project_store):
            try:
                sessions = projects_router.project_chat_store.list_sessions(project_id, username, limit=200)
            except Exception:
                logger.exception(
                    "failed to inspect project chat sessions for feishu routing",
                    extra={"project_id": project_id, "username": username, "connector_id": normalized_connector_id},
                )
                continue
            for item in sessions:
                if not _is_feishu_chat_session_candidate(
                    item,
                    connector_id=normalized_connector_id,
                    source_type=source_type,
                ):
                    continue
                external_chat_id = str(getattr(item, "external_chat_id", "") or "").strip()
                if external_chat_id == normalized_chat_id:
                    exact_matches.append((project_id, username, item))
                    continue
                external_chat_name = str(getattr(item, "external_chat_name", "") or "").strip()
                if not external_chat_id and external_chat_name:
                    unresolved_matches.append((project_id, username, item))

    if len(exact_matches) == 1:
        project_id, username, item = exact_matches[0]
        return (
            project_id,
            username,
            str(getattr(item, "id", "") or "").strip(),
            projects_router._project_chat_session_context(item),
        )
    if len(exact_matches) > 1:
        logger.warning(
            "feishu message ignored because chat binding is ambiguous",
            extra={
                "connector_id": normalized_connector_id,
                "chat_id": normalized_chat_id,
                "match_count": len(exact_matches),
            },
        )
        return None

    if len(unresolved_matches) != 1:
        if len(unresolved_matches) > 1:
            logger.warning(
                "feishu message ignored because unresolved chat binding is ambiguous",
                extra={
                    "connector_id": normalized_connector_id,
                    "chat_id": normalized_chat_id,
                    "match_count": len(unresolved_matches),
                },
            )
        return None

    project_id, username, manual_session = unresolved_matches[0]
    source_context = projects_router._normalize_project_chat_source_context(
        {
            "source_type": source_type,
            "platform": "feishu",
            "connector_id": normalized_connector_id,
            "external_chat_id": normalized_chat_id,
            "external_chat_name": str(getattr(manual_session, "external_chat_name", "") or "").strip(),
            "thread_key": "",
        },
        project_id=project_id,
        default_source_type=source_type,
    )
    updated = projects_router.project_chat_store.update_session(
        project_id,
        username,
        str(getattr(manual_session, "id", "") or "").strip(),
        source_context=source_context,
    )
    target = updated or manual_session
    return (
        project_id,
        username,
        str(getattr(target, "id", "") or "").strip(),
        projects_router._project_chat_session_context(target),
    )


def _find_or_bind_feishu_manual_chat_session(
    *,
    project_id: str,
    username: str,
    connector_id: str,
    chat_id: str,
    chat_type: str,
    projects_router: Any,
) -> tuple[str, dict[str, str]] | None:
    if not project_id or not username or not connector_id or not chat_id:
        return None
    sessions = projects_router.project_chat_store.list_sessions(
        project_id,
        username,
        limit=200,
    )
    group_source_type = _feishu_chat_source_type(chat_type)
    candidates = [
        item
        for item in sessions
        if str(getattr(item, "platform", "") or "").strip().lower() == "feishu"
        and str(getattr(item, "connector_id", "") or "").strip() == connector_id
        and str(getattr(item, "source_type", "") or "").strip() == group_source_type
    ]
    exact = next(
        (
            item
            for item in candidates
            if str(getattr(item, "external_chat_id", "") or "").strip() == chat_id
        ),
        None,
    )
    if exact is not None:
        return str(getattr(exact, "id", "") or "").strip(), projects_router._project_chat_session_context(exact)

    unresolved = [
        item
        for item in candidates
        if not str(getattr(item, "external_chat_id", "") or "").strip()
        and str(getattr(item, "external_chat_name", "") or "").strip()
    ]
    if len(unresolved) != 1:
        return None

    manual_session = unresolved[0]
    source_context = projects_router._normalize_project_chat_source_context(
        {
            "source_type": group_source_type,
            "platform": "feishu",
            "connector_id": connector_id,
            "external_chat_id": chat_id,
            "external_chat_name": str(getattr(manual_session, "external_chat_name", "") or "").strip(),
            "thread_key": "",
        },
        project_id=project_id,
        default_source_type=group_source_type,
    )
    updated = projects_router.project_chat_store.update_session(
        project_id,
        username,
        str(getattr(manual_session, "id", "") or "").strip(),
        source_context=source_context,
    )
    target = updated or manual_session
    return str(getattr(target, "id", "") or "").strip(), projects_router._project_chat_session_context(target)


def _fallback_feishu_chat_name(chat_id: str, chat_type: str) -> str:
    suffix = _safe_resource_token(str(chat_id or "").strip()[-8:] or "unknown")
    prefix = "飞书私聊" if str(chat_type or "").strip().lower() == "p2p" else "飞书群"
    return f"{prefix}-{suffix}"


def _resolve_feishu_chat_name_by_id(connector: dict[str, Any], chat_id: str) -> str:
    normalized_chat_id = str(chat_id or "").strip()
    if not normalized_chat_id:
        return ""
    try:
        token = _get_feishu_tenant_access_token(connector)
        response = requests.get(
            _feishu_open_api_url(f"/open-apis/im/v1/chats/{quote(normalized_chat_id, safe='')}"),
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception:
        logger.debug(
            "failed to resolve feishu chat name by id",
            extra={"chat_id": normalized_chat_id, "connector_id": str(connector.get("id") or "")},
            exc_info=True,
        )
        return ""
    if int(payload.get("code") or 0) != 0:
        return ""
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    return str(data.get("name") or data.get("chat_name") or "").strip()


def _connector_owner_auth_payload(owner_username: str, projects_router: Any) -> dict[str, Any]:
    username = str(owner_username or "").strip()
    if not username:
        return {"sub": "admin", "role": "admin", "roles": ["admin"]}
    try:
        user = projects_router.user_store.get(username)
    except Exception:
        user = None
    role_ids = list(getattr(user, "role_ids", []) or []) if user is not None else []
    role = str(getattr(user, "role", "") or "").strip() if user is not None else ""
    if role and role not in role_ids:
        role_ids.append(role)
    if not role_ids:
        role_ids = ["user"]
    return {"sub": username, "role": role_ids[0], "roles": role_ids}


def _resolve_feishu_fallback_project(connector: dict[str, Any], projects_router: Any) -> tuple[str, str] | None:
    owner_username = str(connector.get("owner_username") or connector.get("created_by") or "").strip()
    projects = [
        project
        for project in projects_router.project_store.list_all()
        if str(getattr(project, "id", "") or "").strip()
    ]
    if owner_username:
        auth_payload = _connector_owner_auth_payload(owner_username, projects_router)
        visible_projects = []
        for project in projects:
            project_id = str(getattr(project, "id", "") or "").strip()
            try:
                projects_router._ensure_project_access(project_id, auth_payload)
            except Exception:
                continue
            visible_projects.append(project)
        projects = visible_projects
    if not projects:
        logger.warning(
            "feishu message ignored because no runtime project is available",
            extra={
                "connector_id": str(connector.get("id") or "").strip(),
                "owner_username": owner_username,
            },
        )
        return None
    project = projects[0]
    project_id = str(getattr(project, "id", "") or "").strip()
    if len(projects) > 1:
        logger.info(
            "feishu connector has no project binding; using first available runtime project",
            extra={
                "connector_id": str(connector.get("id") or "").strip(),
                "project_id": project_id,
                "project_count": len(projects),
                "owner_username": owner_username,
            },
        )
    return project_id, owner_username or _project_chat_username(project)


def _create_feishu_fallback_chat_session(
    connector: dict[str, Any],
    *,
    connector_id: str,
    chat_id: str,
    chat_type: str,
    thread_id: str,
    sender_open_id: str,
    projects_router: Any,
) -> tuple[str, str, str, dict[str, str]] | None:
    resolved_project = _resolve_feishu_fallback_project(connector, projects_router)
    if resolved_project is None:
        return None
    project_id, username = resolved_project
    chat_name = _resolve_feishu_chat_name_by_id(connector, chat_id) or _fallback_feishu_chat_name(chat_id, chat_type)
    source_type = _feishu_chat_source_type(chat_type)
    source_context = projects_router._normalize_project_chat_source_context(
        {
            "source_type": source_type,
            "platform": "feishu",
            "connector_id": connector_id,
            "external_chat_id": chat_id,
            "external_chat_name": chat_name,
            "thread_key": "",
        },
        project_id=project_id,
        default_source_type=source_type,
    )
    chat_session_id = _resolve_feishu_project_chat_session_id(
        connector_id=connector_id,
        chat_type=chat_type,
        chat_id=chat_id,
        thread_id=thread_id,
        sender_open_id=sender_open_id,
    )
    title_prefix = "飞书私聊" if source_type == "private_message" else "飞书群"
    session = projects_router.project_chat_store.create_session(
        project_id,
        username,
        title=f"{title_prefix}：{chat_name}",
        source_context=source_context,
        session_id=chat_session_id,
    )
    return (
        project_id,
        username,
        str(getattr(session, "id", "") or "").strip(),
        projects_router._project_chat_session_context(session),
    )


def _parse_feishu_text_message(event: P2ImMessageReceiveV1) -> str:
    message = getattr(getattr(event, "event", None), "message", None)
    raw_content = str(getattr(message, "content", "") or "").strip()
    if not raw_content:
        return ""
    try:
        payload = json.loads(raw_content)
    except Exception:
        payload = {}
    message_type = str(getattr(message, "message_type", "") or "").strip().lower()
    text = str(payload.get("text") or "").strip()
    if not text and message_type == "post" and isinstance(payload, dict):
        text = _extract_feishu_post_text(payload)
    mentions = getattr(message, "mentions", None) or []
    text = _replace_feishu_mention_keys(text, mentions)
    text = _strip_leading_feishu_mentions(text, mentions)
    return " ".join(text.split())


def _replace_feishu_mention_keys(text: str, mentions: list[Any]) -> str:
    normalized = str(text or "")
    for item in mentions:
        mention_key = _value_from_obj_or_dict(item, "key")
        if mention_key:
            mention_name = _feishu_mention_display_name(item)
            replacement = f"@{mention_name}" if mention_name else " "
            normalized = normalized.replace(mention_key, replacement)
    return normalized


def _strip_leading_feishu_mentions(text: str, mentions: list[Any]) -> str:
    normalized = str(text or "").strip()
    if not normalized:
        return ""
    for item in mentions or []:
        if not _feishu_mention_identity_values(item):
            continue
        for name in _feishu_mention_name_candidates(item):
            pattern = re.compile(rf"^\s*@{re.escape(name)}[\s\xa0]*", re.IGNORECASE)
            updated = pattern.sub("", normalized, count=1).strip()
            if updated != normalized:
                normalized = updated
    return normalized


def _strip_leading_feishu_bot_mentions(text: str, connector: dict[str, Any]) -> str:
    normalized = str(text or "").strip()
    if not normalized:
        return ""
    runtime_identity = _get_feishu_runtime_bot_identity(connector)
    bot_names = {
        _normalize_feishu_mention_label(connector.get(key))
        for key in ("name", "bot_name")
        if _normalize_feishu_mention_label(connector.get(key))
    }
    runtime_bot_name = _normalize_feishu_mention_label(runtime_identity.get("bot_name"))
    if runtime_bot_name:
        bot_names.add(runtime_bot_name)
    for name in sorted(bot_names, key=len, reverse=True):
        if not name:
            continue
        pattern = re.compile(rf"^\s*@{re.escape(name)}[\s\xa0]*", re.IGNORECASE)
        updated = pattern.sub("", normalized, count=1).strip()
        if updated != normalized:
            return updated
    return normalized


def _feishu_mention_identity_values(item: Any) -> set[str]:
    id_obj = item.get("id") if isinstance(item, dict) else getattr(item, "id", None)
    values = {
        _value_from_obj_or_dict(item, "open_id"),
        _value_from_obj_or_dict(item, "user_id"),
        _value_from_obj_or_dict(item, "union_id"),
        _value_from_obj_or_dict(id_obj, "open_id"),
        _value_from_obj_or_dict(id_obj, "user_id"),
        _value_from_obj_or_dict(id_obj, "union_id"),
    }
    values.discard("")
    return values


def _value_from_obj_or_dict(value: Any, key: str) -> str:
    if isinstance(value, dict):
        return str(value.get(key) or "").strip()
    return str(getattr(value, key, "") or "").strip()


def _feishu_mention_display_name(item: Any) -> str:
    for key in ("name", "user_name", "display_name"):
        value = _value_from_obj_or_dict(item, key)
        if value:
            return value
    id_obj = item.get("id") if isinstance(item, dict) else getattr(item, "id", None)
    for key in ("name", "user_name", "display_name"):
        value = _value_from_obj_or_dict(id_obj, key)
        if value:
            return value
    return ""


def _normalize_feishu_mention_label(value: Any) -> str:
    return str(value or "").strip().lstrip("@").strip().lower()


def _collapse_feishu_mention_label(value: Any) -> str:
    return "".join(_normalize_feishu_mention_label(value).split())


def _feishu_mention_name_candidates(item: Any) -> set[str]:
    candidates: set[str] = set()
    for key in ("name", "user_name", "display_name"):
        value = _normalize_feishu_mention_label(_value_from_obj_or_dict(item, key))
        if value:
            candidates.add(value)
            collapsed = _collapse_feishu_mention_label(value)
            if collapsed:
                candidates.add(collapsed)
    id_obj = item.get("id") if isinstance(item, dict) else getattr(item, "id", None)
    for key in ("name", "user_name", "display_name"):
        value = _normalize_feishu_mention_label(_value_from_obj_or_dict(id_obj, key))
        if value:
            candidates.add(value)
            collapsed = _collapse_feishu_mention_label(value)
            if collapsed:
                candidates.add(collapsed)
    display_name = _normalize_feishu_mention_label(_feishu_mention_display_name(item))
    if display_name:
        candidates.add(display_name)
        collapsed = _collapse_feishu_mention_label(display_name)
        if collapsed:
            candidates.add(collapsed)
    return candidates


def _feishu_message_explicitly_mentions_target(message: Any, mention: Any) -> bool:
    mention_key = _value_from_obj_or_dict(mention, "key")
    message_type = str(getattr(message, "message_type", "") or "").strip().lower()
    payload = _parse_feishu_message_content(message)
    raw_text = str(payload.get("text") or "").strip()
    if mention_key and mention_key in raw_text:
        return True
    mention_names = _feishu_mention_name_candidates(mention)
    collapsed_text = "".join(str(raw_text or "").strip().lower().split())
    if mention_names and any(f"@{name}" in collapsed_text for name in mention_names):
        return True
    # Non-text messages do not carry a visible "@name" token in payload text.
    # If Feishu attached a resolved mention entity to the current message event,
    # treat it as an explicit mention for this message only.
    if message_type and message_type not in {"text", "post"}:
        return True
    if message_type != "post":
        return False
    mention_ids = _feishu_mention_identity_values(mention)
    if mention_ids:
        return True
    for node in _iter_feishu_post_nodes(payload.get("content")):
        tag = str(node.get("tag") or "").strip().lower()
        if tag != "at":
            continue
        node_ids = {
            str(node.get("user_id") or "").strip(),
            str(node.get("open_id") or "").strip(),
            str(node.get("union_id") or "").strip(),
        }
        node_ids.discard("")
        if mention_ids and node_ids.intersection(mention_ids):
            return True
    return False


def _feishu_message_has_explicit_mention_entity(message: Any) -> bool:
    mentions = getattr(message, "mentions", None) or []
    if not mentions:
        return False
    payload = _parse_feishu_message_content(message)
    raw_text = str(payload.get("text") or "").strip()
    for mention in mentions:
        mention_key = _value_from_obj_or_dict(mention, "key")
        if mention_key and mention_key in raw_text:
            return True
        if _feishu_mention_identity_values(mention):
            return True
        mention_names = _feishu_mention_name_candidates(mention)
        collapsed_text = "".join(str(raw_text or "").strip().lower().split())
        if mention_names and any(f"@{name}" in collapsed_text for name in mention_names):
            return True
    return False


def _feishu_group_message_mentions_bot(message: Any, connector: dict[str, Any]) -> bool:
    mentions = getattr(message, "mentions", None) or []
    if not mentions:
        return False
    runtime_identity = _get_feishu_runtime_bot_identity(connector)
    bot_ids = {
        str(connector.get(key) or "").strip()
        for key in ("bot_open_id", "bot_user_id", "bot_union_id")
        if str(connector.get(key) or "").strip()
    }
    runtime_bot_open_id = str(runtime_identity.get("bot_open_id") or "").strip()
    if runtime_bot_open_id:
        bot_ids.add(runtime_bot_open_id)
    bot_names = {
        _normalize_feishu_mention_label(connector.get(key))
        for key in ("name", "bot_name")
        if _normalize_feishu_mention_label(connector.get(key))
    }
    runtime_bot_name = _normalize_feishu_mention_label(runtime_identity.get("bot_name"))
    if runtime_bot_name:
        bot_names.add(runtime_bot_name)
    for item in mentions:
        mention_ids = _feishu_mention_identity_values(item)
        mention_names = _feishu_mention_name_candidates(item)
        if (
            (
                (bot_ids and bot_ids.intersection(mention_ids))
                or (bot_names and bot_names.intersection(mention_names))
            )
            and _feishu_message_explicitly_mentions_target(message, item)
        ):
            return True
    if any(
        not _feishu_mention_identity_values(item)
        and not _feishu_mention_name_candidates(item)
        and _value_from_obj_or_dict(item, "key")
        for item in mentions
    ):
        return _feishu_message_has_explicit_mention_entity(message)
    return False


def _should_process_feishu_group_text_message(
    *,
    connector: dict[str, Any],
    message: Any,
    chat_type: str,
    thread_id: str,
    text_message: str,
    resources: list[dict[str, str]],
) -> bool:
    if str(chat_type or "").strip().lower() == "p2p":
        return True
    if _feishu_group_message_mentions_bot(message, connector):
        return True
    return False


def _assistant_workflow_is_open(state: dict[str, Any] | None) -> bool:
    workflow = dict(state or {})
    status = str(workflow.get("status") or "").strip().lower()
    if not status:
        return False
    return status not in {"done", "failed", "cancelled", "ignored", "closed", "completed"}


def _should_continue_feishu_group_workflow_with_resources(
    *,
    previous_messages: list[Any],
    sender_open_id: str,
    resources: list[dict[str, str]],
) -> bool:
    if not resources:
        return False
    normalized_sender_id = str(sender_open_id or "").strip()
    if not normalized_sender_id:
        return False
    last_user_message = None
    last_assistant_message = None
    for item in reversed(previous_messages):
        role = str(getattr(item, "role", "") or "").strip().lower()
        if role == "assistant" and last_assistant_message is None:
            last_assistant_message = item
            continue
        if role == "user":
            item_context = getattr(item, "source_context", None)
            if not isinstance(item_context, dict):
                item_context = {}
            if str(item_context.get("sender_id") or "").strip() == normalized_sender_id:
                last_user_message = item
                break
    if last_user_message is None or last_assistant_message is None:
        return False
    assistant_workflow = assistant_workflow_from_context(getattr(last_assistant_message, "source_context", None))
    archive_status = _archive_workflow_status(getattr(last_assistant_message, "source_context", None))
    if archive_status in {"pending_confirmation", "pending_write", "pending_retry", "pending_attachment"}:
        return True
    if _assistant_workflow_is_open(assistant_workflow):
        return True
    return False


def _feishu_history_from_messages(messages: list[Any]) -> list[dict[str, str]]:
    history: list[dict[str, str]] = []
    for item in messages:
        role = str(getattr(item, "role", "") or "").strip().lower()
        content = str(getattr(item, "content", "") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        history.append({"role": role, "content": content})
    return history


def _recent_feishu_image_urls(messages: list[Any], source_context: dict[str, Any], *, limit: int = 6) -> list[str]:
    connector_id = str(source_context.get("connector_id") or "").strip()
    external_chat_id = str(source_context.get("external_chat_id") or "").strip()
    thread_key = str(source_context.get("thread_key") or "").strip()
    urls: list[str] = []
    for item in reversed(messages):
        if len(urls) >= limit:
            break
        if str(getattr(item, "role", "") or "").strip().lower() != "user":
            continue
        if connector_id and str(getattr(item, "connector_id", "") or "").strip() != connector_id:
            continue
        if external_chat_id and str(getattr(item, "external_chat_id", "") or "").strip() != external_chat_id:
            continue
        if thread_key and str(getattr(item, "thread_key", "") or "").strip() != thread_key:
            continue
        for url in reversed(getattr(item, "images", None) or []):
            normalized = str(url or "").strip()
            if normalized and normalized not in urls:
                urls.append(normalized)
    return list(reversed(urls))


def _recent_feishu_message_resource_refs(
    messages: list[Any],
    source_context: dict[str, Any],
    *,
    limit: int = 8,
) -> list[dict[str, str]]:
    connector_id = str(source_context.get("connector_id") or "").strip()
    external_chat_id = str(source_context.get("external_chat_id") or "").strip()
    thread_key = str(source_context.get("thread_key") or "").strip()
    refs: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in reversed(messages):
        if len(refs) >= limit:
            break
        if str(getattr(item, "role", "") or "").strip().lower() != "user":
            continue
        if connector_id and str(getattr(item, "connector_id", "") or "").strip() != connector_id:
            continue
        if external_chat_id and str(getattr(item, "external_chat_id", "") or "").strip() != external_chat_id:
            continue
        if thread_key and str(getattr(item, "thread_key", "") or "").strip() != thread_key:
            continue
        item_context = getattr(item, "source_context", None)
        if not isinstance(item_context, dict):
            item_context = {}
        message_id = str(
            item_context.get("external_message_id")
            or getattr(item, "external_message_id", "")
            or ""
        ).strip()
        for resource in reversed(item_context.get("message_resources") if isinstance(item_context.get("message_resources"), list) else []):
            if not isinstance(resource, dict):
                continue
            file_key = str(resource.get("file_key") or "").strip()
            resource_type = str(resource.get("type") or "file").strip().lower() or "file"
            if not message_id or not file_key:
                continue
            key = (message_id, file_key, resource_type)
            if key in seen:
                continue
            seen.add(key)
            refs.append(
                {
                    "message_id": message_id,
                    "file_key": file_key,
                    "type": resource_type,
                    "label": str(resource.get("label") or "").strip(),
                }
            )
    return list(reversed(refs))


def _feishu_resource_type_from_key(file_key: str) -> str:
    return "image" if str(file_key or "").strip().lower().startswith(("img", "image")) else "file"


def _append_feishu_resource_ref_from_text(
    refs: list[dict[str, str]],
    seen: set[tuple[str, str]],
    *,
    message_id: str,
    file_key: str,
) -> None:
    normalized_message_id = str(message_id or "").strip()
    normalized_file_key = str(file_key or "").strip()
    if not normalized_message_id or not normalized_file_key:
        return
    key = (normalized_message_id, normalized_file_key)
    if key in seen:
        return
    seen.add(key)
    resource_type = _feishu_resource_type_from_key(normalized_file_key)
    refs.append(
        {
            "message_id": normalized_message_id,
            "file_key": normalized_file_key,
            "type": resource_type,
            "label": "图片" if resource_type == "image" else "附件",
        }
    )


def _extract_feishu_resource_refs_from_text(text: str) -> list[dict[str, str]]:
    value = str(text or "")
    if not value.strip():
        return []
    message_pattern = re.compile(
        r"(?:消息\s*ID|message[_\s-]*id)\s*[：:]\s*`?(om[_A-Za-z0-9-]+)`?",
        re.I,
    )
    file_key_pattern = re.compile(
        r"(?:图片\s*(?:key|资源标识)|附件\s*(?:key|资源标识)|file[_\s-]*key|image[_\s-]*key)\s*[：:]\s*`?([A-Za-z0-9][A-Za-z0-9_.-]{6,})`?",
        re.I,
    )
    refs: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    current_message_id = ""
    for raw_line in value.splitlines():
        line = str(raw_line or "").strip()
        if not line:
            current_message_id = ""
            continue
        message_matches = list(message_pattern.finditer(line))
        file_matches = list(file_key_pattern.finditer(line))
        if message_matches and not file_matches:
            current_message_id = str(message_matches[-1].group(1) or "").strip()
            continue
        if not file_matches:
            if re.match(r"^【.+】$", line):
                current_message_id = ""
            continue
        for file_match in file_matches:
            file_key = str(file_match.group(1) or "").strip()
            same_line_message_id = ""
            if message_matches:
                preceding = [item for item in message_matches if item.start() <= file_match.start()]
                same_line_message_id = str((preceding[-1] if preceding else message_matches[0]).group(1) or "").strip()
            _append_feishu_resource_ref_from_text(
                refs,
                seen,
                message_id=same_line_message_id or current_message_id,
                file_key=file_key,
            )
        if message_matches:
            current_message_id = str(message_matches[-1].group(1) or "").strip()
    return refs


def _recent_feishu_message_resource_refs_from_text(
    messages: list[Any],
    source_context: dict[str, Any],
    *,
    limit: int = 8,
) -> list[dict[str, str]]:
    connector_id = str(source_context.get("connector_id") or "").strip()
    external_chat_id = str(source_context.get("external_chat_id") or "").strip()
    thread_key = str(source_context.get("thread_key") or "").strip()
    refs: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in reversed(messages):
        if len(refs) >= limit:
            break
        if connector_id and str(getattr(item, "connector_id", "") or "").strip() not in {"", connector_id}:
            continue
        if external_chat_id and str(getattr(item, "external_chat_id", "") or "").strip() not in {"", external_chat_id}:
            continue
        item_thread_key = str(getattr(item, "thread_key", "") or "").strip()
        if (
            thread_key
            and item_thread_key not in {"", thread_key}
            and not external_chat_id
        ):
            continue
        for ref in reversed(_extract_feishu_resource_refs_from_text(str(getattr(item, "content", "") or ""))):
            key = (
                str(ref.get("message_id") or "").strip(),
                str(ref.get("file_key") or "").strip(),
                str(ref.get("type") or "").strip(),
            )
            if not key[0] or not key[1] or key in seen:
                continue
            seen.add(key)
            refs.append(ref)
    return list(reversed(refs))


async def _redownload_feishu_message_resources(
    connector: dict[str, Any],
    *,
    connector_id: str,
    resource_refs: list[dict[str, str]],
    download_errors: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    restored: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for ref in resource_refs:
        if not isinstance(ref, dict):
            continue
        resource_connector_id = str(ref.get("connector_id") or connector_id).strip()
        if resource_connector_id != connector_id:
            continue
        key = (
            resource_connector_id,
            str(ref.get("message_id") or "").strip(),
            str(ref.get("file_key") or "").strip(),
        )
        if not all(key) or key in seen:
            continue
        seen.add(key)
        try:
            downloaded = await asyncio.to_thread(
                _download_feishu_message_resource,
                connector,
                connector_id=resource_connector_id,
                message_id=key[1],
                file_key=key[2],
                resource_type=str(ref.get("type") or "file"),
            )
        except Exception as exc:
            error = {
                "connector_id": connector_id,
                "message_id": key[1],
                "file_key": key[2],
                "type": str(ref.get("type") or "file"),
                "message": str(exc),
            }
            if download_errors is not None:
                download_errors.append(error)
            logger.info(
                "failed to redownload recent feishu message resource",
                exc_info=True,
                extra=_sanitize_log_extra(error),
            )
            continue
        if downloaded:
            restored.append(downloaded)
    return restored


async def _redownload_recent_feishu_image_resources(
    connector: dict[str, Any],
    *,
    connector_id: str,
    image_urls: list[str],
) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for image_url in image_urls:
        ref = _parse_feishu_resource_url(image_url)
        if not ref:
            continue
        refs.append(ref)
    return await _redownload_feishu_message_resources(
        connector,
        connector_id=connector_id,
        resource_refs=refs,
    )


def _merge_source_image_urls(source_context: dict[str, Any], image_urls: list[str]) -> dict[str, Any]:
    existing = source_context.get("image_urls")
    if isinstance(existing, list):
        existing_urls = existing
    elif str(existing or "").strip():
        existing_urls = [str(existing).strip()]
    else:
        existing_urls = []
    urls = [
        str(item or "").strip()
        for item in [*existing_urls, *image_urls]
        if str(item or "").strip()
    ]
    if not urls:
        return source_context
    seen: set[str] = set()
    deduped = []
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        deduped.append(url)
    source_context["image_urls"] = deduped
    return source_context


def _merge_source_attachment_files(source_context: dict[str, Any], attachment_files: list[dict[str, str]]) -> dict[str, Any]:
    existing = source_context.get("attachment_files")
    existing_items = existing if isinstance(existing, list) else []
    merged: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in [*existing_items, *attachment_files]:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        url = str(item.get("url") or "").strip()
        key = path or url
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(item)
    if merged:
        source_context["attachment_files"] = merged
    return source_context


def _merge_source_message_resources(source_context: dict[str, Any], resources: list[dict[str, str]]) -> dict[str, Any]:
    existing = source_context.get("message_resources")
    existing_items = existing if isinstance(existing, list) else []
    merged: list[dict[str, str]] = []
    default_message_id = str(source_context.get("external_message_id") or source_context.get("message_id") or "").strip()
    seen: set[tuple[str, str, str]] = set()
    for item in [*existing_items, *resources]:
        if not isinstance(item, dict):
            continue
        file_key = str(item.get("file_key") or "").strip()
        resource_type = str(item.get("type") or "file").strip().lower() or "file"
        message_id = str(item.get("message_id") or item.get("external_message_id") or default_message_id).strip()
        if not file_key:
            continue
        key = (message_id, resource_type, file_key)
        if key in seen:
            continue
        seen.add(key)
        normalized = {
            "file_key": file_key,
            "type": resource_type,
            "label": str(item.get("label") or "").strip(),
        }
        if message_id:
            normalized["message_id"] = message_id
        merged.append(normalized)
    if merged:
        source_context["message_resources"] = merged
    return source_context


def _compact_speech_text(value: str, *, max_length: int = 80) -> str:
    text = re.sub(r"@[_a-zA-Z0-9一-鿿.-]+", " ", str(value or ""))
    text = " ".join(text.split()).strip(" ，。；;、")
    if len(text) > max_length:
        return f"{text[: max_length - 1].rstrip()}…"
    return text


def _matched_task_requests_system_speech(task: dict[str, Any]) -> bool:
    actions = task.get("actions") if isinstance(task.get("actions"), list) else []
    for action in actions:
        if not isinstance(action, dict) or not bool(action.get("enabled", True)):
            continue
        action_type = str(action.get("type") or "").strip().lower()
        if action_type in {"system_speech", "notify"}:
            return True
    text = " ".join([str(task.get("title") or ""), str(task.get("description") or "")])
    return any(term in text for term in ("提醒", "提示", "通知", "播报", "语音", "声音"))


def _build_feishu_task_listener_speech_text(
    *,
    message_text: str,
    matched_tasks: list[dict[str, Any]],
    source_context: dict[str, Any],
) -> str:
    if not any(_matched_task_requests_system_speech(task) for task in matched_tasks):
        return ""
    source_name = str(source_context.get("external_chat_name") or "").strip()
    source_label = f"飞书群 {source_name}" if source_name else "飞书群"
    message_preview = _compact_speech_text(message_text, max_length=72)
    if message_preview:
        return f"{source_label}有新事项：{message_preview}。机器人已回复，请查看。"
    return f"{source_label}有新事项，机器人已回复，请查看。"


def _build_feishu_meeting_reminder_reply(result: dict[str, Any] | None) -> str:
    payload = result if isinstance(result, dict) else {}
    status = str(payload.get("status") or "").strip()
    if status == "created":
        return str(payload.get("message") or "").strip() or "已创建会议提醒，到点会通知本群。"
    if status == "ambiguous":
        return str(payload.get("message") or "").strip() or "要创建会议提醒还缺少具体时间，请补充日期和时间。"
    return ""


def _build_feishu_archive_truth_prompt(connector: dict[str, Any], source_context: dict[str, Any]) -> str:
    bot_name = str(connector.get("name") or "当前机器人").strip() or "当前机器人"
    group_name = str(source_context.get("external_chat_name") or source_context.get("group_name") or "当前飞书群").strip() or "当前飞书群"
    return (
        "飞书归档真实性约束："
        f"当前执行主体是“{bot_name}”，不是泛指每个机器人；归档范围必须绑定到当前飞书群“{group_name}”。"
        "分类归档资源应按当前群 + 当前机器人 + 分类维护，不能写到无群归属的全局资源。"
        "当用户确认记录或结构化内容已完整时，应进入系统归档链路；不要因为未找到现有资源而停止，"
        "应根据用户目标、机器人提示词、任务动作配置和历史上下文选择普通文档、电子表格、多维表格或任务系统，目标资源不存在时按已选择类型创建后再写入。"
        "识别归档内容时必须结合当前群上下文和最近多轮对话，不要只看最后一句。"
        "如果消息中提到图片或附件但系统没有提供可访问链接，应在结构化内容中标记图片/附件待补充，不能编造链接。"
        "如果用户用“追加、补充、放到刚才那条、加到这个记录里”等自然语言表达要处理最近图片，"
        "应结合系统提供的最近图片/附件资源继续处理，不要机械要求用户重发。"
        "除非系统工具已经明确返回创建或写入目标资源成功，否则禁止回复“已归档”“已保存”“已写入”“保存到”。"
        "如果只是识别并整理了字段，只能回复“已整理为待归档记录”，并说明尚未写入目标资源。"
    )


def _normalize_feishu_reply_identity(connector: dict[str, Any]) -> str:
    value = str(connector.get("reply_identity") or "bot").strip().lower()
    return value if value in {"bot", "user"} else "bot"


def _repo_root_from_service() -> Path:
    return Path(__file__).resolve().parents[4]


def _resolve_feishu_skill_resource_directory(project_id: str, projects_router: Any) -> str:
    workspace_path = ""
    try:
        project = projects_router.project_store.get(project_id)
        workspace_path = str(getattr(project, "workspace_path", "") or "").strip()
    except Exception:
        workspace_path = ""
    roots = []
    if workspace_path:
        roots.append(Path(workspace_path) / "skills")
    repo_root = _repo_root_from_service()
    roots.extend([repo_root / "skills", repo_root / ".ai-employee" / "skills" / "host-marketplace"])
    for root in roots:
        if root.exists():
            return str(root)
    return ""


def _build_feishu_agent_workflow_prompt(
    connector: dict[str, Any],
    source_context: dict[str, Any],
    *,
    skill_resource_directory: str,
) -> str:
    identity = _normalize_feishu_reply_identity(connector)
    identity_label = "当前登录用户 user identity" if identity == "user" else "机器人 bot identity"
    source_type = str(source_context.get("source_type") or "").strip()
    conversation_scope = (
        "当前是飞书私聊用户对话；按当前用户与当前机器人的一对一上下文连续处理。"
        if source_type == "private_message"
        else "当前是飞书群聊；按当前群、当前机器人和当前消息线程的上下文连续处理。"
    )
    skill_hint = (
        f"本地 lark-cli 技能目录：{skill_resource_directory}。"
        if skill_resource_directory
        else "如果可访问本地 skills/lark-* 目录，先读取相关 SKILL.md。"
    )
    workspace_path = str(source_context.get("workspace_path") or "").strip()
    workspace_hint = f"当前项目本地工作区：{workspace_path}。" if workspace_path else ""
    return (
        "飞书机器人通用工作流约束："
        "长连接收到消息后，不按单个任务写死分支处理；先由大模型结合当前机器人提示词、项目上下文、飞书来源上下文、历史消息、"
        "本地环境和系统提供的工具技能理解用户意图，再决定是直接回复、追问澄清、生成项目任务、写普通文档、写电子表格、写多维表格、"
        "发送消息、调用项目工具，还是通过 lark-cli 操作飞书资源。"
        f"{conversation_scope}"
        f"{workspace_hint}"
        f"{skill_hint}"
        "凡涉及飞书命令、消息、文档、表格、多维表格、日历、任务等操作，应先从本地技能目录选择对应 lark-* 技能并读取 SKILL.md；"
        "如果本地没有合适技能，再通过可用的项目工具或搜索/技能安装能力查找并安装合适技能，然后继续执行。"
        "执行时优先使用系统提供的工具能力；可用 `project_host_run_command` 时，通过它读取本地环境、列出技能、运行 lark-cli 或安装缺失技能，"
        "不要臆造 API 参数，也不要把口头教程当成已经执行。"
        "当用户询问你是谁、是什么智能体或是否在线时，只按用户可见身份回答：你是当前飞书里的项目机器人/AI 助手；"
        "不要暴露或强调 Hermes、Codex、Claude Code、桌面 Runner、API 服务、内部队列、桥接实现或运行环境名称。"
        "停止处理的条件只有两类：一是工具返回结果已经满足用户本次需求；二是确实缺少可继续执行的环境、权限、授权、必要输入、"
        "可访问附件/文件，或已触发工具预算/轮次保护。除此之外，只要下一步清晰且工具可用，就继续调用工具执行。"
        "不要把“下一步最小操作”“请稍后回复重新执行”“暂时未能完成写入”作为最终回复；这类内容只能作为内部状态，"
        "如果能继续执行必须继续执行，不能让用户重复回复同一句话来驱动本应自动完成的步骤。"
        "你只生成需要回到飞书的最终回复内容；不要在模型执行过程中自行调用 lark-cli im +messages-reply 或 +messages-send 发送最终回复，"
        f"最终回复由系统统一发送，当前配置发送身份为：{identity_label}；bot 身份走飞书 OpenAPI，user 身份走 lark-cli。"
        "如果要执行写入、发送外部通知、删除、部署或其他高风险操作，必须输出待确认方案或草稿，不得直接越权执行。"
        "如果用户已经回复确认发送、确认记录、确认归档、确认发送并记录或继续，应把它视为对上一条待确认方案的确认，继续完成发送/写入，不要再次要求用户确认。"
        "不要把“记录 bug/需求/功能/会议”固定理解为多维表格；应根据用户明确目标、机器人提示词、任务动作配置和历史上下文选择普通文档、电子表格、多维表格或任务系统。"
        "如果目标资源不存在，应按已选择的资源类型创建对应资源后继续写入；若目标类型仍不明确，应先给出简短澄清或待确认方案。"
        "系统可能会在 source_context.attachment_files / image_urls / message_resources 中提供当前或最近飞书图片、文件、音频、视频资源；"
        "如果用户自然语言要求处理最近资源，应优先使用这些资源。attachment_files 是已下载到本地的源文件；"
        "message_resources 保留 message_id/file_key/type，当缺少本地源文件时，应读取 lark-im 技能并通过飞书 IM 资源下载能力获取源文件后继续处理。"
        f"当前飞书来源：connector_id={source_context.get('connector_id') or '-'}，"
        f"chat_id={source_context.get('external_chat_id') or '-'}，"
        f"chat_name={source_context.get('external_chat_name') or '-'}，"
        f"message_id={source_context.get('external_message_id') or '-'}。"
    )


def _task_uses_auto_archive_workflow(task: dict[str, Any]) -> bool:
    for action in task.get("actions") or []:
        if not isinstance(action, dict):
            continue
        if is_feishu_auto_archive_action(action):
            return True
    return False


def _is_auto_archive_project_chat_action(action: dict[str, Any]) -> bool:
    return (
        str(action.get("type") or "record").strip() == "project_chat"
        and is_feishu_auto_archive_action(action)
    )


def _task_archive_write_succeeded(task: dict[str, Any]) -> bool:
    execution = task.get("latest_execution") if isinstance(task.get("latest_execution"), dict) else {}
    for result in execution.get("action_results") or []:
        if not isinstance(result, dict):
            continue
        if str(result.get("action_type") or "").strip() != "project_chat":
            continue
        status = str(result.get("status") or "").strip().lower()
        archive_marker = any(
            str(result.get(key) or "").strip()
            for key in (
                "archive_key",
                "document_title",
                "doc_id",
                "document_id",
                "doc_url",
                "sheet_id",
                "table_id",
                "record_id",
            )
        )
        if archive_marker and status in {"completed", "success", "succeeded", "saved", "archived", "written"}:
            return True
    return False


def _reply_claims_archive_success(content: str) -> bool:
    return _shared_reply_claims_archive_success(content)


def _reply_has_legacy_closed_archive_state(content: str) -> bool:
    return _reply_claims_archive_success(content)


def _latest_pending_archive_message(messages: list[Any], source_context: dict[str, Any]) -> Any | None:
    connector_id = str(source_context.get("connector_id") or "").strip()
    external_chat_id = str(source_context.get("external_chat_id") or "").strip()
    thread_key = str(source_context.get("thread_key") or "").strip()
    for item in reversed(messages):
        if str(getattr(item, "role", "") or "").strip().lower() != "assistant":
            continue
        if connector_id and str(getattr(item, "connector_id", "") or "").strip() not in {"", connector_id}:
            continue
        if external_chat_id and str(getattr(item, "external_chat_id", "") or "").strip() not in {"", external_chat_id}:
            continue
        if thread_key and str(getattr(item, "thread_key", "") or "").strip() not in {"", thread_key}:
            continue
        content = _archive_message_reply_content(item)
        if _message_has_closed_archive_state(item) or _reply_has_legacy_closed_archive_state(content):
            return None
        if _message_has_pending_archive_state(item) or _reply_contains_structured_pending_archive(content):
            return item
    return None


def _reply_contains_structured_pending_archive(content: str) -> bool:
    text = str(content or "")
    if _shared_reply_contains_structured_pending_archive(text):
        return True
    return _reply_contains_direct_bitable_pending_archive(text) or _reply_contains_direct_bitable_attachment_pending(text)


def _reply_contains_direct_bitable_pending_archive(content: str) -> bool:
    text = str(content or "")
    if not text.strip():
        return False
    has_target = bool(
        re.search(r"(?:Base\s*Token|Base|base_token|app_token)\s*[：:]\s*`?[A-Za-z0-9_-]{8,}`?", text, re.I)
        and re.search(r"(?:Table\s*ID|表\s*ID|表ID|数据表|table_id)\s*[：:]\s*`?tbl[A-Za-z0-9_-]+`?", text, re.I)
    )
    if not has_target:
        return False
    has_pending_state = any(
        marker in text
        for marker in (
            "尚未追加",
            "尚未写入",
            "尚未保存",
            "未完成保存",
            "未完成写入",
            "没有收到",
            "待写入",
            "待追加",
            "待保存",
            "已整理，尚未",
        )
    )
    has_record_payload = any(
        marker in text
        for marker in (
            "【待写入内容】",
            "【待追加记录】",
            "【结构化内容】",
            "待写入内容",
            "待追加记录",
            "结构化内容",
        )
    )
    return has_pending_state and has_record_payload


def _matched_tasks_have_archive_success(matched_tasks: list[dict[str, Any]]) -> bool:
    return any(_task_archive_write_succeeded(task) for task in matched_tasks)


def _extract_labeled_token(text: str, labels: tuple[str, ...], pattern: str) -> str:
    label_pattern = "|".join(re.escape(label) for label in labels if label)
    if not label_pattern:
        return ""
    match = re.search(rf"(?:{label_pattern})\s*[：:]\s*`?\s*({pattern})\s*`?", str(text or ""), re.I)
    return str(match.group(1) or "").strip() if match else ""


def _reply_contains_direct_bitable_attachment_pending(content: str) -> bool:
    text = str(content or "")
    if not text.strip():
        return False
    context = _extract_direct_bitable_attachment_context(text, require_detection=False)
    if not all(context.get(key) for key in ("base_token", "table_id", "record_id")):
        return False
    if not context.get("attachment_files"):
        return False
    operation_text = re.search(r"(?:附件|图片|文件).{0,30}(?:上传|写入|追加|补写|更新|替换)", text)
    next_step_text = "下一步" in text or "最小操作" in text or "继续" in text or "重新执行" in text
    incomplete_text = any(marker in text for marker in ("还没有成功写入", "未能完成写入", "没有成功写入", "还没有成功", "已部分完成"))
    return bool(operation_text or (next_step_text and incomplete_text))


def _extract_direct_bitable_attachment_context(content: str, *, require_detection: bool = True) -> dict[str, Any]:
    text = str(content or "")
    if require_detection and not _reply_contains_direct_bitable_attachment_pending(text):
        return {}
    base_token = _extract_labeled_token(
        text,
        ("Base Token", "Base", "base_token", "app_token"),
        r"[A-Za-z0-9_-]{8,}",
    )
    table_id = _extract_labeled_token(
        text,
        ("Table ID", "表 ID", "表ID", "数据表", "table_id"),
        r"tbl[A-Za-z0-9_-]+",
    )
    record_id = _extract_labeled_token(
        text,
        ("Record ID", "记录 ID", "记录ID", "record_id"),
        r"rec[A-Za-z0-9_-]+",
    )
    if not table_id:
        table_id = _first_regex_group(text, r"\b(tbl[A-Za-z0-9_-]+)\b")
    if not record_id:
        record_id = _first_regex_group(text, r"\b(rec[A-Za-z0-9_-]+)\b")
    field_id = _first_regex_group(text, r"(?:附件|图片|文件)?\s*/\s*(fld[A-Za-z0-9_-]+)")
    field_name = ""
    field_match = re.search(r"`\s*([^`\n/：:]{1,40})\s*/\s*(fld[A-Za-z0-9_-]+)\s*`", text)
    if field_match:
        field_name = str(field_match.group(1) or "").strip()
        field_id = str(field_match.group(2) or "").strip()
    if not field_name:
        field_name = _extract_labeled_token(
            text,
            ("附件字段", "图片字段", "文件字段", "字段"),
            r"(?:fld[A-Za-z0-9_-]+|[^`\n，,。；;]{1,40})",
        )
    attachment_field = field_id or field_name or "附件"
    document_title = _extract_direct_bitable_attachment_title(text)
    execution_dir = _extract_direct_bitable_execution_dir(text)
    attachment_files = _extract_pending_local_attachment_files(text, execution_dir=execution_dir)
    return {
        "base_token": base_token,
        "table_id": table_id,
        "record_id": record_id,
        "attachment_field": attachment_field,
        "attachment_field_name": field_name,
        "attachment_field_id": field_id,
        "attachment_files": attachment_files,
        "document_title": document_title,
        "execution_dir": execution_dir,
    }


def _first_regex_group(text: str, pattern: str) -> str:
    match = re.search(pattern, str(text or ""), re.I)
    return str(match.group(1) or "").strip() if match else ""


def _extract_direct_bitable_attachment_title(text: str) -> str:
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        match = re.match(r"^[-*]?\s*(?:保存位置|文档|多维表格|目标文档|目标多维表格|名称)\s*[：:]\s*`?(.+?)`?\s*$", line)
        if not match:
            continue
        value = str(match.group(1) or "").strip().strip("`")
        if value and not value.startswith(("Base", "Table", "BITABLE")):
            return value
    return ""


def _extract_direct_bitable_execution_dir(text: str) -> str:
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        match = re.match(r"^[-*]?\s*(?:本轮执行目录|执行目录|工作目录|cwd)\s*[：:]\s*`?(.+?)`?\s*$", line, re.I)
        if match:
            return str(match.group(1) or "").strip().strip("`")
    return ""


def _extract_pending_local_attachment_files(text: str, *, execution_dir: str = "") -> list[dict[str, str]]:
    candidates: list[str] = []
    for match in re.finditer(r"`([^`\n]+)`", str(text or "")):
        value = str(match.group(1) or "").strip()
        if _looks_like_local_attachment_path(value):
            candidates.append(value)
    for match in re.finditer(r"(?<![\w:/.-])((?:\.{0,2}/)?[\w\u4e00-\u9fff ./-]+\.[A-Za-z0-9]{2,8})(?![\w/.-])", str(text or "")):
        value = str(match.group(1) or "").strip()
        if _looks_like_local_attachment_path(value):
            candidates.append(value)
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for candidate in candidates:
        path = _resolve_pending_local_attachment_path(candidate, execution_dir=execution_dir)
        if not path or path in seen:
            continue
        seen.add(path)
        normalized.append({"path": path, "filename": Path(path).name})
    return normalized


def _looks_like_local_attachment_path(value: str) -> bool:
    path = str(value or "").strip()
    if not path or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", path):
        return False
    suffix = Path(path).suffix.lower()
    return suffix in {
        ".apng",
        ".avif",
        ".bmp",
        ".csv",
        ".doc",
        ".docx",
        ".gif",
        ".heic",
        ".heif",
        ".jpeg",
        ".jpg",
        ".json",
        ".md",
        ".pdf",
        ".png",
        ".ppt",
        ".pptx",
        ".svg",
        ".txt",
        ".webp",
        ".xls",
        ".xlsx",
        ".zip",
    }


def _resolve_pending_local_attachment_path(value: str, *, execution_dir: str = "") -> str:
    raw_path = Path(str(value or "").strip()).expanduser()
    candidates: list[Path] = []
    if raw_path.is_absolute():
        candidates.append(raw_path)
    else:
        if execution_dir:
            candidates.append(Path(execution_dir).expanduser() / raw_path)
        cwd = Path.cwd()
        candidates.extend([cwd / raw_path, cwd.parent / raw_path, cwd.parent.parent / raw_path])
    for candidate in candidates:
        try:
            if candidate.is_file():
                return str(candidate.resolve())
        except OSError:
            continue
    return str(candidates[0]) if candidates else str(raw_path)


def _cleanup_completed_pending_attachment_files(attachment_files: list[Any]) -> None:
    cleanup_roots = [
        (_feishu_resource_root()).resolve(),
        (Path.cwd() / "tmp").resolve(),
        (Path.cwd().parent / "tmp").resolve(),
        (Path.cwd().parent.parent / "tmp").resolve(),
    ]
    touched_dirs: list[Path] = []
    for item in attachment_files:
        raw_path = str(item.get("path") if isinstance(item, dict) else item or "").strip()
        if not raw_path:
            continue
        try:
            path = Path(raw_path).expanduser().resolve()
            if not path.is_file():
                continue
            if not any(root == path.parent or root in path.parents for root in cleanup_roots):
                continue
            touched_dirs.append(path.parent)
            path.unlink()
        except Exception:
            logger.warning("failed to cleanup completed pending attachment file: %s", raw_path, exc_info=True)
    for directory in sorted(set(touched_dirs), key=lambda value: len(value.parts), reverse=True):
        for root in cleanup_roots:
            current = directory
            while root in current.parents and current != root:
                try:
                    current.rmdir()
                except OSError:
                    break
                current = current.parent


def _extract_direct_bitable_archive_context(content: str) -> dict[str, Any]:
    text = str(content or "")
    if not _reply_contains_direct_bitable_pending_archive(text):
        return {}
    base_token = _extract_labeled_token(
        text,
        ("Base Token", "Base", "base_token", "app_token"),
        r"[A-Za-z0-9_-]{8,}",
    )
    table_id = _extract_labeled_token(
        text,
        ("Table ID", "表 ID", "表ID", "table_id"),
        r"tbl[A-Za-z0-9_-]+",
    )
    if not table_id:
        table_id = _extract_labeled_token(
            text,
            ("数据表",),
            r"tbl[A-Za-z0-9_-]+",
        )
    if not base_token or not table_id:
        return {}
    title = ""
    lines = [raw_line.strip() for raw_line in text.splitlines()]
    for index, line in enumerate(lines):
        if line in {"【目标文档】", "【目标多维表格】", "【保存位置】"}:
            for next_line in lines[index + 1 : index + 4]:
                candidate = next_line.strip().lstrip("-*").strip().strip("`")
                if candidate and not re.match(r"^(?:Base|Table|数据表|附件字段)\s*[：:]", candidate, re.I):
                    title = candidate
                    break
            if title:
                break
    for line in lines:
        if title:
            break
        match = re.match(r"^\s*(?:[-*]\s*)?(?:名称|文档|多维表格|目标文档|目标多维表格)\s*[：:]\s*`?(.+?)`?\s*$", line)
        if match:
            candidate = str(match.group(1) or "").strip().strip("`")
            if candidate and not candidate.startswith(("BITABLE", "Base", "Table")):
                title = candidate
                break
    return {
        "archive_target_base_token": base_token,
        "archive_target_table_id": table_id,
        "archive_target_document_title": title,
        "archive_writer_mode": "lark_cli_user",
        "pending_resource_refs": _extract_feishu_resource_refs_from_text(text),
    }


def _build_direct_bitable_archive_task() -> dict[str, Any]:
    return {
        "id": "direct-bitable-pending-archive",
        "title": "继续执行上一条飞书待写入记录",
        "description": "根据上一条机器人回复中的目标资源、结构化内容和附件资源继续完成归档写入。",
        "actions": [
            {
                "id": "direct-bitable-archive",
                "type": "project_chat",
                "params": {
                    "workflow": "feishu_bot_auto_archive_to_doc_table",
                    "writer_type": "bitable",
                    "writer_mode": "lark_cli_user",
                    "categories": {
                        "bug": "bitable",
                        "需求": "bitable",
                        "功能": "bitable",
                        "会议": "bitable",
                    },
                },
            }
        ],
    }


def _direct_bitable_archive_action(task: dict[str, Any]) -> dict[str, Any]:
    actions = task.get("actions") if isinstance(task.get("actions"), list) else []
    for action in actions:
        if isinstance(action, dict) and is_feishu_auto_archive_action(action):
            return action
    return {}


def _find_recent_structured_pending_archive_reply(messages: list[Any], source_context: dict[str, Any]) -> str:
    pending_message = _latest_pending_archive_message(messages, source_context)
    if pending_message is None:
        return ""
    content = _archive_message_reply_content(pending_message)
    return content if _reply_contains_structured_pending_archive(content) else ""


def _first_archive_action_result(matched_tasks: list[dict[str, Any]]) -> dict[str, Any] | None:
    for task in matched_tasks:
        execution = task.get("latest_execution") if isinstance(task.get("latest_execution"), dict) else {}
        for result in execution.get("action_results") or []:
            if not isinstance(result, dict):
                continue
            if str(result.get("action_type") or "").strip() != "project_chat":
                continue
            return result
    return None


def _reply_archive_workflow_state(
    *,
    reply_content: str,
    matched_tasks: list[dict[str, Any]] | None = None,
    direct_archive_result: dict[str, Any] | None = None,
    direct_attachment_result: dict[str, Any] | None = None,
    workflow_id: str = "",
) -> dict[str, Any]:
    matched = matched_tasks if isinstance(matched_tasks, list) else []
    task_result = _first_archive_action_result(matched)
    direct_archive_status = str((direct_archive_result or {}).get("status") or "").strip().lower()
    direct_attachment_status = str((direct_attachment_result or {}).get("status") or "").strip().lower()
    task_status = str((task_result or {}).get("status") or "").strip().lower()

    if direct_attachment_status == "updated":
        return _build_archive_workflow_state(
            status="written",
            workflow_id=workflow_id,
            reply_content=reply_content,
            result=direct_attachment_result,
        )
    if direct_archive_status in {"saved", "archived", "written"}:
        return _build_archive_workflow_state(
            status="written",
            workflow_id=workflow_id,
            reply_content=reply_content,
            result=direct_archive_result,
        )
    if task_status in {"saved", "archived", "written"}:
        return _build_archive_workflow_state(
            status="written",
            workflow_id=workflow_id,
            reply_content=reply_content,
            result=task_result,
        )
    if direct_archive_status in {"pending", "unconfirmed"}:
        return _build_archive_workflow_state(
            status="pending_retry",
            workflow_id=workflow_id,
            reply_content=reply_content,
            result=direct_archive_result,
        )
    if direct_attachment_result and direct_attachment_status in {"skipped", "pending", "unconfirmed"}:
        return _build_archive_workflow_state(
            status="pending_retry",
            workflow_id=workflow_id,
            reply_content=reply_content,
            result=direct_attachment_result,
        )
    if task_status == "failed":
        return _build_archive_workflow_state(
            status="failed",
            workflow_id=workflow_id,
            reply_content=reply_content,
            result=task_result,
        )
    if direct_archive_status in {"failed", "error"}:
        return _build_archive_workflow_state(
            status="failed",
            workflow_id=workflow_id,
            reply_content=reply_content,
            result=direct_archive_result,
        )
    if _reply_contains_direct_bitable_attachment_pending(reply_content):
        return _build_archive_workflow_state(
            status="pending_attachment",
            workflow_id=workflow_id,
            reply_content=reply_content,
        )
    if _reply_contains_direct_bitable_pending_archive(reply_content):
        return _build_archive_workflow_state(
            status="pending_retry",
            workflow_id=workflow_id,
            reply_content=reply_content,
        )
    if _reply_contains_structured_pending_archive(reply_content):
        return _build_archive_workflow_state(
            status="pending_confirmation",
            workflow_id=workflow_id,
            reply_content=reply_content,
        )
    return {}


def _looks_like_feishu_archive_confirmation(text: str) -> bool:
    normalized = re.sub(r"[\s，。！？!?,.;；：:、]+", "", str(text or "").strip().lower())
    if not normalized or len(normalized) > 12:
        return False
    if re.search(r"(不要|取消|停止|别|不保存|不归档|不记录|不写入)", normalized):
        return False
    return normalized in {
        "确认",
        "同意",
        "可以",
        "继续",
        "你继续",
        "那你继续",
        "继续吧",
        "可以继续",
        "直接执行",
        "继续执行",
        "重试",
        "重新执行",
        "再试",
        "执行",
        "保存",
        "归档",
        "提交",
        "写入",
        "确认写入",
        "确认保存",
        "确认归档",
    }


def _process_feishu_archive_tasks_after_reply(
    *,
    username: str,
    project_id: str,
    message_text: str,
    reply_content: str,
    source_context: dict[str, Any],
    already_matched_tasks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    text = str(reply_content or "")
    has_structured_archive_payload = all(
        item in text
        for item in ("【待归档类型】", "【待归档状态】", "【结构化内容】")
    )
    if not has_structured_archive_payload and not _reply_contains_direct_bitable_pending_archive(text):
        return []
    archive_context = {
        **source_context,
        **_extract_direct_bitable_archive_context(reply_content),
        "archive_input": "assistant_structured_reply",
    }
    succeeded_task_ids = {
        str(task.get("id") or "").strip()
        for task in already_matched_tasks
        if _task_archive_write_succeeded(task)
    }
    archive_message = "\n\n".join(
        item
        for item in (
            str(message_text or "").strip(),
            "机器人整理结果：",
            str(reply_content or "").strip(),
        )
        if item
    )
    processed: list[dict[str, Any]] = []
    for task in list_global_assistant_tasks(username=username, project_id=project_id, include_done=False):
        task_id = str(task.get("id") or "").strip()
        if not task_id or task_id in succeeded_task_ids:
            continue
        if not bool(task.get("listen_enabled", True)):
            continue
        if not _task_uses_auto_archive_workflow(task):
            continue
        executed = execute_global_assistant_task(
            username=username,
            project_id=project_id,
            task_id=task_id,
            trigger_type="event",
            message_text=archive_message,
            match_reason="assistant-structured-archive",
            source_context=archive_context,
            action_filter=_is_auto_archive_project_chat_action,
        )
        if executed:
            processed.append({**task, "latest_execution": executed.get("latest_execution")})
    return processed


def _process_direct_bitable_attachment_after_reply(reply_content: str) -> dict[str, Any] | None:
    context = _extract_direct_bitable_attachment_context(reply_content)
    if not context:
        return None
    result = append_direct_bitable_record_attachments(
        app_token=str(context.get("base_token") or ""),
        table_id=str(context.get("table_id") or ""),
        record_id=str(context.get("record_id") or ""),
        attachment_files=context.get("attachment_files") if isinstance(context.get("attachment_files"), list) else [],
        field_name=str(context.get("attachment_field") or ""),
        document_title=str(context.get("document_title") or ""),
    )
    if (
        isinstance(result, dict)
        and str(result.get("status") or "").strip().lower() == "updated"
        and int(result.get("uploaded_count") or 0) > 0
    ):
        files = result.get("attachment_files") if isinstance(result.get("attachment_files"), list) else context.get("attachment_files")
        _cleanup_completed_pending_attachment_files(files if isinstance(files, list) else [])
    return result


async def _process_direct_bitable_archive_after_reply(
    *,
    connector: dict[str, Any],
    connector_id: str,
    message_text: str,
    reply_content: str,
    source_context: dict[str, Any],
) -> dict[str, Any] | None:
    direct_context = _extract_direct_bitable_archive_context(reply_content)
    if not direct_context:
        return None
    task = _build_direct_bitable_archive_task()
    action = _direct_bitable_archive_action(task)
    if not action:
        return None
    archive_context = {
        **source_context,
        **direct_context,
        "archive_input": "assistant_structured_reply",
    }
    pending_resource_refs = direct_context.get("pending_resource_refs")
    downloaded_resources: list[dict[str, str]] = []
    resource_download_errors: list[dict[str, str]] = []
    try:
        if isinstance(pending_resource_refs, list) and pending_resource_refs:
            _merge_source_message_resources(archive_context, pending_resource_refs)
            downloaded_resources = await _redownload_feishu_message_resources(
                connector,
                connector_id=connector_id,
                resource_refs=pending_resource_refs,
                download_errors=resource_download_errors,
            )
            if resource_download_errors:
                archive_context["resource_download_errors"] = resource_download_errors
            if downloaded_resources:
                _merge_source_attachment_files(
                    archive_context,
                    [item for item in downloaded_resources if item.get("path")],
                )
                image_urls = [
                    str(item.get("url") or "").strip()
                    for item in downloaded_resources
                    if str(item.get("url") or "").strip()
                    and str(item.get("type") or "").strip().lower() == "image"
                ]
                if image_urls:
                    _merge_source_image_urls(archive_context, image_urls)
        archive_message = "\n\n".join(
            item
            for item in (
                str(message_text or "").strip(),
                "机器人整理结果：",
                str(reply_content or "").strip(),
            )
            if item
        )
        result = archive_feishu_task_message(
            task=task,
            action=action,
            message_text=archive_message,
            source_context=archive_context,
        )
        if isinstance(result, dict) and resource_download_errors:
            result["resource_download_errors"] = resource_download_errors
            result.setdefault("attachment_error", resource_download_errors[0].get("message") or "附件资源下载失败")
    finally:
        _cleanup_downloaded_feishu_resources(downloaded_resources)
    if (
        isinstance(result, dict)
        and str(result.get("status") or "").strip().lower() in {"saved", "archived", "written"}
        and int(result.get("attachment_upload_count") or 0) > 0
    ):
        attachment_files = archive_context.get("attachment_files")
        _cleanup_completed_pending_attachment_files(attachment_files if isinstance(attachment_files, list) else [])
    return result if isinstance(result, dict) else None


def _build_direct_bitable_archive_reply(result: dict[str, Any] | None) -> str:
    payload = result if isinstance(result, dict) else {}
    if not payload:
        return ""
    status = str(payload.get("status") or "").strip().lower()
    if status in {"saved", "archived", "written"}:
        title = str(payload.get("document_title") or "").strip()
        doc_url = str(payload.get("doc_url") or "").strip()
        doc_id = str(payload.get("doc_id") or payload.get("document_id") or "").strip()
        target = title or doc_url or doc_id or "目标多维表格"
        lines = [f"已保存到：{target}"]
        if doc_url:
            lines.append(doc_url)
        elif doc_id:
            lines.append(f"文档ID：{doc_id}")
        record_id = str(payload.get("record_id") or "").strip()
        if record_id:
            lines.append(f"记录 ID：{record_id}")
        uploaded_count = int(payload.get("attachment_upload_count") or 0)
        if uploaded_count > 0:
            lines.append(f"附件上传数量：{uploaded_count}")
        attachment_error = str(payload.get("attachment_error") or "").strip()
        if attachment_error:
            lines.append("")
            lines.append(f"但附件暂未写入成功：{attachment_error[:500]}")
        resource_errors = payload.get("resource_download_errors")
        if isinstance(resource_errors, list) and resource_errors and not attachment_error:
            first_error = resource_errors[0] if isinstance(resource_errors[0], dict) else {}
            error_message = str(
                first_error.get("message") or first_error.get("error_message") or "飞书消息资源下载失败"
            ).strip()
            lines.append("")
            lines.append(f"但附件暂未写入成功：{error_message[:500]}")
        return "\n".join(lines)
    if status in {"pending", "unconfirmed"}:
        message = str(payload.get("message") or "未确认写入成功").strip()
        table_id = str(payload.get("table_id") or "").strip()
        doc_url = str(payload.get("doc_url") or "").strip()
        lines = [message[:500]]
        if doc_url:
            lines.append(doc_url)
        elif table_id:
            lines.append(f"数据表：{table_id}")
        return "\n".join(lines)
    if status in {"failed", "error"}:
        message = str(payload.get("message") or "归档写入失败").strip()
        return _sanitize_feishu_user_reply(f"归档写入失败：{message[:500]}")
    return ""


def _build_direct_bitable_attachment_reply(result: dict[str, Any] | None) -> str:
    payload = result if isinstance(result, dict) else {}
    if not payload:
        return ""
    status = str(payload.get("status") or "").strip().lower()
    record_id = str(payload.get("record_id") or "").strip()
    table_id = str(payload.get("table_id") or "").strip()
    title = str(payload.get("document_title") or "").strip()
    field_name = str(payload.get("attachment_field_name") or "").strip()
    uploaded_count = int(payload.get("uploaded_count") or 0)
    if status == "updated" and uploaded_count > 0:
        target = title or "目标多维表格"
        lines = [f"已把附件写入：{target}"]
        if record_id:
            lines.append(f"记录 ID：{record_id}")
        if table_id:
            lines.append(f"数据表：{table_id}")
        if field_name:
            lines.append(f"附件字段：{field_name}")
        lines.append(f"上传数量：{uploaded_count}")
        return "\n".join(lines)
    message = str(payload.get("message") or "附件补写未完成").strip()
    detail = f"\n记录 ID：{record_id}" if record_id else ""
    return f"附件补写未完成：{message[:500]}{detail}"


def _build_confirmed_archive_reply(matched_tasks: list[dict[str, Any]]) -> str:
    for task in matched_tasks:
        if not _task_uses_auto_archive_workflow(task):
            continue
        execution = task.get("latest_execution") if isinstance(task.get("latest_execution"), dict) else {}
        for result in execution.get("action_results") or []:
            if not isinstance(result, dict):
                continue
            if str(result.get("action_type") or "").strip() != "project_chat":
                continue
            if str(result.get("status") or "").strip().lower() not in {"saved", "archived", "written"}:
                continue
            title = str(result.get("document_title") or "").strip()
            doc_url = str(result.get("doc_url") or "").strip()
            doc_id = str(result.get("doc_id") or result.get("document_id") or "").strip()
            target = title or doc_url or doc_id or "当前群分类文档"
            suffix = f"\n{doc_url}" if doc_url else (f"\n文档ID：{doc_id}" if doc_id else "")
            attachment_error = str(result.get("attachment_error") or "").strip()
            if attachment_error:
                record_id = str(result.get("record_id") or "").strip()
                extra = f"\n记录 ID：{record_id}" if record_id else ""
                return (
                    f"已保存到：{target}{suffix}{extra}\n\n"
                    "但附件图片暂未写入成功：飞书返回附件 token 当前不可用。"
                    "记录已保留，可稍后直接发送图片并说明“追加到这条记录”。"
                )
            return f"已保存到：{target}{suffix}"
    return ""


def _sanitize_feishu_user_reply(content: str) -> str:
    text = str(content or "").strip()
    if not text:
        return text

    fallback = (
        "当前处理已暂停，但没有拿到可继续执行所需的环境、权限、必要输入或成功工具返回。"
        "请补充缺失的内容、附件或授权后再继续；不要重复发送同一句“重新执行”。"
    )
    internal_patterns = (
        r"(?im)^.*(?:本轮停止原因|当前状态|当前最小下一步|工具执行预算|操作预算|执行预算|预算上限|token预算|上下文预算|本次操作预算|当前操作预算|tool call|tool budget|context budget).*$",
        r"(?im)^.*(?:本轮实际执行过的命令|本轮实际检查结果|本地 lark-cli 有更新提示).*$",
        r"(?im)^.*(?:已达到.*?预算|预算已用尽|预算用尽|操作预算已用尽).*$",
        r"(?is)^\s*['\"]?\s*\{\s*\"tool_uses\".*?\}\s*['\"]?\s*",
    )
    sanitized = text
    for pattern in internal_patterns:
        sanitized = re.sub(pattern, "", sanitized)
    sanitized = re.sub(r"\n{3,}", "\n\n", sanitized).strip()
    if not sanitized:
        return fallback
    return sanitized


def _build_failed_archive_reply(matched_tasks: list[dict[str, Any]]) -> str:
    for task in matched_tasks:
        if not _task_uses_auto_archive_workflow(task):
            continue
        execution = task.get("latest_execution") if isinstance(task.get("latest_execution"), dict) else {}
        for result in execution.get("action_results") or []:
            if not isinstance(result, dict):
                continue
            if str(result.get("action_type") or "").strip() != "project_chat":
                continue
            if str(result.get("status") or "").strip().lower() != "failed":
                continue
            message = str(result.get("message") or "飞书归档写入失败").strip()
            return _sanitize_feishu_user_reply(f"归档写入失败：{message[:500]}")
    return ""


def _downgrade_unconfirmed_archive_reply(content: str, matched_tasks: list[dict[str, Any]]) -> str:
    if not any(_task_uses_auto_archive_workflow(task) and not _task_archive_write_succeeded(task) for task in matched_tasks):
        return content
    if not _reply_claims_archive_success(content):
        return content
    sanitized = str(content or "").strip()
    replacements = (
        ("已归档，保存到", "待归档，目标归档表"),
        ("已归档，保存至", "待归档，目标归档表"),
        ("已归档", "待归档"),
        ("记录已保存", "记录待保存"),
        ("已保存", "待保存"),
        ("已写入", "待写入"),
        ("写入完成", "待写入"),
        ("保存到", "目标归档表"),
    )
    for old, new in replacements:
        sanitized = sanitized.replace(old, new)
    sanitized = _sanitize_feishu_user_reply(sanitized)
    notice = "⚠️ 当前只完成信息整理，尚未真实写入飞书群归档表；请以多维表格实际记录为准。"
    return f"{notice}\n\n{sanitized}" if sanitized else notice


def _build_feishu_reply_text(content: str) -> str:
    normalized = _sanitize_feishu_user_reply(content)
    if not normalized:
        normalized = "模型未返回有效内容。"
    if len(normalized) <= _FEISHU_REPLY_CHAR_LIMIT:
        return normalized
    return normalized[: _FEISHU_REPLY_CHAR_LIMIT - 3].rstrip() + "..."


async def _reply_feishu_text(
    connector: dict[str, Any],
    *,
    message_id: str,
    content: str,
    reply_in_thread: bool = False,
    idempotency_suffix: str = "",
) -> None:
    if _normalize_feishu_reply_identity(connector) == "bot":
        await asyncio.to_thread(
            _reply_feishu_text_with_open_api,
            connector,
            message_id=message_id,
            content=content,
            reply_in_thread=reply_in_thread,
            idempotency_suffix=idempotency_suffix,
        )
        return
    await asyncio.to_thread(
        _reply_feishu_text_with_lark_cli,
        connector,
        message_id=message_id,
        content=content,
        reply_in_thread=reply_in_thread,
        idempotency_suffix=idempotency_suffix,
    )


def _reply_feishu_text_with_lark_cli(
    connector: dict[str, Any],
    *,
    message_id: str,
    content: str,
    reply_in_thread: bool = False,
    idempotency_suffix: str = "",
) -> None:
    normalized_message_id = str(message_id or "").strip()
    if not normalized_message_id:
        raise RuntimeError("缺少飞书 message_id，无法回复")
    suffix = str(idempotency_suffix or "").strip()
    idempotency_key = f"feishu-reply-{normalized_message_id}"
    if suffix:
        idempotency_key = f"{idempotency_key}-{suffix}"
    command = [
        "lark-cli",
        "im",
        "+messages-reply",
        "--message-id",
        normalized_message_id,
        "--text",
        _build_feishu_reply_text(content),
        "--as",
        _normalize_feishu_reply_identity(connector),
        "--idempotency-key",
        idempotency_key,
    ]
    if reply_in_thread:
        command.append("--reply-in-thread")
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("未找到 lark-cli，请先安装 @larksuite/cli 并重新启动服务") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("lark-cli 回复飞书消息超时，请检查飞书授权或网络状态") from exc
    if completed.returncode != 0:
        output = (completed.stderr or completed.stdout or "").strip()[:800]
        raise RuntimeError(f"lark-cli 回复飞书消息失败：{output}")


_FEISHU_OPEN_API_UUID_MAX_LENGTH = 50


def _normalize_feishu_uuid(value: str, *, fallback_prefix: str = "feishu") -> str:
    """Coerce an idempotency key into a valid Feishu OpenAPI ``uuid``.

    Feishu's ``/open-apis/im/v1/messages`` ``uuid`` field rejects values longer
    than 50 characters with an opaque ``400 Bad Request``. Keys within the limit
    pass through unchanged so idempotency is preserved; over-long (or empty) keys
    are replaced with a value derived from a deterministic hash of the full key.
    A hash rather than a raw truncation avoids two distinct keys colliding on a
    shared prefix.
    """
    normalized = str(value or "").strip()
    if normalized and len(normalized) <= _FEISHU_OPEN_API_UUID_MAX_LENGTH:
        return normalized
    seed = uuid.uuid4().hex if not normalized else hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"{fallback_prefix}-{seed}"[:_FEISHU_OPEN_API_UUID_MAX_LENGTH]


def _parse_feishu_open_api_response(response: requests.Response, *, action: str) -> dict[str, Any]:
    """Return the Feishu OpenAPI payload, raising a descriptive error on failure.

    Feishu encodes the real reason for a failure in the JSON body (``code`` /
    ``msg``) even when the HTTP status is 4xx. Parsing that body before raising
    surfaces the actual cause (e.g. an invalid ``uuid``) instead of a bare
    ``400 Bad Request``. Falls back to ``raise_for_status`` when the body is not
    a parseable Feishu envelope.
    """
    payload: Any = None
    try:
        payload = response.json()
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        code = int(payload.get("code") or 0)
        if code != 0:
            msg = str(payload.get("msg") or "").strip() or "未知错误"
            status_code = getattr(response, "status_code", None)
            detail = f"{action}失败：{msg}（code={code}"
            if status_code is not None:
                detail += f", http={status_code}"
            detail += "）"
            raise RuntimeError(detail)
        return payload

    response.raise_for_status()
    return {}


def _reply_feishu_text_with_open_api(
    connector: dict[str, Any],
    *,
    message_id: str,
    content: str,
    reply_in_thread: bool = False,
    idempotency_suffix: str = "",
) -> None:
    normalized_message_id = str(message_id or "").strip()
    if not normalized_message_id:
        raise RuntimeError("缺少飞书 message_id，无法回复")
    suffix = str(idempotency_suffix or "").strip()
    idempotency_key = f"feishu-reply-{normalized_message_id}"
    if suffix:
        idempotency_key = f"{idempotency_key}-{suffix}"
    token = _get_feishu_tenant_access_token(connector)
    response = requests.post(
        _feishu_open_api_url(f"/open-apis/im/v1/messages/{quote(normalized_message_id)}/reply"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        params={"uuid": _normalize_feishu_uuid(idempotency_key, fallback_prefix="feishu-reply")},
        json={
            "msg_type": "text",
            "content": json.dumps({"text": _build_feishu_reply_text(content)}, ensure_ascii=False),
            "reply_in_thread": bool(reply_in_thread),
        },
        timeout=30,
    )
    _parse_feishu_open_api_response(response, action="飞书机器人回复")


def send_feishu_text_message_with_open_api(
    connector: dict[str, Any],
    *,
    chat_id: str,
    content: str,
    idempotency_key: str = "",
) -> dict[str, str]:
    normalized_chat_id = str(chat_id or "").strip()
    if not normalized_chat_id:
        raise RuntimeError("缺少飞书 chat_id，无法发送消息")
    token = _get_feishu_tenant_access_token(connector)
    uuid_value = _normalize_feishu_uuid(idempotency_key, fallback_prefix="feishu-send")
    response = requests.post(
        _feishu_open_api_url("/open-apis/im/v1/messages"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        params={"receive_id_type": "chat_id"},
        json={
            "receive_id": normalized_chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": _build_feishu_reply_text(content)}, ensure_ascii=False),
            "uuid": uuid_value,
        },
        timeout=30,
    )
    payload = _parse_feishu_open_api_response(response, action="飞书机器人发送消息")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    return {
        "message_id": str(data.get("message_id") or "").strip(),
        "chat_id": normalized_chat_id,
    }


def _feishu_external_agent_approval_card(
    *,
    task_id: str,
    approval: dict[str, Any],
    resolved_label: str = "",
) -> dict[str, Any]:
    title = str(approval.get("title") or "Hermes 权限确认").strip()
    description = str(approval.get("description") or "Hermes 请求执行需要确认的操作，请选择允许范围或拒绝。").strip()
    approval_id = str(approval.get("id") or "").strip()
    options = approval.get("options") if isinstance(approval.get("options"), list) else []
    if resolved_label:
        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"content": resolved_label, "tag": "plain_text"},
                "template": "green" if "拒绝" not in resolved_label else "red",
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": f"**{title}**\n\n{description}\n\n{resolved_label}",
                }
            ],
        }

    def _button(option: dict[str, Any], index: int) -> dict[str, Any]:
        decision = str(option.get("decision") or "").strip()
        label = str(option.get("label") or option.get("value") or "").strip()
        button_type = "default"
        if decision == "approve_once" and index == 0:
            button_type = "primary"
        elif decision == "reject":
            button_type = "danger"
        return {
            "tag": "button",
            "text": {"tag": "plain_text", "content": label or "选择"},
            "type": button_type,
            "value": {
                "ai_employee_action": "external_agent_permission",
                "task_id": str(task_id or "").strip(),
                "approval_id": approval_id,
                "option_id": str(option.get("value") or "").strip(),
            },
        }

    actions = [
        _button(option, index)
        for index, option in enumerate(options)
        if isinstance(option, dict) and str(option.get("value") or "").strip()
    ]
    if not actions:
        actions = [
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "拒绝"},
                "type": "danger",
                "value": {
                    "ai_employee_action": "external_agent_permission",
                    "task_id": str(task_id or "").strip(),
                    "approval_id": approval_id,
                    "option_id": "denied",
                },
            }
        ]
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"content": title, "tag": "plain_text"},
            "template": "orange",
        },
        "elements": [
            {
                "tag": "markdown",
                "content": f"**需要授权后继续执行**\n\n{description}",
            },
            {"tag": "action", "actions": actions[:4]},
        ],
    }


def send_feishu_external_agent_approval_card(
    connector: dict[str, Any],
    *,
    chat_id: str,
    task_id: str,
    approval: dict[str, Any],
) -> dict[str, str]:
    normalized_chat_id = str(chat_id or "").strip()
    if not normalized_chat_id:
        raise RuntimeError("缺少飞书 chat_id，无法发送授权卡片")
    token = _get_feishu_tenant_access_token(connector)
    approval_id = str(approval.get("id") or "").strip()
    response = requests.post(
        _feishu_open_api_url("/open-apis/im/v1/messages"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        params={"receive_id_type": "chat_id"},
        json={
            "receive_id": normalized_chat_id,
            "msg_type": "interactive",
            "content": json.dumps(
                _feishu_external_agent_approval_card(task_id=task_id, approval=approval),
                ensure_ascii=False,
            ),
            "uuid": _normalize_feishu_uuid(
                f"feishu-external-agent-approval-{task_id}-{approval_id}",
                fallback_prefix="feishu-approval",
            ),
        },
        timeout=30,
    )
    payload = _parse_feishu_open_api_response(response, action="飞书发送授权卡片")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    return {
        "message_id": str(data.get("message_id") or "").strip(),
        "chat_id": normalized_chat_id,
    }


def _update_feishu_external_agent_approval_card(
    connector: dict[str, Any],
    *,
    message_id: str,
    task_id: str,
    approval: dict[str, Any],
    resolved_label: str,
) -> None:
    normalized_message_id = str(message_id or "").strip()
    if not normalized_message_id:
        return
    token = _get_feishu_tenant_access_token(connector)
    response = requests.patch(
        _feishu_open_api_url(f"/open-apis/im/v1/messages/{quote(normalized_message_id)}"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        json={
            "msg_type": "interactive",
            "content": json.dumps(
                _feishu_external_agent_approval_card(
                    task_id=task_id,
                    approval=approval,
                    resolved_label=resolved_label,
                ),
                ensure_ascii=False,
            ),
        },
        timeout=30,
    )
    _parse_feishu_open_api_response(response, action="飞书更新授权卡片")


async def process_feishu_message_event(connector_id: str, event: P2ImMessageReceiveV1) -> None:
    from routers import projects as projects_router

    connector = get_feishu_connector(connector_id)
    if connector is None or not bool(connector.get("enabled", True)):
        return
    app_id = str(connector.get("app_id") or "").strip()
    app_secret = str(connector.get("app_secret") or "").strip()
    if not app_id or not app_secret:
        logger.warning("feishu connector ignored because app credentials are incomplete", extra={"connector_id": connector_id})
        return

    payload = getattr(event, "event", None)
    sender = getattr(payload, "sender", None)
    message = getattr(payload, "message", None)
    if sender is None or message is None:
        return
    if str(getattr(sender, "sender_type", "") or "").strip().lower() != "user":
        return

    chat_type = str(getattr(message, "chat_type", "") or "").strip().lower()
    chat_id = str(getattr(message, "chat_id", "") or "").strip()
    thread_id = str(getattr(message, "thread_id", "") or "").strip()
    message_id = str(getattr(message, "message_id", "") or "").strip()
    sender_id = getattr(sender, "sender_id", None)
    sender_open_id = str(getattr(sender_id, "open_id", "") or "").strip()
    if not chat_id or not message_id:
        return

    text_message = _strip_leading_feishu_bot_mentions(
        _parse_feishu_text_message(event),
        connector,
    )
    resources = _extract_feishu_message_resources(message)
    mentioned = _should_process_feishu_group_text_message(
        connector=connector,
        message=message,
        chat_type=chat_type,
        thread_id=thread_id,
        text_message=text_message,
        resources=resources,
    )

    binding = _find_feishu_project_chat_session_binding(
        connector_id=connector_id,
        chat_id=chat_id,
        chat_type=chat_type,
        projects_router=projects_router,
    )
    if binding is None and mentioned:
        binding = _create_feishu_fallback_chat_session(
            connector,
            connector_id=connector_id,
            chat_id=chat_id,
            chat_type=chat_type,
            thread_id=thread_id,
            sender_open_id=sender_open_id,
            projects_router=projects_router,
        )

    continue_with_resources = False
    previous_messages: list[Any] = []
    if binding is not None:
        project_id, username, chat_session_id, bound_context = binding
        previous_messages = projects_router.project_chat_store.list_messages(
            project_id,
            username,
            limit=80,
            chat_session_id=chat_session_id,
        )
        continue_with_resources = _should_continue_feishu_group_workflow_with_resources(
            previous_messages=previous_messages,
            sender_open_id=sender_open_id,
            resources=resources,
        )

    if not mentioned and not continue_with_resources:
        logger.debug(
            "feishu group text message ignored because bot was not mentioned",
            extra={"connector_id": connector_id, "chat_id": chat_id, "message_id": message_id},
        )
        return
    if binding is None:
        logger.warning(
            "feishu message ignored because no project chat session binding was found",
            extra={
                "connector_id": connector_id,
                "chat_id": chat_id,
                "chat_type": chat_type,
                "message_id": message_id,
            },
        )
        return

    project_id, username, chat_session_id, bound_context = binding
    source_context = projects_router._normalize_project_chat_source_context(
        {
            **bound_context,
            "platform": "feishu",
            "connector_id": connector_id,
            "external_chat_id": chat_id,
            "external_message_id": message_id,
            "sender_id": sender_open_id,
            "source_type": _feishu_chat_source_type(chat_type),
            "thread_key": str(bound_context.get("thread_key") or chat_session_id),
        },
        project_id=project_id,
        default_source_type=_feishu_chat_source_type(chat_type),
    )
    try:
        project = projects_router.project_store.get(project_id)
        workspace_path = str(getattr(project, "workspace_path", "") or "").strip() if project is not None else ""
    except Exception:
        workspace_path = ""
    if workspace_path:
        source_context["workspace_path"] = workspace_path
    if any(str(getattr(item, "id", "") or "").strip() == message_id for item in previous_messages):
        return
    history = _feishu_history_from_messages(previous_messages)
    await projects_router.publish_project_chat_group_status_realtime(
        project_id=project_id,
        username=username,
        chat_session_id=chat_session_id,
        status="processing",
        message="当前飞书群正在通讯",
        source_context=source_context,
    )

    downloaded_resources: list[dict[str, str]] = []
    if resources:
        _merge_source_message_resources(source_context, resources)
    for resource in resources:
        try:
            downloaded_resource = await asyncio.to_thread(
                _download_feishu_message_resource,
                connector,
                connector_id=connector_id,
                message_id=message_id,
                file_key=str(resource.get("file_key") or ""),
                resource_type=str(resource.get("type") or "image"),
            )
            if downloaded_resource:
                downloaded_resources.append(downloaded_resource)
        except Exception:
            logger.exception(
                "failed to download feishu message resource",
                extra={
                    "connector_id": connector_id,
                    "message_id": message_id,
                    "resource_type": str(resource.get("type") or ""),
                },
            )
    image_urls = [
        str(item.get("url") or "").strip()
        for item in downloaded_resources
        if str(item.get("url") or "").strip()
        and str(item.get("type") or "").strip().lower() == "image"
    ]
    attachment_files = [item for item in downloaded_resources if item.get("path")]
    if image_urls:
        _merge_source_image_urls(source_context, image_urls)
    if attachment_files:
        _merge_source_attachment_files(source_context, attachment_files)

    if not text_message:
        resource = resources[0] if resources else {}
        text_message = (
            f"用户发送了{resource.get('label') or '非文本消息'}。"
            if resources
            else f"用户发送了飞书非文本消息：{str(getattr(message, 'message_type', '') or 'unknown')}。"
        )

    recent_image_urls = _recent_feishu_image_urls(previous_messages, source_context)
    if recent_image_urls:
        _merge_source_image_urls(source_context, recent_image_urls)
    recent_resource_refs = _recent_feishu_message_resource_refs(previous_messages, source_context)
    if not recent_resource_refs:
        recent_resource_refs = _recent_feishu_message_resource_refs_from_text(previous_messages, source_context)
    if recent_resource_refs:
        _merge_source_message_resources(source_context, recent_resource_refs)
    if not attachment_files and recent_resource_refs:
        restored_resources = await _redownload_feishu_message_resources(
            connector,
            connector_id=connector_id,
            resource_refs=recent_resource_refs,
        )
        if restored_resources:
            downloaded_resources.extend(restored_resources)
            restored_image_urls = [
                str(item.get("url") or "").strip()
                for item in restored_resources
                if str(item.get("url") or "").strip()
                and str(item.get("type") or "").strip().lower() == "image"
            ]
            image_urls = [
                str(item or "").strip()
                for item in [*image_urls, *restored_image_urls]
                if str(item or "").strip()
            ]
            attachment_files = [*attachment_files, *[item for item in restored_resources if item.get("path")]]
            if restored_image_urls:
                _merge_source_image_urls(source_context, restored_image_urls)
            if attachment_files:
                _merge_source_attachment_files(source_context, attachment_files)
    if not attachment_files and recent_image_urls:
        restored_resources = await _redownload_recent_feishu_image_resources(
            connector,
            connector_id=connector_id,
            image_urls=recent_image_urls,
        )
        if restored_resources:
            downloaded_resources.extend(restored_resources)
            restored_image_urls = [
                str(item.get("url") or "").strip()
                for item in restored_resources
                if str(item.get("url") or "").strip()
            ]
            image_urls = [
                str(item or "").strip()
                for item in [*image_urls, *restored_image_urls]
                if str(item or "").strip()
            ]
            attachment_files = [*attachment_files, *[item for item in restored_resources if item.get("path")]]
            if restored_image_urls:
                _merge_source_image_urls(source_context, restored_image_urls)
            if attachment_files:
                _merge_source_attachment_files(source_context, attachment_files)

    should_reply_in_thread = bool(thread_id)
    pending_archive_message = _latest_pending_archive_message(previous_messages, source_context)
    recent_pending_archive_reply = _archive_message_reply_content(pending_archive_message) if pending_archive_message is not None else ""
    if recent_pending_archive_reply and _looks_like_feishu_archive_confirmation(text_message):
        user_record = projects_router._append_chat_record(
            project_id=project_id,
            username=username,
            role="user",
            content=text_message,
            message_id=message_id,
            chat_session_id=chat_session_id,
            images=image_urls,
            source_context=source_context,
        )
        await projects_router.publish_project_chat_record_realtime(
            project_id=project_id,
            username=username,
            chat_session_id=chat_session_id,
            message=user_record,
        )
        matched_tasks = _process_feishu_archive_tasks_after_reply(
            username=username,
            project_id=project_id,
            message_text=text_message,
            reply_content=recent_pending_archive_reply,
            source_context=source_context,
            already_matched_tasks=[],
        )
        direct_attachment_result = None
        direct_archive_result = None
        if not matched_tasks:
            direct_attachment_result = _process_direct_bitable_attachment_after_reply(recent_pending_archive_reply)
        if not _matched_tasks_have_archive_success(matched_tasks) and not direct_attachment_result:
            direct_archive_result = await _process_direct_bitable_archive_after_reply(
                connector=connector,
                connector_id=connector_id,
                message_text=text_message,
                reply_content=recent_pending_archive_reply,
                source_context=source_context,
            )
        reply_content = (
            _build_confirmed_archive_reply(matched_tasks)
            or _build_failed_archive_reply(matched_tasks)
            or _build_direct_bitable_attachment_reply(direct_attachment_result)
            or _build_direct_bitable_archive_reply(direct_archive_result)
            or (
                "已收到确认，但没有找到可继续执行的待处理写入动作或成功工具返回。"
                "当前暂停原因是缺少可执行上下文、权限/环境或必要输入；"
                "请补充目标记录、附件/文件或授权信息后继续，不要重复发送同一句“重新执行”。"
            )
        )
        archive_workflow_state = _reply_archive_workflow_state(
            reply_content=reply_content,
            matched_tasks=matched_tasks,
            direct_archive_result=direct_archive_result,
            direct_attachment_result=direct_attachment_result,
        )
        current_assistant_workflow = assistant_workflow_from_context(
            getattr(pending_archive_message, "source_context", None)
        )
        next_source_context = _with_archive_workflow_state(source_context, archive_workflow_state)
        next_source_context = with_assistant_workflow_state(
            next_source_context,
            evolve_assistant_workflow_state(
                current_assistant_workflow,
                reply_content=reply_content,
                archive_workflow_state=archive_workflow_state,
            ),
        )
        assistant_record = projects_router._append_chat_record(
            project_id=project_id,
            username=username,
            role="assistant",
            content=reply_content,
            message_id=f"bot-reply-{uuid.uuid4().hex[:12]}",
            chat_session_id=chat_session_id,
            source_context=next_source_context,
        )
        await projects_router.publish_project_chat_record_realtime(
            project_id=project_id,
            username=username,
            chat_session_id=chat_session_id,
            message=assistant_record,
        )
        await _reply_feishu_text(
            connector,
            message_id=message_id,
            content=reply_content,
            reply_in_thread=bool(thread_id),
        )
        await projects_router.publish_project_chat_group_status_realtime(
            project_id=project_id,
            username=username,
            chat_session_id=chat_session_id,
            status="linked",
            message="当前飞书群已链接工作群",
            source_context=source_context,
        )
        _cleanup_downloaded_feishu_resources(downloaded_resources)
        return

    auth_payload = {"sub": username, "role": "admin", "roles": ["admin"]}
    skill_resource_directory = _resolve_feishu_skill_resource_directory(project_id, projects_router)
    chat_mode = "system"
    external_agent_type = str(connector.get("external_agent_type") or "").strip().lower()
    if external_agent_type not in {"codex_cli", "hermes", "claude_code"}:
        external_agent_type = "codex_cli"
    req = ProjectChatReq(
        message=text_message,
        message_id=message_id,
        assistant_message_id=f"bot-reply-{uuid.uuid4().hex[:12]}",
        chat_session_id=chat_session_id,
        chat_mode=chat_mode,
        chat_surface="main-chat",
        external_agent_type=external_agent_type,
        provider_id=str(connector.get("provider_id") or "").strip(),
        model_name=str(connector.get("model_name") or "").strip(),
        history=history,
        employee_id="",
        system_prompt="\n\n".join(
            item
            for item in (
                str(connector.get("system_prompt") or "").strip(),
                _build_feishu_agent_workflow_prompt(
                    connector,
                    source_context,
                    skill_resource_directory=skill_resource_directory,
                ),
                _build_feishu_archive_truth_prompt(connector, source_context),
            )
            if item
        ),
        source_context=source_context,
        images=image_urls,
        skill_resource_directory=skill_resource_directory,
    )
    try:
        try:
            await _reply_feishu_text(
                connector,
                message_id=message_id,
                content="收到，正在处理。",
                reply_in_thread=should_reply_in_thread,
                idempotency_suffix="processing",
            )
        except Exception:
            logger.warning(
                "failed to send feishu processing acknowledgement",
                exc_info=True,
                extra={
                    "connector_id": connector_id,
                    "message_id": message_id,
                    "chat_id": chat_id,
                },
            )
        result = await run_project_chat_once(
            project_id=project_id,
            username=username,
            req=req,
            auth_payload=auth_payload,
            save_memory_snapshot=False,
            publish_realtime=True,
        )
        if bool(getattr(result, "is_error", False)):
            await projects_router.publish_project_chat_group_status_realtime(
                project_id=project_id,
                username=username,
                chat_session_id=chat_session_id,
                status="error",
                message=result.content,
                source_context=source_context,
            )
            await _reply_feishu_text(
                connector,
                message_id=message_id,
                content=result.content,
                reply_in_thread=should_reply_in_thread,
            )
            _cleanup_downloaded_feishu_resources(downloaded_resources)
            return
        await projects_router.publish_project_chat_group_status_realtime(
            project_id=project_id,
            username=username,
            chat_session_id=chat_session_id,
            status="linked",
            message="当前飞书群已链接工作群",
            source_context=source_context,
        )
        latest_messages = projects_router.project_chat_store.list_messages(
            project_id,
            username,
            limit=80,
            chat_session_id=chat_session_id,
        )
        late_image_urls = _recent_feishu_image_urls(latest_messages, source_context)
        if late_image_urls:
            _merge_source_image_urls(source_context, late_image_urls)
        matched_tasks = process_global_assistant_tasks_for_event(
            username=username,
            project_id=project_id,
            message_text=text_message,
            source_context=source_context,
            skip_auto_archive_actions=True,
        )
        meeting_reminder_result = create_feishu_meeting_reminder_task(
            username=username,
            project_id=project_id,
            connector=connector,
            connector_id=connector_id,
            chat_id=chat_id,
            message_id=message_id,
            message_text=text_message,
            source_context=source_context,
        )
        matched_tasks.extend(
            _process_feishu_archive_tasks_after_reply(
                username=username,
                project_id=project_id,
                message_text=text_message,
                reply_content=result.content,
                source_context=source_context,
                already_matched_tasks=matched_tasks,
            )
        )
        direct_archive_result = None
        if not _matched_tasks_have_archive_success(matched_tasks):
            direct_archive_result = await _process_direct_bitable_archive_after_reply(
                connector=connector,
                connector_id=connector_id,
                message_text=text_message,
                reply_content=result.content,
                source_context=source_context,
            )
        speech_text = _build_feishu_task_listener_speech_text(
            message_text=text_message,
            matched_tasks=matched_tasks,
            source_context=source_context,
        )
        if speech_text:
            speech_result = await enqueue_system_speech(
                speech_text,
                owner_username=username,
                role_ids=["admin"],
                source="feishu-task-listener",
                require_enabled=True,
            )
            if not bool(speech_result.get("queued")):
                logger.info(
                    "feishu task-listener response was not queued for system speech",
                    extra={
                        "reason": str(speech_result.get("reason") or "").strip(),
                        "connector_id": connector_id,
                        "matched_task_ids": [str(item.get("id") or "") for item in matched_tasks],
                        "speech_text": speech_text,
                    },
                )
        reply_content = (
            _build_feishu_meeting_reminder_reply(meeting_reminder_result)
            or
            _build_confirmed_archive_reply(matched_tasks)
            or _build_failed_archive_reply(matched_tasks)
            or _build_direct_bitable_archive_reply(direct_archive_result)
            or _downgrade_unconfirmed_archive_reply(result.content, matched_tasks)
        )
        archive_workflow_state = _reply_archive_workflow_state(
            reply_content=reply_content,
            matched_tasks=matched_tasks,
            direct_archive_result=direct_archive_result,
        )
        current_assistant_workflow = {}
        latest_messages_for_state = projects_router.project_chat_store.list_messages(
            project_id,
            username,
            limit=20,
            chat_session_id=chat_session_id,
        )
        for item in reversed(latest_messages_for_state):
            if str(getattr(item, "id", "") or "").strip() != str(req.assistant_message_id or "").strip():
                continue
            current_assistant_workflow = assistant_workflow_from_context(getattr(item, "source_context", None))
            break
        next_source_context = _with_archive_workflow_state(source_context, archive_workflow_state)
        next_source_context = with_assistant_workflow_state(
            next_source_context,
            evolve_assistant_workflow_state(
                current_assistant_workflow,
                reply_content=reply_content,
                archive_workflow_state=archive_workflow_state,
            ),
        )
        updated_record = projects_router.project_chat_store.update_message(
            project_id,
            username,
            str(req.assistant_message_id or "").strip(),
            content=reply_content,
            source_context=next_source_context,
        )
        if updated_record is not None:
            await projects_router.publish_project_chat_record_realtime(
                project_id=project_id,
                username=username,
                chat_session_id=chat_session_id,
                message=updated_record,
            )
        await _reply_feishu_text(
            connector,
            message_id=message_id,
            content=reply_content,
            reply_in_thread=should_reply_in_thread,
        )
    finally:
        _cleanup_downloaded_feishu_resources(downloaded_resources)
