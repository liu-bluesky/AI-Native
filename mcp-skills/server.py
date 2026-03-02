"""技能管理 MCP 服务入口"""

from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from store import (
    SkillStore, BindingStore, EmployeeSkillBinding,
    _serialize_skill, _now_iso,
)

DATA_DIR = Path(__file__).parent / "knowledge"

mcp = FastMCP("skills-service")
skill_store = SkillStore(DATA_DIR)
binding_store = BindingStore(DATA_DIR)


# ── Tools ──

@mcp.tool()
def get_skill(skill_id: str, version: str = "") -> dict:
    """获取技能详情"""
    s = skill_store.get(skill_id)
    if s is None:
        return {"error": f"Skill {skill_id} not found"}
    if version and s.version != version:
        return {"error": f"Skill {skill_id} version {version} not found, current: {s.version}"}
    return _serialize_skill(s)


@mcp.tool()
def list_skills(tags: str = "", domain: str = "") -> list[dict]:
    """列出可用技能，可按标签和领域过滤"""
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    results = skill_store.query(tags=tag_list, domain=domain or None)
    return [_serialize_skill(s) for s in results]


@mcp.tool()
def install_skill(employee_id: str, skill_id: str) -> dict:
    """安装技能到 AI 员工"""
    s = skill_store.get(skill_id)
    if s is None:
        return {"error": f"Skill {skill_id} not found"}
    tool_names = tuple(t.name for t in s.tools)
    binding = EmployeeSkillBinding(
        employee_id=employee_id, skill_id=skill_id,
        enabled_tools=tool_names,
    )
    binding_store.add(binding)
    return {"status": "installed", "employee_id": employee_id,
            "skill_id": skill_id, "enabled_tools": list(tool_names)}


@mcp.tool()
def uninstall_skill(employee_id: str, skill_id: str) -> dict:
    """从 AI 员工卸载技能"""
    removed = binding_store.remove(employee_id, skill_id)
    if not removed:
        return {"error": f"Skill {skill_id} not bound to {employee_id}"}
    return {"status": "uninstalled", "employee_id": employee_id,
            "skill_id": skill_id}


# ── Resources ──

@mcp.resource("skill://catalog")
def skill_catalog() -> str:
    """技能目录"""
    skills = skill_store.list_all()
    lines = [f"[{s.id}] {s.name} v{s.version} | {s.description} | tags: {','.join(s.tags)}"
             for s in skills]
    return "\n".join(lines) if lines else "技能库为空"


@mcp.resource("skill://{skill_id}")
def skill_detail(skill_id: str) -> str:
    """技能详情"""
    s = skill_store.get(skill_id)
    if s is None:
        return f"Skill {skill_id} not found"
    tools_str = "\n".join(f"  - {t.name}: {t.description}" for t in s.tools)
    return f"# {s.name} v{s.version}\n{s.description}\n\nTools:\n{tools_str}"


@mcp.resource("skill://{skill_id}/tools")
def skill_tools(skill_id: str) -> str:
    """技能工具列表"""
    s = skill_store.get(skill_id)
    if s is None:
        return f"Skill {skill_id} not found"
    lines = [f"- {t.name}: {t.description}" for t in s.tools]
    return "\n".join(lines) if lines else "该技能暂无工具"


# ── Entry Point ──

if __name__ == "__main__":
    mcp.run()
