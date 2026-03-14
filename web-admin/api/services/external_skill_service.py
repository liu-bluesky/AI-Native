"""External skill suggestion helpers."""

from __future__ import annotations

import re
from typing import Any

from services.external_skill_catalog import EXTERNAL_SKILL_CATALOG


def _normalize_text_value(value: Any, *, limit: int = 4000) -> str:
    return str(value or "").strip()[:limit]


def _normalize_text_list(values: list[str] | None, *, limit: int = 20, item_limit: int = 240) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for item in values or []:
        text = _normalize_text_value(item, limit=item_limit)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(text)
        if len(normalized) >= limit:
            break
    return normalized


def _normalize_match_key(value: Any) -> str:
    return str(value or "").strip().lower()


def _build_query_tokens(
    *,
    name: str,
    description: str,
    goal: str,
    skills: list[str] | None,
    rule_titles: list[str] | None,
    rule_domains: list[str] | None,
    style_hints: list[str] | None,
    default_workflow: list[str] | None,
    tool_usage_policy: str,
    industry: str = "",
) -> list[str]:
    raw_values = _normalize_text_list(
        [
            name,
            description,
            goal,
            industry,
            *list(skills or []),
            *list(rule_titles or []),
            *list(rule_domains or []),
            *list(style_hints or []),
            *list(default_workflow or []),
            tool_usage_policy,
        ],
        limit=80,
        item_limit=240,
    )
    seen: set[str] = set()
    tokens: list[str] = []
    for value in raw_values:
        for piece in [value, *re.split(r"[\s,，。；;、/|]+", value)]:
            token = _normalize_match_key(piece)
            if not token or len(token) < 2 or token in seen:
                continue
            seen.add(token)
            tokens.append(token)
    return tokens


def suggest_external_skills(
    *,
    name: str,
    description: str,
    goal: str,
    skills: list[str] | None,
    rule_titles: list[str] | None,
    rule_domains: list[str] | None,
    style_hints: list[str] | None,
    default_workflow: list[str] | None,
    tool_usage_policy: str,
    industry: str = "",
    source_filters: list[str] | None = None,
    limit: int = 6,
) -> list[dict[str, Any]]:
    tokens = _build_query_tokens(
        name=name,
        description=description,
        goal=goal,
        skills=skills,
        rule_titles=rule_titles,
        rule_domains=rule_domains,
        style_hints=style_hints,
        default_workflow=default_workflow,
        tool_usage_policy=tool_usage_policy,
        industry=industry,
    )
    normalized_tokens = {token for token in tokens if token}
    normalized_industry = _normalize_match_key(industry)
    allowed_sources = {
        _normalize_match_key(value)
        for value in _normalize_text_list(source_filters, limit=12, item_limit=120)
    }

    scored: list[dict[str, Any]] = []
    for item in EXTERNAL_SKILL_CATALOG:
        source_id = _normalize_match_key(item.get("source_id"))
        if allowed_sources and source_id not in allowed_sources:
            continue

        item_industries = [
            _normalize_match_key(value)
            for value in item.get("industries") or []
            if _normalize_match_key(value)
        ]
        if normalized_industry and item_industries:
            if normalized_industry not in item_industries:
                continue

        keyword_values = [
            _normalize_match_key(value)
            for value in item.get("keywords") or []
            if _normalize_match_key(value)
        ]
        matched_keywords = [token for token in keyword_values if token in normalized_tokens]
        score = len(matched_keywords) * 3
        joined_keywords = " ".join(keyword_values)
        for token in normalized_tokens:
            if token in matched_keywords or len(token) < 3:
                continue
            if token == _normalize_match_key(item.get("name")):
                score += 3
            elif token in joined_keywords:
                score += 1
        if normalized_industry and normalized_industry in item_industries:
            score += 2
        if score <= 0:
            continue
        scored.append(
            {
                **item,
                "score": score,
                "matched_keywords": matched_keywords[:6],
            }
        )

    if not scored:
        return []

    scored.sort(
        key=lambda item: (
            -int(item.get("score", 0)),
            str(item.get("source_label") or ""),
            str(item.get("name") or ""),
        )
    )
    top_ids = {str(item.get("id") or "") for item in scored[: min(3, len(scored))]}
    suggestions: list[dict[str, Any]] = []
    for item in scored[:limit]:
        suggestions.append(
            {
                "id": str(item.get("id") or ""),
                "name": str(item.get("name") or ""),
                "skill_name": str(item.get("skill_name") or item.get("name") or ""),
                "summary": str(item.get("summary") or ""),
                "source_id": str(item.get("source_id") or ""),
                "source_label": str(item.get("source_label") or "External"),
                "source_url": str(item.get("source_url") or ""),
                "preview_url": str(item.get("preview_url") or item.get("source_url") or ""),
                "industries": _normalize_text_list(item.get("industries") or [], limit=8, item_limit=80),
                "matched_keywords": list(item.get("matched_keywords") or []),
                "recommended": str(item.get("id") or "") in top_ids,
            }
        )
    return suggestions
