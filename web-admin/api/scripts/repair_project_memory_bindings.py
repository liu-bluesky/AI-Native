"""Backfill explicit project binding for legacy project memories.

This script repairs old `project-context` memory rows that were saved before
explicit `project-id:<id>` tagging and `[项目ID]/[项目名称]` content binding were
added. It uses task-tree and work-session trace fields to conservatively infer
the owning project, then updates the memory payload in place.

Usage:
    python scripts/repair_project_memory_bindings.py
    python scripts/repair_project_memory_bindings.py --project-id proj-657fe77f
    python scripts/repair_project_memory_bindings.py --project-id proj-657fe77f --apply
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from psycopg import connect
from psycopg.rows import dict_row

API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from core.config import get_settings
from core.deps import project_store, work_session_store
from stores.factory import project_chat_task_store


def _normalize_text(value: Any, *, limit: int = 4000) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()[:limit]


def _extract_section(content: Any, label: str, *, limit: int = 400) -> str:
    text = _normalize_text(content)
    if not text or not label:
        return ""
    matched = re.search(rf"\[{re.escape(label)}\]\s*([^\n]+)", text)
    if not matched:
        return ""
    return _normalize_text(matched.group(1), limit=limit)


def _extract_inline_binding(content: Any, key: str, *, limit: int = 120) -> str:
    text = _normalize_text(content)
    normalized_key = str(key or "").strip()
    if not text or not normalized_key:
        return ""
    patterns = (
        rf"(?:^|[\s,;]){re.escape(normalized_key)}=([A-Za-z0-9_.:-]+)",
        rf'"{re.escape(normalized_key)}"\s*:\s*"([^"]+)"',
    )
    for pattern in patterns:
        matched = re.search(pattern, text)
        if matched:
            return _normalize_text(matched.group(1), limit=limit)
    return ""


def _extract_tag_binding(purpose_tags: Any, prefix: str, *, limit: int = 120) -> str:
    normalized_prefix = str(prefix or "").strip().lower()
    if not normalized_prefix:
        return ""
    for item in purpose_tags or ():
        tag = str(item or "").strip()
        if tag and tag.lower().startswith(normalized_prefix):
            return _normalize_text(tag[len(prefix):], limit=limit)
    return ""


def _parse_memory_binding(content: Any, purpose_tags: Any = ()) -> dict[str, str]:
    text = _normalize_text(content)
    result = {
        "project_id": _extract_section(text, "项目ID", limit=120)
        or _extract_tag_binding(purpose_tags, "project-id:", limit=120)
        or _extract_inline_binding(text, "project_id", limit=120),
        "project_name": _extract_section(text, "项目名称", limit=160)
        or _extract_inline_binding(text, "project_name", limit=160),
        "chat_session_id": _extract_section(text, "关联会话", limit=120)
        or _extract_tag_binding(purpose_tags, "chat-session:", limit=120)
        or _extract_inline_binding(text, "chat_session_id", limit=120),
        "task_tree_session_id": _extract_inline_binding(text, "task_tree_session_id", limit=80),
        "task_tree_chat_session_id": _extract_inline_binding(text, "task_tree_chat_session_id", limit=80),
        "session_id": _extract_inline_binding(text, "session_id", limit=120),
    }
    matched = re.search(r"\[执行轨迹JSON\]\s*([^\n]+)", text)
    if matched:
        try:
            payload = json.loads(str(matched.group(1) or "").strip())
        except json.JSONDecodeError:
            payload = {}
        if isinstance(payload, dict):
            result.update(
                {
                    "project_id": _normalize_text(payload.get("project_id") or result.get("project_id"), limit=120),
                    "project_name": _normalize_text(
                        payload.get("project_name") or result.get("project_name"),
                        limit=160,
                    ),
                    "chat_session_id": _normalize_text(
                        payload.get("chat_session_id") or result.get("chat_session_id"),
                        limit=120,
                    ),
                    "task_tree_session_id": _normalize_text(
                        payload.get("task_tree_session_id") or payload.get("id") or result.get("task_tree_session_id"),
                        limit=80,
                    ),
                    "task_tree_chat_session_id": _normalize_text(
                        payload.get("task_tree_chat_session_id")
                        or payload.get("source_chat_session_id")
                        or payload.get("chat_session_id")
                        or result.get("task_tree_chat_session_id"),
                        limit=80,
                    ),
                    "session_id": _normalize_text(payload.get("session_id") or result.get("session_id"), limit=120),
                }
            )
    return {key: value for key, value in result.items() if value}


def _upsert_section(text: str, label: str, value: str) -> str:
    content = _normalize_text(text, limit=12000)
    replacement = f"[{label}] {value}"
    pattern = rf"(^|\n)\[{re.escape(label)}\]\s*[^\n]*"
    if re.search(pattern, content):
        return re.sub(pattern, lambda match: f"{match.group(1)}{replacement}", content, count=1)
    if not content:
        return replacement
    return f"{content}\n{replacement}"


def _bind_project_content(content: str, project_id: str, project_name: str) -> str:
    updated = _normalize_text(content, limit=12000)
    if project_id:
        updated = _upsert_section(updated, "项目ID", project_id)
    if project_name:
        updated = _upsert_section(updated, "项目名称", project_name)
    return updated


def _with_project_tag(purpose_tags: Any, project_id: str) -> list[str]:
    tags = [str(item or "").strip() for item in (purpose_tags or []) if str(item or "").strip()]
    if any(tag.lower().startswith("project-id:") for tag in tags):
        return tags
    tags.append(f"project-id:{project_id}")
    return tags


def _register_unique(index: dict[str, str | None], key: str, project_id: str) -> None:
    normalized_key = _normalize_text(key, limit=120)
    normalized_project_id = _normalize_text(project_id, limit=120)
    if not normalized_key or not normalized_project_id:
        return
    existing = index.get(normalized_key)
    if existing is None and normalized_key in index:
        return
    if existing and existing != normalized_project_id:
        index[normalized_key] = None
        return
    index[normalized_key] = normalized_project_id


@dataclass(frozen=True)
class MemoryRow:
    id: str
    employee_id: str
    created_at: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class TraceIndex:
    project_names: dict[str, str]
    task_session_projects: dict[str, str | None]
    chat_session_projects: dict[str, str | None]
    work_session_projects: dict[str, str | None]


@dataclass(frozen=True)
class RepairPlan:
    memory_id: str
    employee_id: str
    created_at: str
    from_project_name: str
    resolved_project_id: str
    resolved_project_name: str
    matched_sources: tuple[str, ...]
    changed_fields: tuple[str, ...]
    updated_payload: dict[str, Any]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill explicit project binding for legacy project-context memories. "
            "By default this only prints the planned updates."
        )
    )
    parser.add_argument(
        "--project-id",
        default="",
        help="Only apply repairs whose resolved owner project matches this project ID.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the repair. Without this flag the script only prints the plan.",
    )
    return parser.parse_args()


def _load_memory_rows(database_url: str) -> list[MemoryRow]:
    conn = connect(database_url, autocommit=True, row_factory=dict_row)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, employee_id, created_at, payload
                FROM memories
                WHERE payload->>'type' = 'project-context'
                ORDER BY created_at DESC, id DESC
                """
            )
            rows = cur.fetchall() or []
    finally:
        conn.close()
    return [
        MemoryRow(
            id=str(row["id"]),
            employee_id=str(row["employee_id"]),
            created_at=str(row["created_at"]),
            payload=dict(row.get("payload") or {}),
        )
        for row in rows
    ]


