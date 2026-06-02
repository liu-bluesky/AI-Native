"""Generic external operation wait tasks with persistent local state."""

from __future__ import annotations

import threading
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from core.config import get_project_root
from services.cli_plugin_profile_service import (
    _cli_plugin_auth_config,
    _default_cli_plugin_login_command,
    _default_cli_plugin_test_command,
    execute_cli_plugin_profile_command_streaming,
    execute_cli_plugin_profile_command,
    serialize_cli_plugin_profile,
    update_cli_plugin_profile,
)
from services.cli_plugin_market_service import get_cli_plugin

_TASK_LOCK = threading.RLock()
_TASK_SUBSCRIBERS: dict[str, set[Callable[[dict[str, Any]], None]]] = defaultdict(set)
_TASK_THREADS: dict[str, threading.Thread] = {}
_ACTIVE_STATUSES = {"queued", "running", "waiting_user_action"}
_TERMINAL_STATUSES = {"succeeded", "failed", "timeout"}
_AUTH_POLL_INTERVAL_SEC = 5
_AUTH_POLL_TIMEOUT_SEC = 600
_UNAUTHENTICATED_AUTH_STATUS_PATTERNS = (
    "no user logged in",
    "only bot",
    '"identity":"bot"',
    '"identity": "bot"',
    "'identity':'bot'",
    "'identity': 'bot'",
)
_LARK_AUTH_DOMAIN_OPTIONS = (
    "all",
    "approval",
    "attendance",
    "base",
    "calendar",
    "contact",
    "doc",
    "drive",
    "im",
    "mail",
    "minutes",
    "okr",
    "sheets",
    "slides",
    "task",
    "vc",
    "wiki",
)


def _plugin_auth_config(plugin_id: str) -> dict[str, Any]:
    return _cli_plugin_auth_config(plugin_id)


def _plugin_operation_kind(plugin_id: str) -> str:
    auth = _plugin_auth_config(plugin_id)
    return str(auth.get("operation_kind") or "auth_login").strip() or "auth_login"


def _plugin_operation_label(plugin_id: str) -> str:
    auth = _plugin_auth_config(plugin_id)
    return str(auth.get("operation_label") or "网页登录授权").strip() or "网页登录授权"


def _plugin_unauthenticated_markers(plugin_id: str) -> tuple[str, ...]:
    auth = _plugin_auth_config(plugin_id)
    configured = tuple(
        str(item or "").strip().lower()
        for item in (auth.get("unauthenticated_markers") or [])
        if str(item or "").strip()
    )
    return configured or _UNAUTHENTICATED_AUTH_STATUS_PATTERNS


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _task_root_path() -> Path:
    return get_project_root() / ".ai-employee" / "operation-wait-tasks"


def _task_path(task_id: str) -> Path:
    return _task_root_path() / f"{str(task_id or '').strip()}.json"


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
    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return normalized


def _build_task_status_label(status: str) -> str:
    normalized_status = str(status or "").strip().lower()
    return {
        "queued": "排队中",
        "running": "执行中",
        "waiting_user_action": "等待操作",
        "succeeded": "已完成",
        "failed": "执行失败",
        "timeout": "执行超时",
        "cancelled": "已取消",
    }.get(normalized_status, "状态未知")


def _build_task_status_reason(
    *,
    status: str,
    execution: dict[str, Any] | None = None,
    error_message: str = "",
) -> str:
    normalized_status = str(status or "").strip().lower()
    if normalized_status == "queued":
        return "任务已创建，等待后台执行"
    if normalized_status == "running":
        return "正在执行操作"
    if normalized_status == "waiting_user_action":
        return "等待你完成当前操作；完成后系统会自动检测并继续。"
    if error_message:
        return error_message
    preview = str((execution or {}).get("stderr") or (execution or {}).get("stdout") or "").strip()
    if preview:
        return preview[-240:]
    if normalized_status == "succeeded":
        return "操作完成，检测通过"
    if normalized_status == "timeout":
        return "操作在限定时间内未完成"
    if normalized_status == "failed":
        return "操作执行失败"
    return ""


def _strip_ansi_control_sequences(value: str) -> str:
    import re

    text = str(value or "")
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    text = re.sub(r"\x1b\][^\x07]*(?:\x07|\x1b\\)", "", text)
    return text.replace("\x1b", "")


