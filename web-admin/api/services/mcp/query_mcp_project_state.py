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
2. 再按当前客户端读取对应画像：Codex 读 `query://client-profile/codex`，Claude Code 读 `query://client-profile/claude-code`，其他 CLI 或不确定时读 `query://client-profile/generic-cli`。
3. 先以当前 CLI 工作区为准，检查并补齐本地 `.ai-employee/`，至少确保 `.ai-employee/skills/`、`.ai-employee/query-mcp/active-sessions/`、`.ai-employee/query-mcp/session-history/` 与 `.ai-employee/requirements/<project_id>/` 可用。
4. 项目本地工作流技能默认位于当前项目根目录 `.ai-employee/skills/query-mcp-workflow/`；优先读取本地副本中的 `SKILL.md` 与 `manifest.json`。
5. 只有当前仓库本身就是统一查询 MCP 工作流技能的系统源仓时，才把 `mcp-skills/knowledge/skills/query-mcp-workflow.json` 与 `mcp-skills/knowledge/skill-packages/query-mcp-workflow/` 作为回源比对位置。
6. 如果本地技能已存在且可用，直接复用，不要重复创建。
7. 遇到“打包部署”“发布测试环境”“执行部署命令”等打包、部署或发布任务时，必须先加载 `.ai-employee/skills/project-deploy-artifact/`；本地缺失时从 `mcp-skills/knowledge/skill-packages/project-deploy-artifact/` 同步。

## 适用场景

- `更新`：需要修改 query-mcp 提示词、`SKILL.md`、`manifest.json`、运行时模板、同步约束或预览文案时使用。
- `使用`：需要执行需求、恢复进度、推进任务树、验证结果或交付结论时使用。

## 必须遵守的工作流

1. 仅在缺少明确的 `project_id` / `employee_id` / `rule_id`，或者需要跨项目检索时，才调用 `search_ids(keyword="<用户原始问题>")`；已明确当前项目时，不要为走流程而机械调用。
2. 进入项目内执行前，先调用 `get_manual_content(project_id=...)` 读取项目手册。
3. 实现型任务在改文件前必须先走 `analyze_task -> resolve_relevant_context -> generate_execution_plan`。
4. 显式调用 `bind_project_context(...)` 绑定当前任务；真正执行前再用 `get_current_task_tree(...)` 确认当前节点。
5. 整个任务固定复用同一个 `chat_session_id` 和同一个 `session_id`；不要在项目工作区写入分叉会话状态文件。
6. 本地 requirement 记录写入 `.ai-employee/requirements/<project_id>/<chat_session_id>.json`；本地 query-mcp 状态写入 `.ai-employee/query-mcp/` 下的 canonical 文件。
7. 工作流必须本地优先：先完成分析、改动、验证和本地记录，再把任务树状态、工作事实和交付结果同步回服务端。
8. 中断恢复顺序固定为：`bind_project_context(...) -> resume_work_session(...) -> summarize_checkpoint(...)`。
9. 开始节点前先调用 `update_task_node_status(...)`；完成节点时必须调用 `complete_task_node_with_verification(...)`。
10. 如果宿主拿不到任务树读取或推进工具，只能明确说明“任务树闭环未完成”，不能把自然语言进度当成已完成。

## 项目聊天部署约束

用户提“部署 / 发布到服务器 / 上线 / 发版”需求时，第一步先调用 `get_project_deploy_options(project_id)` 读取脱敏部署配置，把可选环境档位 profile（prod/test 等）和服务器目标 target（含 remote_path、是否带 deploy_command）摆给用户让其选择，再决定打包/上传/触发远端命令；部署不一定是压缩包，按 component 的 `artifact_kind` 和 target 部署方式判断；通知由配置的 `notify_enabled` 决定，不询问用户；返回 `configured=false` 时直接报 `blocked` / `missing` 并提示去项目详情补齐部署配置，不要凭空打包或臆造服务器信息。

