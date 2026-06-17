"""Project deployment artifact and run store."""

from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from stores.json.project_chat_store import _now_iso, _safe_token


@dataclass
class ProjectDeployArtifact:
    id: str
    project_id: str
    profile: str
    artifact_name: str
    component: str = ""
    artifact_kind: str = "source-bundle"
    version: str = ""
    checksum: str = ""
    size: int = 0
    storage_path: str = ""
    status: str = "uploading"
    manifest: dict[str, Any] = field(default_factory=dict)
    storage_kind: str = "file"
    file_tree: list[dict[str, Any]] = field(default_factory=list)
    uploaded_by: str = ""
    uploaded_at: str = field(default_factory=_now_iso)
    ready_at: str = ""
    deployment_id: str = ""
    error: str = ""


@dataclass
class ProjectDeployRun:
    id: str
    project_id: str
    profile: str
    status: str = "queued"
    component: str = ""
    requested_by: str = ""
    chat_session_id: str = ""
    task_tree_node_id: str = ""
    stage: str = "queued"
    dry_run: bool = False
    config_version: str = ""
    config_snapshot: dict[str, Any] = field(default_factory=dict)
    artifact_id: str = ""
    artifact_summary: dict[str, Any] = field(default_factory=dict)
    log_excerpt: str = ""
    notify_result: list[dict[str, Any]] = field(default_factory=list)
    rollback_ref: str = ""
    deleted_at: str = ""
    deleted_by: str = ""
    delete_reason: str = ""
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)


class ProjectDeployStore:
    def __init__(self, data_dir: Path) -> None:
        self._root = data_dir / "project-deploy"
        self._artifacts_dir = self._root / "artifacts"
        self._runs_dir = self._root / "runs"
        self._files_dir = self._root / "files"
        self._artifacts_dir.mkdir(parents=True, exist_ok=True)
        self._runs_dir.mkdir(parents=True, exist_ok=True)
        self._files_dir.mkdir(parents=True, exist_ok=True)

    @property
    def files_dir(self) -> Path:
        return self._files_dir

    def new_artifact_id(self) -> str:
        return f"artifact-{uuid.uuid4().hex[:12]}"

    def new_run_id(self) -> str:
        return f"deploy-{uuid.uuid4().hex[:12]}"

    def artifact_file_dir(self, project_id: str, artifact_id: str) -> Path:
        return self._files_dir / _safe_token(project_id) / _safe_token(artifact_id)

    def _artifact_path(self, project_id: str, artifact_id: str) -> Path:
        return self._artifacts_dir / _safe_token(project_id) / f"{_safe_token(artifact_id)}.json"

    def _run_path(self, project_id: str, run_id: str) -> Path:
        return self._runs_dir / _safe_token(project_id) / f"{_safe_token(run_id)}.json"

    def save_artifact(self, artifact: ProjectDeployArtifact) -> ProjectDeployArtifact:
        artifact_dir = self._artifacts_dir / _safe_token(artifact.project_id)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        self._artifact_path(artifact.project_id, artifact.id).write_text(
            json.dumps(asdict(artifact), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return artifact

    def get_artifact(self, project_id: str, artifact_id: str) -> ProjectDeployArtifact | None:
        path = self._artifact_path(project_id, artifact_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return ProjectDeployArtifact(**data)

    def delete_artifact(self, project_id: str, artifact_id: str, *, delete_file: bool = True) -> bool:
        artifact = self.get_artifact(project_id, artifact_id)
        path = self._artifact_path(project_id, artifact_id)
        deleted = False
        if path.exists():
            path.unlink()
            deleted = True
        if delete_file and artifact is not None:
            artifact_dir = self.artifact_file_dir(project_id, artifact_id).resolve()
            root = self._files_dir.resolve()
            if root in artifact_dir.parents and artifact_dir.exists():
                shutil.rmtree(artifact_dir)
        return deleted

    def delete_run(self, project_id: str, run_id: str, *, deleted_by: str = "", reason: str = "") -> bool:
        run = self.get_run(project_id, run_id)
        if run is None:
            return False
        run.deleted_at = _now_iso()
        run.deleted_by = str(deleted_by or "").strip()
        run.delete_reason = str(reason or "").strip()
        self.save_run(run)
        return True

    def list_artifacts(self, project_id: str, *, limit: int = 50) -> list[ProjectDeployArtifact]:
        project_dir = self._artifacts_dir / _safe_token(project_id)
        if not project_dir.exists():
            return []
        items: list[ProjectDeployArtifact] = []
        for path in sorted(project_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
            try:
                items.append(ProjectDeployArtifact(**json.loads(path.read_text(encoding="utf-8"))))
            except Exception:
                continue
            if len(items) >= limit:
                break
        return items

    def save_run(self, run: ProjectDeployRun) -> ProjectDeployRun:
        run.updated_at = _now_iso()
        run_dir = self._runs_dir / _safe_token(run.project_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        self._run_path(run.project_id, run.id).write_text(
            json.dumps(asdict(run), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return run

    def get_run(self, project_id: str, run_id: str) -> ProjectDeployRun | None:
        path = self._run_path(project_id, run_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return ProjectDeployRun(**data)

    def list_runs(self, project_id: str, *, limit: int = 50) -> list[ProjectDeployRun]:
        project_dir = self._runs_dir / _safe_token(project_id)
        if not project_dir.exists():
            return []
        items: list[ProjectDeployRun] = []
        for path in sorted(project_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
            try:
                run = ProjectDeployRun(**json.loads(path.read_text(encoding="utf-8")))
                if run.deleted_at:
                    continue
                items.append(run)
            except Exception:
                continue
            if len(items) >= limit:
                break
        return items
