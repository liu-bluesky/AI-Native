"""Background CLI plugin install tasks with persistent local state."""

from __future__ import annotations

import threading
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from core.config import get_project_root
from services.cli_plugin_market_service import get_cli_plugin, install_cli_plugin

_TASK_LOCK = threading.RLock()
_TASK_SUBSCRIBERS: dict[str, set[Callable[[dict[str, Any]], None]]] = defaultdict(set)
_TASK_THREADS: dict[str, threading.Thread] = {}
_ACTIVE_STATUSES = {"queued", "running"}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _task_root_path() -> Path:
    return get_project_root() / ".ai-employee" / "cli-plugin-market" / "tasks"


def _task_path(task_id: str) -> Path:
    normalized_task_id = str(task_id or "").strip()
    return _task_root_path() / f"{normalized_task_id}.json"


def _read_task_file(path: Path) -> dict[str, Any] | None:
    try:
        import json

        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_task(task: dict[str, Any]) -> dict[str, Any]:
    import json

    task_id = str(task.get("task_id") or "").strip()
    if not task_id:
        raise ValueError("task_id is required")
    normalized = dict(task)
    normalized["task_id"] = task_id
    normalized["updated_at"] = _utc_now_iso()
    normalized["event_version"] = int(normalized.get("event_version") or 0) + 1
    path = _task_path(task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return normalized


def _update_task(task_id: str, **patch: Any) -> dict[str, Any]:
    with _TASK_LOCK:
        task = get_install_task(task_id)
        if task is None:
            raise ValueError(f"Unknown install task: {task_id}")
        task.update(patch)
        normalized = _write_task(task)
    _emit_task_event(normalized, event_type="task_update")
    return normalized


def _task_sort_key(task: dict[str, Any]) -> tuple[str, str]:
    return (
        str(task.get("updated_at") or task.get("created_at") or ""),
        str(task.get("task_id") or ""),
    )


def _build_task_status_label(status: str) -> str:
    normalized_status = str(status or "").strip().lower()
    return {
        "queued": "排队中",
        "running": "安装中",
        "succeeded": "安装完成",
        "failed": "安装失败",
        "timeout": "安装超时",
    }.get(normalized_status, "状态未知")


def _build_task_status_reason(
    *,
    status: str,
    stdout: str = "",
    stderr: str = "",
    error_message: str = "",
) -> str:
    normalized_status = str(status or "").strip().lower()
    if normalized_status == "queued":
        return "任务已创建，等待后台执行"
    if normalized_status == "running":
        return "正在后台执行安装命令"
    if error_message:
        return error_message
    preview = str(stderr or stdout or "").strip()
    if preview:
        return preview[-240:]
    if normalized_status == "succeeded":
        return "安装命令已执行完成"
    if normalized_status == "timeout":
        return "安装命令在限定时间内未完成"
    if normalized_status == "failed":
        return "安装命令执行失败"
    return ""


def _emit_task_event(task: dict[str, Any], *, event_type: str = "task_update") -> None:
    username = str(task.get("created_by") or "").strip()
    if not username:
        return
    payload = {
        "type": event_type,
        "task": dict(task),
    }
    callbacks = list(_TASK_SUBSCRIBERS.get(username, set()))
    for callback in callbacks:
        try:
            callback(payload)
        except Exception:
            continue


def subscribe_install_task_events(
    username: str,
    callback: Callable[[dict[str, Any]], None],
) -> Callable[[], None]:
    normalized_username = str(username or "").strip()
    if not normalized_username:
        raise ValueError("username is required")
    with _TASK_LOCK:
        _TASK_SUBSCRIBERS[normalized_username].add(callback)

    def _unsubscribe() -> None:
        with _TASK_LOCK:
            callbacks = _TASK_SUBSCRIBERS.get(normalized_username)
            if callbacks is None:
                return
            callbacks.discard(callback)
            if not callbacks:
                _TASK_SUBSCRIBERS.pop(normalized_username, None)

    return _unsubscribe


def get_install_task(task_id: str) -> dict[str, Any] | None:
    normalized_task_id = str(task_id or "").strip()
    if not normalized_task_id:
        return None
    path = _task_path(normalized_task_id)
    if not path.is_file():
        return None
    return _read_task_file(path)


def list_install_tasks(
    *,
    username: str = "",
    plugin_id: str = "",
    statuses: set[str] | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    root = _task_root_path()
    if not root.is_dir():
        return []
    normalized_username = str(username or "").strip()
    normalized_plugin_id = str(plugin_id or "").strip().lower()
    normalized_statuses = {
        str(item or "").strip().lower()
        for item in (statuses or set())
        if str(item or "").strip()
    }
    items: list[dict[str, Any]] = []
    for path in root.glob("*.json"):
        task = _read_task_file(path)
        if task is None:
            continue
        if normalized_username and str(task.get("created_by") or "").strip() != normalized_username:
            continue
        if normalized_plugin_id and str(task.get("plugin_id") or "").strip().lower() != normalized_plugin_id:
            continue
        if normalized_statuses and str(task.get("status") or "").strip().lower() not in normalized_statuses:
            continue
        items.append(task)
    items.sort(key=_task_sort_key, reverse=True)
    safe_limit = max(1, min(int(limit or 20), 200))
    return items[:safe_limit]


def _find_active_task(plugin_id: str, username: str) -> dict[str, Any] | None:
    active_tasks = list_install_tasks(
        username=username,
        plugin_id=plugin_id,
        statuses=set(_ACTIVE_STATUSES),
        limit=1,
    )
    return active_tasks[0] if active_tasks else None


def create_install_task(
    plugin_id: str,
    *,
    username: str,
    timeout_sec: int = 1800,
) -> dict[str, Any]:
    plugin = get_cli_plugin(plugin_id, include_status=False)
    if plugin is None:
        raise ValueError(f"Unsupported CLI plugin: {plugin_id}")
    normalized_username = str(username or "").strip()
    if not normalized_username:
        raise ValueError("username is required")

    existing_task = _find_active_task(str(plugin.get("id") or "").strip(), normalized_username)
    if existing_task is not None:
        return existing_task

    safe_timeout = max(30, min(int(timeout_sec or 1800), 7200))
    task = {
        "task_id": f"cli-plugin-install-{uuid.uuid4().hex}",
        "plugin_id": str(plugin.get("id") or "").strip(),
        "plugin": plugin,
        "created_by": normalized_username,
        "status": "queued",
        "status_label": _build_task_status_label("queued"),
        "status_reason": _build_task_status_reason(status="queued"),
        "timeout_sec": safe_timeout,
        "command": str(plugin.get("install_command") or "").strip(),
        "exit_code": None,
        "ok": False,
        "stdout": "",
        "stderr": "",
        "error_message": "",
        "install_status": {},
        "created_at": _utc_now_iso(),
        "started_at": "",
        "finished_at": "",
        "updated_at": "",
        "event_version": 0,
    }
    with _TASK_LOCK:
        normalized_task = _write_task(task)
    _emit_task_event(normalized_task, event_type="task_update")

    thread = threading.Thread(
        target=_run_install_task,
        args=(str(normalized_task["task_id"]),),
        name=f"cli-plugin-install-{normalized_task['task_id']}",
        daemon=True,
    )
    with _TASK_LOCK:
        _TASK_THREADS[str(normalized_task["task_id"])] = thread
    thread.start()
    return normalized_task


def _run_install_task(task_id: str) -> None:
    try:
        task = _update_task(
            task_id,
            status="running",
            status_label=_build_task_status_label("running"),
            status_reason=_build_task_status_reason(status="running"),
            started_at=_utc_now_iso(),
        )
        result = install_cli_plugin(
            str(task.get("plugin_id") or "").strip(),
            timeout_sec=max(30, min(int(task.get("timeout_sec") or 1800), 7200)),
        )
        status = "succeeded" if bool(result.get("ok")) else "failed"
        stdout = str(result.get("stdout") or "").strip()
        stderr = str(result.get("stderr") or "").strip()
        error_message = stderr if status == "failed" and stderr else ""
        _update_task(
            task_id,
            status=status,
            status_label=_build_task_status_label(status),
            status_reason=_build_task_status_reason(
                status=status,
                stdout=stdout,
                stderr=stderr,
                error_message=error_message,
            ),
            finished_at=_utc_now_iso(),
            exit_code=result.get("exit_code"),
            ok=bool(result.get("ok")),
            stdout=stdout,
            stderr=stderr,
            error_message=error_message,
            install_status=result.get("install_status") or {},
        )
    except TimeoutError as exc:
        _update_task(
            task_id,
            status="timeout",
            status_label=_build_task_status_label("timeout"),
            status_reason=_build_task_status_reason(
                status="timeout",
                error_message=str(exc),
            ),
            finished_at=_utc_now_iso(),
            ok=False,
            error_message=str(exc),
        )
    except Exception as exc:
        _update_task(
            task_id,
            status="failed",
            status_label=_build_task_status_label("failed"),
            status_reason=_build_task_status_reason(
                status="failed",
                error_message=str(exc),
            ),
            finished_at=_utc_now_iso(),
            ok=False,
            error_message=str(exc),
        )
    finally:
        with _TASK_LOCK:
            _TASK_THREADS.pop(str(task_id or "").strip(), None)
