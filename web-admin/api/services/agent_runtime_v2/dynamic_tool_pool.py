"""Effective tool pool helpers for agent_runtime_v2."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from services.agent_runtime_v2.browser_tool_loader import build_browser_runtime_tools
from services.agent_runtime_v2.plugin_registry import (
    PluginRegistry,
    PluginRegistryContext,
    RuntimeToolEntry,
)


@dataclass
class DynamicToolPool:
    entries: list[RuntimeToolEntry] = field(default_factory=list)
    registry_summary: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_runtime_tools(
        cls,
        tools: list[dict[str, Any]] | None,
        *,
        tool_priority: list[str] | None = None,
        context: PluginRegistryContext | None = None,
    ) -> "DynamicToolPool":
        runtime_tools = list(tools or [])
        if context is not None and context.include_browser_tools:
            runtime_tools.extend(
                build_browser_runtime_tools(
                    enabled=True,
                    bridge_available=context.browser_bridge_available,
                )
            )
        registry = PluginRegistry.from_runtime_tools(runtime_tools, context=context)
        priority_order = {
            str(item or "").strip(): index
            for index, item in enumerate(tool_priority or [])
            if str(item or "").strip()
        }
        entries = sorted(
            registry.available_entries(),
            key=lambda item: (
                priority_order.get(item.tool_name, len(priority_order)),
                item.tool_name,
            ),
        )
        return cls(entries=entries, registry_summary=registry.summary())

    def names(self) -> list[str]:
        return [item.tool_name for item in self.entries if item.tool_name]

    def openai_tools(self) -> list[dict[str, Any]]:
        return [item.openai_tool() for item in self.entries]

    def summary(self, *, max_items: int = 24) -> dict[str, Any]:
        tools = [item.summary() for item in self.entries]
        return {
            "effective_tools": tools[:max_items],
            "effective_tool_total": len(tools),
            "tool_names": self.names(),
            "plugin_registry": dict(self.registry_summary),
        }