def _build_trace_index() -> TraceIndex:
    project_names: dict[str, str] = {}
    task_session_projects: dict[str, str | None] = {}
    chat_session_projects: dict[str, str | None] = {}
    work_session_projects: dict[str, str | None] = {}

    for project in project_store.list_all() or []:
        project_id = _normalize_text(getattr(project, "id", ""), limit=120)
        if not project_id:
            continue
        project_names[project_id] = _normalize_text(getattr(project, "name", ""), limit=160) or project_id
        for session in project_chat_task_store.list_by_project(project_id, limit=2000) or []:
            _register_unique(task_session_projects, getattr(session, "id", ""), project_id)
            _register_unique(chat_session_projects, getattr(session, "chat_session_id", ""), project_id)
            _register_unique(chat_session_projects, getattr(session, "source_chat_session_id", ""), project_id)
            _register_unique(work_session_projects, getattr(session, "source_session_id", ""), project_id)

    list_all_work = getattr(work_session_store, "list_all", None)
    work_items = list_all_work() if callable(list_all_work) else work_session_store.list_events(limit=2000)
    for item in work_items or []:
        project_id = _normalize_text(getattr(item, "project_id", ""), limit=120)
        if not project_id:
            continue
        _register_unique(work_session_projects, getattr(item, "session_id", ""), project_id)
        _register_unique(task_session_projects, getattr(item, "task_tree_session_id", ""), project_id)
        _register_unique(chat_session_projects, getattr(item, "task_tree_chat_session_id", ""), project_id)

    return TraceIndex(
        project_names=project_names,
        task_session_projects=task_session_projects,
        chat_session_projects=chat_session_projects,
        work_session_projects=work_session_projects,
    )


