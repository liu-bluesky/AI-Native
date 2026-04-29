"""Feishu scheduled meeting/reminder detection and delivery."""

from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from services.global_assistant_task_service import upsert_global_assistant_task

_LOCAL_TZ = ZoneInfo("Asia/Shanghai")
_TIME_INTENT_TERMS = (
    "开会",
    "会议",
    "例会",
    "会一下",
    "提醒",
    "通知",
    "定时",
    "到点",
    "叫我",
    "叫大家",
)
_AMBIGUOUS_TIME_TERMS = ("几点", "啥时候", "什么时候", "哪天", "待定")
_CN_NUMBERS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
    "十一": 11,
    "十二": 12,
}
_DEFAULT_REMIND_BEFORE_MINUTES = 10


@dataclass(frozen=True)
class ParsedReminder:
    meeting_at: datetime
    reminder_at: datetime
    title: str
    meeting_label: str
    reminder_label: str


def _strip_feishu_mentions(value: str) -> str:
    text = re.sub(r"<at\b[^>]*>.*?</at>", " ", str(value or ""), flags=re.IGNORECASE)
    text = re.sub(r"@[_a-zA-Z0-9一-鿿.-]+", " ", text)
    return " ".join(text.split())


def _has_reminder_intent(text: str) -> bool:
    return any(term in text for term in _TIME_INTENT_TERMS)


def _parse_number(value: str) -> int | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.isdigit():
        return int(raw)
    if raw in _CN_NUMBERS:
        return _CN_NUMBERS[raw]
    if raw.startswith("十") and len(raw) == 2 and raw[1:] in _CN_NUMBERS:
        return 10 + int(_CN_NUMBERS[raw[1:]])
    if raw.endswith("十") and raw[:-1] in _CN_NUMBERS:
        return int(_CN_NUMBERS[raw[:-1]]) * 10
    return None


def _resolve_date(text: str, now_local: datetime) -> tuple[datetime, bool]:
    base = now_local
    if "后天" in text:
        return base + timedelta(days=2), True
    if "明天" in text or "明日" in text:
        return base + timedelta(days=1), True
    if "今天" in text or "今日" in text or "今晚" in text:
        return base, True

    absolute = re.search(r"(?:(20\d{2})[年/-])?(\d{1,2})[月/-](\d{1,2})[日号]?", text)
    if absolute:
        year = int(absolute.group(1) or base.year)
        month = int(absolute.group(2))
        day = int(absolute.group(3))
        try:
            return base.replace(year=year, month=month, day=day), True
        except ValueError:
            return base, False

    weekdays = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
    match = re.search(r"(下)?(?:周|星期|礼拜)([一二三四五六日天])", text)
    if match:
        target = weekdays[match.group(2)]
        days = (target - base.weekday()) % 7
        if match.group(1) or days == 0:
            days += 7
        return base + timedelta(days=days), True

    return base, False


def _resolve_time(text: str) -> tuple[int, int] | None:
    match = re.search(r"(\d{1,2})[:：](\d{1,2})", text)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
    else:
        token = r"\d{1,2}|十[一二]?|[一二两三四五六七八九十]"
        match = re.search(rf"({token})点(半|({token})分?)?", text)
        if not match:
            return None
        parsed_hour = _parse_number(match.group(1))
        if parsed_hour is None:
            return None
        hour = parsed_hour
        if match.group(2) == "半":
            minute = 30
        else:
            minute = _parse_number(match.group(3) or "") or 0

    if minute < 0 or minute > 59 or hour < 0 or hour > 23:
        return None
    if re.search(r"下午|晚上|今晚|傍晚", text) and 1 <= hour <= 11:
        hour += 12
    if "中午" in text and hour < 11:
        hour = 12 if hour == 0 else hour + 12
    return hour, minute


def parse_feishu_meeting_reminder(
    text: str,
    *,
    now: datetime | None = None,
    remind_before_minutes: int = _DEFAULT_REMIND_BEFORE_MINUTES,
) -> ParsedReminder | None:
    normalized = _strip_feishu_mentions(text)
    if not normalized or not _has_reminder_intent(normalized):
        return None
    if any(term in normalized for term in _AMBIGUOUS_TIME_TERMS):
        return None

    now_local = (now or datetime.now(_LOCAL_TZ)).astimezone(_LOCAL_TZ)
    date_base, has_explicit_date = _resolve_date(normalized, now_local)
    resolved_time = _resolve_time(normalized)
    if resolved_time is None:
        return None
    hour, minute = resolved_time
    try:
        due_local = date_base.replace(hour=hour, minute=minute, second=0, microsecond=0)
    except ValueError:
        return None
    if not has_explicit_date and due_local <= now_local:
        due_local += timedelta(days=1)

    title = normalized[:80] or "会议提醒"
    lead_minutes = max(0, min(int(remind_before_minutes or 0), 24 * 60))
    reminder_local = due_local - timedelta(minutes=lead_minutes)
    if reminder_local <= now_local:
        reminder_local = now_local
    meeting_label = due_local.strftime("%Y-%m-%d %H:%M")
    reminder_label = reminder_local.strftime("%Y-%m-%d %H:%M")
    return ParsedReminder(
        meeting_at=due_local.astimezone(timezone.utc),
        reminder_at=reminder_local.astimezone(timezone.utc),
        title=title,
        meeting_label=meeting_label,
        reminder_label=reminder_label,
    )


