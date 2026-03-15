"""行业智能体模板库路由。"""

from __future__ import annotations

import json
import os
import re
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
import httpx

from core.deps import (
    agent_template_store,
    ensure_permission,
    local_connector_store,
    require_auth,
    role_store,
)
from core.role_permissions import resolve_role_permissions
from core.ownership import current_username
from models.requests import (
    AgentTemplateBatchDeleteReq,
    AgentTemplateDeduplicateReq,
    AgentTemplateBatchSaveReq,
    AgentTemplateTranslateNamesReq,
    EmployeeAgentTemplateImportReq,
)
from services.employee_template_import_service import import_agent_templates
from services.llm_provider_service import get_llm_provider_service
from services.local_connector_service import (
    build_local_connector_provider_id,
    connector_agent_available,
    connector_base_url,
    connector_headers,
    list_connector_llm_models,
    parse_local_connector_provider_id,
)
from stores.json.agent_template_store import AgentTemplate, _now_iso

router = APIRouter(
    prefix="/api/agent-templates",
    dependencies=[Depends(require_auth)],
)

_EXTERNAL_AGENT_SPECS: dict[str, dict[str, str]] = {
    "codex_cli": {
        "label": "Codex CLI",
        "binary_name": "codex",
    },
    "claude_cli": {
        "label": "Claude Code",
        "binary_name": "claude",
    },
    "gemini_cli": {
        "label": "Gemini CLI",
        "binary_name": "gemini",
    },
}


def _serialize_agent_template(template: AgentTemplate) -> dict[str, Any]:
    return {
        "id": template.id,
        "name": template.name,
        "name_zh": template.name_zh,
        "created_by": template.created_by,
        "description": template.description,
        "content": template.content,
        "goal": template.goal,
        "source_name": template.source_name,
        "source_url": template.source_url,
        "relative_path": template.relative_path,
        "tone": template.tone,
        "verbosity": template.verbosity,
        "language": template.language,
        "rule_domains": list(template.rule_domains or []),
        "style_hints": list(template.style_hints or []),
        "default_workflow": list(template.default_workflow or []),
        "tool_usage_policy": template.tool_usage_policy,
        "draft": template.draft or {},
        "created_at": template.created_at,
        "updated_at": template.updated_at,
    }


def _normalize_text(value: Any, *, limit: int = 4000) -> str:
    return str(value or "").strip()[:limit]


