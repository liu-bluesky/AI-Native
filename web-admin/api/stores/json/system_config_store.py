"""系统配置存储层"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SystemConfig:
    id: str = "global"
    enable_project_manual_generation: bool = False
    enable_employee_manual_generation: bool = False
    enable_user_register: bool = True
    chat_upload_max_limit: int = 6
    chat_max_tokens: int = 512
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)


class SystemConfigStore:
    def __init__(self, data_dir: Path) -> None:
        self._path = data_dir / "system-config.json"

    def get_global(self) -> SystemConfig:
        if not self._path.exists():
            return SystemConfig()
        data = json.loads(self._path.read_text(encoding="utf-8"))
        return SystemConfig(**data)

    def save_global(self, config: SystemConfig) -> None:
        self._path.write_text(
            json.dumps(asdict(config), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def patch_global(self, updates: dict) -> SystemConfig:
        current = self.get_global()
        payload = asdict(current)
        payload.update(updates)
        payload["updated_at"] = _now_iso()
        if not payload.get("created_at"):
            payload["created_at"] = _now_iso()
        updated = SystemConfig(**payload)
        self.save_global(updated)
        return updated
