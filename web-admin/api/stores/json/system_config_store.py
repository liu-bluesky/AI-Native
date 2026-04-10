"""系统配置存储层"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit


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


def default_global_assistant_guide_modules() -> list[dict[str, object]]:
    return [
        {
            "id": "ai-chat",
            "name": "AI 对话中心",
            "summary": "统一的 AI 对话入口，可用于系统咨询、项目协作、状态排查和需求推进。",
            "paths": ["/ai/chat"],
            "permission": "menu.ai.chat",
            "enabled": True,
            "is_public": False,
            "sort_order": 10,
        },
        {
            "id": "projects",
            "name": "项目管理",
            "summary": "管理项目、项目成员、项目聊天设置与项目级工作入口。",
            "paths": ["/projects"],
            "permission": "menu.projects",
            "enabled": True,
            "is_public": False,
            "sort_order": 20,
        },
        {
            "id": "employees",
            "name": "员工管理",
            "summary": "配置 AI 员工、职责、技能绑定、规则绑定和使用手册。",
            "paths": ["/employees"],
            "permission": "menu.employees",
            "enabled": True,
            "is_public": False,
            "sort_order": 30,
        },
        {
            "id": "skills",
            "name": "技能目录",
            "summary": "维护技能、技能资源与可复用能力资产。",
            "paths": ["/skills", "/skill-resources"],
            "permission": "menu.skills",
            "enabled": True,
            "is_public": False,
            "sort_order": 40,
        },
        {
            "id": "rules",
            "name": "规则管理",
            "summary": "维护通用规则、项目规则与员工规则，用于约束 AI 输出和执行方式。",
            "paths": ["/rules"],
            "permission": "menu.rules",
            "enabled": True,
            "is_public": False,
            "sort_order": 50,
        },
        {
            "id": "system-config",
            "name": "系统配置",
            "summary": "配置系统级开关、语音能力、默认提示词和运行参数。",
            "paths": ["/system/config"],
            "permission": "menu.system.config",
            "enabled": True,
            "is_public": False,
            "sort_order": 60,
        },
        {
            "id": "llm-providers",
            "name": "模型供应商",
            "summary": "接入文本、语音、图像等模型供应商，并配置默认模型。",
            "paths": ["/llm/providers"],
            "permission": "menu.llm.providers",
            "enabled": True,
            "is_public": False,
            "sort_order": 70,
        },
        {
            "id": "users-roles",
            "name": "用户与角色",
            "summary": "管理账号、角色、菜单权限和按钮权限。",
            "paths": ["/users", "/roles"],
            "permission": "menu.users",
            "enabled": True,
            "is_public": False,
            "sort_order": 80,
        },
        {
            "id": "materials",
            "name": "素材工作区",
            "summary": "查看素材库、声音资产和产出作品。",
            "paths": ["/materials", "/materials/voices", "/materials/works"],
            "permission": "",
            "enabled": True,
            "is_public": False,
            "sort_order": 90,
        },
        {
            "id": "studio",
            "name": "短片工作台",
            "summary": "围绕分镜、音轨、导出等流程完成短片制作。",
            "paths": ["/materials/studio"],
            "permission": "",
            "enabled": True,
            "is_public": False,
            "sort_order": 100,
        },
        {
            "id": "intro",
            "name": "官网介绍页",
            "summary": "对外展示产品定位、核心能力和整体工作流。",
            "paths": ["/intro"],
            "permission": "",
            "enabled": True,
            "is_public": True,
            "sort_order": 110,
        },
        {
            "id": "market",
            "name": "官网市场页",
            "summary": "对外展示产品能力、案例与市场化介绍内容。",
            "paths": ["/market"],
            "permission": "",
            "enabled": True,
            "is_public": True,
            "sort_order": 120,
        },
        {
            "id": "updates",
            "name": "官网更新页",
            "summary": "对外展示版本更新、功能变更和产品迭代记录。",
            "paths": ["/updates"],
            "permission": "",
            "enabled": True,
            "is_public": True,
            "sort_order": 130,
        },
    ]


def normalize_voice_allowed_usernames(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_item in value:
        username = str(raw_item or "").strip()[:120]
        if not username:
            continue
        dedupe_key = username.lower()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized.append(username)
        if len(normalized) >= 200:
            break
    return normalized


def normalize_voice_allowed_role_ids(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_item in value:
        role_id = str(raw_item or "").strip().lower()[:64]
        if not role_id or role_id in seen:
            continue
        seen.add(role_id)
        normalized.append(role_id)
        if len(normalized) >= 50:
            break
    return normalized


def normalize_global_assistant_wake_phrase(value: object) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = " ".join(part for part in text.split())
    return text.strip()[:80] or "你好助手"


def normalize_global_assistant_idle_timeout_sec(value: object) -> int:
    try:
        timeout_sec = int(value or 5)
    except (TypeError, ValueError):
        timeout_sec = 5
    return max(3, min(30, timeout_sec))


DEFAULT_GLOBAL_ASSISTANT_GREETING_TEXT = (
    "你好，我是系统状态助手。我会默认保持实时通话，随时帮你观察当前页面、系统状态和功能是否可用。"
)
DEFAULT_GLOBAL_ASSISTANT_SYSTEM_PROMPT = (
    "你是系统状态助手。\n"
    "你的职责是基于当前页面、实时系统快照和本轮对话消息，直接回答系统状态、当前页面、当前项目、当前账号、功能可用性相关问题。\n"
    "你已经拿到本轮对话历史和实时快照；禁止回答“我无法访问之前的对话历史”或“我没有上下文”。\n"
    "如果答案就在本轮消息或快照里，直接给结论；如果快照里没有，就明确说明“当前快照里没有这项数据”，并指出缺少什么信息。\n"
    "不要把用户打回去重新描述，除非用户问题本身含糊到无法判断目标。\n"
    "当用户询问这个系统做什么、有哪些功能、怎么使用、去哪里配置、哪个页面负责什么时，先调用 global_assistant_system_guide 再回答。\n"
    "当用户询问当前页面接口状态、最近请求、响应数据、报错接口或页面是否真的拿到数据时，优先调用 global_assistant_browser_requests。\n"
    "当用户要求你检查页面元素、读取页面文字、点击、输入、选择、滚动、按键、切换页面、跳转路由或直接执行页面脚本时，优先调用 global_assistant_browser_actions。\n"
    "执行 click、fill、select 前，如果页面里是图标按钮或存在多个相邻按钮，先用 query_dom 查看候选元素，并优先使用 data-testid、id、aria-label、title 这些唯一标识来构造 selector；不要猜测或使用过宽的 .el-button、button:nth-child(...) 之类 selector。"
)
DEFAULT_GLOBAL_ASSISTANT_TRANSCRIPTION_PROMPT = (
    "请严格逐字转写用户原话，只输出识别到的中文文本；不要补充、不要改写、不要总结、不要猜测、不要重复上一句；听不清就留空。"
)


def normalize_global_assistant_greeting_audio(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, object] = {}
    signature = str(value.get("signature") or "").strip()[:64]
    if signature:
        normalized["signature"] = signature
    storage_path = str(value.get("storage_path") or "").strip()[:500]
    if storage_path:
        normalized["storage_path"] = storage_path
    content_type = str(value.get("content_type") or "").strip()[:120]
    if content_type:
        normalized["content_type"] = content_type
    generated_at = str(value.get("generated_at") or "").strip()[:80]
    if generated_at:
        normalized["generated_at"] = generated_at
    try:
        file_size_bytes = int(value.get("file_size_bytes") or 0)
    except (TypeError, ValueError):
        file_size_bytes = 0
    if file_size_bytes > 0:
        normalized["file_size_bytes"] = file_size_bytes
    return normalized


def normalize_public_changelog(value: object) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return text.strip()[:24000]


def normalize_query_mcp_public_base_url(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = urlsplit(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    if parsed.query or parsed.fragment:
        return ""
    normalized_path = str(parsed.path or "").strip().rstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, normalized_path, "", ""))


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


def _normalize_global_assistant_guide_module_id(raw_value: object, fallback: str) -> str:
    text = str(raw_value or "").strip().lower()[:80]
    for source, target in (
        (" ", "-"),
        ("/", "-"),
        ("\\", "-"),
        (".", "-"),
        (":", "-"),
    ):
        text = text.replace(source, target)
    while "--" in text:
        text = text.replace("--", "-")
    text = text.strip("-_")
    if text:
        return text
    return fallback


def normalize_global_assistant_guide_modules(value: object) -> list[dict[str, object]]:
    defaults = deepcopy(default_global_assistant_guide_modules())
    if not isinstance(value, list):
        return defaults

    normalized: list[dict[str, object]] = []
    seen: set[str] = set()
    for raw_item in value:
        if not isinstance(raw_item, dict):
            continue
        raw_paths = raw_item.get("paths")
        path_values = raw_paths if isinstance(raw_paths, list) else [raw_paths]
        paths: list[str] = []
        seen_paths: set[str] = set()
        for raw_path in path_values:
            path = str(raw_path or "").strip()[:240]
            if not path or path in seen_paths:
                continue
            seen_paths.add(path)
            paths.append(path)
            if len(paths) >= 12:
                break
        name = str(raw_item.get("name") or "").strip()[:120]
        summary = str(raw_item.get("summary") or "").strip()[:280]
        permission = str(raw_item.get("permission") or "").strip()[:120]
        fallback_id = f"module-{len(normalized) + 1}"
        module_id = _normalize_global_assistant_guide_module_id(
            raw_item.get("id") or name or (paths[0] if paths else ""),
            fallback_id,
        )
        dedupe_key = module_id.lower()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        try:
            sort_order = int(raw_item.get("sort_order") or 0)
        except (TypeError, ValueError):
            sort_order = 0
        sort_order = max(0, min(999, sort_order))
        normalized.append(
            {
                "id": module_id,
                "name": name or module_id,
                "summary": summary,
                "paths": paths,
                "permission": permission,
                "enabled": bool(raw_item.get("enabled", True)),
                "is_public": bool(raw_item.get("is_public", False)),
                "sort_order": sort_order,
            }
        )
        if len(normalized) >= 40:
            break
    if not normalized:
        return defaults
    return sorted(
        normalized,
        key=lambda item: (
            int(item.get("sort_order") or 0),
            str(item.get("name") or "").strip(),
            str(item.get("id") or "").strip(),
        ),
    )


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
    global_assistant_guide_modules: list[dict[str, object]] = field(
        default_factory=default_global_assistant_guide_modules
    )
    voice_input_enabled: bool = False
    voice_input_provider_id: str = ""
    voice_input_model_name: str = ""
    voice_input_allowed_usernames: list[str] = field(default_factory=list)
    voice_input_allowed_role_ids: list[str] = field(default_factory=list)
    voice_output_enabled: bool = False
    voice_output_provider_id: str = ""
    voice_output_model_name: str = ""
    voice_output_voice: str = ""
    global_assistant_greeting_enabled: bool = True
    global_assistant_greeting_text: str = DEFAULT_GLOBAL_ASSISTANT_GREETING_TEXT
    global_assistant_chat_provider_id: str = ""
    global_assistant_chat_model_name: str = ""
    global_assistant_system_prompt: str = DEFAULT_GLOBAL_ASSISTANT_SYSTEM_PROMPT
    global_assistant_transcription_prompt: str = DEFAULT_GLOBAL_ASSISTANT_TRANSCRIPTION_PROMPT
    global_assistant_wake_phrase: str = "你好助手"
    global_assistant_idle_timeout_sec: int = 5
    global_assistant_greeting_audio: dict[str, object] = field(default_factory=dict)
    public_contact_channels: list[dict[str, object]] = field(
        default_factory=default_public_contact_channels
    )
    public_changelog: str = ""
    query_mcp_public_base_url: str = ""
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
        self.query_mcp_public_base_url = normalize_query_mcp_public_base_url(
            self.query_mcp_public_base_url
        )
        self.employee_auto_rule_generation_max_count = max(
            1, min(6, self.employee_auto_rule_generation_max_count)
        )
        self.employee_auto_rule_generation_prompt = str(
            self.employee_auto_rule_generation_prompt or DEFAULT_EMPLOYEE_RULE_GENERATION_PROMPT
        ).strip()[:8000] or DEFAULT_EMPLOYEE_RULE_GENERATION_PROMPT
        self.employee_external_skill_sites = normalize_employee_external_skill_sites(
            self.employee_external_skill_sites
        )
        self.global_assistant_guide_modules = normalize_global_assistant_guide_modules(
            self.global_assistant_guide_modules
        )
        self.voice_input_provider_id = str(self.voice_input_provider_id or "").strip()[:120]
        self.voice_input_model_name = str(self.voice_input_model_name or "").strip()[:160]
        self.voice_input_allowed_usernames = normalize_voice_allowed_usernames(
            self.voice_input_allowed_usernames
        )
        self.voice_input_allowed_role_ids = normalize_voice_allowed_role_ids(
            self.voice_input_allowed_role_ids
        )
        self.voice_output_provider_id = str(self.voice_output_provider_id or "").strip()[:120]
        self.voice_output_model_name = str(self.voice_output_model_name or "").strip()[:160]
        self.voice_output_voice = str(self.voice_output_voice or "").strip()[:200]
        self.global_assistant_chat_provider_id = str(
            self.global_assistant_chat_provider_id or ""
        ).strip()[:120]
        self.global_assistant_chat_model_name = str(
            self.global_assistant_chat_model_name or ""
        ).strip()[:160]
        self.global_assistant_greeting_text = str(
            self.global_assistant_greeting_text
            or DEFAULT_GLOBAL_ASSISTANT_GREETING_TEXT
        ).strip()[:1000]
        self.global_assistant_system_prompt = str(
            self.global_assistant_system_prompt or DEFAULT_GLOBAL_ASSISTANT_SYSTEM_PROMPT
        ).strip()[:8000]
        self.global_assistant_transcription_prompt = str(
            self.global_assistant_transcription_prompt or DEFAULT_GLOBAL_ASSISTANT_TRANSCRIPTION_PROMPT
        ).strip()[:1000]
        self.global_assistant_wake_phrase = normalize_global_assistant_wake_phrase(
            self.global_assistant_wake_phrase
        )
        self.global_assistant_idle_timeout_sec = normalize_global_assistant_idle_timeout_sec(
            self.global_assistant_idle_timeout_sec
        )
        self.global_assistant_greeting_audio = normalize_global_assistant_greeting_audio(
            self.global_assistant_greeting_audio
        )
        self.public_contact_channels = normalize_public_contact_channels(
            self.public_contact_channels
        )
        self.public_changelog = normalize_public_changelog(self.public_changelog)
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
