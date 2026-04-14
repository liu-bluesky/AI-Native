"""Task tree evolution summary helpers."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from typing import Any, Iterable

from core.deps import task_tree_evolution_store
from stores.json.task_tree_evolution_store import TaskTreeEvolutionSample


def _normalize_counter_limit(value: int | None, *, default: int = 5) -> int:
    try:
        normalized = int(value or default)
    except (TypeError, ValueError):
        normalized = default
    return max(1, min(normalized, 20))


def _top_counts(
    values: Iterable[str],
    *,
    key_name: str,
    limit: int,
) -> list[dict[str, Any]]:
    counter = Counter(str(value or "").strip() for value in values if str(value or "").strip())
    return [
        {
            key_name: item,
            "count": count,
        }
        for item, count in counter.most_common(limit)
    ]


def serialize_task_tree_evolution_sample(sample: TaskTreeEvolutionSample) -> dict[str, Any]:
    return asdict(sample)


def summarize_task_tree_evolution_samples(
    samples: list[TaskTreeEvolutionSample],
    *,
    top_limit: int = 5,
) -> dict[str, Any]:
    safe_top_limit = _normalize_counter_limit(top_limit)
    ordered_samples = sorted(
        list(samples or []),
        key=lambda item: (str(getattr(item, "created_at", "") or ""), str(getattr(item, "id", "") or "")),
        reverse=True,
    )
    recent_samples = [
        serialize_task_tree_evolution_sample(item)
        for item in ordered_samples[:safe_top_limit]
    ]
    latest_created_at = str(ordered_samples[0].created_at or "") if ordered_samples else ""
    return {
        "total_samples": len(ordered_samples),
        "latest_created_at": latest_created_at,
        "user_visible_count": sum(1 for item in ordered_samples if bool(item.user_visible)),
        "manually_corrected_count": sum(
            1 for item in ordered_samples if bool(item.manually_corrected)
        ),
        "rebuild_successful_count": sum(
            1 for item in ordered_samples if bool(item.rebuild_successful)
        ),
        "top_issue_codes": _top_counts(
            (item.issue_code for item in ordered_samples),
            key_name="issue_code",
            limit=safe_top_limit,
        ),
        "top_wrong_templates": _top_counts(
            (item.wrong_template for item in ordered_samples),
            key_name="wrong_template",
            limit=safe_top_limit,
        ),
        "top_detected_intents": _top_counts(
            (item.detected_intent for item in ordered_samples),
            key_name="detected_intent",
            limit=safe_top_limit,
        ),
        "top_source_kinds": _top_counts(
            (item.source_kind for item in ordered_samples),
            key_name="source_kind",
            limit=safe_top_limit,
        ),
        "top_evidence_patterns": _top_counts(
            (
                evidence
                for item in ordered_samples
                for evidence in list(item.evidence or [])
            ),
            key_name="evidence",
            limit=safe_top_limit,
        ),
        "recent_samples": recent_samples,
    }


def build_task_tree_evolution_summary(
    *,
    project_id: str,
    chat_session_id: str = "",
    task_tree_session_id: str = "",
    issue_code: str = "",
    source_kind: str = "",
    limit: int = 200,
    top_limit: int = 5,
) -> dict[str, Any]:
    samples = task_tree_evolution_store.list_samples(
        project_id=str(project_id or "").strip(),
        chat_session_id=str(chat_session_id or "").strip(),
        task_tree_session_id=str(task_tree_session_id or "").strip(),
        issue_code=str(issue_code or "").strip(),
        source_kind=str(source_kind or "").strip(),
        limit=max(1, min(int(limit or 200), 500)),
    )
    return {
        "project_id": str(project_id or "").strip(),
        "chat_session_id": str(chat_session_id or "").strip(),
        "task_tree_session_id": str(task_tree_session_id or "").strip(),
        "issue_code": str(issue_code or "").strip(),
        "source_kind": str(source_kind or "").strip(),
        "summary": summarize_task_tree_evolution_samples(
            samples,
            top_limit=top_limit,
        ),
    }
