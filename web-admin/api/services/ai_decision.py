"""AI 自主决策模块"""
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def execute_db_query(query: str) -> dict:
    """安全执行数据库查询（只读）"""
    from core.config import get_settings
    from sqlalchemy import create_engine, text

    query = query.strip()
    if not query.upper().startswith(("SELECT", "SHOW", "DESC", "EXPLAIN", "WITH")):
        return {"error": "仅支持只读查询"}

    engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            result = conn.execute(text(query))
            rows = [dict(row._mapping) for row in result.fetchmany(100)]
            return {"status": "ok", "rows": rows, "count": len(rows)}
    except Exception as e:
        return {"error": str(e)}
    finally:
        engine.dispose()


def get_db_schema_info() -> dict:
    """获取数据库表结构信息"""
    from core.config import get_settings
    db_url = get_settings().database_url
    return {
        "url_masked": db_url.split("@")[1] if "@" in db_url else "localhost",
        "tables": ["employees", "projects", "skills", "project_members", "feedbacks", "usage_records"],
    }


async def ai_decide_action(
    llm_service,
    provider_id: str,
    model_name: str,
    user_message: str,
    project_id: str,
    available_tools: list[dict],
) -> dict | None:
    """AI 自主决策执行动作"""
    from core.deps import project_store

    db_info = get_db_schema_info()
    all_projects = project_store.list_all()
    tool_names = [t.get("tool_name", "") for t in available_tools[:5]]

    system_prompt = f"""你是项目助手，可以：
1. 直接查询数据库（{db_info["url_masked"]}，表：{", ".join(db_info["tables"])}）
2. 调用项目工具：{tool_names}
3. 推荐切换到更合适的项目（系统共 {len(all_projects)} 个项目）

根据用户需求，返回 JSON（必须是有效 JSON）：
{{"action": "query_db", "query": "SELECT ...", "reason": "..."}}
或 {{"action": "call_tool", "tool": "工具名", "args": {{}}, "reason": "..."}}
或 {{"action": "recommend_project", "reason": "..."}}
或 {{"action": "chat"}}（普通对话）

规则：
- 查询数据库时直接返回 SQL
- 不要重复要求用户提供数据库信息
- 优先使用已有工具和数据库"""

    try:
        result = await llm_service.chat_completion(
            provider_id=provider_id,
            model_name=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=0.1,
            max_tokens=500,
            timeout=30,
        )
        content = str(result.get("content") or "").strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
        return json.loads(content.strip())
    except Exception as e:
        logger.warning(f"AI decision failed: {e}")
        return None


def recommend_better_project(user_message: str, current_project_id: str) -> dict | None:
    """基于用户意图推荐更合适的项目"""
    from core.deps import project_store

    all_projects = project_store.list_all()
    keywords = user_message.lower().split()

    for proj in all_projects:
        if proj.id == current_project_id:
            continue
        desc_lower = (proj.description or "").lower()
        name_lower = (proj.name or "").lower()
        if any(kw in desc_lower or kw in name_lower for kw in keywords if len(kw) > 2):
            return {
                "project_id": proj.id,
                "name": proj.name,
                "reason": f"该项目专注于 {proj.description}，可能更匹配您的需求"
            }
    return None
