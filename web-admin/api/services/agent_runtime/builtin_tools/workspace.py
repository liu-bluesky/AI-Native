"""Workspace 路径安全检查。

所有文件/命令工具的 path/cwd/dest_path 参数都必须经过 resolve_workspace_path，
确保不会逃逸到 workspace 之外。路径穿越（../）直接拒绝。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class WorkspacePathError(ValueError):
    """路径逃逸 workspace 或路径非法。"""

    def __init__(self, path: str, reason: str = "out of workspace scope") -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"workspace.out_of_scope: {path} ({reason})")


def resolve_workspace_path(
    workspace_path: str,
    relative_path: str = ".",
    *,
    must_exist: bool = False,
    allow_create: bool = False,
) -> Path:
    """把相对路径解析为 workspace 内的绝对路径，拒绝逃逸。

    参数:
        workspace_path: workspace 根目录的绝对路径。
        relative_path: 相对于 workspace 的路径，默认 "."。
        must_exist: 路径必须已存在。
        allow_create: 允许路径不存在（用于 write_file 等创建场景）。
    """
    workspace = Path(str(workspace_path or "").strip()).resolve()
    if not workspace or not workspace.is_dir():
        raise WorkspacePathError(str(workspace_path), "workspace root is not a directory")

    raw = str(relative_path or "").strip()
    if not raw:
        raw = "."

    # 拒绝绝对路径
    if Path(raw).is_absolute():
        raise WorkspacePathError(raw, "absolute paths are not allowed")

    resolved = (workspace / raw).resolve()

    # 检查是否在 workspace 内
    try:
        resolved.relative_to(workspace)
    except ValueError:
        raise WorkspacePathError(raw, "path escapes workspace") from None

    if must_exist and not resolved.exists():
        raise WorkspacePathError(raw, "path does not exist")

    if not allow_create and not resolved.exists():
        # 对于 list_files 等只读操作，路径必须存在
        # write_file 场景传 allow_create=True
        raise WorkspacePathError(raw, "path does not exist")

    return resolved


def safe_relative_path(workspace_path: str, absolute_path: str) -> str:
    """把绝对路径转回 workspace 内的相对路径字符串。"""
    workspace = Path(str(workspace_path or "").strip()).resolve()
    target = Path(str(absolute_path or "").strip()).resolve()
    try:
        return str(target.relative_to(workspace))
    except ValueError:
        return str(target)


def _str_arg(args: dict[str, Any], key: str, default: str = "") -> str:
    return str(args.get(key) or default).strip()


def _int_arg(args: dict[str, Any], key: str, default: int, minimum: int = 0, maximum: int = 0) -> int:
    raw = args.get(key)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    if value < minimum:
        return minimum
    if maximum > 0 and value > maximum:
        return maximum
    return value


def _bool_arg(args: dict[str, Any], key: str, default: bool = False) -> bool:
    raw = args.get(key)
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"true", "1", "yes", "on"}
