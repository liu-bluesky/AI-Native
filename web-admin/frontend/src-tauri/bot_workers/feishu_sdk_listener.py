#!/usr/bin/env python3
"""Desktop Feishu bot long-connection listener.

This worker is intentionally independent from the backend API service. Tauri
starts it with connector credentials in environment variables, then reads
stdout as NDJSON events and stderr as status/error logs.
"""

from __future__ import annotations

import json
import hashlib
import os
import sys
import traceback
from typing import Any


def emit_stderr(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False), file=sys.stderr, flush=True)


def emit_error(error_type: str, message: str, *, hint: str = "", detail: str = "") -> None:
    payload: dict[str, Any] = {
        "ok": False,
        "error": {
            "type": error_type,
            "message": message,
        },
    }
    if hint:
        payload["error"]["hint"] = hint
    if detail:
        payload["error"]["detail"] = detail
    emit_stderr(payload)


def read_env(name: str) -> str:
    return str(os.environ.get(name) or "").strip()


def plain(value: Any, depth: int = 0) -> Any:
    if depth > 12:
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    if isinstance(value, (list, tuple, set)):
        return [plain(item, depth + 1) for item in value]
    if isinstance(value, dict):
        return {
            str(key): plain(item, depth + 1)
            for key, item in value.items()
            if item is not None and not str(key).startswith("_")
        }
    if hasattr(value, "__dict__"):
        return plain(vars(value), depth + 1)
    return str(value)


def field(source: Any, *keys: str) -> Any:
    if isinstance(source, dict):
        for key in keys:
            if key in source:
                value = source[key]
                if value not in (None, ""):
                    return value
        return None
    for key in keys:
        value = getattr(source, key, None)
        if value not in (None, ""):
            return value
    return None


def first_field(sources: tuple[Any, ...], *keys: str) -> Any:
    for source in sources:
        value = field(source, *keys)
        if value not in (None, ""):
            return value
    return None


def pick_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        if isinstance(value, dict):
            value = field(value, "text", "content", "value")
            if value is None:
                continue
        text = str(value).strip()
        if text:
            return text
    return ""


def nested(source: Any, *keys: str) -> Any:
    current = source
    for key in keys:
        current = field(current, key)
        if current is None:
            return None
    return current


FEISHU_OPEN_API_UUID_MAX_LENGTH = 50


def normalize_feishu_uuid(value: str, *, fallback_prefix: str = "feishu") -> str:
    normalized = str(value or "").strip()
    if normalized and len(normalized) <= FEISHU_OPEN_API_UUID_MAX_LENGTH:
        return normalized
    seed = hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized else os.urandom(16).hex()
    return f"{fallback_prefix}-{seed}"[:FEISHU_OPEN_API_UUID_MAX_LENGTH]


