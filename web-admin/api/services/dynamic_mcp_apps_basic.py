"""Basic dynamic MCP app builders for rules and skills."""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from services.dynamic_mcp_transports import DualTransportMcpApp, apply_mcp_arguments_compat
from stores.mcp_bridge import rule_store, skill_store

_FASTMCP_HOST = os.environ.get("FASTMCP_HOST", "0.0.0.0")


def _new_mcp(service_name: str) -> FastMCP:
    return FastMCP(service_name, host=_FASTMCP_HOST, stateless_http=True)


def create_rule_mcp(rule_id: str):
    rule_obj = rule_store.get(rule_id)
    service_name = getattr(rule_obj, "mcp_service", "") or rule_id
    mcp = _new_mcp(service_name)

    @mcp.resource(f"rule://{rule_id}")
    def get_this_rule() -> str:
        rule = rule_store.get(rule_id)
        if not rule or not rule.mcp_enabled:
            return "Rule disabled or deleted."
        return f"[{rule.id}] {rule.title}\nSeverity: {rule.severity.value}\nContent:\n{rule.content}"

    @mcp.tool()
    def get_rule_info() -> dict:
        rule = rule_store.get(rule_id)
        if not rule or not rule.mcp_enabled:
            return {"error": "Rule not available"}
        return {"id": rule.id, "title": rule.title, "domain": rule.domain}

    return DualTransportMcpApp(
        apply_mcp_arguments_compat(mcp.sse_app()),
        mcp.streamable_http_app(),
    )


def create_skill_mcp(skill_id: str):
    skill_obj = skill_store.get(skill_id)
    service_name = getattr(skill_obj, "mcp_service", "") or skill_id
    mcp = _new_mcp(service_name)

    @mcp.resource(f"skill://{skill_id}/info")
    def get_skill_info() -> str:
        skill = skill_store.get(skill_id)
        if not skill or not skill.mcp_enabled:
            return "Skill disabled or deleted."
        return f"[{skill.id}] {skill.name}\nDescription: {skill.description}"

    @mcp.tool()
    def get_skill_tools() -> list[dict]:
        skill = skill_store.get(skill_id)
        if not skill or not skill.mcp_enabled:
            return []
        return [{"name": tool.name, "description": tool.description} for tool in skill.tools]

    return DualTransportMcpApp(
        apply_mcp_arguments_compat(mcp.sse_app()),
        mcp.streamable_http_app(),
    )