def _contains_cjk(value: Any) -> bool:
    return bool(re.search(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]", _normalize_text(value, limit=400)))


def _contains_ascii_alnum(value: Any) -> bool:
    return bool(re.search(r"[A-Za-z0-9]", _normalize_text(value, limit=400)))


def _is_chinese_display_name(value: Any) -> bool:
    text = _normalize_text(value, limit=160)
    if not text:
        return False
    return _contains_cjk(text) and not _contains_ascii_alnum(text)


def _normalize_match_key(value: Any) -> str:
    return _normalize_text(value, limit=4000).lower()


def _current_username(auth_payload: dict) -> str:
    username = str(auth_payload.get("sub") or "").strip()
    return username or "unknown"


def _current_role_id(auth_payload: dict) -> str:
    return str(auth_payload.get("role") or "").strip().lower()


def _is_admin_like(auth_payload: dict) -> bool:
    role_id = _current_role_id(auth_payload)
    role = role_store.get(role_id)
    permissions = getattr(role, "permissions", [])
    resolved = resolve_role_permissions(permissions, role_id)
    return "*" in set(resolved)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_external_agent_type(value: Any) -> str:
    agent_type = str(value or "codex_cli").strip().lower()
    return agent_type if agent_type in _EXTERNAL_AGENT_SPECS else "codex_cli"


def _normalize_source_type(value: Any) -> str:
    normalized = str(value or "internal").strip().lower()
    return normalized if normalized in {"internal", "external"} else "internal"


def _normalize_text_list(value: Any, *, limit: int = 80) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_item in value:
        item = str(raw_item or "").strip()[:limit]
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(item)
    return normalized


def _connector_llm_shared_with_usernames(item: Any) -> list[str]:
    return _normalize_text_list(getattr(item, "llm_shared_with_usernames", []), limit=64)


def _connector_llm_shared_with_roles(item: Any) -> list[str]:
    return [item.lower() for item in _normalize_text_list(getattr(item, "llm_shared_with_roles", []), limit=64)]


def _connector_llm_accessible(item: Any, auth_payload: dict) -> bool:
    if _is_admin_like(auth_payload):
        return True
    username = _current_username(auth_payload)
    if str(getattr(item, "owner_username", "") or "").strip() == username:
        return True
    if username in _connector_llm_shared_with_usernames(item):
        return True
    return _current_role_id(auth_payload) in _connector_llm_shared_with_roles(item)


def _connector_external_agent_shared_with_usernames(item: Any) -> list[str]:
    return _normalize_text_list(getattr(item, "external_agent_shared_with_usernames", []), limit=64)


def _connector_external_agent_shared_with_roles(item: Any) -> list[str]:
    return [
        item.lower()
        for item in _normalize_text_list(getattr(item, "external_agent_shared_with_roles", []), limit=64)
    ]


def _connector_external_agent_accessible(item: Any, auth_payload: dict) -> bool:
    if _is_admin_like(auth_payload):
        return True
    username = _current_username(auth_payload)
    if str(getattr(item, "owner_username", "") or "").strip() == username:
        return True
    if username in _connector_external_agent_shared_with_usernames(item):
        return True
    return _current_role_id(auth_payload) in _connector_external_agent_shared_with_roles(item)


def _list_accessible_local_connectors(auth_payload: dict) -> list[Any]:
    return [
        item
        for item in local_connector_store.list_connectors()
        if _connector_llm_accessible(item, auth_payload)
    ]


def _resolve_accessible_local_connector(
    connector_id: str,
    auth_payload: dict,
) -> Any | None:
    normalized = str(connector_id or "").strip()
    if not normalized:
        return None
    item = local_connector_store.get_connector(normalized)
    if item is None:
        return None
    return item if _connector_llm_accessible(item, auth_payload) else None


def _list_accessible_external_agent_connectors(auth_payload: dict) -> list[Any]:
    return [
        item
        for item in local_connector_store.list_connectors()
        if _connector_external_agent_accessible(item, auth_payload)
    ]


def _resolve_accessible_external_agent_connector(
    connector_id: str,
    auth_payload: dict,
) -> Any | None:
    normalized = str(connector_id or "").strip()
    if not normalized:
        return None
    item = local_connector_store.get_connector(normalized)
    if item is None:
        return None
    return item if _connector_external_agent_accessible(item, auth_payload) else None


def _normalize_text_list(values: Any, *, limit: int = 32, item_limit: int = 240) -> list[str]:
    seen: set[str] = set()
    results: list[str] = []
    for item in values or []:
        text = _normalize_text(item, limit=item_limit)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        results.append(text)
        if len(results) >= limit:
            break
    return results


def _find_existing_template(source_url: str, relative_path: str) -> AgentTemplate | None:
    source_key = _normalize_text(source_url, limit=400).lower()
    path_key = _normalize_text(relative_path, limit=400).lower()
    if not source_key or not path_key:
        return None
    for template in agent_template_store.list_all():
        if (
            _normalize_text(template.source_url, limit=400).lower() == source_key
            and _normalize_text(template.relative_path, limit=400).lower() == path_key
        ):
            return template
    return None


def _safe_template_excerpt(template: AgentTemplate, *, limit: int = 1200) -> str:
    content = _normalize_text(template.content, limit=8000)
    if content:
        return content[:limit]
    draft = template.draft if isinstance(template.draft, dict) else {}
    fallback_parts = [
        _normalize_text(template.description, limit=600),
        _normalize_text(template.goal, limit=300),
        "\n".join(_normalize_text_list(template.style_hints, limit=6, item_limit=120)),
        "\n".join(_normalize_text_list(template.default_workflow, limit=6, item_limit=180)),
        _normalize_text(draft.get("tool_usage_policy"), limit=1200),
    ]
    return _normalize_text("\n".join(part for part in fallback_parts if part), limit=limit)


def _preferred_template_name_zh(name: Any, current_name_zh: Any = "") -> str:
    normalized_name_zh = _normalize_text(current_name_zh, limit=160)
    if _is_chinese_display_name(normalized_name_zh):
        return normalized_name_zh
    normalized_name = _normalize_text(name, limit=160)
    if _is_chinese_display_name(normalized_name):
        return normalized_name
    return ""


def _normalize_template_exact_text(value: Any) -> str:
    raw = str(value or "").replace("\r\n", "\n").replace("\r", "\n").replace("\ufeff", "")
    lines = [line.rstrip() for line in raw.split("\n")]
    normalized = "\n".join(lines).strip()
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized


def _template_exact_content_key(template: AgentTemplate) -> str:
    content = _normalize_template_exact_text(template.content)
    if content:
        return f"content:{content}"
    draft = template.draft if isinstance(template.draft, dict) else {}
    fallback_parts = [
        _normalize_template_exact_text(template.name),
        _normalize_template_exact_text(template.description),
        _normalize_template_exact_text(template.goal),
        _normalize_template_exact_text("\n".join(_normalize_text_list(template.rule_domains, limit=24, item_limit=120))),
        _normalize_template_exact_text("\n".join(_normalize_text_list(template.style_hints, limit=40, item_limit=240))),
        _normalize_template_exact_text("\n".join(_normalize_text_list(template.default_workflow, limit=40, item_limit=240))),
        _normalize_template_exact_text(draft.get("tool_usage_policy")),
    ]
    fallback = "\n\n".join(part for part in fallback_parts if part)
    return f"fallback:{fallback}" if fallback else ""


def _template_keep_priority(template: AgentTemplate) -> tuple[Any, ...]:
    direct_name_zh = _preferred_template_name_zh(template.name, template.name_zh)
    content = _normalize_template_exact_text(template.content)
    updated_at = _normalize_text(template.updated_at, limit=80)
    created_at = _normalize_text(template.created_at, limit=80)
    return (
        1 if direct_name_zh else 0,
        1 if _normalize_text(template.description, limit=2000) else 0,
        1 if _normalize_text(template.goal, limit=600) else 0,
        len(_normalize_text_list(template.rule_domains, limit=24, item_limit=120)),
        len(_normalize_text_list(template.style_hints, limit=40, item_limit=240)),
        len(_normalize_text_list(template.default_workflow, limit=40, item_limit=240)),
        1 if _normalize_text(template.tool_usage_policy, limit=4000) else 0,
        len(content),
        updated_at,
        created_at,
        template.id,
    )


def _deduplicate_exact_templates(
    templates: list[AgentTemplate],
) -> list[dict[str, Any]]:
    groups_by_key: dict[str, list[AgentTemplate]] = {}
    for template in templates:
        exact_key = _template_exact_content_key(template)
        if not exact_key:
            continue
        groups_by_key.setdefault(exact_key, []).append(template)
    dedup_groups: list[dict[str, Any]] = []
    for group_templates in groups_by_key.values():
        if len(group_templates) < 2:
            continue
        ordered = sorted(group_templates, key=_template_keep_priority, reverse=True)
        keep = ordered[0]
        remove = ordered[1:]
        if not remove:
            continue
        dedup_groups.append(
            {
                "dedupe_source": "exact",
                "type_label": "完全相同模板",
                "reason": "模板内容完全一致，已按内容精确去重",
                "keep": _serialize_agent_template(keep),
                "remove": [_serialize_agent_template(item) for item in remove],
            }
        )
    return dedup_groups


def _normalize_template_match_text(value: Any, *, limit: int = 240) -> str:
    text = _normalize_text(value, limit=limit).lower()
    return re.sub(r"[^a-z0-9\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+", "", text)


def _extract_template_match_tokens(value: Any, *, limit: int = 2000) -> set[str]:
    text = _normalize_text(value, limit=limit).lower()
    if not text:
        return set()
    tokens: set[str] = set()
    for item in re.findall(r"[a-z0-9]{2,}", text):
        tokens.add(item)
    for segment in re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]{2,}", text):
        compact = segment.strip()
        if not compact:
            continue
        if len(compact) <= 4:
            tokens.add(compact)
        for index in range(0, len(compact) - 1):
            tokens.add(compact[index : index + 2])
    return tokens


def _template_match_keys(template: AgentTemplate) -> set[str]:
    keys = {
        _normalize_template_match_text(template.name, limit=160),
        _normalize_template_match_text(template.name_zh, limit=160),
    }
    path_value = _normalize_text(template.relative_path, limit=400).strip("/")
    if path_value:
        basename = path_value.rsplit("/", 1)[-1]
        stem = basename.rsplit(".", 1)[0]
        keys.add(_normalize_template_match_text(basename, limit=160))
        keys.add(_normalize_template_match_text(stem, limit=160))
    return {item for item in keys if item}


def _template_match_bundle(template: AgentTemplate) -> dict[str, Any]:
    draft = template.draft if isinstance(template.draft, dict) else {}
    name_text = "\n".join(
        part
        for part in [
            _normalize_text(template.name, limit=160),
            _normalize_text(template.name_zh, limit=160),
            _normalize_text(template.relative_path, limit=240),
        ]
        if part
    )
    meta_text = "\n".join(
        part
        for part in [
            _normalize_text(template.description, limit=1000),
            _normalize_text(template.goal, limit=600),
            "\n".join(_normalize_text_list(template.rule_domains, limit=24, item_limit=120)),
            "\n".join(_normalize_text_list(template.style_hints, limit=32, item_limit=160)),
            "\n".join(_normalize_text_list(template.default_workflow, limit=32, item_limit=200)),
            _normalize_text(template.tool_usage_policy, limit=1500),
            _normalize_text(draft.get("tool_usage_policy"), limit=1500),
        ]
        if part
    )
    content_text = _safe_template_excerpt(template, limit=1600)
    return {
        "keys": _template_match_keys(template),
        "name_tokens": _extract_template_match_tokens(name_text, limit=500),
        "meta_tokens": _extract_template_match_tokens(meta_text, limit=2200),
        "content_tokens": _extract_template_match_tokens(content_text, limit=1800),
        "domains": {
            item.lower()
            for item in _normalize_text_list(template.rule_domains, limit=24, item_limit=120)
        },
    }


