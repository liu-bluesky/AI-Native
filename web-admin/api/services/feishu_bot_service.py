"""Feishu bot webhook integration."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import mimetypes
import os
import re
import uuid
from email.message import Message
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import requests

try:
    import lark_oapi as lark
    from lark_oapi.api.im.v1 import (
        P2ImMessageReceiveV1,
        ReplyMessageRequest,
        ReplyMessageRequestBody,
    )
except ModuleNotFoundError as exc:
    lark = None
    P2ImMessageReceiveV1 = Any
    ReplyMessageRequest = Any
    ReplyMessageRequestBody = Any
    _LARK_IMPORT_ERROR: ModuleNotFoundError | None = exc
else:
    _LARK_IMPORT_ERROR = None

if TYPE_CHECKING:
    import lark_oapi as _lark_module

from core.config import get_api_data_dir
from models.requests import ProjectChatReq
from services.bot_connector_service import list_bot_connectors
from services.feishu_archive_writer_service import append_feishu_archive_attachments
from services.project_chat_execution_service import run_project_chat_once
from services.global_assistant_task_service import (
    execute_global_assistant_task,
    list_global_assistant_tasks,
    process_global_assistant_tasks_for_event,
)
from services.system_speech_service import enqueue_system_speech

logger = logging.getLogger(__name__)

_FEISHU_REPLY_CHAR_LIMIT = 4000
_FEISHU_OPEN_API_BASE_URL = "https://open.feishu.cn"
_FEISHU_RESOURCE_DIR = "feishu-message-resources"
_FEISHU_RESOURCE_PUBLIC_PREFIX = "/api/bot-events/feishu"


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


def _extract_feishu_message_resources(message: Any) -> list[dict[str, str]]:
    message_type = str(getattr(message, "message_type", "") or "").strip().lower()
    payload = _parse_feishu_message_content(message)
    resources: list[dict[str, str]] = []
    if message_type == "image":
        image_key = str(payload.get("image_key") or payload.get("imageKey") or "").strip()
        if image_key:
            resources.append({"file_key": image_key, "type": "image", "label": "图片"})
    if message_type in {"file", "audio", "video"}:
        file_key = str(payload.get("file_key") or payload.get("fileKey") or "").strip()
        if file_key:
            resources.append({"file_key": file_key, "type": "file", "label": "附件"})
    if message_type == "post":
        for node in _iter_feishu_post_nodes(payload.get("content")):
            image_key = str(node.get("image_key") or node.get("imageKey") or "").strip()
            if image_key:
                resources.append({"file_key": image_key, "type": "image", "label": "图片"})
            file_key = str(node.get("file_key") or node.get("fileKey") or "").strip()
            if file_key:
                resources.append({"file_key": file_key, "type": "file", "label": "附件"})
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
    response.raise_for_status()
    content_type = str(response.headers.get("Content-Type") or "").strip()
    if content_type.startswith("application/json"):
        try:
            payload = response.json()
        except Exception:
            payload = {}
        raise RuntimeError(str(payload.get("msg") or "飞书资源下载失败"))

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


def resolve_feishu_chat_by_name(connector: dict[str, Any], chat_name: str) -> dict[str, Any]:
    query = str(chat_name or "").strip()
    if not query:
        raise RuntimeError("请先填写群名称")
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
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    raw_items = data.get("items") or data.get("chats") or data.get("chatters") or []
    items = [
        item
        for item in (_normalize_feishu_chat_search_item(raw) for raw in raw_items if isinstance(raw, dict))
        if item.get("chat_id")
    ]
    exact = [item for item in items if item.get("name") == query]
    candidates = exact or items
    if not candidates:
        raise RuntimeError("没有搜索到机器人可见的飞书群，请确认机器人在群内、应用权限已开通 im:chat:read，或换更精确的群名")
    if len(candidates) > 1:
        preview = "、".join(f"{item.get('name') or '未命名'}({item.get('chat_id')})" for item in candidates[:5])
        raise RuntimeError(f"搜索到多个飞书群，请把群名称填得更精确：{preview}")
    return candidates[0]


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

    return (
        lark.EventDispatcherHandler.builder(encrypt_key, verification_token)
        .register_p2_im_message_receive_v1(_on_message)
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
    for item in mentions:
        mention_key = str(getattr(item, "key", "") or "").strip()
        if mention_key:
            text = text.replace(mention_key, " ")
    return " ".join(text.split())


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


def _build_feishu_archive_truth_prompt(connector: dict[str, Any], source_context: dict[str, Any]) -> str:
    bot_name = str(connector.get("agent_name") or connector.get("name") or "当前机器人").strip() or "当前机器人"
    group_name = str(source_context.get("external_chat_name") or source_context.get("group_name") or "当前飞书群").strip() or "当前飞书群"
    return (
        "飞书归档真实性约束："
        f"当前执行主体是“{bot_name}”，不是泛指每个机器人；归档范围必须绑定到当前飞书群“{group_name}”。"
        "分类文档/表格应按当前群 + 当前机器人 + 分类维护，不能写到无群归属的全局文档。"
        "识别归档内容时必须结合当前群上下文和最近多轮对话，不要只看最后一句；若上下文已经补齐字段，可以整理为结构化待归档记录。"
        "如果消息中提到图片或附件但系统没有提供可访问链接，应在结构化内容中标记图片/附件待补充，不能编造链接。"
        "除非系统工具已经明确返回创建/追加飞书文档成功，否则禁止回复“已归档”“已保存”“已写入”“保存到”。"
        "如果只是识别并整理了字段，只能回复“已整理为待归档记录”，并说明尚未写入群文档。"
    )


def _task_uses_auto_archive_workflow(task: dict[str, Any]) -> bool:
    for action in task.get("actions") or []:
        if not isinstance(action, dict):
            continue
        params = action.get("params") if isinstance(action.get("params"), dict) else {}
        if str(params.get("workflow") or "").strip() == "feishu_bot_auto_archive_to_doc_table":
            return True
    return False


def _task_archive_write_succeeded(task: dict[str, Any]) -> bool:
    execution = task.get("latest_execution") if isinstance(task.get("latest_execution"), dict) else {}
    for result in execution.get("action_results") or []:
        if not isinstance(result, dict):
            continue
        if str(result.get("action_type") or "").strip() != "project_chat":
            continue
        status = str(result.get("status") or "").strip().lower()
        if status in {"completed", "success", "succeeded", "saved", "archived", "written"}:
            return True
    return False


def _reply_claims_archive_success(content: str) -> bool:
    return bool(re.search(r"已(?:归档|保存|写入)|保存到|写入完成|记录已保存", str(content or "")))


def _reply_contains_structured_pending_archive(content: str) -> bool:
    text = str(content or "")
    return all(
        item in text
        for item in ("【待归档类型】", "【待归档状态】", "【结构化内容】")
    ) and ("尚未写入" in text or "待归档" in text or "已整理" in text)


def _process_feishu_archive_tasks_after_reply(
    *,
    username: str,
    project_id: str,
    message_text: str,
    reply_content: str,
    source_context: dict[str, Any],
    already_matched_tasks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not _reply_contains_structured_pending_archive(reply_content):
        return []
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
            source_context=source_context,
        )
        if executed:
            processed.append({**task, "latest_execution": executed.get("latest_execution")})
    return processed


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
            return f"已保存到：{target}{suffix}"
    return ""


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
            return f"归档写入失败：{message[:500]}"
    return ""


def _downgrade_unconfirmed_archive_reply(content: str, matched_tasks: list[dict[str, Any]]) -> str:
    if not any(_task_uses_auto_archive_workflow(task) and not _task_archive_write_succeeded(task) for task in matched_tasks):
        return content
    if not _reply_claims_archive_success(content):
        return content
    sanitized = str(content or "").strip()
    replacements = (
        ("已归档，保存到", "待归档，目标文档"),
        ("已归档，保存至", "待归档，目标文档"),
        ("已归档", "待归档"),
        ("记录已保存", "记录待保存"),
        ("已保存", "待保存"),
        ("已写入", "待写入"),
        ("写入完成", "待写入"),
        ("保存到", "目标文档"),
    )
    for old, new in replacements:
        sanitized = sanitized.replace(old, new)
    notice = "⚠️ 当前只完成信息整理，尚未真实写入飞书群文档；请以群文档实际记录为准。"
    return f"{notice}\n\n{sanitized}" if sanitized else notice


def _resolve_employee_id_from_connector(project_id: str, connector: dict[str, Any]) -> str:
    from stores.factory import employee_store, project_store

    target = str(connector.get("agent_name") or "").strip()
    if not target:
        return ""
    normalized_target = target.lower()
    for member in project_store.list_members(project_id):
        employee_id = str(getattr(member, "employee_id", "") or "").strip()
        if not employee_id:
            continue
        employee = employee_store.get(employee_id)
        employee_name = str(getattr(employee, "name", "") or "").strip()
        if normalized_target in {employee_id.lower(), employee_name.lower()}:
            return employee_id
    return ""


def _build_feishu_reply_text(content: str) -> str:
    normalized = str(content or "").strip()
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
) -> None:
    _require_feishu_sdk()
    client = (
        lark.Client.builder()
        .app_id(str(connector.get("app_id") or "").strip())
        .app_secret(str(connector.get("app_secret") or "").strip())
        .build()
    )
    request = (
        ReplyMessageRequest.builder()
        .message_id(message_id)
        .request_body(
            ReplyMessageRequestBody.builder()
            .content(json.dumps({"text": _build_feishu_reply_text(content)}, ensure_ascii=False))
            .msg_type("text")
            .reply_in_thread(bool(reply_in_thread))
            .uuid(uuid.uuid4().hex[:32])
            .build()
        )
        .build()
    )
    response = await asyncio.to_thread(client.im.v1.message.reply, request)
    if not response.success():
        raise RuntimeError(
            f"reply feishu message failed, code={response.code}, msg={response.msg}, "
            f"log_id={response.get_log_id()}"
        )


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

    binding = _find_feishu_project_chat_session_binding(
        connector_id=connector_id,
        chat_id=chat_id,
        chat_type=chat_type,
        projects_router=projects_router,
    )
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
    previous_messages = projects_router.project_chat_store.list_messages(
        project_id,
        username,
        limit=80,
        chat_session_id=chat_session_id,
    )
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

    text_message = _parse_feishu_text_message(event)
    resources = _extract_feishu_message_resources(message)
    downloaded_resources: list[dict[str, str]] = []
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
    image_urls = [str(item.get("url") or "").strip() for item in downloaded_resources if str(item.get("url") or "").strip()]
    attachment_files = [item for item in downloaded_resources if item.get("path")]
    if image_urls:
        _merge_source_image_urls(source_context, image_urls)
    if attachment_files:
        source_context["attachment_files"] = attachment_files

    if not text_message:
        resource = resources[0] if resources else {}
        user_record = projects_router._append_chat_record(
            project_id=project_id,
            username=username,
            role="user",
            content=(
                f"（飞书发送了{resource.get('label') or '非文本消息'}：{image_urls[0]}）"
                if image_urls
                else f"（飞书发送了非文本消息：{str(getattr(message, 'message_type', '') or 'unknown')}）"
            ),
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
        merge_result = None
        if image_urls:
            try:
                merge_result = append_feishu_archive_attachments(
                    source_context=source_context,
                    attachment_urls=image_urls,
                    attachment_files=attachment_files,
                )
            except Exception:
                logger.exception(
                    "failed to append feishu image resource to latest archive",
                    extra={"connector_id": connector_id, "message_id": message_id},
                )
        assistant_text = ""
        if image_urls and merge_result and str(merge_result.get("status") or "") == "updated":
            if int(merge_result.get("uploaded_count") or 0) > 0:
                assistant_text = "已接收图片并上传到最近飞书归档记录的附件字段。"
            else:
                assistant_text = "已接收图片并合并到最近的飞书归档记录。"
        elif image_urls:
            assistant_text = "已接收图片，已保存到本地，等待可匹配的飞书归档记录。"
        else:
            assistant_text = "已接收飞书非文本消息，暂未生成可归档链接。"
        assistant_record = projects_router._append_chat_record(
            project_id=project_id,
            username=username,
            role="assistant",
            content=assistant_text,
            message_id=f"bot-reply-{uuid.uuid4().hex[:12]}",
            chat_session_id=chat_session_id,
        )
        await projects_router.publish_project_chat_record_realtime(
            project_id=project_id,
            username=username,
            chat_session_id=chat_session_id,
            message=assistant_record,
        )
        await projects_router.publish_project_chat_group_status_realtime(
            project_id=project_id,
            username=username,
            chat_session_id=chat_session_id,
            status="linked",
            message="当前飞书群已链接工作群",
            source_context=source_context,
        )
        return

    recent_image_urls = _recent_feishu_image_urls(previous_messages, source_context)
    if recent_image_urls:
        _merge_source_image_urls(source_context, recent_image_urls)

    auth_payload = {"sub": username, "role": "admin", "roles": ["admin"]}
    req = ProjectChatReq(
        message=text_message,
        message_id=message_id,
        assistant_message_id=f"bot-reply-{uuid.uuid4().hex[:12]}",
        chat_session_id=chat_session_id,
        chat_mode="system",
        chat_surface="main-chat",
        history=history,
        employee_id=_resolve_employee_id_from_connector(project_id, connector),
        system_prompt="\n\n".join(
            item
            for item in (
                str(connector.get("system_prompt") or "").strip(),
                _build_feishu_archive_truth_prompt(connector, source_context),
            )
            if item
        ),
        source_context=source_context,
        images=image_urls,
    )
    result = await run_project_chat_once(
        project_id=project_id,
        username=username,
        req=req,
        auth_payload=auth_payload,
        save_memory_snapshot=False,
        publish_realtime=True,
    )
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
        _build_confirmed_archive_reply(matched_tasks)
        or _build_failed_archive_reply(matched_tasks)
        or _downgrade_unconfirmed_archive_reply(result.content, matched_tasks)
    )
    await _reply_feishu_text(
        connector,
        message_id=message_id,
        content=reply_content,
        reply_in_thread=bool(thread_id),
    )
