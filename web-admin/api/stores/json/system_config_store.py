"""系统配置存储层"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


DEFAULT_PROMPTS_CHAT_URL = "https://prompts.chat/api/mcp"
DEFAULT_VETT_BASE_URL = "https://vett.sh/api/v1"
DEFAULT_EMPLOYEE_RULE_GENERATION_PROMPT = (
    "基于员工职责、目标、技能建议和 prompts.chat MCP 相关能力，为员工自动补全 1 到 3 条可直接落地的执行规则。"
    "优先生成问题排查、输出规范、风险控制、技术选型相关规则；规则内容必须具体、可执行、可绑定。"
)


def default_employee_external_skill_sites() -> list[dict[str, object]]:
    return [
        {
            "id": "frontend-ui",
            "title": "UI 与界面一致性",
            "description": "适合界面审美、排版层级、交互一致性和设计系统类员工。",
            "url": "https://vett.sh/skills/clawhub.ai/ivangdavila/ui",
        },
        {
            "id": "frontend-css",
            "title": "CSS 与样式工程化",
            "description": "适合布局系统、响应式、动画和样式治理类员工。",
            "url": "https://vett.sh/skills/clawhub.ai/ivangdavila/css",
        },
        {
            "id": "frontend-vue",
            "title": "Vue 深度应用",
            "description": "适合 Vue 组件设计、Composition API 和工程实践类员工。",
            "url": "https://vett.sh/skills/clawhub.ai/ivangdavila/vue",
        },
        {
            "id": "frontend-browser",
            "title": "浏览器调试与性能排查",
            "description": "适合 Chrome DevTools、渲染链路和性能定位类员工。",
            "url": "https://vett.sh/skills/clawhub.ai/ivangdavila/chrome",
        },
        {
            "id": "frontend-architecture",
            "title": "架构设计与技术选型",
            "description": "适合系统拆分、边界设计、技术取舍和演进治理类员工。",
            "url": "https://vett.sh/skills/clawhub.ai/ivangdavila/software-architect",
        },
        {
            "id": "frontend-nodejs",
            "title": "JavaScript / Node.js 工程实践",
            "description": "适合 JS 工具链、构建脚本、运行时治理和工程交付类员工。",
            "url": "https://vett.sh/skills/clawhub.ai/ivangdavila/nodejs",
        },
    ]


def default_public_contact_channels() -> list[dict[str, object]]:
    return []


def default_system_mcp_config() -> dict[str, object]:
    return {
        "mcpServers": {
            "prompts.chat": {
                "url": DEFAULT_PROMPTS_CHAT_URL,
                "enabled": True,
            }
        }
    }


def default_skill_registry_sources() -> dict[str, object]:
    return {
        "vett": {
            "enabled": True,
            "base_url": DEFAULT_VETT_BASE_URL,
            "timeout_ms": 10000,
            "risk_policy": {
                "allow": ["none", "low", "medium"],
                "review": ["high"],
                "deny": ["critical"],
            },
        }
    }


def normalize_system_mcp_config(value: object) -> dict[str, object]:
    normalized = deepcopy(default_system_mcp_config())
    if not isinstance(value, dict):
        return normalized

    merged = dict(value)
    servers: dict[str, dict[str, object]] = {}
    raw_servers = value.get("mcpServers")
    if isinstance(raw_servers, dict):
        for raw_name, raw_server in raw_servers.items():
            name = str(raw_name or "").strip()
            if not name or not isinstance(raw_server, dict):
                continue
            servers[name] = dict(raw_server)

    prompts_chat = dict(servers.get("prompts.chat") or {})
    prompts_chat["url"] = str(prompts_chat.get("url") or DEFAULT_PROMPTS_CHAT_URL).strip() or DEFAULT_PROMPTS_CHAT_URL
    prompts_chat["enabled"] = bool(prompts_chat.get("enabled", True))
    servers["prompts.chat"] = prompts_chat
    for name, server in list(servers.items()):
        normalized_server = dict(server)
        normalized_server["enabled"] = bool(normalized_server.get("enabled", True))
        if "url" in normalized_server:
            normalized_server["url"] = str(normalized_server.get("url") or "").strip()
        servers[name] = normalized_server
    merged["mcpServers"] = servers
    normalized.update(merged)
    return normalized


def normalize_employee_external_skill_sites(value: object) -> list[dict[str, object]]:
    defaults = default_employee_external_skill_sites()
    if not isinstance(value, list):
        return defaults

    normalized: list[dict[str, object]] = []
    seen: set[str] = set()
    for raw_item in value:
        if not isinstance(raw_item, dict):
            continue
        item_id = str(raw_item.get("id") or "").strip()[:80]
        title = str(raw_item.get("title") or "").strip()[:120]
        description = str(raw_item.get("description") or "").strip()[:280]
        url = str(raw_item.get("url") or "").strip()[:500]
        dedupe_key = (item_id or title or url).lower()
        if not dedupe_key or dedupe_key in seen or not url:
            continue
        seen.add(dedupe_key)
        normalized.append(
            {
                "id": item_id or f"site-{len(normalized) + 1}",
                "title": title or "未命名站点",
                "description": description,
                "url": url,
            }
        )
        if len(normalized) >= 20:
            break
    return normalized


def normalize_public_contact_channels(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []

    normalized: list[dict[str, object]] = []
    seen: set[str] = set()
    for raw_item in value:
        if not isinstance(raw_item, dict):
            continue
        channel_type = str(raw_item.get("type") or "qq_group").strip().lower()
        if channel_type != "qq_group":
            continue
        item_id = str(raw_item.get("id") or "").strip()[:80]
        title = str(raw_item.get("title") or "").strip()[:120]
        description = str(raw_item.get("description") or "").strip()[:280]
        qq_group_number = "".join(
            char for char in str(raw_item.get("qq_group_number") or "") if char.isdigit()
        )[:32]
        button_text = str(raw_item.get("button_text") or "").strip()[:40]
        guide_text = str(raw_item.get("guide_text") or "").strip()[:160]
        join_link = str(raw_item.get("join_link") or "").strip()[:500]
        qr_image_url = str(raw_item.get("qr_image_url") or "").strip()[:500]
        try:
            sort_order = int(raw_item.get("sort_order") or 0)
        except (TypeError, ValueError):
            sort_order = 0
        sort_order = max(0, min(999, sort_order))
        dedupe_key = (item_id or qq_group_number or title).lower()
        if not dedupe_key or dedupe_key in seen:
            continue
        if not qq_group_number and not join_link and not qr_image_url:
            continue
        seen.add(dedupe_key)
        normalized.append(
            {
                "id": item_id or f"contact-{len(normalized) + 1}",
                "enabled": bool(raw_item.get("enabled", True)),
                "type": "qq_group",
                "title": title or "加入用户交流群",
                "description": description,
                "qq_group_number": qq_group_number,
                "button_text": button_text or "复制群号",
                "guide_text": guide_text or "打开 QQ，搜索群号加入。",
                "join_link": join_link,
                "qr_image_url": qr_image_url,
                "sort_order": sort_order,
            }
        )
        if len(normalized) >= 10:
            break
    return normalized


def normalize_skill_registry_sources(value: object) -> dict[str, object]:
    defaults = deepcopy(default_skill_registry_sources())
    if not isinstance(value, dict):
        return defaults

    normalized = deepcopy(defaults)
    raw_vett = value.get("vett")
    if not isinstance(raw_vett, dict):
        return normalized

    vett = dict(raw_vett)
    base_url = str(vett.get("base_url") or DEFAULT_VETT_BASE_URL).strip() or DEFAULT_VETT_BASE_URL
    try:
        timeout_ms = int(vett.get("timeout_ms") or 10000)
    except (TypeError, ValueError):
        timeout_ms = 10000
    timeout_ms = max(1000, min(60000, timeout_ms))

    raw_policy = vett.get("risk_policy")
    default_policy = defaults["vett"]["risk_policy"]
    normalized_policy: dict[str, list[str]] = {}
    for key in ("allow", "review", "deny"):
        source_values = raw_policy.get(key) if isinstance(raw_policy, dict) else default_policy.get(key)
        items: list[str] = []
        seen: set[str] = set()
        for item in source_values if isinstance(source_values, list) else []:
            text = str(item or "").strip().lower()
            if not text or text in seen:
                continue
            seen.add(text)
            items.append(text)
        normalized_policy[key] = items or list(default_policy.get(key) or [])

    normalized["vett"] = {
        "enabled": bool(vett.get("enabled", True)),
        "base_url": base_url.rstrip("/"),
        "timeout_ms": timeout_ms,
        "risk_policy": normalized_policy,
    }
    return normalized


def normalize_dictionaries(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}

    def normalize_image_resolution_token(raw: object) -> str:
        text = str(raw or "").strip()
        if not text:
            return ""
        lowered = text.lower()
        alias_map = {
            "720p": "720x720",
            "1080p": "1080x1080",
            "fhd": "1080x1080",
            "fullhd": "1080x1080",
            "4k": "2160x2160",
            "uhd": "2160x2160",
            "2160p": "2160x2160",
        }
        if lowered in alias_map:
            return alias_map[lowered]
        if lowered.endswith("p") and lowered[:-1].isdigit():
            base = lowered[:-1]
            return f"{base}x{base}"
        if "x" in lowered or "*" in lowered:
            raw_width, _, raw_height = lowered.replace("*", "x").partition("x")
            if raw_width.isdigit() and raw_height.isdigit():
                return f"{int(raw_width)}x{int(raw_height)}"
        return text

    normalized: dict[str, object] = {}
    for raw_key, raw_definition in value.items():
        dictionary_key = str(raw_key or "").strip()[:80]
        if not dictionary_key or not isinstance(raw_definition, dict):
            continue

        options: list[dict[str, str]] = []
        seen_option_ids: set[str] = set()
        for raw_option in raw_definition.get("options") if isinstance(raw_definition.get("options"), list) else []:
            if not isinstance(raw_option, dict):
                continue
            option_id = str(raw_option.get("id") or "").strip()[:80]
            if dictionary_key == "llm_image_resolutions":
                option_id = normalize_image_resolution_token(option_id)[:80]
            if not option_id or option_id in seen_option_ids:
                continue
            seen_option_ids.add(option_id)
            option_label = str(raw_option.get("label") or option_id).strip()[:120] or option_id
            if dictionary_key == "llm_image_resolutions":
                option_label = normalize_image_resolution_token(option_label)[:120] or option_id
            options.append(
                {
                    "id": option_id,
                    "label": option_label,
                    "description": str(raw_option.get("description") or "").strip()[:500],
                    "chat_parameter_mode": str(raw_option.get("chat_parameter_mode") or "").strip()[:40],
                }
            )
            if len(options) >= 100:
                break

        default_value = str(raw_definition.get("default_value") or "").strip()[:80]
        if dictionary_key == "llm_image_resolutions":
            default_value = normalize_image_resolution_token(default_value)[:80]

        definition: dict[str, Any] = {
            "key": dictionary_key,
            "label": str(raw_definition.get("label") or "").strip()[:120],
            "description": str(raw_definition.get("description") or "").strip()[:500],
            "default_value": default_value,
            "options": options,
        }
        normalized[dictionary_key] = definition

    return normalized


@dataclass
class SystemConfig:
    id: str = "global"
    enable_project_manual_generation: bool = False
    enable_employee_manual_generation: bool = False
    enable_user_register: bool = True
    chat_upload_max_limit: int = 6
    chat_max_tokens: int = 512
    default_chat_system_prompt: str = ""
    employee_auto_rule_generation_enabled: bool = True
    employee_auto_rule_generation_source_filters: list[str] = field(
        default_factory=lambda: ["prompts_chat_curated"]
    )
    employee_auto_rule_generation_max_count: int = 3
    employee_auto_rule_generation_prompt: str = DEFAULT_EMPLOYEE_RULE_GENERATION_PROMPT
    employee_external_skill_sites: list[dict[str, object]] = field(
        default_factory=default_employee_external_skill_sites
    )
    public_contact_channels: list[dict[str, object]] = field(
        default_factory=default_public_contact_channels
    )
    skill_registry_sources: dict[str, object] = field(
        default_factory=default_skill_registry_sources
    )
    dictionaries: dict[str, object] = field(default_factory=dict)
    mcp_config: dict[str, object] = field(default_factory=default_system_mcp_config)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def __post_init__(self) -> None:
        self.default_chat_system_prompt = str(self.default_chat_system_prompt or "").strip()[:8000]
        self.employee_auto_rule_generation_source_filters = [
            str(item or "").strip()
            for item in (self.employee_auto_rule_generation_source_filters or [])
            if str(item or "").strip()
        ][:12] or ["prompts_chat_curated"]
        try:
            self.employee_auto_rule_generation_max_count = int(
                self.employee_auto_rule_generation_max_count or 3
            )
        except (TypeError, ValueError):
            self.employee_auto_rule_generation_max_count = 3
        self.employee_auto_rule_generation_max_count = max(
            1, min(6, self.employee_auto_rule_generation_max_count)
        )
        self.employee_auto_rule_generation_prompt = str(
            self.employee_auto_rule_generation_prompt or DEFAULT_EMPLOYEE_RULE_GENERATION_PROMPT
        ).strip()[:8000] or DEFAULT_EMPLOYEE_RULE_GENERATION_PROMPT
        self.employee_external_skill_sites = normalize_employee_external_skill_sites(
            self.employee_external_skill_sites
        )
        self.public_contact_channels = normalize_public_contact_channels(
            self.public_contact_channels
        )
        self.skill_registry_sources = normalize_skill_registry_sources(
            self.skill_registry_sources
        )
        self.dictionaries = normalize_dictionaries(self.dictionaries)
        self.mcp_config = normalize_system_mcp_config(self.mcp_config)


class SystemConfigStore:
    def __init__(self, data_dir: Path) -> None:
        self._path = data_dir / "system-config.json"

    def get_global(self) -> SystemConfig:
        if not self._path.exists():
            return SystemConfig()
        data = json.loads(self._path.read_text(encoding="utf-8"))
        config = SystemConfig(**data)
        if asdict(config) != data:
            self.save_global(config)
        return config

    def save_global(self, config: SystemConfig) -> None:
        self._path.write_text(
            json.dumps(asdict(config), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def patch_global(self, updates: dict) -> SystemConfig:
        current = self.get_global()
        payload = asdict(current)
        payload.update(updates)
        payload["updated_at"] = _now_iso()
        if not payload.get("created_at"):
            payload["created_at"] = _now_iso()
        updated = SystemConfig(**payload)
        self.save_global(updated)
        return updated
