"""CLI plugin user profile store (JSON implementation)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class CliPluginUserProfileRecord:
    plugin_id: str
    owner_username: str
    created_by: str = ""
    share_scope: str = "private"
    shared_with_usernames: list[str] = field(default_factory=list)
    status: str = "uninitialized"
    status_label: str = "未初始化"
    runtime_root: str = ""
    home_dir: str = ""
    config_dir: str = ""
    data_dir: str = ""
    cache_dir: str = ""
    login_command: str = ""
    logout_command: str = ""
    test_command: str = ""
    last_login_at: str = ""
    last_logout_at: str = ""
    last_test_at: str = ""
    last_test_ok: bool = False
    last_error: str = ""
    metadata: dict[str, object] = field(default_factory=dict)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)


class CliPluginProfileStore:
    def __init__(self, data_dir: Path) -> None:
        self._root = data_dir / "cli-plugin-profiles"
        self._root.mkdir(parents=True, exist_ok=True)

    def _safe_key(self, value: str) -> str:
        text = str(value or "").strip()
        return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in text)

    def _profile_path(self, plugin_id: str, owner_username: str) -> Path:
        return self._root / f"{self._safe_key(plugin_id)}__{self._safe_key(owner_username)}.json"

    def save_profile(self, item: CliPluginUserProfileRecord) -> None:
        path = self._profile_path(item.plugin_id, item.owner_username)
        path.write_text(
            json.dumps(asdict(item), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def get_profile(
        self,
        plugin_id: str,
        owner_username: str,
    ) -> Optional[CliPluginUserProfileRecord]:
        path = self._profile_path(plugin_id, owner_username)
        if not path.exists():
            return None
        return CliPluginUserProfileRecord(**json.loads(path.read_text(encoding="utf-8")))

    def list_profiles(
        self,
        *,
        plugin_id: str = "",
        owner_username: str = "",
    ) -> list[CliPluginUserProfileRecord]:
        normalized_plugin_id = str(plugin_id or "").strip()
        normalized_owner = str(owner_username or "").strip()
        items: list[CliPluginUserProfileRecord] = []
        for path in self._root.glob("*.json"):
            try:
                item = CliPluginUserProfileRecord(**json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                continue
            if normalized_plugin_id and item.plugin_id != normalized_plugin_id:
                continue
            if normalized_owner and item.owner_username != normalized_owner:
                continue
            items.append(item)
        items.sort(key=lambda item: (item.updated_at, item.created_at, item.plugin_id), reverse=True)
        return items

    def delete_profile(self, plugin_id: str, owner_username: str) -> bool:
        path = self._profile_path(plugin_id, owner_username)
        if not path.exists():
            return False
        path.unlink()
        return True
