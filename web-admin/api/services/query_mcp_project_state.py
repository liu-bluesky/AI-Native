from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.deps import project_store

_STATE_DIR = Path(".ai-employee") / "query-mcp"
_LOCAL_ROOT_DIR = Path(".ai-employee")
_ACTIVE_SESSIONS_DIR = "active-sessions"
_OUTBOX_DIR = "outbox"
_REQUIREMENTS_DIR = "requirements"
_SKILLS_DIR = "skills"
_LEGACY_CURRENT_SESSION_FILE = "current-session.json"
_LEGACY_JSON_POINTER_FILES = ("current-work-session.json", "current-query-session.json")
_LEGACY_TEXT_POINTER_FILES = {
    "chat_session_id": ("chat_session_id.txt", "chat_session_id"),
    "session_id": ("session_id.txt", "session_id"),
}
_MAX_LOCAL_TASKS = 100
_STATE_FIELD_LIMITS = {
    "project_id": 120,
    "project_name": 200,
    "workspace_path": 1000,
    "employee_id": 120,
    "chat_session_id": 200,
    "session_id": 200,
    "root_goal": 1000,
    "latest_status": 80,
    "phase": 80,
    "step": 200,
    "developer_name": 120,
    "key_owner_username": 120,
    "source": 120,
    "updated_at": 80,
}
_TERMINAL_STATUSES = {"done", "completed", "archived", "closed"}
_REQUIREMENT_HISTORY_LIMIT = 50
_QUERY_MCP_WORKFLOW_SKILL_ID = "query-mcp-workflow"
_QUERY_MCP_WORKFLOW_SKILL_VERSION = "1.1.0"
_QUERY_MCP_WORKFLOW_MANIFEST = {
    "name": "项目本地 Query MCP 工作流",
    "description": "项目本地统一 MCP 工作流技能，用于指导 AI 在本地优先、任务树闭环和服务端延迟同步模式下稳定执行。",
    "version": _QUERY_MCP_WORKFLOW_SKILL_VERSION,
    "tags": [
        "query-mcp",
        "workflow",
        "local-first",
        "requirements",
        "task-tree",
    ],
    "mcp_service": "query-center-project",
}
_QUERY_MCP_WORKFLOW_SKILL_TEXT = """# 项目本地 Query MCP 工作流

## 作用

当当前需求通过统一查询 MCP 处理，并且执行过程需要在“本地优先推进、支持中断恢复、最后再同步服务端”模式下稳定运行时，使用这个项目本地技能。

这个技能是工作流说明，不是 CLI 包装器。它负责约束 AI 如何一致地使用现有 MCP 工具、本地状态文件和任务树闭环；它不能替代后端校验。

## 初始化要求

1. 执行前先读取 `query://usage-guide`。
2. 当前宿主是 Codex CLI 时，再读取 `query://client-profile/codex`。
3. 先以当前 CLI 工作区为准，检查并补齐本地 `.ai-employee/`，至少确保 `.ai-employee/skills/`、`.ai-employee/query-mcp/active-sessions/`、`.ai-employee/query-mcp/active/`、`.ai-employee/query-mcp/session-history/` 与 `.ai-employee/requirements/<project_id>/` 可用。
4. 项目本地工作流技能默认位于当前项目根目录 `.ai-employee/skills/query-mcp-workflow/`；优先读取本地副本中的 `SKILL.md` 与 `manifest.json`。
5. 只有当前仓库本身就是统一查询 MCP 工作流技能的系统源仓时，才把 `mcp-skills/knowledge/skills/query-mcp-workflow.json` 与 `mcp-skills/knowledge/skill-packages/query-mcp-workflow/` 作为回源比对位置。
6. 如果本地技能已存在且可用，直接复用，不要重复创建。

## 适用场景

- `更新`：需要修改 query-mcp 提示词、`SKILL.md`、`manifest.json`、运行时模板、同步约束或预览文案时使用。
- `使用`：需要执行需求、恢复进度、推进任务树、验证结果或交付结论时使用。

## 必须遵守的工作流

1. 仅在缺少明确的 `project_id` / `employee_id` / `rule_id`，或者需要跨项目检索时，才调用 `search_ids(keyword="<用户原始问题>")`；已明确当前项目时，不要为走流程而机械调用。
2. 进入项目内执行前，先调用 `get_manual_content(project_id=...)` 读取项目手册。
3. 实现型任务在改文件前必须先走 `analyze_task -> resolve_relevant_context -> generate_execution_plan`。
4. 显式调用 `bind_project_context(...)` 绑定当前任务；真正执行前再用 `get_current_task_tree(...)` 确认当前节点。
5. 整个任务固定复用同一个 `chat_session_id` 和同一个 `session_id`；禁止再写 `current-session.json`、`chat_session_id.txt`、`session.env` 这类 legacy 文件。
6. 本地 requirement 记录写入 `.ai-employee/requirements/<project_id>/<chat_session_id>.json`；本地 query-mcp 状态写入 `.ai-employee/query-mcp/` 下的 canonical 文件。
7. 工作流必须本地优先：先完成分析、改动、验证和本地记录，再把任务树状态、工作事实和交付结果同步回服务端。
8. 中断恢复顺序固定为：`bind_project_context(...) -> resume_work_session(...) -> summarize_checkpoint(...)`。
9. 开始节点前先调用 `update_task_node_status(...)`；完成节点时必须调用 `complete_task_node_with_verification(...)`。
10. 如果宿主拿不到任务树读取或推进工具，只能明确说明“任务树闭环未完成”，不能把自然语言进度当成已完成。

## 本地存储约束

- 一个需求对应一个 requirement 文件，不要把多个需求写进同一个聚合文件。
- requirement 文件路径固定为 `.ai-employee/requirements/<project_id>/<chat_session_id>.json`。
- 项目本地工作流技能路径固定为 `.ai-employee/skills/query-mcp-workflow/`。
- query-mcp canonical 本地状态固定写在 `.ai-employee/query-mcp/active-sessions/`、`.ai-employee/query-mcp/active/`、`.ai-employee/query-mcp/session-history/`。

## 同步约束

- 修改 query-mcp 提示词、运行时返回、前端预览、技能包说明或工作流代码时，必须同步更新相关提示词入口、技能说明与回归测试，不能只改单处。
- 如果本地技能和项目入口文件 `AGENTS.md` 不一致，以当前项目 `AGENTS.md` 的约束为准，并应尽快把本地技能同步到一致。

## 边界

- 不要只在自然语言里宣布任务完成；真正完成依赖任务树验证结果和最终同步状态。
- 不要在每一步都把零碎进度立即推回服务端；在本地优先模式下，应优先维护本地状态并按节点回写。
- 不要重新引入 legacy 会话文件或分叉指针文件。
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(value: object, limit: int = 400) -> str:
    return str(value or "").strip()[:limit]


def _safe_name(value: object, fallback: str = "unknown") -> str:
    normalized = _normalize_text(value, 200)
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", normalized).strip("._")
    return cleaned or fallback


def _normalize_state_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    normalized: dict[str, Any] = {}
    for field, limit in _STATE_FIELD_LIMITS.items():
        value = _normalize_text(payload.get(field), limit)
        if value:
            normalized[field] = value
    return normalized


def _merge_state_payloads(*payloads: dict[str, Any] | None) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for payload in payloads:
        normalized = _normalize_state_payload(payload)
        for field, value in normalized.items():
            if field not in merged:
                merged[field] = value
    return merged


def _resolve_project_workspace_path(project_id: str = "", workspace_path: str = "") -> str:
    direct = _normalize_text(workspace_path, 1000)
    if direct:
        candidate = Path(direct).expanduser()
        if candidate.is_dir():
            return str(candidate)
    project_id_value = _normalize_text(project_id, 120)
    if not project_id_value:
        return ""
    try:
        project = project_store.get(project_id_value)
    except Exception:
        project = None
    if project is None:
        return ""
    chat_settings = getattr(project, "chat_settings", {}) or {}
    connector_workspace_path = _normalize_text(
        chat_settings.get("connector_workspace_path"),
        1000,
    )
    if connector_workspace_path:
        candidate = Path(connector_workspace_path).expanduser()
        if candidate.is_dir():
            return str(candidate)
    project_workspace_path = _normalize_text(getattr(project, "workspace_path", ""), 1000)
    if project_workspace_path:
        candidate = Path(project_workspace_path).expanduser()
        if candidate.is_dir():
            return str(candidate)
    return ""


def _resolve_cli_fallback_workspace_path() -> str:
    candidates: list[Path] = []
    for env_name in ("QUERY_MCP_WORKSPACE_PATH", "CODEX_WORKSPACE_ROOT", "PWD"):
        raw_value = _normalize_text(os.environ.get(env_name), 1000)
        if not raw_value:
            continue
        candidate = Path(raw_value).expanduser()
        if candidate.is_dir() and candidate not in candidates:
            candidates.append(candidate)
    try:
        cwd = Path.cwd()
    except Exception:
        cwd = None
    if cwd is not None and cwd.is_dir() and cwd not in candidates:
        candidates.append(cwd)
    return str(candidates[0]) if candidates else ""


def _resolve_local_workspace_context(project_id: str = "", workspace_path: str = "") -> tuple[str, str]:
    resolved_project_workspace = _resolve_project_workspace_path(project_id, workspace_path)
    if resolved_project_workspace:
        return resolved_project_workspace, "project-workspace"
    fallback_workspace = _resolve_cli_fallback_workspace_path()
    if fallback_workspace:
        return fallback_workspace, "cli-fallback"
    return "", ""


def _project_local_root(project_id: str = "", workspace_path: str = "") -> Path | None:
    workspace_root, _storage_scope = _resolve_local_workspace_context(project_id, workspace_path)
    if workspace_root:
        return Path(workspace_root) / _LOCAL_ROOT_DIR
    return None


def _state_root(project_id: str = "", workspace_path: str = "") -> Path | None:
    local_root = _project_local_root(project_id, workspace_path)
    if local_root is not None:
        return local_root / "query-mcp"
    return None


def _requirements_project_dir(project_id: str, workspace_path: str = "") -> Path | None:
    local_root = _project_local_root(project_id, workspace_path)
    if local_root is None:
        return None
    return local_root / _REQUIREMENTS_DIR / _safe_name(project_id)


def _requirement_path(project_id: str, chat_session_id: str, workspace_path: str = "") -> Path | None:
    project_dir = _requirements_project_dir(project_id, workspace_path)
    if project_dir is None:
        return None
    return project_dir / f"{_safe_name(chat_session_id)}.json"


def _workflow_skill_dir(project_id: str, workspace_path: str = "") -> Path | None:
    local_root = _project_local_root(project_id, workspace_path)
    if local_root is None:
        return None
    return local_root / _SKILLS_DIR / _QUERY_MCP_WORKFLOW_SKILL_ID


def _active_session_path(chat_session_id: str, project_id: str = "", workspace_path: str = "") -> Path | None:
    state_root = _state_root(project_id, workspace_path)
    if state_root is None:
        return None
    return state_root / _ACTIVE_SESSIONS_DIR / f"{_safe_name(chat_session_id)}.json"


def _active_state_path(project_id: str, workspace_path: str = "") -> Path | None:
    state_root = _state_root(project_id, workspace_path)
    if state_root is None:
        return None
    return state_root / "active" / f"{_safe_name(project_id)}.json"


def _session_state_path(project_id: str, chat_session_id: str, workspace_path: str = "") -> Path | None:
    state_root = _state_root(project_id, workspace_path)
    if state_root is None:
        return None
    file_name = f"{_safe_name(project_id)}__{_safe_name(chat_session_id)}.json"
    return state_root / "session-history" / file_name


def _outbox_path(project_id: str, chat_session_id: str, workspace_path: str = "") -> Path | None:
    state_root = _state_root(project_id, workspace_path)
    if state_root is None:
        return None
    file_name = f"{_safe_name(project_id)}__{_safe_name(chat_session_id)}.jsonl"
    return state_root / _OUTBOX_DIR / file_name


def _legacy_current_session_path(project_id: str = "", workspace_path: str = "") -> Path | None:
    state_root = _state_root(project_id, workspace_path)
    if state_root is None:
        return None
    return state_root / _LEGACY_CURRENT_SESSION_FILE


def _is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, PermissionError):
        return False


def _extract_pid_from_chat_session_id(chat_session_id: str) -> int:
    parts = chat_session_id.split(".")
    for part in parts:
        if part.isdigit() and len(part) >= 2:
            return int(part)
    return 0


def _load_latest_active_session(project_id: str, workspace_path: str = "") -> dict[str, Any]:
    state_root = _state_root(project_id, workspace_path)
    if state_root is None:
        return {}
    sessions_dir = state_root / _ACTIVE_SESSIONS_DIR
    if not sessions_dir.exists():
        return {}
    project_id_value = _normalize_text(project_id, 120)
    best_payload: dict[str, Any] = {}
    best_updated_at = ""
    for path in sessions_dir.glob("*.json"):
        payload = _read_json(path)
        if not payload:
            continue
        payload_project_id = _normalize_text(payload.get("project_id"), 120)
        if payload_project_id and payload_project_id != project_id_value:
            continue
        updated_at = _normalize_text(payload.get("updated_at"), 80)
        if updated_at >= best_updated_at:
            best_payload = payload
            best_updated_at = updated_at
    return best_payload


def _read_json(path: Path | None) -> dict[str, Any]:
    try:
        if path is None or not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _read_text(path: Path | None, limit: int = 400) -> str:
    try:
        if path is None or not path.exists():
            return ""
        return path.read_text(encoding="utf-8").strip()[:limit]
    except Exception:
        return ""


def _write_json(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    normalized = _normalize_state_payload(payload)
    if not normalized:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_raw_json(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_jsonl(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []
    items: list[dict[str, Any]] = []
    try:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            decoded = json.loads(line)
            if isinstance(decoded, dict):
                items.append(decoded)
    except Exception:
        return []
    return items


def _write_jsonl(path: Path | None, payloads: list[dict[str, Any]]) -> None:
    if path is None:
        return
    if not payloads:
        try:
            if path.exists():
                path.unlink()
        except Exception:
            return
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = "\n".join(json.dumps(item, ensure_ascii=False) for item in payloads if isinstance(item, dict))
    if not serialized:
        return
    path.write_text(serialized + "\n", encoding="utf-8")


def _summarize_text(value: object, limit: int = 240) -> str:
    normalized = re.sub(r"\s+", " ", _normalize_text(value, 4000)).strip()
    return normalized[:limit]


def _summarize_requirement_event(entry: dict[str, Any] | None) -> str:
    if not isinstance(entry, dict):
        return ""
    trajectory = entry.get("trajectory") if isinstance(entry.get("trajectory"), dict) else {}
    facts = trajectory.get("facts") if isinstance(trajectory.get("facts"), list) else []
    if facts:
        return _summarize_text(facts[0], 240)
    content = _normalize_text(entry.get("content"), 4000)
    if content:
        return _summarize_text(content, 240)
    step = _normalize_text(trajectory.get("step"), 200)
    phase = _normalize_text(trajectory.get("phase"), 80)
    return _summarize_text(f"{phase} {step}".strip(), 240)


def _normalize_requirement_history_entry(entry: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(entry, dict):
        return {}
    trajectory = entry.get("trajectory") if isinstance(entry.get("trajectory"), dict) else {}
    normalized = {
        "event_id": _normalize_text(entry.get("event_id"), 80),
        "created_at": _normalize_text(entry.get("created_at"), 80),
        "updated_at": _normalize_text(entry.get("updated_at"), 80),
        "source_kind": _normalize_text(entry.get("source_kind"), 80)
        or _normalize_text(entry.get("memory_type"), 80),
        "event_type": _normalize_text(trajectory.get("event_type"), 80),
        "status": _normalize_text(trajectory.get("status"), 80),
        "phase": _normalize_text(trajectory.get("phase"), 80),
        "step": _normalize_text(trajectory.get("step"), 200),
        "summary": _summarize_requirement_event(entry),
    }
    return {key: value for key, value in normalized.items() if value not in ("", None)}


def _merge_requirement_history(
    existing: list[dict[str, Any]] | None,
    new_entry: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in existing or []:
        if not isinstance(item, dict):
            continue
        normalized = _normalize_requirement_history_entry(item)
        event_id = _normalize_text(normalized.get("event_id"), 80)
        if event_id and event_id in seen_ids:
            continue
        if event_id:
            seen_ids.add(event_id)
        if normalized:
            items.append(normalized)
    normalized_new_entry = _normalize_requirement_history_entry(new_entry)
    new_event_id = _normalize_text(normalized_new_entry.get("event_id"), 80)
    if normalized_new_entry and (not new_event_id or new_event_id not in seen_ids):
        items.append(normalized_new_entry)
    items.sort(
        key=lambda item: (
            _normalize_text(item.get("created_at"), 80),
            _normalize_text(item.get("event_id"), 80),
        ),
        reverse=True,
    )
    return items[:_REQUIREMENT_HISTORY_LIMIT]


def _read_requirement_record(path: Path | None) -> dict[str, Any]:
    payload = _read_json(path)
    return payload if isinstance(payload, dict) else {}


def ensure_query_mcp_workflow_skill(
    *,
    project_id: str,
    workspace_path: str = "",
) -> dict[str, Any]:
    project_id_value = _normalize_text(project_id, 120)
    if not project_id_value:
        return {}
    skill_dir = _workflow_skill_dir(project_id_value, workspace_path)
    if skill_dir is None:
        return {}
    manifest_path = skill_dir / "manifest.json"
    skill_md_path = skill_dir / "SKILL.md"
    created_files: list[str] = []
    skill_dir.mkdir(parents=True, exist_ok=True)
    if not manifest_path.exists():
        manifest_path.write_text(
            json.dumps(_QUERY_MCP_WORKFLOW_MANIFEST, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        created_files.append(str(manifest_path))
    if not skill_md_path.exists():
        skill_md_path.write_text(_QUERY_MCP_WORKFLOW_SKILL_TEXT.strip() + "\n", encoding="utf-8")
        created_files.append(str(skill_md_path))
    return {
        "skill_id": _QUERY_MCP_WORKFLOW_SKILL_ID,
        "version": _QUERY_MCP_WORKFLOW_SKILL_VERSION,
        "path": str(skill_dir),
        "manifest_path": str(manifest_path),
        "skill_md_path": str(skill_md_path),
        "created": bool(created_files),
        "created_files": created_files,
    }


def _coerce_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_task_tree_branches(
    task_tree_payload: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    if not isinstance(task_tree_payload, dict) or not task_tree_payload:
        return {}, {}, []
    current_node_payload = (
        task_tree_payload.get("current_node") if isinstance(task_tree_payload.get("current_node"), dict) else {}
    )
    current_node_id = _normalize_text(
        current_node_payload.get("id") or task_tree_payload.get("current_node_id"),
        80,
    )
    normalized_branches: list[dict[str, Any]] = []
    child_map: dict[str, list[str]] = {}
    for raw_node in task_tree_payload.get("nodes") or []:
        if not isinstance(raw_node, dict):
            continue
        node_id = _normalize_text(raw_node.get("id"), 80)
        if not node_id:
            continue
        parent_id = _normalize_text(raw_node.get("parent_id"), 80)
        if parent_id:
            child_map.setdefault(parent_id, []).append(node_id)
        branch_payload = {
            "id": node_id,
            "parent_id": parent_id,
            "title": _normalize_text(raw_node.get("title"), 200),
            "status": _normalize_text(raw_node.get("status"), 80),
            "node_kind": _normalize_text(raw_node.get("node_kind"), 80),
            "stage_key": _normalize_text(raw_node.get("stage_key"), 80),
            "level": _coerce_int(raw_node.get("level"), 0),
            "sort_order": _coerce_int(raw_node.get("sort_order"), 0),
            "is_current": node_id == current_node_id,
            "summary": _summarize_text(
                raw_node.get("summary_for_model")
                or raw_node.get("latest_outcome")
                or raw_node.get("description"),
                240,
            ),
            "verification_result": _normalize_text(raw_node.get("verification_result"), 500),
        }
        normalized_branches.append(
            {key: value for key, value in branch_payload.items() if value not in ("", None)}
        )
    for branch_payload in normalized_branches:
        branch_children = child_map.get(branch_payload.get("id", ""), [])
        if branch_children:
            branch_payload["children_ids"] = branch_children
    current_branch = next(
        (branch for branch in normalized_branches if branch.get("id") == current_node_id),
        {},
    )
    task_tree_summary = {
        "id": _normalize_text(task_tree_payload.get("id"), 80),
        "chat_session_id": _normalize_text(task_tree_payload.get("chat_session_id"), 200),
        "source_chat_session_id": _normalize_text(task_tree_payload.get("source_chat_session_id"), 200),
        "title": _normalize_text(task_tree_payload.get("title"), 200),
        "root_goal": _normalize_text(task_tree_payload.get("root_goal"), 2000),
        "status": _normalize_text(task_tree_payload.get("status"), 80),
        "lifecycle_status": _normalize_text(task_tree_payload.get("lifecycle_status"), 80),
        "progress_percent": _coerce_int(task_tree_payload.get("progress_percent"), 0),
        "round_index": _coerce_int(task_tree_payload.get("round_index"), 0),
        "current_node_id": current_node_id,
        "current_node_title": _normalize_text(current_branch.get("title"), 200),
        "task_branch_count": len(normalized_branches),
        "updated_at": _normalize_text(task_tree_payload.get("updated_at"), 80),
    }
    health_payload = (
        task_tree_payload.get("task_tree_health")
        if isinstance(task_tree_payload.get("task_tree_health"), dict)
        else {}
    )
    if health_payload:
        task_tree_summary["health"] = {
            "health_score": _coerce_int(health_payload.get("health_score"), 0),
            "issue_count": _coerce_int(health_payload.get("issue_count"), 0),
            "safe_to_display": bool(health_payload.get("safe_to_display")),
        }
    return (
        {key: value for key, value in task_tree_summary.items() if value not in ("", None)},
        current_branch,
        normalized_branches,
    )


def upsert_query_mcp_requirement_record(
    *,
    project_id: str,
    chat_session_id: str,
    workspace_path: str = "",
    project_name: str = "",
    session_id: str = "",
    root_goal: str = "",
    latest_status: str = "",
    phase: str = "",
    step: str = "",
    source: str = "",
    event_entry: dict[str, Any] | None = None,
    sync_status: str = "",
    task_tree_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    project_id_value = _normalize_text(project_id, 120)
    chat_session_id_value = _normalize_text(chat_session_id, 200)
    if not project_id_value or not chat_session_id_value:
        return {}
    path = _requirement_path(project_id_value, chat_session_id_value, workspace_path)
    if path is None:
        return {}
    existing = _read_requirement_record(path)
    now_iso = _now_iso()
    workspace_root, storage_scope = _resolve_local_workspace_context(project_id_value, workspace_path)
    skill_payload = ensure_query_mcp_workflow_skill(
        project_id=project_id_value,
        workspace_path=workspace_path,
    )
    outbox_entries = _read_jsonl(_outbox_path(project_id_value, chat_session_id_value, workspace_path))
    normalized_sync_status = _normalize_text(sync_status, 40).lower()
    if not normalized_sync_status:
        if outbox_entries:
            normalized_sync_status = "pending"
        else:
            normalized_sync_status = _normalize_text(existing.get("sync_status"), 40).lower() or "idle"
    history_items = _merge_requirement_history(existing.get("history"), event_entry)
    existing_task_tree = existing.get("task_tree") if isinstance(existing.get("task_tree"), dict) else {}
    existing_current_task_node = (
        existing.get("current_task_node") if isinstance(existing.get("current_task_node"), dict) else {}
    )
    existing_task_branches = existing.get("task_branches") if isinstance(existing.get("task_branches"), list) else []
    normalized_task_tree, normalized_current_task_node, normalized_task_branches = _normalize_task_tree_branches(
        task_tree_payload
    )
    payload = {
        "record_type": "query-mcp-requirement",
        "version": 2,
        "project_id": project_id_value,
        "project_name": _normalize_text(project_name, 200)
        or _normalize_text(existing.get("project_name"), 200),
        "workspace_path": workspace_root or _normalize_text(existing.get("workspace_path"), 1000),
        "chat_session_id": chat_session_id_value,
        "session_id": _normalize_text(session_id, 200)
        or _normalize_text(existing.get("session_id"), 200),
        "title": _summarize_text(root_goal or existing.get("title") or existing.get("root_goal"), 200),
        "root_goal": _normalize_text(root_goal, 2000)
        or _normalize_text(existing.get("root_goal"), 2000),
        "latest_status": _normalize_text(latest_status, 80)
        or _normalize_text(existing.get("latest_status"), 80),
        "phase": _normalize_text(phase, 80) or _normalize_text(existing.get("phase"), 80),
        "step": _normalize_text(step, 200) or _normalize_text(existing.get("step"), 200),
        "source": _normalize_text(source, 120) or _normalize_text(existing.get("source"), 120),
        "storage_mode": "local-first",
        "storage_scope": storage_scope or _normalize_text(existing.get("storage_scope"), 80),
        "record_path": str(path),
        "sync_status": normalized_sync_status,
        "pending_outbox_count": len(outbox_entries),
        "history_count": len(history_items),
        "history": history_items,
        "workflow_skill": {
            "id": _QUERY_MCP_WORKFLOW_SKILL_ID,
            "version": _QUERY_MCP_WORKFLOW_SKILL_VERSION,
            "path": _normalize_text(skill_payload.get("path"), 1000),
            "manifest_path": _normalize_text(skill_payload.get("manifest_path"), 1000),
            "skill_md_path": _normalize_text(skill_payload.get("skill_md_path"), 1000),
            "created": bool(skill_payload.get("created")),
        },
        "task_tree": normalized_task_tree or existing_task_tree,
        "current_task_node": normalized_current_task_node or existing_current_task_node,
        "task_branches": normalized_task_branches or existing_task_branches,
        "task_branch_count": len(normalized_task_branches or existing_task_branches),
        "created_at": _normalize_text(existing.get("created_at"), 80) or now_iso,
        "updated_at": now_iso,
    }
    _write_raw_json(path, payload)
    return payload


def bootstrap_query_mcp_local_workspace(
    *,
    project_id: str,
    chat_session_id: str,
    workspace_path: str = "",
    project_name: str = "",
    session_id: str = "",
    root_goal: str = "",
    latest_status: str = "",
    phase: str = "",
    step: str = "",
    source: str = "",
    sync_status: str = "",
    task_tree_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    project_id_value = _normalize_text(project_id, 120)
    chat_session_id_value = _normalize_text(chat_session_id, 200)
    if not project_id_value or not chat_session_id_value:
        return {}
    skill_payload = ensure_query_mcp_workflow_skill(
        project_id=project_id_value,
        workspace_path=workspace_path,
    )
    requirement_payload = upsert_query_mcp_requirement_record(
        project_id=project_id_value,
        chat_session_id=chat_session_id_value,
        workspace_path=workspace_path,
        project_name=project_name,
        session_id=session_id,
        root_goal=root_goal,
        latest_status=latest_status,
        phase=phase,
        step=step,
        source=source,
        sync_status=sync_status,
        task_tree_payload=task_tree_payload,
    )
    return {
        "skill": skill_payload,
        "requirement": requirement_payload,
    }


def load_query_mcp_requirement_record(
    project_id: str,
    *,
    chat_session_id: str,
    workspace_path: str = "",
) -> dict[str, Any]:
    project_id_value = _normalize_text(project_id, 120)
    chat_session_id_value = _normalize_text(chat_session_id, 200)
    if not project_id_value or not chat_session_id_value:
        return {}
    return _read_requirement_record(
        _requirement_path(project_id_value, chat_session_id_value, workspace_path)
    )


def _normalize_progress_list(values: object, *, item_limit: int = 400, max_items: int = 50) -> list[str]:
    items: list[str] = []
    if isinstance(values, str):
        source = [values]
    elif isinstance(values, (list, tuple, set)):
        source = [str(item or "") for item in values]
    else:
        source = [str(values or "")] if values not in (None, "") else []
    for item in source:
        normalized = _normalize_text(item, item_limit)
        if normalized and normalized not in items:
            items.append(normalized)
        if len(items) >= max_items:
            break
    return items


def _normalize_progress_trajectory(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    normalized: dict[str, Any] = {}
    for key in (
        "kind",
        "session_id",
        "task_tree_session_id",
        "task_tree_chat_session_id",
        "task_node_id",
        "task_node_title",
        "event_type",
        "phase",
        "step",
        "status",
        "goal",
        "content",
    ):
        value = _normalize_text(payload.get(key), 4000 if key == "content" else 400)
        if value:
            normalized[key] = value
    for key in ("facts", "changed_files", "verification", "risks", "next_steps"):
        values = _normalize_progress_list(payload.get(key))
        if values:
            normalized[key] = values
    return normalized


def _normalize_outbox_entry(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    normalized = {
        "event_id": _normalize_text(payload.get("event_id"), 80),
        "project_id": _normalize_text(payload.get("project_id"), 120),
        "project_name": _normalize_text(payload.get("project_name"), 200),
        "employee_id": _normalize_text(payload.get("employee_id"), 120),
        "chat_session_id": _normalize_text(payload.get("chat_session_id"), 200),
        "session_id": _normalize_text(payload.get("session_id"), 200),
        "root_goal": _normalize_text(payload.get("root_goal"), 1000),
        "source_kind": _normalize_text(payload.get("source_kind"), 80),
        "memory_type": _normalize_text(payload.get("memory_type"), 80),
        "content": _normalize_text(payload.get("content"), 8000),
        "created_at": _normalize_text(payload.get("created_at"), 80) or _now_iso(),
        "updated_at": _normalize_text(payload.get("updated_at"), 80) or _now_iso(),
    }
    try:
        normalized["importance"] = max(0.0, min(float(payload.get("importance", 0.6)), 1.0))
    except (TypeError, ValueError):
        normalized["importance"] = 0.6
    purpose_tags = _normalize_progress_list(payload.get("purpose_tags"), item_limit=120, max_items=20)
    if purpose_tags:
        normalized["purpose_tags"] = purpose_tags
    work_session_event_id = _normalize_text(payload.get("work_session_event_id"), 80)
    if work_session_event_id:
        normalized["work_session_event_id"] = work_session_event_id
        normalized["work_session_event_saved"] = True
    trajectory = _normalize_progress_trajectory(payload.get("trajectory"))
    if trajectory:
        normalized["trajectory"] = trajectory
    return {key: value for key, value in normalized.items() if value not in ("", [], None)}


def _trim_query_mcp_session_artifacts(
    project_id: str,
    workspace_path: str = "",
    keep: int = _MAX_LOCAL_TASKS,
) -> list[str]:
    project_id_value = _normalize_text(project_id, 120)
    if not project_id_value:
        return []
    state_root = _state_root(project_id_value, workspace_path)
    if state_root is None:
        return []
    try:
        keep_value = max(1, min(int(keep or _MAX_LOCAL_TASKS), 500))
    except (TypeError, ValueError):
        keep_value = _MAX_LOCAL_TASKS
    sessions: dict[str, dict[str, Any]] = {}

    def _merge_session(chat_session_id: str, payload: dict[str, Any] | None, path: Path | None) -> None:
        chat_value = _normalize_text(chat_session_id, 200)
        if not chat_value:
            return
        item = sessions.setdefault(
            chat_value,
            {
                "chat_session_id": chat_value,
                "updated_at": "",
                "latest_status": "",
                "paths": [],
            },
        )
        if path is not None and path not in item["paths"]:
            item["paths"].append(path)
        payload = payload or {}
        updated_at = _normalize_text(payload.get("updated_at"), 80)
        if updated_at and updated_at >= item["updated_at"]:
            item["updated_at"] = updated_at
        latest_status = _normalize_text(payload.get("latest_status"), 80)
        if latest_status:
            item["latest_status"] = latest_status

    history_dir = state_root / "session-history"
    if history_dir.exists():
        for path in history_dir.glob(f"{_safe_name(project_id_value)}__*.json"):
            payload = _read_json(path)
            _merge_session(payload.get("chat_session_id"), payload, path)

    active_sessions_dir = state_root / _ACTIVE_SESSIONS_DIR
    if active_sessions_dir.exists():
        for path in active_sessions_dir.glob("*.json"):
            payload = _read_json(path)
            payload_project_id = _normalize_text(payload.get("project_id"), 120)
            if payload_project_id and payload_project_id != project_id_value:
                continue
            _merge_session(payload.get("chat_session_id"), payload, path)

    outbox_dir = state_root / _OUTBOX_DIR
    if outbox_dir.exists():
        for path in outbox_dir.glob(f"{_safe_name(project_id_value)}__*.jsonl"):
            entries = _read_jsonl(path)
            if not entries:
                continue
            latest_entry = _normalize_outbox_entry(entries[-1])
            latest_payload = {
                "updated_at": latest_entry.get("updated_at") or latest_entry.get("created_at"),
                "latest_status": (
                    (latest_entry.get("trajectory") or {}).get("status")
                    if isinstance(latest_entry.get("trajectory"), dict)
                    else ""
                ),
            }
            _merge_session(latest_entry.get("chat_session_id"), latest_payload, path)

    requirements_dir = _requirements_project_dir(project_id_value, workspace_path)
    if requirements_dir is not None and requirements_dir.exists():
        for path in requirements_dir.glob("*.json"):
            payload = _read_requirement_record(path)
            _merge_session(payload.get("chat_session_id"), payload, path)

    if len(sessions) <= keep_value:
        return []

    active_payload = _read_json(_active_state_path(project_id_value, workspace_path))
    active_chat_session_id = _normalize_text(active_payload.get("chat_session_id"), 200)
    candidates = [item for item in sessions.values() if item["chat_session_id"] != active_chat_session_id]

    def _sort_key(item: dict[str, Any]) -> tuple[int, str, str]:
        status_value = _normalize_text(item.get("latest_status"), 80).lower()
        is_terminal = 0 if status_value in _TERMINAL_STATUSES else 1
        return (is_terminal, _normalize_text(item.get("updated_at"), 80), _normalize_text(item.get("chat_session_id"), 200))

    candidates.sort(key=_sort_key)
    excess = max(0, len(sessions) - keep_value)
    trimmed_chat_session_ids: list[str] = []
    for item in candidates[:excess]:
        chat_session_id_value = _normalize_text(item.get("chat_session_id"), 200)
        if not chat_session_id_value:
            continue
        for path in item.get("paths") or []:
            try:
                if isinstance(path, Path) and path.exists():
                    path.unlink()
            except Exception:
                continue
        trimmed_chat_session_ids.append(chat_session_id_value)
    return trimmed_chat_session_ids


def _load_latest_history_payload(project_id: str, workspace_path: str = "") -> dict[str, Any]:
    state_root = _state_root(project_id, workspace_path)
    if state_root is None:
        return {}
    history_dir = state_root / "session-history"
    if not history_dir.exists():
        return {}
    candidates = sorted(history_dir.glob(f"{_safe_name(project_id)}__*.json"))
    latest_payload: dict[str, Any] = {}
    latest_updated_at = ""
    for path in candidates:
        payload = _read_json(path)
        updated_at = _normalize_text(payload.get("updated_at"), 80)
        if updated_at >= latest_updated_at and payload:
            latest_payload = payload
            latest_updated_at = updated_at
    return latest_payload


def _read_legacy_env_state(project_id: str, workspace_path: str = "") -> dict[str, Any]:
    state_root = _state_root(project_id, workspace_path)
    if state_root is None:
        return {}
    raw = _read_text(state_root / "session.env", 2000)
    if not raw:
        return {}
    parsed: dict[str, str] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        parsed[key.strip().lower()] = value.strip().strip("\"'")
    env_payload = {
        "project_id": parsed.get("project_id", ""),
        "chat_session_id": parsed.get("chat_session_id", ""),
        "session_id": parsed.get("session_id", ""),
        "root_goal": parsed.get("root_goal", ""),
    }
    project_id_value = _normalize_text(project_id, 120)
    payload_project_id = _normalize_text(env_payload.get("project_id"), 120)
    if payload_project_id and payload_project_id != project_id_value:
        return {}
    if not payload_project_id and project_id_value:
        env_payload["project_id"] = project_id_value
    return _normalize_state_payload(env_payload)


def _load_legacy_pointer_state(project_id: str, workspace_path: str = "") -> dict[str, Any]:
    project_id_value = _normalize_text(project_id, 120)
    state_root = _state_root(project_id_value, workspace_path)
    if state_root is None:
        return {}
    legacy_json_payloads: list[dict[str, Any]] = []
    for file_name in _LEGACY_JSON_POINTER_FILES:
        payload = _read_json(state_root / file_name)
        if not payload:
            continue
        payload_project_id = _normalize_text(payload.get("project_id"), 120)
        if payload_project_id and payload_project_id != project_id_value:
            continue
        if not payload_project_id:
            payload = {**payload, "project_id": project_id_value}
        legacy_json_payloads.append(payload)
    fallback_text_payload = {
        "project_id": project_id_value,
        "chat_session_id": "",
        "session_id": "",
    }
    for field, file_names in _LEGACY_TEXT_POINTER_FILES.items():
        for file_name in file_names:
            value = _read_text(state_root / file_name, _STATE_FIELD_LIMITS[field])
            if value:
                fallback_text_payload[field] = value
                break
    return _merge_state_payloads(
        *legacy_json_payloads,
        _read_legacy_env_state(project_id_value, workspace_path),
        fallback_text_payload,
    )


def _payload_matches_chat_session(payload: dict[str, Any], chat_session_id: str) -> bool:
    payload_chat_session_id = _normalize_text(payload.get("chat_session_id"), 200)
    return bool(payload_chat_session_id and payload_chat_session_id == chat_session_id)


def load_bound_query_mcp_session(
    project_id: str,
    chat_session_id: str,
    workspace_path: str = "",
) -> dict[str, Any]:
    project_id_value = _normalize_text(project_id, 120)
    chat_session_id_value = _normalize_text(chat_session_id, 200)
    if not project_id_value or not chat_session_id_value:
        return {}
    payload = _merge_state_payloads(
        _read_json(_active_session_path(chat_session_id_value, project_id_value, workspace_path)),
        _read_json(_session_state_path(project_id_value, chat_session_id_value, workspace_path)),
    )
    payload_project_id = _normalize_text(payload.get("project_id"), 120)
    if payload_project_id and payload_project_id != project_id_value:
        return {}
    if not _payload_matches_chat_session(payload, chat_session_id_value):
        return {}
    if payload and not payload_project_id:
        payload = {**payload, "project_id": project_id_value}
    return _normalize_state_payload(payload)


def load_current_query_mcp_session(
    project_id: str,
    workspace_path: str = "",
    chat_session_id: str = "",
) -> dict[str, Any]:
    """Return only an explicitly bound MCP session.

    Project-level active/history/legacy files are resumable hints, not a safe
    current binding. Without a chat_session_id from the transport or caller,
    treating the latest project file as current can attach a new window to an
    old task tree.
    """
    if _normalize_text(chat_session_id, 200):
        return load_bound_query_mcp_session(project_id, chat_session_id, workspace_path)
    _ = project_id, workspace_path
    return {}


def load_query_mcp_local_state(project_id: str, workspace_path: str = "") -> dict[str, Any]:
    project_id_value = _normalize_text(project_id, 120)
    if not project_id_value:
        return {}
    return _merge_state_payloads(
        _read_json(_active_state_path(project_id_value, workspace_path)),
        _load_latest_history_payload(project_id_value, workspace_path),
        _load_legacy_pointer_state(project_id_value, workspace_path),
    )


def load_resumable_query_mcp_local_state(project_id: str, workspace_path: str = "") -> dict[str, Any]:
    payload = load_query_mcp_local_state(project_id, workspace_path)
    if not payload:
        return {}
    latest_status = _normalize_text(payload.get("latest_status"), 40).lower()
    if latest_status in _TERMINAL_STATUSES:
        return {}
    if not _normalize_text(payload.get("chat_session_id"), 200):
        return {}
    return payload


def persist_query_mcp_local_state(
    *,
    project_id: str,
    chat_session_id: str,
    workspace_path: str = "",
    project_name: str = "",
    employee_id: str = "",
    session_id: str = "",
    root_goal: str = "",
    latest_status: str = "",
    phase: str = "",
    step: str = "",
    developer_name: str = "",
    key_owner_username: str = "",
    source: str = "",
    task_tree_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    project_id_value = _normalize_text(project_id, 120)
    chat_session_id_value = _normalize_text(chat_session_id, 200)
    if not project_id_value or not chat_session_id_value:
        return {}
    active_path = _active_state_path(project_id_value, workspace_path)
    session_path = _session_state_path(project_id_value, chat_session_id_value, workspace_path)
    active_session_path = _active_session_path(chat_session_id_value, project_id_value, workspace_path)
    if active_path is None or session_path is None or active_session_path is None:
        return {}
    active_payload = _read_json(active_path)
    if not _payload_matches_chat_session(active_payload, chat_session_id_value):
        active_payload = {}
    legacy_payload = _load_legacy_pointer_state(project_id_value, workspace_path)
    if not _payload_matches_chat_session(legacy_payload, chat_session_id_value):
        legacy_payload = {}
    existing = _merge_state_payloads(
        _read_json(active_session_path),
        _read_json(session_path),
        active_payload,
        legacy_payload,
    )
    payload = {
        "project_id": project_id_value,
        "project_name": _normalize_text(project_name, 200)
        or _normalize_text(existing.get("project_name"), 200),
        "workspace_path": _resolve_project_workspace_path(project_id_value, workspace_path)
        or _normalize_text(existing.get("workspace_path"), 1000),
        "employee_id": _normalize_text(employee_id, 120)
        or _normalize_text(existing.get("employee_id"), 120),
        "chat_session_id": chat_session_id_value,
        "session_id": _normalize_text(session_id, 200)
        or _normalize_text(existing.get("session_id"), 200),
        "root_goal": _normalize_text(root_goal, 1000)
        or _normalize_text(existing.get("root_goal"), 1000),
        "latest_status": _normalize_text(latest_status, 80)
        or _normalize_text(existing.get("latest_status"), 80),
        "phase": _normalize_text(phase, 80) or _normalize_text(existing.get("phase"), 80),
        "step": _normalize_text(step, 200) or _normalize_text(existing.get("step"), 200),
        "developer_name": _normalize_text(developer_name, 120)
        or _normalize_text(existing.get("developer_name"), 120),
        "key_owner_username": _normalize_text(key_owner_username, 120)
        or _normalize_text(existing.get("key_owner_username"), 120),
        "source": _normalize_text(source, 120) or _normalize_text(existing.get("source"), 120),
        "updated_at": _now_iso(),
    }
    bootstrap_query_mcp_local_workspace(
        project_id=project_id_value,
        chat_session_id=chat_session_id_value,
        workspace_path=workspace_path,
        project_name=payload.get("project_name", ""),
        session_id=payload.get("session_id", ""),
        root_goal=payload.get("root_goal", ""),
        latest_status=payload.get("latest_status", ""),
        phase=payload.get("phase", ""),
        step=payload.get("step", ""),
        source=payload.get("source", ""),
        task_tree_payload=task_tree_payload,
    )
    _write_json(active_session_path, payload)
    _write_json(session_path, payload)
    _write_json(active_path, payload)
    _trim_query_mcp_session_artifacts(project_id_value, workspace_path)
    return _normalize_state_payload(payload)


def append_query_mcp_progress_outbox(
    *,
    project_id: str,
    chat_session_id: str,
    session_id: str = "",
    workspace_path: str = "",
    project_name: str = "",
    employee_id: str = "",
    root_goal: str = "",
    latest_status: str = "",
    phase: str = "",
    step: str = "",
    source_kind: str = "",
    memory_type: str = "",
    content: str = "",
    importance: float = 0.6,
    purpose_tags: list[str] | tuple[str, ...] | None = None,
    trajectory: dict[str, Any] | None = None,
    task_tree_payload: dict[str, Any] | None = None,
    work_session_event_id: str = "",
) -> dict[str, Any]:
    project_id_value = _normalize_text(project_id, 120)
    chat_session_id_value = _normalize_text(chat_session_id, 200)
    if not project_id_value or not chat_session_id_value:
        return {}
    path = _outbox_path(project_id_value, chat_session_id_value, workspace_path)
    if path is None:
        return {}
    entry = _normalize_outbox_entry(
        {
            "event_id": f"lqe-{_safe_name(chat_session_id_value, 'chat')}-{os.urandom(4).hex()}",
            "project_id": project_id_value,
            "project_name": project_name,
            "employee_id": employee_id,
            "chat_session_id": chat_session_id_value,
            "session_id": session_id,
            "root_goal": root_goal,
            "source_kind": source_kind,
            "memory_type": memory_type,
            "content": content,
            "importance": importance,
            "purpose_tags": list(purpose_tags or []),
            "trajectory": trajectory or {},
            "work_session_event_id": work_session_event_id,
            "updated_at": _now_iso(),
            "created_at": _now_iso(),
        }
    )
    if not entry:
        return {}
    existing = _read_jsonl(path)
    existing.append(entry)
    _write_jsonl(path, existing)
    upsert_query_mcp_requirement_record(
        project_id=project_id_value,
        chat_session_id=chat_session_id_value,
        workspace_path=workspace_path,
        project_name=project_name,
        session_id=session_id,
        root_goal=root_goal,
        latest_status=latest_status or (
            (entry.get("trajectory") or {}).get("status")
            if isinstance(entry.get("trajectory"), dict)
            else ""
        ),
        phase=phase or (
            (entry.get("trajectory") or {}).get("phase")
            if isinstance(entry.get("trajectory"), dict)
            else ""
        ),
        step=step or (
            (entry.get("trajectory") or {}).get("step")
            if isinstance(entry.get("trajectory"), dict)
            else ""
        ),
        source="local_outbox",
        event_entry=entry,
        sync_status="pending",
        task_tree_payload=task_tree_payload,
    )
    persist_query_mcp_local_state(
        project_id=project_id_value,
        project_name=project_name,
        employee_id=employee_id,
        chat_session_id=chat_session_id_value,
        session_id=session_id,
        root_goal=root_goal,
        latest_status=latest_status or ((entry.get("trajectory") or {}).get("status") if isinstance(entry.get("trajectory"), dict) else ""),
        phase=phase or ((entry.get("trajectory") or {}).get("phase") if isinstance(entry.get("trajectory"), dict) else ""),
        step=step or ((entry.get("trajectory") or {}).get("step") if isinstance(entry.get("trajectory"), dict) else ""),
        source="local_outbox",
    )
    _trim_query_mcp_session_artifacts(project_id_value, workspace_path)
    return entry


def mark_query_mcp_outbox_work_session_event(
    *,
    project_id: str,
    chat_session_id: str,
    event_id: str,
    work_session_event_id: str,
    workspace_path: str = "",
) -> dict[str, Any]:
    project_id_value = _normalize_text(project_id, 120)
    chat_session_id_value = _normalize_text(chat_session_id, 200)
    event_id_value = _normalize_text(event_id, 80)
    work_session_event_id_value = _normalize_text(work_session_event_id, 80)
    if not project_id_value or not chat_session_id_value or not event_id_value or not work_session_event_id_value:
        return {}
    path = _outbox_path(project_id_value, chat_session_id_value, workspace_path)
    if path is None:
        return {}
    updated_entries: list[dict[str, Any]] = []
    updated_entry: dict[str, Any] = {}
    for item in _read_jsonl(path):
        normalized = _normalize_outbox_entry(item)
        if _normalize_text(normalized.get("event_id"), 80) == event_id_value:
            normalized["work_session_event_id"] = work_session_event_id_value
            normalized["work_session_event_saved"] = True
            updated_entry = normalized
        updated_entries.append(normalized)
    if updated_entry:
        _write_jsonl(path, updated_entries)
    return updated_entry


def load_query_mcp_progress_outbox(
    project_id: str,
    *,
    chat_session_id: str = "",
    session_id: str = "",
    workspace_path: str = "",
    limit: int = 200,
    oldest_first: bool = False,
) -> list[dict[str, Any]]:
    project_id_value = _normalize_text(project_id, 120)
    if not project_id_value:
        return []
    try:
        limit_value = max(1, min(int(limit or 200), 1000))
    except (TypeError, ValueError):
        limit_value = 200
    state_root = _state_root(project_id_value, workspace_path)
    if state_root is None:
        return []
    chat_session_id_value = _normalize_text(chat_session_id, 200)
    session_id_value = _normalize_text(session_id, 200)
    paths: list[Path] = []
    if chat_session_id_value:
        path = _outbox_path(project_id_value, chat_session_id_value, workspace_path)
        if path is not None:
            paths = [path]
    else:
        outbox_dir = state_root / _OUTBOX_DIR
        if outbox_dir.exists():
            paths = sorted(outbox_dir.glob(f"{_safe_name(project_id_value)}__*.jsonl"))
    entries: list[dict[str, Any]] = []
    for path in paths:
        for item in _read_jsonl(path):
            normalized = _normalize_outbox_entry(item)
            if not normalized:
                continue
            if session_id_value and _normalize_text(normalized.get("session_id"), 200) != session_id_value:
                continue
            entries.append(normalized)
    entries.sort(
        key=lambda item: (
            _normalize_text(item.get("created_at"), 80),
            _normalize_text(item.get("event_id"), 80),
        ),
        reverse=not oldest_first,
    )
    return entries[:limit_value]


def delete_query_mcp_progress_outbox_entries(
    project_id: str,
    *,
    chat_session_id: str,
    event_ids: list[str] | tuple[str, ...] | set[str] | None = None,
    workspace_path: str = "",
) -> int:
    project_id_value = _normalize_text(project_id, 120)
    chat_session_id_value = _normalize_text(chat_session_id, 200)
    if not project_id_value or not chat_session_id_value:
        return 0
    path = _outbox_path(project_id_value, chat_session_id_value, workspace_path)
    if path is None:
        return 0
    existing = _read_jsonl(path)
    if not existing:
        return 0
    target_ids = {_normalize_text(item, 80) for item in (event_ids or []) if _normalize_text(item, 80)}
    if not target_ids:
        _write_jsonl(path, [])
        upsert_query_mcp_requirement_record(
            project_id=project_id_value,
            chat_session_id=chat_session_id_value,
            workspace_path=workspace_path,
            sync_status="synced",
        )
        return len(existing)
    remaining = [item for item in existing if _normalize_text(item.get("event_id"), 80) not in target_ids]
    deleted = len(existing) - len(remaining)
    _write_jsonl(path, remaining)
    upsert_query_mcp_requirement_record(
        project_id=project_id_value,
        chat_session_id=chat_session_id_value,
        workspace_path=workspace_path,
        sync_status="synced" if not remaining else "partial",
    )
    return deleted


def load_query_mcp_project_state(project_id: str, workspace_path: str = "") -> dict[str, Any]:
    return load_query_mcp_local_state(project_id, workspace_path)


def load_resumable_query_mcp_project_state(project_id: str, workspace_path: str = "") -> dict[str, Any]:
    return load_resumable_query_mcp_local_state(project_id, workspace_path)


def save_query_mcp_project_state(
    *,
    project_id: str,
    chat_session_id: str,
    workspace_path: str = "",
    project_name: str = "",
    employee_id: str = "",
    session_id: str = "",
    root_goal: str = "",
    latest_status: str = "",
    phase: str = "",
    step: str = "",
    developer_name: str = "",
    key_owner_username: str = "",
    source: str = "",
) -> dict[str, Any]:
    return persist_query_mcp_local_state(
        project_id=project_id,
        chat_session_id=chat_session_id,
        workspace_path=workspace_path,
        project_name=project_name,
        employee_id=employee_id,
        session_id=session_id,
        root_goal=root_goal,
        latest_status=latest_status,
        phase=phase,
        step=step,
        developer_name=developer_name,
        key_owner_username=key_owner_username,
        source=source,
    )
