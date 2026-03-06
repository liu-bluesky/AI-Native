"""Feedback upgrade business service (PostgreSQL only)."""

from __future__ import annotations
from dataclasses import replace
from functools import lru_cache
from typing import Any

from config import get_settings
from deps import employee_store
from feedback_store_pg import FeedbackStorePostgres
from llm_provider_service import get_llm_provider_service
from stores import RiskDomain, Rule, Severity, rule_store, rules_now_iso

_ALLOWED_SEVERITY = {"low", "medium", "high", "critical"}
_ALLOWED_REVIEW_ACTION = {"approve", "edit", "reject"}
_ALLOWED_RISK_LEVEL = {"low", "medium", "high"}


class FeedbackService:
    def __init__(self, store: FeedbackStorePostgres, feedback_enabled_global: bool = True) -> None:
        self._store = store
        self._feedback_enabled_global = feedback_enabled_global

    @staticmethod
    def _confidence_by_severity(severity: str) -> float:
        return {
            "critical": 0.95,
            "high": 0.9,
            "medium": 0.8,
            "low": 0.7,
        }.get(severity, 0.75)

    @staticmethod
    def _risk_by_severity(severity: str) -> str:
        return {
            "critical": "high",
            "high": "high",
            "medium": "medium",
            "low": "low",
        }.get(severity, "medium")

    @staticmethod
    def _severity_rank(severity: str) -> int:
        return {
            "low": 1,
            "medium": 2,
            "high": 3,
            "critical": 4,
        }.get(str(severity or "").strip().lower(), 2)

    @staticmethod
    def _normalize_category(value: str) -> str:
        raw = str(value or "").strip().lower()
        if not raw:
            return "general"
        normalized = "".join(ch if (ch.isalnum() or ch in {"-", "_"}) else "-" for ch in raw)
        normalized = "-".join(part for part in normalized.replace("_", "-").split("-") if part)
        return normalized[:64] or "general"

    @staticmethod
    def _normalize_feedback_ids(items: list[str] | None) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in items or []:
            value = str(item or "").strip()
            if not value or value in seen:
                continue
            seen.add(value)
            normalized.append(value)
        return normalized

    @staticmethod
    def _candidate_feedback_ids(candidate: dict[str, Any]) -> list[str]:
        ids = FeedbackService._normalize_feedback_ids(candidate.get("feedback_ids") or [])
        if ids:
            return ids
        fallback = str(candidate.get("feedback_id") or "").strip()
        return [fallback] if fallback else []

    @staticmethod
    def _candidate_status(candidate: dict[str, Any]) -> str:
        return str(candidate.get("status") or "").strip().lower()

    @staticmethod
    def _is_active_candidate(candidate: dict[str, Any]) -> bool:
        return FeedbackService._candidate_status(candidate) in {"pending", "approved"}

    @staticmethod
    def _normalize_rule_id(value: str) -> str:
        return str(value or "").strip()

    def _match_candidate_group(
        self,
        candidate: dict[str, Any],
        employee_id: str,
        category: str,
        target_rule_id: str,
    ) -> bool:
        return (
            str(candidate.get("employee_id") or "").strip() == employee_id
            and self._normalize_category(str(candidate.get("category") or "general")) == category
            and self._normalize_rule_id(str(candidate.get("target_rule_id") or "")) == target_rule_id
        )

    def _find_active_group_candidate(
        self,
        project_id: str,
        employee_id: str,
        category: str,
        target_rule_id: str,
    ) -> dict[str, Any] | None:
        candidates = self._store.list_candidates(
            project_id=project_id,
            status="",
            employee_id=employee_id,
            limit=200,
        )
        for candidate in candidates:
            if not self._is_active_candidate(candidate):
                continue
            if self._match_candidate_group(candidate, employee_id, category, target_rule_id):
                return candidate
        return None

    def _collect_group_bugs(
        self,
        project_id: str,
        feedback_ids: list[str],
        employee_id: str,
        category: str,
        target_rule_id: str,
    ) -> list[dict[str, Any]]:
        bugs: list[dict[str, Any]] = []
        for feedback_id in self._normalize_feedback_ids(feedback_ids):
            bug = self._store.get_bug(project_id, feedback_id)
            if bug is None:
                continue
            if str(bug.get("employee_id") or "").strip() != employee_id:
                continue
            bug_category = self._normalize_category(str(bug.get("category") or "general"))
            bug_rule_id = self._normalize_rule_id(str(bug.get("rule_id") or ""))
            if bug_category != category or bug_rule_id != target_rule_id:
                continue
            bugs.append(bug)
        return bugs

    @staticmethod
    def _compose_publish_content(candidate: dict[str, Any]) -> str:
        proposed = str(candidate.get("proposed_rule_content") or "").strip()
        executable = str(candidate.get("executable_rule_content") or "").strip()
        if not proposed and not executable:
            return ""
        if not executable:
            return proposed
        if not proposed:
            return executable
        if executable in proposed:
            return proposed
        return f"{proposed}\n\n[可执行规则]\n{executable}"

    @staticmethod
    def _build_executable_rule_content(
        bugs: list[dict[str, Any]],
        analysis: dict[str, Any] | None,
        category: str,
    ) -> str:
        _ = bugs
        _ = analysis
        return (
            "规则目标:\n"
            "- 消除前后端字段模型漂移，确保提示词和接口契约一致可执行。\n\n"
            "触发条件:\n"
            f"- {category} 场景下发生接口字段新增/重命名/语义变更。"
        )

    @staticmethod
    def _ensure_employee_feedback_enabled(employee_id: str) -> None:
        employee = employee_store.get(employee_id)
        if employee is None:
            raise LookupError(f"Employee {employee_id} not found")
        if not bool(getattr(employee, "feedback_upgrade_enabled", False)):
            raise ValueError(f"Employee {employee_id} has feedback upgrade disabled")

    @staticmethod
    def _is_default_project_token(value: str) -> bool:
        token = str(value or "").strip().lower()
        return token in {"", "default", "default-project", "default project"}

    @staticmethod
    def _standalone_project_id(employee_id: str) -> str:
        return f"standalone:{employee_id}"

    def _resolve_project_id(self, project_id: str, employee_id: str = "") -> str:
        project_id_value = str(project_id or "").strip()
        employee_id_value = str(employee_id or "").strip()
        if project_id_value and not self._is_default_project_token(project_id_value):
            return project_id_value
        if employee_id_value:
            return self._standalone_project_id(employee_id_value)
        return project_id_value

    def _assert_project_feedback_enabled(self, project_id: str) -> None:
        if not self._feedback_enabled_global:
            raise ValueError("Feedback upgrade is globally disabled")
        cfg = self._store.get_project_config(project_id)
        if not bool(cfg.get("enabled", True)):
            raise ValueError(f"Feedback upgrade is disabled for project {project_id}")

    def get_project_config(self, project_id: str) -> dict[str, Any]:
        cfg = self._store.get_project_config(project_id)
        cfg["enabled_global"] = self._feedback_enabled_global
        return cfg

    def update_project_config(self, project_id: str, enabled: bool) -> dict[str, Any]:
        cfg = self._store.update_project_config(project_id, enabled=bool(enabled))
        cfg["enabled_global"] = self._feedback_enabled_global
        return cfg

    def create_bug(self, project_id: str, payload: dict[str, Any], actor: str = "") -> dict[str, Any]:
        severity = str(payload.get("severity") or "medium").strip().lower()
        if severity not in _ALLOWED_SEVERITY:
            raise ValueError(f"Invalid severity: {severity}")
        employee_id = str(payload.get("employee_id") or "").strip()
        title = str(payload.get("title") or "").strip()
        symptom = str(payload.get("symptom") or "").strip()
        expected = str(payload.get("expected") or "").strip()
        if not employee_id or not title or not symptom or not expected:
            raise ValueError("employee_id/title/symptom/expected are required")
        project_id_value = self._resolve_project_id(project_id, employee_id)
        self._assert_project_feedback_enabled(project_id_value)
        self._ensure_employee_feedback_enabled(employee_id)

        req_payload = dict(payload)
        req_payload["severity"] = severity
        req_payload["category"] = self._normalize_category(str(req_payload.get("category") or "general"))
        if not str(req_payload.get("reporter") or "").strip():
            req_payload["reporter"] = actor or "unknown"
        return self._store.create_bug(project_id_value, req_payload)

    def list_bugs(
        self,
        project_id: str,
        employee_id: str = "",
        category: str = "",
        rule_id: str = "",
        status: str = "",
        severity: str = "",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        project_id_value = self._resolve_project_id(project_id, employee_id)
        try:
            self._assert_project_feedback_enabled(project_id_value)
        except ValueError:
            return []
        if employee_id:
            try:
                self._ensure_employee_feedback_enabled(employee_id)
            except (LookupError, ValueError):
                return []
        return self._store.list_bugs(
            project_id=project_id_value,
            employee_id=employee_id,
            category=self._normalize_category(category) if str(category or "").strip() else "",
            rule_id=str(rule_id or "").strip(),
            status=status,
            severity=severity,
            limit=max(1, min(int(limit), 200)),
        )

    def summarize_bugs_by_category(
        self,
        project_id: str,
        employee_id: str = "",
        rule_id: str = "",
        status: str = "",
        severity: str = "",
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        bugs = self.list_bugs(
            project_id=project_id,
            employee_id=employee_id,
            rule_id=rule_id,
            status=status,
            severity=severity,
            limit=limit,
        )
        grouped: dict[str, dict[str, Any]] = {}
        for bug in bugs:
            category = self._normalize_category(str(bug.get("category") or "general"))
            row = grouped.get(category)
            if row is None:
                row = {
                    "category": category,
                    "total": 0,
                    "new_count": 0,
                    "analyzing_count": 0,
                    "pending_review_count": 0,
                    "closed_count": 0,
                    "analyze_failed_count": 0,
                    "latest_updated_at": "",
                    "feedback_ids": [],
                    "sample_titles": [],
                }
                grouped[category] = row
            row["total"] += 1
            status_value = str(bug.get("status") or "").strip().lower()
            if status_value == "new":
                row["new_count"] += 1
            elif status_value == "analyzing":
                row["analyzing_count"] += 1
            elif status_value == "pending_review":
                row["pending_review_count"] += 1
            elif status_value == "closed":
                row["closed_count"] += 1
            elif status_value == "analyze_failed":
                row["analyze_failed_count"] += 1
            updated_at = str(bug.get("updated_at") or "")
            if updated_at and (not row["latest_updated_at"] or updated_at > row["latest_updated_at"]):
                row["latest_updated_at"] = updated_at
            bug_id = str(bug.get("id") or "")
            if bug_id and len(row["feedback_ids"]) < 20 and bug_id not in row["feedback_ids"]:
                row["feedback_ids"].append(bug_id)
            title = str(bug.get("title") or "").strip()
            if title and len(row["sample_titles"]) < 3 and title not in row["sample_titles"]:
                row["sample_titles"].append(title)
        return sorted(grouped.values(), key=lambda item: (-item["total"], item["category"]))

    def get_bug_detail(self, project_id: str, feedback_id: str, employee_id: str = "") -> dict[str, Any]:
        project_id_value = self._resolve_project_id(project_id, employee_id)
        bug = self._store.get_bug(project_id_value, feedback_id)
        if bug is None:
            raise LookupError(f"Feedback bug {feedback_id} not found")
        candidates = self._store.list_candidates(project_id_value, feedback_id=feedback_id, limit=50)
        candidate_ids = [str(item.get("id") or "").strip() for item in candidates if str(item.get("id") or "").strip()]
        reviews = self._store.list_reviews_by_feedback(project_id_value, feedback_id, limit=100)
        related_reviews = self._store.list_reviews_by_candidate_ids(project_id_value, candidate_ids, limit=100)
        merged_reviews: list[dict[str, Any]] = []
        seen_review_ids: set[str] = set()
        for item in reviews + related_reviews:
            review_id = str(item.get("id") or "").strip()
            if review_id and review_id in seen_review_ids:
                continue
            if review_id:
                seen_review_ids.add(review_id)
            merged_reviews.append(item)
        merged_reviews.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return {
            "bug": bug,
            "analysis": self._store.get_analysis(project_id_value, feedback_id),
            "candidates": candidates,
            "reviews": merged_reviews[:100],
        }

    def delete_bug(self, project_id: str, feedback_id: str, employee_id: str = "") -> dict[str, Any]:
        feedback_id_value = str(feedback_id or "").strip()
        if not feedback_id_value:
            raise ValueError("feedback_id is required")
        employee_id_value = str(employee_id or "").strip()
        project_id_value = self._resolve_project_id(project_id, employee_id_value)
        bug = self._store.get_bug(project_id_value, feedback_id_value)
        if bug is None:
            raise LookupError(f"Feedback bug {feedback_id_value} not found")
        if employee_id_value and str(bug.get("employee_id") or "") != employee_id_value:
            raise ValueError(f"Feedback bug {feedback_id_value} does not belong to employee {employee_id_value}")
        deleted = self._store.delete_bug(project_id_value, feedback_id_value)
        if not deleted.get("deleted_bug"):
            raise RuntimeError(f"Failed to delete feedback bug {feedback_id_value}")
        return {"feedback_id": feedback_id_value, **deleted}

    def delete_bugs(
        self,
        project_id: str,
        feedback_ids: list[str],
        employee_id: str = "",
    ) -> dict[str, Any]:
        normalized_ids: list[str] = []
        seen: set[str] = set()
        for item in feedback_ids or []:
            value = str(item or "").strip()
            if not value or value in seen:
                continue
            seen.add(value)
            normalized_ids.append(value)
        if not normalized_ids:
            raise ValueError("feedback_ids is required")

        deleted_items: list[dict[str, Any]] = []
        missing_ids: list[str] = []
        skipped_ids: list[str] = []
        employee_id_value = str(employee_id or "").strip()
        project_id_value = self._resolve_project_id(project_id, employee_id_value)

        for feedback_id in normalized_ids:
            bug = self._store.get_bug(project_id_value, feedback_id)
            if bug is None:
                missing_ids.append(feedback_id)
                continue
            if employee_id_value and str(bug.get("employee_id") or "") != employee_id_value:
                skipped_ids.append(feedback_id)
                continue
            deleted = self._store.delete_bug(project_id_value, feedback_id)
            if deleted.get("deleted_bug"):
                deleted_items.append({"feedback_id": feedback_id, **deleted})
            else:
                skipped_ids.append(feedback_id)

        return {
            "requested_count": len(normalized_ids),
            "deleted_count": len(deleted_items),
            "deleted_items": deleted_items,
            "missing_ids": missing_ids,
            "skipped_ids": skipped_ids,
        }

    def _build_reflection(self, bug: dict[str, Any]) -> dict[str, Any]:
        symptom = bug.get("symptom", "")
        expected = bug.get("expected", "")
        direct_cause = f"在场景中出现了偏差：{symptom[:120]}" if symptom else "规则执行与预期不一致"
        root_cause = f"缺少针对目标结果的约束：{expected[:120]}" if expected else "规则缺乏上下文约束"
        evidence_refs = []
        if bug.get("session_id"):
            evidence_refs.append({"type": "session", "id": bug["session_id"]})
        if bug.get("rule_id"):
            evidence_refs.append({"type": "rule", "id": bug["rule_id"]})
        confidence = self._confidence_by_severity(str(bug.get("severity") or "medium"))
        reflection_output = {
            "summary": f"反馈“{bug.get('title', '')}”的主要问题是输出与预期不一致。",
            "direct_cause": direct_cause,
            "root_cause": root_cause,
            "next_action": "生成规则候选并进入审核",
        }
        return {
            "bug_type": "rule_mismatch",
            "direct_cause": direct_cause,
            "root_cause": root_cause,
            "evidence_refs": evidence_refs,
            "confidence": confidence,
            "model_name": "heuristic-reflector-v1",
            "reflection_output": reflection_output,
        }

    def _build_reflection_by_model(
        self,
        project_id: str,
        bug: dict[str, Any],
        analyze_options: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], bool]:
        options = analyze_options or {}
        employee_id = str(bug.get("employee_id") or "").strip()
        provider_id = str(options.get("provider_id") or "").strip()
        model_name = str(options.get("model_name") or "").strip()
        temperature = options.get("temperature")
        use_explicit_model = bool(provider_id or model_name)
        llm_service = get_llm_provider_service()

        if use_explicit_model and not provider_id:
            raise ValueError("provider_id is required when model_name is provided")

        target = llm_service.resolve_reflection_target(
            project_id=project_id,
            employee_id=employee_id,
            preferred_provider_id=provider_id,
            preferred_model_name=model_name,
            preferred_temperature=temperature,
        )
        if target is None:
            return self._build_reflection(bug), False

        try:
            reflection = llm_service.reflect_bug(
                bug=bug,
                provider_id=str(target.get("provider_id") or ""),
                model_name=str(target.get("model_name") or ""),
                temperature=float(target.get("temperature") if target.get("temperature") is not None else 0.2),
            )
            return reflection, True
        except (LookupError, ValueError):
            raise
        except Exception as exc:
            if use_explicit_model:
                raise RuntimeError(f"模型反思失败: {exc}") from exc
            fallback = self._build_reflection(bug)
            fallback["model_name"] = f"heuristic-reflector-v1 (fallback: {exc})"
            return fallback, False

    def _build_candidate_payload(self, bugs: list[dict[str, Any]], analysis: dict[str, Any]) -> dict[str, Any]:
        if not bugs:
            raise ValueError("bugs is required")
        bug = bugs[0]
        old_rule_content = ""
        if bug.get("rule_id"):
            target_rule = rule_store.get(bug["rule_id"])
            if target_rule is not None:
                old_rule_content = target_rule.content

        # 候选“编辑内容”仅保留原版规则内容，不再自动拼接反馈驱动建议块。
        proposed_content = old_rule_content
        executable_rule_content = self._build_executable_rule_content(
            bugs=bugs,
            analysis=analysis,
            category=self._normalize_category(str(bug.get("category") or "general")),
        )
        return {
            "employee_id": bug.get("employee_id", ""),
            "category": self._normalize_category(str(bug.get("category") or "general")),
            "target_rule_id": bug.get("rule_id", ""),
            "old_rule_content": old_rule_content,
            "proposed_rule_content": proposed_content,
            "executable_rule_content": executable_rule_content,
            "risk_level": self._risk_by_severity(str(bug.get("severity") or "medium")),
            "confidence": float(analysis.get("confidence") or 0),
            "status": "pending",
            "review_comment": "",
            "source": "analysis",
            "feedback_ids": self._normalize_feedback_ids([str(item.get("id") or "").strip() for item in bugs]),
        }

    def create_manual_candidate(
        self,
        project_id: str,
        payload: dict[str, Any],
        actor: str = "",
    ) -> dict[str, Any]:
        employee_id = str(payload.get("employee_id") or "").strip()
        if not employee_id:
            raise ValueError("employee_id is required")
        project_id_value = self._resolve_project_id(project_id, employee_id)
        self._assert_project_feedback_enabled(project_id_value)
        self._ensure_employee_feedback_enabled(employee_id)

        proposed_rule_content = str(payload.get("proposed_rule_content") or "").strip()
        if not proposed_rule_content:
            raise ValueError("proposed_rule_content is required")

        feedback_ids = self._normalize_feedback_ids(payload.get("feedback_ids") or [])
        if not feedback_ids:
            raise ValueError("feedback_ids is required for manual upgrade")
        feedback_id = feedback_ids[0]
        bugs: list[dict[str, Any]] = []
        for item in feedback_ids:
            bug_item = self._store.get_bug(project_id_value, item)
            if bug_item is None:
                raise LookupError(f"Feedback bug {item} not found")
            if str(bug_item.get("employee_id") or "") != employee_id:
                raise ValueError("feedback_id does not belong to employee_id")
            bugs.append(bug_item)
        bug = bugs[0]
        category = self._normalize_category(str(payload.get("category") or bug.get("category") or "general"))

        target_rule_id = str(payload.get("target_rule_id") or "").strip()
        old_rule_content = ""
        if target_rule_id:
            target_rule = rule_store.get(target_rule_id)
            if target_rule is None:
                raise LookupError(f"Rule {target_rule_id} not found")
            old_rule_content = target_rule.content

        risk_level = str(payload.get("risk_level") or "medium").strip().lower()
        if risk_level not in _ALLOWED_RISK_LEVEL:
            raise ValueError(f"Invalid risk_level: {risk_level}")
        try:
            confidence = float(payload.get("confidence") if payload.get("confidence") is not None else 0.8)
        except (TypeError, ValueError):
            confidence = 0.8
        confidence = max(0.0, min(confidence, 1.0))
        active_candidate = self._find_active_group_candidate(
            project_id=project_id_value,
            employee_id=employee_id,
            category=category,
            target_rule_id=target_rule_id,
        )
        combined_feedback_ids = self._normalize_feedback_ids(
            (active_candidate or {}).get("feedback_ids") or []
            + feedback_ids
        )
        grouped_bugs = self._collect_group_bugs(
            project_id=project_id_value,
            feedback_ids=combined_feedback_ids,
            employee_id=employee_id,
            category=category,
            target_rule_id=target_rule_id,
        )
        if not grouped_bugs:
            raise ValueError("No valid feedbacks found for candidate group")

        executable_rule_content = str(payload.get("executable_rule_content") or "").strip()
        if not executable_rule_content:
            analysis = self._store.get_analysis(project_id_value, feedback_id)
            executable_rule_content = self._build_executable_rule_content(
                bugs=grouped_bugs,
                analysis=analysis,
                category=category,
            )

        candidate_payload = {
            "employee_id": employee_id,
            "category": category,
            "target_rule_id": target_rule_id,
            "old_rule_content": old_rule_content,
            "proposed_rule_content": proposed_rule_content,
            "risk_level": risk_level,
            "confidence": confidence,
            "status": "pending",
            "review_comment": str(payload.get("comment") or "").strip(),
            "executable_rule_content": executable_rule_content,
            "created_by": actor or "unknown",
            "source": "manual",
            "feedback_ids": combined_feedback_ids,
        }
        if active_candidate:
            candidate = self._store.patch_candidate(
                project_id_value,
                active_candidate["id"],
                candidate_payload,
            )
            if candidate is None:
                raise RuntimeError("Failed to update candidate")
        else:
            candidate = self._store.create_candidate(
                project_id_value,
                feedback_id,
                candidate_payload,
            )
        for item in combined_feedback_ids:
            self._store.patch_bug(project_id_value, item, {"status": "pending_review"})
        return candidate

    def analyze_bug(
        self,
        project_id: str,
        feedback_id: str,
        analyze_options: dict[str, Any] | None = None,
        employee_id: str = "",
    ) -> dict[str, Any]:
        project_id_value = self._resolve_project_id(project_id, employee_id)
        self._assert_project_feedback_enabled(project_id_value)
        bug = self._store.get_bug(project_id_value, feedback_id)
        if bug is None:
            raise LookupError(f"Feedback bug {feedback_id} not found")
        self._ensure_employee_feedback_enabled(str(bug.get("employee_id") or ""))

        self._store.patch_bug(project_id_value, feedback_id, {"status": "analyzing"})
        reflection, used_model = self._build_reflection_by_model(
            project_id=project_id_value,
            bug=bug,
            analyze_options=analyze_options,
        )
        analysis = self._store.upsert_analysis(project_id_value, feedback_id, reflection)

        employee_id = str(bug.get("employee_id") or "").strip()
        category = self._normalize_category(str(bug.get("category") or "general"))
        target_rule_id = self._normalize_rule_id(str(bug.get("rule_id") or ""))
        active_candidate = self._find_active_group_candidate(
            project_id=project_id_value,
            employee_id=employee_id,
            category=category,
            target_rule_id=target_rule_id,
        )
        merged_feedback_ids = self._normalize_feedback_ids(
            (active_candidate or {}).get("feedback_ids") or []
            + [feedback_id]
        )
        grouped_bugs = self._collect_group_bugs(
            project_id=project_id_value,
            feedback_ids=merged_feedback_ids,
            employee_id=employee_id,
            category=category,
            target_rule_id=target_rule_id,
        )
        bug_id = str(bug.get("id") or "").strip()
        if bug_id and all(str(item.get("id") or "").strip() != bug_id for item in grouped_bugs):
            grouped_bugs = [bug, *grouped_bugs]
        candidate_payload = self._build_candidate_payload(grouped_bugs, analysis)
        if active_candidate:
            candidate = self._store.patch_candidate(
                project_id_value,
                active_candidate["id"],
                {
                    "proposed_rule_content": candidate_payload["proposed_rule_content"],
                    "executable_rule_content": candidate_payload["executable_rule_content"],
                    "old_rule_content": candidate_payload["old_rule_content"],
                    "risk_level": candidate_payload["risk_level"],
                    "confidence": candidate_payload["confidence"],
                    "status": "pending",
                    "feedback_ids": candidate_payload["feedback_ids"],
                },
            )
        else:
            candidate = self._store.create_candidate(project_id_value, feedback_id, candidate_payload)

        if candidate is None:
            raise RuntimeError("Failed to generate candidate")
        for bug_item in grouped_bugs:
            bug_id = str(bug_item.get("id") or "").strip()
            if bug_id:
                self._store.patch_bug(project_id_value, bug_id, {"status": "pending_review"})
        return {"analysis": analysis, "candidate": candidate, "used_model": used_model}

    def analyze_bugs_batch(
        self,
        project_id: str,
        feedback_ids: list[str],
        analyze_options: dict[str, Any] | None = None,
        employee_id: str = "",
    ) -> dict[str, Any]:
        project_id_value = self._resolve_project_id(project_id, employee_id)
        self._assert_project_feedback_enabled(project_id_value)
        normalized_ids = self._normalize_feedback_ids(feedback_ids)
        if not normalized_ids:
            raise ValueError("feedback_ids is required")

        bugs: list[dict[str, Any]] = []
        for feedback_id in normalized_ids:
            bug = self._store.get_bug(project_id_value, feedback_id)
            if bug is None:
                raise LookupError(f"Feedback bug {feedback_id} not found")
            bugs.append(bug)

        primary = bugs[0]
        employee_id = str(primary.get("employee_id") or "").strip()
        target_rule_id = self._normalize_rule_id(str((analyze_options or {}).get("target_rule_id") or ""))
        if not target_rule_id:
            raise ValueError("target_rule_id is required for batch analyze")
        target_rule = rule_store.get(target_rule_id)
        if target_rule is None:
            raise LookupError(f"Rule {target_rule_id} not found")
        category = self._normalize_category(str(target_rule.domain or primary.get("category") or "general"))
        self._ensure_employee_feedback_enabled(employee_id)
        for bug in bugs[1:]:
            if str(bug.get("employee_id") or "").strip() != employee_id:
                raise ValueError("All feedback_ids must belong to the same employee")

        merged_bug = dict(primary)
        merged_bug["title"] = "批量反馈综合分析"
        merged_bug["rule_id"] = target_rule_id
        merged_bug["category"] = category
        merged_bug["symptom"] = "；".join(
            [str(item.get("symptom") or "").strip() for item in bugs if str(item.get("symptom") or "").strip()][:8]
        )
        merged_bug["expected"] = "；".join(
            [str(item.get("expected") or "").strip() for item in bugs if str(item.get("expected") or "").strip()][:8]
        )
        merged_bug["severity"] = max(
            [str(item.get("severity") or "medium").strip().lower() for item in bugs],
            key=self._severity_rank,
        )

        aggregate_bug = self._store.create_bug(
            project_id_value,
            {
                "employee_id": employee_id,
                "category": category,
                "session_id": "",
                "rule_id": target_rule_id,
                "title": "批量反馈综合分析",
                "symptom": merged_bug["symptom"],
                "expected": merged_bug["expected"],
                "severity": merged_bug["severity"],
                "reporter": "batch-analyze",
                "source_context": {
                    "batch_mode": True,
                    "batch_feedback_ids": normalized_ids,
                    "batch_target_rule_id": target_rule_id,
                },
            },
        )
        self._store.patch_bug(project_id_value, aggregate_bug["id"], {"status": "analyzing"})

        reflection, used_model = self._build_reflection_by_model(
            project_id=project_id_value,
            bug=merged_bug,
            analyze_options=analyze_options,
        )

        analysis = self._store.upsert_analysis(project_id_value, aggregate_bug["id"], reflection)
        candidate_payload = self._build_candidate_payload([merged_bug], analysis)
        candidate_payload["target_rule_id"] = target_rule_id
        candidate_payload["feedback_ids"] = [aggregate_bug["id"]]
        candidate_payload["source_feedback_ids"] = normalized_ids

        existing = self._store.list_candidates(project_id_value, feedback_id=aggregate_bug["id"], limit=1)
        if existing:
            candidate = self._store.patch_candidate(
                project_id_value,
                existing[0]["id"],
                {
                    "proposed_rule_content": candidate_payload["proposed_rule_content"],
                    "executable_rule_content": candidate_payload["executable_rule_content"],
                    "old_rule_content": candidate_payload["old_rule_content"],
                    "risk_level": candidate_payload["risk_level"],
                    "confidence": candidate_payload["confidence"],
                    "status": "pending",
                    "feedback_ids": candidate_payload["feedback_ids"],
                    "source_feedback_ids": candidate_payload["source_feedback_ids"],
                },
            )
        else:
            candidate = self._store.create_candidate(project_id_value, aggregate_bug["id"], candidate_payload)

        if candidate is None:
            raise RuntimeError("Failed to generate candidate")
        self._store.patch_bug(project_id_value, aggregate_bug["id"], {"status": "pending_review"})
        return {
            "analysis": analysis,
            "bug": self._store.get_bug(project_id_value, aggregate_bug["id"]) or aggregate_bug,
            "candidate": candidate,
            "used_model": used_model,
            "feedback_ids": normalized_ids,
        }

    def list_candidates(
        self,
        project_id: str,
        status: str = "pending",
        employee_id: str = "",
        feedback_id: str = "",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        project_id_value = self._resolve_project_id(project_id, employee_id)
        try:
            self._assert_project_feedback_enabled(project_id_value)
        except ValueError:
            return []
        if employee_id:
            try:
                self._ensure_employee_feedback_enabled(employee_id)
            except (LookupError, ValueError):
                return []
        return self._store.list_candidates(
            project_id=project_id_value,
            status=status,
            employee_id=employee_id,
            feedback_id=feedback_id,
            limit=max(1, min(int(limit), 200)),
        )

    def review_candidate(
        self,
        project_id: str,
        candidate_id: str,
        reviewed_by: str,
        action: str,
        comment: str = "",
        edited_content: str = "",
        edited_executable_content: str = "",
        employee_id: str = "",
    ) -> dict[str, Any]:
        project_id_value = self._resolve_project_id(project_id, employee_id)
        self._assert_project_feedback_enabled(project_id_value)
        action_value = str(action or "").strip().lower()
        if action_value not in _ALLOWED_REVIEW_ACTION:
            raise ValueError(f"Invalid action: {action}")

        candidate = self._store.get_candidate(project_id_value, candidate_id)
        if candidate is None:
            raise LookupError(f"Candidate {candidate_id} not found")
        employee_id_value = str(employee_id or "").strip()
        if employee_id_value and str(candidate.get("employee_id") or "").strip() != employee_id_value:
            raise ValueError(f"Candidate {candidate_id} does not belong to employee {employee_id_value}")
        self._ensure_employee_feedback_enabled(str(candidate.get("employee_id") or ""))

        updates: dict[str, Any] = {
            "reviewer": reviewed_by,
            "review_comment": comment,
        }
        if action_value == "approve":
            updates["status"] = "approved"
        elif action_value == "reject":
            updates["status"] = "rejected"
        else:
            if not str(edited_content or "").strip():
                raise ValueError("edited_content is required when action='edit'")
            updates["status"] = "approved"
            updates["proposed_rule_content"] = edited_content
            if str(edited_executable_content or "").strip():
                updates["executable_rule_content"] = edited_executable_content

        updated = self._store.patch_candidate(project_id_value, candidate_id, updates)
        if updated is None:
            raise LookupError(f"Candidate {candidate_id} not found")

        self._store.create_review(
            project_id_value,
            candidate["feedback_id"],
            candidate_id,
            {
                "reviewer": reviewed_by,
                "action": action_value,
                "comment": comment,
                "edited_content": edited_content,
                "edited_executable_content": edited_executable_content,
            },
        )
        return updated

    def publish_candidate(
        self,
        project_id: str,
        candidate_id: str,
        published_by: str = "",
        comment: str = "",
        employee_id: str = "",
    ) -> dict[str, Any]:
        project_id_value = self._resolve_project_id(project_id, employee_id)
        self._assert_project_feedback_enabled(project_id_value)
        candidate = self._store.get_candidate(project_id_value, candidate_id)
        if candidate is None:
            raise LookupError(f"Candidate {candidate_id} not found")
        employee_id_value = str(employee_id or "").strip()
        if employee_id_value and str(candidate.get("employee_id") or "").strip() != employee_id_value:
            raise ValueError(f"Candidate {candidate_id} does not belong to employee {employee_id_value}")
        self._ensure_employee_feedback_enabled(str(candidate.get("employee_id") or ""))
        if candidate.get("status") != "approved":
            raise ValueError("Only approved candidates can be published")

        publish_content = self._compose_publish_content(candidate)
        if not publish_content:
            raise ValueError("Candidate content is empty")
        target_rule_id = str(candidate.get("target_rule_id") or "").strip()
        if target_rule_id:
            target_rule = rule_store.get(target_rule_id)
            if target_rule is None:
                raise LookupError(f"Rule {target_rule_id} not found")
            updated_rule = replace(
                target_rule,
                content=publish_content,
                updated_at=rules_now_iso(),
            )
            rule_store.save(updated_rule)
        else:
            bug = self._store.get_bug(project_id_value, str(candidate.get("feedback_id") or ""))
            category = self._normalize_category(str(candidate.get("category") or "general"))
            title_seed = str((bug or {}).get("title") or f"{category} upgrade").strip()
            new_rule = Rule(
                id=rule_store.new_id(),
                domain=category,
                title=f"[反馈升级] {title_seed}"[:80],
                content=publish_content,
                severity=Severity.RECOMMENDED,
                risk_domain=RiskDomain.MEDIUM,
                updated_at=rules_now_iso(),
            )
            rule_store.save(new_rule)
            target_rule_id = new_rule.id

        updated = self._store.patch_candidate(
            project_id_value,
            candidate_id,
            {
                "status": "published",
                "target_rule_id": target_rule_id,
                "reviewer": published_by,
                "review_comment": comment,
                "published_rule_content": publish_content,
            },
        )
        if updated is None:
            raise LookupError(f"Candidate {candidate_id} not found")

        for feedback_id in self._candidate_feedback_ids(candidate):
            self._store.patch_bug(project_id_value, feedback_id, {"status": "closed"})
        return updated

    def rollback_candidate(
        self,
        project_id: str,
        candidate_id: str,
        rolled_back_by: str = "",
        comment: str = "",
        employee_id: str = "",
    ) -> dict[str, Any]:
        project_id_value = self._resolve_project_id(project_id, employee_id)
        self._assert_project_feedback_enabled(project_id_value)
        candidate = self._store.get_candidate(project_id_value, candidate_id)
        if candidate is None:
            raise LookupError(f"Candidate {candidate_id} not found")
        employee_id_value = str(employee_id or "").strip()
        if employee_id_value and str(candidate.get("employee_id") or "").strip() != employee_id_value:
            raise ValueError(f"Candidate {candidate_id} does not belong to employee {employee_id_value}")
        self._ensure_employee_feedback_enabled(str(candidate.get("employee_id") or ""))
        if candidate.get("status") != "published":
            raise ValueError("Only published candidates can be rolled back")

        target_rule_id = candidate.get("target_rule_id") or ""
        old_content = candidate.get("old_rule_content") or ""
        if target_rule_id and old_content:
            target_rule = rule_store.get(target_rule_id)
            if target_rule is None:
                raise LookupError(f"Rule {target_rule_id} not found")
            restored = replace(target_rule, content=old_content, updated_at=rules_now_iso())
            rule_store.save(restored)

        updated = self._store.patch_candidate(
            project_id_value,
            candidate_id,
            {
                "status": "rolled_back",
                "reviewer": rolled_back_by,
                "review_comment": comment,
            },
        )
        if updated is None:
            raise LookupError(f"Candidate {candidate_id} not found")

        for feedback_id in self._candidate_feedback_ids(candidate):
            self._store.patch_bug(project_id_value, feedback_id, {"status": "pending_review"})
        return updated


@lru_cache(maxsize=1)
def get_feedback_service() -> FeedbackService:
    settings = get_settings()
    if settings.core_store_backend != "postgres":
        raise RuntimeError("Feedback module requires CORE_STORE_BACKEND=postgres")
    return FeedbackService(
        FeedbackStorePostgres(settings.database_url),
        feedback_enabled_global=settings.feedback_upgrade_enabled_global,
    )