打包命令只能通过项目聊天命令执行能力处理，并且必须在桌面端 Runner 中运行；客户端打包或读取指定压缩包后，必须推送到服务端项目详情的部署产物模块；若本地 `project-deploy-artifact` 技能提供 `scripts/push_local_artifact.py`，优先用脚本从当前客户端/Runner 读取本地文件并上传，否则调用 `push_project_deploy_artifact` 时必须传 `artifact_content_base64`；再由部署产物 AI/服务端自动部署能力执行部署。

执行本地打包命令前必须明确命令内容、工作目录、影响范围、生成产物路径和可恢复性；执行本地打包命令前必须取得用户明确授权；部署到生产档位或触发远端 deploy_command 等不可逆操作前必须单独说明影响范围和可恢复性并取得用户确认。

未运行桌面端 Runner 或当前电脑不可达时，必须停止并提示无法执行本地打包命令；只有用户明确给出 `artifact_id` 或明确说部署已有服务端产物时，才调用 `deploy_project_deploy_artifact`；本地 zip、新代码、重新打包、上传部署或推送部署产物必须先上传本轮文件生成新 artifact。

如果入口当前接入上下文、URL 默认上下文或渲染出的 CLI 提示词已提供 `project_id`，部署、上传或推送部署产物时把它视为明确项目 ID；不要因为用户回复“确认部署”时未重复 project_id 就暂停。

部署任务禁止扫描、读取或复用历史发布配置、CI 配置、本地凭据、远端脚本或环境变量作为执行依据；禁止把 FTP/SSH 账号密码交给模型或本地命令；凭据只通过项目部署配置由服务端使用，AI 侧只读到脱敏摘要；缺少桌面端 Runner、打包命令、部署产物上传能力、服务端 artifact、项目部署配置或部署产物自动部署能力时，直接报告 `blocked` / `missing`。

## 任务树生成约束

1. 生成任务树前先识别需求类型和真实对象：查询、文档、修复、治理/工作流、页面交互、优化或通用实现。
2. 查询型问题保持 1 个检索回答节点，最多补 1 个轻量整理节点；不要拆成实现、修复或测试链路。
3. 实现型、修复型、治理型、文档型任务禁止固定生成“分析 / 实现 / 验证”三步。节点数量、标题和阶段必须随需求类型变化。
4. 节点标题不能把“当前需求”当作主要对象；必须写出用户原始需求里的路径、功能名、状态枚举、MCP 对象、文档目录或模块名。
5. 治理/工作流类任务至少覆盖入口链路、任务树生成、健康检查、恢复续跑、提示词/技能同步和测试验证。
6. 修复类任务至少覆盖复现、状态/数据映射定位、最小修复、回归测试和真实或模拟流程验证。
7. 文档类任务至少覆盖目标路径确认、现有文档梳理、内容写入、回读校对和后续实现项记录。
8. 如果已生成的任务树出现固定三步、多个节点含“当前需求”、缺少真实对象或实现型节点少于必要链路，必须重建后再展示或继续执行。

## 本地存储约束

- 一个需求对应一个 requirement 文件，不要把多个需求写进同一个聚合文件。
- requirement 文件路径固定为 `.ai-employee/requirements/<project_id>/<chat_session_id>.json`。
- 项目本地工作流技能路径固定为 `.ai-employee/skills/query-mcp-workflow/`。
- query-mcp canonical 本地状态固定写在 `.ai-employee/query-mcp/active-sessions/` 与 `.ai-employee/query-mcp/session-history/`。

## 同步约束

- 修改 query-mcp 提示词、运行时返回、前端预览、技能包说明或工作流代码时，必须同步更新相关提示词入口、技能说明与回归测试，不能只改单处。
- 如果本地技能和项目入口文件 `AGENTS.md` 不一致，以当前项目 `AGENTS.md` 的约束为准，并应尽快把本地技能同步到一致。

## 边界

