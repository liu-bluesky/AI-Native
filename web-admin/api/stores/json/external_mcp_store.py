"""外部 MCP 模块存储层"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ExternalMcpModule:
    id: str
    name: str
    description: str = ""
    endpoint_http: str = ""
    endpoint_sse: str = ""
    auth_type: str = "none"
    project_id: str = ""
    enabled: bool = True
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)


class ExternalMcpStore:
    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir / "external-mcp-modules"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, module_id: str) -> Path:
        return self._dir / f"{module_id}.json"

    def save(self, module: ExternalMcpModule) -> None:
        self._path(module.id).write_text(
            json.dumps(asdict(module), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get(self, module_id: str) -> Optional[ExternalMcpModule]:
        path = self._path(module_id)
        if not path.exists():
            return None
        return ExternalMcpModule(**json.loads(path.read_text(encoding="utf-8")))

    def list_all(self) -> list[ExternalMcpModule]:
        items: list[ExternalMcpModule] = []
        for path in sorted(self._dir.glob("*.json")):
            items.append(ExternalMcpModule(**json.loads(path.read_text(encoding="utf-8"))))
        return items

    def delete(self, module_id: str) -> bool:
        path = self._path(module_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    def new_id(self) -> str:
        return f"xmcp-{uuid.uuid4().hex[:8]}"