def event_shape_diagnostic(data: Any) -> str:
    raw = plain(data)
    if not isinstance(raw, dict):
        return json.dumps(
            {
                "input_type": type(data).__name__,
                "root_keys": [],
                "event_keys": [],
                "message_keys": [],
            },
            ensure_ascii=False,
            sort_keys=True,
        )

    event = field(raw, "event")
    if not isinstance(event, dict):
        event = raw if any(
            key in raw
            for key in (
                "message",
                "sender",
                "message_id",
                "messageId",
                "chat_id",
                "chatId",
            )
        ) else {}
    message = field(event, "message")
    if not isinstance(message, dict):
        message = event
    return json.dumps(
        {
            "input_type": type(data).__name__,
            "root_keys": sorted(str(key) for key in raw.keys()),
            "event_keys": sorted(str(key) for key in event.keys()),
            "message_keys": sorted(str(key) for key in message.keys()),
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def sdk_response_error_detail(response: Any) -> str:
    detail: dict[str, Any] = {}
    for field in ("code", "msg", "request_id", "log_id"):
        value = getattr(response, field, None)
        if value not in (None, ""):
            detail[field] = plain(value)
    for method in ("get_log_id", "get_troubleshooter"):
        candidate = getattr(response, method, None)
        if callable(candidate):
            try:
                value = candidate()
            except Exception as exc:
                value = f"<{type(exc).__name__}: {exc}>"
            if value not in (None, ""):
                detail[method] = plain(value)
    raw = plain(response)
    if raw not in (None, "", {}) and raw != detail:
        detail["raw"] = raw
    return json.dumps(detail or {"response": str(response)}, ensure_ascii=False)


def normalize_message_event(data: Any, connector_id: str) -> dict[str, Any]:
    raw = plain(data)
    if not isinstance(raw, dict):
        raw = {}
    header = field(raw, "header")
    if not isinstance(header, dict):
        header = {}
    event = field(raw, "event")
    if not isinstance(event, dict):
        event = {}
    if not event and any(
        key in raw
        for key in (
            "message",
            "sender",
            "message_id",
            "messageId",
            "chat_id",
            "chatId",
        )
    ):
        event = raw
    message = field(event, "message")
    if not isinstance(message, dict):
        message = event
    sender = field(event, "sender")
    if not isinstance(sender, dict):
        sender = field(message, "sender")
    if not isinstance(sender, dict):
        sender = {}
    sender_id = field(sender, "sender_id", "senderId")
    if not isinstance(sender_id, dict):
        sender_id = {}
    body = field(message, "body")
    if not isinstance(body, dict):
        body = {}

    content = pick_text(first_field((message, body, event, raw), "content", "text"))
    text = content
    if content.startswith("{"):
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                text = pick_text(parsed.get("text"), parsed.get("content"), content)
        except Exception:
            text = content

    return {
        "type": pick_text(
            first_field((header, raw, event), "event_type", "eventType"),
            "im.message.receive_v1",
        ),
        "event_id": pick_text(
            first_field(
                (header, raw, event, message),
                "event_id",
                "eventId",
                "message_id",
                "messageId",
            )
        ),
        "message_id": pick_text(
            first_field((message, event, raw), "message_id", "messageId", "id")
        ),
        "id": pick_text(
            first_field((message, event, raw), "message_id", "messageId", "id")
        ),
        "message_type": pick_text(
            first_field(
                (message, event, raw),
                "message_type",
                "messageType",
                "msg_type",
                "msgType",
            )
        ),
        "chat_id": pick_text(first_field((message, event, raw), "chat_id", "chatId")),
        "chat_type": pick_text(
            first_field((message, event, raw), "chat_type", "chatType")
        ),
        "mentions": plain(
            first_field((message, event, raw), "mentions", "message_mentions") or []
        ),
        "content": text,
        "raw_content": content,
        "sender_id": pick_text(
            field(sender_id, "open_id", "openId"),
            field(sender_id, "user_id", "userId"),
            field(sender_id, "union_id", "unionId"),
            field(sender, "open_id", "openId"),
            field(sender, "user_id", "userId"),
            nested(sender, "sender_id"),
        ),
        "create_time": pick_text(
            first_field((message, event, raw), "create_time", "createTime")
        ),
        "timestamp": pick_text(
            first_field((header, raw, event), "create_time", "createTime")
        ),
        "connector_id": connector_id,
        "raw": raw,
    }


def message_payload_has_signal(payload: dict[str, Any]) -> bool:
    return any(
        str(payload.get(key) or "").strip()
        for key in ("event_id", "message_id", "chat_id", "chat_type", "content")
    )


def main() -> int:
    command = read_env("AI_EMPLOYEE_FEISHU_COMMAND").lower()
    connector_id = read_env("AI_EMPLOYEE_FEISHU_CONNECTOR_ID")
    app_id = read_env("AI_EMPLOYEE_FEISHU_APP_ID")
    app_secret = read_env("AI_EMPLOYEE_FEISHU_APP_SECRET")
    encrypt_key = read_env("AI_EMPLOYEE_FEISHU_ENCRYPT_KEY")
    verification_token = read_env("AI_EMPLOYEE_FEISHU_VERIFICATION_TOKEN")

    if not connector_id:
        emit_error("config", "缺少机器人连接器 ID")
        return 2
    if not app_id or not app_secret:
        emit_error("config", "飞书机器人缺少 App ID 或 App Secret")
        return 2

    try:
        import lark_oapi as lark
        from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody
        from lark_oapi.api.im.v1 import PatchMessageRequest, PatchMessageRequestBody
        from lark_oapi.api.im.v1 import ReplyMessageRequest, ReplyMessageRequestBody
        from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
        from lark_oapi.event.callback.model.p2_card_action_trigger import P2CardActionTriggerResponse
        from lark_oapi.ws import Client
    except Exception as exc:
        emit_error(
            "dependency",
            "当前 Python 环境缺少飞书 Python SDK lark_oapi",
            hint="请设置 AI_EMPLOYEE_FEISHU_PYTHON 指向已安装 lark-oapi 的 Python，或为桌面端 Python 环境安装 lark-oapi。",
            detail=str(exc),
        )
        return 3

    if command == "reply":
        message_id = read_env("AI_EMPLOYEE_FEISHU_MESSAGE_ID")
        content = read_env("AI_EMPLOYEE_FEISHU_REPLY_CONTENT")
        uuid = normalize_feishu_uuid(
            read_env("AI_EMPLOYEE_FEISHU_IDEMPOTENCY_KEY") or f"desktop-bot-reply-{message_id}",
            fallback_prefix="feishu-reply",
        )
        reply_in_thread = read_env("AI_EMPLOYEE_FEISHU_REPLY_IN_THREAD").lower() in {
            "1",
            "true",
            "yes",
        }
        if not message_id or not content:
            emit_error("config", "飞书 SDK 回复需要 message_id 和 content")
            return 2
        try:
            client = lark.Client.builder().app_id(app_id).app_secret(app_secret).build()
            body = (
                ReplyMessageRequestBody.builder()
                .msg_type("text")
                .content(json.dumps({"text": content}, ensure_ascii=False))
                .uuid(uuid)
                .reply_in_thread(reply_in_thread)
                .build()
            )
            request = (
                ReplyMessageRequest.builder()
                .message_id(message_id)
                .request_body(body)
                .build()
            )
            response = client.im.v1.message.reply(request)
            if not response.success():
                emit_error(
                    "reply",
                    "飞书 Python SDK 回复失败",
                    detail=sdk_response_error_detail(response),
                )
                return 4
            print(json.dumps({"ok": True, "message_id": message_id}, ensure_ascii=False), flush=True)
            return 0
        except Exception as exc:
            emit_error("reply", "飞书 Python SDK 回复失败", detail=str(exc))
            return 4

    if command == "send_card":
        chat_id = read_env("AI_EMPLOYEE_FEISHU_CHAT_ID")
        content = read_env("AI_EMPLOYEE_FEISHU_CARD_CONTENT")
        uuid = normalize_feishu_uuid(
            read_env("AI_EMPLOYEE_FEISHU_IDEMPOTENCY_KEY") or f"desktop-bot-card-{chat_id}",
            fallback_prefix="feishu-card",
        )
        if not chat_id or not content:
            emit_error("config", "飞书 SDK 发送卡片需要 chat_id 和 card content")
            return 2
        try:
            client = lark.Client.builder().app_id(app_id).app_secret(app_secret).build()
            body = (
                CreateMessageRequestBody.builder()
                .receive_id(chat_id)
                .msg_type("interactive")
                .content(content)
                .uuid(uuid)
                .build()
            )
            request = (
                CreateMessageRequest.builder()
                .receive_id_type("chat_id")
                .request_body(body)
                .build()
            )
            response = client.im.v1.message.create(request)
            if not response.success():
                emit_error(
                    "send_card",
                    "飞书 Python SDK 发送卡片失败",
                    detail=sdk_response_error_detail(response),
                )
                return 4
            response_data = plain(getattr(response, "data", None))
            message_id = ""
            if isinstance(response_data, dict):
                message_id = pick_text(response_data.get("message_id"), response_data.get("messageId"))
            print(
                json.dumps(
                    {"ok": True, "message_id": message_id, "chat_id": chat_id},
                    ensure_ascii=False,
                ),
                flush=True,
            )
            return 0
        except Exception as exc:
            emit_error("send_card", "飞书 Python SDK 发送卡片失败", detail=str(exc))
            return 4

    if command == "update_card":
        message_id = read_env("AI_EMPLOYEE_FEISHU_MESSAGE_ID")
        content = read_env("AI_EMPLOYEE_FEISHU_CARD_CONTENT")
        if not message_id or not content:
            emit_error("config", "飞书 SDK 更新卡片需要 message_id 和 card content")
            return 2
        try:
            client = lark.Client.builder().app_id(app_id).app_secret(app_secret).build()
            body = PatchMessageRequestBody.builder().content(content).build()
            request = (
                PatchMessageRequest.builder()
                .message_id(message_id)
                .request_body(body)
                .build()
            )
            response = client.im.v1.message.patch(request)
            if not response.success():
                emit_error(
                    "update_card",
                    "飞书 Python SDK 更新卡片失败",
                    detail=sdk_response_error_detail(response),
                )
                return 4
            print(json.dumps({"ok": True, "message_id": message_id}, ensure_ascii=False), flush=True)
            return 0
        except Exception as exc:
            emit_error("update_card", "飞书 Python SDK 更新卡片失败", detail=str(exc))
            return 4

    def normalize_card_action_event(data: Any) -> dict[str, Any]:
        raw = plain(data)
        event = raw.get("event") if isinstance(raw, dict) else {}
        if not isinstance(event, dict):
            event = {}
        action = event.get("action") if isinstance(event.get("action"), dict) else {}
        operator = event.get("operator") if isinstance(event.get("operator"), dict) else {}
        operator_id = operator.get("operator_id") if isinstance(operator.get("operator_id"), dict) else {}
        header = raw.get("header") if isinstance(raw, dict) and isinstance(raw.get("header"), dict) else {}
        action_value = action.get("value")
        if not isinstance(action_value, dict):
            action_value = {}
        return {
            "kind": "card_action",
            "type": pick_text(header.get("event_type"), "p2.card.action.trigger"),
            "event_id": pick_text(header.get("event_id"), event.get("event_id")),
            "open_message_id": pick_text(event.get("open_message_id"), event.get("openMessageId")),
            "message_id": pick_text(event.get("open_message_id"), event.get("openMessageId")),
            "chat_id": pick_text(event.get("open_chat_id"), event.get("openChatId"), event.get("chat_id")),
            "operator_id": pick_text(
                operator_id.get("open_id"),
                operator_id.get("user_id"),
                operator_id.get("union_id"),
                nested(operator, "operator_id"),
            ),
            "action_value": action_value,
            "actionValue": action_value,
            "connector_id": connector_id,
            "raw": raw,
        }

    seen_empty_event_shapes: set[str] = set()

    def on_message(data: P2ImMessageReceiveV1) -> None:
        try:
            payload = normalize_message_event(data, connector_id)
            if not message_payload_has_signal(payload):
                diagnostic = event_shape_diagnostic(data)
                if diagnostic not in seen_empty_event_shapes:
                    seen_empty_event_shapes.add(diagnostic)
                    print(
                        f"[feishu-sdk] event-shape {diagnostic}",
                        file=sys.stderr,
                        flush=True,
                    )
                return
            print(json.dumps(payload, ensure_ascii=False), flush=True)
        except Exception as exc:
            emit_error(
                "event_normalize_failed",
                "飞书消息事件转换失败",
                detail=f"{exc}\n{traceback.format_exc()}",
            )

    def on_card_action(data: Any) -> Any:
        try:
            payload = normalize_card_action_event(data)
            print(json.dumps(payload, ensure_ascii=False), flush=True)
        except Exception as exc:
            emit_error(
                "event_normalize_failed",
                "飞书卡片事件转换失败",
                detail=f"{exc}\n{traceback.format_exc()}",
            )
        return P2CardActionTriggerResponse()

    try:
        handler = (
            lark.EventDispatcherHandler.builder(encrypt_key, verification_token)
            .register_p2_im_message_receive_v1(on_message)
            .register_p2_card_action_trigger(on_card_action)
            .build()
        )
        print("[feishu-sdk] ready event_key=im.message.receive_v1,p2.card.action.trigger", file=sys.stderr, flush=True)
        Client(app_id, app_secret, event_handler=handler).start()
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        emit_error("listener", "飞书 Python SDK 长连接监听失败", detail=str(exc))
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
