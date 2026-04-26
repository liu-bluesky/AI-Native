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

from core.config import get_api_data_dir
from services.feishu_archive_writer_service import archive_feishu_task_message, is_feishu_auto_archive_action

logger = logging.getLogger(__name__)

_TASK_LOCK = threading.RLock()
_ACTIVE_STATUSES = {"todo", "doing"}
_EXECUTION_HISTORY_LIMIT = 50
_SCHEDULER_TASK: asyncio.Task[None] | None = None
_SCHEDULER_LOCK = threading.RLock()
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
    if action_type not in {"record", "notify", "system_speech", "project_chat", "file_processing", "webhook"}:
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


def _normalize_triggers(raw: dict[str, Any]) -> list[dict[str, Any]]:
    raw_triggers = raw.get("triggers") if isinstance(raw.get("triggers"), list) else []
    triggers = [_normalize_trigger(item) for item in raw_triggers if isinstance(item, dict)]
    if not triggers:
        event_trigger = _legacy_event_trigger(raw)
        schedule_trigger = _legacy_schedule_trigger(raw)
        triggers = [item for item in (event_trigger, schedule_trigger) if item]
    if not triggers:
        triggers = [_normalize_trigger({"type": "manual", "enabled": True}, fallback_type="manual")]
    return triggers


def _normalize_actions(raw: dict[str, Any]) -> list[dict[str, Any]]:
    raw_actions = raw.get("actions") if isinstance(raw.get("actions"), list) else []
    actions = [_normalize_action(item) for item in raw_actions if isinstance(item, dict)]
    if not actions and isinstance(raw.get("action"), dict):
        actions = [_normalize_action(raw.get("action"))]
    if (not actions or _actions_are_default_record(actions)) and _task_implies_system_speech(raw):
        return [
            _normalize_action(
                {
                    "type": "system_speech",
                    "label": "后台语音提醒",
                    "params": {"mode": "brief"},
                },
                fallback_type="system_speech",
            )
        ]
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
    triggers = _normalize_triggers(raw)
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
            execution_record = {
                "id": f"run-{uuid.uuid4().hex[:12]}",
                "trigger_type": str(trigger_type or "manual").strip() or "manual",
                "status": "completed",
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
