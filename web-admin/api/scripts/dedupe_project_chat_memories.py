"""Deduplicate project-chat auto-captured memories that were fanned out per employee.

Usage:
    python scripts/dedupe_project_chat_memories.py --project-name "ai设计规范"
    python scripts/dedupe_project_chat_memories.py --project-name "ai设计规范" --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from psycopg import connect
from psycopg.rows import dict_row

API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from core.config import get_settings


@dataclass(frozen=True)
class MemoryRow:
    id: str
    employee_id: str
    created_at: datetime
    payload: dict

    @property
    def project_name(self) -> str:
        return str(self.payload.get("project_name") or "").strip()

    @property
    def content(self) -> str:
        return str(self.payload.get("content") or "")

    @property
    def scope(self) -> str:
        return str(self.payload.get("scope") or "").strip()

    @property
    def purpose_tags(self) -> tuple[str, ...]:
        raw = self.payload.get("purpose_tags") or []
        return tuple(str(item or "").strip() for item in raw if str(item or "").strip())


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Deduplicate fanned-out project-chat memories for a project."
    )
    parser.add_argument("--project-name", required=True, help="Project name stored in memory payload.")
    parser.add_argument(
        "--window-seconds",
        type=float,
        default=5.0,
        help="Time window used to cluster identical fan-out copies. Default: 5 seconds.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the cleanup. Without this flag the script only prints the planned actions.",
    )
    return parser.parse_args()


def _load_candidate_rows(database_url: str, project_name: str) -> list[MemoryRow]:
    conn = connect(database_url, autocommit=True, row_factory=dict_row)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, employee_id, created_at, payload
                FROM memories
                WHERE payload->>'project_name' = %s
                  AND payload->>'type' = 'project-context'
                  AND payload->>'scope' = 'employee-private'
                  AND payload->'purpose_tags' ? 'auto-capture'
                  AND payload->'purpose_tags' ? 'project-chat'
                ORDER BY payload->>'content', created_at ASC, id ASC
                """,
                (project_name,),
            )
            return [
                MemoryRow(
                    id=str(row["id"]),
                    employee_id=str(row["employee_id"]),
                    created_at=row["created_at"],
                    payload=dict(row["payload"] or {}),
                )
                for row in cur.fetchall()
            ]
    finally:
        conn.close()


def _group_duplicate_clusters(rows: list[MemoryRow], window_seconds: float) -> list[list[MemoryRow]]:
    by_content: dict[str, list[MemoryRow]] = defaultdict(list)
    for row in rows:
        by_content[row.content].append(row)

    clusters: list[list[MemoryRow]] = []
    for same_content_rows in by_content.values():
        current: list[MemoryRow] = []
        for row in same_content_rows:
            if not current:
                current = [row]
                continue
            delta = (row.created_at - current[-1].created_at).total_seconds()
            if delta <= window_seconds:
                current.append(row)
                continue
            if len(current) > 1 and len({item.employee_id for item in current}) > 1:
                clusters.append(current)
            current = [row]
        if len(current) > 1 and len({item.employee_id for item in current}) > 1:
            clusters.append(current)
    return clusters


def _print_plan(clusters: list[list[MemoryRow]]) -> None:
    print(f"duplicate_clusters={len(clusters)}")
    print(f"duplicate_rows={sum(len(cluster) for cluster in clusters)}")
    for cluster in clusters:
        keep = cluster[0]
        delete_rows = cluster[1:]
        print("---")
        print(f"keep={keep.id} employee={keep.employee_id} created_at={keep.created_at.isoformat()}")
        print("delete=" + ",".join(row.id for row in delete_rows))
        print("employees=" + ",".join(row.employee_id for row in cluster))
        print("content=" + repr(keep.content[:180]))


def _apply_cleanup(database_url: str, clusters: list[list[MemoryRow]]) -> tuple[int, int]:
    conn = connect(database_url, autocommit=True, row_factory=dict_row)
    updated = 0
    deleted = 0
    try:
        with conn.cursor() as cur:
            for cluster in clusters:
                keep = cluster[0]
                delete_rows = cluster[1:]
                new_payload = dict(keep.payload)
                new_payload["scope"] = "team-shared"
                cur.execute(
                    """
                    UPDATE memories
                    SET payload = %s::jsonb
                    WHERE id = %s
                    """,
                    (json.dumps(new_payload, ensure_ascii=False), keep.id),
                )
                updated += cur.rowcount
                if delete_rows:
                    cur.execute(
                        "DELETE FROM memories WHERE id = ANY(%s)",
                        ([row.id for row in delete_rows],),
                    )
                    deleted += cur.rowcount
        return updated, deleted
    finally:
        conn.close()


def main() -> int:
    args = _parse_args()
    settings = get_settings()
    rows = _load_candidate_rows(settings.database_url, args.project_name)
    clusters = _group_duplicate_clusters(rows, args.window_seconds)
    _print_plan(clusters)
    if not args.apply:
        print("dry_run=true")
        return 0
    updated, deleted = _apply_cleanup(settings.database_url, clusters)
    print("dry_run=false")
    print(f"updated={updated}")
    print(f"deleted={deleted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
