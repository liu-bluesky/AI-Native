"""Curated CLI plugin marketplace helpers."""

from __future__ import annotations

import getpass
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from shutil import which
from typing import Any

from core.config import get_project_root

_STATUS_CACHE_TTL_SEC = 300
_CLI_PLUGIN_STATUS_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}

_CLI_PLUGIN_REGISTRY: tuple[dict[str, Any], ...] = (
    {
        "id": "feishu-cli",
        "name": "飞书 CLI",
        "description": "为 AI Agent 提供飞书侧工具能力，支持按官方安装命令一键接入。",
        "vendor": "Lark / Feishu",
        "category": "agent-plugin",
        "package_name": "@larksuite/cli",
        "binary_name": "lark-cli",
        "install_command": "npx @larksuite/cli@latest install",
        "docs_url": "https://open.feishu.cn/document/no_class/mcp-archive/feishu-cli-installation-guide.md",
        "ai_install_prompt": "帮我安装飞书 CLI：https://open.feishu.cn/document/no_class/mcp-archive/feishu-cli-installation-guide.md",
        "requires_restart": False,
        "tags": ["feishu", "agent", "cli", "official"],
    },
)


def _normalize_plugin_tags(values: object) -> list[str]:
    if not isinstance(values, (list, tuple)):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in values:
        value = str(item or "").strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(value)
    return normalized


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _plugin_status_store_path() -> Path:
    return get_project_root() / ".ai-employee" / "cli-plugin-market" / "install-state.json"


def _shared_host_skill_root() -> Path:
    return get_project_root() / ".ai-employee" / "skills" / "host-marketplace"


def _managed_host_skill_directories() -> tuple[Path, ...]:
    project_root = get_project_root()
    return (
        project_root / ".agents" / "skills",
        project_root / ".qoder" / "skills",
        project_root / ".codebuddy" / "skills",
        project_root / ".augment" / "skills",
    )


def _iter_directory_entries(path: Path) -> list[Path]:
    if not path.is_dir():
        return []
    try:
        return list(path.iterdir())
    except OSError:
        return []


def _is_alias_tree(path: Path) -> bool:
    if not path.is_dir() or path.is_symlink():
        return False
    entries = _iter_directory_entries(path)
    if not entries:
        return False
    for entry in entries:
        if not entry.is_symlink():
            return False
        if not entry.exists():
            return False
    return True


def _replace_with_directory_symlink(path: Path, target: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        path.unlink()
    elif path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)
    relative_target = os.path.relpath(target, start=path.parent)
    path.symlink_to(relative_target, target_is_directory=True)


def _move_or_copy_directory(source: Path, target: Path) -> str:
    try:
        source.rename(target)
        return "moved_source"
    except OSError:
        shutil.copytree(source, target, symlinks=True)
        shutil.rmtree(source)
        return "copied_source"


def _directory_fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    for current in sorted(path.rglob("*")):
        relative = str(current.relative_to(path))
        digest.update(relative.encode("utf-8", errors="ignore"))
        if current.is_symlink():
            digest.update(b"symlink:")
            try:
                digest.update(os.readlink(current).encode("utf-8", errors="ignore"))
            except OSError:
                continue
            continue
        if current.is_file():
            digest.update(b"file:")
            try:
                digest.update(current.read_bytes())
            except OSError:
                continue
    return digest.hexdigest()