def create_feishu_meeting_reminder_task(
    *,
    username: str,
    project_id: str,
    connector: dict[str, Any],
    connector_id: str,
    chat_id: str,
    message_id: str,
    message_text: str,
    source_context: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    parsed = parse_feishu_meeting_reminder(message_text, now=now)
    if parsed is None:
        if _has_reminder_intent(_strip_feishu_mentions(message_text)) and any(term in message_text for term in _AMBIGUOUS_TIME_TERMS):
            return {"status": "ambiguous", "message": "要创建会议提醒还缺少具体时间，请补充日期和时间。"}
        return {"status": "ignored"}

    normalized_connector_id = str(connector_id or "").strip()
    normalized_chat_id = str(chat_id or "").strip()
    normalized_message_id = str(message_id or "").strip()
    if not normalized_connector_id or not normalized_chat_id or not normalized_message_id:
        return {"status": "ignored"}

    seed = "|".join([normalized_connector_id, normalized_chat_id, normalized_message_id, parsed.meeting_at.isoformat()])
    task_id = f"feishu-reminder-{hashlib.sha1(seed.encode('utf-8')).hexdigest()[:16]}"
    chat_name = str((source_context or {}).get("external_chat_name") or "").strip()
    reminder_text = f"会议提醒：{parsed.title}\n会议时间：{parsed.meeting_label}"
    if chat_name:
        reminder_text += f"\n来源群：{chat_name}"

    identity = str(connector.get("reply_identity") or "bot").strip().lower()
    if identity not in {"bot", "user"}:
        identity = "bot"
    task = upsert_global_assistant_task(
        username=username,
        project_id=project_id,
        task={
            "id": task_id,
            "title": f"会议提醒：{parsed.title[:40]}",
            "description": parsed.title,
            "status": "todo",
            "source": "feishu_meeting_reminder",
            "task_type": "reminder",
            "triggers": [
                {
                    "type": "schedule",
                    "enabled": True,
                    "source": "feishu",
                    "schedule": {
                        "run_at": parsed.reminder_at.isoformat(timespec="seconds"),
                        "next_run_at": parsed.reminder_at.isoformat(timespec="seconds"),
                        "interval_seconds": 0,
                    },
                }
            ],
            "actions": [
                {
                    "id": "action-feishu-reminder",
                    "type": "feishu_message",
                    "label": "飞书到点提醒",
                    "params": {
                        "connector_id": normalized_connector_id,
                        "chat_id": normalized_chat_id,
                        "message_id": normalized_message_id,
                        "identity": identity,
                        "text": reminder_text,
                        "meeting_at": parsed.meeting_at.isoformat(timespec="seconds"),
                        "remind_before_minutes": _DEFAULT_REMIND_BEFORE_MINUTES,
                    },
                }
            ],
        },
    )
    return {
        "status": "created",
        "task_id": task.get("id") or task_id,
        "due_at": parsed.reminder_at.isoformat(timespec="seconds"),
        "meeting_at": parsed.meeting_at.isoformat(timespec="seconds"),
        "local_label": parsed.reminder_label,
        "meeting_label": parsed.meeting_label,
        "reminder_label": parsed.reminder_label,
        "title": parsed.title,
        "message": f"已创建会议提醒：会议 {parsed.meeting_label}，将在 {parsed.reminder_label} 提前通知本群。",
    }


def send_feishu_scheduled_message(*, task: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
    params = action.get("params") if isinstance(action.get("params"), dict) else {}
    chat_id = str(params.get("chat_id") or "").strip()
    text = str(params.get("text") or task.get("description") or task.get("title") or "提醒时间到了").strip()
    identity = str(params.get("identity") or "bot").strip().lower()
    if identity not in {"bot", "user"}:
        identity = "bot"
    if not chat_id:
        raise RuntimeError("缺少飞书 chat_id，无法发送定时提醒")
    command = [
        "lark-cli",
        "im",
        "+messages-send",
        "--chat-id",
        chat_id,
        "--text",
        text,
        "--as",
        identity,
        "--idempotency-key",
        f"feishu-reminder-{task.get('id') or ''}",
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
    except FileNotFoundError as exc:
        raise RuntimeError("未找到 lark-cli，请先安装 @larksuite/cli 并重新启动服务") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("lark-cli 发送飞书定时提醒超时，请检查飞书授权或网络状态") from exc
    if completed.returncode != 0:
        output = (completed.stderr or completed.stdout or "").strip()[:800]
        raise RuntimeError(f"lark-cli 发送飞书定时提醒失败：{output}")
    return {"status": "sent", "message": "飞书定时提醒已发送", "chat_id": chat_id}