def _token_jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    shared = len(left & right)
    if shared == 0:
        return 0.0
    return shared / max(1, len(left | right))


def _template_keys_overlap(left: set[str], right: set[str]) -> bool:
    if not left or not right:
        return False
    for item in left:
        for other in right:
            if item == other:
                return True
            if min(len(item), len(other)) >= 6 and (item in other or other in item):
                return True
    return False


def _templates_likely_same_type(
    left_template: AgentTemplate,
    right_template: AgentTemplate,
    bundles: dict[str, dict[str, Any]],
) -> bool:
    left = bundles[left_template.id]
    right = bundles[right_template.id]
    if _template_keys_overlap(left["keys"], right["keys"]):
        return True
    name_score = _token_jaccard(left["name_tokens"], right["name_tokens"])
    meta_score = _token_jaccard(left["meta_tokens"], right["meta_tokens"])
    content_score = _token_jaccard(left["content_tokens"], right["content_tokens"])
    shared_domains = bool(left["domains"] & right["domains"])
    if name_score >= 0.52:
        return True
    if name_score >= 0.26 and meta_score >= 0.18:
        return True
    if shared_domains and (name_score >= 0.18 or meta_score >= 0.24):
        return True
    if meta_score >= 0.34:
        return True
    if content_score >= 0.36 and (name_score >= 0.12 or meta_score >= 0.16):
        return True
    return False


def _build_template_candidate_groups(
    templates: list[AgentTemplate],
) -> list[list[AgentTemplate]]:
    if len(templates) < 2:
        return []
    bundles = {
        template.id: _template_match_bundle(template)
        for template in templates
    }
    adjacency: dict[str, set[str]] = {template.id: set() for template in templates}
    for index, left_template in enumerate(templates):
        for right_template in templates[index + 1 :]:
            if not _templates_likely_same_type(left_template, right_template, bundles):
                continue
            adjacency[left_template.id].add(right_template.id)
            adjacency[right_template.id].add(left_template.id)
    groups: list[list[AgentTemplate]] = []
    visited: set[str] = set()
    id_map = {template.id: template for template in templates}
    for template in templates:
        if template.id in visited or not adjacency.get(template.id):
            continue
        stack = [template.id]
        component: list[AgentTemplate] = []
        while stack:
            current_id = stack.pop()
            if current_id in visited:
                continue
            visited.add(current_id)
            current_template = id_map.get(current_id)
            if current_template is not None:
                component.append(current_template)
            stack.extend(
                neighbor_id
                for neighbor_id in adjacency.get(current_id, set())
                if neighbor_id not in visited
            )
        if len(component) >= 2:
            groups.append(component)
    return groups


def _coarse_template_bucket_key(template: AgentTemplate) -> str:
    domains = _normalize_text_list(template.rule_domains, limit=2, item_limit=80)
    if domains:
        return f"domain:{'|'.join(item.lower() for item in domains)}"
    path = _normalize_text(template.relative_path, limit=400).strip("/")
    if path:
        first = path.split("/", 1)[0].strip().lower()
        if first:
            return f"path:{first}"
    language = _normalize_text(template.language, limit=40).lower() or "unknown"
    return f"lang:{language}"


def _extract_json_payload(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        raise ValueError("LLM returned empty content")
    code_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, re.IGNORECASE)
    if code_match:
        raw = code_match.group(1).strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("LLM did not return a JSON object")
    return json.loads(raw[start : end + 1])


def _extract_text_segments(value: Any) -> list[str]:
    parts: list[str] = []
    if isinstance(value, str):
        text = value.strip()
        if text:
            parts.append(text)
        return parts
    if isinstance(value, list):
        for item in value:
            parts.extend(_extract_text_segments(item))
        return parts
    if isinstance(value, dict):
        if isinstance(value.get("text"), str):
            parts.extend(_extract_text_segments(value.get("text")))
        if isinstance(value.get("content"), list):
            for item in value.get("content") or []:
                if isinstance(item, dict):
                    parts.extend(_extract_text_segments(item.get("text") or item.get("content") or item.get("value")))
        for key in ("content", "message", "result", "delta", "completion", "value"):
            if key in value:
                parts.extend(_extract_text_segments(value.get(key)))
        return parts
    return parts


def _extract_text_payload(value: Any) -> str:
    seen: set[str] = set()
    parts: list[str] = []
    for item in _extract_text_segments(value):
        if item in seen:
            continue
        seen.add(item)
        parts.append(item)
    return "\n".join(parts).strip()


def _compute_incremental_text(previous: str, current: str) -> tuple[str, str]:
    prev = str(previous or "")
    curr = str(current or "")
    if not curr:
        return prev, ""
    if prev and curr.startswith(prev):
        return curr, curr[len(prev) :]
    if curr == prev:
        return prev, ""
    return curr, curr


def _connector_online(item: Any) -> bool:
    raw = str(getattr(item, "last_seen_at", "") or "").strip()
    if not raw:
        return False
    try:
        last_seen = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return False
    return (_now_utc() - last_seen).total_seconds() <= 90


def _build_external_agent_statuses_for_connector(connector: Any) -> list[dict[str, Any]]:
    connector_name = str(getattr(connector, "connector_name", "") or getattr(connector, "id", "") or "当前连接器").strip()
    statuses: list[dict[str, Any]] = []
    for agent_type, spec in _EXTERNAL_AGENT_SPECS.items():
        available = connector_agent_available(connector, agent_type)
        reason = ""
        if not available:
            reason = f"{connector_name} 暂未检测到 {spec['label']}，请先在该电脑安装并启动对应 CLI"
        statuses.append(
            {
                "agent_type": agent_type,
                "label": spec["label"],
                "available": available,
                "reason": reason,
            }
        )
    return statuses


def _serialize_external_agent_connector(connector: Any) -> dict[str, Any]:
    connector_id = str(getattr(connector, "id", "") or "").strip()
    connector_name = str(getattr(connector, "connector_name", "") or connector_id or "Local Connector").strip()
    return {
        "id": connector_id,
        "name": connector_name,
        "owner_username": str(getattr(connector, "owner_username", "") or "").strip(),
        "platform": str(getattr(connector, "platform", "") or "").strip(),
        "online": _connector_online(connector),
        "advertised_url": connector_base_url(connector),
        "agent_types": _build_external_agent_statuses_for_connector(connector),
    }