- 不要只在自然语言里宣布任务完成；真正完成依赖任务树验证结果和最终同步状态。
- 不要在每一步都把零碎进度立即推回服务端；在本地优先模式下，应优先维护本地状态并按节点回写。
- 不要重新引入分叉会话状态文件。
"""

# --- Claude Code hook 自动初始化 ---------------------------------------------
# 任意电脑、任意项目接入统一查询 MCP 时，bind 阶段自动在客户端工作区落地
# `.claude/` hook，让 Claude Code 每轮自动注入 MCP bootstrap 提醒，而不是依赖
# 某台机器手工配置。所有受管文件带 _CLAUDE_MANAGED_MARKER，便于幂等刷新且不覆盖
# 用户自定义内容。
_CLAUDE_DIR = ".claude"
_CLAUDE_HOOKS_DIR = "hooks"
_CLAUDE_SETTINGS_FILE = "settings.json"
_CLAUDE_HOOK_SCRIPT_NAME = "mcp-bootstrap-reminder.sh"
_CLAUDE_MANAGED_MARKER = "query-mcp-managed:v1"
_CLAUDE_HOOK_COMMAND = (
    'bash "$CLAUDE_PROJECT_DIR/.claude/hooks/mcp-bootstrap-reminder.sh"'
)
_CLAUDE_HOOK_EVENTS = ("SessionStart", "UserPromptSubmit")
_CLAUDE_HOOK_SCRIPT_TEMPLATE = """#!/usr/bin/env bash
# {marker}
# 统一查询 MCP · Claude Code 接入强制提醒 hook（由 bind_project_context 自动初始化）。
# 被 SessionStart 与 UserPromptSubmit 复用；stdout 会被 Claude Code 作为附加上下文注入当前轮。
# 本文件由 MCP 自动维护：顶部 marker 在时会被刷新，删掉 marker 即视为用户接管、不再覆盖。
set -euo pipefail

cat <<'REMINDER'
[统一查询 MCP · 强制接入提醒]
当前仓库已接入统一查询 MCP，本轮开始执行前请按需确认：
1. 首轮先用 read_mcp_resource 读取 query://usage-guide 与对应 client-profile（已读过则复用，勿反复 list_mcp_resources）。
2. 凡涉及开发/实现/修改/写入/部署等改变项目状态的需求：先 bind_project_context(project_id, chat_session_id, root_goal) 记需求并建任务树；纯查询/解释型问题且清晰度>=3 可直接答，不必机械 bootstrap。
3. 进入执行：开始节点调 update_task_node_status，完成节点必须调 complete_task_node_with_verification 写验证结果——禁止只用自然语言宣布完成。
4. 默认项目 project_id={project_id}；并行 CLI 新任务请自生成唯一 chat_session_id。
5. 本地 canonical 状态只写 .ai-employee/query-mcp/active-sessions/<chat_session_id>.json、session-history/<project_id>__<chat_session_id>.json 与 requirements/<project_id>/<chat_session_id>.json。
REMINDER
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
    """Legacy project-level pointer path.

    Do not write this path for new state. A single project-level active file is
    last-write-wins and cannot represent multiple windows safely.
    """
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


def _claude_dir(project_id: str = "", workspace_path: str = "") -> Path | None:
    workspace_root, _scope = _resolve_local_workspace_context(project_id, workspace_path)
    if not workspace_root:
        return None
    return Path(workspace_root) / _CLAUDE_DIR


def _write_claude_hook_script(
    script_path: Path,
    project_id_value: str,
) -> bool:
    """写入/刷新 hook 脚本。返回是否发生写盘。

    幂等规则：文件不存在则写；存在且含受管 marker 则按需刷新；
    存在但无 marker 视为用户接管，保持不动。
    """
    desired = _CLAUDE_HOOK_SCRIPT_TEMPLATE.format(
        marker=_CLAUDE_MANAGED_MARKER,
        project_id=project_id_value or "<project_id>",
    )
    if script_path.exists():
        try:
            current = script_path.read_text(encoding="utf-8")
        except OSError:
            current = ""
        if _CLAUDE_MANAGED_MARKER not in current:
            return False
        if current == desired:
            return False
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(desired, encoding="utf-8")
    try:
        script_path.chmod(0o755)
    except OSError:
        pass
    return True


