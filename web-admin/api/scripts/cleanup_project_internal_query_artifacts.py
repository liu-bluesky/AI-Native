"""Clean internal unified-query auto-capture artifacts for a project.

Usage:
    python scripts/cleanup_project_internal_query_artifacts.py --project-id proj-d16591a6
    python scripts/cleanup_project_internal_query_artifacts.py --project-id proj-d16591a6 --apply
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from psycopg import connect
from psycopg.rows import dict_row

API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from core.config import get_settings
from core.deps import project_store
from services.project_chat_task_tree import archive_task_tree, list_project_task_tree_summaries
from stores.factory import project_chat_task_store, work_session_store

_INTERNAL_TOOL_TAGS = {
    "mcp:tools/call:bind_project_context",
    "mcp:tools/call:search_ids",
    "mcp:tools/call:start_work_session",
    "mcp:tools/call:save_work_facts",
    "mcp:tools/call:append_session_event",
    "mcp:tools/call:resume_work_session",
    "mcp:tools/call:summarize_checkpoint",
    "mcp:tools/call:list_recent_project_requirements",
    "mcp:tools/call:get_requirement_history",
    "mcp:tools/call:build_delivery_report",
    "mcp:tools/call:generate_release_note_entry",
    "mcp:tools/call:save_project_memory",
}


@dataclass(frozen=True)
class InternalMemoryRow:
    id: str
    created_at: str
    employee_id: str
    chat_session_id: str
    capture_kind: str
    tool_tags: tuple[str, ...]
    content: str


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Delete internal unified-query auto-captured memories and archive their orphan task trees."
    )
    parser.add_argument("--project-id", required=True, help="Project ID.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the cleanup. Without this flag the script only prints the planned actions.",
    )
    parser.add_argument(
        "--hard-delete-shadow-query-cli",
        action="store_true",
        help=(
            "Hard-delete confirmed synthetic shadow task trees and related query-cli work-session events "
            "when an equivalent formal non-query-cli chain exists."
        ),
    )
    parser.add_argument(
        "--shadow-query-cli-only",
        action="store_true",
        help=(
            "Only plan/apply confirmed synthetic shadow-chain hard deletes. "
            "Skip generic internal memory cleanup and orphan task-tree archiving."
        ),
    )
    return parser.parse_args()


def _project_name_tokens(project_id: str) -> tuple[str, ...]:
    project = project_store.get(project_id)
    names = [str(project_id or "").strip()]
    if project is not None:
        names.append(str(getattr(project, "name", "") or "").strip())
    return tuple(item for item in names if item)


def _extract_chat_session_id(payload: dict) -> str:
    content = str(payload.get("content") or "")
    for line in content.splitlines():
        if line.startswith("[关联会话]"):
            return line.split("]", 1)[-1].strip()
    return ""


def _normalize_goal_key(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def _is_query_cli_chat_session_id(value: object) -> bool:
    return str(value or "").strip().lower().startswith("query-cli.")


def _is_shadow_task_chat_session_id(value: object) -> bool:
    normalized = str(value or "").strip().lower()
    return normalized.startswith("query-cli.") or normalized.startswith("ws_")


def _is_work_session_chat_session_id(value: object) -> bool:
    return str(value or "").strip().lower().startswith("ws_")


def _parse_timestamp(value: object) -> float | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    candidate = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _load_internal_memories(database_url: str, project_tokens: tuple[str, ...]) -> list[InternalMemoryRow]:
    if not project_tokens:
        return []
    conn = connect(database_url, autocommit=True, row_factory=dict_row)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, employee_id, created_at, payload
                FROM memories
                WHERE payload->>'project_name' = ANY(%s)
                  AND payload->>'type' = 'project-context'
                ORDER BY created_at DESC, id DESC
                """,
                (list(project_tokens),),
            )
            rows = cur.fetchall() or []
    finally:
        conn.close()

    items: list[InternalMemoryRow] = []
    for row in rows:
        payload = dict(row.get("payload") or {})
        tags = tuple(str(item or "").strip() for item in (payload.get("purpose_tags") or []) if str(item or "").strip())
        if "auto-capture" not in tags:
            continue
        capture_kind = ""
        if "user-question" in tags:
            capture_kind = "user-question"
        elif "query-result" in tags:
            capture_kind = "query-result"
        if not capture_kind:
            continue
        tool_tags = tuple(tag for tag in tags if tag in _INTERNAL_TOOL_TAGS)
        if not tool_tags:
            continue
        chat_session_id = _extract_chat_session_id(payload)
        items.append(
            InternalMemoryRow(
                id=str(row["id"]),
                created_at=str(row["created_at"]),
                employee_id=str(row["employee_id"]),
                chat_session_id=chat_session_id,
                capture_kind=capture_kind,
                tool_tags=tool_tags,
                content=str(payload.get("content") or ""),
            )
        )
    return items


