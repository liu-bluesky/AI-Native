"""更新日志存储层"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(value: object, limit: int) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()[:limit]


def _normalize_release_date(value: object) -> str:
    raw = str(value or "").strip()[:32]
    if not raw:
        return ""
    normalized = raw.replace("/", "-").replace(".", "-")
    try:
        parsed = datetime.fromisoformat(normalized[:10])
    except ValueError:
        return raw
    return parsed.date().isoformat()


def _timestamp_for_sort(value: object) -> float:
    raw = str(value or "").strip()
    if not raw:
        return 0.0
    normalized = raw.replace(" ", "T").replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).timestamp()
    except ValueError:
        try:
            return datetime.fromisoformat(f"{normalized[:10]}T00:00:00+00:00").timestamp()
        except ValueError:
            return 0.0


@dataclass
class ChangelogEntry:
    id: str
    version: str = ""
    title: str = ""
    summary: str = ""
    content: str = ""
    release_date: str = ""
    published: bool = False
    sort_order: int = 100
    created_by: str = ""
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def __post_init__(self) -> None:
        self.id = str(self.id or "").strip()[:80]
        self.version = _normalize_text(self.version, 80)
        self.title = _normalize_text(self.title, 160)
        self.summary = _normalize_text(self.summary, 600)
        self.content = _normalize_text(self.content, 24000)
        self.release_date = _normalize_release_date(self.release_date)
        self.published = bool(self.published)
        try:
            self.sort_order = int(self.sort_order)
        except (TypeError, ValueError):
            self.sort_order = 100
        self.sort_order = max(0, min(9999, self.sort_order))
        self.created_by = _normalize_text(self.created_by, 80)
        self.created_at = _normalize_text(self.created_at or _now_iso(), 40) or _now_iso()
        self.updated_at = _normalize_text(self.updated_at or _now_iso(), 40) or _now_iso()


def sort_changelog_entries(items: list[ChangelogEntry]) -> list[ChangelogEntry]:
    return sorted(
        items,
        key=lambda item: (
            int(getattr(item, "sort_order", 100) or 100),
            -_timestamp_for_sort(getattr(item, "release_date", "")),
            -_timestamp_for_sort(getattr(item, "updated_at", "")),
            str(getattr(item, "id", "") or ""),
        ),
    )


class ChangelogEntryStore:
    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir / "changelog-entries"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, entry_id: str) -> Path:
        return self._dir / f"{str(entry_id or '').strip()}.json"

    def save(self, entry: ChangelogEntry) -> None:
        payload = asdict(ChangelogEntry(**asdict(entry)))
        if not payload.get("id"):
            raise ValueError("Changelog entry id is required")
        if not payload.get("created_at"):
            payload["created_at"] = _now_iso()
        payload["updated_at"] = _now_iso()
        self._path(payload["id"]).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get(self, entry_id: str) -> ChangelogEntry | None:
        path = self._path(entry_id)
        if not path.exists():
            return None
        return ChangelogEntry(**json.loads(path.read_text(encoding="utf-8")))

    def list_all(self) -> list[ChangelogEntry]:
        items: list[ChangelogEntry] = []
        for path in self._dir.glob("*.json"):
            items.append(ChangelogEntry(**json.loads(path.read_text(encoding="utf-8"))))
        return sort_changelog_entries(items)

    def list_public(self) -> list[ChangelogEntry]:
        return [item for item in self.list_all() if bool(item.published)]

    def delete(self, entry_id: str) -> bool:
        path = self._path(entry_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    def new_id(self) -> str:
        return f"clog-{uuid.uuid4().hex[:8]}"
