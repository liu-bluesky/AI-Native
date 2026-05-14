"""Helpers for using chat runtime context objects."""

from __future__ import annotations

from typing import Any

from services.runtime.runtime_types import ChatRuntimeContext


def runtime_messages(context: ChatRuntimeContext) -> list[dict[str, Any]]:
    return [dict(item) for item in context.resolved_messages]


def runtime_tools(context: ChatRuntimeContext) -> list[dict[str, Any]]:
    return [dict(item) for item in context.resolved_tools]


def runtime_capability_routing(context: ChatRuntimeContext) -> dict[str, Any]:
    return dict(context.capability_routing or {})
