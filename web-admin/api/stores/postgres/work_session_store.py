"""工作会话轨迹存储层（PostgreSQL 实现）"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict

from psycopg.rows import dict_row

from stores.postgres._connection import connect
from stores.json.work_session_store import WorkSessionEvent, _now_iso, _timestamp_for_sort


class WorkSessionStorePostgres:
    def __init__(self, database_url: str) -> None:
        self._conn = connect(database_url, autocommit=True, row_factory=dict_row)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS work_session_events (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    payload JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_work_session_events_project_session
                    ON work_session_events (project_id, session_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_work_session_events_session
                    ON work_session_events (session_id, updated_at DESC);
                """
            )

    def save(self, event: WorkSessionEvent) -> None:
        normalized = WorkSessionEvent(**asdict(event))
        if not normalized.created_at:
            normalized.created_at = _now_iso()
        normalized.updated_at = _now_iso()
        payload = json.dumps(asdict(normalized), ensure_ascii=False)
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO work_session_events (id, project_id, session_id, payload, updated_at)
                VALUES (%s, %s, %s, %s::jsonb, NOW())
                ON CONFLICT (id) DO UPDATE
                SET project_id = EXCLUDED.project_id,
                    session_id = EXCLUDED.session_id,
                    payload = EXCLUDED.payload,
                    updated_at = NOW()
                """,
                (normalized.id, normalized.project_id, normalized.session_id, payload),
            )

    def get(self, event_id: str) -> WorkSessionEvent | None:
        normalized_id = str(event_id or "").strip()
        with self._conn.cursor() as cur:
            cur.execute("SELECT payload FROM work_session_events WHERE id = %s", (normalized_id,))
            row = cur.fetchone()
        if row is None:
            return None
        return WorkSessionEvent(**row["payload"])

    def list_all(self) -> list[WorkSessionEvent]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT payload FROM work_session_events")
            rows = cur.fetchall()
        items = [WorkSessionEvent(**row["payload"]) for row in rows]
        items.sort(key=lambda item: (_timestamp_for_sort(item.created_at), item.id), reverse=True)
        return items

    def list_events(
        self,
        *,
        project_id: str = "",
        employee_id: str = "",
        session_id: str = "",
        task_tree_session_id: str = "",
        task_tree_chat_session_id: str = "",
        task_node_id: str = "",
        query: str = "",
        limit: int = 200,
    ) -> list[WorkSessionEvent]:
        normalized_project_id = str(project_id or "").strip()
        normalized_employee_id = str(employee_id or "").strip()
        normalized_session_id = str(session_id or "").strip()
        normalized_task_tree_session_id = str(task_tree_session_id or "").strip()
        normalized_task_tree_chat_session_id = str(task_tree_chat_session_id or "").strip()
        normalized_task_node_id = str(task_node_id or "").strip()
        keyword = str(query or "").strip().lower()
        try:
            limit_value = max(1, min(int(limit or 200), 500))
        except (TypeError, ValueError):
            limit_value = 200
        items: list[WorkSessionEvent] = []
        for item in self.list_all():
            if normalized_project_id and item.project_id != normalized_project_id:
                continue
            if normalized_employee_id and item.employee_id != normalized_employee_id:
                continue
            if normalized_session_id and item.session_id != normalized_session_id:
                continue
            if normalized_task_tree_session_id and item.task_tree_session_id != normalized_task_tree_session_id:
                continue
            if (
                normalized_task_tree_chat_session_id
                and item.task_tree_chat_session_id != normalized_task_tree_chat_session_id
            ):
                continue
            if normalized_task_node_id and item.task_node_id != normalized_task_node_id:
                continue
            if keyword:
                haystack = "\n".join(
                    [
                        item.project_name,
                        item.employee_id,
                        item.session_id,
                        item.task_tree_session_id,
                        item.task_tree_chat_session_id,
                        item.task_node_id,
                        item.task_node_title,
                        item.source_kind,
                        item.event_type,
                        item.phase,
                        item.step,
                        item.status,
                        item.goal,
                        item.content,
                        *item.facts,
                        *item.changed_files,
                        *item.verification,
                        *item.risks,
                        *item.next_steps,
                    ]
                ).lower()
                if keyword not in haystack:
                    continue
            items.append(item)
            if len(items) >= limit_value:
                break
        return items

    def delete_by_session(self, session_id: str, *, project_id: str = "") -> int:
        normalized_session_id = str(session_id or "").strip()
        normalized_project_id = str(project_id or "").strip()
        with self._conn.cursor() as cur:
            if normalized_project_id:
                cur.execute(
                    "DELETE FROM work_session_events WHERE session_id = %s AND project_id = %s",
                    (normalized_session_id, normalized_project_id),
                )
            else:
                cur.execute(
                    "DELETE FROM work_session_events WHERE session_id = %s",
                    (normalized_session_id,),
                )
            return cur.rowcount

    def new_id(self) -> str:
        return f"wse-{uuid.uuid4().hex[:8]}"