def _merge_claude_hook_settings(settings_path: Path) -> bool:
    """把两个 hook 事件并入 settings.json，保留用户已有键。返回是否写盘。"""
    data: dict[str, Any] = {}
    if settings_path.exists():
        try:
            loaded = json.loads(settings_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except (OSError, json.JSONDecodeError):
            # 不破坏无法解析的用户文件，交还给用户处理。
            return False
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        hooks = {}
    changed = False
    for event in _CLAUDE_HOOK_EVENTS:
        matchers = hooks.get(event)
        if not isinstance(matchers, list):
            matchers = []
        already = any(
            isinstance(group, dict)
            and any(
                isinstance(hook, dict) and hook.get("command") == _CLAUDE_HOOK_COMMAND
                for hook in (group.get("hooks") or [])
                if isinstance(hook, dict)
            )
            for group in matchers
        )
        if already:
            continue
        matchers.append(
            {"hooks": [{"type": "command", "command": _CLAUDE_HOOK_COMMAND}]}
        )
        hooks[event] = matchers
        changed = True
    if not changed:
        return False
    data["hooks"] = hooks
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return True


def ensure_claude_code_hooks(
    *,
    project_id: str,
    workspace_path: str = "",
) -> dict[str, Any]:
    """在客户端工作区初始化 Claude Code 的 MCP bootstrap 提醒 hook。

    与 ensure_query_mcp_workflow_skill 同属 bind 阶段本地落地，跨电脑可移植：
    路径全部相对客户端 workspace，命令用 $CLAUDE_PROJECT_DIR，不写死任何机器路径。
    """
    project_id_value = _normalize_text(project_id, 120)
    if not project_id_value:
        return {}
    claude_dir = _claude_dir(project_id_value, workspace_path)
    if claude_dir is None:
        return {}
    script_path = claude_dir / _CLAUDE_HOOKS_DIR / _CLAUDE_HOOK_SCRIPT_NAME
    settings_path = claude_dir / _CLAUDE_SETTINGS_FILE
    changed: list[str] = []
    if _write_claude_hook_script(script_path, project_id_value):
        changed.append(str(script_path))
    if _merge_claude_hook_settings(settings_path):
        changed.append(str(settings_path))
    return {
        "path": str(claude_dir),
        "script_path": str(script_path),
        "settings_path": str(settings_path),
        "events": list(_CLAUDE_HOOK_EVENTS),
        "changed": bool(changed),
        "changed_files": changed,
    }


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
    outbox_entries = _read_jsonl(_outbox_path(project_id_value, chat_session_id_value, workspace_path))
    normalized_sync_status = _normalize_text(sync_status, 40).lower()
    if not normalized_sync_status:
        if outbox_entries:
            normalized_sync_status = "pending"
        else:
            normalized_sync_status = _normalize_text(existing.get("sync_status"), 40).lower() or "idle"
    requirement_text = _normalize_text(root_goal, 2000) or _normalize_text(existing.get("requirement"), 2000)
    title = _summarize_text(requirement_text or existing.get("title"), 200)
    payload = {
        "record_type": "query-mcp-requirement",
        "version": 3,
        "project_id": project_id_value,
        "project_name": _normalize_text(project_name, 200)
        or _normalize_text(existing.get("project_name"), 200),
        "workspace_path": workspace_root or _normalize_text(existing.get("workspace_path"), 1000),
        "chat_session_id": chat_session_id_value,
        "session_id": _normalize_text(session_id, 200)
        or _normalize_text(existing.get("session_id"), 200),
        "title": title,
        "requirement": requirement_text,
        "root_goal": requirement_text,
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
    claude_hooks_payload = ensure_claude_code_hooks(
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
        "claude_hooks": claude_hooks_payload,
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

    active_payload = _load_latest_active_session(project_id_value, workspace_path)
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
        _load_latest_active_session(project_id_value, workspace_path),
        _load_latest_history_payload(project_id_value, workspace_path),
        _read_json(_active_state_path(project_id_value, workspace_path)),
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
    session_path = _session_state_path(project_id_value, chat_session_id_value, workspace_path)
    active_session_path = _active_session_path(chat_session_id_value, project_id_value, workspace_path)
    if session_path is None or active_session_path is None:
        return {}
    legacy_payload = _load_legacy_pointer_state(project_id_value, workspace_path)
    if not _payload_matches_chat_session(legacy_payload, chat_session_id_value):
        legacy_payload = {}
    existing = _merge_state_payloads(
        _read_json(active_session_path),
        _read_json(session_path),
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
