"""CLI plugin user profile service."""

from __future__ import annotations

import getpass
import threading
import re
import shlex
import subprocess
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from core.config import get_project_root
from core.ownership import normalize_share_scope, normalize_shared_usernames, ownership_payload
from stores.factory import cli_plugin_profile_store
from stores.json.cli_plugin_profile_store import CliPluginUserProfileRecord


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_username(value: object) -> str:
    return str(value or "").strip()


def _normalize_plugin_id(value: object) -> str:
    return str(value or "").strip().lower()


def _safe_segment(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in str(value or "").strip())


_URL_PATTERN = re.compile(r"https?://[^\s<>\"]+")
_DEFAULT_INTERACTIVE_COMMAND_MARKERS = (
    " auth login",
    " login",
    " authorize",
    " oauth",
    " device",
    " config init",
)
_DEFAULT_USER_ACTION_MARKERS = (
    "authorize",
    "authorization",
    "open the following link",
    "please visit",
    "verification url",
    "device code",
    "browser",
    "浏览器",
    "授权",
    "登录",
)
def get_cli_plugin_user_runtime_dirs(
    plugin_id: str,
    owner_username: str,
) -> dict[str, str]:
    normalized_plugin_id = _normalize_plugin_id(plugin_id)
    normalized_owner = _normalize_username(owner_username)
    runtime_root = (
        get_project_root()
        / ".ai-employee"
        / "cli-runtime"
        / "users"
        / _safe_segment(normalized_owner)
        / _safe_segment(normalized_plugin_id)
    )
    home_dir = runtime_root / "home"
    return {
        "runtime_root": str(runtime_root),
        "home_dir": str(home_dir),
        "config_dir": str(home_dir / ".config"),
        "data_dir": str(home_dir / ".local" / "share"),
        "cache_dir": str(home_dir / ".cache"),
    }


def ensure_cli_plugin_user_runtime_dirs(
    plugin_id: str,
    owner_username: str,
) -> dict[str, str]:
    dirs = get_cli_plugin_user_runtime_dirs(plugin_id, owner_username)
    for key in ("runtime_root", "home_dir", "config_dir", "data_dir", "cache_dir"):
        Path(dirs[key]).mkdir(parents=True, exist_ok=True)
    return dirs


def _default_profile(
    plugin_id: str,
    owner_username: str,
) -> CliPluginUserProfileRecord:
    dirs = get_cli_plugin_user_runtime_dirs(plugin_id, owner_username)
    return CliPluginUserProfileRecord(
        plugin_id=plugin_id,
        owner_username=owner_username,
        created_by=owner_username,
        runtime_root=dirs["runtime_root"],
        home_dir=dirs["home_dir"],
        config_dir=dirs["config_dir"],
        data_dir=dirs["data_dir"],
        cache_dir=dirs["cache_dir"],
    )


def get_cli_plugin_profile(
    plugin_id: str,
    owner_username: str,
) -> CliPluginUserProfileRecord | None:
    normalized_plugin_id = _normalize_plugin_id(plugin_id)
    normalized_owner = _normalize_username(owner_username)
    if not normalized_plugin_id or not normalized_owner:
        return None
    return cli_plugin_profile_store.get_profile(normalized_plugin_id, normalized_owner)


