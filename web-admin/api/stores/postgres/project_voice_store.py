"""Project studio voice storage (PostgreSQL only)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from psycopg.rows import dict_row

from stores.postgres._connection import connect


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_dumps(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False)


class ProjectVoiceStorePostgres:
    def __init__(self, database_url: str) -> None:
        self._conn = connect(database_url, autocommit=True, row_factory=dict_row)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS project_studio_voices (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    provider_id TEXT NOT NULL,
                    model_name TEXT NOT NULL DEFAULT '',
                    voice_id TEXT NOT NULL DEFAULT '',
                    name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'ready',
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    payload JSONB NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_project_studio_voices_project_updated
                ON project_studio_voices (project_id, updated_at DESC);
                """
            )

    @staticmethod
    def new_voice_id() -> str:
        return f"studio-voice-{uuid.uuid4().hex[:8]}"

    def save_voice(self, voice: dict[str, Any]) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO project_studio_voices (
                    id, project_id, provider_id, model_name, voice_id, name, status, updated_at, payload
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (id) DO UPDATE
                SET project_id = EXCLUDED.project_id,
                    provider_id = EXCLUDED.provider_id,
                    model_name = EXCLUDED.model_name,
                    voice_id = EXCLUDED.voice_id,
                    name = EXCLUDED.name,
                    status = EXCLUDED.status,
                    updated_at = EXCLUDED.updated_at,
                    payload = EXCLUDED.payload
                """,
                (
                    voice["id"],
                    voice["project_id"],
                    voice["provider_id"],
                    voice["model_name"],
                    voice["voice_id"],
                    voice["name"],
                    voice["status"],
                    voice["updated_at"],
                    _json_dumps(voice),
                ),
            )

    def create_voice(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = _now_iso()
        voice = {
            "id": str(payload.get("id") or self.new_voice_id()).strip(),
            "project_id": str(payload.get("project_id") or "").strip(),
            "provider_id": str(payload.get("provider_id") or "").strip(),
            "model_name": str(payload.get("model_name") or "").strip(),
            "voice_id": str(payload.get("voice_id") or "").strip(),
            "name": str(payload.get("name") or "").strip(),
            "status": str(payload.get("status") or "ready").strip() or "ready",
            "source_type": str(payload.get("source_type") or "custom_clone").strip() or "custom_clone",
            "description": str(payload.get("description") or "").strip(),
            "preview_text": str(payload.get("preview_text") or "").strip(),
            "transcript_text": str(payload.get("transcript_text") or "").strip(),
            "provider_voice_name": str(payload.get("provider_voice_name") or "").strip(),
            "provider_payload": payload.get("provider_payload") or {},
            "sample_audio": payload.get("sample_audio") or {},
            "preview_audio": payload.get("preview_audio") or {},
            "created_by": str(payload.get("created_by") or "").strip(),
            "created_at": str(payload.get("created_at") or now).strip() or now,
            "updated_at": now,
        }
        self.save_voice(voice)
        return voice

    def get_voice(self, voice_id: str) -> dict[str, Any] | None:
        with self._conn.cursor() as cur:
            cur.execute("SELECT payload FROM project_studio_voices WHERE id = %s", (voice_id,))
            row = cur.fetchone()
        return row["payload"] if row else None

    def list_project_voices(self, project_id: str) -> list[dict[str, Any]]:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT payload FROM project_studio_voices
                WHERE project_id = %s
                ORDER BY updated_at DESC
                """,
                (project_id,),
            )
            rows = cur.fetchall()
        return [row["payload"] for row in rows]

    def patch_voice(self, voice_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        voice = self.get_voice(voice_id)
        if voice is None:
            return None
        voice.update(updates)
        voice["updated_at"] = _now_iso()
        self.save_voice(voice)
        return voice

    def delete_voice(self, voice_id: str) -> bool:
        with self._conn.cursor() as cur:
            cur.execute("DELETE FROM project_studio_voices WHERE id = %s", (voice_id,))
            return bool(cur.rowcount and cur.rowcount > 0)
