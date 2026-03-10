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
    script_path = Path(spec["script_path"]).resolve()
    if not script_path.exists():
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
    if spec["script_type"] == "py":
        cmd = [sys.executable, str(script_path)]
    elif spec["script_type"] == "js":
        cmd = ["node", str(script_path)]
    else:
        return {"error": f"Unsupported script type: {spec['script_type']}"}

    cmd.extend(build_cli_args(payload))
    if employee_id:
        cmd.extend(["--employee-id", employee_id])
    if current_api_key:
        cmd.extend(["--api-key", current_api_key])
    try:
        result = subprocess.run(
            cmd,
            cwd=str(project_root),
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
    }