def _task_done_leaf_total(session) -> int:
    total = 0
    for node in getattr(session, "nodes", []) or []:
        if int(getattr(node, "level", 0) or 0) <= 0:
            continue
        if str(getattr(node, "status", "") or "").strip() == "done":
            total += 1
    return total


def _select_orphan_task_sessions(project_id: str, chat_session_ids: set[str]) -> list:
    candidates = []
    for session in project_chat_task_store.list_by_project(project_id, limit=500):
        if str(getattr(session, "chat_session_id", "") or "").strip() not in chat_session_ids:
            continue
        if str(getattr(session, "lifecycle_status", "") or "").strip() != "active":
            continue
        if int(getattr(session, "progress_percent", 0) or 0) != 0:
            continue
        if _task_done_leaf_total(session) != 0:
            continue
        candidates.append(session)
    return candidates


def _summary_timestamp(item: dict[str, object]) -> float | None:
    return _parse_timestamp(item.get("updated_at")) or _parse_timestamp(item.get("created_at"))


def _select_shadow_query_cli_task_sessions(project_id: str) -> tuple[list[dict[str, object]], set[str]]:
    duplicate_window_seconds = 15 * 60
    grouped_by_goal: dict[str, list[dict[str, object]]] = {}
    for item in list_project_task_tree_summaries(project_id, 500):
        if not isinstance(item, dict):
            continue
        goal_key = _normalize_goal_key(item.get("root_goal") or item.get("title"))
        if not goal_key:
            continue
        grouped_by_goal.setdefault(goal_key, []).append(item)

    shadow_sessions: list[dict[str, object]] = []
    duplicate_goal_keys: set[str] = set()
    seen_ids: set[str] = set()
    for goal_key, grouped in grouped_by_goal.items():
        shadow_items = [item for item in grouped if _is_shadow_task_chat_session_id(item.get("chat_session_id"))]
        formal_items = [item for item in grouped if not _is_shadow_task_chat_session_id(item.get("chat_session_id"))]
        if not shadow_items or not formal_items:
            continue
        for shadow_item in shadow_items:
            shadow_id = str(shadow_item.get("id") or "").strip()
            shadow_chat_session_id = str(shadow_item.get("chat_session_id") or "").strip()
            shadow_username = str(shadow_item.get("username") or "").strip()
            shadow_timestamp = _summary_timestamp(shadow_item)
            if not shadow_id:
                continue
            for formal_item in formal_items:
                formal_username = str(formal_item.get("username") or "").strip()
                formal_timestamp = _summary_timestamp(formal_item)
                if shadow_username and formal_username and shadow_username != formal_username:
                    continue
                if _is_work_session_chat_session_id(shadow_chat_session_id):
                    pass
                else:
                    if shadow_timestamp is None or formal_timestamp is None:
                        continue
                    if abs(formal_timestamp - shadow_timestamp) > duplicate_window_seconds:
                        continue
                if shadow_id not in seen_ids:
                    shadow_sessions.append(shadow_item)
                    seen_ids.add(shadow_id)
                duplicate_goal_keys.add(goal_key)
                break
    return shadow_sessions, duplicate_goal_keys


def _select_shadow_query_cli_work_events(project_id: str, duplicate_goal_keys: set[str]) -> list:
    if not duplicate_goal_keys:
        return []
    matched = []
    for event in work_session_store.list_events(project_id=project_id, limit=500):
        task_tree_chat_session_id = str(getattr(event, "task_tree_chat_session_id", "") or "").strip()
        if not _is_query_cli_chat_session_id(task_tree_chat_session_id):
            continue
        if _normalize_goal_key(getattr(event, "goal", "")) not in duplicate_goal_keys:
            continue
        matched.append(event)
    return matched


