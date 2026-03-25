"""Skill proxy execution helpers for dynamic MCP runtime."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def build_cli_args(payload: dict) -> list[str]:
    argv: list[str] = []
    for key, value in payload.items():
        name = str(key or "").strip()
        if not name:
            continue
        flag = f"--{name.replace('_', '-')}"
        if isinstance(value, bool):
            if value:
                argv.append(flag)
            continue
        if value is None:
            continue
        if isinstance(value, list):
            for item in value:
                argv.extend((flag, str(item)))
            continue
        argv.extend((flag, str(value)))
    return argv


def _build_command(spec: dict, *, script_path: Path | None) -> list[str] | None:
    runtime = str(spec.get("runtime") or spec.get("script_type") or "").strip().lower()
    explicit_command = [str(item).strip() for item in spec.get("command", []) if str(item).strip()]
    if explicit_command:
        return [*explicit_command, *([str(script_path)] if script_path is not None else [])]
    if runtime in {"python", "py"}:
        if script_path is None:
            return None
        return [sys.executable, str(script_path)]
    if runtime in {"node", "js"}:
        if script_path is None:
            return None
        return ["node", str(script_path)]
    if runtime == "command" and script_path is not None:
        return [str(script_path)]
    return None


def _append_context_flag(cmd: list[str], flag_name: str, value: str) -> None:
    flag = str(flag_name or "").strip()
    if flag and value:
        cmd.extend([flag, value])


def execute_skill_proxy(
    spec: dict,
    *,
    project_root: Path,
    current_api_key: str = "",
    args: dict | None = None,
    args_json: str | None = None,
    timeout_sec: int = 30,
    employee_id: str | None = None,
) -> dict:
    script_path_text = str(spec.get("script_path") or "").strip()
    script_path = Path(script_path_text).resolve() if script_path_text else None
    if script_path is not None and not script_path.exists():
        return {"error": f"Script not found: {script_path}"}

    if args is not None:
        if not isinstance(args, dict):
            return {"error": "args must be an object"}
        payload = args
    else:
        try:
            payload = json.loads(args_json or "{}")
        except Exception as exc:
            return {"error": f"Invalid args_json: {exc}"}
        if not isinstance(payload, dict):
            return {"error": "args_json must be a JSON object"}

    try:
        timeout = int(timeout_sec)
    except (TypeError, ValueError):
        timeout = 30
    timeout = max(1, min(timeout, 600))
    cmd = _build_command(spec, script_path=script_path)
    if cmd is None:
        runtime = str(spec.get("runtime") or spec.get("script_type") or "").strip() or "unknown"
        return {"error": f"Unsupported proxy runtime: {runtime}"}

    cmd.extend(build_cli_args(payload))
    _append_context_flag(cmd, str(spec.get("employee_id_flag", "--employee-id") or ""), str(employee_id or ""))
    _append_context_flag(cmd, str(spec.get("api_key_flag", "--api-key") or ""), current_api_key)
    cwd_value = str(spec.get("cwd") or "").strip()
    cwd = str(Path(cwd_value).resolve()) if cwd_value else str(project_root)
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        return {"error": str(exc), "command": cmd}
    except subprocess.TimeoutExpired:
        return {
            "error": "Skill execution timed out",
            "timeout_sec": timeout,
            "command": cmd,
        }

    return {
        "status": "ok" if result.returncode == 0 else "error",
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "command": cmd,
        "cwd": cwd,
    }