def _execution_text(execution: dict[str, Any] | None) -> str:
    payload = execution or {}
    return "\n".join(
        str(payload.get(key) or "")
        for key in (
            "stdout",
            "stderr",
            "next_step",
            "status_label",
            "status",
            "detail",
            "message",
        )
    )


def _execution_has_lark_auth_domain_prompt(execution: dict[str, Any] | None) -> bool:
    text = _strip_ansi_control_sequences(_execution_text(execution)).lower()
    if "业务域" not in text:
        return False
    return any(marker in text for marker in ("选择", "请选择", "select", "choose"))


def _build_lark_auth_domain_interaction_schema() -> dict[str, Any]:
    return {
        "title": "选择 lark-cli 授权业务域",
        "description": "请选择需要授权的业务域后继续。",
        "submit_label": "确认并继续",
        "fallback_label": "稍后处理",
        "response_mode": "interaction",
        "schema": [
            {
                "label": "业务域",
                "prop": "domains",
                "componentName": "ElCheckboxGroup",
                "required": True,
                "colAttrs": {"span": 24},
                "attrs": {"class": "message-terminal-form__checkbox-group"},
                "rules": [
                    {
                        "required": True,
                        "type": "array",
                        "min": 1,
                        "message": "请至少选择一项业务域",
                        "trigger": "change",
                    }
                ],
                "children": [
                    {
                        "componentName": "ElCheckbox",
                        "attrs": {"label": value, "value": value},
                    }
                    for value in _LARK_AUTH_DOMAIN_OPTIONS
                ],
            }
        ],
        "model": {"domains": []},
    }


