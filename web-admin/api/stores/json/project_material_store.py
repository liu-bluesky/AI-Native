"""项目素材库存储层（JSON 实现）"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from stores.json.project_store import _now_iso


@dataclass
class ProjectMaterialAsset:
    id: str
    project_id: str
    asset_type: str
    group_type: str
    title: str
    summary: str = ""
    source_message_id: str = ""
    source_chat_session_id: str = ""
    source_username: str = ""
    created_by: str = ""
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    preview_url: str = ""
    content_url: str = ""
    mime_type: str = ""
    status: str = "ready"
    structured_content: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class ProjectMaterialStore:
    def __init__(self, data_dir: Path) -> None:
        self._root = data_dir / "project-materials"
        self._root.mkdir(parents=True, exist_ok=True)

    def _project_path(self, project_id: str) -> Path:
        return self._root / f"{str(project_id or '').strip()}.json"

    def _read_project_assets(self, project_id: str) -> list[ProjectMaterialAsset]:
        path = self._project_path(project_id)
        if not path.exists():
            return []
        try:
            raw_list = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
        items: list[ProjectMaterialAsset] = []
        for raw in raw_list if isinstance(raw_list, list) else []:
            if not isinstance(raw, dict):
                continue
            try:
                items.append(ProjectMaterialAsset(**raw))
            except TypeError:
                continue
        items.sort(key=lambda item: str(item.updated_at or ""), reverse=True)
        return items

    def _write_project_assets(self, project_id: str, items: list[ProjectMaterialAsset]) -> None:
        path = self._project_path(project_id)
        path.write_text(
            json.dumps([asdict(item) for item in items], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def new_id(self) -> str:
        return f"asset-{uuid.uuid4().hex[:8]}"

    def list_by_project(self, project_id: str) -> list[ProjectMaterialAsset]:
        return self._read_project_assets(project_id)

    def get(self, project_id: str, asset_id: str) -> ProjectMaterialAsset | None:
        normalized_asset_id = str(asset_id or "").strip()
        if not normalized_asset_id:
            return None
        for item in self._read_project_assets(project_id):
            if item.id == normalized_asset_id:
                return item
        return None

    def save(self, asset: ProjectMaterialAsset) -> None:
        project_id = str(asset.project_id or "").strip()
        if not project_id:
            raise ValueError("project_id is required")
        items = [item for item in self._read_project_assets(project_id) if item.id != asset.id]
        items.append(asset)
        items.sort(key=lambda item: str(item.updated_at or ""), reverse=True)
        self._write_project_assets(project_id, items)

    def delete(self, project_id: str, asset_id: str) -> bool:
        items = self._read_project_assets(project_id)
        remaining = [item for item in items if item.id != str(asset_id or "").strip()]
        if len(remaining) == len(items):
            return False
        if remaining:
            self._write_project_assets(project_id, remaining)
        else:
            path = self._project_path(project_id)
            if path.exists():
                path.unlink()
        return True
