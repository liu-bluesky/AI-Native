"""文件工具实现：list_files / read_file / search_text / apply_patch / write_file。

所有路径参数都经过 resolve_workspace_path 检查，拒绝逃逸 workspace。
"""

from __future__ import annotations

import fnmatch
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from services.agent_runtime.builtin_tools.workspace import (
    WorkspacePathError,
    _bool_arg,
    _int_arg,
    _str_arg,
    resolve_workspace_path,
    safe_relative_path,
)


def _truncate(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True


async def list_files(workspace_path: str, args: dict[str, Any]) -> dict[str, Any]:
    """列出目录内容。"""
    target_path = _str_arg(args, "path", ".")
    max_depth = _int_arg(args, "max_depth", 2, minimum=1, maximum=5)
    include_hidden = _bool_arg(args, "include_hidden", False)

    try:
        target = resolve_workspace_path(workspace_path, target_path, must_exist=True)
    except WorkspacePathError as exc:
        return {"ok": False, "error": str(exc), "error_code": "workspace.out_of_scope"}

    entries: list[dict[str, Any]] = []
    truncated = False
    max_entries = 500

    for root, dirs, files in os.walk(target):
        rel_root = Path(root).relative_to(target)
        depth = 0 if str(rel_root) == "." else len(rel_root.parts)
        if depth > max_depth:
            dirs[:] = []
            continue
        if not include_hidden:
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            files = [f for f in files if not f.startswith(".")]

        for name in sorted(dirs):
            if len(entries) >= max_entries:
                truncated = True
                break
            full = Path(root) / name
            entries.append({
                "path": str(rel_root / name) if str(rel_root) != "." else name,
                "type": "directory",
                "size": 0,
            })
        if truncated:
            break

        for name in sorted(files):
            if len(entries) >= max_entries:
                truncated = True
                break
            full = Path(root) / name
            try:
                size = full.stat().st_size
            except OSError:
                size = 0
            entries.append({
                "path": str(rel_root / name) if str(rel_root) != "." else name,
                "type": "file",
                "size": size,
            })
        if truncated:
            break

    summary = f"列出 {len(entries)} 个条目" + ("（已截断）" if truncated else "")
    return {
        "ok": True,
        "entries": entries,
        "truncated": truncated,
        "summary": summary,
    }


async def read_file(workspace_path: str, args: dict[str, Any]) -> dict[str, Any]:
    """读取文件内容。"""
    target_path = _str_arg(args, "path")
    start_line = _int_arg(args, "start_line", 1, minimum=1)
    line_count = _int_arg(args, "line_count", 200, minimum=1, maximum=5000)

    try:
        target = resolve_workspace_path(workspace_path, target_path, must_exist=True)
    except WorkspacePathError as exc:
        return {"ok": False, "error": str(exc), "error_code": "workspace.out_of_scope"}

    if not target.is_file():
        return {"ok": False, "error": f"not a file: {target_path}", "error_code": "tool.schema_invalid"}

    try:
        raw = target.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"ok": False, "error": f"read failed: {exc}", "error_code": "tool.schema_invalid"}

    lines = raw.split("\n")
    total_lines = len(lines)
    end_line = min(start_line + line_count - 1, total_lines)
    selected = lines[start_line - 1 : end_line]
    content = "\n".join(selected)
    truncated = end_line < total_lines

    relative_target_path = safe_relative_path(workspace_path, str(target))
    summary = f"读取 {relative_target_path} 行 {start_line}-{end_line}/{total_lines}"
    return {
        "ok": True,
        "path": relative_target_path,
        "content": content,
        "start_line": start_line,
        "end_line": end_line,
        "total_lines": total_lines,
        "truncated": truncated,
        "summary": summary,
    }


async def search_text(workspace_path: str, args: dict[str, Any]) -> dict[str, Any]:
    """在 workspace 内搜索文本。优先用 ripgrep，不可用时回退到 Python 遍历。"""
    query = _str_arg(args, "query")
    search_path = _str_arg(args, "path", ".")
    glob_pattern = _str_arg(args, "glob")
    max_results = _int_arg(args, "max_results", 50, minimum=1, maximum=200)

    if not query:
        return {"ok": False, "error": "query is required", "error_code": "tool.schema_invalid"}

    try:
        search_root = resolve_workspace_path(workspace_path, search_path, must_exist=True)
    except WorkspacePathError as exc:
        return {"ok": False, "error": str(exc), "error_code": "workspace.out_of_scope"}

    matches: list[dict[str, Any]] = []
    truncated = False

    # 优先尝试 ripgrep（更快）
    rg_available = _check_rg_available()
    if rg_available:
        matches, truncated = _search_with_rg(
            search_root, query, glob_pattern, max_results
        )
    else:
        matches, truncated = _search_with_python(
            search_root, query, glob_pattern, max_results
        )

    summary = f"搜索 \"{query}\" 命中 {len(matches)} 处" + ("（已截断）" if truncated else "")
    return {
        "ok": True,
        "matches": matches,
        "truncated": truncated,
        "summary": summary,
    }


