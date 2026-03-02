"""动态 Micro-MCP 服务生成器"""
from __future__ import annotations

from fastapi.responses import JSONResponse
from mcp.server.fastmcp import FastMCP

from stores import rule_store, skill_store

# 缓存动态生成的 ASGI App
_rule_apps = {}
_skill_apps = {}

def _create_rule_mcp(rule_id: str):
    r = rule_store.get(rule_id)
    service_name = getattr(r, "mcp_service", "") or rule_id
    mcp = FastMCP(service_name)

    @mcp.resource(f"rule://{rule_id}")
    def get_this_rule() -> str:
        """获取本规则的详细内容和约束"""
        rule = rule_store.get(rule_id)
        if not rule or not rule.mcp_enabled:
            return "Rule disabled or deleted."
        return f"[{rule.id}] {rule.title}\nSeverity: {rule.severity.value}\nContent:\n{rule.content}"

    @mcp.tool()
    def get_rule_info() -> dict:
        """获取本规则的元信息"""
        rule = rule_store.get(rule_id)
        if not rule or not rule.mcp_enabled:
            return {"error": "Rule not available"}
        return {"id": rule.id, "title": rule.title, "domain": rule.domain}

    # 该 app 已经被挂载在 /mcp/rules/{rule_id}，这里不要再传 mount_path，
    # 否则 endpoint 事件会把路径重复拼接成 /mcp/.../mcp/.../messages。
    return mcp.sse_app()


def _create_skill_mcp(skill_id: str):
    s = skill_store.get(skill_id)
    service_name = getattr(s, "mcp_service", "") or skill_id
    mcp = FastMCP(service_name)

    @mcp.resource(f"skill://{skill_id}/info")
    def get_skill_info() -> str:
        s = skill_store.get(skill_id)
        if not s or not s.mcp_enabled:
            return "Skill disabled or deleted."
        return f"[{s.id}] {s.name}\nDescription: {s.description}"

    @mcp.tool()
    def get_skill_tools() -> list[dict]:
        """获取本技能包含的所有底层工具"""
        s = skill_store.get(skill_id)
        if not s or not s.mcp_enabled:
            return []
        return [{"name": t.name, "description": t.description} for t in s.tools]
        
    # 同上：由外层 app.mount 提供前缀，避免 messages 路径重复。
    return mcp.sse_app()


class _RuleMcpProxyApp:
    async def __call__(self, scope, receive, send):
        rule_id = scope.get("path_params", {}).get("rule_id")
        if not rule_id:
            response = JSONResponse({"detail": "Missing rule_id"}, status_code=400)
            await response(scope, receive, send)
            return

        rule = rule_store.get(rule_id)
        if not rule or not getattr(rule, "mcp_enabled", False):
            response = JSONResponse(
                {"detail": "Rule MCP service is disabled or rule not found."},
                status_code=404,
            )
            await response(scope, receive, send)
            return

        if rule_id not in _rule_apps:
            _rule_apps[rule_id] = _create_rule_mcp(rule_id)
        await _rule_apps[rule_id](scope, receive, send)


class _SkillMcpProxyApp:
    async def __call__(self, scope, receive, send):
        skill_id = scope.get("path_params", {}).get("skill_id")
        if not skill_id:
            response = JSONResponse({"detail": "Missing skill_id"}, status_code=400)
            await response(scope, receive, send)
            return

        skill = skill_store.get(skill_id)
        if not skill or not getattr(skill, "mcp_enabled", False):
            response = JSONResponse(
                {"detail": "Skill MCP service is disabled or skill not found."},
                status_code=404,
            )
            await response(scope, receive, send)
            return

        if skill_id not in _skill_apps:
            _skill_apps[skill_id] = _create_skill_mcp(skill_id)
        await _skill_apps[skill_id](scope, receive, send)


rule_mcp_proxy_app = _RuleMcpProxyApp()
skill_mcp_proxy_app = _SkillMcpProxyApp()
