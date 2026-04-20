"""后台项目经验总结执行器。"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from typing import Any

from stores.json.project_experience_summary_store import ProjectExperienceSummaryJob
from stores.json.project_store import _now_iso

logger = logging.getLogger(__name__)

_ACTIVE_STATUSES = {"queued", "processing"}


def _normalize_text(value: Any, *, limit: int = 1000) -> str:
    return str(value or "").strip()[:limit]


class ProjectExperienceSummaryBackgroundService:
    def __init__(
        self,
        *,
        project_store: Any,
        project_experience_summary_store: Any,
        poll_interval_seconds: int = 5,
    ) -> None:
        self._project_store = project_store
        self._project_experience_summary_store = project_experience_summary_store
        self._poll_interval_seconds = max(2, int(poll_interval_seconds or 5))
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._run_lock = asyncio.Lock()

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(
            self._run_loop(),
            name="project-experience-summary-worker",
        )

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.run_pending_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("project experience summary worker loop failed")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._poll_interval_seconds)
            except asyncio.TimeoutError:
                continue

    async def run_pending_once(self) -> None:
        if self._run_lock.locked():
            return
        async with self._run_lock:
            for project in self._project_store.list_all():
                project_id = _normalize_text(getattr(project, "id", ""), limit=120)
                if not project_id:
                    continue
                queued_jobs = self._project_experience_summary_store.list_by_project(
                    project_id,
                    status="queued",
                    limit=20,
                )
                for queued_job in queued_jobs:
                    await self._process_job(project_id, queued_job.id)

    async def _process_job(self, project_id: str, job_id: str) -> None:
        current = self._project_experience_summary_store.get(project_id, job_id)
        if current is None or current.status != "queued":
            return
        now = _now_iso()
        processing_job = replace(
            current,
            status="processing",
            progress=max(5, int(current.progress or 0)),
            stage="summarizing",
            status_message="正在提炼候选开发经验卡片",
            started_at=now,
            updated_at=now,
            error_code="",
            error_message="",
            error_details={},
            finished_at="",
        )
        self._project_experience_summary_store.save(processing_job)
        try:
            await self._execute_job(processing_job)
        except Exception as exc:
            failed_job = self._project_experience_summary_store.get(project_id, job_id)
            if failed_job is None:
                return
            self._project_experience_summary_store.save(
                replace(
                    failed_job,
                    status="failed",
                    progress=100,
                    stage="failed",
                    status_message="总结任务执行失败",
                    error_code=type(exc).__name__,
                    error_message=_normalize_text(str(exc), limit=2000) or "总结任务执行失败",
                    error_details={},
                    finished_at=_now_iso(),
                    updated_at=_now_iso(),
                )
            )

    async def _execute_job(self, job: ProjectExperienceSummaryJob) -> None:
        from models.requests import ProjectRequirementRecordBatchDeleteReq
        from routers import projects as projects_router

        project = self._project_store.get(job.project_id)
        if project is None:
            raise RuntimeError(f"Project {job.project_id} not found")

        auth_payload = {
            "sub": _normalize_text(job.created_by, limit=120) or "system",
            "role": "admin",
        }
        source_records = [item for item in (job.source_records or []) if isinstance(item, dict)]
        source_record_ids = [
            projects_router._normalize_project_record_token(item.get("id"), limit=80)
            for item in source_records
        ]
        source_record_ids = [item for item in source_record_ids if item]
        if not source_records or not source_record_ids:
            raise RuntimeError("没有可用于总结的需求记录")

        cards = await projects_router._summarize_project_experience_cards(
            project,
            provider_id=job.provider_id,
            model_name=job.model_name,
            records=source_records,
            max_cards=int(job.max_cards or 5),
            auth_payload=auth_payload,
        )
        self._save_job_update(
            job.project_id,
            job.id,
            progress=48,
            stage="reviewing",
            status_message="正在执行经验入库门禁评审",
            source_record_ids=source_record_ids,
            source_record_count=len(source_records),
            source_records=source_records,
            candidate_card_count=len(cards),
        )

        review_result = await projects_router._review_project_experience_cards(
            project,
            records=source_records,
            candidate_cards=cards,
            auth_payload=auth_payload,
            provider_id=job.provider_id,
            model_name=job.model_name,
            experience_scope=job.experience_scope,
            min_confidence=float(job.min_review_confidence),
            max_evidence_snippets_per_record=int(job.max_evidence_snippets_per_record or 2),
        )
        approved_cards = [
            item
            for item in (review_result.get("approved_cards") if isinstance(review_result, dict) else [])
            if isinstance(item, dict)
        ]

        updated_project = project
        created_rule_ids: list[str] = []
        updated_rule_ids: list[str] = []
        if approved_cards:
            self._save_job_update(
                job.project_id,
                job.id,
                progress=76,
                stage="upserting_rules",
                status_message="正在写入经验规则",
                approved_card_count=len(approved_cards),
            )
            updated_project, created_rule_ids, updated_rule_ids = await projects_router._upsert_project_experience_rules(
                project,
                approved_cards,
                auth_payload=auth_payload,
                experience_scope=job.experience_scope,
                provider_id=job.provider_id,
                model_name=job.model_name,
            )

        clear_result: dict[str, Any] | None = None
        should_clear_requirement_records = bool(
            job.review_mode == "auto"
            and job.clear_requirement_records_requested
            and isinstance(review_result, dict)
            and bool((review_result.get("summary") or {}).get("allow_clear_requirement_records"))
        )
        if should_clear_requirement_records:
            self._save_job_update(
                job.project_id,
                job.id,
                progress=92,
                stage="clearing_records",
                status_message="正在清理已沉淀的源需求记录",
            )
            clear_result = await projects_router.batch_delete_project_requirement_records(
                job.project_id,
                ProjectRequirementRecordBatchDeleteReq(record_ids=source_record_ids),
                auth_payload,
            )

        if not approved_cards:
            status = "review_blocked"
        elif job.review_mode == "manual":
            status = "partial_completed"
        elif job.clear_requirement_records_requested and not should_clear_requirement_records:
            status = "partial_completed"
        else:
            status = "completed"

        terminal_stage = {
            "completed": "completed",
            "partial_completed": "partial_completed",
            "review_blocked": "review_blocked",
        }.get(status, "completed")
        terminal_message = {
            "completed": "经验总结完成",
            "partial_completed": "经验已入库，仍保留部分源记录",
            "review_blocked": "经验评审未通过，未写入规则库",
        }.get(status, "经验总结完成")

        current = self._project_experience_summary_store.get(job.project_id, job.id)
        if current is None:
            return
        self._project_experience_summary_store.save(
            replace(
                current,
                status=status,
                progress=100,
                stage=terminal_stage,
                status_message=terminal_message,
                source_record_ids=source_record_ids,
                source_records=source_records,
                source_record_count=len(source_records),
                candidate_card_count=len(cards),
                approved_card_count=len(approved_cards),
                created_rule_ids=created_rule_ids,
                updated_rule_ids=updated_rule_ids,
                experience_rule_ids=projects_router._normalize_project_experience_rule_ids(
                    getattr(updated_project, "experience_rule_ids", []) or []
                ),
                experience_rule_bindings=projects_router._resolve_project_experience_rule_bindings(updated_project),
                review_result=(
                    {
                        "cards": review_result.get("cards"),
                        "summary": review_result.get("summary"),
                        "records": review_result.get("records"),
                    }
                    if isinstance(review_result, dict)
                    else {}
                ),
                clear_result=clear_result or {},
                clear_requirement_records_executed=should_clear_requirement_records,
                manual_review_required=job.review_mode == "manual",
                error_code="",
                error_message="",
                error_details={},
                finished_at=_now_iso(),
                updated_at=_now_iso(),
            )
        )

    def _save_job_update(self, project_id: str, job_id: str, **updates: Any) -> None:
        current = self._project_experience_summary_store.get(project_id, job_id)
        if current is None or current.status not in _ACTIVE_STATUSES:
            return
        updates["updated_at"] = _now_iso()
        self._project_experience_summary_store.save(replace(current, **updates))