def _resolve_project_from_binding(binding: dict[str, str], trace_index: TraceIndex) -> tuple[str, tuple[str, ...], str]:
    strong_hits: list[tuple[str, str]] = []
    medium_hits: list[tuple[str, str]] = []
    ambiguous_sources: list[str] = []
    checks = (
        ("task_tree_session_id", trace_index.task_session_projects, "strong"),
        ("session_id", trace_index.work_session_projects, "strong"),
        ("task_tree_chat_session_id", trace_index.chat_session_projects, "medium"),
        ("chat_session_id", trace_index.chat_session_projects, "medium"),
    )
    for source, index, strength in checks:
        value = _normalize_text(binding.get(source), limit=120)
        if not value:
            continue
        if value not in index:
            continue
        project_id = index.get(value)
        if project_id is None:
            ambiguous_sources.append(source)
            continue
        hit = (source, project_id)
        if strength == "strong":
            strong_hits.append(hit)
        else:
            medium_hits.append(hit)

    if strong_hits:
        strong_project_ids = {project_id for _, project_id in strong_hits}
        if len(strong_project_ids) != 1:
            return "", (), "conflicting-strong-signals"
        resolved_project_id = next(iter(strong_project_ids))
        medium_conflicts = {project_id for _, project_id in medium_hits if project_id != resolved_project_id}
        if medium_conflicts:
            return "", (), "conflicting-chat-signals"
        matched_sources = tuple(source for source, _ in [*strong_hits, *medium_hits])
        return resolved_project_id, matched_sources, "repairable"

    if medium_hits:
        medium_project_ids = {project_id for _, project_id in medium_hits}
        if len(medium_project_ids) != 1:
            return "", (), "conflicting-chat-signals"
        matched_sources = tuple(source for source, _ in medium_hits)
        return next(iter(medium_project_ids)), matched_sources, "repairable"

    if ambiguous_sources:
        return "", (), "ambiguous-session-signal"
    return "", (), "no-trace-match"


