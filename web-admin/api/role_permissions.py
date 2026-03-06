"""角色权限目录定义"""

from __future__ import annotations

from collections.abc import Iterable

MENU_PERMISSION_ITEMS = [
    {"key": "menu.ai.chat", "label": "AI 对话", "path": "/ai/chat"},
    {"key": "menu.projects", "label": "项目管理", "path": "/projects"},
    {"key": "menu.employees", "label": "员工管理", "path": "/employees"},
    {"key": "menu.employees.create", "label": "创建员工", "path": "/employees/create"},
    {"key": "menu.users", "label": "用户管理", "path": "/users"},
    {"key": "menu.roles", "label": "角色管理", "path": "/roles"},
    {"key": "menu.skills", "label": "技能目录", "path": "/skills"},
    {"key": "menu.rules", "label": "规则管理", "path": "/rules"},
    {"key": "menu.system.config", "label": "系统配置", "path": "/system/config"},
    {"key": "menu.llm.providers", "label": "模型供应商", "path": "/llm/providers"},
    {"key": "menu.usage.keys", "label": "API Key", "path": "/usage/keys"},
]

BUTTON_PERMISSION_ITEMS = [
    {"key": "button.project.chat", "label": "项目详情-AI对话"},
    {"key": "button.users.create", "label": "用户管理-新增用户"},
    {"key": "button.users.update_password", "label": "用户管理-重置密码"},
    {"key": "button.users.delete", "label": "用户管理-删除用户"},
    {"key": "button.roles.create", "label": "角色管理-新增角色"},
    {"key": "button.roles.update", "label": "角色管理-编辑角色"},
    {"key": "button.roles.delete", "label": "角色管理-删除角色"},
    {"key": "button.apikey.create", "label": "API Key-创建"},
    {"key": "button.apikey.deactivate", "label": "API Key-停用"},
]

ALL_PERMISSION_KEYS = {
    item["key"] for item in MENU_PERMISSION_ITEMS + BUTTON_PERMISSION_ITEMS
}

DEFAULT_USER_PERMISSION_KEYS = sorted(
    {
        "menu.ai.chat",
        "menu.projects",
        "menu.employees",
        "menu.employees.create",
        "menu.skills",
        "menu.rules",
        "menu.system.config",
        "menu.llm.providers",
        "menu.usage.keys",
        "button.project.chat",
        "button.apikey.create",
        "button.apikey.deactivate",
    }
)


def normalize_permissions(values: Iterable[str] | None) -> list[str]:
    """过滤无效权限并去重。保留 '*' 超级权限。"""
    if not values:
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in values:
        key = str(raw or "").strip()
        if not key:
            continue
        if key == "*":
            return ["*"]
        if key not in ALL_PERMISSION_KEYS:
            continue
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(key)
    return sorted(cleaned)


def resolve_role_permissions(role_permissions: Iterable[str] | None, role_id: str = "") -> list[str]:
    """将角色权限补全为最终可用权限集。"""
    normalized = normalize_permissions(role_permissions)
    if "*" in normalized:
        return ["*"]
    role_token = str(role_id or "").strip().lower()
    if normalized:
        return normalized
    if role_token == "admin":
        return ["*"]
    if role_token == "user":
        return list(DEFAULT_USER_PERMISSION_KEYS)
    return []


def has_permission(permission_list: Iterable[str] | None, permission_key: str) -> bool:
    normalized = resolve_role_permissions(permission_list)
    if "*" in normalized:
        return True
    target = str(permission_key or "").strip()
    if not target:
        return True
    return target in set(normalized)


def permission_catalog() -> dict:
    return {
        "groups": [
            {"group": "menu", "label": "菜单权限", "items": MENU_PERMISSION_ITEMS},
            {"group": "button", "label": "按钮权限", "items": BUTTON_PERMISSION_ITEMS},
        ],
        "all_keys": sorted(ALL_PERMISSION_KEYS),
    }
