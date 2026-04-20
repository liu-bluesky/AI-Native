"""项目经验总结任务存储层（JSON 实现）"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from stores.json.project_store import _now_iso


@dataclass
class ProjectExperienceSummaryJob:
    id: str
    project_id: str
    status: str = "queued"
    progress: int = 0
    stage: str = "queued"
    status_message: str = ""
    provider_id: str = ""
    model_name: str = ""
    review_mode: str = "auto"
    experience_scope: str = "development"
    clear_requirement_records_requested: bool = True
    clear_requirement_records_executed: bool = False
    manual_review_required: bool = False
    requested_record_ids: list[str] = field(default_factory=list)
    source_record_ids: list[str] = field(default_factory=list)
    source_records: list[dict[str, Any]] = field(default_factory=list)
    source_record_count: int = 0
    max_cards: int = 5
    min_review_confidence: float = 0.75
    max_evidence_snippets_per_record: int = 2
    candidate_card_count: int = 0
    approved_card_count: int = 0
    created_rule_ids: list[str] = field(default_factory=list)
    updated_rule_ids: list[str] = field(default_factory=list)
    experience_rule_ids: list[str] = field(default_factory=list)
    experience_rule_bindings: list[dict[str, Any]] = field(default_factory=list)
    review_result: dict[str, Any] = field(default_factory=dict)
    clear_result: dict[str, Any] = field(default_factory=dict)
    error_code: str = ""
    error_message: str = ""
    error_details: dict[str, Any] = field(default_factory=dict)
    created_by: str = ""
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    started_at: str = ""
    finished_at: str = ""


class ProjectExperienceSummaryStore:
    def __init__(self, data_dir: Path) -> None:
        self._root = data_dir / "project-experience-summary-jobs"
        self._root.mkdir(parents=True, exist_ok=True)

    def _project_path(self, project_id: str) -> Path:
        return self._root / f"{str(project_id or '').strip()}.json"

    def _read_project_jobs(self, project_id: str) -> list[ProjectExperienceSummaryJob]:
        path = self._project_path(project_id)
        if not path.exists():
            return []
        try:
            raw_list = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
        items: list[ProjectExperienceSummaryJob] = []
        for raw in raw_list if isinstance(raw_list, list) else []:
            if not isinstance(raw, dict):
                continue
            try:
                items.append(ProjectExperienceSummaryJob(**raw))
            except TypeError:
                continue
        items.sort(key=lambda item: str(item.updated_at or ""), reverse=True)
        return items

    def _write_project_jobs(self, project_id: str, items: list[ProjectExperienceSummaryJob]) -> None:
        path = self._project_path(project_id)
        path.write_text(
            json.dumps([asdict(item) for item in items], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def new_id(self) -> str:
        return f"experience-summary-{uuid.uuid4().hex[:8]}"

    def list_by_project(
        self,
        project_id: str,
        *,
        status: str = "",
        limit: int = 0,
    ) -> list[ProjectExperienceSummaryJob]:
        items = self._read_project_jobs(project_id)
        normalized_status = str(status or "").strip()
        if normalized_status:
            items = [item for item in items if item.status == normalized_status]
        if limit and limit > 0:
            return items[:limit]
        return items

    def get(self, project_id: str, job_id: str) -> ProjectExperienceSummaryJob | None:
        normalized_job_id = str(job_id or "").strip()
        if not normalized_job_id:
            return None
        for item in self._read_project_jobs(project_id):
            if item.id == normalized_job_id:
                return item
        return None

    def save(self, job: ProjectExperienceSummaryJob) -> None:
        project_id = str(job.project_id or "").strip()
        if not project_id:
            raise ValueError("project_id is required")
        items = [item for item in self._read_project_jobs(project_id) if item.id != job.id]
        items.append(job)
        items.sort(key=lambda item: str(item.updated_at or ""), reverse=True)
        self._write_project_jobs(project_id, items)