def _plan_memory_repair(
    row: MemoryRow,
    trace_index: TraceIndex,
    *,
    target_project_id: str = "",
) -> tuple[RepairPlan | None, str]:
    payload = dict(row.payload or {})
    binding = _parse_memory_binding(payload.get("content") or "", payload.get("purpose_tags") or ())
    if binding.get("project_id"):
        return None, "explicit-project-id"

    resolved_project_id, matched_sources, reason = _resolve_project_from_binding(binding, trace_index)
    if not resolved_project_id:
        return None, reason
    if target_project_id and resolved_project_id != target_project_id:
        return None, "target-project-mismatch"

    resolved_project_name = _normalize_text(
        trace_index.project_names.get(resolved_project_id) or payload.get("project_name") or resolved_project_id,
        limit=160,
    )
    updated_payload = dict(payload)
    changed_fields: list[str] = []

    if _normalize_text(payload.get("project_name"), limit=160) != resolved_project_name:
        updated_payload["project_name"] = resolved_project_name
        changed_fields.append("project_name")

    updated_content = _bind_project_content(
        str(payload.get("content") or ""),
        resolved_project_id,
        resolved_project_name,
    )
    if updated_content != str(payload.get("content") or ""):
        updated_payload["content"] = updated_content
        changed_fields.append("content")

    updated_tags = _with_project_tag(payload.get("purpose_tags") or [], resolved_project_id)
    if updated_tags != list(payload.get("purpose_tags") or []):
        updated_payload["purpose_tags"] = updated_tags
        changed_fields.append("purpose_tags")

    if not changed_fields:
        return None, "already-consistent"

    return (
        RepairPlan(
            memory_id=row.id,
            employee_id=row.employee_id,
            created_at=row.created_at,
            from_project_name=_normalize_text(payload.get("project_name"), limit=160),
            resolved_project_id=resolved_project_id,
            resolved_project_name=resolved_project_name,
            matched_sources=matched_sources,
            changed_fields=tuple(changed_fields),
            updated_payload=updated_payload,
        ),
        "repairable",
    )


def _plan_repairs(
    rows: list[MemoryRow],
    trace_index: TraceIndex,
    *,
    target_project_id: str = "",
) -> tuple[list[RepairPlan], Counter]:
    plans: list[RepairPlan] = []
    reason_counts: Counter = Counter()
    for row in rows:
        plan, reason = _plan_memory_repair(row, trace_index, target_project_id=target_project_id)
        reason_counts[reason] += 1
        if plan is not None:
            plans.append(plan)
    return plans, reason_counts


def _print_plan(plans: list[RepairPlan], reason_counts: Counter, *, scanned_rows: int, target_project_id: str) -> None:
    print(f"scanned_rows={scanned_rows}")
    print(f"repairable_rows={len(plans)}")
    print(f"target_project_id={target_project_id or '*'}")
    print("reason_counts=" + json.dumps(dict(sorted(reason_counts.items())), ensure_ascii=False, sort_keys=True))
    print("sample_repairs=")
    for item in plans[:20]:
        print(
            json.dumps(
                {
                    "memory_id": item.memory_id,
                    "employee_id": item.employee_id,
                    "created_at": item.created_at,
                    "from_project_name": item.from_project_name,
                    "resolved_project_id": item.resolved_project_id,
                    "resolved_project_name": item.resolved_project_name,
                    "matched_sources": item.matched_sources,
                    "changed_fields": item.changed_fields,
                },
                ensure_ascii=False,
            )
        )


def _apply_repairs(database_url: str, plans: list[RepairPlan]) -> int:
    if not plans:
        return 0
    conn = connect(database_url, autocommit=True, row_factory=dict_row)
    updated = 0
    try:
        with conn.cursor() as cur:
            for plan in plans:
                cur.execute(
                    """
                    UPDATE memories
                    SET payload = %s::jsonb
                    WHERE id = %s
                    """,
                    (json.dumps(plan.updated_payload, ensure_ascii=False), plan.memory_id),
                )
                updated += int(cur.rowcount or 0)
    finally:
        conn.close()
    return updated


def main() -> int:
    args = _parse_args()
    settings = get_settings()
    target_project_id = _normalize_text(args.project_id, limit=120)
    rows = _load_memory_rows(settings.database_url)
    trace_index = _build_trace_index()
    plans, reason_counts = _plan_repairs(rows, trace_index, target_project_id=target_project_id)
    _print_plan(plans, reason_counts, scanned_rows=len(rows), target_project_id=target_project_id)
    if not args.apply:
        print("dry_run=true")
        return 0
    updated = _apply_repairs(settings.database_url, plans)
    print("dry_run=false")
    print(f"updated={updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
