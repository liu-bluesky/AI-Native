"""Project-scoped studio voice asset service."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from core.config import get_settings
from stores.postgres.project_voice_store import ProjectVoiceStorePostgres


class ProjectVoiceService:
    def __init__(self, store: ProjectVoiceStorePostgres) -> None:
        self._store = store

    @staticmethod
    def _normalize_text(value: Any, *, limit: int = 500) -> str:
        return str(value or "").strip()[:limit]

    def new_voice_id(self) -> str:
        return self._store.new_voice_id()

    def list_project_voices(self, project_id: str) -> list[dict[str, Any]]:
        normalized_project_id = self._normalize_text(project_id, limit=120)
        if not normalized_project_id:
            return []
        return self._store.list_project_voices(normalized_project_id)

    def get_project_voice(self, project_id: str, voice_id: str) -> dict[str, Any] | None:
        normalized_project_id = self._normalize_text(project_id, limit=120)
        normalized_voice_id = self._normalize_text(voice_id, limit=120)
        if not normalized_project_id or not normalized_voice_id:
            return None
        voice = self._store.get_voice(normalized_voice_id)
        if not voice:
            return None
        if self._normalize_text(voice.get("project_id"), limit=120) != normalized_project_id:
            return None
        return voice

    def create_project_voice(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = {
            "id": self._normalize_text(payload.get("id"), limit=120),
            "project_id": self._normalize_text(payload.get("project_id"), limit=120),
            "provider_id": self._normalize_text(payload.get("provider_id"), limit=120),
            "model_name": self._normalize_text(payload.get("model_name"), limit=160),
            "voice_id": self._normalize_text(payload.get("voice_id"), limit=200),
            "name": self._normalize_text(payload.get("name"), limit=120),
            "status": self._normalize_text(payload.get("status"), limit=40) or "ready",
            "source_type": self._normalize_text(payload.get("source_type"), limit=40) or "custom_clone",
            "description": self._normalize_text(payload.get("description"), limit=500),
            "preview_text": self._normalize_text(payload.get("preview_text"), limit=500),
            "transcript_text": self._normalize_text(payload.get("transcript_text"), limit=4000),
            "provider_voice_name": self._normalize_text(payload.get("provider_voice_name"), limit=160),
            "provider_payload": payload.get("provider_payload") if isinstance(payload.get("provider_payload"), dict) else {},
            "sample_audio": payload.get("sample_audio") if isinstance(payload.get("sample_audio"), dict) else {},
            "preview_audio": payload.get("preview_audio") if isinstance(payload.get("preview_audio"), dict) else {},
            "created_by": self._normalize_text(payload.get("created_by"), limit=120),
        }
        if not normalized["project_id"]:
            raise ValueError("project_id is required")
        if not normalized["provider_id"]:
            raise ValueError("provider_id is required")
        if not normalized["voice_id"]:
            raise ValueError("voice_id is required")
        if not normalized["name"]:
            raise ValueError("name is required")
        return self._store.create_voice(normalized)

    def update_project_voice(self, project_id: str, voice_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        current = self.get_project_voice(project_id, voice_id)
        if current is None:
            raise LookupError("project voice not found")
        updates: dict[str, Any] = {}
        if "name" in payload:
            updates["name"] = self._normalize_text(payload.get("name"), limit=120)
        if "description" in payload:
            updates["description"] = self._normalize_text(payload.get("description"), limit=500)
        if "preview_text" in payload:
            updates["preview_text"] = self._normalize_text(payload.get("preview_text"), limit=500)
        if "transcript_text" in payload:
            updates["transcript_text"] = self._normalize_text(payload.get("transcript_text"), limit=4000)
        if "voice_id" in payload and self._normalize_text(current.get("source_type"), limit=40) == "manual_binding":
            updates["voice_id"] = self._normalize_text(payload.get("voice_id"), limit=200)
        if "provider_voice_name" in payload:
            updates["provider_voice_name"] = self._normalize_text(payload.get("provider_voice_name"), limit=160)
        if "preview_audio" in payload:
            updates["preview_audio"] = payload.get("preview_audio") if isinstance(payload.get("preview_audio"), dict) else {}
        if "status" in payload:
            updates["status"] = self._normalize_text(payload.get("status"), limit=40) or "ready"
        if not updates:
            return current
        next_name = updates.get("name") or self._normalize_text(current.get("name"), limit=120)
        next_voice_id = updates.get("voice_id") or self._normalize_text(current.get("voice_id"), limit=200)
        if not next_name:
            raise ValueError("name is required")
        if not next_voice_id:
            raise ValueError("voice_id is required")
        updated = self._store.patch_voice(str(current.get("id") or "").strip(), updates)
        if updated is None:
            raise LookupError("project voice not found")
        return updated

    def delete_project_voice(self, project_id: str, voice_id: str) -> dict[str, Any]:
        voice = self.get_project_voice(project_id, voice_id)
        if voice is None:
            raise LookupError("project voice not found")
        if not self._store.delete_voice(str(voice.get("id") or "").strip()):
            raise LookupError("project voice not found")
        return voice


@lru_cache(maxsize=1)
def get_project_voice_service() -> ProjectVoiceService:
    settings = get_settings()
    if settings.core_store_backend != "postgres":
        raise RuntimeError("Project voice module requires CORE_STORE_BACKEND=postgres")
    return ProjectVoiceService(ProjectVoiceStorePostgres(settings.database_url))
