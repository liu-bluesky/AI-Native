"""Agent template store."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AgentTemplate:
    id: str
    name: str
    name_zh: str = ""
    created_by: str = ""
    description: str = ""
    content: str = ""
    goal: str = ""
    source_name: str = ""
    source_url: str = ""
    relative_path: str = ""
    tone: str = "professional"
    verbosity: str = "concise"
    language: str = "zh-CN"
    rule_domains: list[str] = field(default_factory=list)
    style_hints: list[str] = field(default_factory=list)
    default_workflow: list[str] = field(default_factory=list)
    tool_usage_policy: str = ""
    draft: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)


class AgentTemplateStore:
    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir / "agent_templates"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, template_id: str) -> Path:
        return self._dir / f"{template_id}.json"

    def save(self, template: AgentTemplate) -> None:
        self._path(template.id).write_text(
            json.dumps(asdict(template), ensure_ascii=False, indent=2),
        )

    def get(self, template_id: str) -> Optional[AgentTemplate]:
        path = self._path(template_id)
        if not path.exists():
            return None
        return AgentTemplate(**json.loads(path.read_text()))

    def list_all(self) -> list[AgentTemplate]:
        results = []
        for path in sorted(self._dir.glob("*.json")):
            results.append(AgentTemplate(**json.loads(path.read_text())))
        return results

    def delete(self, template_id: str) -> bool:
        path = self._path(template_id)
        if path.exists():
            path.unlink()
            return True
        return False

    def new_id(self) -> str:
        return f"agtpl-{uuid.uuid4().hex[:8]}"