def normalize_cli_plugin_host_skill_layout() -> dict[str, Any]:
    shared_root = _shared_host_skill_root()
    host_dirs = _managed_host_skill_directories()
    host_dir_preexisting = {
        path: bool(path.exists() or path.is_symlink())
        for path in host_dirs
    }
    actions: list[dict[str, str]] = []

    if shared_root.is_symlink():
        shared_root.unlink()
    if not shared_root.exists():
        source_dir: Path | None = None
        for candidate in host_dirs:
            if candidate.is_symlink() or not candidate.is_dir():
                continue
            if _iter_directory_entries(candidate):
                source_dir = candidate
                break
        shared_root.parent.mkdir(parents=True, exist_ok=True)
        if source_dir is not None:
            move_action = _move_or_copy_directory(source_dir, shared_root)
            actions.append(
                {
                    "action": move_action,
                    "source": str(source_dir.relative_to(get_project_root())),
                    "target": str(shared_root.relative_to(get_project_root())),
                }
            )
        else:
            shared_root.mkdir(parents=True, exist_ok=True)
            actions.append(
                {
                    "action": "created_shared_root",
                    "target": str(shared_root.relative_to(get_project_root())),
                }
            )

    shared_root.parent.mkdir(parents=True, exist_ok=True)
    shared_root.mkdir(parents=True, exist_ok=True)
    shared_root_resolved = shared_root.resolve()

    for host_dir in host_dirs:
        host_label = str(host_dir.relative_to(get_project_root()))
        if host_dir.is_symlink():
            try:
                current_target = host_dir.resolve()
            except OSError:
                current_target = None
            if current_target == shared_root_resolved:
                actions.append({"action": "already_linked", "path": host_label})
                continue
            _replace_with_directory_symlink(host_dir, shared_root)
            actions.append(
                {
                    "action": "relinked_symlink",
                    "path": host_label,
                    "target": str(shared_root.relative_to(get_project_root())),
                }
            )
            continue
        if host_dir.is_dir():
            entries = _iter_directory_entries(host_dir)
            if not entries:
                host_dir.rmdir()
                _replace_with_directory_symlink(host_dir, shared_root)
                actions.append(
                    {
                        "action": "linked_empty_dir",
                        "path": host_label,
                        "target": str(shared_root.relative_to(get_project_root())),
                    }
                )
                continue
            if _is_alias_tree(host_dir):
                shutil.rmtree(host_dir)
                _replace_with_directory_symlink(host_dir, shared_root)
                actions.append(
                    {
                        "action": "collapsed_alias_tree",
                        "path": host_label,
                        "target": str(shared_root.relative_to(get_project_root())),
                    }
                )
                continue
            if host_dir.resolve() == shared_root_resolved:
                actions.append({"action": "already_linked", "path": host_label})
                continue
            if _directory_fingerprint(host_dir) == _directory_fingerprint(shared_root):
                shutil.rmtree(host_dir)
                _replace_with_directory_symlink(host_dir, shared_root)
                actions.append(
                    {
                        "action": "collapsed_duplicate_dir",
                        "path": host_label,
                        "target": str(shared_root.relative_to(get_project_root())),
                    }
                )
                continue
            actions.append(
                {
                    "action": "skipped_nonempty_dir",
                    "path": host_label,
                }
            )
            continue
        if host_dir.exists():
            actions.append(
                {
                    "action": "skipped_non_directory",
                    "path": host_label,
                }
            )
            continue
        if host_dir_preexisting.get(host_dir):
            _replace_with_directory_symlink(host_dir, shared_root)
            actions.append(
                {
                    "action": "linked_missing_dir",
                    "path": host_label,
                    "target": str(shared_root.relative_to(get_project_root())),
                }
            )

    return {
        "shared_root": str(shared_root),
        "host_dirs": [str(path) for path in host_dirs],
        "actions": actions,
    }


def _load_plugin_install_state() -> dict[str, Any]:
    path = _plugin_status_store_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    installs = data.get("installs")
    return installs if isinstance(installs, dict) else {}


def _save_plugin_install_state(installs: dict[str, Any]) -> None:
    path = _plugin_status_store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": _utc_now_iso(),
        "installs": installs,
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _record_successful_install(
    plugin_id: str,
    *,
    installed_version: str = "",
    latest_version: str = "",
    detection_source: str = "",
    toolchain_snapshot: dict[str, Any] | None = None,
) -> None:
    installs = _load_plugin_install_state()
    installs[str(plugin_id).strip()] = {
        "installed": True,
        "installed_version": str(installed_version or "").strip(),
        "latest_version": str(latest_version or "").strip(),
        "last_installed_at": _utc_now_iso(),
        "detection_source": str(detection_source or "").strip() or "install-command",
        "toolchain": (
            dict(toolchain_snapshot)
            if isinstance(toolchain_snapshot, dict)
            else {}
        ),
    }
    _save_plugin_install_state(installs)


