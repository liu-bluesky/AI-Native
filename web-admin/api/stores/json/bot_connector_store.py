"""Bot connector store (JSON implementation)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from stores.json.system_config_store import normalize_bot_platform_connectors


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class BotConnectorStore:
    def __init__(self, data_dir: Path) -> None:
        self._root = data_dir / "bot-connectors"
        self._path = self._root / "global.json"
        self._root.mkdir(parents=True, exist_ok=True)

    def list_all(self) -> list[dict[str, object]]:
        if not self._path.exists():
            return []
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return []
        items = payload.get("items") if isinstance(payload, dict) else payload
        return normalize_bot_platform_connectors(items)

    def replace_all(self, items: object) -> list[dict[str, object]]:
        normalized = normalize_bot_platform_connectors(items)
        self._path.write_text(
            json.dumps(
                {
                    "id": "global",
                    "items": normalized,
                    "updated_at": _now_iso(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return normalized
