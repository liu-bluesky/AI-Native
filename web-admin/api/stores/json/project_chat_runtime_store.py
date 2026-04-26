"""项目 AI 对话运行态快照存储层（JSON 实现）"""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import Any

from stores.json.project_chat_store import _now_iso, _safe_token


class ProjectChatRuntimeStore:
    def __init__(self, data_dir: Path) -> None:
        self._root = data_dir / "project-chat-runtime"
        self._root.mkdir(parents=True, exist_ok=True)

    def _project_dir(self, project_id: str) -> Path:
        return self._root / _safe_token(project_id)

    def _username_dir(self, project_id: str, username: str) -> Path:
        return self._project_dir(project_id) / _safe_token(username, max_len=64)

    def _snapshot_path(self, project_id: str, username: str, chat_session_id: str) -> Path:
        return self._username_dir(project_id, username) / f"{_safe_token(chat_session_id, max_len=128)}.json"

    def get_snapshot(self, project_id: str, username: str, chat_session_id: str) -> dict[str, Any] | None:
        normalized_session_id = str(chat_session_id or "").strip()
        if not normalized_session_id:
            return None
        path = self._snapshot_path(project_id, username, normalized_session_id)
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(raw, dict):
            return None
        payload = raw.get("payload")
        return {
            "project_id": str(raw.get("project_id") or project_id).strip(),
            "username": str(raw.get("username") or username).strip(),
            "chat_session_id": str(raw.get("chat_session_id") or normalized_session_id).strip(),
            "payload": payload if isinstance(payload, dict) else {},
            "updated_at": str(raw.get("updated_at") or _now_iso()).strip(),
        }

    def save_snapshot(
        self,
        project_id: str,
        username: str,
        chat_session_id: str,
        payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        normalized_project_id = str(project_id or "").strip()
        normalized_username = str(username or "").strip()
        normalized_session_id = str(chat_session_id or "").strip()
        if not normalized_project_id or not normalized_username or not normalized_session_id:
            raise ValueError("project_id, username and chat_session_id are required")
        snapshot = {
            "project_id": normalized_project_id,
            "username": normalized_username,
            "chat_session_id": normalized_session_id,
            "payload": payload if isinstance(payload, dict) else {},
            "updated_at": _now_iso(),
        }
        target_dir = self._username_dir(normalized_project_id, normalized_username)
        target_dir.mkdir(parents=True, exist_ok=True)
        self._snapshot_path(
            normalized_project_id,
            normalized_username,
            normalized_session_id,
        ).write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return snapshot

    def delete_snapshot(self, project_id: str, username: str, chat_session_id: str = "") -> int:
        normalized_project_id = str(project_id or "").strip()
        normalized_username = str(username or "").strip()
        normalized_session_id = str(chat_session_id or "").strip()
        if not normalized_project_id or not normalized_username:
            return 0
        user_dir = self._username_dir(normalized_project_id, normalized_username)
        if not user_dir.exists():
            return 0
        if normalized_session_id:
            path = self._snapshot_path(
                normalized_project_id,
                normalized_username,
                normalized_session_id,
            )
            if not path.exists():
                return 0
            path.unlink()
            return 1
        removed = 0
        for path in user_dir.glob("*.json"):
            if not path.is_file():
                continue
            path.unlink()
            removed += 1
        return removed

    def clear_project(self, project_id: str) -> int:
        normalized_project_id = str(project_id or "").strip()
        if not normalized_project_id:
            return 0
        project_dir = self._project_dir(normalized_project_id)
        if not project_dir.exists():
            return 0
        removed = 0
        for path in project_dir.rglob("*.json"):
            if not path.is_file():
                continue
            path.unlink()
            removed += 1
        for path in sorted(project_dir.rglob("*"), reverse=True):
            if path.is_dir():
                with contextlib.suppress(OSError):
                    path.rmdir()
        with contextlib.suppress(OSError):
            project_dir.rmdir()
        return removed