def _check_rg_available() -> bool:
    try:
        result = subprocess.run(
            ["rg", "--version"],
            capture_output=True,
            timeout=3,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _search_with_rg(
    root: Path,
    query: str,
    glob_pattern: str,
    max_results: int,
) -> tuple[list[dict[str, Any]], bool]:
    cmd = [
        "rg",
        "--line-number",
        "--no-heading",
        "--color=never",
        "--max-count", str(max_results),
        query,
        str(root),
    ]
    if glob_pattern:
        cmd.extend(["--glob", glob_pattern])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return [], False

    matches: list[dict[str, Any]] = []
    truncated = False
    for line in result.stdout.split("\n"):
        if not line.strip():
            continue
        # rg 输出格式: path:line_number:content
        parts = line.split(":", 2)
        if len(parts) < 3:
            continue
        file_path, line_num, content = parts[0], parts[1], parts[2]
        rel = os.path.relpath(file_path, str(root))
        matches.append({
            "path": rel,
            "line": int(line_num),
            "content": content.strip(),
        })
        if len(matches) >= max_results:
            truncated = True
            break

    return matches, truncated


def _search_with_python(
    root: Path,
    query: str,
    glob_pattern: str,
    max_results: int,
) -> tuple[list[dict[str, Any]], bool]:
    matches: list[dict[str, Any]] = []
    truncated = False
    query_lower = query.lower()

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d != "__pycache__"]
        for filename in filenames:
            if glob_pattern and not fnmatch.fnmatch(filename, glob_pattern):
                continue
            filepath = Path(dirpath) / filename
            try:
                content = filepath.read_text(encoding="utf-8", errors="replace")
            except (OSError, UnicodeDecodeError):
                continue
            for line_num, line in enumerate(content.split("\n"), 1):
                if query_lower in line.lower():
                    rel = os.path.relpath(str(filepath), str(root))
                    matches.append({
                        "path": rel,
                        "line": line_num,
                        "content": line.strip()[:200],
                    })
                    if len(matches) >= max_results:
                        truncated = True
                        return matches, truncated

    return matches, truncated


async def apply_patch(workspace_path: str, args: dict[str, Any]) -> dict[str, Any]:
    """应用 unified diff patch。"""
    patch_text = str(args.get("patch") or "")
    summary_text = _str_arg(args, "summary")

    if not patch_text.strip():
        return {"ok": False, "error": "patch is required", "error_code": "tool.schema_invalid"}

    workspace = Path(workspace_path).resolve()
    changed_files = _extract_patch_paths(patch_text)
    if not changed_files:
        return {"ok": False, "error": "patch does not contain changed files", "error_code": "tool.schema_invalid"}
    for path in changed_files:
        try:
            resolve_workspace_path(str(workspace), path, allow_create=True)
        except WorkspacePathError as exc:
            return {"ok": False, "error": str(exc), "error_code": "workspace.out_of_scope"}

    try:
        check_result = subprocess.run(
            ["git", "apply", "--check", "--whitespace=fix", "-"],
            input=patch_text,
            capture_output=True,
            text=True,
            cwd=str(workspace),
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": f"git apply --check failed: {exc}", "error_code": "tool.schema_invalid"}

    if check_result.returncode != 0:
        return {
            "ok": False,
            "error": check_result.stderr.strip() or "git apply --check failed",
            "error_code": "tool.schema_invalid",
            "stdout": check_result.stdout,
        }

    # 用 git apply 执行 patch
    try:
        result = subprocess.run(
            ["git", "apply", "--verbose", "--whitespace=fix", "-"],
            input=patch_text,
            capture_output=True,
            text=True,
            cwd=str(workspace),
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": f"git apply failed: {exc}", "error_code": "tool.schema_invalid"}

    if result.returncode != 0:
        return {
            "ok": False,
            "error": result.stderr.strip() or "git apply failed",
            "error_code": "tool.schema_invalid",
            "stdout": result.stdout,
        }

    summary = f"应用 patch：{len(changed_files)} 个文件变更。{summary_text}"
    return {
        "ok": True,
        "changed_files": changed_files,
        "applied": True,
        "summary": summary,
    }


def _extract_patch_paths(patch_text: str) -> list[str]:
    changed: list[str] = []
    seen: set[str] = set()

    def add_path(value: str) -> None:
        path = _normalize_patch_path(value)
        if not path or path in seen:
            return
        seen.add(path)
        changed.append(path)

    for raw_line in str(patch_text or "").splitlines():
        line = raw_line.strip()
        if line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4:
                add_path(parts[2])
                add_path(parts[3])
            continue
        if line.startswith("--- ") or line.startswith("+++ "):
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                add_path(parts[1])
    return changed


def _normalize_patch_path(value: str) -> str:
    path = str(value or "").strip()
    if not path or path == "/dev/null":
        return ""
    if "\t" in path:
        path = path.split("\t", 1)[0].strip()
    if path.startswith('"') and path.endswith('"'):
        path = path[1:-1]
    if path.startswith("a/") or path.startswith("b/"):
        path = path[2:]
    return path


async def write_file(workspace_path: str, args: dict[str, Any]) -> dict[str, Any]:
    """写入或创建文件。"""
    target_path = _str_arg(args, "path")
    content = str(args.get("content") or "")
    overwrite = _bool_arg(args, "overwrite", False)

    if not target_path:
        return {"ok": False, "error": "path is required", "error_code": "tool.schema_invalid"}

    try:
        target = resolve_workspace_path(workspace_path, target_path, allow_create=True)
    except WorkspacePathError as exc:
        return {"ok": False, "error": str(exc), "error_code": "workspace.out_of_scope"}

    existed = target.exists()
    if existed and not overwrite and target.is_file():
        return {
            "ok": False,
            "error": f"file already exists: {target_path} (set overwrite=true to replace)",
            "error_code": "tool.schema_invalid",
        }

    # 确保父目录存在
    target.parent.mkdir(parents=True, exist_ok=True)

    try:
        target.write_text(content, encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "error": f"write failed: {exc}", "error_code": "tool.schema_invalid"}

    summary = f"{'覆盖' if existed else '创建'} {target_path}（{len(content)} 字符）"
    return {
        "ok": True,
        "path": target_path,
        "created": not existed,
        "overwritten": existed,
        "bytes": len(content.encode("utf-8")),
        "summary": summary,
    }
