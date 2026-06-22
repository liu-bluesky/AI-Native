"""命令工具实现：check_command_risk / run_command。

风险分类按 docs/liuAgent-cli/design/08-tool-contracts.md 定义：
- safe: pwd、ls、rg、只读 git 查询
- medium: 写 workspace 文件的格式化、测试生成缓存
- high: 安装依赖、启动长服务、网络写入
- critical: 部署、删除、系统目录写入、凭据操作
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import Any

from services.agent_runtime.builtin_tools.workspace import (
    WorkspacePathError,
    _int_arg,
    _str_arg,
    resolve_workspace_path,
)

# 风险关键词映射
_SAFE_COMMAND_PREFIXES = (
    "pwd", "ls", "cat", "head", "tail", "wc", "rg ", "grep ", "find ",
    "git status", "git log", "git diff", "git show", "git branch",
    "echo ", "which ", "file ", "stat ",
)

_MEDIUM_COMMAND_PATTERNS = (
    "npm run", "yarn run", "pnpm run", "python -m pytest", "pytest",
    "go test", "cargo test", "make test", "ruff ", "black ", "prettier",
    "eslint", "tsc ", "mypy ",
)

_HIGH_COMMAND_PATTERNS = (
    "npm install", "yarn install", "pnpm install", "pip install",
    "npm ci", "yarn add", "pnpm add", "pip install",
    "docker ", "curl ", "wget ", "ssh ", "scp ",
    "npm publish", "yarn publish", "pip upload",
    "go build", "cargo build", "make build",
)

_CRITICAL_COMMAND_PATTERNS = (
    "rm -rf", "rm -r", "sudo ", "chmod ", "chown ",
    "git push", "git reset --hard", "git clean -fd",
    "docker stop", "docker rm", "docker rmi",
    "kill -9", "kill -15", "pkill ",
    "shutdown", "reboot", "halt",
    " dd ", "mkfs", "fdisk",
    "deploy", "publish --prod", "release",
)

# 凭据相关关键词
_CREDENTIAL_TERMS = (
    "password", "passwd", "secret", "token", "api_key", "apikey",
    "private_key", "ssh_key", "credential", "auth_token",
)


def classify_command_risk(cmd: str) -> tuple[str, list[str]]:
    """对命令做风险分类，返回 (risk_level, reasons)。"""
    normalized = f" {cmd.strip().lower()} "
    reasons: list[str] = []
    risk = "low"

    # critical 检查
    for pattern in _CRITICAL_COMMAND_PATTERNS:
        if pattern in normalized:
            risk = "critical"
            reasons.append(f"matches critical pattern: {pattern.strip()}")

    # 凭据检查
    for term in _CREDENTIAL_TERMS:
        if term in normalized:
            risk = "critical"
            reasons.append(f"contains credential term: {term}")
            break

    # high 检查
    if risk != "critical":
        for pattern in _HIGH_COMMAND_PATTERNS:
            if pattern in normalized:
                risk = "high"
                reasons.append(f"matches high-risk pattern: {pattern.strip()}")
                break

    # medium 检查
    if risk == "low":
        for pattern in _MEDIUM_COMMAND_PATTERNS:
            if pattern in normalized:
                risk = "medium"
                reasons.append(f"matches medium-risk pattern: {pattern.strip()}")
                break

    # safe 检查
    if risk == "low":
        for prefix in _SAFE_COMMAND_PREFIXES:
            if normalized.strip().startswith(prefix.strip()):
                reasons.append(f"safe read-only command: {prefix.strip()}")
                break
        else:
            # 不是已知 safe 命令，默认 medium
            risk = "medium"
            reasons.append("unknown command, defaulting to medium")

    return risk, reasons


async def check_command_risk(workspace_path: str, args: dict[str, Any]) -> dict[str, Any]:
    """检查命令的风险等级（不执行命令）。"""
    cmd = _str_arg(args, "cmd")
    cwd = _str_arg(args, "cwd", ".")

    if not cmd:
        return {"ok": False, "error": "cmd is required", "error_code": "tool.schema_invalid"}

    try:
        resolve_workspace_path(workspace_path, cwd, must_exist=True)
    except WorkspacePathError as exc:
        return {"ok": False, "error": str(exc), "error_code": "workspace.out_of_scope"}

    risk, reasons = classify_command_risk(cmd)
    requires_approval = risk in {"medium", "high", "critical"}

    return {
        "ok": True,
        "risk": risk,
        "reasons": reasons,
        "requires_approval": requires_approval,
        "suggested_preview": {
            "cmd": cmd,
            "cwd": cwd,
            "risk_level": risk,
        },
        "summary": f"命令风险等级: {risk}" + (f"（{'; '.join(reasons)}）" if reasons else ""),
    }


async def run_command(workspace_path: str, args: dict[str, Any]) -> dict[str, Any]:
    """在 workspace 内执行命令。"""
    cmd = _str_arg(args, "cmd")
    cwd = _str_arg(args, "cwd", ".")
    timeout_ms = _int_arg(args, "timeout_ms", 30000, minimum=1000, maximum=300000)
    max_output_chars = _int_arg(args, "max_output_chars", 20000, minimum=1000, maximum=100000)

    if not cmd:
        return {"ok": False, "error": "cmd is required", "error_code": "tool.schema_invalid"}

    try:
        work_dir = resolve_workspace_path(workspace_path, cwd, must_exist=True)
    except WorkspacePathError as exc:
        return {"ok": False, "error": str(exc), "error_code": "workspace.out_of_scope"}

    import time
    start = time.monotonic()

    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(work_dir),
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout_ms / 1000.0,
        )
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except (ProcessLookupError, OSError):
            pass
        return {
            "ok": False,
            "error": f"command timeout after {timeout_ms}ms",
            "error_code": "command.timeout",
            "exit_code": -1,
            "duration_ms": int((time.monotonic() - start) * 1000),
        }
    except OSError as exc:
        return {
            "ok": False,
            "error": f"command failed: {exc}",
            "error_code": "command.failed",
            "exit_code": -1,
            "duration_ms": int((time.monotonic() - start) * 1000),
        }

    stdout = stdout_bytes.decode("utf-8", errors="replace")
    stderr = stderr_bytes.decode("utf-8", errors="replace")
    stdout, stdout_truncated = _truncate_output(stdout, max_output_chars)
    stderr, stderr_truncated = _truncate_output(stderr, max_output_chars)
    duration_ms = int((time.monotonic() - start) * 1000)
    exit_code = proc.returncode if proc.returncode is not None else -1
    ok = exit_code == 0

    summary = f"命令退出码 {exit_code}，耗时 {duration_ms}ms"
    if stdout_truncated or stderr_truncated:
        summary += "（输出已截断）"

    return {
        "ok": ok,
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "duration_ms": duration_ms,
        "truncated": stdout_truncated or stderr_truncated,
        "summary": summary,
        "error": "" if ok else (stderr.strip()[:200] or f"exit code {exit_code}"),
        "error_code": "" if ok else "command.failed",
    }


def _truncate_output(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars] + "\n... [truncated]", True
