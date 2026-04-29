"""Global assistant user task storage, event matching, and lightweight execution."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
import uuid
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from core.config import get_api_data_dir
from services.feishu_archive_writer_service import archive_feishu_task_message, is_feishu_auto_archive_action

logger = logging.getLogger(__name__)

_TASK_LOCK = threading.RLock()
_ACTIVE_STATUSES = {"todo", "doing"}
_EXECUTION_HISTORY_LIMIT = 50
_SCHEDULER_TASK: asyncio.Task[None] | None = None
_SCHEDULER_LOCK = threading.RLock()
_LOCAL_TZ = ZoneInfo("Asia/Shanghai")
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
_GENERIC_CHINESE_TERMS = {
    "任务",
    "创建",
    "新建",
    "添加",
    "监听",
    "播报",
    "提醒",
    "提示",
    "通知",
    "执行",
    "飞书",
    "机器人",
    "群里",
    "消息",
    "内容",
    "时候",
    "如果",
    "有人",
}
_SYSTEM_SPEECH_INTENT_TERMS = {
    "提醒",
    "提示",
    "通知",
    "播报",
    "语音",
    "声音",
    "朗读",
    "说一声",
    "alert",
    "notify",
    "notification",
    "speech",
    "speak",
}
_SCHEDULE_INTENT_TERMS = {
    "提醒",
    "提示",
    "通知",
    "定时",
    "到点",
    "到时间",
    "叫我",
    "叫一下",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_iso_datetime(value: Any) -> datetime | None:
    raw_value = str(value or "").strip()
    if not raw_value:
        return None
    if raw_value.endswith("Z"):
        raw_value = f"{raw_value[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw_value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def _task_store_path() -> Path:
    return get_api_data_dir() / "global-assistant-tasks.json"


def _normalize_username(username: str) -> str:
    return str(username or "").strip() or "anonymous"


def _normalize_status(status: str) -> str:
    normalized = str(status or "todo").strip().lower()
    return normalized if normalized in {"todo", "doing", "done"} else "todo"


def _normalize_task_type(value: Any) -> str:
    normalized = str(value or "generic").strip().lower()
    allowed = {"generic", "reminder", "message_listener", "file_processing", "workflow"}
    return normalized if normalized in allowed else "generic"


def _normalize_interval_seconds(value: Any) -> int:
    try:
        interval_seconds = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return max(0, min(interval_seconds, 31_536_000))


def _parse_chinese_number(value: str) -> int | None:
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


def _resolve_natural_schedule_date(text: str, base_local: datetime) -> tuple[datetime, bool]:
    if "后天" in text:
        return base_local + timedelta(days=2), True
    if "明天" in text or "明日" in text:
        return base_local + timedelta(days=1), True
    if "今天" in text or "今日" in text or "今晚" in text:
        return base_local, True
    absolute = re.search(r"(?:(20\d{2})[年/-])?(\d{1,2})[月/-](\d{1,2})[日号]?", text)
    if absolute:
        try:
            return (
                base_local.replace(
                    year=int(absolute.group(1) or base_local.year),
                    month=int(absolute.group(2)),
                    day=int(absolute.group(3)),
                ),
                True,
            )
        except ValueError:
            return base_local, False
    return base_local, False


def _resolve_natural_schedule_time(text: str) -> tuple[int, int] | None:
    match = re.search(r"(\d{1,2})[:：](\d{1,2})", text)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
    else:
        token = r"\d{1,2}|十[一二]?|[一二两三四五六七八九十]"
        match = re.search(rf"({token})点(半|({token})分?)?", text)
        if not match:
            return None
        parsed_hour = _parse_chinese_number(match.group(1))
        if parsed_hour is None:
            return None
        hour = parsed_hour
        minute = 30 if match.group(2) == "半" else (_parse_chinese_number(match.group(3) or "") or 0)
    if minute < 0 or minute > 59 or hour < 0 or hour > 23:
        return None
    if re.search(r"下午|晚上|今晚|傍晚", text) and 1 <= hour <= 11:
        hour += 12
    if "中午" in text and hour < 11:
        hour = 12 if hour == 0 else hour + 12
    return hour, minute


def _infer_natural_schedule_time(raw: dict[str, Any], *, base_time: datetime | None = None) -> datetime | None:
    if str(raw.get("status") or "todo").strip().lower() == "done":
        return None
    if int(raw.get("execution_count") or raw.get("executionCount") or 0) > 0:
        return None
    text = " ".join(
        str(item or "").strip()
        for item in (raw.get("title"), raw.get("description"), raw.get("task_type"), raw.get("taskType"))
        if str(item or "").strip()
    )
    if not text or not any(term in text for term in _SCHEDULE_INTENT_TERMS):
        return None
    base_local = (base_time or datetime.now(timezone.utc)).astimezone(_LOCAL_TZ)
    date_base, has_explicit_date = _resolve_natural_schedule_date(text, base_local)
    resolved_time = _resolve_natural_schedule_time(text)
    if resolved_time is None:
        return None
    hour, minute = resolved_time
    try:
        due_local = date_base.replace(hour=hour, minute=minute, second=0, microsecond=0)
    except ValueError:
        return None
    if not has_explicit_date and due_local <= base_local:
        due_local += timedelta(days=1)
    return due_local.astimezone(timezone.utc)


def _normalize_trigger(raw_trigger: dict[str, Any] | None, *, fallback_type: str = "manual") -> dict[str, Any]:
    raw = raw_trigger if isinstance(raw_trigger, dict) else {}
    trigger_type = str(raw.get("type") or raw.get("trigger_type") or fallback_type or "manual").strip().lower()
    if trigger_type not in {"manual", "event", "schedule"}:
        trigger_type = "manual"
    phrases = [
        str(item or "").strip()
        for item in (raw.get("phrases") or raw.get("trigger_phrases") or raw.get("triggerPhrases") or [])
        if str(item or "").strip()
    ]
    schedule = raw.get("schedule") if isinstance(raw.get("schedule"), dict) else {}
    run_at = str(raw.get("run_at") or raw.get("runAt") or schedule.get("run_at") or schedule.get("runAt") or "").strip()
    next_run_at = str(
        raw.get("next_run_at")
        or raw.get("nextRunAt")
        or schedule.get("next_run_at")
        or schedule.get("nextRunAt")
        or run_at
        or ""
    ).strip()
    interval_seconds = _normalize_interval_seconds(
        raw.get("interval_seconds")
        or raw.get("intervalSeconds")
        or schedule.get("interval_seconds")
        or schedule.get("intervalSeconds")
    )
    return {
        "id": str(raw.get("id") or f"trigger-{uuid.uuid4().hex[:10]}").strip(),
        "type": trigger_type,
        "enabled": bool(raw.get("enabled", True)),
        "source": str(raw.get("source") or "").strip(),
        "phrases": phrases,
        "schedule": {
            "run_at": _format_datetime(_parse_iso_datetime(run_at)),
            "next_run_at": _format_datetime(_parse_iso_datetime(next_run_at)),
            "interval_seconds": interval_seconds,
        },
    }


def _normalize_action(raw_action: dict[str, Any] | None, *, fallback_type: str = "record") -> dict[str, Any]:
    raw = raw_action if isinstance(raw_action, dict) else {}
    action_type = str(raw.get("type") or raw.get("action_type") or fallback_type or "record").strip().lower()
    if action_type not in {
        "record",
        "notify",
        "system_speech",
        "project_chat",
        "file_processing",
        "webhook",
        "feishu_message",
    }:
        action_type = "record"
    params = raw.get("params") if isinstance(raw.get("params"), dict) else {}
    return {
        "id": str(raw.get("id") or f"action-{uuid.uuid4().hex[:10]}").strip(),
        "type": action_type,
        "enabled": bool(raw.get("enabled", True)),
        "label": str(raw.get("label") or raw.get("name") or "").strip()[:80],
        "params": params,
    }


def _contains_system_speech_intent(*values: Any) -> bool:
    text = " ".join(str(item or "").strip().lower() for item in values if str(item or "").strip())
    if not text:
        return False
    return any(term in text for term in _SYSTEM_SPEECH_INTENT_TERMS)


def _actions_are_default_record(actions: list[dict[str, Any]]) -> bool:
    if len(actions) != 1:
        return False
    action = actions[0]
    action_type = str(action.get("type") or "").strip().lower()
    label = str(action.get("label") or "").strip()
    return action_type == "record" and label in {"", "记录任务执行"}


def _dynamic_project_chat_action() -> dict[str, Any]:
    return _normalize_action(
        {
            "type": "project_chat",
            "label": "大模型动态执行",
            "params": {"mode": "dynamic_task"},
        },
        fallback_type="project_chat",
    )


def _is_dynamic_project_chat_action(action: dict[str, Any]) -> bool:
    if str(action.get("type") or "").strip().lower() != "project_chat":
        return False
    params = action.get("params") if isinstance(action.get("params"), dict) else {}
    return str(params.get("mode") or "").strip() in {"", "dynamic_task"}


def _actions_are_dynamic_project_chat(actions: list[dict[str, Any]]) -> bool:
    return len(actions) == 1 and _is_dynamic_project_chat_action(actions[0])


def _raw_task_has_event_listener(raw: dict[str, Any]) -> bool:
    if bool(raw.get("listen_enabled", raw.get("listenEnabled", False))):
        text = " ".join(str(item or "") for item in (raw.get("title"), raw.get("description")))
        if any(term in text for term in ("监听", "收到", "飞书群", "群里", "消息")):
            return True
    if raw.get("trigger_phrases") or raw.get("triggerPhrases"):
        return True
    raw_triggers = raw.get("triggers") if isinstance(raw.get("triggers"), list) else []
    return any(
        isinstance(trigger, dict)
        and str(trigger.get("type") or trigger.get("trigger_type") or "").strip().lower() == "event"
        and bool(trigger.get("phrases") or trigger.get("trigger_phrases") or trigger.get("triggerPhrases"))
        for trigger in raw_triggers
    )


def _system_speech_reminder_action(raw: dict[str, Any]) -> dict[str, Any] | None:
    task_type = _normalize_task_type(raw.get("task_type") or raw.get("taskType"))
    if task_type == "message_listener" or _raw_task_has_event_listener(raw):
        return None
    dynamic_actions = _infer_simple_reminder_dynamic_actions(raw)
    if dynamic_actions:
        first = dynamic_actions[0]
        text = str(first.get("text") or "").strip()
        repeat = int(first.get("repeat") or 1)
    else:
        text = _strip_simple_reminder_control_text(str(raw.get("description") or raw.get("title") or ""))
        repeat = _extract_simple_reminder_repeat(
            " ".join(str(item or "") for item in (raw.get("description"), raw.get("title")))
        )
    if not text:
        return None
    return _normalize_action(
        {
            "type": "system_speech",
            "label": "系统播报",
            "params": {
                "text": text,
                "repeat": max(1, min(int(repeat or 1), 10)),
            },
        },
        fallback_type="system_speech",
    )


def _is_empty_task_module_speech_action(raw: dict[str, Any], actions: list[dict[str, Any]]) -> bool:
    if str(raw.get("source") or "").strip() != "tasks-module":
        return False
    if len(actions) != 1:
        return False
    action = actions[0]
    if str(action.get("type") or "").strip().lower() != "system_speech":
        return False
    params = action.get("params") if isinstance(action.get("params"), dict) else {}
    return not str(params.get("text") or params.get("message") or "").strip()


def _task_implies_system_speech(raw: dict[str, Any]) -> bool:
    return _contains_system_speech_intent(
        raw.get("title"),
        raw.get("description"),
        raw.get("task_type"),
        raw.get("source"),
    )


def _normalize_execution_history(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for raw_item in value[-_EXECUTION_HISTORY_LIMIT:]:
        if not isinstance(raw_item, dict):
            continue
        started_at = _format_datetime(_parse_iso_datetime(raw_item.get("started_at") or raw_item.get("startedAt"))) or _now_iso()
        finished_at = _format_datetime(_parse_iso_datetime(raw_item.get("finished_at") or raw_item.get("finishedAt")))
        action_results = raw_item.get("action_results") or raw_item.get("actionResults") or []
        result.append(
            {
                "id": str(raw_item.get("id") or f"run-{uuid.uuid4().hex[:12]}").strip(),
                "trigger_type": str(raw_item.get("trigger_type") or raw_item.get("triggerType") or "manual").strip() or "manual",
                "status": str(raw_item.get("status") or "completed").strip() or "completed",
                "started_at": started_at,
                "finished_at": finished_at,
                "message": str(raw_item.get("message") or "").strip()[:500],
                "match_reason": str(raw_item.get("match_reason") or raw_item.get("matchReason") or "").strip()[:120],
                "action_results": action_results if isinstance(action_results, list) else [],
            }
        )
    return result


def _legacy_event_trigger(raw: dict[str, Any]) -> dict[str, Any] | None:
    phrases = [
        str(item or "").strip()
        for item in (raw.get("trigger_phrases") or raw.get("triggerPhrases") or [])
        if str(item or "").strip()
    ]
    listen_enabled = bool(raw.get("listen_enabled", raw.get("listenEnabled", True)))
    if not listen_enabled and not phrases:
        return None
    return _normalize_trigger(
        {
            "type": "event",
            "enabled": listen_enabled,
            "source": "feishu",
            "phrases": phrases,
        },
        fallback_type="event",
    )


def _legacy_schedule_trigger(raw: dict[str, Any]) -> dict[str, Any] | None:
    schedule = raw.get("schedule") if isinstance(raw.get("schedule"), dict) else {}
    next_run_at = raw.get("next_run_at") or raw.get("nextRunAt") or schedule.get("next_run_at") or schedule.get("nextRunAt")
    run_at = raw.get("run_at") or raw.get("runAt") or schedule.get("run_at") or schedule.get("runAt")
    interval_seconds = raw.get("interval_seconds") or raw.get("intervalSeconds") or schedule.get("interval_seconds") or schedule.get("intervalSeconds")
    if not next_run_at and not run_at and not interval_seconds:
        return None
    return _normalize_trigger(
        {
            "type": "schedule",
            "enabled": True,
            "schedule": {
                "run_at": run_at,
                "next_run_at": next_run_at or run_at,
                "interval_seconds": interval_seconds,
            },
        },
        fallback_type="schedule",
    )


def _normalize_triggers(raw: dict[str, Any], *, base_time: datetime | None = None) -> list[dict[str, Any]]:
    raw_triggers = raw.get("triggers") if isinstance(raw.get("triggers"), list) else []
    triggers = [_normalize_trigger(item) for item in raw_triggers if isinstance(item, dict)]
    if not triggers:
        event_trigger = _legacy_event_trigger(raw)
        schedule_trigger = _legacy_schedule_trigger(raw)
        triggers = [item for item in (event_trigger, schedule_trigger) if item]
    has_scheduled_time = any(
        isinstance(trigger, dict)
        and trigger.get("type") == "schedule"
        and (
            _parse_iso_datetime((trigger.get("schedule") if isinstance(trigger.get("schedule"), dict) else {}).get("next_run_at"))
            or _parse_iso_datetime((trigger.get("schedule") if isinstance(trigger.get("schedule"), dict) else {}).get("run_at"))
            or _normalize_interval_seconds((trigger.get("schedule") if isinstance(trigger.get("schedule"), dict) else {}).get("interval_seconds")) > 0
        )
        for trigger in triggers
    )
    inferred_run_at = None if has_scheduled_time else _infer_natural_schedule_time(raw, base_time=base_time)
    if inferred_run_at is not None:
        triggers.append(
            _normalize_trigger(
                {
                    "type": "schedule",
                    "enabled": True,
                    "source": "natural-language",
                    "schedule": {
                        "run_at": inferred_run_at.isoformat(timespec="seconds"),
                        "next_run_at": inferred_run_at.isoformat(timespec="seconds"),
                        "interval_seconds": 0,
                    },
                },
                fallback_type="schedule",
            )
        )
    if not triggers:
        triggers = [_normalize_trigger({"type": "manual", "enabled": True}, fallback_type="manual")]
    return triggers


def _normalize_actions(raw: dict[str, Any]) -> list[dict[str, Any]]:
    raw_actions = raw.get("actions") if isinstance(raw.get("actions"), list) else []
    actions = [_normalize_action(item) for item in raw_actions if isinstance(item, dict)]
    if not actions and isinstance(raw.get("action"), dict):
        actions = [_normalize_action(raw.get("action"))]
    reminder_action = _system_speech_reminder_action(raw)
    if (
        reminder_action
        and _normalize_task_type(raw.get("task_type") or raw.get("taskType")) == "reminder"
        and (not actions or _actions_are_default_record(actions) or _actions_are_dynamic_project_chat(actions))
    ):
        return [reminder_action]
    if _is_empty_task_module_speech_action(raw, actions):
        return [reminder_action] if reminder_action else [_dynamic_project_chat_action()]
    if (not actions or _actions_are_default_record(actions)) and _task_implies_system_speech(raw):
        return [reminder_action] if reminder_action else [_dynamic_project_chat_action()]
    if not actions:
        actions = [_normalize_action({"type": "record", "label": "记录任务执行"})]
    return actions


def _resolve_next_run_at(raw: dict[str, Any], triggers: list[dict[str, Any]]) -> str:
    explicit = _format_datetime(_parse_iso_datetime(raw.get("next_run_at") or raw.get("nextRunAt")))
    if explicit:
        return explicit
    candidates: list[datetime] = []
    for trigger in triggers:
        if trigger.get("type") != "schedule" or not bool(trigger.get("enabled", True)):
            continue
        schedule = trigger.get("schedule") if isinstance(trigger.get("schedule"), dict) else {}
        candidate = _parse_iso_datetime(schedule.get("next_run_at")) or _parse_iso_datetime(schedule.get("run_at"))
        if candidate:
            candidates.append(candidate)
    return _format_datetime(min(candidates)) if candidates else ""


def _normalize_task(raw_task: dict[str, Any] | None, *, username: str) -> dict[str, Any]:
    raw = raw_task if isinstance(raw_task, dict) else {}
    now = _now_iso()
    description = str(raw.get("description") or raw.get("title") or "").strip()
    title = str(raw.get("title") or description.split("\n")[0] or "未命名任务").strip()[:60]
    if not title:
        title = "未命名任务"
    task_id = str(raw.get("id") or raw.get("task_id") or "").strip()
    if not task_id:
        task_id = f"task-{uuid.uuid4().hex[:12]}"
    created_at = str(raw.get("createdAt") or raw.get("created_at") or "").strip() or now
    updated_at = str(raw.get("updatedAt") or raw.get("updated_at") or "").strip() or now
    triggers = _normalize_triggers(raw, base_time=_parse_iso_datetime(created_at))
    actions = _normalize_actions(raw)
    trigger_phrases: list[str] = []
    listen_enabled = False
    for trigger in triggers:
        if trigger.get("type") != "event":
            continue
        listen_enabled = listen_enabled or bool(trigger.get("enabled", True))
        trigger_phrases.extend([str(item or "").strip() for item in trigger.get("phrases") or [] if str(item or "").strip()])
    execution_history = _normalize_execution_history(raw.get("execution_history") or raw.get("executionHistory"))
    return {
        "id": task_id,
        "title": title,
        "description": description,
        "status": _normalize_status(str(raw.get("status") or "todo")),
        "source": str(raw.get("source") or "manual").strip() or "manual",
        "task_type": _normalize_task_type(raw.get("task_type") or raw.get("taskType")),
        "project_id": str(raw.get("project_id") or raw.get("projectId") or "").strip(),
        "listen_enabled": listen_enabled,
        "trigger_phrases": trigger_phrases,
        "triggers": triggers,
        "actions": actions,
        "next_run_at": _resolve_next_run_at(raw, triggers),
        "last_run_at": _format_datetime(_parse_iso_datetime(raw.get("last_run_at") or raw.get("lastRunAt"))),
        "execution_count": max(0, int(raw.get("execution_count") or raw.get("executionCount") or len(execution_history) or 0)),
        "execution_history": execution_history,
        "created_by": _normalize_username(str(raw.get("created_by") or raw.get("createdBy") or username)),
        "created_at": created_at,
        "updated_at": updated_at,
    }


def _task_configuration_changed(existing: dict[str, Any], candidate: dict[str, Any]) -> bool:
    scalar_keys = (
        "title",
        "description",
        "source",
        "task_type",
        "project_id",
        "listen_enabled",
        "trigger_phrases",
        "next_run_at",
    )
    if any(existing.get(key) != candidate.get(key) for key in scalar_keys):
        return True

    def comparable_trigger(trigger: dict[str, Any]) -> dict[str, Any]:
        payload = trigger if isinstance(trigger, dict) else {}
        schedule = payload.get("schedule") if isinstance(payload.get("schedule"), dict) else {}
        return {
            "type": payload.get("type"),
            "enabled": payload.get("enabled"),
            "source": payload.get("source"),
            "phrases": payload.get("phrases") or [],
            "schedule": {
                "run_at": schedule.get("run_at") or "",
                "next_run_at": schedule.get("next_run_at") or "",
                "interval_seconds": schedule.get("interval_seconds") or 0,
            },
        }

    def comparable_action(action: dict[str, Any]) -> dict[str, Any]:
        payload = action if isinstance(action, dict) else {}
        return {
            "type": payload.get("type"),
            "enabled": payload.get("enabled"),
            "label": payload.get("label") or "",
            "params": payload.get("params") if isinstance(payload.get("params"), dict) else {},
        }

    existing_triggers = [comparable_trigger(item) for item in existing.get("triggers") or []]
    candidate_triggers = [comparable_trigger(item) for item in candidate.get("triggers") or []]
    existing_actions = [comparable_action(item) for item in existing.get("actions") or []]
    candidate_actions = [comparable_action(item) for item in candidate.get("actions") or []]
    return existing_triggers != candidate_triggers or existing_actions != candidate_actions


def _read_payload() -> dict[str, Any]:
    path = _task_store_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "tasks": []}
    if not isinstance(payload, dict):
        return {"version": 1, "tasks": []}
    tasks = payload.get("tasks")
    if not isinstance(tasks, list):
        payload["tasks"] = []
    return payload


def _write_payload(payload: dict[str, Any]) -> None:
    path = _task_store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def list_global_assistant_tasks(*, username: str, project_id: str = "", include_done: bool = True) -> list[dict[str, Any]]:
    owner = _normalize_username(username)
    normalized_project_id = str(project_id or "").strip()
    with _TASK_LOCK:
        tasks = [
            _normalize_task(task, username=owner)
            for task in _read_payload().get("tasks", [])
            if isinstance(task, dict)
        ]
    result: list[dict[str, Any]] = []
    for task in tasks:
        if task.get("created_by") != owner:
            continue
        task_project_id = str(task.get("project_id") or "").strip()
        if normalized_project_id and task_project_id and task_project_id != normalized_project_id:
            continue
        if not include_done and task.get("status") not in _ACTIVE_STATUSES:
            continue
        result.append(task)
    return sorted(result, key=lambda item: str(item.get("created_at") or ""), reverse=True)


def upsert_global_assistant_task(*, username: str, task: dict[str, Any], project_id: str = "") -> dict[str, Any]:
    owner = _normalize_username(username)
    normalized_project_id = str(project_id or "").strip()
    normalized = _normalize_task({**(task or {}), "project_id": (task or {}).get("project_id") or normalized_project_id}, username=owner)
    normalized["created_by"] = owner
    normalized["updated_at"] = _now_iso()
    with _TASK_LOCK:
        payload = _read_payload()
        tasks = [item for item in payload.get("tasks", []) if isinstance(item, dict)]
        replaced = False
        for index, existing in enumerate(tasks):
            if str(existing.get("id") or existing.get("task_id") or "").strip() != normalized["id"]:
                continue
            if _normalize_username(str(existing.get("created_by") or existing.get("createdBy") or owner)) != owner:
                continue
            existing_normalized = _normalize_task(existing, username=owner)
            if (
                existing_normalized.get("status") == "doing"
                and _task_configuration_changed(existing_normalized, normalized)
            ):
                raise ValueError("进行中的任务不允许编辑")
            normalized["created_at"] = str(existing.get("created_at") or existing.get("createdAt") or normalized["created_at"])
            if not any(key in (task or {}) for key in ("execution_count", "executionCount")):
                normalized["execution_count"] = existing_normalized.get("execution_count", 0)
            if not any(key in (task or {}) for key in ("execution_history", "executionHistory")):
                normalized["execution_history"] = existing_normalized.get("execution_history", [])
            if not any(key in (task or {}) for key in ("last_run_at", "lastRunAt")):
                normalized["last_run_at"] = existing_normalized.get("last_run_at", "")
            tasks[index] = normalized
            replaced = True
            break
        if not replaced:
            tasks.append(normalized)
        payload["tasks"] = tasks
        _write_payload(payload)
    return normalized


def update_global_assistant_task(*, username: str, task_id: str, updates: dict[str, Any], project_id: str = "") -> dict[str, Any] | None:
    owner = _normalize_username(username)
    target_id = str(task_id or "").strip()
    if not target_id:
        return None
    with _TASK_LOCK:
        payload = _read_payload()
        tasks = [item for item in payload.get("tasks", []) if isinstance(item, dict)]
        for index, existing in enumerate(tasks):
            if str(existing.get("id") or existing.get("task_id") or "").strip() != target_id:
                continue
            if _normalize_username(str(existing.get("created_by") or existing.get("createdBy") or owner)) != owner:
                continue
            merged = {**existing, **(updates or {}), "id": target_id}
            normalized = upsert_global_assistant_task(username=owner, task=merged, project_id=project_id)
            return normalized
        payload["tasks"] = tasks
    return None


def delete_global_assistant_task(*, username: str, task_id: str) -> bool:
    owner = _normalize_username(username)
    target_id = str(task_id or "").strip()
    if not target_id:
        return False
    with _TASK_LOCK:
        payload = _read_payload()
        tasks = [item for item in payload.get("tasks", []) if isinstance(item, dict)]
        next_tasks = [
            item
            for item in tasks
            if not (
                str(item.get("id") or item.get("task_id") or "").strip() == target_id
                and _normalize_username(str(item.get("created_by") or item.get("createdBy") or owner)) == owner
            )
        ]
        if len(next_tasks) == len(tasks):
            return False
        payload["tasks"] = next_tasks
        _write_payload(payload)
    return True


def _list_all_tasks() -> list[dict[str, Any]]:
    with _TASK_LOCK:
        return [
            _normalize_task(task, username=str(task.get("created_by") or task.get("createdBy") or "anonymous"))
            for task in _read_payload().get("tasks", [])
            if isinstance(task, dict)
        ]


def _execute_actions(
    task: dict[str, Any],
    *,
    trigger_type: str,
    message_text: str = "",
    source_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for action in task.get("actions") or []:
        if not isinstance(action, dict) or not bool(action.get("enabled", True)):
            continue
        action_type = str(action.get("type") or "record").strip() or "record"
        if action_type == "system_speech":
            try:
                speech_result = _enqueue_system_speech_action(task, action)
            except Exception as exc:
                logger.exception("failed to queue system speech reminder")
                results.append(
                    {
                        "action_id": str(action.get("id") or "").strip(),
                        "action_type": action_type,
                        "status": "failed",
                        "trigger_type": trigger_type,
                        "message": str(exc).strip()[:200] or "系统提醒播报失败",
                    }
                )
            else:
                queued = bool(speech_result.get("queued"))
                queued_count = int(speech_result.get("queued_count") or 1)
                results.append(
                    {
                        "action_id": str(action.get("id") or "").strip(),
                        "action_type": action_type,
                        "status": "queued" if queued else "failed",
                        "trigger_type": trigger_type,
                        "message": (
                            f"系统提醒已加入播报队列（{queued_count}次）"
                            if queued
                            else str(speech_result.get("reason") or "系统提醒播报未入队").strip()[:200]
                        ),
                        "queued_count": queued_count if queued else 0,
                    }
                )
            continue
        if action_type == "project_chat" and is_feishu_auto_archive_action(action):
            try:
                archive_result = archive_feishu_task_message(
                    task=task,
                    action=action,
                    message_text=message_text,
                    source_context=source_context,
                )
            except Exception as exc:
                logger.exception("failed to write feishu archive document")
                results.append(
                    {
                        "action_id": str(action.get("id") or "").strip(),
                        "action_type": action_type,
                        "status": "failed",
                        "trigger_type": trigger_type,
                        "message": str(exc).strip()[:200] or "飞书群文档写入失败",
                    }
                )
            else:
                results.append(
                    {
                        "action_id": str(action.get("id") or "").strip(),
                        "action_type": action_type,
                        "status": "saved",
                        "trigger_type": trigger_type,
                        "message": str(archive_result.get("message") or "飞书群文档写入成功").strip()[:200],
                        "archive_key": archive_result.get("archive_key") or "",
                        "category": archive_result.get("category") or "",
                        "document_title": archive_result.get("document_title") or "",
                        "doc_id": archive_result.get("doc_id") or archive_result.get("document_id") or "",
                        "document_id": archive_result.get("document_id") or archive_result.get("doc_id") or "",
                        "doc_url": archive_result.get("doc_url") or "",
                        "writer_type": archive_result.get("writer_type") or "",
                        "writer_mode": archive_result.get("writer_mode") or "",
                        "sheet_id": archive_result.get("sheet_id") or "",
                        "table_id": archive_result.get("table_id") or "",
                        "record_id": archive_result.get("record_id") or "",
                        "created": bool(archive_result.get("created")),
                    }
                )
            continue
        if action_type == "project_chat":
            try:
                dynamic_result = _execute_dynamic_project_chat_action(
                    task,
                    action,
                    trigger_type=trigger_type,
                    message_text=message_text,
                    source_context=source_context,
                )
            except Exception as exc:
                logger.exception("failed to execute dynamic global assistant task")
                results.append(
                    {
                        "action_id": str(action.get("id") or "").strip(),
                        "action_type": action_type,
                        "status": "failed",
                        "trigger_type": trigger_type,
                        "message": str(exc).strip()[:200] or "动态任务执行失败",
                    }
                )
            else:
                status = str(dynamic_result.get("status") or "").strip() or "completed"
                results.append(
                    {
                        "action_id": str(action.get("id") or "").strip(),
                        "action_type": action_type,
                        "status": status,
                        "trigger_type": trigger_type,
                        "message": str(dynamic_result.get("message") or "动态任务已执行").strip()[:200],
                        "dynamic_action_count": dynamic_result.get("dynamic_action_count", 0),
                    }
                )
            continue
        if action_type == "feishu_message":
            try:
                from services.feishu_scheduled_reminder_service import send_feishu_scheduled_message

                send_result = send_feishu_scheduled_message(task=task, action=action)
            except Exception as exc:
                logger.exception("failed to send feishu scheduled reminder")
                results.append(
                    {
                        "action_id": str(action.get("id") or "").strip(),
                        "action_type": action_type,
                        "status": "failed",
                        "trigger_type": trigger_type,
                        "message": str(exc).strip()[:200] or "飞书定时提醒发送失败",
                    }
                )
            else:
                results.append(
                    {
                        "action_id": str(action.get("id") or "").strip(),
                        "action_type": action_type,
                        "status": str(send_result.get("status") or "sent").strip() or "sent",
                        "trigger_type": trigger_type,
                        "message": str(send_result.get("message") or "飞书定时提醒已发送").strip()[:200],
                        "chat_id": send_result.get("chat_id") or "",
                    }
                )
            continue
        status = "completed"
        if action_type in {"project_chat", "file_processing", "webhook", "system_speech"}:
            # The generic engine records intent and execution history here; concrete runners can be
            # attached per action type without changing the task schema.
            status = "recorded"
        results.append(
            {
                "action_id": str(action.get("id") or "").strip(),
                "action_type": action_type,
                "status": status,
                "trigger_type": trigger_type,
                "message": str(action.get("label") or action_type).strip()[:200],
            }
        )
    if not results:
        results.append(
            {
                "action_id": "",
                "action_type": "record",
                "status": "completed",
                "trigger_type": trigger_type,
                "message": "任务执行已记录",
            }
        )
    return results


def _extract_json_object(value: str) -> dict[str, Any]:
    text = str(value or "").strip()
    if not text:
        return {}
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S)
    if fenced:
        text = fenced.group(1).strip()
    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _normalize_dynamic_actions(plan: dict[str, Any]) -> list[dict[str, Any]]:
    raw_actions = plan.get("actions") if isinstance(plan.get("actions"), list) else []
    result: list[dict[str, Any]] = []
    for item in raw_actions:
        if not isinstance(item, dict):
            continue
        action_type = str(item.get("type") or "").strip().lower()
        if action_type not in {"system_speech"}:
            continue
        text = str(item.get("text") or item.get("message") or "").strip()
        if not text:
            continue
        try:
            repeat = int(item.get("repeat") or item.get("count") or 1)
        except (TypeError, ValueError):
            repeat = 1
        result.append(
            {
                "type": action_type,
                "text": text,
                "repeat": max(1, min(repeat, 10)),
            }
        )
    return result


def _strip_simple_reminder_control_text(text: str) -> str:
    normalized = str(text or "").strip()
    if not normalized:
        return ""
    if "提醒：" in normalized:
        normalized = normalized.split("提醒：", 1)[1]
    elif "提醒:" in normalized:
        normalized = normalized.split("提醒:", 1)[1]
    normalized = re.sub(r"(?:共)?(?:提醒|播报|重复(?:执行)?|说)[0-9一二两三四五六七八九十两]+[次遍]", "", normalized)
    normalized = re.sub(r"[，,。；;！!\s]+$", "", normalized).strip()
    normalized = re.sub(r"^[，,。；;：:\s]+", "", normalized).strip()
    return normalized


def _extract_simple_reminder_repeat(text: str) -> int:
    for match in re.finditer(
        r"(?:共)?(?:提醒|播报|重复(?:执行)?|说)([0-9一二两三四五六七八九十两]+)[次遍]",
        str(text or ""),
    ):
        parsed = _parse_chinese_number(match.group(1))
        if parsed:
            return max(1, min(parsed, 10))
    return 1


def _infer_simple_reminder_dynamic_actions(task: dict[str, Any], message_text: str = "") -> list[dict[str, Any]]:
    text = " ".join(
        str(item or "").strip()
        for item in (message_text, task.get("description"), task.get("title"))
        if str(item or "").strip()
    )
    if not text or not any(term in text for term in _SCHEDULE_INTENT_TERMS):
        return []
    if not (
        str(task.get("task_type") or task.get("taskType") or "").strip().lower() == "reminder"
        or _contains_system_speech_intent(text)
        or "提醒" in text
    ):
        return []
    repeat = _extract_simple_reminder_repeat(text)
    candidates = [
        _strip_simple_reminder_control_text(str(task.get("description") or "")),
        _strip_simple_reminder_control_text(str(message_text or "")),
        _strip_simple_reminder_control_text(str(task.get("title") or "")),
    ]
    speech_text = next((item for item in candidates if item), "")
    if not speech_text:
        return []
    return [{"type": "system_speech", "text": speech_text, "repeat": repeat}]


def _dynamic_task_chat_session_id(task: dict[str, Any]) -> str:
    task_id = str(task.get("id") or "task").strip() or "task"
    return f"chat-session-global-task-{task_id[:80]}"


def _record_async_dynamic_action_result(
    *,
    username: str,
    task_id: str,
    action_id: str,
    result: dict[str, Any],
) -> None:
    owner = _normalize_username(username)
    target_id = str(task_id or "").strip()
    target_action_id = str(action_id or "").strip()
    if not target_id or not target_action_id:
        return
    with _TASK_LOCK:
        payload = _read_payload()
        tasks = [item for item in payload.get("tasks", []) if isinstance(item, dict)]
        changed = False
        for task in tasks:
            if str(task.get("id") or task.get("task_id") or "").strip() != target_id:
                continue
            if _normalize_username(str(task.get("created_by") or task.get("createdBy") or owner)) != owner:
                continue
            history = task.get("execution_history") if isinstance(task.get("execution_history"), list) else []
            for execution in reversed(history):
                if not isinstance(execution, dict):
                    continue
                action_results = execution.get("action_results") if isinstance(execution.get("action_results"), list) else []
                for action_result in action_results:
                    if not isinstance(action_result, dict):
                        continue
                    if str(action_result.get("action_id") or "").strip() != target_action_id:
                        continue
                    if str(action_result.get("status") or "").strip().lower() != "queued":
                        continue
                    status = str(result.get("status") or "failed").strip().lower() or "failed"
                    action_result["status"] = status
                    action_result["message"] = str(result.get("message") or "").strip()[:500]
                    action_result["dynamic_action_count"] = int(result.get("dynamic_action_count") or 0)
                    execution["status"] = "failed" if status == "failed" else "completed"
                    execution["finished_at"] = _now_iso()
                    task["updated_at"] = execution["finished_at"]
                    if status == "failed" and str(execution.get("trigger_type") or "") == "schedule":
                        task["status"] = "todo"
                        task["next_run_at"] = _format_datetime(datetime.now(timezone.utc) + timedelta(seconds=60))
                    changed = True
                    break
                if changed:
                    break
            break
        if changed:
            payload["tasks"] = tasks
            _write_payload(payload)


def _execute_dynamic_project_chat_action(
    task: dict[str, Any],
    action: dict[str, Any],
    *,
    trigger_type: str,
    message_text: str = "",
    source_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    async def _run() -> dict[str, Any]:
        from models.requests import ProjectChatReq
        from routers import projects as projects_router
        from services.project_chat_execution_service import run_project_chat_once
        from services.system_speech_service import enqueue_system_speech

        project_id = str(task.get("project_id") or "").strip()
        username = _normalize_username(str(task.get("created_by") or "admin"))
        if not project_id:
            return {"status": "failed", "message": "动态任务缺少 project_id", "dynamic_action_count": 0}
        if projects_router.project_store.get(project_id) is None:
            return {"status": "failed", "message": f"项目不存在：{project_id}", "dynamic_action_count": 0}

        chat_session_id = _dynamic_task_chat_session_id(task)
        if projects_router.project_chat_store.get_session(project_id, username, chat_session_id) is None:
            projects_router.project_chat_store.create_session(
                project_id,
                username,
                f"动态任务：{str(task.get('title') or task.get('description') or '未命名任务')[:48]}",
                source_context={"source_type": "global_assistant_task", "platform": "system"},
                session_id=chat_session_id,
            )

        prompt = (
            "你是全局助手的动态任务执行器。请理解任务定义和触发上下文，输出 JSON 执行计划，不要输出解释文字。\n"
            "当前只允许使用这些安全动作：\n"
            "- system_speech: 系统语音播报。字段：text（播报正文），repeat（重复次数，1-10）。\n"
            "如果用户写“重复执行3次 / 重复3遍 / 说三次”，应把 repeat 设为 3，并把 text 设为真正要提醒的正文，"
            "如果用户写“共提醒2次 / 提醒2次 / 播报2遍”，也应把 repeat 设为 2，"
            "不要把“到时间提醒”“重复执行3次”等控制语句放进 text。\n"
            "输出格式：{\"actions\":[{\"type\":\"system_speech\",\"text\":\"...\",\"repeat\":1}],\"summary\":\"...\"}\n\n"
            f"任务标题：{task.get('title') or ''}\n"
            f"任务定义：{task.get('description') or ''}\n"
            f"触发类型：{trigger_type}\n"
            f"触发消息：{message_text}\n"
            f"上下文：{json.dumps(source_context or {}, ensure_ascii=False)[:2000]}"
        )
        params = action.get("params") if isinstance(action.get("params"), dict) else {}
        req = ProjectChatReq(
            message=prompt,
            chat_session_id=chat_session_id,
            chat_surface="global-assistant-task",
            source_context={"source_type": "global_assistant_task", "task_id": str(task.get("id") or "")},
            system_prompt="你只输出严格 JSON，不要 Markdown，不要解释。",
            temperature=0.0,
            max_tokens=800,
            auto_use_tools=False,
            task_tree_enabled=False,
            task_tree_auto_generate=False,
        )
        result = await run_project_chat_once(
            project_id=project_id,
            username=username,
            req=req,
            auth_payload={"sub": username, "role": "admin", "roles": ["admin"]},
            save_memory_snapshot=False,
            publish_realtime=False,
        )
        plan = _extract_json_object(result.content)
        dynamic_actions = _normalize_dynamic_actions(plan)
        if not dynamic_actions:
            return {
                "status": "failed",
                "message": "大模型未返回可执行动作",
                "dynamic_action_count": 0,
            }
        executed_count = 0
        for dynamic_action in dynamic_actions:
            if dynamic_action["type"] != "system_speech":
                continue
            for _ in range(int(dynamic_action["repeat"])):
                speech_result = await enqueue_system_speech(
                    str(dynamic_action["text"]),
                    owner_username=username,
                    role_ids=params.get("role_ids") if isinstance(params.get("role_ids"), list) else ["admin"],
                    source="global-assistant-dynamic-task",
                    require_enabled=bool(params.get("require_enabled", True)),
                )
                if not bool(speech_result.get("queued")):
                    return {
                        "status": "failed",
                        "message": str(speech_result.get("reason") or "系统播报未入队"),
                        "dynamic_action_count": executed_count,
                    }
                executed_count += 1
        summary = str(plan.get("summary") or "").strip()
        return {
            "status": "completed",
            "message": summary or f"动态任务已执行 {executed_count} 个动作",
            "dynamic_action_count": executed_count,
        }

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_run())
    future = loop.create_task(_run())

    def _on_done(task_future: asyncio.Task[dict[str, Any]]) -> None:
        try:
            async_result = task_future.result()
        except Exception as exc:
            logger.exception("dynamic global assistant task failed")
            async_result = {
                "status": "failed",
                "message": str(exc),
                "dynamic_action_count": 0,
            }
        _record_async_dynamic_action_result(
            username=str(task.get("created_by") or "admin"),
            task_id=str(task.get("id") or ""),
            action_id=str(action.get("id") or ""),
            result=async_result,
        )

    future.add_done_callback(_on_done)
    return {"status": "queued", "message": "动态任务已交给大模型执行", "dynamic_action_count": 0}


def _enqueue_system_speech_action(task: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
    params = action.get("params") if isinstance(action.get("params"), dict) else {}
    text = str(
        params.get("text")
        or params.get("message")
        or task.get("description")
        or task.get("title")
        or "提醒时间到了"
    ).strip()
    try:
        repeat = int(params.get("repeat") or params.get("count") or 1)
    except (TypeError, ValueError):
        repeat = 1
    repeat = max(1, min(repeat, 10))
    role_ids = params.get("role_ids") if isinstance(params.get("role_ids"), list) else ["admin"]
    require_enabled = bool(params.get("require_enabled", True))
    if not text:
        return {"queued": False, "reason": "语音内容为空"}
    if require_enabled:
        from services.system_speech_service import is_system_speech_allowed

        allowed, reason = is_system_speech_allowed(
            owner_username=str(task.get("created_by") or "").strip(),
            role_ids=role_ids,
        )
        if not allowed:
            return {"queued": False, "reason": reason}

    async def _enqueue() -> dict[str, Any]:
        from services.system_speech_service import enqueue_system_speech

        last_result: dict[str, Any] = {"queued": True}
        for _ in range(repeat):
            last_result = await enqueue_system_speech(
                text,
                owner_username=str(task.get("created_by") or "").strip(),
                role_ids=role_ids,
                source="global-assistant-task",
                require_enabled=False,
            )
            if not bool(last_result.get("queued")):
                return {**last_result, "queued_count": 0}
        return {**last_result, "queued_count": repeat}

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_enqueue())
    loop.create_task(_enqueue())
    return {"queued": True, "reason": "", "async": True, "queued_count": repeat}


def _calculate_following_schedule(task: dict[str, Any], *, finished_at: datetime) -> str:
    candidates: list[datetime] = []
    now = finished_at.astimezone(timezone.utc)
    for trigger in task.get("triggers") or []:
        if not isinstance(trigger, dict) or trigger.get("type") != "schedule" or not bool(trigger.get("enabled", True)):
            continue
        schedule = trigger.get("schedule") if isinstance(trigger.get("schedule"), dict) else {}
        interval_seconds = _normalize_interval_seconds(schedule.get("interval_seconds"))
        if interval_seconds > 0:
            candidates.append(now + timedelta(seconds=interval_seconds))
            continue
        next_run = _parse_iso_datetime(schedule.get("next_run_at") or schedule.get("run_at"))
        if next_run and next_run > now:
            candidates.append(next_run)
    return _format_datetime(min(candidates)) if candidates else ""


def execute_global_assistant_task(
    *,
    username: str,
    task_id: str,
    project_id: str = "",
    trigger_type: str = "manual",
    message_text: str = "",
    match_reason: str = "",
    source_context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    owner = _normalize_username(username)
    normalized_project_id = str(project_id or "").strip()
    target_id = str(task_id or "").strip()
    if not target_id:
        return None
    now = datetime.now(timezone.utc)
    now_iso = _format_datetime(now)
    with _TASK_LOCK:
        payload = _read_payload()
        tasks = [item for item in payload.get("tasks", []) if isinstance(item, dict)]
        for index, existing in enumerate(tasks):
            if str(existing.get("id") or existing.get("task_id") or "").strip() != target_id:
                continue
            if _normalize_username(str(existing.get("created_by") or existing.get("createdBy") or owner)) != owner:
                continue
            task = _normalize_task(existing, username=owner)
            if normalized_project_id and str(task.get("project_id") or "").strip() not in {"", normalized_project_id}:
                return None
            action_results = _execute_actions(
                task,
                trigger_type=trigger_type,
                message_text=message_text,
                source_context=source_context,
            )
            has_failed_action = any(str(item.get("status") or "").strip().lower() == "failed" for item in action_results)
            execution_record = {
                "id": f"run-{uuid.uuid4().hex[:12]}",
                "trigger_type": str(trigger_type or "manual").strip() or "manual",
                "status": "failed" if has_failed_action else "completed",
                "started_at": now_iso,
                "finished_at": _now_iso(),
                "message": str(message_text or "").strip()[:500],
                "match_reason": str(match_reason or "").strip()[:120],
                "action_results": action_results,
            }
            history = _normalize_execution_history([*task.get("execution_history", []), execution_record])
            task["execution_history"] = history
            task["execution_count"] = int(task.get("execution_count") or 0) + 1
            task["last_run_at"] = execution_record["finished_at"]
            task["updated_at"] = execution_record["finished_at"]
            if trigger_type == "schedule":
                task["next_run_at"] = _calculate_following_schedule(task, finished_at=now)
                if not task["next_run_at"] and has_failed_action:
                    task["next_run_at"] = _format_datetime(now + timedelta(seconds=60))
                elif not task["next_run_at"]:
                    task["status"] = "done"
                    for trigger in task.get("triggers") or []:
                        if not isinstance(trigger, dict) or trigger.get("type") != "schedule":
                            continue
                        schedule = trigger.get("schedule") if isinstance(trigger.get("schedule"), dict) else {}
                        if _normalize_interval_seconds(schedule.get("interval_seconds")) <= 0:
                            schedule["next_run_at"] = ""
                            schedule["run_at"] = ""
                            trigger["schedule"] = schedule
            tasks[index] = task
            payload["tasks"] = tasks
            _write_payload(payload)
            return {**task, "latest_execution": execution_record}
    return None


def run_due_global_assistant_tasks(*, now: datetime | None = None) -> list[dict[str, Any]]:
    reference_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    results: list[dict[str, Any]] = []
    for task in _list_all_tasks():
        if task.get("status") not in _ACTIVE_STATUSES:
            continue
        next_run_at = _parse_iso_datetime(task.get("next_run_at"))
        if next_run_at is None or next_run_at > reference_time:
            continue
        executed = execute_global_assistant_task(
            username=str(task.get("created_by") or "anonymous"),
            task_id=str(task.get("id") or ""),
            project_id=str(task.get("project_id") or ""),
            trigger_type="schedule",
            match_reason="schedule-due",
            source_context={"scheduler": "global-assistant-task"},
        )
        if executed:
            results.append(executed)
    return results


async def _scheduler_loop(poll_interval_seconds: float) -> None:
    while True:
        try:
            executed = run_due_global_assistant_tasks()
            if executed:
                logger.info("executed due global assistant tasks", extra={"task_count": len(executed)})
        except Exception:
            logger.exception("global assistant task scheduler failed")
        await asyncio.sleep(max(1.0, float(poll_interval_seconds or 5.0)))


def start_global_assistant_task_scheduler(*, poll_interval_seconds: float = 5.0) -> asyncio.Task[None] | None:
    global _SCHEDULER_TASK
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return None
    with _SCHEDULER_LOCK:
        if _SCHEDULER_TASK is not None and not _SCHEDULER_TASK.done():
            return _SCHEDULER_TASK
        _SCHEDULER_TASK = loop.create_task(_scheduler_loop(poll_interval_seconds))
        return _SCHEDULER_TASK


async def stop_global_assistant_task_scheduler() -> None:
    global _SCHEDULER_TASK
    task = _SCHEDULER_TASK
    _SCHEDULER_TASK = None
    if task is None or task.done():
        return
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


def _compact_text(value: str) -> str:
    text = str(value or "").lower()
    text = re.sub(r"@[_a-z0-9一-鿿.-]+", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    return re.sub(r"[^0-9a-z一-鿿]+", "", text)


def _segment_text(value: str) -> list[str]:
    text = str(value or "").lower()
    text = re.sub(r"@[_a-z0-9一-鿿.-]+", " ", text)
    return [item for item in re.split(r"[^0-9a-z一-鿿]+", text) if item]


def _longest_common_substring_length(left: str, right: str) -> int:
    if not left or not right:
        return 0
    if len(left) > len(right):
        left, right = right, left
    previous = [0] * (len(right) + 1)
    best = 0
    for left_char in left:
        current = [0]
        for index, right_char in enumerate(right, start=1):
            value = previous[index - 1] + 1 if left_char == right_char else 0
            current.append(value)
            if value > best:
                best = value
        previous = current
    return best


def _extract_trigger_phrases_from_instruction(raw: str) -> list[str]:
    compact = _compact_text(raw)
    if not compact:
        return []
    phrases: list[str] = []
    for pattern in (
        r"有(.{1,24}?)(?:的时候|时)(?:提示|提醒|通知|播报)?",
        r"(?:监听|关注|监控)(?:到)?(.{1,24}?)(?:的时候|时|就|后|要|并|，|。|$)",
        r"(?:当|如果)(?:有)?(.{1,24}?)(?:的时候|时|就|后|，|。|$)",
    ):
        for match in re.finditer(pattern, compact):
            phrase = str(match.group(1) or "").strip()
            phrase = re.sub(r"^(?:有|出现|收到|发现)", "", phrase)
            phrase = re.sub(r"(?:提示|提醒|通知|播报|消息|内容)$", "", phrase)
            if len(phrase) >= 2 and phrase not in _GENERIC_CHINESE_TERMS:
                phrases.append(phrase)
    return phrases


def _extract_trigger_candidates(task: dict[str, Any]) -> list[str]:
    raw_values: list[str] = []
    raw_values.extend([str(item or "") for item in task.get("trigger_phrases") or []])
    raw_values.append(str(task.get("description") or ""))
    raw_values.append(str(task.get("title") or ""))
    candidates: list[str] = []
    for raw in raw_values:
        candidates.extend(_extract_trigger_phrases_from_instruction(raw))
        for segment in _segment_text(raw):
            if len(segment) < 2 or segment in _GENERIC_CHINESE_TERMS:
                continue
            candidates.append(segment)
        compact = _compact_text(raw)
        if compact and compact not in candidates:
            candidates.append(compact)
    seen: set[str] = set()
    result: list[str] = []
    for item in candidates:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _task_matches_text(task: dict[str, Any], message_text: str) -> tuple[bool, str]:
    message_compact = _compact_text(message_text)
    if len(message_compact) < 2:
        return False, "empty-message"
    for candidate in _extract_trigger_candidates(task):
        candidate_compact = _compact_text(candidate)
        if len(candidate_compact) < 2:
            continue
        if len(candidate_compact) >= 2 and candidate_compact in message_compact:
            return True, f"phrase:{candidate_compact[:32]}"
        if len(message_compact) >= 3 and message_compact in candidate_compact:
            return True, "message-contained-in-task"
        common_length = _longest_common_substring_length(candidate_compact, message_compact)
        if common_length >= 4 or (common_length >= 3 and min(len(candidate_compact), len(message_compact)) <= 6):
            return True, f"overlap:{common_length}"
    return False, "no-match"


def match_global_assistant_tasks_for_event(
    *,
    username: str,
    project_id: str = "",
    message_text: str,
    source_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    del source_context
    matches: list[dict[str, Any]] = []
    for task in list_global_assistant_tasks(username=username, project_id=project_id, include_done=False):
        if not bool(task.get("listen_enabled", True)):
            continue
        matched, reason = _task_matches_text(task, message_text)
        if not matched:
            continue
        matches.append({**task, "match_reason": reason})
    return matches


def process_global_assistant_tasks_for_event(
    *,
    username: str,
    project_id: str = "",
    message_text: str,
    source_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    processed: list[dict[str, Any]] = []
    for task in match_global_assistant_tasks_for_event(
        username=username,
        project_id=project_id,
        message_text=message_text,
        source_context=source_context,
    ):
        executed = execute_global_assistant_task(
            username=username,
            project_id=project_id,
            task_id=str(task.get("id") or ""),
            trigger_type="event",
            message_text=message_text,
            match_reason=str(task.get("match_reason") or ""),
            source_context=source_context,
        )
        processed.append({**task, "latest_execution": (executed or {}).get("latest_execution")})
    return processed