def _print_plan(memories: list[InternalMemoryRow], task_sessions: list, shadow_task_sessions: list, shadow_work_events: list) -> None:
    print(f"internal_memory_count={len(memories)}")
    print(f"orphan_task_tree_count={len(task_sessions)}")
    print(f"shadow_query_cli_task_tree_count={len(shadow_task_sessions)}")
    print(f"shadow_query_cli_work_event_count={len(shadow_work_events)}")
    print("sample_internal_memories=")
    for item in memories[:10]:
        preview = item.content.replace("\n", " | ")[:180]
        print(
            json.dumps(
                {
                    "id": item.id,
                    "created_at": item.created_at,
                    "employee_id": item.employee_id,
                    "chat_session_id": item.chat_session_id,
                    "capture_kind": item.capture_kind,
                    "tool_tags": item.tool_tags,
                    "preview": preview,
                },
                ensure_ascii=False,
            )
        )
    print("sample_orphan_task_trees=")
    for session in task_sessions[:10]:
        print(
            json.dumps(
                {
                    "id": getattr(session, "id", ""),
                    "username": getattr(session, "username", ""),
                    "chat_session_id": getattr(session, "chat_session_id", ""),
                    "title": getattr(session, "title", ""),
                    "status": getattr(session, "status", ""),
                    "progress_percent": getattr(session, "progress_percent", 0),
                },
                ensure_ascii=False,
            )
        )
    print("sample_shadow_query_cli_task_trees=")
    for item in shadow_task_sessions[:10]:
        print(
            json.dumps(
                {
                    "id": item.get("id"),
                    "username": item.get("username"),
                    "chat_session_id": item.get("chat_session_id"),
                    "root_goal": item.get("root_goal"),
                    "lifecycle_status": item.get("lifecycle_status"),
                    "created_at": item.get("created_at"),
                    "updated_at": item.get("updated_at"),
                },
                ensure_ascii=False,
            )
        )
    print("sample_shadow_query_cli_work_events=")
    for event in shadow_work_events[:10]:
        print(
            json.dumps(
                {
                    "id": getattr(event, "id", ""),
                    "session_id": getattr(event, "session_id", ""),
                    "task_tree_session_id": getattr(event, "task_tree_session_id", ""),
                    "task_tree_chat_session_id": getattr(event, "task_tree_chat_session_id", ""),
                    "goal": getattr(event, "goal", ""),
                    "created_at": getattr(event, "created_at", ""),
                },
                ensure_ascii=False,
            )
        )


def _delete_memories(database_url: str, memory_ids: list[str]) -> int:
    if not memory_ids:
        return 0
    conn = connect(database_url, autocommit=True, row_factory=dict_row)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM memories WHERE id = ANY(%s)", (memory_ids,))
            return int(cur.rowcount or 0)
    finally:
        conn.close()


def _archive_task_sessions(task_sessions: list) -> int:
    archived = 0
    for session in task_sessions:
        archive_task_tree(
            session,
            reason="cleanup_internal_query_artifact",
            delete_current=True,
        )
        archived += 1
    return archived


def _hard_delete_task_sessions(task_sessions: list[dict[str, object]]) -> int:
    deleted = 0
    for item in task_sessions:
        project_id = str(item.get("project_id") or "").strip()
        username = str(item.get("username") or "").strip()
        chat_session_id = str(item.get("chat_session_id") or "").strip()
        if not (project_id and username and chat_session_id):
            continue
        deleted += int(project_chat_task_store.delete_exact(project_id, username, chat_session_id) or 0)
    return deleted


def _delete_work_session_events(database_url: str, event_ids: list[str]) -> int:
    normalized_ids = [str(item or "").strip() for item in event_ids if str(item or "").strip()]
    if not normalized_ids:
        return 0
    conn = connect(database_url, autocommit=True, row_factory=dict_row)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM work_session_events WHERE id = ANY(%s)", (normalized_ids,))
            return int(cur.rowcount or 0)
    finally:
        conn.close()


def main() -> int:
    args = _parse_args()
    settings = get_settings()
    if args.shadow_query_cli_only:
        args.hard_delete_shadow_query_cli = True
    project_tokens = _project_name_tokens(args.project_id)
    internal_memories: list[InternalMemoryRow] = []
    orphan_task_sessions: list = []
    if not args.shadow_query_cli_only:
        internal_memories = _load_internal_memories(settings.database_url, project_tokens)
        internal_chat_session_ids = {
            item.chat_session_id
            for item in internal_memories
            if item.chat_session_id
        }
        orphan_task_sessions = _select_orphan_task_sessions(args.project_id, internal_chat_session_ids)
    shadow_task_sessions: list[dict[str, object]] = []
    shadow_work_events = []
    if args.hard_delete_shadow_query_cli:
        shadow_task_sessions, duplicate_goal_keys = _select_shadow_query_cli_task_sessions(args.project_id)
        shadow_work_events = _select_shadow_query_cli_work_events(args.project_id, duplicate_goal_keys)

    _print_plan(internal_memories, orphan_task_sessions, shadow_task_sessions, shadow_work_events)
    if not args.apply:
        print("dry_run=true")
        return 0

    deleted = _delete_memories(settings.database_url, [item.id for item in internal_memories])
    archived = _archive_task_sessions(orphan_task_sessions)
    deleted_shadow_task_trees = 0
    deleted_shadow_work_events = 0
    if args.hard_delete_shadow_query_cli:
        deleted_shadow_task_trees = _hard_delete_task_sessions(shadow_task_sessions)
        deleted_shadow_work_events = _delete_work_session_events(
            settings.database_url,
            [getattr(event, "id", "") for event in shadow_work_events],
        )
    print("dry_run=false")
    print(f"deleted_memories={deleted}")
    print(f"archived_task_trees={archived}")
    print(f"deleted_shadow_query_cli_task_trees={deleted_shadow_task_trees}")
    print(f"deleted_shadow_query_cli_work_events={deleted_shadow_work_events}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
