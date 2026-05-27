"""Workspace trust policy for agent_runtime_v2."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.config import get_project_root
from services.agent_runtime_v2.task_run import utc_now_iso


@dataclass
class WorkspaceTrust:
    workspace_path: str
    trusted: bool = False
    trusted_by: str = ""
    trusted_at: str = ""
    source: str = "project"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_path": self.workspace_path,
            "trusted": self.trusted,
            "trusted_by": self.trusted_by,
            "trusted_at": self.trusted_at,
            "source": self.source,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WorkspaceTrust":
        return cls(
            workspace_path=str(payload.get("workspace_path") or "").strip(),
            trusted=bool(payload.get("trusted")),
            trusted_by=str(payload.get("trusted_by") or "").strip(),
            trusted_at=str(payload.get("trusted_at") or "").strip(),
            source=str(payload.get("source") or "project").strip() or "project",
            metadata=dict(payload.get("metadata") or {}),
        )


class TrustPolicy:
    def __init__(self, root_path: Path | None = None):
        self._root_path = root_path or (
            get_project_root() / ".ai-employee" / "agent-runtime-v2" / "trust"
        )

    def _path_for(self, workspace_path: str) -> Path:
        normalized = str(workspace_path or "").strip()
        if not normalized:
            raise ValueError("workspace_path is required")
        safe_name = normalized.replace("/", "__").replace(":", "_")
        return self._root_path / f"{safe_name}.json"

    def get(self, workspace_path: str) -> WorkspaceTrust:
        path = self._path_for(workspace_path)
        if not path.is_file():
            return WorkspaceTrust(workspace_path=str(workspace_path or "").strip())
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return WorkspaceTrust(workspace_path=str(workspace_path or "").strip())
        return WorkspaceTrust.from_dict(payload) if isinstance(payload, dict) else WorkspaceTrust(workspace_path=workspace_path)

    def mark_trusted(
        self,
        *,
        workspace_path: str,
        username: str,
        source: str = "project",
        metadata: dict[str, Any] | None = None,
    ) -> WorkspaceTrust:
        trust = WorkspaceTrust(
            workspace_path=str(workspace_path or "").strip(),
            trusted=True,
            trusted_by=str(username or "").strip(),
            trusted_at=utc_now_iso(),
            source=str(source or "project").strip() or "project",
            metadata=dict(metadata or {}),
        )
        path = self._path_for(trust.workspace_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(trust.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return trust

    def ensure_workspace_trusted(self, workspace_path: str) -> WorkspaceTrust:
        trust = self.get(workspace_path)
        if not trust.trusted:
            return trust
        return trust
