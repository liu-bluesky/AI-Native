"""Clean internal unified-query auto-capture artifacts for a project.

Usage:
    python scripts/cleanup_project_internal_query_artifacts.py --project-id proj-d16591a6
    python scripts/cleanup_project_internal_query_artifacts.py --project-id proj-d16591a6 --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from psycopg import connect
from psycopg.rows import dict_row

API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from core.config import get_settings
from core.deps import project_store
from services.project_chat_task_tree import archive_task_tree
from stores.factory import project_chat_task_store

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


def _print_plan(memories: list[InternalMemoryRow], task_sessions: list) -> None:
    print(f"internal_memory_count={len(memories)}")
    print(f"orphan_task_tree_count={len(task_sessions)}")
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


def main() -> int:
    args = _parse_args()
    settings = get_settings()
    project_tokens = _project_name_tokens(args.project_id)
    internal_memories = _load_internal_memories(settings.database_url, project_tokens)
    internal_chat_session_ids = {
        item.chat_session_id
        for item in internal_memories
        if item.chat_session_id
    }
    orphan_task_sessions = _select_orphan_task_sessions(args.project_id, internal_chat_session_ids)

    _print_plan(internal_memories, orphan_task_sessions)
    if not args.apply:
        print("dry_run=true")
        return 0

    deleted = _delete_memories(settings.database_url, [item.id for item in internal_memories])
    archived = _archive_task_sessions(orphan_task_sessions)
    print("dry_run=false")
    print(f"deleted_memories={deleted}")
    print(f"archived_task_trees={archived}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