def _read_install_receipt(plugin_id: str) -> dict[str, Any]:
    receipt = _load_plugin_install_state().get(str(plugin_id).strip(), {})
    return receipt if isinstance(receipt, dict) else {}


def _resolve_executable_path(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    candidate = Path(text).expanduser()
    try:
        resolved = candidate.resolve()
    except OSError:
        return ""
    if not resolved.exists() or not resolved.is_file() or not os.access(resolved, os.X_OK):
        return ""
    return str(resolved)


def _unique_path_entries(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in values:
        value = str(item or "").strip()
        if not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _join_path_entries(entries: list[str], base_path: str = "") -> str:
    values = _unique_path_entries(entries + [str(base_path or "").strip()])
    return os.pathsep.join(item for item in values if item)


def _collect_receipt_runtime_path_entries(receipt: dict[str, Any] | None) -> list[str]:
    source = receipt if isinstance(receipt, dict) else {}
    toolchain = source.get("toolchain") if isinstance(source.get("toolchain"), dict) else {}
    entries: list[str] = []
    for key in ("node_path", "npm_path", "npx_path", "plugin_binary_path"):
        resolved = _resolve_executable_path(toolchain.get(key))
        if resolved:
            entries.append(str(Path(resolved).parent))
    for key in ("npm_global_bin",):
        candidate = str(toolchain.get(key) or "").strip()
        if candidate and Path(candidate).expanduser().is_dir():
            entries.append(str(Path(candidate).expanduser().resolve()))
    prefix = str(toolchain.get("npm_global_prefix") or "").strip()
    if prefix:
        prefix_bin = Path(prefix).expanduser() / "bin"
        if prefix_bin.is_dir():
            entries.append(str(prefix_bin.resolve()))
    return _unique_path_entries(entries)


def _build_runtime_env_from_receipt(
    receipt: dict[str, Any] | None,
    *,
    base_env: dict[str, str] | None = None,
) -> dict[str, str]:
    env = dict(base_env or os.environ)
    env["PATH"] = _join_path_entries(
        _collect_receipt_runtime_path_entries(receipt),
        str(env.get("PATH") or ""),
    )
    return env


def _run_command(
    command: list[str],
    *,
    timeout_sec: int = 12,
    env: dict[str, str] | None = None,
) -> tuple[bool, str, str]:
    try:
        completed = subprocess.run(
            command,
            cwd=str(get_project_root()),
            capture_output=True,
            text=True,
            timeout=max(3, timeout_sec),
            env=env,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return False, "", str(exc)
    stdout = str(completed.stdout or "").strip()
    stderr = str(completed.stderr or "").strip()
    return completed.returncode == 0, stdout, stderr


def _resolve_runtime_command_path(command_name: str, receipt: dict[str, Any] | None = None) -> str:
    normalized_command_name = str(command_name or "").strip()
    if not normalized_command_name:
        return ""
    for candidate in (
        _resolve_executable_path(
            (
                receipt.get("toolchain")
                if isinstance(receipt, dict) and isinstance(receipt.get("toolchain"), dict)
                else {}
            ).get(f"{normalized_command_name}_path")
        ),
        _resolve_executable_path(
            (
                receipt.get("toolchain")
                if isinstance(receipt, dict) and isinstance(receipt.get("toolchain"), dict)
                else {}
            ).get("plugin_binary_path")
            if normalized_command_name == "lark-cli"
            else ""
        ),
        _resolve_executable_path(which(normalized_command_name) or ""),
    ):
        if candidate:
            return candidate
    return ""


def _collect_runtime_toolchain_snapshot(
    plugin: dict[str, Any],
    *,
    receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    binary_name = str(plugin.get("binary_name") or "").strip()
    runtime_receipt = receipt if isinstance(receipt, dict) else {}
    runtime_env = _build_runtime_env_from_receipt(runtime_receipt)
    node_path = _resolve_runtime_command_path("node", runtime_receipt)
    npm_path = _resolve_runtime_command_path("npm", runtime_receipt)
    npx_path = _resolve_runtime_command_path("npx", runtime_receipt)
    plugin_binary_path = _resolve_executable_path(
        (
            runtime_receipt.get("toolchain")
            if isinstance(runtime_receipt.get("toolchain"), dict)
            else {}
        ).get("plugin_binary_path")
    )
    if not plugin_binary_path and binary_name:
        plugin_binary_path = _resolve_executable_path(which(binary_name) or "")

    npm_global_prefix = ""
    npm_global_bin = ""
    if npm_path:
        ok, stdout, _stderr = _run_command([npm_path, "prefix", "-g"], timeout_sec=10, env=runtime_env)
        if ok:
            npm_global_prefix = str(stdout or "").strip()
        if npm_global_prefix:
            prefix_bin = Path(npm_global_prefix).expanduser() / "bin"
            if prefix_bin.is_dir():
                npm_global_bin = str(prefix_bin.resolve())

    path_entries = _unique_path_entries(
        _collect_receipt_runtime_path_entries(runtime_receipt)
        + [str(Path(value).parent) for value in (node_path, npm_path, npx_path, plugin_binary_path) if value]
        + [npm_global_bin]
    )
    return {
        "captured_at": _utc_now_iso(),
        "captured_by_user": getpass.getuser(),
        "node_path": node_path,
        "npm_path": npm_path,
        "npx_path": npx_path,
        "plugin_binary_path": plugin_binary_path,
        "plugin_binary_name": binary_name,
        "npm_global_prefix": npm_global_prefix,
        "npm_global_bin": npm_global_bin,
        "runtime_path_entries": path_entries,
        "path_snapshot": str(runtime_env.get("PATH") or ""),
    }


def build_cli_plugin_runtime_environment(
    *,
    plugin_id: str = "",
    base_env: dict[str, str] | None = None,
) -> tuple[dict[str, str], dict[str, Any]]:
    env = dict(base_env or os.environ)
    installs = _load_plugin_install_state()
    normalized_plugin_id = str(plugin_id or "").strip()
    if normalized_plugin_id:
        selected_plugins = []
        plugin = get_cli_plugin(normalized_plugin_id, include_status=False)
        if plugin is not None:
            selected_plugins.append(plugin)
    else:
        selected_plugins = list_cli_plugins(include_status=False)
    path_entries: list[str] = []
    runtime_plugins: list[dict[str, Any]] = []
    for plugin in selected_plugins:
        current_plugin_id = str(plugin.get("id") or "").strip()
        if not current_plugin_id:
            continue
        receipt = installs.get(current_plugin_id)
        if not isinstance(receipt, dict):
            receipt = {}
        receipt_entries = _collect_receipt_runtime_path_entries(receipt)
        toolchain = (
            receipt.get("toolchain")
            if isinstance(receipt.get("toolchain"), dict)
            else {}
        )
        if not receipt_entries:
            toolchain_snapshot = _collect_runtime_toolchain_snapshot(
                plugin,
                receipt=receipt,
            )
            receipt_entries = _unique_path_entries(
                list(toolchain_snapshot.get("runtime_path_entries") or []),
            )
            if receipt_entries:
                installed_version, detection_source = _detect_installed_version(
                    plugin,
                )
                if installed_version or detection_source:
                    _record_successful_install(
                        current_plugin_id,
                        installed_version=installed_version,
                        latest_version=_extract_version(
                            receipt.get("latest_version"),
                        ),
                        detection_source=detection_source or "runtime-detect",
                        toolchain_snapshot=toolchain_snapshot,
                    )
                    receipt = _read_install_receipt(current_plugin_id)
                    toolchain = (
                        receipt.get("toolchain")
                        if isinstance(receipt.get("toolchain"), dict)
                        else {}
                    )
                    receipt_entries = _collect_receipt_runtime_path_entries(
                        receipt,
                    )
                else:
                    toolchain = dict(toolchain_snapshot)
        if not receipt_entries:
            continue
        path_entries.extend(receipt_entries)
        runtime_plugins.append(
            {
                "plugin_id": str(current_plugin_id or "").strip(),
                "binary_path": _resolve_executable_path(toolchain.get("plugin_binary_path")),
                "npm_global_bin": str(toolchain.get("npm_global_bin") or "").strip(),
                "detection_source": str(receipt.get("detection_source") or "").strip(),
            }
        )
    unique_entries = _unique_path_entries(path_entries)
    if unique_entries:
        env["PATH"] = _join_path_entries(unique_entries, str(env.get("PATH") or ""))
    metadata = {
        "plugin_runtime_enabled": bool(unique_entries),
        "plugin_runtime_path_entries": unique_entries,
        "plugin_runtime_plugins": runtime_plugins,
    }
    return env, metadata


def _extract_version(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    match = re.search(r"\bv?(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)\b", text)
    return str(match.group(1) or "").strip() if match else ""


def _parse_version(value: str) -> tuple[int, int, int, str] | None:
    text = str(value or "").strip()
    match = re.match(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-+]([0-9A-Za-z.-]+))?$", text)
    if not match:
        return None
    return (
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3)),
        str(match.group(4) or ""),
    )


def _compare_versions(left: str, right: str) -> int | None:
    left_version = _parse_version(left)
    right_version = _parse_version(right)
    if left_version is None or right_version is None:
        return None
    if left_version[:3] != right_version[:3]:
        return -1 if left_version[:3] < right_version[:3] else 1
    left_suffix = left_version[3]
    right_suffix = right_version[3]
    if left_suffix == right_suffix:
        return 0
    if not left_suffix:
        return 1
    if not right_suffix:
        return -1
    return -1 if left_suffix < right_suffix else 1


def _detect_installed_version(plugin: dict[str, Any]) -> tuple[str, str]:
    receipt = _read_install_receipt(str(plugin.get("id") or "").strip())
    runtime_env = _build_runtime_env_from_receipt(receipt)
    binary_name = str(plugin.get("binary_name") or "").strip()
    binary_path = _resolve_executable_path(
        (
            receipt.get("toolchain")
            if isinstance(receipt.get("toolchain"), dict)
            else {}
        ).get("plugin_binary_path")
    )
    if not binary_path and binary_name:
        binary_path = _resolve_executable_path(which(binary_name) or "")
    if binary_path:
        ok, stdout, stderr = _run_command([binary_path, "--version"], timeout_sec=8, env=runtime_env)
        version = _extract_version(stdout or stderr)
        if ok and version:
            return version, "binary"

    package_name = str(plugin.get("package_name") or "").strip()
    npm_path = _resolve_runtime_command_path("npm", receipt)
    if package_name and npm_path:
        ok, stdout, _stderr = _run_command(
            [npm_path, "list", "-g", package_name, "--depth=0", "--json"],
            timeout_sec=10,
            env=runtime_env,
        )
        if ok:
            try:
                payload = json.loads(stdout or "{}")
            except json.JSONDecodeError:
                payload = {}
            dependencies = payload.get("dependencies")
            if isinstance(dependencies, dict):
                dependency = dependencies.get(package_name)
                if isinstance(dependency, dict):
                    version = _extract_version(dependency.get("version"))
                    if version:
                        return version, "npm-global"
    return "", ""


def _detect_latest_version(plugin: dict[str, Any]) -> tuple[str, str]:
    package_name = str(plugin.get("package_name") or "").strip()
    if not package_name:
        return "", "missing-package-name"
    receipt = _read_install_receipt(str(plugin.get("id") or "").strip())
    npm_path = _resolve_runtime_command_path("npm", receipt)
    if not npm_path:
        return "", "npm-not-found"
    ok, stdout, stderr = _run_command(
        [npm_path, "view", package_name, "version"],
        timeout_sec=12,
        env=_build_runtime_env_from_receipt(receipt),
    )
    version = _extract_version(stdout)
    if ok and version:
        return version, ""
    return "", stderr or "latest-version-unavailable"


def _resolve_plugin_status(plugin: dict[str, Any], *, refresh: bool = False) -> dict[str, Any]:
    plugin_id = str(plugin.get("id") or "").strip()
    if not plugin_id:
        return {
            "status": "unknown",
            "status_label": "状态未知",
            "status_reason": "缺少插件标识",
            "installed": False,
            "installed_version": "",
            "latest_version": "",
            "update_available": False,
            "last_installed_at": "",
            "last_checked_at": _utc_now_iso(),
        }

    if not refresh:
        cached = _CLI_PLUGIN_STATUS_CACHE.get(plugin_id)
        if cached and (time.time() - cached[0]) < _STATUS_CACHE_TTL_SEC:
            return dict(cached[1])

    receipt = _read_install_receipt(plugin_id)
    toolchain_snapshot = _collect_runtime_toolchain_snapshot(plugin, receipt=receipt)
    installed_version, detected_source = _detect_installed_version(plugin)
    receipt_version = _extract_version(receipt.get("installed_version"))
    effective_installed_version = installed_version or receipt_version
    installed = bool(
        effective_installed_version
        or detected_source
        or receipt.get("installed") is True
    )

    latest_version, latest_error = _detect_latest_version(plugin)
    if not latest_version:
        latest_version = _extract_version(receipt.get("latest_version"))
    update_available = False
    status = "not_installed"
    status_label = "未安装"
    status_reason = "未检测到本地安装记录"

    comparable_installed_version = effective_installed_version
    if installed:
        status = "installed"
        status_label = "已安装"
        if effective_installed_version:
            status_reason = f"当前本地版本 {effective_installed_version}"
        else:
            status_reason = "根据本地安装记录判定已安装"
        if latest_version and comparable_installed_version:
            comparison = _compare_versions(comparable_installed_version, latest_version)
            if comparison is not None and comparison < 0:
                update_available = True
                status = "update_available"
                status_label = "可更新"
                status_reason = f"当前 {comparable_installed_version}，最新 {latest_version}"
            elif comparison == 0:
                status_reason = f"当前已是最新版本 {latest_version}"
        elif latest_error:
            status_reason = f"{status_reason}，但最新版本检测失败"
    elif latest_error:
        status_reason = "未安装，且最新版本检测失败"

    payload = {
        "status": status,
        "status_label": status_label,
        "status_reason": status_reason,
        "installed": installed,
        "installed_version": comparable_installed_version,
        "latest_version": latest_version,
        "update_available": update_available,
        "latest_check_error": latest_error,
        "last_installed_at": str(receipt.get("last_installed_at") or "").strip(),
        "last_checked_at": _utc_now_iso(),
        "detection_source": detected_source or str(receipt.get("detection_source") or "").strip(),
        "toolchain": toolchain_snapshot,
        "preferred_binary_path": str(toolchain_snapshot.get("plugin_binary_path") or "").strip(),
        "preferred_command": (
            str(toolchain_snapshot.get("plugin_binary_path") or "").strip()
            or str(plugin.get("binary_name") or "").strip()
            or str(plugin.get("install_command") or "").strip()
        ),
        "environment_summary": _build_plugin_environment_summary(plugin_id, toolchain_snapshot),
    }
    _CLI_PLUGIN_STATUS_CACHE[plugin_id] = (time.time(), dict(payload))
    return payload


def _build_plugin_environment_summary(plugin_id: str, toolchain_snapshot: dict[str, Any] | None) -> str:
    snapshot = toolchain_snapshot if isinstance(toolchain_snapshot, dict) else {}
    binary_path = str(snapshot.get("plugin_binary_path") or "").strip()
    node_path = str(snapshot.get("node_path") or "").strip()
    npm_path = str(snapshot.get("npm_path") or "").strip()
    npm_global_bin = str(snapshot.get("npm_global_bin") or "").strip()
    details = [f"插件 {plugin_id}"]
    if binary_path:
        details.append(f"binary={binary_path}")
    if node_path:
        details.append(f"node={node_path}")
    if npm_path:
        details.append(f"npm={npm_path}")
    if npm_global_bin:
        details.append(f"npm_global_bin={npm_global_bin}")
    return "安装环境: " + " | ".join(details)


def _serialize_cli_plugin(raw_item: dict[str, Any], *, include_status: bool = True) -> dict[str, Any]:
    item = {
        "id": str(raw_item.get("id") or "").strip(),
        "name": str(raw_item.get("name") or "").strip(),
        "description": str(raw_item.get("description") or "").strip(),
        "vendor": str(raw_item.get("vendor") or "").strip(),
        "category": str(raw_item.get("category") or "").strip(),
        "package_name": str(raw_item.get("package_name") or "").strip(),
        "binary_name": str(raw_item.get("binary_name") or "").strip(),
        "install_command": str(raw_item.get("install_command") or "").strip(),
        "docs_url": str(raw_item.get("docs_url") or "").strip(),
        "ai_install_prompt": str(raw_item.get("ai_install_prompt") or "").strip(),
        "requires_restart": bool(raw_item.get("requires_restart", False)),
        "tags": _normalize_plugin_tags(raw_item.get("tags")),
    }
    if include_status:
        item["install_status"] = _resolve_plugin_status(item)
    return item


def list_cli_plugins(*, include_status: bool = True) -> list[dict[str, Any]]:
    return [
        _serialize_cli_plugin(raw_item, include_status=include_status)
        for raw_item in _CLI_PLUGIN_REGISTRY
    ]


def get_cli_plugin(plugin_id: str, *, include_status: bool = True) -> dict[str, Any] | None:
    normalized_plugin_id = str(plugin_id or "").strip().lower()
    if not normalized_plugin_id:
        return None
    for item in list_cli_plugins(include_status=include_status):
        if str(item.get("id") or "").strip().lower() == normalized_plugin_id:
            return item
    return None


def _install_script_path() -> Path:
    return Path(__file__).resolve().parents[1] / "scripts" / "install_cli_plugin.sh"


def install_cli_plugin(plugin_id: str, *, timeout_sec: int = 180) -> dict[str, Any]:
    plugin = get_cli_plugin(plugin_id, include_status=False)
    if plugin is None:
        raise ValueError(f"Unsupported CLI plugin: {plugin_id}")
    safe_timeout = max(30, min(int(timeout_sec or 180), 900))
    script_path = _install_script_path()
    if not script_path.is_file():
        raise RuntimeError(f"CLI plugin installer script is missing: {script_path}")
    preinstall_snapshot = _collect_runtime_toolchain_snapshot(plugin)
    install_env = dict(os.environ)
    install_env["PATH"] = _join_path_entries(
        list(preinstall_snapshot.get("runtime_path_entries") or []),
        str(install_env.get("PATH") or ""),
    )
    install_env["CLI_PLUGIN_RUNTIME_PATH"] = str(install_env.get("PATH") or "")
    if str(preinstall_snapshot.get("node_path") or "").strip():
        install_env["CLI_PLUGIN_NODE_PATH"] = str(preinstall_snapshot["node_path"])
    if str(preinstall_snapshot.get("npx_path") or "").strip():
        install_env["CLI_PLUGIN_NPX_PATH"] = str(preinstall_snapshot["npx_path"])

    try:
        completed = subprocess.run(
            ["/bin/bash", str(script_path), str(plugin["id"])],
            cwd=str(get_project_root()),
            capture_output=True,
            text=True,
            timeout=safe_timeout,
            env=install_env,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(
            f"CLI plugin install timed out after {safe_timeout} seconds"
        ) from exc
    stdout = str(completed.stdout or "").strip()
    stderr = str(completed.stderr or "").strip()
    latest_version = ""
    install_status = _resolve_plugin_status(plugin, refresh=True)
    if completed.returncode == 0:
        latest_version, _ = _detect_latest_version(plugin)
        toolchain_snapshot = _collect_runtime_toolchain_snapshot(plugin)
        installed_version, detection_source = _detect_installed_version(plugin)
        host_skill_layout = normalize_cli_plugin_host_skill_layout()
        _record_successful_install(
            str(plugin.get("id") or "").strip(),
            installed_version=installed_version or latest_version,
            latest_version=latest_version,
            detection_source=detection_source or "install-command",
            toolchain_snapshot=toolchain_snapshot,
        )
        install_status = _resolve_plugin_status(plugin, refresh=True)
        install_status["host_skill_layout"] = host_skill_layout
    return {
        "plugin": plugin,
        "command": str(plugin.get("install_command") or "").strip(),
        "exit_code": int(completed.returncode),
        "ok": completed.returncode == 0,
        "stdout": stdout,
        "stderr": stderr,
        "install_status": install_status,
        "environment_summary": str(install_status.get("environment_summary") or "").strip(),
        "preferred_command": str(install_status.get("preferred_command") or "").strip(),
    }
