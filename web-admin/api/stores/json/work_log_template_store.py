"""Global work log template store."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class WorkLogTemplate:
    value: str
    label: str
    description: str = ""
    fields: int = 1
    updated_by: str = ""
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)


class WorkLogTemplateStore:
    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir / "work_log_templates"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, template_key: str) -> Path:
        return self._dir / f"{template_key}.json"

    def save(self, template: WorkLogTemplate) -> None:
        self._path(template.value).write_text(
            json.dumps(asdict(template), ensure_ascii=False, indent=2),
        )

    def get(self, template_key: str) -> WorkLogTemplate | None:
        path = self._path(template_key)
        if not path.exists():
            return None
        return WorkLogTemplate(**json.loads(path.read_text()))

    def list_all(self) -> list[WorkLogTemplate]:
        results = []
        for path in sorted(self._dir.glob("*.json")):
            results.append(WorkLogTemplate(**json.loads(path.read_text())))
        return results