def ensure_cli_plugin_profile(
    plugin_id: str,
    owner_username: str,
    *,
    actor_username: str = "",
) -> CliPluginUserProfileRecord:
    from services.plugins.cli_plugin_market_service import get_cli_plugin

    normalized_plugin_id = _normalize_plugin_id(plugin_id)
    normalized_owner = _normalize_username(owner_username)
    if not normalized_plugin_id:
        raise ValueError("plugin_id is required")
    if not normalized_owner:
        raise ValueError("owner_username is required")
    plugin = get_cli_plugin(normalized_plugin_id, include_status=False)
    if plugin is None:
        raise ValueError(f"Unsupported CLI plugin: {normalized_plugin_id}")
    existing = get_cli_plugin_profile(normalized_plugin_id, normalized_owner)
    if existing is not None:
        dirs = ensure_cli_plugin_user_runtime_dirs(normalized_plugin_id, normalized_owner)
        changed = False
        for key in ("runtime_root", "home_dir", "config_dir", "data_dir", "cache_dir"):
            current = str(getattr(existing, key, "") or "").strip()
            if current != dirs[key]:
                setattr(existing, key, dirs[key])
                changed = True
        if changed:
            existing.updated_at = _now_iso()
            cli_plugin_profile_store.save_profile(existing)
        return existing
    dirs = ensure_cli_plugin_user_runtime_dirs(normalized_plugin_id, normalized_owner)
    now = _now_iso()
    item = _default_profile(normalized_plugin_id, normalized_owner)
    item.created_by = _normalize_username(actor_username) or normalized_owner
    item.runtime_root = dirs["runtime_root"]
    item.home_dir = dirs["home_dir"]
    item.config_dir = dirs["config_dir"]
    item.data_dir = dirs["data_dir"]
    item.cache_dir = dirs["cache_dir"]
    item.status = "ready"
    item.status_label = "已初始化"
    item.updated_at = now
    cli_plugin_profile_store.save_profile(item)
    return item