def _build_template_compare_prompt(templates: list[AgentTemplate]) -> str:
    payload = []
    for template in templates:
        payload.append(
            {
                "id": template.id,
                "name": template.name,
                "description": _normalize_text(template.description, limit=500),
                "goal": _normalize_text(template.goal, limit=240),
                "rule_domains": _normalize_text_list(template.rule_domains, limit=6, item_limit=60),
                "style_hints": _normalize_text_list(template.style_hints, limit=6, item_limit=100),
                "default_workflow": _normalize_text_list(template.default_workflow, limit=5, item_limit=120),
                "relative_path": _normalize_text(template.relative_path, limit=240),
                "content_excerpt": _safe_template_excerpt(template, limit=1200),
            }
        )
    return (
        "下面是一组智能体模板，请找出其中“职责/用途/输出目标明显重复”的同类型模板簇，"
        "并且每个模板簇只保留质量最佳的一个。\n\n"
        "判定同类型时，重点看角色职责、解决的问题、交付方式，而不是只看措辞是否相似。\n"
        "保留最佳模板时，优先考虑：目标更清晰、流程更完整、约束更具体、可执行性更强、风格说明更稳定。\n"
        "不要把职责明显不同的模板归成一组。\n\n"
        "你必须只输出 JSON，不要输出 markdown。\n"
        "JSON 结构必须为："
        "{\"clusters\":[{\"type_label\":\"类型名\",\"template_ids\":[\"id1\",\"id2\"],\"keep_id\":\"id1\",\"reason\":\"...\"}],\"unmatched_ids\":[\"id3\"]}\n"
        "要求：\n"
        "1. 只有在你确信是同类型时才放入 clusters。\n"
        "2. 每个 cluster 至少 2 个模板。\n"
        "3. keep_id 必须属于 template_ids。\n"
        "4. unmatched_ids 放无法判定重复或无需去重的模板 id。\n\n"
        f"模板数据：\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def _build_template_name_translate_prompt(items: list[dict[str, str]]) -> str:
    return (
        "下面是一组智能体模板名称。请把每个名称翻译成简洁、自然、适合后台列表展示的中文名称。\n"
        "要求：\n"
        "1. 保留原本职责和角色定位，不要过度发挥。\n"
        "2. 结果必须是中文全称，不要保留任何英文、缩写、数字或英文括号解释。\n"
        "3. 每个中文名尽量控制在 12 个汉字以内。\n"
        "4. 如果原名本身已经是中文，直接返回原名。\n"
        "5. 你必须只输出 JSON，不要输出 markdown。\n"
        'JSON 结构必须为：{"items":[{"id":"xxx","name_zh":"中文名"}]}\n\n'
        f"名称数据：\n{json.dumps(items, ensure_ascii=False, indent=2)}"
    )


def _build_external_agent_translate_prompt(items: list[dict[str, str]]) -> str:
    return (
        "你是智能体模板命名助手。你负责把英文或其他非中文模板名翻译成简洁准确的中文名称。"
        "你必须只输出合法 JSON，不要输出任何解释。\n\n"
        f"{_build_template_name_translate_prompt(items)}"
    )


def _build_external_agent_deduplicate_prompt(templates: list[AgentTemplate]) -> str:
    return (
        "你是模板库治理助手。你擅长识别职责重复的智能体模板，并从重复模板里选出质量最佳版本。"
        "你必须只输出合法 JSON，不要输出任何解释。\n\n"
        f"{_build_template_compare_prompt(templates)}"
    )


def _build_external_agent_exec_command(agent_type: str, prompt: str) -> list[str]:
    normalized = _normalize_external_agent_type(agent_type)
    spec = _EXTERNAL_AGENT_SPECS.get(normalized) or _EXTERNAL_AGENT_SPECS["codex_cli"]
    binary_name = spec["binary_name"]
    if normalized == "claude_cli":
        return [
            binary_name,
            "-p",
            prompt,
            "--verbose",
            "--output-format",
            "stream-json",
            "--include-partial-messages",
            "--permission-mode",
            "plan",
        ]
    if normalized == "gemini_cli":
        return [
            binary_name,
            "--output-format",
            "stream-json",
            "--approval-mode",
            "plan",
            "-p",
            prompt,
        ]
    return [
        binary_name,
        "exec",
        "--json",
        "--color",
        "never",
        "--skip-git-repo-check",
        "-s",
        "read-only",
        prompt,
    ]


def _merge_external_agent_output(
    previous: str,
    raw_chunk: str,
    agent_type: str,
) -> str:
    normalized = _normalize_external_agent_type(agent_type)
    raw = str(raw_chunk or "").strip()
    if not raw:
        return previous
    try:
        payload = json.loads(raw)
    except Exception:
        updated, _ = _compute_incremental_text(previous, raw)
        return updated
    if normalized == "codex_cli":
        event_type = str(payload.get("type") or "").strip()
        if event_type == "item.completed":
            item = payload.get("item") if isinstance(payload.get("item"), dict) else {}
            if str(item.get("type") or "").strip() == "agent_message":
                text = str(item.get("text") or "").strip()
                if text:
                    return text
        if event_type.endswith(".delta"):
            text = _extract_text_payload(payload)
            return previous + text if text else previous
        if event_type == "turn.completed":
            text = _extract_text_payload(payload)
            if text:
                updated, _ = _compute_incremental_text(previous, text)
                return updated
        return previous
    if normalized == "claude_cli":
        event_type = str(payload.get("type") or "").strip().lower()
        if event_type == "error":
            message = _extract_text_payload(payload) or "Claude Code 执行失败"
            raise RuntimeError(message)
        if event_type not in {"assistant", "result"}:
            return previous
        text = _extract_text_payload(payload.get("message") or payload.get("content") or payload)
        updated, _ = _compute_incremental_text(previous, text)
        return updated
    event_type = str(payload.get("type") or "").strip().lower()
    if event_type == "error":
        message = _extract_text_payload(payload) or "Gemini CLI 执行失败"
        raise RuntimeError(message)
    if event_type != "message":
        return previous
    if str(payload.get("role") or "").strip().lower() == "user":
        return previous
    text = _extract_text_payload(payload.get("content") or payload)
    if not text:
        return previous
    if bool(payload.get("delta")):
        return previous + text
    updated, _ = _compute_incremental_text(previous, text)
    return updated


async def _run_external_agent_prompt(
    connector: Any,
    *,
    agent_type: str,
    prompt: str,
    timeout: float = 180.0,
) -> str:
    normalized_agent_type = _normalize_external_agent_type(agent_type)
    if not connector_base_url(connector):
        raise RuntimeError("当前连接器未提供可访问地址")
    if not connector_agent_available(connector, normalized_agent_type):
        label = (_EXTERNAL_AGENT_SPECS.get(normalized_agent_type) or {}).get("label") or normalized_agent_type
        raise RuntimeError(f"当前连接器暂未检测到 {label}")
    cmd = _build_external_agent_exec_command(normalized_agent_type, prompt)
    stderr_lines: list[str] = []
    final_content = ""
    exit_code: int | None = None
    env = os.environ.copy()
    env["TERM"] = env.get("TERM") or "xterm-256color"
    env["NO_COLOR"] = "1"
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=10.0)) as client:
        async with client.stream(
            "POST",
            f"{connector_base_url(connector)}/exec/stream",
            headers=connector_headers(connector),
            json={
                "cmd": cmd,
                "env": env,
            },
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                raw = str(line or "").strip()
                if not raw:
                    continue
                try:
                    event = json.loads(raw)
                except Exception:
                    continue
                event_type = str(event.get("type") or "").strip()
                if event_type == "stderr":
                    text = str(event.get("data") or "").strip()
                    if text:
                        stderr_lines.append(text)
                    continue
                if event_type == "exit":
                    try:
                        exit_code = int(event.get("returncode"))
                    except Exception:
                        exit_code = None
                    break
                if event_type != "stdout":
                    continue
                final_content = _merge_external_agent_output(
                    final_content,
                    str(event.get("data") or ""),
                    normalized_agent_type,
                )
    if not final_content.strip():
        stderr_text = "\n".join(stderr_lines[-8:]).strip()
        if exit_code not in (None, 0) and stderr_text:
            raise RuntimeError(stderr_text)
        raise RuntimeError(stderr_text or "外部智能体未返回有效内容")
    return final_content


async def _ai_translate_template_names(
    items: list[dict[str, str]],
    *,
    provider_id: str,
    model_name: str,
) -> dict[str, str]:
    if not items:
        return {}
    llm_service = get_llm_provider_service()
    result = await llm_service.chat_completion(
        provider_id=provider_id,
        model_name=model_name,
        messages=[
            {
                "role": "system",
                "content": (
                    "你是智能体模板命名助手。你负责把英文或其他非中文模板名翻译成简洁准确的中文名称。"
                    "你必须只输出合法 JSON。"
                ),
            },
            {"role": "user", "content": _build_template_name_translate_prompt(items)},
        ],
        temperature=0,
        max_tokens=1200,
        timeout=60,
    )
    payload = _extract_json_payload(result.get("content") or "")
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        return {}
    valid_ids = {_normalize_text(item.get("id"), limit=80) for item in items}
    translated: dict[str, str] = {}
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        item_id = _normalize_text(item.get("id"), limit=80)
        if item_id not in valid_ids:
            continue
        name_zh = _normalize_text(item.get("name_zh"), limit=160)
        if not _is_chinese_display_name(name_zh):
            continue
        translated[item_id] = name_zh
    return translated


async def _ai_translate_template_names_via_external_agent(
    items: list[dict[str, str]],
    *,
    connector: Any,
    agent_type: str,
) -> dict[str, str]:
    if not items:
        return {}
    payload = _extract_json_payload(
        await _run_external_agent_prompt(
            connector,
            agent_type=agent_type,
            prompt=_build_external_agent_translate_prompt(items),
        )
    )
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        return {}
    valid_ids = {_normalize_text(item.get("id"), limit=80) for item in items}
    translated: dict[str, str] = {}
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        item_id = _normalize_text(item.get("id"), limit=80)
        if item_id not in valid_ids:
            continue
        name_zh = _normalize_text(item.get("name_zh"), limit=160)
        if not _is_chinese_display_name(name_zh):
            continue
        translated[item_id] = name_zh
    return translated


async def _build_connector_translation_provider(connector: Any) -> dict[str, Any] | None:
    connector_id = str(getattr(connector, "id", "") or "").strip()
    if not connector_id or not connector_base_url(connector):
        return None
    try:
        llm_info = await list_connector_llm_models(connector)
    except Exception:
        llm_info = {
            "enabled": False,
            "default_model": "",
            "models": [],
        }
    if not bool(llm_info.get("enabled")):
        return None
    models = [
        str(item or "").strip()
        for item in (llm_info.get("models") or [])
        if str(item or "").strip()
    ]
    default_model = str(llm_info.get("default_model") or "").strip()
    if default_model and default_model not in models:
        models = [default_model, *models]
    if not models:
        return None
    connector_name = (
        str(getattr(connector, "connector_name", "") or "").strip() or connector_id
    )
    connector_owner = str(getattr(connector, "owner_username", "") or "").strip()
    provider_name = (
        f"本地连接器 · {connector_name} · {connector_owner}"
        if connector_owner
        else f"本地连接器 · {connector_name}"
    )
    return {
        "id": build_local_connector_provider_id(connector_id),
        "name": provider_name,
        "provider_type": "local-connector",
        "base_url": connector_base_url(connector),
        "models": models,
        "default_model": default_model or models[0],
        "enabled": True,
        "is_default": False,
        "connector_id": connector_id,
        "connector_name": connector_name,
        "connector_owner_username": connector_owner,
    }


async def _list_translation_model_providers(auth_payload: dict) -> list[dict[str, Any]]:
    llm_service = get_llm_provider_service()
    providers = list(llm_service.list_providers(enabled_only=True) or [])
    connector_items = _list_accessible_local_connectors(auth_payload)
    for connector in connector_items:
        provider = await _build_connector_translation_provider(connector)
        if provider is not None:
            providers.append(provider)
    return providers


def _resolve_llm_provider(
    *,
    preferred_provider_id: str = "",
    preferred_model_name: str = "",
    required: bool = True,
) -> tuple[dict[str, Any] | None, str]:
    llm_service = get_llm_provider_service()
    providers = llm_service.list_providers(enabled_only=True)
    if not providers:
        if required:
            raise HTTPException(400, "未配置可用的大模型提供商")
        return None, ""
    normalized_provider_id = _normalize_text(preferred_provider_id, limit=80)
    provider = next(
        (
            item
            for item in providers
            if _normalize_text(item.get("id"), limit=80) == normalized_provider_id
        ),
        next((item for item in providers if item.get("is_default")), providers[0]),
    )
    model_name = _normalize_text(preferred_model_name, limit=160) or _normalize_text(
        provider.get("default_model"),
        limit=160,
    )
    if not model_name:
        if required:
            raise HTTPException(400, "当前提供商没有可用默认模型")
        return None, ""
    return provider, model_name


async def _resolve_llm_provider_async(
    *,
    preferred_provider_id: str = "",
    preferred_model_name: str = "",
    required: bool = True,
    auth_payload: dict | None = None,
) -> tuple[dict[str, Any] | None, str]:
    connector_id = parse_local_connector_provider_id(preferred_provider_id)
    if connector_id:
        if auth_payload is None:
            if required:
                raise HTTPException(400, "Local connector provider requires auth context")
            return None, ""
        connector = _resolve_accessible_local_connector(connector_id, auth_payload)
        if connector is None:
            if required:
                raise HTTPException(404, "Local connector not found")
            return None, ""
        provider = await _build_connector_translation_provider(connector)
        if provider is None:
            if required:
                raise HTTPException(400, "当前本地连接器未配置可用模型")
            return None, ""
        model_name = _normalize_text(preferred_model_name, limit=160) or _normalize_text(
            provider.get("default_model"),
            limit=160,
        )
        if not model_name:
            if required:
                raise HTTPException(400, "当前本地连接器没有可用默认模型")
            return None, ""
        return provider, model_name
    return _resolve_llm_provider(
        preferred_provider_id=preferred_provider_id,
        preferred_model_name=preferred_model_name,
        required=required,
    )


async def _ensure_template_name_translations(
    templates: list[AgentTemplate],
    *,
    persist: bool,
    force: bool = False,
    source_type: str = "internal",
    provider_id: str = "",
    model_name: str = "",
    external_connector: Any | None = None,
    external_agent_type: str = "codex_cli",
    strict: bool = False,
    auth_payload: dict | None = None,
) -> list[AgentTemplate]:
    normalized_templates: list[AgentTemplate] = []
    pending: list[dict[str, str]] = []
    for template in templates:
        direct_name_zh = (
            _normalize_text(template.name, limit=160)
            if _is_chinese_display_name(template.name)
            else ""
        )
        if direct_name_zh:
            normalized = template
            if direct_name_zh != _normalize_text(template.name_zh, limit=160):
                normalized = replace(template, name_zh=direct_name_zh)
                if persist:
                    agent_template_store.save(normalized)
            normalized_templates.append(normalized)
            continue
        normalized_templates.append(template)
        if not force and _normalize_text(template.name_zh, limit=160):
            continue
        pending.append(
            {
                "id": template.id,
                "name": _normalize_text(template.name, limit=160),
            }
        )
    if not pending:
        return normalized_templates

    normalized_source_type = _normalize_source_type(source_type)
    provider = None
    resolved_model_name = ""
    if normalized_source_type == "external":
        if external_connector is None:
            if strict:
                raise RuntimeError("未找到可用的外部智能体连接器")
            return normalized_templates
    else:
        provider, resolved_model_name = await _resolve_llm_provider_async(
            preferred_provider_id=provider_id,
            preferred_model_name=model_name,
            required=False,
            auth_payload=auth_payload,
        )
        if provider is None or not resolved_model_name:
            return normalized_templates

    translated_by_id: dict[str, str] = {}
    try:
        for index in range(0, len(pending), 20):
            chunk = pending[index : index + 20]
            if normalized_source_type == "external":
                translated_by_id.update(
                    await _ai_translate_template_names_via_external_agent(
                        chunk,
                        connector=external_connector,
                        agent_type=external_agent_type,
                    )
                )
                continue
            translated_by_id.update(
                await _ai_translate_template_names(
                    chunk,
                    provider_id=str(provider.get("id") or ""),
                    model_name=resolved_model_name,
                )
            )
    except Exception as exc:
        if strict:
            raise RuntimeError(f"模板中文名翻译调用失败: {str(exc)}") from exc
        return normalized_templates

    if strict and not translated_by_id:
        sample_names = "、".join(
            item["name"] for item in pending[:5] if _normalize_text(item.get("name"), limit=160)
        )
        raise RuntimeError(
            f"模型未返回可用的中文名称结果。待翻译模板示例: {sample_names or '未命名模板'}"
        )

    updated_templates: list[AgentTemplate] = []
    for template in normalized_templates:
        translated_name = _normalize_text(translated_by_id.get(template.id), limit=160)
        if not translated_name:
            updated_templates.append(template)
            continue
        updated = replace(template, name_zh=translated_name)
        updated_templates.append(updated)
        if persist:
            agent_template_store.save(updated)
    return updated_templates


async def _ai_pick_duplicate_clusters(
    templates: list[AgentTemplate],
    *,
    provider_id: str,
    model_name: str,
    temperature: float,
) -> list[dict[str, Any]]:
    if len(templates) < 2:
        return []
    llm_service = get_llm_provider_service()
    result = await llm_service.chat_completion(
        provider_id=provider_id,
        model_name=model_name,
        messages=[
            {
                "role": "system",
                "content": (
                    "你是模板库治理助手。你擅长识别职责重复的智能体模板，并从重复模板里选出质量最佳版本。"
                    "你必须只输出合法 JSON。"
                ),
            },
            {"role": "user", "content": _build_template_compare_prompt(templates)},
        ],
        temperature=temperature,
        max_tokens=2200,
        timeout=90,
    )
    payload = _extract_json_payload(result.get("content") or "")
    clusters = payload.get("clusters")
    if not isinstance(clusters, list):
        return []
    valid_ids = {template.id for template in templates}
    normalized_clusters: list[dict[str, Any]] = []
    for item in clusters:
        if not isinstance(item, dict):
            continue
        template_ids = [
            _normalize_text(value, limit=80)
            for value in (item.get("template_ids") or [])
            if _normalize_text(value, limit=80) in valid_ids
        ]
        seen_ids: set[str] = set()
        template_ids = [value for value in template_ids if not (value in seen_ids or seen_ids.add(value))]
        keep_id = _normalize_text(item.get("keep_id"), limit=80)
        if len(template_ids) < 2 or keep_id not in template_ids:
            continue
        normalized_clusters.append(
            {
                "type_label": _normalize_text(item.get("type_label"), limit=120) or "同类型模板",
                "template_ids": template_ids,
                "keep_id": keep_id,
                "reason": _normalize_text(item.get("reason"), limit=800),
            }
        )
    return normalized_clusters


async def _ai_pick_duplicate_clusters_via_external_agent(
    templates: list[AgentTemplate],
    *,
    connector: Any,
    agent_type: str,
) -> list[dict[str, Any]]:
    if len(templates) < 2:
        return []
    payload = _extract_json_payload(
        await _run_external_agent_prompt(
            connector,
            agent_type=agent_type,
            prompt=_build_external_agent_deduplicate_prompt(templates),
            timeout=240.0,
        )
    )
    clusters = payload.get("clusters")
    if not isinstance(clusters, list):
        return []
    valid_ids = {template.id for template in templates}
    normalized_clusters: list[dict[str, Any]] = []
    for item in clusters:
        if not isinstance(item, dict):
            continue
        template_ids = [
            _normalize_text(value, limit=80)
            for value in (item.get("template_ids") or [])
            if _normalize_text(value, limit=80) in valid_ids
        ]
        seen_ids: set[str] = set()
        template_ids = [value for value in template_ids if not (value in seen_ids or seen_ids.add(value))]
        keep_id = _normalize_text(item.get("keep_id"), limit=80)
        if len(template_ids) < 2 or keep_id not in template_ids:
            continue
        normalized_clusters.append(
            {
                "type_label": _normalize_text(item.get("type_label"), limit=120) or "同类型模板",
                "template_ids": template_ids,
                "keep_id": keep_id,
                "reason": _normalize_text(item.get("reason"), limit=800),
            }
        )
    return normalized_clusters


async def _deduplicate_templates_by_ai(
    templates: list[AgentTemplate],
    *,
    source_type: str = "internal",
    provider_id: str,
    model_name: str,
    external_connector: Any | None = None,
    external_agent_type: str = "codex_cli",
    temperature: float,
) -> list[dict[str, Any]]:
    dedup_groups = _deduplicate_exact_templates(templates)
    used_template_ids: set[str] = {
        _normalize_text(item.get("id"), limit=80)
        for group in dedup_groups
        for item in (group.get("keep"), *(group.get("remove") or []))
        if isinstance(item, dict) and _normalize_text(item.get("id"), limit=80)
    }
    remaining_templates = [
        template
        for template in templates
        if template.id not in used_template_ids
    ]
    candidate_groups = _build_template_candidate_groups(remaining_templates)
    for bucket_templates in candidate_groups:
        if _normalize_source_type(source_type) == "external":
            clusters = await _ai_pick_duplicate_clusters_via_external_agent(
                bucket_templates,
                connector=external_connector,
                agent_type=external_agent_type,
            )
        else:
            clusters = await _ai_pick_duplicate_clusters(
                bucket_templates,
                provider_id=provider_id,
                model_name=model_name,
                temperature=temperature,
            )
        id_map = {template.id: template for template in bucket_templates}
        for cluster in clusters:
            cluster_ids = [item for item in cluster["template_ids"] if item not in used_template_ids]
            keep_id = cluster["keep_id"]
            if len(cluster_ids) < 2 or keep_id not in cluster_ids:
                continue
            remove_ids = [item for item in cluster_ids if item != keep_id]
            if not remove_ids:
                continue
            for template_id in cluster_ids:
                used_template_ids.add(template_id)
            dedup_groups.append(
                {
                    "dedupe_source": "semantic",
                    "type_label": cluster["type_label"],
                    "reason": cluster["reason"],
                    "keep": _serialize_agent_template(id_map[keep_id]),
                    "remove": [_serialize_agent_template(id_map[item]) for item in remove_ids],
                }
            )
    return dedup_groups


def _build_template_model(raw: dict[str, Any], *, created_by: str) -> AgentTemplate:
    draft = raw.get("draft") if isinstance(raw.get("draft"), dict) else {}
    existing = _find_existing_template(raw.get("source_url"), raw.get("relative_path"))
    now = _now_iso()
    payload = {
        "name": _normalize_text(raw.get("name"), limit=160) or _normalize_text(draft.get("name"), limit=160) or "未命名模板",
        "name_zh": _preferred_template_name_zh(
            raw.get("name") or draft.get("name"),
            raw.get("name_zh"),
        ),
        "description": _normalize_text(raw.get("description"), limit=2000) or _normalize_text(draft.get("description"), limit=2000),
        "content": _normalize_text(raw.get("content"), limit=200000),
        "goal": _normalize_text(draft.get("goal"), limit=600),
        "source_name": _normalize_text(raw.get("source_name"), limit=240),
        "source_url": _normalize_text(raw.get("source_url"), limit=400),
        "relative_path": _normalize_text(raw.get("relative_path"), limit=400),
        "tone": _normalize_text(draft.get("tone"), limit=80) or "professional",
        "verbosity": _normalize_text(draft.get("verbosity"), limit=80) or "concise",
        "language": _normalize_text(draft.get("language"), limit=80) or "zh-CN",
        "rule_domains": _normalize_text_list(draft.get("rule_domains"), limit=12, item_limit=80),
        "style_hints": _normalize_text_list(draft.get("style_hints"), limit=24, item_limit=160),
        "default_workflow": _normalize_text_list(draft.get("default_workflow"), limit=24, item_limit=200),
        "tool_usage_policy": _normalize_text(draft.get("tool_usage_policy"), limit=8000),
        "draft": draft,
        "updated_at": now,
    }
    if existing is not None:
        return replace(existing, **payload)
    return AgentTemplate(
        id=agent_template_store.new_id(),
        created_by=created_by,
        created_at=now,
        **payload,
    )


@router.get("")
async def list_agent_templates(auth_payload: dict = Depends(require_auth)):
    ensure_permission(auth_payload, "menu.employees")
    templates = await _ensure_template_name_translations(
        agent_template_store.list_all(),
        persist=True,
    )
    templates.sort(key=lambda item: (item.updated_at, item.created_at, item.id), reverse=True)
    return {"templates": [_serialize_agent_template(item) for item in templates]}


@router.get("/translation-models")
async def list_agent_template_translation_models(
    auth_payload: dict = Depends(require_auth),
):
    ensure_permission(auth_payload, "menu.employees.create")
    providers = await _list_translation_model_providers(auth_payload)
    return {"providers": providers}


@router.get("/ai-sources")
async def list_agent_template_ai_sources(
    auth_payload: dict = Depends(require_auth),
):
    ensure_permission(auth_payload, "menu.employees.create")
    llm_service = get_llm_provider_service()
    providers = list(llm_service.list_providers(enabled_only=True) or [])
    external_connectors = [
        _serialize_external_agent_connector(item)
        for item in _list_accessible_external_agent_connectors(auth_payload)
        if str(getattr(item, "id", "") or "").strip()
    ]
    return {
        "internal_providers": providers,
        "external_connectors": external_connectors,
    }


@router.get("/{template_id}")
async def get_agent_template(template_id: str, auth_payload: dict = Depends(require_auth)):
    ensure_permission(auth_payload, "menu.employees")
    template = agent_template_store.get(template_id)
    if template is None:
        raise HTTPException(404, "Template not found")
    enriched = await _ensure_template_name_translations([template], persist=True)
    template = enriched[0] if enriched else template
    return {"template": _serialize_agent_template(template)}


@router.post("/import-preview")
async def preview_agent_templates(
    req: EmployeeAgentTemplateImportReq,
    auth_payload: dict = Depends(require_auth),
):
    ensure_permission(auth_payload, "menu.employees.create")
    templates = import_agent_templates(
        source_type=req.source_type,
        source=req.source,
        subdirectory=req.subdirectory,
        branch=req.branch,
        limit=req.limit,
    )
    return {"templates": templates, "count": len(templates)}


@router.post("/batch")
async def save_agent_templates(
    req: AgentTemplateBatchSaveReq,
    auth_payload: dict = Depends(require_auth),
):
    ensure_permission(auth_payload, "menu.employees.create")
    if not req.templates:
        raise HTTPException(400, "templates is required")
    actor = current_username(auth_payload)
    models = [
        _build_template_model(item.model_dump(), created_by=actor)
        for item in req.templates
    ]
    models = await _ensure_template_name_translations(models, persist=False)
    saved: list[dict[str, Any]] = []
    for template in models:
        agent_template_store.save(template)
        saved.append(_serialize_agent_template(template))
    return {"templates": saved, "count": len(saved)}


@router.post("/batch-delete")
async def batch_delete_agent_templates(
    req: AgentTemplateBatchDeleteReq,
    auth_payload: dict = Depends(require_auth),
):
    ensure_permission(auth_payload, "menu.employees")
    template_ids = [
        _normalize_text(item, limit=80)
        for item in (req.template_ids or [])
        if _normalize_text(item, limit=80)
    ]
    unique_template_ids: list[str] = []
    seen_ids: set[str] = set()
    for template_id in template_ids:
        if template_id in seen_ids:
            continue
        seen_ids.add(template_id)
        unique_template_ids.append(template_id)
    if not unique_template_ids:
        raise HTTPException(400, "没有可删除的模板")
    deleted_ids: list[str] = []
    for template_id in unique_template_ids:
        if agent_template_store.delete(template_id):
            deleted_ids.append(template_id)
    return {
        "count": len(unique_template_ids),
        "deleted_count": len(deleted_ids),
        "deleted_ids": deleted_ids,
    }


@router.post("/translate-names")
async def translate_agent_template_names(
    req: AgentTemplateTranslateNamesReq,
    auth_payload: dict = Depends(require_auth),
):
    ensure_permission(auth_payload, "menu.employees.create")
    all_templates = agent_template_store.list_all()
    selected_ids = {
        _normalize_text(item, limit=80)
        for item in (req.template_ids or [])
        if _normalize_text(item, limit=80)
    }
    templates = [
        item for item in all_templates if not selected_ids or item.id in selected_ids
    ]
    if not templates:
        raise HTTPException(400, "没有可处理的模板")

    normalized_source_type = _normalize_source_type(req.source_type)
    provider = None
    model_name = ""
    external_connector = None
    external_agent_type = _normalize_external_agent_type(req.external_agent_type)
    if any(
        not _is_chinese_display_name(item.name)
        and (bool(req.force) or not _is_chinese_display_name(item.name_zh))
        for item in templates
    ):
        if normalized_source_type == "external":
            external_connector = _resolve_accessible_external_agent_connector(
                req.local_connector_id,
                auth_payload,
            )
            if external_connector is None:
                raise HTTPException(404, "未找到可用的外部智能体连接器")
            if not connector_agent_available(external_connector, external_agent_type):
                label = (_EXTERNAL_AGENT_SPECS.get(external_agent_type) or {}).get("label") or external_agent_type
                raise HTTPException(400, f"当前连接器暂未检测到 {label}")
        else:
            provider, model_name = await _resolve_llm_provider_async(
                preferred_provider_id=req.provider_id,
                preferred_model_name=req.model_name,
                required=True,
                auth_payload=auth_payload,
            )

    try:
        updated_templates = await _ensure_template_name_translations(
            templates,
            persist=True,
            force=bool(req.force),
            source_type=normalized_source_type,
            provider_id=str(provider.get("id") or "") if provider else "",
            model_name=model_name,
            external_connector=external_connector,
            external_agent_type=external_agent_type,
            strict=True,
            auth_payload=auth_payload,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"模板中文名翻译失败: {str(exc)}") from exc

    updated_count = 0
    items: list[dict[str, Any]] = []
    original_map = {item.id: item for item in templates}
    for template in updated_templates:
        previous = original_map.get(template.id)
        if previous and _normalize_text(previous.name_zh, limit=160) != _normalize_text(template.name_zh, limit=160):
            updated_count += 1
        items.append(_serialize_agent_template(template))

    return {
        "source_type": normalized_source_type,
        "provider_id": str(provider.get("id") or "") if provider else "",
        "model_name": model_name,
        "local_connector_id": str(getattr(external_connector, "id", "") or "").strip(),
        "external_agent_type": external_agent_type if normalized_source_type == "external" else "",
        "count": len(items),
        "updated_count": updated_count,
        "force": bool(req.force),
        "templates": items,
    }


@router.post("/deduplicate")
async def deduplicate_agent_templates(
    req: AgentTemplateDeduplicateReq,
    auth_payload: dict = Depends(require_auth),
):
    ensure_permission(auth_payload, "menu.employees.create")
    all_templates = agent_template_store.list_all()
    selected_ids = {
        _normalize_text(item, limit=80)
        for item in (req.template_ids or [])
        if _normalize_text(item, limit=80)
    }
    templates = [
        item for item in all_templates if not selected_ids or item.id in selected_ids
    ]
    if len(templates) < 2:
        raise HTTPException(400, "至少需要 2 个模板才能执行同类去重")

    normalized_source_type = _normalize_source_type(req.source_type)
    provider = None
    model_name = ""
    external_connector = None
    external_agent_type = _normalize_external_agent_type(req.external_agent_type)
    if normalized_source_type == "external":
        external_connector = _resolve_accessible_external_agent_connector(
            req.local_connector_id,
            auth_payload,
        )
        if external_connector is None:
            raise HTTPException(404, "未找到可用的外部智能体连接器")
        if not connector_agent_available(external_connector, external_agent_type):
            label = (_EXTERNAL_AGENT_SPECS.get(external_agent_type) or {}).get("label") or external_agent_type
            raise HTTPException(400, f"当前连接器暂未检测到 {label}")
    else:
        provider, model_name = await _resolve_llm_provider_async(
            preferred_provider_id=req.provider_id,
            preferred_model_name=req.model_name,
            required=True,
            auth_payload=auth_payload,
        )

    try:
        groups = await _deduplicate_templates_by_ai(
            templates,
            source_type=normalized_source_type,
            provider_id=str(provider.get("id") or "") if provider else "",
            model_name=model_name,
            external_connector=external_connector,
            external_agent_type=external_agent_type,
            temperature=float(req.temperature if req.temperature is not None else 0.1),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"AI 模板去重失败: {str(exc)}") from exc

    remove_ids = [
        item["id"]
        for group in groups
        for item in (group.get("remove") or [])
        if isinstance(item, dict) and _normalize_text(item.get("id"), limit=80)
    ]
    exact_group_count = sum(
        1 for group in groups if str(group.get("dedupe_source") or "").strip() == "exact"
    )
    semantic_group_count = sum(
        1 for group in groups if str(group.get("dedupe_source") or "").strip() == "semantic"
    )
    exact_remove_count = sum(
        len(group.get("remove") or [])
        for group in groups
        if str(group.get("dedupe_source") or "").strip() == "exact"
    )
    semantic_remove_count = sum(
        len(group.get("remove") or [])
        for group in groups
        if str(group.get("dedupe_source") or "").strip() == "semantic"
    )
    removed_count = 0
    if bool(req.apply):
        for template_id in remove_ids:
            if agent_template_store.delete(template_id):
                removed_count += 1

    return {
        "source_type": normalized_source_type,
        "provider_id": str(provider.get("id") or "") if provider else "",
        "model_name": model_name,
        "local_connector_id": str(getattr(external_connector, "id", "") or "").strip(),
        "external_agent_type": external_agent_type if normalized_source_type == "external" else "",
        "groups": groups,
        "group_count": len(groups),
        "remove_count": len(remove_ids),
        "deleted_count": removed_count,
        "exact_group_count": exact_group_count,
        "semantic_group_count": semantic_group_count,
        "exact_remove_count": exact_remove_count,
        "semantic_remove_count": semantic_remove_count,
        "apply": bool(req.apply),
    }


@router.delete("/{template_id}")
async def delete_agent_template(template_id: str, auth_payload: dict = Depends(require_auth)):
    ensure_permission(auth_payload, "menu.employees")
    if not agent_template_store.delete(template_id):
        raise HTTPException(404, "Template not found")
    return {"status": "deleted"}
