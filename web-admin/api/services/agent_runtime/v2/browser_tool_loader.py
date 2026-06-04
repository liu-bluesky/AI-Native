"""Browser tool definitions for agent_runtime_v2."""

from __future__ import annotations

from typing import Any

from services.assistant.global_assistant_service import (
    GLOBAL_ASSISTANT_BROWSER_ACTIONS_TOOL_NAME,
    GLOBAL_ASSISTANT_BROWSER_REQUESTS_TOOL_NAME,
    build_global_assistant_builtin_tools,
)


BROWSER_TOOL_NAMES = {
    GLOBAL_ASSISTANT_BROWSER_REQUESTS_TOOL_NAME,
    GLOBAL_ASSISTANT_BROWSER_ACTIONS_TOOL_NAME,
}


def build_browser_runtime_tools(
    *,
    enabled: bool,
    bridge_available: bool,
) -> list[dict[str, Any]]:
    if not enabled:
        return []
    tools: list[dict[str, Any]] = []
    for item in build_global_assistant_builtin_tools():
        tool_name = str(item.get("tool_name") or "").strip()
        if tool_name not in BROWSER_TOOL_NAMES:
            continue
        payload = dict(item)
        payload.update(
            {
                "source": "browser",
                "plugin_id": "browser-tools",
                "plugin_name": "Browser Tools",
                "installed": bool(bridge_available),
                "requires_trust": True,
                "requires_browser_bridge": True,
                "load_status": "available" if bridge_available else "bridge_unavailable",
                "version": "builtin",
            }
        )
        tools.append(payload)
    return tools