def update_cli_plugin_profile(
    plugin_id: str,
    owner_username: str,
    *,
    status: str | None = None,
    status_label: str | None = None,
    login_command: str | None = None,
    logout_command: str | None = None,
    test_command: str | None = None,
    last_login_at: str | None = None,
    last_logout_at: str | None = None,
    last_test_at: str | None = None,
    last_test_ok: bool | None = None,
    last_error: str | None = None,
    share_scope: str | None = None,
    shared_with_usernames: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> CliPluginUserProfileRecord:
    item = ensure_cli_plugin_profile(plugin_id, owner_username, actor_username=owner_username)
    if status is not None:
        item.status = str(status or "").strip() or item.status
    if status_label is not None:
        item.status_label = str(status_label or "").strip() or item.status_label
    if login_command is not None:
        item.login_command = str(login_command or "").strip()
    if logout_command is not None:
        item.logout_command = str(logout_command or "").strip()
    if test_command is not None:
        item.test_command = str(test_command or "").strip()
    if last_login_at is not None:
        item.last_login_at = str(last_login_at or "").strip()
    if last_logout_at is not None:
        item.last_logout_at = str(last_logout_at or "").strip()
    if last_test_at is not None:
        item.last_test_at = str(last_test_at or "").strip()
    if last_test_ok is not None:
        item.last_test_ok = bool(last_test_ok)
    if last_error is not None:
        item.last_error = str(last_error or "").strip()
    if share_scope is not None:
        item.share_scope = normalize_share_scope(share_scope)
    if shared_with_usernames is not None:
        item.shared_with_usernames = normalize_shared_usernames(
            shared_with_usernames,
            owner_username=item.created_by or item.owner_username,
        )
    if metadata is not None:
        item.metadata = dict(metadata)
    item.updated_at = _now_iso()
    cli_plugin_profile_store.save_profile(item)
    return item


def build_cli_plugin_profile_runtime_env(
    plugin_id: str,
    owner_username: str,
) -> dict[str, str]:
    profile = ensure_cli_plugin_profile(plugin_id, owner_username, actor_username=owner_username)
    dirs = ensure_cli_plugin_user_runtime_dirs(plugin_id, owner_username)
    if profile.home_dir != dirs["home_dir"]:
        profile.home_dir = dirs["home_dir"]
        profile.config_dir = dirs["config_dir"]
        profile.data_dir = dirs["data_dir"]
        profile.cache_dir = dirs["cache_dir"]
        profile.runtime_root = dirs["runtime_root"]
        profile.updated_at = _now_iso()
        cli_plugin_profile_store.save_profile(profile)
    return {
        "HOME": profile.home_dir,
        "XDG_CONFIG_HOME": profile.config_dir,
        "XDG_DATA_HOME": profile.data_dir,
        "XDG_CACHE_HOME": profile.cache_dir,
        "CLI_PLUGIN_RUNTIME_ROOT": profile.runtime_root,
        "CLI_PLUGIN_RUNTIME_OWNER": profile.owner_username,
        "CLI_PLUGIN_RUNTIME_PROFILE_STATUS": profile.status,
    }


def _default_cli_plugin_login_command(plugin_id: str) -> str:
    normalized_plugin_id = _normalize_plugin_id(plugin_id)
    auth = _cli_plugin_auth_config(normalized_plugin_id)
    if auth:
        return str(auth.get("login_command") or "").strip()
    return ""


def _default_cli_plugin_logout_command(plugin_id: str) -> str:
    normalized_plugin_id = _normalize_plugin_id(plugin_id)
    auth = _cli_plugin_auth_config(normalized_plugin_id)
    if auth:
        return str(auth.get("logout_command") or "").strip()
    return ""


def _default_cli_plugin_test_command(plugin_id: str) -> str:
    normalized_plugin_id = _normalize_plugin_id(plugin_id)
    auth = _cli_plugin_auth_config(normalized_plugin_id)
    if auth:
        return str(auth.get("test_command") or "").strip()
    return ""


def _cli_plugin_auth_config(plugin_id: str) -> dict[str, Any]:
    from services.plugins.cli_plugin_market_service import get_cli_plugin

    plugin = get_cli_plugin(plugin_id, include_status=False)
    auth = plugin.get("auth") if isinstance(plugin, dict) else {}
    return dict(auth or {}) if isinstance(auth, dict) else {}


def _extract_first_url(*values: object) -> str:
    for value in values:
        match = _URL_PATTERN.search(str(value or ""))
        if match:
            return str(match.group(0) or "").strip()
    return ""


def _pattern_matches(pattern: str, value: str) -> bool:
    normalized_pattern = str(pattern or "").strip()
    if not normalized_pattern:
        return False
    try:
        return re.search(normalized_pattern, value, re.IGNORECASE) is not None
    except re.error:
        return normalized_pattern.lower() in value.lower()


def _parse_shell_like_command(command: str) -> list[str]:
    try:
        return shlex.split(str(command or "").strip())
    except ValueError:
        return str(command or "").strip().split()


def _is_help_command(command: str) -> bool:
    return any(
        str(arg or "").strip().lower() in {"-h", "--help", "help"}
        for arg in _parse_shell_like_command(command)
    )


def _is_interactive_auth_command(command: str, *, plugin_id: str = "") -> bool:
    normalized_command = str(command or "").strip().lower()
    if not normalized_command:
        return False
    if _is_help_command(normalized_command):
        return False
    auth = _cli_plugin_auth_config(plugin_id)
    patterns = list(auth.get("interactive_command_patterns") or []) + list(auth.get("command_patterns") or [])
    if any(_pattern_matches(str(pattern or ""), normalized_command) for pattern in patterns):
        return True
    return any(marker in normalized_command for marker in _DEFAULT_INTERACTIVE_COMMAND_MARKERS)


def _build_cli_plugin_execution_result(
    *,
    plugin_id: str = "",
    command: str,
    stdout: str,
    stderr: str,
    exit_code: int | None,
    timed_out: bool,
    runtime_metadata: dict[str, Any],
) -> dict[str, Any]:
    normalized_command = str(command or "").strip()
    normalized_stdout = str(stdout or "")
    normalized_stderr = str(stderr or "")
    interactive = _is_interactive_auth_command(normalized_command, plugin_id=plugin_id)
    authorization_url = _extract_first_url(normalized_stdout, normalized_stderr)
    combined_output = f"{normalized_stdout}\n{normalized_stderr}".lower()
    auth = _cli_plugin_auth_config(plugin_id)
    markers = [
        str(value or "").strip().lower()
        for value in (auth.get("user_action_markers") or [])
        if str(value or "").strip()
    ] or list(_DEFAULT_USER_ACTION_MARKERS)
    requires_user_action = bool(
        interactive
        and (
            timed_out
            or bool(authorization_url)
            or any(marker in combined_output for marker in markers)
        )
    )
    ok = exit_code == 0 and not timed_out
    status = "succeeded" if ok else "failed"
    status_label = "执行成功" if ok else "执行失败"
    next_step = ""
    if requires_user_action:
        status = "pending_user_action"
        status_label = "等待网页授权"
        next_step = "请在浏览器打开授权链接完成授权；完成后系统会自动检测并继续。"
    elif timed_out:
        status = "timed_out"
        status_label = "执行超时"
        next_step = "命令超时结束，请检查命令是否需要人工交互。"
    elif not ok:
        next_step = "请检查命令输出后重试。"
    return {
        "ok": ok,
        "timed_out": timed_out,
        "interactive": interactive,
        "requires_user_action": requires_user_action,
        "authorization_url": authorization_url,
        "status": status,
        "status_label": status_label,
        "next_step": next_step,
        "command": normalized_command,
        "plugin_id": _normalize_plugin_id(plugin_id),
        "stdout": normalized_stdout,
        "stderr": normalized_stderr,
        "exit_code": exit_code,
        **runtime_metadata,
    }


def execute_cli_plugin_profile_command(
    plugin_id: str,
    owner_username: str,
    *,
    command: str,
    timeout_sec: int = 120,
) -> dict[str, Any]:
    from services.plugins.cli_plugin_market_service import build_cli_plugin_runtime_environment

    normalized_plugin_id = _normalize_plugin_id(plugin_id)
    normalized_owner = _normalize_username(owner_username)
    normalized_command = str(command or "").strip()
    if not normalized_plugin_id:
        raise ValueError("plugin_id is required")
    if not normalized_owner:
        raise ValueError("owner_username is required")
    if not normalized_command:
        raise ValueError("command is required")
    ensure_cli_plugin_profile(normalized_plugin_id, normalized_owner, actor_username=normalized_owner)
    env, runtime_metadata = build_cli_plugin_runtime_environment(
        plugin_id=normalized_plugin_id,
        owner_username=normalized_owner,
    )
    safe_timeout = max(15, min(int(timeout_sec or 120), 600))
    try:
        completed = subprocess.run(
            ["/bin/zsh", "-lc", normalized_command],
            cwd=str(get_project_root()),
            capture_output=True,
            text=True,
            timeout=safe_timeout,
            env=env,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(str(exc)) from exc
    except subprocess.TimeoutExpired as exc:
        return _build_cli_plugin_execution_result(
            command=normalized_command,
            stdout=str(exc.stdout or ""),
            stderr=str(exc.stderr or ""),
            exit_code=None,
            timed_out=True,
            plugin_id=normalized_plugin_id,
            runtime_metadata=runtime_metadata,
        )
    return _build_cli_plugin_execution_result(
        command=normalized_command,
        stdout=str(completed.stdout or ""),
        stderr=str(completed.stderr or ""),
        exit_code=int(completed.returncode),
        timed_out=False,
        plugin_id=normalized_plugin_id,
        runtime_metadata=runtime_metadata,
    )


def execute_cli_plugin_profile_command_streaming(
    plugin_id: str,
    owner_username: str,
    *,
    command: str,
    timeout_sec: int = 120,
    on_update: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    from services.plugins.cli_plugin_market_service import build_cli_plugin_runtime_environment

    normalized_plugin_id = _normalize_plugin_id(plugin_id)
    normalized_owner = _normalize_username(owner_username)
    normalized_command = str(command or "").strip()
    if not normalized_plugin_id:
        raise ValueError("plugin_id is required")
    if not normalized_owner:
        raise ValueError("owner_username is required")
    if not normalized_command:
        raise ValueError("command is required")
    ensure_cli_plugin_profile(normalized_plugin_id, normalized_owner, actor_username=normalized_owner)
    env, runtime_metadata = build_cli_plugin_runtime_environment(
        plugin_id=normalized_plugin_id,
        owner_username=normalized_owner,
    )
    safe_timeout = max(15, min(int(timeout_sec or 120), 600))
    try:
        process = subprocess.Popen(
            ["/bin/zsh", "-lc", normalized_command],
            cwd=str(get_project_root()),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(str(exc)) from exc

    stdout_parts: list[str] = []
    stderr_parts: list[str] = []
    output_lock = threading.Lock()

    def _emit_update() -> None:
        if on_update is None:
            return
        with output_lock:
            stdout = "".join(stdout_parts)
            stderr = "".join(stderr_parts)
        update = _build_cli_plugin_execution_result(
            command=normalized_command,
            stdout=stdout,
            stderr=stderr,
            exit_code=None,
            timed_out=False,
            plugin_id=normalized_plugin_id,
            runtime_metadata=runtime_metadata,
        )
        try:
            on_update(update)
        except Exception:
            return

    def _read_stream(stream: Any, sink: list[str]) -> None:
        if stream is None:
            return
        try:
            for chunk in iter(stream.readline, ""):
                if not chunk:
                    break
                with output_lock:
                    sink.append(str(chunk or ""))
                _emit_update()
        finally:
            try:
                stream.close()
            except Exception:
                pass

    stdout_thread = threading.Thread(
        target=_read_stream,
        args=(process.stdout, stdout_parts),
        name="cli-plugin-profile-stdout",
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_read_stream,
        args=(process.stderr, stderr_parts),
        name="cli-plugin-profile-stderr",
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()
    timed_out = False
    exit_code: int | None
    try:
        exit_code = process.wait(timeout=safe_timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        exit_code = None
    stdout_thread.join(timeout=2)
    stderr_thread.join(timeout=2)
    with output_lock:
        stdout = "".join(stdout_parts)
        stderr = "".join(stderr_parts)
    return _build_cli_plugin_execution_result(
        command=normalized_command,
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        timed_out=timed_out,
        plugin_id=normalized_plugin_id,
        runtime_metadata=runtime_metadata,
    )


def serialize_cli_plugin_profile(
    plugin_id: str,
    owner_username: str,
    *,
    auth_payload: dict | None = None,
) -> dict[str, Any]:
    from services.plugins.cli_plugin_market_service import get_cli_plugin

    plugin = get_cli_plugin(plugin_id, include_status=False)
    if plugin is None:
        raise ValueError(f"Unsupported CLI plugin: {plugin_id}")
    profile = ensure_cli_plugin_profile(plugin_id, owner_username, actor_username=owner_username)
    payload = asdict(profile)
    payload["runtime_env"] = {
        "HOME": profile.home_dir,
        "XDG_CONFIG_HOME": profile.config_dir,
        "XDG_DATA_HOME": profile.data_dir,
        "XDG_CACHE_HOME": profile.cache_dir,
    }
    payload["plugin_id"] = _normalize_plugin_id(plugin_id)
    payload["owner_username"] = _normalize_username(owner_username)
    payload["ownership"] = ownership_payload(profile, auth_payload)
    payload["plugin"] = {
        "id": str(plugin.get("id") or "").strip(),
        "name": str(plugin.get("name") or "").strip(),
        "binary_name": str(plugin.get("binary_name") or "").strip(),
        "install_command": str(plugin.get("install_command") or "").strip(),
    }
    payload["current_os_user"] = getpass.getuser()
    return payload
