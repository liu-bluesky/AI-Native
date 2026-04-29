"""Feishu group archive writer for global assistant listener tasks."""

from __future__ import annotations

import json
import logging
import re
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from core.config import get_api_data_dir
from services.bot_connector_service import get_bot_connector

logger = logging.getLogger(__name__)

_FEISHU_OPEN_API_BASE_URL = "https://open.feishu.cn"
_ARCHIVE_STATE_LOCK = threading.RLock()
_ARCHIVE_WORKFLOW = "feishu_bot_auto_archive_to_doc_table"
_ARCHIVE_ATTACHMENT_TEXT_COLUMN = "图片/附件"
_ARCHIVE_ATTACHMENT_COLUMN = "图片附件"
_CLI_FIELD_ID_CACHE: dict[tuple[str, str, str], str] = {}
_ARCHIVE_COLUMNS = (
    "归档时间",
    "类型",
    "标题",
    "摘要",
    "详细内容",
    "优先级",
    "负责人",
    "提出人",
    "来源群",
    _ARCHIVE_ATTACHMENT_TEXT_COLUMN,
    "消息链接",
    "聊天记录",
)
_ARCHIVE_BITABLE_COLUMNS = (*_ARCHIVE_COLUMNS, _ARCHIVE_ATTACHMENT_COLUMN)
_BITABLE_ATTACHMENT_FIELD_TYPE = 17
_LEGACY_ARCHIVE_COLUMNS = (
    "分类",
    "机器人",
    "external_chat_id",
    "connector_id",
    "external_message_id",
    "sender_id",
    "原始消息",
)
_STRUCTURED_FIELD_ALIASES = {
    "标题": "标题",
    "问题标题": "标题",
    "需求标题": "标题",
    "功能名称": "标题",
    "会议主题": "标题",
    "问题描述": "问题描述",
    "背景": "背景",
    "目标": "目标",
    "详细说明": "详细说明",
    "功能说明": "功能说明",
    "使用场景": "使用场景",
    "输入输出": "输入输出",
    "复现步骤": "复现步骤",
    "期望结果": "期望结果",
    "实际结果": "实际结果",
    "影响范围": "影响范围",
    "验收标准": "验收标准",
    "优先级": "优先级",
    "负责人": "负责人",
    "提出人": "提出人",
    "报告人": "提出人",
    "时间": "时间",
    "参会人": "参会人",
    "结论": "结论",
    "待办事项": "待办事项",
    "截止时间": "截止时间",
    "来源群": "来源群",
    "消息链接": "消息链接",
    "创建时间": "创建时间",
}
_SUMMARY_KEYS = ("问题描述", "背景", "目标", "功能说明", "详细说明", "结论", "待办事项")
_DETAIL_KEYS = (
    "问题描述",
    "背景",
    "目标",
    "详细说明",
    "使用场景",
    "功能说明",
    "输入输出",
    "复现步骤",
    "期望结果",
    "实际结果",
    "影响范围",
    "验收标准",
    "时间",
    "参会人",
    "结论",
    "待办事项",
    "截止时间",
)
_CATEGORY_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("bug", ("bug", "BUG", "缺陷", "问题", "报错", "异常", "复现", "期望结果", "实际结果")),
    ("需求", ("需求", "诉求", "想要", "希望", "需要支持")),
    ("功能", ("功能", "能力", "模块", "特性", "feature", "Feature")),
    ("会议", ("会议", "开会", "会前", "会后", "参会", "待办事项", "会议纪要")),
)


def is_feishu_auto_archive_action(action: dict[str, Any] | None) -> bool:
    payload = action if isinstance(action, dict) else {}
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    return str(params.get("workflow") or "").strip() == _ARCHIVE_WORKFLOW


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _archive_state_path() -> Path:
    return get_api_data_dir() / "feishu-archive-docs.json"


def _read_archive_state() -> dict[str, Any]:
    path = _archive_state_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "archives": {}}
    if not isinstance(payload, dict):
        return {"version": 1, "archives": {}}
    archives = payload.get("archives")
    if not isinstance(archives, dict):
        payload["archives"] = {}
    return payload


def _write_archive_state(payload: dict[str, Any]) -> None:
    path = _archive_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _feishu_open_api_url(path: str) -> str:
    normalized = "/" + str(path or "").lstrip("/")
    return f"{_FEISHU_OPEN_API_BASE_URL}{normalized}"