def _operation_interaction_schema_for_execution(
    plugin_id: str,
    execution: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if str(plugin_id or "").strip().lower() not in {"lark-cli", "feishu-cli"}:
        return None
    if _execution_has_lark_auth_domain_prompt(execution):
        return _build_lark_auth_domain_interaction_schema()
    return None


def _operation_action_type_for_execution(
    plugin_id: str,
    execution: dict[str, Any] | None,
) -> str:
    if str((execution or {}).get("authorization_url") or "").strip():
        return "open_url"
    if _operation_interaction_schema_for_execution(plugin_id, execution):
        return "interaction_form"
    return "none"


def _emit_task_event(task: dict[str, Any], *, event_type: str = "task_update") -> None:
    username = str(task.get("created_by") or "").strip()
    if not username:
        return
    payload = {"type": event_type, "task": dict(task)}
    callbacks = list(_TASK_SUBSCRIBERS.get(username, set()))
    for callback in callbacks:
        try:
            callback(payload)
        except Exception:
            continue


def subscribe_operation_wait_task_events(
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


def get_operation_wait_task(task_id: str) -> dict[str, Any] | None:
    normalized_task_id = str(task_id or "").strip()
    if not normalized_task_id:
        return None
    path = _task_path(normalized_task_id)
    if not path.is_file():
        return None
    return _read_task_file(path)


def list_operation_wait_tasks(
    *,
    username: str = "",
    plugin_id: str = "",
    operation_kind: str = "",
    statuses: set[str] | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    root = _task_root_path()
    if not root.is_dir():
        return []
    normalized_username = str(username or "").strip()
    normalized_plugin_id = str(plugin_id or "").strip().lower()
    normalized_operation_kind = str(operation_kind or "").strip().lower()
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
        if normalized_operation_kind and str(task.get("operation_kind") or "").strip().lower() != normalized_operation_kind:
            continue
        if normalized_statuses and str(task.get("status") or "").strip().lower() not in normalized_statuses:
            continue
        items.append(task)
    items.sort(
        key=lambda task: (
            str(task.get("updated_at") or task.get("created_at") or ""),
            str(task.get("task_id") or ""),
        ),
        reverse=True,
    )
    safe_limit = max(1, min(int(limit or 20), 200))
    return items[:safe_limit]


def _update_task(task_id: str, **patch: Any) -> dict[str, Any]:
    with _TASK_LOCK:
        task = get_operation_wait_task(task_id)
        if task is None:
            raise ValueError(f"Unknown operation wait task: {task_id}")
        task.update(patch)
        normalized = _write_task(task)
    _emit_task_event(normalized, event_type="task_update")
    return normalized


def merge_operation_wait_task_metadata(
    task_id: str,
    metadata_patch: dict[str, Any] | None,
) -> dict[str, Any] | None:
    normalized_task_id = str(task_id or "").strip()
    if not normalized_task_id or not isinstance(metadata_patch, dict) or not metadata_patch:
        return None
    with _TASK_LOCK:
        task = get_operation_wait_task(normalized_task_id)
        if task is None:
            return None
        metadata = dict(task.get("metadata") or {})
        metadata.update(metadata_patch)
        task["metadata"] = metadata
        normalized = _write_task(task)
    _emit_task_event(normalized, event_type="task_update")
    return normalized


def claim_operation_wait_task_resume(task_id: str) -> dict[str, Any] | None:
    normalized_task_id = str(task_id or "").strip()
    if not normalized_task_id:
        return None
    with _TASK_LOCK:
        task = get_operation_wait_task(normalized_task_id)
        if task is None:
            return None
        if str(task.get("status") or "").strip().lower() != "succeeded":
            return None
        metadata = dict(task.get("metadata") or {})
        if str(metadata.get("resume_dispatched_at") or "").strip():
            return None
        agent_runtime_meta = (
            metadata.get("agent_runtime_v2")
            if isinstance(metadata.get("agent_runtime_v2"), dict)
            else {}
        )
        has_resume_command = bool(str(metadata.get("resume_command") or "").strip())
        has_agent_runtime_resume = bool(str(agent_runtime_meta.get("run_id") or "").strip())
        if not has_resume_command and not has_agent_runtime_resume:
            return None
        metadata["resume_dispatched_at"] = _utc_now_iso()
        task["metadata"] = metadata
        normalized = _write_task(task)
    _emit_task_event(normalized, event_type="task_update")
    return normalized


def _find_active_task(plugin_id: str, username: str) -> dict[str, Any] | None:
    active_tasks = list_operation_wait_tasks(
        username=username,
        plugin_id=plugin_id,
        operation_kind=_plugin_operation_kind(plugin_id),
        statuses=set(_ACTIVE_STATUSES),
        limit=1,
    )
    return active_tasks[0] if active_tasks else None


def _execution_has_authorization_prompt(execution: dict[str, Any] | None) -> bool:
    payload = execution or {}
    plugin_id = str(payload.get("plugin_id") or "").strip()
    if payload.get("requires_user_action"):
        return True
    if str(payload.get("authorization_url") or "").strip():
        return True
    if _operation_interaction_schema_for_execution(plugin_id, execution):
        return True
    text = _execution_text(payload).lower()
    return any(
        pattern in text
        for pattern in (
            "authorize",
            "authorization",
            "auth login",
            "open the following link",
            "please visit",
            "浏览器",
            "授权",
            "登录",
        )
    )


def _is_authenticated_test_execution(execution: dict[str, Any] | None) -> bool:
    payload = execution or {}
    if not payload.get("ok"):
        return False
    text = "\n".join(str(payload.get(key) or "") for key in ("stdout", "stderr")).lower()
    plugin_id = str(payload.get("plugin_id") or "").strip()
    if any(pattern in text for pattern in _plugin_unauthenticated_markers(plugin_id)):
        return False
    return True


def _verify_cli_plugin_authenticated(plugin_id: str, username: str) -> dict[str, Any] | None:
    test_command = _default_cli_plugin_test_command(plugin_id)
    if not test_command:
        return None
    return execute_cli_plugin_profile_command(
        plugin_id,
        username,
        command=test_command,
        timeout_sec=30,
    )


def _build_auth_verification_error_execution(
    plugin_id: str,
    *,
    error: Exception,
) -> dict[str, Any]:
    test_command = _default_cli_plugin_test_command(plugin_id)
    raw_error = str(error or "").strip() or error.__class__.__name__
    return {
        "ok": False,
        "timed_out": False,
        "interactive": False,
        "requires_user_action": False,
        "authorization_url": "",
        "status": "failed",
        "status_label": "登录检测失败",
        "next_step": "请检查 CLI 插件配置、网络代理或域名解析后重试。",
        "command": test_command,
        "plugin_id": str(plugin_id or "").strip(),
        "stdout": "",
        "stderr": raw_error,
        "exit_code": None,
        "error": raw_error,
        "error_type": error.__class__.__name__,
    }


def _mark_operation_task_succeeded(
    task_id: str,
    *,
    plugin_id: str,
    username: str,
    task: dict[str, Any],
    execution: dict[str, Any],
    status_reason: str = "授权完成，检测通过",
) -> dict[str, Any]:
    test_command = _default_cli_plugin_test_command(plugin_id)
    update_cli_plugin_profile(
        plugin_id,
        username,
        status="authenticated",
        status_label="已登录",
        test_command=test_command,
        last_test_at=_utc_now_iso(),
        last_test_ok=True,
        last_error="",
        metadata={**dict(task.get("metadata") or {}), "last_execution": execution},
    )
    profile = serialize_cli_plugin_profile(plugin_id, username, auth_payload={"sub": username})
    return _update_task(
        task_id,
        status="succeeded",
        status_label=_build_task_status_label("succeeded"),
        status_reason=status_reason,
        finished_at=_utc_now_iso(),
        exit_code=execution.get("exit_code"),
        ok=bool(execution.get("ok", True)),
        execution_ok=bool(execution.get("ok", True)),
        stdout=str(execution.get("stdout") or "").strip(),
        stderr=str(execution.get("stderr") or "").strip(),
        error_message="",
        execution=execution,
        profile=profile,
    )


def _mark_operation_task_waiting_for_user_action(
    task_id: str,
    *,
    plugin_id: str,
    username: str,
    task: dict[str, Any],
    execution: dict[str, Any],
) -> dict[str, Any] | None:
    current = get_operation_wait_task(task_id)
    if current is None:
        return None
    if str(current.get("status") or "").strip().lower() in _TERMINAL_STATUSES:
        return current
    if not _execution_has_authorization_prompt(execution):
        return current
    interaction_schema = _operation_interaction_schema_for_execution(plugin_id, execution)
    action_type = _operation_action_type_for_execution(plugin_id, execution)
    execution_payload = {
        **dict(execution or {}),
        "verification": dict(current.get("execution") or {}).get("verification") or {},
        "action_type": action_type,
    }
    if interaction_schema:
        execution_payload["interaction_schema"] = interaction_schema
    update_cli_plugin_profile(
        plugin_id,
        username,
        status="pending_auth",
        status_label="等待授权",
        login_command=str(task.get("command") or "").strip(),
        last_login_at=str(task.get("started_at") or "") or _utc_now_iso(),
        last_error="",
        metadata={**dict(task.get("metadata") or {}), "last_execution": execution},
    )
    profile = serialize_cli_plugin_profile(plugin_id, username, auth_payload={"sub": username})
    return _update_task(
        task_id,
        status="waiting_user_action",
        status_label=_build_task_status_label("waiting_user_action"),
        status_reason=_build_task_status_reason(status="waiting_user_action", execution=execution),
        finished_at="",
        exit_code=execution.get("exit_code"),
        ok=bool(execution.get("ok")),
        execution_ok=bool(execution.get("ok")),
        stdout=str(execution.get("stdout") or "").strip(),
        stderr=str(execution.get("stderr") or "").strip(),
        error_message="",
        execution=execution_payload,
        profile=profile,
    )


def create_cli_plugin_auth_operation_task(
    plugin_id: str,
    *,
    username: str,
    login_command: str = "",
    metadata: dict[str, Any] | None = None,
    timeout_sec: int = 120,
) -> dict[str, Any]:
    plugin = get_cli_plugin(plugin_id, include_status=False)
    if plugin is None:
        raise ValueError(f"Unsupported CLI plugin: {plugin_id}")
    normalized_username = str(username or "").strip()
    if not normalized_username:
        raise ValueError("username is required")
    normalized_plugin_id = str(plugin.get("id") or "").strip()
    existing_task = _find_active_task(normalized_plugin_id, normalized_username)
    if existing_task is not None:
        return existing_task

    command = str(login_command or "").strip() or _default_cli_plugin_login_command(normalized_plugin_id)
    if not command:
        raise ValueError("operation command is required")
    safe_timeout = max(15, min(int(timeout_sec or 120), 600))
    task = {
        "task_id": f"operation-wait-{uuid.uuid4().hex}",
        "operation_kind": _plugin_operation_kind(normalized_plugin_id),
        "operation_label": _plugin_operation_label(normalized_plugin_id),
        "plugin_id": normalized_plugin_id,
        "plugin": plugin,
        "created_by": normalized_username,
        "status": "queued",
        "status_label": _build_task_status_label("queued"),
        "status_reason": _build_task_status_reason(status="queued"),
        "timeout_sec": safe_timeout,
        "command": command,
        "ok": False,
        "execution_ok": False,
        "exit_code": None,
        "stdout": "",
        "stderr": "",
        "error_message": "",
        "execution": {},
        "profile": {},
        "metadata": dict(metadata or {}),
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
        target=_run_cli_plugin_auth_operation_task,
        args=(str(normalized_task["task_id"]),),
        name=f"operation-wait-{normalized_task['task_id']}",
        daemon=True,
    )
    with _TASK_LOCK:
        _TASK_THREADS[str(normalized_task["task_id"])] = thread
    thread.start()
    return normalized_task


def _run_cli_plugin_auth_operation_task(task_id: str) -> None:
    try:
        task = _update_task(
            task_id,
            status="running",
            status_label=_build_task_status_label("running"),
            status_reason=_build_task_status_reason(status="running"),
            started_at=_utc_now_iso(),
        )
        username = str(task.get("created_by") or "").strip()
        plugin_id = str(task.get("plugin_id") or "").strip()
        def _handle_execution_update(update: dict[str, Any]) -> None:
            if not _execution_has_authorization_prompt(update):
                return
            current_task = get_operation_wait_task(task_id)
            if str((current_task or {}).get("status") or "").strip().lower() == "waiting_user_action":
                return
            _mark_operation_task_waiting_for_user_action(
                task_id,
                plugin_id=plugin_id,
                username=username,
                task=task,
                execution=update,
            )

        execution = execute_cli_plugin_profile_command_streaming(
            plugin_id,
            username,
            command=str(task.get("command") or "").strip(),
            timeout_sec=max(15, min(int(task.get("timeout_sec") or 120), 600)),
            on_update=_handle_execution_update,
        )
        try:
            verification_execution = _verify_cli_plugin_authenticated(plugin_id, username)
        except Exception as exc:
            verification_execution = _build_auth_verification_error_execution(
                plugin_id,
                error=exc,
            )
        if _is_authenticated_test_execution(verification_execution):
            _mark_operation_task_succeeded(
                task_id,
                plugin_id=plugin_id,
                username=username,
                task=task,
                execution=verification_execution or execution,
            )
            return

        execution_ok = bool(execution.get("ok"))
        has_authorization_prompt = _execution_has_authorization_prompt(execution)
        if execution.get("timed_out") and has_authorization_prompt:
            profile_status = "pending_auth"
            profile_status_label = "等待授权"
            task_status = "waiting_user_action"
        elif execution.get("timed_out"):
            profile_status = "ready"
            profile_status_label = "授权超时"
            task_status = "timeout"
        elif execution.get("requires_user_action") or execution_ok or has_authorization_prompt:
            profile_status = "pending_auth"
            profile_status_label = "等待授权"
            task_status = "waiting_user_action"
        else:
            profile_status = "ready"
            profile_status_label = "登录失败"
            task_status = "failed"
        update_cli_plugin_profile(
            plugin_id,
            username,
            status=profile_status,
            status_label=profile_status_label,
            login_command=str(task.get("command") or "").strip(),
            last_login_at=_utc_now_iso(),
            last_error="" if execution.get("ok") or execution.get("requires_user_action") else str(execution.get("stderr") or execution.get("stdout") or "").strip(),
            metadata={
                **dict(task.get("metadata") or {}),
                "last_execution": execution,
                "last_verification_execution": verification_execution or {},
            },
        )
        profile = serialize_cli_plugin_profile(plugin_id, username, auth_payload={"sub": username})
        interaction_schema = _operation_interaction_schema_for_execution(plugin_id, execution)
        action_type = _operation_action_type_for_execution(plugin_id, execution)
        execution_payload = {
            **dict(execution or {}),
            "verification": verification_execution or {},
            "action_type": action_type,
        }
        if interaction_schema:
            execution_payload["interaction_schema"] = interaction_schema
        task = _update_task(
            task_id,
            status=task_status,
            status_label=_build_task_status_label(task_status),
            status_reason=_build_task_status_reason(status=task_status, execution=execution),
            finished_at=_utc_now_iso() if task_status in _TERMINAL_STATUSES else "",
            exit_code=execution.get("exit_code"),
            ok=execution_ok,
            execution_ok=execution_ok,
            stdout=str(execution.get("stdout") or "").strip(),
            stderr=str(execution.get("stderr") or "").strip(),
            error_message="" if execution.get("ok") or execution.get("requires_user_action") else str(execution.get("stderr") or execution.get("stdout") or "").strip(),
            execution=execution_payload,
            profile=profile,
        )
        if task_status == "waiting_user_action":
            _poll_auth_operation_until_authenticated(task_id, plugin_id=plugin_id, username=username)
    except Exception as exc:
        _update_task(
            task_id,
            status="failed",
            status_label=_build_task_status_label("failed"),
            status_reason=_build_task_status_reason(status="failed", error_message=str(exc)),
            finished_at=_utc_now_iso(),
            ok=False,
            error_message=str(exc),
        )
    finally:
        with _TASK_LOCK:
            _TASK_THREADS.pop(str(task_id or "").strip(), None)


def _poll_auth_operation_until_authenticated(
    task_id: str,
    *,
    plugin_id: str,
    username: str,
) -> None:
    test_command = _default_cli_plugin_test_command(plugin_id)
    if not test_command:
        return
    deadline = time.time() + _AUTH_POLL_TIMEOUT_SEC
    while time.time() < deadline:
        time.sleep(_AUTH_POLL_INTERVAL_SEC)
        task = get_operation_wait_task(task_id)
        if task is None:
            return
        if str(task.get("status") or "").strip().lower() != "waiting_user_action":
            return
        try:
            execution = _verify_cli_plugin_authenticated(plugin_id, username)
        except Exception as exc:
            execution = _build_auth_verification_error_execution(
                plugin_id,
                error=exc,
            )
            update_cli_plugin_profile(
                plugin_id,
                username,
                status="ready",
                status_label="登录检测失败",
                last_error=str(execution.get("stderr") or execution.get("error") or "").strip(),
                metadata={**dict(task.get("metadata") or {}), "last_verification_execution": execution},
            )
            profile = serialize_cli_plugin_profile(plugin_id, username, auth_payload={"sub": username})
            _update_task(
                task_id,
                status="failed",
                status_label=_build_task_status_label("failed"),
                status_reason=_build_task_status_reason(status="failed", execution=execution),
                finished_at=_utc_now_iso(),
                ok=False,
                execution_ok=False,
                exit_code=execution.get("exit_code"),
                stdout=str(execution.get("stdout") or "").strip(),
                stderr=str(execution.get("stderr") or "").strip(),
                error_message=str(execution.get("stderr") or execution.get("error") or "").strip(),
                execution=execution,
                profile=profile,
            )
            return
        if not _is_authenticated_test_execution(execution):
            continue
        _mark_operation_task_succeeded(
            task_id,
            plugin_id=plugin_id,
            username=username,
            task=task,
            execution=execution,
        )
        return

    update_cli_plugin_profile(
        plugin_id,
        username,
        status="ready",
        status_label="授权超时",
        last_error="授权等待超时，请重新发起登录。",
    )
    profile = serialize_cli_plugin_profile(plugin_id, username, auth_payload={"sub": username})
    _update_task(
        task_id,
        status="timeout",
        status_label=_build_task_status_label("timeout"),
        status_reason="授权等待超时，请重新发起登录。",
        finished_at=_utc_now_iso(),
        ok=False,
        execution_ok=False,
        error_message="授权等待超时，请重新发起登录。",
        profile=profile,
    )


# Backward-compatible function names for existing market routes/tests. The module
# name is intentionally generic; callers should prefer operation_* names.
subscribe_login_task_events = subscribe_operation_wait_task_events
get_login_task = get_operation_wait_task
list_login_tasks = list_operation_wait_tasks
merge_login_task_metadata = merge_operation_wait_task_metadata
claim_login_task_resume = claim_operation_wait_task_resume
create_login_task = create_cli_plugin_auth_operation_task
_poll_login_task_until_authenticated = _poll_auth_operation_until_authenticated
