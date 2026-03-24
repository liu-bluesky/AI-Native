"""Feedback upgrade storage (PostgreSQL only)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from stores.postgres._connection import connect
from psycopg.rows import dict_row


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_dumps(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False)


class FeedbackStorePostgres:
    def __init__(self, database_url: str) -> None:
        self._conn = connect(database_url, autocommit=True, row_factory=dict_row)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS feedback_bugs (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    employee_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    payload JSONB NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_feedback_bugs_project_status_created
                ON feedback_bugs (project_id, status, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_feedback_bugs_project_employee
                ON feedback_bugs (project_id, employee_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS feedback_analyses (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    feedback_id TEXT NOT NULL,
                    confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
                    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    payload JSONB NOT NULL,
                    UNIQUE (project_id, feedback_id)
                );
                CREATE INDEX IF NOT EXISTS idx_feedback_analyses_project_feedback
                ON feedback_analyses (project_id, feedback_id);

                CREATE TABLE IF NOT EXISTS feedback_candidates (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    feedback_id TEXT NOT NULL,
                    employee_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    payload JSONB NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_feedback_candidates_project_status_created
                ON feedback_candidates (project_id, status, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_feedback_candidates_project_feedback
                ON feedback_candidates (project_id, feedback_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_feedback_candidates_project_employee
                ON feedback_candidates (project_id, employee_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS feedback_reviews (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    feedback_id TEXT NOT NULL,
                    candidate_id TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    payload JSONB NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_feedback_reviews_project_feedback
                ON feedback_reviews (project_id, feedback_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_feedback_reviews_project_candidate
                ON feedback_reviews (project_id, candidate_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS feedback_project_configs (
                    project_id TEXT PRIMARY KEY,
                    enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )

    @staticmethod
    def _new_id(prefix: str) -> str:
        return f"{prefix}-{uuid.uuid4().hex[:8]}"

    def new_bug_id(self) -> str:
        return self._new_id("fbug")

    def new_analysis_id(self) -> str:
        return self._new_id("fana")

    def new_candidate_id(self) -> str:
        return self._new_id("fcand")

    def new_review_id(self) -> str:
        return self._new_id("frev")

    def get_project_config(self, project_id: str) -> dict[str, Any]:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT project_id, enabled, updated_at
                FROM feedback_project_configs
                WHERE project_id = %s
                """,
                (project_id,),
            )
            row = cur.fetchone()
        if row is None:
            return {"project_id": project_id, "enabled": True, "updated_at": ""}
        return {
            "project_id": row["project_id"],
            "enabled": bool(row["enabled"]),
            "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else "",
        }

    def update_project_config(self, project_id: str, enabled: bool) -> dict[str, Any]:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO feedback_project_configs (project_id, enabled, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (project_id) DO UPDATE
                SET enabled = EXCLUDED.enabled, updated_at = NOW()
                """,
                (project_id, enabled),
            )
        return self.get_project_config(project_id)

    def save_bug(self, bug: dict[str, Any]) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO feedback_bugs (id, project_id, employee_id, status, severity, created_at, updated_at, payload)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (id) DO UPDATE
                SET project_id = EXCLUDED.project_id,
                    employee_id = EXCLUDED.employee_id,
                    status = EXCLUDED.status,
                    severity = EXCLUDED.severity,
                    created_at = EXCLUDED.created_at,
                    updated_at = EXCLUDED.updated_at,
                    payload = EXCLUDED.payload
                """,
                (
                    bug["id"],
                    bug["project_id"],
                    bug["employee_id"],
                    bug["status"],
                    bug["severity"],
                    bug["created_at"],
                    bug["updated_at"],
                    _json_dumps(bug),
                ),
            )

    def create_bug(self, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = _now_iso()
        bug = {
            "id": self.new_bug_id(),
            "project_id": project_id,
            "employee_id": str(payload.get("employee_id") or "").strip(),
            "category": str(payload.get("category") or "general").strip() or "general",
            "session_id": str(payload.get("session_id") or "").strip(),
            "rule_id": str(payload.get("rule_id") or "").strip(),
            "title": str(payload.get("title") or "").strip(),
            "symptom": str(payload.get("symptom") or "").strip(),
            "expected": str(payload.get("expected") or "").strip(),
            "severity": str(payload.get("severity") or "medium").strip().lower(),
            "reporter": str(payload.get("reporter") or "").strip(),
            "status": "new",
            "source_context": payload.get("source_context") or {},
            "created_at": now,
            "updated_at": now,
        }
        self.save_bug(bug)
        return bug

    def get_bug(self, project_id: str, feedback_id: str) -> dict[str, Any] | None:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT payload FROM feedback_bugs WHERE project_id = %s AND id = %s",
                (project_id, feedback_id),
            )
            row = cur.fetchone()
        return row["payload"] if row else None

    def patch_bug(self, project_id: str, feedback_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        bug = self.get_bug(project_id, feedback_id)
        if bug is None:
            return None
        bug.update(updates)
        bug["updated_at"] = _now_iso()
        self.save_bug(bug)
        return bug

    def list_bugs(
        self,
        project_id: str,
        employee_id: str = "",
        category: str = "",
        rule_id: str = "",
        status: str = "",
        severity: str = "",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        sql = "SELECT payload FROM feedback_bugs WHERE project_id = %s"
        params: list[Any] = [project_id]
        if employee_id:
            sql += " AND employee_id = %s"
            params.append(employee_id)
        if category:
            sql += " AND COALESCE(payload->>'category', '') = %s"
            params.append(category)
        if rule_id:
            sql += " AND COALESCE(payload->>'rule_id', '') = %s"
            params.append(rule_id)
        if status:
            sql += " AND status = %s"
            params.append(status)
        if severity:
            sql += " AND severity = %s"
            params.append(severity)
        sql += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        with self._conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
        return [r["payload"] for r in rows]

    def delete_bug(self, project_id: str, feedback_id: str) -> dict[str, Any]:
        result = {
            "deleted_bug": False,
            "deleted_analysis_count": 0,
            "deleted_candidate_count": 0,
            "deleted_review_count": 0,
        }
        with self._conn.transaction():
            with self._conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM feedback_reviews WHERE project_id = %s AND feedback_id = %s",
                    (project_id, feedback_id),
                )
                result["deleted_review_count"] = int(cur.rowcount or 0)

                cur.execute(
                    "DELETE FROM feedback_candidates WHERE project_id = %s AND feedback_id = %s",
                    (project_id, feedback_id),
                )
                result["deleted_candidate_count"] = int(cur.rowcount or 0)

                cur.execute(
                    "DELETE FROM feedback_analyses WHERE project_id = %s AND feedback_id = %s",
                    (project_id, feedback_id),
                )
                result["deleted_analysis_count"] = int(cur.rowcount or 0)

                cur.execute(
                    "DELETE FROM feedback_bugs WHERE project_id = %s AND id = %s",
                    (project_id, feedback_id),
                )
                result["deleted_bug"] = bool(cur.rowcount and cur.rowcount > 0)
        return result

    def save_analysis(self, analysis: dict[str, Any]) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO feedback_analyses (id, project_id, feedback_id, confidence, generated_at, payload)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (project_id, feedback_id) DO UPDATE
                SET id = EXCLUDED.id,
                    confidence = EXCLUDED.confidence,
                    generated_at = EXCLUDED.generated_at,
                    payload = EXCLUDED.payload
                """,
                (
                    analysis["id"],
                    analysis["project_id"],
                    analysis["feedback_id"],
                    float(analysis.get("confidence") or 0),
                    analysis["generated_at"],
                    _json_dumps(analysis),
                ),
            )

    def upsert_analysis(self, project_id: str, feedback_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = _now_iso()
        existing = self.get_analysis(project_id, feedback_id)
        analysis = {
            "id": existing["id"] if existing else self.new_analysis_id(),
            "project_id": project_id,
            "feedback_id": feedback_id,
            "bug_type": str(payload.get("bug_type") or "rule_mismatch"),
            "direct_cause": str(payload.get("direct_cause") or ""),
            "root_cause": str(payload.get("root_cause") or ""),
            "evidence_refs": payload.get("evidence_refs") or [],
            "confidence": float(payload.get("confidence") or 0),
            "provider_id": str(payload.get("provider_id") or ""),
            "model_name": str(payload.get("model_name") or "heuristic-reflector"),
            "reflection_output": payload.get("reflection_output") or {},
            "generated_at": now,
        }
        self.save_analysis(analysis)
        return analysis

    def get_analysis(self, project_id: str, feedback_id: str) -> dict[str, Any] | None:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT payload FROM feedback_analyses WHERE project_id = %s AND feedback_id = %s",
                (project_id, feedback_id),
            )
            row = cur.fetchone()
        return row["payload"] if row else None

    def save_candidate(self, candidate: dict[str, Any]) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO feedback_candidates (
                    id, project_id, feedback_id, employee_id, status, confidence, created_at, updated_at, payload
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (id) DO UPDATE
                SET project_id = EXCLUDED.project_id,
                    feedback_id = EXCLUDED.feedback_id,
                    employee_id = EXCLUDED.employee_id,
                    status = EXCLUDED.status,
                    confidence = EXCLUDED.confidence,
                    created_at = EXCLUDED.created_at,
                    updated_at = EXCLUDED.updated_at,
                    payload = EXCLUDED.payload
                """,
                (
                    candidate["id"],
                    candidate["project_id"],
                    candidate["feedback_id"],
                    candidate["employee_id"],
                    candidate["status"],
                    float(candidate.get("confidence") or 0),
                    candidate["created_at"],
                    candidate["updated_at"],
                    _json_dumps(candidate),
                ),
            )

    def create_candidate(self, project_id: str, feedback_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = _now_iso()
        feedback_ids = [str(item).strip() for item in (payload.get("feedback_ids") or []) if str(item).strip()]
        if not feedback_ids:
            feedback_ids = [feedback_id]
        source_feedback_ids = [
            str(item).strip() for item in (payload.get("source_feedback_ids") or []) if str(item).strip()
        ]
        candidate = {
            "id": self.new_candidate_id(),
            "project_id": project_id,
            "feedback_id": feedback_id,
            "feedback_ids": feedback_ids,
            "source_feedback_ids": source_feedback_ids,
            "employee_id": str(payload.get("employee_id") or "").strip(),
            "category": str(payload.get("category") or "general").strip() or "general",
            "source": str(payload.get("source") or "analysis").strip() or "analysis",
            "created_by": str(payload.get("created_by") or "").strip(),
            "target_rule_id": str(payload.get("target_rule_id") or "").strip(),
            "old_rule_content": str(payload.get("old_rule_content") or ""),
            "proposed_rule_content": str(payload.get("proposed_rule_content") or ""),
            "executable_rule_content": str(payload.get("executable_rule_content") or ""),
            "risk_level": str(payload.get("risk_level") or "medium").strip().lower(),
            "confidence": float(payload.get("confidence") or 0),
            "status": str(payload.get("status") or "pending").strip().lower(),
            "reviewer": str(payload.get("reviewer") or "").strip(),
            "review_comment": str(payload.get("review_comment") or "").strip(),
            "created_at": now,
            "updated_at": now,
        }
        self.save_candidate(candidate)
        return candidate

    def get_candidate(self, project_id: str, candidate_id: str) -> dict[str, Any] | None:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT payload FROM feedback_candidates WHERE project_id = %s AND id = %s",
                (project_id, candidate_id),
            )
            row = cur.fetchone()
        return row["payload"] if row else None

    def patch_candidate(
        self,
        project_id: str,
        candidate_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        candidate = self.get_candidate(project_id, candidate_id)
        if candidate is None:
            return None
        candidate.update(updates)
        candidate["updated_at"] = _now_iso()
        self.save_candidate(candidate)
        return candidate

    def list_candidates(
        self,
        project_id: str,
        status: str = "",
        employee_id: str = "",
        feedback_id: str = "",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        sql = "SELECT payload FROM feedback_candidates WHERE project_id = %s"
        params: list[Any] = [project_id]
        if status:
            sql += " AND status = %s"
            params.append(status)
        if employee_id:
            sql += " AND employee_id = %s"
            params.append(employee_id)
        if feedback_id:
            sql += """
            AND (
                feedback_id = %s
                OR (
                    payload ? 'feedback_ids'
                    AND EXISTS (
                        SELECT 1
                        FROM jsonb_array_elements_text(payload->'feedback_ids') AS fid
                        WHERE fid = %s
                    )
                )
            )
            """
            params.extend([feedback_id, feedback_id])
        sql += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        with self._conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
        return [r["payload"] for r in rows]

    def create_review(self, project_id: str, feedback_id: str, candidate_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        review = {
            "id": self.new_review_id(),
            "project_id": project_id,
            "feedback_id": feedback_id,
            "candidate_id": candidate_id,
            "reviewer": str(payload.get("reviewer") or "").strip(),
            "action": str(payload.get("action") or "").strip(),
            "comment": str(payload.get("comment") or "").strip(),
            "edited_content": str(payload.get("edited_content") or ""),
            "edited_executable_content": str(payload.get("edited_executable_content") or ""),
            "created_at": _now_iso(),
        }
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO feedback_reviews (id, project_id, feedback_id, candidate_id, created_at, payload)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    review["id"],
                    review["project_id"],
                    review["feedback_id"],
                    review["candidate_id"],
                    review["created_at"],
                    _json_dumps(review),
                ),
            )
        return review

    def list_reviews_by_feedback(self, project_id: str, feedback_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT payload FROM feedback_reviews
                WHERE project_id = %s AND feedback_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (project_id, feedback_id, limit),
            )
            rows = cur.fetchall()
        return [r["payload"] for r in rows]

    def list_reviews_by_candidate_ids(
        self,
        project_id: str,
        candidate_ids: list[str],
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        ids = [str(item or "").strip() for item in (candidate_ids or []) if str(item or "").strip()]
        if not ids:
            return []
        placeholders = ", ".join(["%s"] * len(ids))
        sql = f"""
            SELECT payload FROM feedback_reviews
            WHERE project_id = %s AND candidate_id IN ({placeholders})
            ORDER BY created_at DESC
            LIMIT %s
        """
        with self._conn.cursor() as cur:
            cur.execute(sql, (project_id, *ids, limit))
            rows = cur.fetchall()
        return [r["payload"] for r in rows]