def _post_feishu_json(path: str, *, token: str, payload: dict[str, Any], timeout: int = 15) -> dict[str, Any]:
    response = requests.post(
        _feishu_open_api_url(path),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"},
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    body = response.json()
    if int(body.get("code") or 0) != 0:
        raise RuntimeError(str(body.get("msg") or "飞书接口调用失败"))
    data = body.get("data")
    return data if isinstance(data, dict) else {}


def _patch_feishu_json(path: str, *, token: str, payload: dict[str, Any], timeout: int = 15) -> dict[str, Any]:
    response = requests.patch(
        _feishu_open_api_url(path),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"},
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    body = response.json()
    if int(body.get("code") or 0) != 0:
        raise RuntimeError(str(body.get("msg") or "飞书接口调用失败"))
    data = body.get("data")
    return data if isinstance(data, dict) else {}


def _patch_feishu_json(path: str, *, token: str, payload: dict[str, Any], timeout: int = 15) -> dict[str, Any]:
    response = requests.patch(
        _feishu_open_api_url(path),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"},
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    body = response.json()
    if int(body.get("code") or 0) != 0:
        raise RuntimeError(str(body.get("msg") or "飞书接口调用失败"))
    data = body.get("data")
    return data if isinstance(data, dict) else {}


def _get_feishu_json(path: str, *, token: str, params: dict[str, Any] | None = None, timeout: int = 15) -> dict[str, Any]:
    response = requests.get(
        _feishu_open_api_url(path),
        headers={"Authorization": f"Bearer {token}"},
        params=params or {},
        timeout=timeout,
    )
    response.raise_for_status()
    body = response.json()
    if int(body.get("code") or 0) != 0:
        raise RuntimeError(str(body.get("msg") or "飞书接口调用失败"))
    data = body.get("data")
    return data if isinstance(data, dict) else {}


def _get_tenant_access_token(connector: dict[str, Any]) -> str:
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


def _connector_domain(connector: dict[str, Any]) -> str:
    raw = (
        connector.get("tenant_domain")
        or connector.get("domain")
        or connector.get("feishu_domain")
        or connector.get("base_url")
        or ""
    )
    domain = str(raw or "").strip().removeprefix("https://").removeprefix("http://").strip("/")
    return domain or "liulantian.feishu.cn"


def _drive_doc_type(writer_type: str) -> str:
    if writer_type == "sheet":
        return "sheet"
    if writer_type == "bitable":
        return "bitable"
    return "docx"


def _query_drive_url(*, token: str, resource_id: str, writer_type: str) -> str:
    if not resource_id:
        return ""
    try:
        data = _post_feishu_json(
            "/open-apis/drive/v1/metas/batch_query",
            token=token,
            payload={
                "request_docs": [
                    {"doc_token": resource_id, "doc_type": _drive_doc_type(writer_type)}
                ],
                "with_url": True,
            },
        )
        metas = data.get("metas") if isinstance(data.get("metas"), list) else []
        for meta in metas:
            if isinstance(meta, dict) and str(meta.get("url") or "").strip():
                return str(meta.get("url") or "").strip()
    except Exception:
        logger.info("failed to query feishu archive document url", exc_info=True)
    return ""


def _doc_url(connector: dict[str, Any], resource_id: str, writer_type: str) -> str:
    token = str(resource_id or "").strip()
    if not token:
        return ""
    domain = _connector_domain(connector)
    path = "docx"
    if writer_type == "sheet":
        path = "sheets"
    elif writer_type == "bitable":
        path = "base"
    return f"https://{domain}/{path}/{token}"


def _try_open_link_permission(*, token: str, resource_id: str, writer_type: str) -> None:
    if not resource_id:
        return
    drive_type = "docx" if writer_type == "docx" else ("sheet" if writer_type == "sheet" else "bitable")
    try:
        _patch_feishu_json(
            f"/open-apis/drive/v1/permissions/{resource_id}/public?type={drive_type}",
            token=token,
            payload={
                "external_access": False,
                "security_entity": "anyone_can_view",
                "comment_entity": "anyone_can_view",
                "share_entity": "anyone",
                "link_share_entity": "tenant_readable",
                "invite_external": False,
            },
        )
    except Exception:
        logger.info("failed to open feishu archive link permission", exc_info=True)


def _clean_title_part(value: Any, fallback: str) -> str:
    text = str(value or "").strip() or fallback
    text = re.sub(r"[\\/:*?\"<>|#%&{}$!@`'=+\r\n\t]+", " ", text)
    return " ".join(text.split()).strip()[:80] or fallback


def _category_writer_config(action: dict[str, Any], category: str) -> dict[str, Any]:
    params = action.get("params") if isinstance(action.get("params"), dict) else {}
    categories = params.get("categories") if isinstance(params.get("categories"), dict) else {}
    category_value = categories.get(category)
    if isinstance(category_value, dict):
        return category_value
    if isinstance(category_value, str):
        return {"writer_type": category_value}
    return {}


def _normalize_writer_type(action: dict[str, Any], category: str) -> str:
    params = action.get("params") if isinstance(action.get("params"), dict) else {}
    category_config = _category_writer_config(action, category)
    raw = (
        category_config.get("writer_type")
        or category_config.get("target_type")
        or category_config.get("storage_type")
        or params.get("writer_type")
        or params.get("target_type")
        or params.get("storage_type")
        or params.get("archive_type")
        or "docx"
    )
    normalized = str(raw or "docx").strip().lower()
    aliases = {
        "doc": "docx",
        "document": "docx",
        "docs": "docx",
        "docx": "docx",
        "sheet": "sheet",
        "sheets": "sheet",
        "spreadsheet": "sheet",
        "table": "sheet",
        "base": "bitable",
        "bitable": "bitable",
        "多维表格": "bitable",
        "电子表格": "sheet",
        "文档": "docx",
    }
    return aliases.get(normalized, "docx")


def _normalize_writer_mode(action: dict[str, Any], category: str) -> str:
    params = action.get("params") if isinstance(action.get("params"), dict) else {}
    category_config = _category_writer_config(action, category)
    raw = (
        category_config.get("writer_mode")
        or category_config.get("writer_identity")
        or category_config.get("identity")
        or category_config.get("create_as")
        or category_config.get("as")
        or params.get("writer_mode")
        or params.get("writer_identity")
        or params.get("identity")
        or params.get("create_as")
        or params.get("as")
        or "bot_openapi"
    )
    normalized = str(raw or "bot_openapi").strip().lower().replace("-", "_")
    aliases = {
        "bot": "bot_openapi",
        "app": "bot_openapi",
        "openapi": "bot_openapi",
        "bot_openapi": "bot_openapi",
        "user": "lark_cli_user",
        "cli_user": "lark_cli_user",
        "user_cli": "lark_cli_user",
        "lark_cli_user": "lark_cli_user",
        "larkcli_user": "lark_cli_user",
    }
    return aliases.get(normalized, "bot_openapi")


def _infer_category(*, message_text: str, task: dict[str, Any], action: dict[str, Any]) -> str:
    params = action.get("params") if isinstance(action.get("params"), dict) else {}
    configured_categories = params.get("categories") if isinstance(params.get("categories"), dict) else {}
    text = "\n".join(
        str(item or "")
        for item in (
            message_text,
            task.get("title"),
            task.get("description"),
            action.get("label"),
        )
    )
    for category, aliases in _CATEGORY_ALIASES:
        if category in configured_categories and any(alias in text for alias in aliases):
            return category
    for category, aliases in _CATEGORY_ALIASES:
        if any(alias in text for alias in aliases):
            return category
    if configured_categories:
        first_category = str(next(iter(configured_categories.keys())) or "").strip()
        if first_category:
            return first_category
    return "未分类"


def _archive_key(*, connector_id: str, external_chat_id: str, category: str, writer_type: str, writer_mode: str = "bot_openapi") -> str:
    base = f"{connector_id}|{external_chat_id}|{category}"
    if writer_mode == "bot_openapi":
        return base if writer_type == "docx" else f"{base}|{writer_type}"
    return f"{base}|{writer_type}|{writer_mode}"


def _target_title(*, external_chat_name: str, category: str, bot_name: str, writer_type: str) -> str:
    target_kind = "文档" if writer_type == "docx" else "表格"
    return f"{external_chat_name}-{category}{target_kind}【{bot_name}】"


def _make_text_block(content: str) -> dict[str, Any]:
    return {
        "block_type": 2,
        "text": {
            "elements": [
                {"text_run": {"content": content, "text_element_style": {}}}
            ],
            "style": {},
        },
    }


def _append_text_to_document(*, token: str, document_id: str, content: str) -> dict[str, Any]:
    child_index = 0
    try:
        blocks_data = _get_feishu_json(
            f"/open-apis/docx/v1/documents/{document_id}/blocks",
            token=token,
            params={"page_size": 500},
        )
        items = blocks_data.get("items") if isinstance(blocks_data.get("items"), list) else []
        root_children = [item for item in items if isinstance(item, dict) and str(item.get("parent_id") or "") == document_id]
        child_index = len(root_children)
    except Exception:
        logger.info("failed to list feishu document blocks before append", exc_info=True)
    return _post_feishu_json(
        f"/open-apis/docx/v1/documents/{document_id}/blocks/{document_id}/children",
        token=token,
        payload={"children": [_make_text_block(content)], "index": child_index},
        timeout=20,
    )


def _create_document(*, token: str, title: str, folder_token: str = "") -> dict[str, Any]:
    payload: dict[str, Any] = {"title": title}
    if folder_token:
        payload["folder_token"] = folder_token
    data = _post_feishu_json("/open-apis/docx/v1/documents", token=token, payload=payload)
    document = data.get("document") if isinstance(data.get("document"), dict) else data
    document_id = str(document.get("document_id") or "").strip()
    if not document_id:
        raise RuntimeError("飞书创建文档后未返回 document_id")
    return document


def _create_spreadsheet(*, token: str, title: str, folder_token: str = "") -> dict[str, Any]:
    payload: dict[str, Any] = {"title": title}
    if folder_token:
        payload["folder_token"] = folder_token
    data = _post_feishu_json("/open-apis/sheets/v3/spreadsheets", token=token, payload=payload)
    spreadsheet = data.get("spreadsheet") if isinstance(data.get("spreadsheet"), dict) else data
    spreadsheet_token = str(spreadsheet.get("spreadsheet_token") or spreadsheet.get("token") or "").strip()
    if not spreadsheet_token:
        raise RuntimeError("飞书创建电子表格后未返回 spreadsheet_token")
    return spreadsheet


def _resolve_first_sheet_id(*, token: str, spreadsheet_token: str) -> str:
    data = _get_feishu_json(
        f"/open-apis/sheets/v3/spreadsheets/{spreadsheet_token}/sheets/query",
        token=token,
    )
    sheets = data.get("sheets") if isinstance(data.get("sheets"), list) else []
    for sheet in sheets:
        if isinstance(sheet, dict) and str(sheet.get("sheet_id") or "").strip():
            return str(sheet.get("sheet_id") or "").strip()
    raise RuntimeError("飞书电子表格未返回可写入的 sheet_id")


def _append_sheet_values(*, token: str, spreadsheet_token: str, sheet_id: str, rows: list[list[Any]]) -> dict[str, Any]:
    return _post_feishu_json(
        f"/open-apis/sheets/v2/spreadsheets/{spreadsheet_token}/values_append",
        token=token,
        payload={"valueRange": {"range": f"{sheet_id}!A:I", "values": rows}},
        timeout=20,
    )


def _create_bitable_app(*, token: str, title: str, folder_token: str = "") -> dict[str, Any]:
    payload: dict[str, Any] = {"name": title}
    if folder_token:
        payload["folder_token"] = folder_token
    data = _post_feishu_json("/open-apis/bitable/v1/apps", token=token, payload=payload)
    app = data.get("app") if isinstance(data.get("app"), dict) else data
    app_token = str(app.get("app_token") or "").strip()
    if not app_token:
        raise RuntimeError("飞书创建多维表格后未返回 app_token")
    return app


def _archive_cli_field_spec(column: str) -> dict[str, str]:
    if column == _ARCHIVE_ATTACHMENT_COLUMN:
        return {"name": column, "type": "attachment"}
    return {"name": column, "type": "text"}


def _archive_openapi_field_spec(column: str) -> dict[str, Any]:
    if column == _ARCHIVE_ATTACHMENT_COLUMN:
        return {"field_name": column, "type": _BITABLE_ATTACHMENT_FIELD_TYPE}
    return {"field_name": column, "type": 1}


def _archive_record_fields_for_bitable(fields: dict[str, Any]) -> dict[str, Any]:
    return {
        column: fields.get(column, "")
        for column in _ARCHIVE_COLUMNS
        if column != _ARCHIVE_ATTACHMENT_COLUMN
    }


def _create_bitable_table(*, token: str, app_token: str, category: str) -> dict[str, Any]:
    fields = [_archive_openapi_field_spec(column) for column in _ARCHIVE_BITABLE_COLUMNS]
    data = _post_feishu_json(
        f"/open-apis/bitable/v1/apps/{app_token}/tables",
        token=token,
        payload={"table": {"name": category[:100] or "归档", "default_view_name": "归档视图", "fields": fields}},
        timeout=20,
    )
    table = data.get("table") if isinstance(data.get("table"), dict) else data
    table_id = str(table.get("table_id") or "").strip()
    if not table_id:
        raise RuntimeError("飞书创建多维表格数据表后未返回 table_id")
    return table


def _create_bitable_record(*, token: str, app_token: str, table_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    data = _post_feishu_json(
        f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records",
        token=token,
        payload={"fields": fields},
        timeout=20,
    )
    record = data.get("record") if isinstance(data.get("record"), dict) else data
    return record


def _patch_bitable_record(
    *,
    token: str,
    app_token: str,
    table_id: str,
    record_id: str,
    fields: dict[str, Any],
) -> dict[str, Any]:
    data = _patch_feishu_json(
        f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}",
        token=token,
        payload={"fields": fields},
        timeout=20,
    )
    record = data.get("record") if isinstance(data.get("record"), dict) else data
    return record


def _clean_markdown_label(value: str) -> str:
    text = re.sub(r"^[\s\-*>#0-9.、]+", "", str(value or "").strip())
    text = re.sub(r"\*+", "", text)
    text = text.strip(" ：:")
    return text


def _structured_label_pattern() -> str:
    labels = sorted(_STRUCTURED_FIELD_ALIASES.keys(), key=len, reverse=True)
    return "|".join(re.escape(label) for label in labels)


def _normalize_structured_archive_text(text: str) -> str:
    normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    label_pattern = _structured_label_pattern()
    if not label_pattern:
        return normalized
    # Some LLM replies collapse the whole archive payload into one Markdown line:
    # "1. **标题**xxx 2. **问题描述**yyy - **负责人**：zzz".
    # Split known field labels back into parser-friendly lines.
    normalized = re.sub(
        rf"(?<!^)(?=\s*\d+[.)、]\s*\*\*(?:{label_pattern})\*\*)",
        "\n",
        normalized,
    )
    normalized = re.sub(
        rf"(?<!^)(?=\s*[-*]\s*\*\*(?:{label_pattern})\*\*)",
        "\n",
        normalized,
    )
    normalized = re.sub(
        rf"[；;]\s*(?=(?:\*\*)?(?:{label_pattern})(?:\*\*)?\s*[：:])",
        "\n",
        normalized,
    )
    normalized = re.sub(
        rf"[。]\s*(?=(?:\*\*)?(?:{label_pattern})(?:\*\*)?\s*[：:])",
        "\n",
        normalized,
    )
    return normalized


def _extract_structured_archive_fields(message_text: str) -> dict[str, str]:
    text = str(message_text or "")
    marker = "【结构化内容】"
    if marker in text:
        text = text.split(marker, 1)[1]
    text = _normalize_structured_archive_text(text)
    parsed: dict[str, str] = {}
    current_key = ""
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        match = re.match(
            r"^\s*(?:[-*]\s*)?(?:\d+[.)、]\s*)?(?:\*\*)?([^：:\n*]{1,24})(?:\*\*)?\s*(?:[：:]|\s+)?\s*(.*)$",
            line,
        )
        if match:
            label = _clean_markdown_label(match.group(1))
            key = _STRUCTURED_FIELD_ALIASES.get(label)
            if key:
                value = str(match.group(2) or "").strip()
                parsed[key] = value
                current_key = key
                continue
        if current_key and (raw_line.startswith(" ") or raw_line.lstrip().startswith(("-", "*")) or re.match(r"^\s*\d+[.)、]", raw_line)):
            previous = parsed.get(current_key, "").strip()
            parsed[current_key] = (previous + "\n" + line.strip()).strip()
    return {key: value for key, value in parsed.items() if str(value or "").strip()}


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _compact_text(value: str, limit: int = 260) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _compact_short_field(value: Any) -> str:
    return " ".join(str(value or "").split()).strip(" \t\r\n。；;，,、")


def _build_detail_text(structured: dict[str, str], fallback: str) -> str:
    lines = [f"{key}：{structured[key]}" for key in _DETAIL_KEYS if str(structured.get(key) or "").strip()]
    if lines:
        return "\n".join(lines)[:12000]
    return _compact_text(fallback, 4000)


def _attachment_item_text(item: Any) -> str:
    if isinstance(item, dict):
        return str(
            item.get("url")
            or item.get("file_url")
            or item.get("path")
            or item.get("file_path")
            or item.get("local_path")
            or item.get("filename")
            or item.get("name")
            or ""
        ).strip()
    return str(item or "").strip()


def _source_attachment_text(source_context: dict[str, Any]) -> str:
    values: list[str] = []
    for key in ("attachments", "attachment_urls", "image_urls", "file_urls", "images", "files"):
        value = source_context.get(key)
        if isinstance(value, list):
            values.extend(_attachment_item_text(item) for item in value if _attachment_item_text(item))
        elif str(value or "").strip():
            values.append(str(value).strip())
    return "\n".join(values)


def _normalize_attachment_file_items(
    *,
    attachment_files: list[Any] | None = None,
    source_context: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    context = source_context if isinstance(source_context, dict) else {}
    raw_items: list[Any] = []
    if isinstance(attachment_files, list):
        raw_items.extend(attachment_files)
    for key in ("attachment_files", "downloaded_resources"):
        value = context.get(key)
        if isinstance(value, list):
            raw_items.extend(value)
        elif value:
            raw_items.append(value)

    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw_items:
        if isinstance(item, dict):
            raw_path = item.get("path") or item.get("file_path") or item.get("local_path") or ""
            raw_name = item.get("filename") or item.get("name") or ""
            raw_url = item.get("url") or item.get("file_url") or ""
        else:
            raw_path = item
            raw_name = ""
            raw_url = ""
        path = str(raw_path or "").strip()
        if not path:
            continue
        file_path = Path(path)
        if not file_path.is_file():
            logger.warning("skip missing feishu archive attachment file: %s", path)
            continue
        resolved = str(file_path.resolve())
        if resolved in seen:
            continue
        seen.add(resolved)
        filename = Path(str(raw_name or "")).name.strip() or file_path.name
        normalized.append({"path": resolved, "filename": filename, "url": str(raw_url or "").strip()})
    return normalized


def _upload_cli_bitable_attachments(
    *,
    app_token: str,
    table_id: str,
    record_id: str,
    attachments: list[dict[str, str]],
    field_name: str = _ARCHIVE_ATTACHMENT_COLUMN,
) -> int:
    uploaded = 0
    field_identifier = _resolve_cli_bitable_field_identifier(
        app_token=app_token,
        table_id=table_id,
        field_name=field_name,
    )
    for attachment in attachments:
        path = str(attachment.get("path") or "").strip()
        if not path:
            continue
        file_path = Path(path)
        relative_file = f"./{file_path.name}"
        command = [
            "base",
            "+record-upload-attachment",
            "--as",
            "user",
            "--base-token",
            app_token,
            "--table-id",
            table_id,
            "--record-id",
            record_id,
            "--field-id",
            field_identifier,
            "--file",
            relative_file,
        ]
        filename = str(attachment.get("filename") or "").strip()
        _append_optional_arg(command, "--name", filename)
        _run_lark_cli_json(command, timeout=180, cwd=file_path.parent)
        uploaded += 1
    return uploaded


def _merge_attachment_text(existing: Any, attachments: list[str]) -> str:
    values: list[str] = []
    raw_existing = str(existing or "").strip()
    if raw_existing and raw_existing != "无":
        values.extend(item.strip() for item in raw_existing.splitlines() if item.strip())
    values.extend(str(item or "").strip() for item in attachments if str(item or "").strip())
    seen: set[str] = set()
    result: list[str] = []
    for item in values:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return "\n".join(result)


def _build_archive_fields(
    *,
    category: str,
    message_text: str,
    source_context: dict[str, Any],
    connector_id: str,
    bot_name: str,
    archived_at: str,
) -> dict[str, str]:
    external_chat_name = str(source_context.get("external_chat_name") or source_context.get("group_name") or "").strip()
    external_chat_id = str(source_context.get("external_chat_id") or "").strip()
    raw_message = str(message_text or "").strip() or "（空消息）"
    structured = _extract_structured_archive_fields(raw_message)
    message_link = _first_nonempty(structured.get("消息链接"), source_context.get("message_link"), source_context.get("external_message_url"))
    title = _first_nonempty(structured.get("标题"), _compact_text(raw_message, 80), f"{category}记录")
    summary = _first_nonempty(*[structured.get(key) for key in _SUMMARY_KEYS], structured.get("影响范围"), raw_message)
    priority = _first_nonempty(_compact_short_field(structured.get("优先级")), "未标注")
    assignee = _first_nonempty(_compact_short_field(structured.get("负责人")), "未指定")
    reporter = _first_nonempty(
        _compact_short_field(structured.get("提出人")),
        source_context.get("sender_name"),
        source_context.get("sender_id"),
        "未记录",
    )
    fields = {
        "归档时间": _first_nonempty(structured.get("创建时间"), archived_at),
        "类型": category,
        "标题": _compact_text(title, 120),
        "摘要": _compact_text(summary, 500),
        "详细内容": _build_detail_text(structured, raw_message),
        "优先级": priority,
        "负责人": assignee,
        "提出人": reporter,
        "来源群": external_chat_name or external_chat_id or "未知群",
        "图片/附件": _source_attachment_text(source_context) or "无",
        "消息链接": message_link or "无",
        "聊天记录": raw_message[:12000],
        "分类": category,
        "机器人": bot_name,
        "external_chat_id": external_chat_id,
        "connector_id": connector_id,
        "external_message_id": str(source_context.get("external_message_id") or source_context.get("message_id") or "").strip(),
        "sender_id": str(source_context.get("sender_id") or "").strip(),
        "原始消息": raw_message,
    }
    return fields


def _archive_row(fields: dict[str, Any]) -> list[Any]:
    return [fields.get(column, "") for column in _ARCHIVE_COLUMNS]


def _build_archive_entry(fields: dict[str, str], source_context: dict[str, Any]) -> str:
    lines = [f"{column}：{fields.get(column, '')}" for column in _ARCHIVE_COLUMNS if str(fields.get(column, "")).strip()]
    source_type = str(source_context.get("source_type") or "").strip()
    thread_key = str(source_context.get("thread_key") or "").strip()
    if source_type:
        lines.append(f"来源类型：{source_type}")
    if thread_key:
        lines.append(f"会话线索：{thread_key}")
    lines.extend(["", "---", ""])
    return "\n".join(lines)[:12000]


def _extract_cli_json(stdout: str) -> dict[str, Any]:
    text = str(stdout or "").strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else {"value": payload}
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    latest: Any = None
    for match in re.finditer(r"[\{\[]", text):
        try:
            candidate, _ = decoder.raw_decode(text[match.start():])
        except json.JSONDecodeError:
            continue
        latest = candidate
    if isinstance(latest, dict):
        return latest
    if latest is not None:
        return {"value": latest}
    return {"raw_output": text}


def _run_lark_cli_json(args: list[str], *, timeout: int = 90, cwd: Path | str | None = None) -> dict[str, Any]:
    command = ["lark-cli", *args]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            cwd=str(cwd) if cwd is not None else None,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("未找到 lark-cli，请先安装 @larksuite/cli 并重新启动服务") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("lark-cli 执行超时，请确认已完成用户登录授权") from exc
    if completed.returncode != 0:
        output = (completed.stderr or completed.stdout or "").strip()[:800]
        raise RuntimeError(f"lark-cli 执行失败，请先确认已执行 lark-cli auth login：{output}")
    return _extract_cli_json(completed.stdout)


def _find_cli_value(payload: Any, keys: tuple[str, ...]) -> str:
    key_set = {key.lower() for key in keys}
    if isinstance(payload, dict):
        for key, value in payload.items():
            if str(key).lower() in key_set and str(value or "").strip():
                return str(value).strip()
        for value in payload.values():
            found = _find_cli_value(value, keys)
            if found:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _find_cli_value(item, keys)
            if found:
                return found
    return ""


def _find_cli_path_value(payload: Any, paths: tuple[tuple[str, ...], ...]) -> str:
    for path in paths:
        current = payload
        for key in path:
            if isinstance(current, dict):
                current = current.get(key)
                continue
            if isinstance(current, list) and str(key).isdigit():
                index = int(key)
                current = current[index] if 0 <= index < len(current) else None
                continue
            current = None
            break
        if str(current or "").strip():
            return str(current).strip()
    return ""


def _find_cli_table_id(payload: dict[str, Any]) -> str:
    return _find_cli_path_value(
        payload,
        (
            ("table", "table_id"),
            ("table", "id"),
            ("data", "table", "table_id"),
            ("data", "table", "id"),
        ),
    ) or _find_cli_value(payload, ("table_id", "tableId"))


def _find_cli_record_id(payload: dict[str, Any]) -> str:
    found = _find_cli_path_value(
        payload,
        (
            ("record", "record_id"),
            ("record", "id"),
            ("record", "record_id_list", "0"),
            ("records", "0", "record_id"),
            ("records", "0", "id"),
            ("data", "record", "record_id"),
            ("data", "record", "id"),
            ("data", "record", "record_id_list", "0"),
            ("data", "record_id"),
            ("data", "id"),
            ("data", "records", "0", "record_id"),
            ("data", "records", "0", "id"),
            ("data", "data", "record", "record_id"),
            ("data", "data", "record", "id"),
            ("data", "data", "record", "record_id_list", "0"),
            ("data", "data", "record_id"),
            ("data", "data", "id"),
            ("data", "data", "records", "0", "record_id"),
            ("data", "data", "records", "0", "id"),
        ),
    ) or _find_cli_value(payload, ("record_id", "recordId"))
    if found:
        return found

    def find_record_like_id(value: Any) -> str:
        if isinstance(value, dict):
            for key, item in value.items():
                if str(key).lower() == "id":
                    candidate = str(item or "").strip()
                    if candidate.startswith("rec"):
                        return candidate
            for item in value.values():
                candidate = find_record_like_id(item)
                if candidate:
                    return candidate
        elif isinstance(value, list):
            for item in value:
                candidate = find_record_like_id(item)
                if candidate:
                    return candidate
        return ""

    return find_record_like_id(payload)


def _append_optional_arg(command: list[str], flag: str, value: str) -> None:
    if str(value or "").strip():
        command.extend([flag, str(value).strip()])


def _with_bitable_table_url(url: str, table_id: str) -> str:
    base_url = str(url or "").strip()
    table = str(table_id or "").strip()
    if not base_url or not table or "?table=" in base_url or "&table=" in base_url:
        return base_url
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}table={table}"


def _cli_field_type(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"17", "attachment"}:
        return "attachment"
    return raw


def _extract_cli_field_refs(payload: dict[str, Any]) -> dict[str, dict[str, str]]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    raw_fields = data.get("fields") if isinstance(data, dict) else []
    fields: dict[str, dict[str, str]] = {}
    if isinstance(raw_fields, list):
        for item in raw_fields:
            if isinstance(item, dict):
                name = str(item.get("name") or item.get("field_name") or "").strip()
                field_type = _cli_field_type(item.get("type") or item.get("ui_type") or item.get("uiType"))
                field_id = str(item.get("id") or item.get("field_id") or item.get("fieldId") or "").strip()
            else:
                name = str(item or "").strip()
                field_type = ""
                field_id = ""
            if name:
                fields[name] = {"type": field_type, "id": field_id}
    return fields


def _extract_cli_fields(payload: dict[str, Any]) -> dict[str, str]:
    return {name: item.get("type", "") for name, item in _extract_cli_field_refs(payload).items()}


def _cache_cli_field_refs(app_token: str, table_id: str, field_refs: dict[str, dict[str, str]]) -> None:
    app = str(app_token or "").strip()
    table = str(table_id or "").strip()
    if not app or not table:
        return
    for name, item in field_refs.items():
        field_id = str(item.get("id") or "").strip()
        if name:
            _CLI_FIELD_ID_CACHE[(app, table, name)] = field_id or name


def _find_cli_field_id(payload: dict[str, Any]) -> str:
    return _find_cli_path_value(
        payload,
        (
            ("field", "id"),
            ("field", "field_id"),
            ("data", "field", "id"),
            ("data", "field", "field_id"),
            ("data", "id"),
            ("data", "field_id"),
        ),
    ) or _find_cli_value(payload, ("field_id", "fieldId"))


def _resolve_cli_bitable_field_identifier(*, app_token: str, table_id: str, field_name: str) -> str:
    name = str(field_name or "").strip()
    if not name:
        return _ARCHIVE_ATTACHMENT_COLUMN
    if name.startswith("fld"):
        return name
    cache_key = (str(app_token or "").strip(), str(table_id or "").strip(), name)
    cached = _CLI_FIELD_ID_CACHE.get(cache_key, "")
    if cached:
        return cached
    payload = _run_lark_cli_json([
        "base",
        "+field-list",
        "--as",
        "user",
        "--base-token",
        app_token,
        "--table-id",
        table_id,
    ])
    _cache_cli_field_refs(app_token, table_id, _extract_cli_field_refs(payload))
    return _CLI_FIELD_ID_CACHE.get(cache_key, "") or name


def _next_attachment_field_name(existing_fields: dict[str, str]) -> str:
    preferred = "图片附件"
    if preferred not in existing_fields:
        return preferred
    index = 2
    while f"{preferred}{index}" in existing_fields:
        index += 1
    return f"{preferred}{index}"


def _preferred_existing_attachment_field(existing_fields: dict[str, str]) -> str:
    for name in (_ARCHIVE_ATTACHMENT_COLUMN, _ARCHIVE_ATTACHMENT_TEXT_COLUMN, "图片附件2", "附件", "图片"):
        if existing_fields.get(name) == "attachment":
            return name
    for name, field_type in existing_fields.items():
        if field_type == "attachment":
            return name
    return ""


def _ensure_cli_bitable_fields(
    *,
    app_token: str,
    table_id: str,
    columns: tuple[str, ...] = _ARCHIVE_BITABLE_COLUMNS,
    preferred_attachment_field_name: str = "",
) -> str:
    payload = _run_lark_cli_json([
        "base",
        "+field-list",
        "--as",
        "user",
        "--base-token",
        app_token,
        "--table-id",
        table_id,
    ])
    field_refs = _extract_cli_field_refs(payload)
    _cache_cli_field_refs(app_token, table_id, field_refs)
    existing_fields = {name: item.get("type", "") for name, item in field_refs.items()}
    preferred_attachment_field_name = str(preferred_attachment_field_name or "").strip()
    canonical_attachment_field_name = _preferred_existing_attachment_field(existing_fields)
    if canonical_attachment_field_name:
        attachment_field_name = canonical_attachment_field_name
    elif preferred_attachment_field_name and existing_fields.get(preferred_attachment_field_name) == "attachment":
        attachment_field_name = preferred_attachment_field_name
    else:
        attachment_field_name = _ARCHIVE_ATTACHMENT_COLUMN
    for column in columns:
        if column == _ARCHIVE_ATTACHMENT_COLUMN:
            if existing_fields.get(column) == "attachment":
                attachment_field_name = column
                continue
            if column in existing_fields:
                attachment_field_name = _preferred_existing_attachment_field(existing_fields)
                if attachment_field_name:
                    continue
                attachment_field_name = _next_attachment_field_name(existing_fields)
            else:
                attachment_field_name = column
            created_field_payload = _run_lark_cli_json([
                "base",
                "+field-create",
                "--as",
                "user",
                "--base-token",
                app_token,
                "--table-id",
                table_id,
                "--json",
                json.dumps({"name": attachment_field_name, "type": "attachment"}, ensure_ascii=False),
            ])
            existing_fields[attachment_field_name] = "attachment"
            field_id = _find_cli_field_id(created_field_payload)
            if field_id:
                _CLI_FIELD_ID_CACHE[(app_token, table_id, attachment_field_name)] = field_id
            continue
        if column in existing_fields:
            continue
        created_field_payload = _run_lark_cli_json([
            "base",
            "+field-create",
            "--as",
            "user",
            "--base-token",
            app_token,
            "--table-id",
            table_id,
            "--json",
            json.dumps(_archive_cli_field_spec(column), ensure_ascii=False),
        ])
        existing_fields[column] = _archive_cli_field_spec(column)["type"]
        field_id = _find_cli_field_id(created_field_payload)
        if field_id:
            _CLI_FIELD_ID_CACHE[(app_token, table_id, column)] = field_id
    return attachment_field_name


def _write_cli_docx_archive(*, existing: dict[str, Any], title: str, folder_token: str, entry: str) -> tuple[dict[str, Any], bool]:
    document_id = str(existing.get("document_id") or existing.get("doc_id") or "").strip()
    created = False
    if not document_id:
        command = [
            "docs",
            "+create",
            "--as",
            "user",
            "--title",
            title,
            "--markdown",
            f"# {title}\n\n归档范围：当前飞书群 + 当前机器人 + 分类\n\n---\n\n{entry}",
        ]
        _append_optional_arg(command, "--folder-token", folder_token)
        payload = _run_lark_cli_json(command)
        document_id = _find_cli_value(payload, ("document_id", "doc_id", "obj_token", "token"))
        if not document_id:
            raise RuntimeError("lark-cli 创建文档后未返回 document_id")
        return {
            "document_id": document_id,
            "doc_id": document_id,
            "doc_url": _find_cli_value(payload, ("doc_url", "url", "share_url")),
        }, True
    payload = _run_lark_cli_json(["docs", "+update", "--as", "user", "--doc", document_id, "--mode", "append", "--markdown", entry])
    return {
        "document_id": document_id,
        "doc_id": document_id,
        "doc_url": str(existing.get("doc_url") or _find_cli_value(payload, ("doc_url", "url", "share_url")) or "").strip(),
    }, created


def _write_cli_sheet_archive(*, existing: dict[str, Any], title: str, folder_token: str, row: list[Any]) -> tuple[dict[str, Any], bool]:
    spreadsheet_token = str(existing.get("spreadsheet_token") or existing.get("doc_id") or "").strip()
    sheet_id = str(existing.get("sheet_id") or "").strip()
    created = False
    if not spreadsheet_token:
        command = [
            "sheets",
            "+create",
            "--as",
            "user",
            "--title",
            title,
            "--headers",
            json.dumps(list(_ARCHIVE_COLUMNS), ensure_ascii=False),
            "--data",
            json.dumps([row], ensure_ascii=False),
        ]
        _append_optional_arg(command, "--folder-token", folder_token)
        payload = _run_lark_cli_json(command)
        spreadsheet_token = _find_cli_value(payload, ("spreadsheet_token", "spreadsheetToken", "token", "doc_id"))
        sheet_id = _find_cli_value(payload, ("sheet_id", "sheetId", "gid"))
        if not spreadsheet_token:
            raise RuntimeError("lark-cli 创建电子表格后未返回 spreadsheet_token")
        return {
            "spreadsheet_token": spreadsheet_token,
            "sheet_id": sheet_id,
            "document_id": spreadsheet_token,
            "doc_id": spreadsheet_token,
            "doc_url": _find_cli_value(payload, ("doc_url", "url", "share_url")),
        }, True
    if not sheet_id:
        raise RuntimeError("缺少 sheet_id，无法通过 lark-cli 追加电子表格记录")
    payload = _run_lark_cli_json([
        "sheets",
        "+append",
        "--as",
        "user",
        "--spreadsheet-token",
        spreadsheet_token,
        "--sheet-id",
        sheet_id,
        "--values",
        json.dumps([row], ensure_ascii=False),
    ])
    return {
        "spreadsheet_token": spreadsheet_token,
        "sheet_id": sheet_id,
        "document_id": spreadsheet_token,
        "doc_id": spreadsheet_token,
        "doc_url": str(existing.get("doc_url") or _find_cli_value(payload, ("doc_url", "url", "share_url")) or "").strip(),
    }, created


def _write_cli_bitable_archive(
    *,
    existing: dict[str, Any],
    title: str,
    folder_token: str,
    category: str,
    fields: dict[str, Any],
    attachment_files: list[Any] | None = None,
) -> tuple[dict[str, Any], bool]:
    app_token = str(existing.get("app_token") or existing.get("base_token") or existing.get("doc_id") or "").strip()
    table_id = str(existing.get("table_id") or "").strip()
    had_existing_table = bool(app_token and table_id)
    attachment_field_name = str(existing.get("attachment_field_name") or _ARCHIVE_ATTACHMENT_COLUMN).strip() or _ARCHIVE_ATTACHMENT_COLUMN
    doc_url = str(existing.get("doc_url") or "").strip()
    created = False
    if not app_token:
        command = ["base", "+base-create", "--as", "user", "--name", title]
        _append_optional_arg(command, "--folder-token", folder_token)
        base_payload = _run_lark_cli_json(command)
        app_token = _find_cli_value(base_payload, ("app_token", "base_token", "token"))
        doc_url = _find_cli_value(base_payload, ("doc_url", "url", "share_url"))
        if not app_token:
            raise RuntimeError("lark-cli 创建多维表格后未返回 app_token/base_token")
        table_payload = _run_lark_cli_json([
            "base",
            "+table-create",
            "--as",
            "user",
            "--base-token",
            app_token,
            "--name",
            category[:100] or "归档",
            "--fields",
            json.dumps([_archive_cli_field_spec(column) for column in _ARCHIVE_BITABLE_COLUMNS], ensure_ascii=False),
        ])
        table_id = _find_cli_table_id(table_payload)
        created = True
    if not table_id:
        raise RuntimeError("缺少 table_id，无法通过 lark-cli 追加多维表格记录")
    if had_existing_table:
        attachment_field_name = _ensure_cli_bitable_fields(
            app_token=app_token,
            table_id=table_id,
            preferred_attachment_field_name=attachment_field_name,
        )
    record_fields = _archive_record_fields_for_bitable(fields)
    record_payload = _run_lark_cli_json([
        "base",
        "+record-upsert",
        "--as",
        "user",
        "--base-token",
        app_token,
        "--table-id",
        table_id,
        "--json",
        json.dumps(record_fields, ensure_ascii=False),
    ])
    record_id = _find_cli_record_id(record_payload)
    attachments = _normalize_attachment_file_items(attachment_files=attachment_files)
    uploaded_count = 0
    if record_id and attachments:
        uploaded_count = _upload_cli_bitable_attachments(
            app_token=app_token,
            table_id=table_id,
            record_id=record_id,
            attachments=attachments,
            field_name=attachment_field_name,
        )
    elif attachments:
        logger.warning(
            "skip feishu bitable attachment upload because record_id was not found",
            extra={"table_id": table_id, "attachment_count": len(attachments)},
        )
    return {
        "app_token": app_token,
        "base_token": app_token,
        "table_id": table_id,
        "record_id": record_id,
        "last_attachment_upload_count": uploaded_count,
        "attachment_field_name": attachment_field_name,
        "document_id": app_token,
        "doc_id": app_token,
        "doc_url": _with_bitable_table_url(doc_url or _find_cli_value(record_payload, ("doc_url", "url", "share_url", "record_url")), table_id),
    }, created


def _write_docx_archive(
    *,
    token: str,
    existing: dict[str, Any],
    title: str,
    folder_token: str,
    entry: str,
) -> tuple[dict[str, Any], bool]:
    document_id = str(existing.get("document_id") or existing.get("doc_id") or "").strip()
    created = False
    if not document_id:
        document = _create_document(token=token, title=title, folder_token=folder_token)
        document_id = str(document.get("document_id") or "").strip()
        created = True
        _append_text_to_document(
            token=token,
            document_id=document_id,
            content=f"{title}\n\n归档范围：当前飞书群 + 当前机器人 + 分类\n\n---\n",
        )
    _append_text_to_document(token=token, document_id=document_id, content=entry)
    return {"document_id": document_id, "doc_id": document_id, "doc_url": str(existing.get("doc_url") or "").strip()}, created


def _write_sheet_archive(
    *,
    token: str,
    existing: dict[str, Any],
    title: str,
    folder_token: str,
    row: list[Any],
) -> tuple[dict[str, Any], bool]:
    spreadsheet_token = str(existing.get("spreadsheet_token") or existing.get("doc_id") or "").strip()
    sheet_id = str(existing.get("sheet_id") or "").strip()
    created = False
    if not spreadsheet_token:
        spreadsheet = _create_spreadsheet(token=token, title=title, folder_token=folder_token)
        spreadsheet_token = str(spreadsheet.get("spreadsheet_token") or spreadsheet.get("token") or "").strip()
        sheet_id = _resolve_first_sheet_id(token=token, spreadsheet_token=spreadsheet_token)
        created = True
        _append_sheet_values(token=token, spreadsheet_token=spreadsheet_token, sheet_id=sheet_id, rows=[list(_ARCHIVE_COLUMNS)])
    if not sheet_id:
        sheet_id = _resolve_first_sheet_id(token=token, spreadsheet_token=spreadsheet_token)
    _append_sheet_values(token=token, spreadsheet_token=spreadsheet_token, sheet_id=sheet_id, rows=[row])
    return {
        "spreadsheet_token": spreadsheet_token,
        "sheet_id": sheet_id,
        "document_id": spreadsheet_token,
        "doc_id": spreadsheet_token,
        "doc_url": str(existing.get("doc_url") or "").strip(),
    }, created


def _write_bitable_archive(
    *,
    token: str,
    existing: dict[str, Any],
    title: str,
    folder_token: str,
    category: str,
    fields: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    app_token = str(existing.get("app_token") or existing.get("doc_id") or "").strip()
    table_id = str(existing.get("table_id") or "").strip()
    created = False
    if not app_token:
        app = _create_bitable_app(token=token, title=title, folder_token=folder_token)
        app_token = str(app.get("app_token") or "").strip()
        table = _create_bitable_table(token=token, app_token=app_token, category=category)
        table_id = str(table.get("table_id") or "").strip()
        created = True
    if not table_id:
        raise RuntimeError("缺少 table_id，无法追加多维表格记录")
    record_fields = _archive_record_fields_for_bitable(fields)
    record = _create_bitable_record(token=token, app_token=app_token, table_id=table_id, fields=record_fields)
    return {
        "app_token": app_token,
        "table_id": table_id,
        "record_id": str(record.get("record_id") or "").strip(),
        "document_id": app_token,
        "doc_id": app_token,
        "doc_url": str(existing.get("doc_url") or record.get("record_url") or record.get("shared_url") or "").strip(),
    }, created


def archive_feishu_task_message(
    *,
    task: dict[str, Any],
    action: dict[str, Any],
    message_text: str,
    source_context: dict[str, Any] | None,
) -> dict[str, Any]:
    context = source_context if isinstance(source_context, dict) else {}
    connector_id = str(context.get("connector_id") or "").strip()
    external_chat_id = str(context.get("external_chat_id") or "").strip()
    if not connector_id:
        raise RuntimeError("缺少 connector_id，无法定位飞书机器人")
    if not external_chat_id:
        raise RuntimeError("缺少 external_chat_id，无法绑定当前飞书群文档")
    connector = get_bot_connector(connector_id)
    if not connector or str(connector.get("platform") or "").strip().lower() != "feishu":
        raise RuntimeError(f"未找到飞书连接器：{connector_id}")

    category = _infer_category(message_text=message_text, task=task, action=action)
    writer_type = _normalize_writer_type(action, category)
    writer_mode = _normalize_writer_mode(action, category)
    external_chat_name = _clean_title_part(context.get("external_chat_name") or context.get("group_name"), external_chat_id)
    bot_name = _clean_title_part(connector.get("agent_name") or connector.get("name"), "飞书机器人")
    document_title = _target_title(
        external_chat_name=external_chat_name,
        category=category,
        bot_name=bot_name,
        writer_type=writer_type,
    )
    archive_key = _archive_key(
        connector_id=connector_id,
        external_chat_id=external_chat_id,
        category=category,
        writer_type=writer_type,
        writer_mode=writer_mode,
    )
    params = action.get("params") if isinstance(action.get("params"), dict) else {}
    folder_token = str(params.get("folder_token") or params.get("folderToken") or "").strip()

    token = ""
    if writer_mode == "bot_openapi":
        token = _get_tenant_access_token(connector)
    archived_at = _now_iso()
    fields = _build_archive_fields(
        category=category,
        message_text=message_text,
        source_context=context,
        connector_id=connector_id,
        bot_name=bot_name,
        archived_at=archived_at,
    )
    attachment_files = _normalize_attachment_file_items(source_context=context)
    entry = _build_archive_entry(fields, context)

    with _ARCHIVE_STATE_LOCK:
        state = _read_archive_state()
        archives = state.setdefault("archives", {})
        existing = archives.get(archive_key) if isinstance(archives.get(archive_key), dict) else {}
        if writer_mode == "lark_cli_user":
            if writer_type == "sheet":
                resource, created = _write_cli_sheet_archive(
                    existing=existing,
                    title=document_title,
                    folder_token=folder_token,
                    row=_archive_row(fields),
                )
            elif writer_type == "bitable":
                resource, created = _write_cli_bitable_archive(
                    existing=existing,
                    title=document_title,
                    folder_token=folder_token,
                    category=category,
                    fields=fields,
                    attachment_files=attachment_files,
                )
            else:
                resource, created = _write_cli_docx_archive(
                    existing=existing,
                    title=document_title,
                    folder_token=folder_token,
                    entry=entry,
                )
        elif writer_type == "sheet":
            resource, created = _write_sheet_archive(
                token=token,
                existing=existing,
                title=document_title,
                folder_token=folder_token,
                row=_archive_row(fields),
            )
        elif writer_type == "bitable":
            resource, created = _write_bitable_archive(
                token=token,
                existing=existing,
                title=document_title,
                folder_token=folder_token,
                category=category,
                fields=fields,
            )
        else:
            resource, created = _write_docx_archive(
                token=token,
                existing=existing,
                title=document_title,
                folder_token=folder_token,
                entry=entry,
            )
        resource_id = str(resource.get("doc_id") or resource.get("document_id") or "").strip()
        if resource_id:
            if writer_mode == "bot_openapi":
                queried_url = _query_drive_url(token=token, resource_id=resource_id, writer_type=writer_type)
                resource["doc_url"] = str(resource.get("doc_url") or queried_url or _doc_url(connector, resource_id, writer_type)).strip()
                _try_open_link_permission(token=token, resource_id=resource_id, writer_type=writer_type)
            else:
                resource["doc_url"] = str(resource.get("doc_url") or _doc_url(connector, resource_id, writer_type)).strip()
        now = _now_iso()
        record = {
            **existing,
            **resource,
            "archive_key": archive_key,
            "connector_id": connector_id,
            "external_chat_id": external_chat_id,
            "external_chat_name": external_chat_name,
            "bot_name": bot_name,
            "category": category,
            "writer_type": writer_type,
            "writer_mode": writer_mode,
            "document_title": document_title,
            "created_at": str(existing.get("created_at") or now),
            "updated_at": now,
            "last_external_message_id": str(context.get("external_message_id") or "").strip(),
            "last_attachment_text": str(fields.get("图片/附件") or "").strip(),
            "last_attachment_upload_count": int(resource.get("last_attachment_upload_count") or existing.get("last_attachment_upload_count") or 0),
            "last_action_id": str(action.get("id") or "").strip(),
        }
        archives[archive_key] = record
        _write_archive_state(state)

    return {
        "status": "saved",
        "created": created,
        "archive_key": archive_key,
        "connector_id": connector_id,
        "external_chat_id": external_chat_id,
        "category": category,
        "writer_type": writer_type,
        "writer_mode": writer_mode,
        "document_title": document_title,
        "document_id": str(record.get("document_id") or record.get("doc_id") or ""),
        "doc_id": str(record.get("doc_id") or record.get("document_id") or ""),
        "doc_url": str(record.get("doc_url") or ""),
        "sheet_id": str(record.get("sheet_id") or ""),
        "table_id": str(record.get("table_id") or ""),
        "record_id": str(record.get("record_id") or ""),
        "attachment_upload_count": int(record.get("last_attachment_upload_count") or 0),
        "attachment_field_name": str(record.get("attachment_field_name") or ""),
        "message": f"已保存到：{document_title}",
        "client_token": f"archive-{uuid.uuid4().hex[:12]}",
    }


def append_feishu_archive_attachments(
    *,
    source_context: dict[str, Any] | None,
    attachment_urls: list[str] | None = None,
    attachment_files: list[Any] | None = None,
) -> dict[str, Any] | None:
    context = source_context if isinstance(source_context, dict) else {}
    connector_id = str(context.get("connector_id") or "").strip()
    external_chat_id = str(context.get("external_chat_id") or "").strip()
    attachment_text_items = [str(item or "").strip() for item in (attachment_urls or []) if str(item or "").strip()]
    local_files = _normalize_attachment_file_items(attachment_files=attachment_files, source_context=context)
    if not connector_id or not external_chat_id or (not attachment_text_items and not local_files):
        return None

    with _ARCHIVE_STATE_LOCK:
        state = _read_archive_state()
        archives = state.setdefault("archives", {})
        candidates = [
            (key, item)
            for key, item in archives.items()
            if isinstance(item, dict)
            and str(item.get("connector_id") or "").strip() == connector_id
            and str(item.get("external_chat_id") or "").strip() == external_chat_id
            and str(item.get("writer_type") or "").strip() == "bitable"
            and str(item.get("record_id") or "").strip()
            and str(item.get("table_id") or "").strip()
            and str(item.get("app_token") or item.get("base_token") or item.get("doc_id") or "").strip()
        ]
        candidates.sort(key=lambda pair: str(pair[1].get("updated_at") or pair[1].get("created_at") or ""), reverse=True)
        if not candidates:
            return {
                "status": "skipped",
                "message": "未找到可补写图片链接的最近飞书 Base 归档记录",
            }

        archive_key, record = candidates[0]
        app_token = str(record.get("app_token") or record.get("base_token") or record.get("doc_id") or "").strip()
        table_id = str(record.get("table_id") or "").strip()
        record_id = str(record.get("record_id") or "").strip()
        writer_mode = str(record.get("writer_mode") or "").strip()
        attachment_field_name = str(record.get("attachment_field_name") or _ARCHIVE_ATTACHMENT_COLUMN).strip() or _ARCHIVE_ATTACHMENT_COLUMN
        attachment_text = _merge_attachment_text(
            record.get("last_attachment_text"),
            attachment_text_items or [item.get("url") or item.get("filename") or item.get("path") or "" for item in local_files],
        )
        fields = {"图片/附件": attachment_text}
        uploaded_count = 0

        if writer_mode == "lark_cli_user":
            if local_files:
                attachment_field_name = _ensure_cli_bitable_fields(
                    app_token=app_token,
                    table_id=table_id,
                    preferred_attachment_field_name=attachment_field_name,
                )
                uploaded_count = _upload_cli_bitable_attachments(
                    app_token=app_token,
                    table_id=table_id,
                    record_id=record_id,
                    attachments=local_files,
                    field_name=attachment_field_name,
                )
            else:
                return {
                    "status": "skipped",
                    "message": "没有本地附件文件，未向飞书 Base 附件字段写入 URL 文本",
                    "writer_mode": writer_mode,
                }
        elif writer_mode == "bot_openapi":
            if local_files:
                return {
                    "status": "skipped",
                    "message": "bot_openapi 模式暂不支持把本地文件上传到飞书 Base 附件字段，请使用 lark_cli_user 写入模式",
                    "writer_mode": writer_mode,
                }
            connector = get_bot_connector(connector_id)
            if not connector or str(connector.get("platform") or "").strip().lower() != "feishu":
                raise RuntimeError(f"未找到飞书连接器：{connector_id}")
            token = _get_tenant_access_token(connector)
            _patch_bitable_record(
                token=token,
                app_token=app_token,
                table_id=table_id,
                record_id=record_id,
                fields=fields,
            )
        else:
            return {
                "status": "skipped",
                "message": "当前归档写入模式暂不支持补写图片链接",
                "writer_mode": writer_mode,
            }

        now = _now_iso()
        record["last_attachment_text"] = attachment_text
        record["last_attachment_upload_count"] = int(record.get("last_attachment_upload_count") or 0) + uploaded_count
        record["attachment_field_name"] = attachment_field_name
        record["updated_at"] = now
        record["last_external_message_id"] = str(context.get("external_message_id") or record.get("last_external_message_id") or "").strip()
        archives[str(archive_key)] = record
        _write_archive_state(state)
        return {
            "status": "updated",
            "archive_key": str(record.get("archive_key") or archive_key),
            "record_id": record_id,
            "table_id": table_id,
            "document_title": str(record.get("document_title") or ""),
            "attachment_text": attachment_text,
            "attachment_field_name": attachment_field_name,
            "uploaded_count": uploaded_count,
        }
