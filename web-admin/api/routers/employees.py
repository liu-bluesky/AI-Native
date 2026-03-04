"""员工管理路由"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4
from fastapi import APIRouter, HTTPException, Depends

from deps import require_auth, employee_store
from employee_store import EmployeeConfig, _now_iso
from stores import rule_store, skill_store
from models.requests import EmployeeCreateReq, EmployeeUpdateReq
from config import get_settings

router = APIRouter(prefix="/api/employees", dependencies=[Depends(require_auth)])


_TOOL_SUFFIXES = {".py", ".js"}


def _normalize_domain(value: str) -> str:
    return str(value or "").strip().lower()


def _scan_skill_entries(skill) -> tuple[int, list[str]]:
    package_dir = str(getattr(skill, "package_dir", "") or "").strip()
    if not package_dir:
        return 0, []
    package_path = Path(package_dir)
    if not package_path.is_absolute():
        package_path = Path(__file__).resolve().parents[3] / package_path
    package_path = package_path.resolve()
    if not package_path.exists() or not package_path.is_dir():
        return 0, []

    entries: list[str] = []
    for base_dir in ("tools", "scripts"):
        root = package_path / base_dir
        if not root.exists():
            continue
        for file in sorted(root.rglob("*")):
            if not file.is_file() or file.suffix.lower() not in _TOOL_SUFFIXES:
                continue
            rel = file.relative_to(package_path).as_posix()
            entries.append(rel)
    return len(entries), entries[:8]


@router.get("")
async def list_employees():
    employees = employee_store.list_all()
    return {"employees": [vars(e) for e in employees]}


@router.post("")
async def create_employee(req: EmployeeCreateReq):
    emp = EmployeeConfig(
        id=employee_store.new_id(),
        name=req.name,
        description=req.description,
        skills=req.skills,
        rule_domains=req.rule_domains,
        memory_scope=req.memory_scope,
        memory_retention_days=req.memory_retention_days,
        tone=req.tone,
        verbosity=req.verbosity,
        language=req.language,
        style_hints=req.style_hints,
        auto_evolve=req.auto_evolve,
        evolve_threshold=req.evolve_threshold,
        mcp_enabled=req.mcp_enabled,
        feedback_upgrade_enabled=req.feedback_upgrade_enabled,
    )
    employee_store.save(emp)
    return {"status": "created", "employee": vars(emp)}


@router.get("/{employee_id}/config-test")
async def test_employee_config(employee_id: str):
    emp = employee_store.get(employee_id)
    if emp is None:
        raise HTTPException(404, f"Employee {employee_id} not found")

    skill_checks = []
    blocking_issues = []
    warning_issues = []
    skills_available = 0
    executable_skills = 0

    for skill_id in emp.skills or []:
        skill = skill_store.get(skill_id)
        if skill is None:
            skill_checks.append(
                {
                    "skill_id": skill_id,
                    "name": skill_id,
                    "status": "missing",
                    "entry_count": 0,
                    "sample_entries": [],
                    "message": "技能不存在或已删除",
                }
            )
            blocking_issues.append(f"技能缺失: {skill_id}")
            continue

        skills_available += 1
        entry_count, sample_entries = _scan_skill_entries(skill)
        if entry_count > 0:
            executable_skills += 1
            status = "ok"
            message = "技能脚本可执行"
        else:
            status = "warning"
            message = "未发现 tools/scripts 可执行脚本"
            warning_issues.append(f"技能无可执行脚本: {skill_id}")

        skill_checks.append(
            {
                "skill_id": skill.id,
                "name": skill.name,
                "status": status,
                "entry_count": entry_count,
                "sample_entries": sample_entries,
                "message": message,
            }
        )

    all_rules = rule_store.list_all()
    domain_checks = []
    matched_domains = 0
    total_matched_rules = 0

    for domain in emp.rule_domains or []:
        key = _normalize_domain(domain)
        matched = [r for r in all_rules if _normalize_domain(r.domain) == key]
        total_matched_rules += len(matched)
        if matched:
            matched_domains += 1
            status = "ok"
            message = f"匹配 {len(matched)} 条规则"
        else:
            status = "missing"
            message = "该领域未匹配到规则"
            blocking_issues.append(f"规则领域无匹配: {domain}")

        domain_checks.append(
            {
                "domain": domain,
                "status": status,
                "matched_rule_count": len(matched),
                "sample_titles": [r.title for r in matched[:3]],
                "message": message,
            }
        )

    if not (emp.skills or []):
        warning_issues.append("员工未绑定任何技能")
    if not (emp.rule_domains or []):
        warning_issues.append("员工未绑定任何规则领域")

    is_healthy = len(blocking_issues) == 0
    overall_status = "healthy" if is_healthy else "failed"
    if is_healthy and warning_issues:
        overall_status = "warning"

    return {
        "employee_id": emp.id,
        "employee_name": emp.name,
        "summary": {
            "overall_status": overall_status,
            "is_healthy": is_healthy,
            "skills_total": len(emp.skills or []),
            "skills_available": skills_available,
            "skills_executable": executable_skills,
            "rule_domains_total": len(emp.rule_domains or []),
            "rule_domains_matched": matched_domains,
            "rules_total_matched": total_matched_rules,
        },
        "skills": skill_checks,
        "rule_domains": domain_checks,
        "blocking_issues": blocking_issues,
        "warning_issues": warning_issues,
    }


@router.get("/{employee_id}")
async def get_employee(employee_id: str):
    emp = employee_store.get(employee_id)
    if emp is None:
        raise HTTPException(404, f"Employee {employee_id} not found")
    return {"employee": vars(emp)}


def _apply_employee_update(employee_id: str, req: EmployeeUpdateReq):
    emp = employee_store.get(employee_id)
    if emp is None:
        raise HTTPException(404, f"Employee {employee_id} not found")
    updates = req.model_dump(exclude_none=True)
    if not updates:
        return {"status": "no_change", "employee": vars(emp)}
    for field_name, val in updates.items():
        setattr(emp, field_name, val)
    emp.updated_at = _now_iso()
    employee_store.save(emp)
    return {"status": "updated", "employee": vars(emp)}


@router.put("/{employee_id}")
async def update_employee(employee_id: str, req: EmployeeUpdateReq):
    return _apply_employee_update(employee_id, req)


@router.patch("/{employee_id}")
async def patch_employee(employee_id: str, req: EmployeeUpdateReq):
    return _apply_employee_update(employee_id, req)


@router.post("/{employee_id}")
async def update_employee_compat(employee_id: str, req: EmployeeUpdateReq):
    """兼容部分工具默认使用 POST 调试更新接口。"""
    return _apply_employee_update(employee_id, req)


@router.delete("/{employee_id}")
async def delete_employee(employee_id: str):
    if not employee_store.delete(employee_id):
        raise HTTPException(404, f"Employee {employee_id} not found")
    return {"status": "deleted", "employee_id": employee_id}


@router.post("/{employee_id}/mcp-test")
async def test_employee_mcp(employee_id: str):
    """测试员工 MCP 配置完整性"""
    emp = employee_store.get(employee_id)
    if emp is None:
        raise HTTPException(404, f"Employee {employee_id} not found")

    if not emp.mcp_enabled:
        return {
            "status": "disabled",
            "message": "员工 MCP 未开启",
            "mcp_enabled": False,
        }

    issues = []
    if not (emp.skills or []):
        issues.append("未绑定技能")
    if not (emp.rule_domains or []):
        issues.append("未绑定规则领域")

    skill_count = len(emp.skills or [])
    rule_domain_count = len(emp.rule_domains or [])

    if issues:
        return {
            "status": "warning",
            "message": f"MCP 已开启，但配置不完整: {', '.join(issues)}",
            "mcp_enabled": True,
            "skill_count": skill_count,
            "rule_domain_count": rule_domain_count,
        }

    return {
        "status": "success",
        "message": f"MCP 配置完整：{skill_count} 个技能，{rule_domain_count} 个规则领域",
        "mcp_enabled": True,
        "skill_count": skill_count,
        "rule_domain_count": rule_domain_count,
    }



@router.get("/{employee_id}/prompt-history")
async def get_prompt_history(employee_id: str, limit: int = 20):
    """获取员工提示词生成历史"""
    from prompt_history_store_pg import PromptHistoryStorePostgres

    emp = employee_store.get(employee_id)
    if emp is None:
        raise HTTPException(404, f"Employee {employee_id} not found")

    settings = get_settings()
    if settings.core_store_backend != "postgres":
        return {"history": []}

    store = PromptHistoryStorePostgres(settings.database_url)
    history = store.list_by_employee(employee_id, limit)
    return {"history": history}


@router.delete("/{employee_id}/prompt-history/{record_id}")
async def delete_prompt_history(employee_id: str, record_id: str):
    """删除提示词历史记录"""
    from prompt_history_store_pg import PromptHistoryStorePostgres

    emp = employee_store.get(employee_id)
    if emp is None:
        raise HTTPException(404, f"Employee {employee_id} not found")

    settings = get_settings()
    if settings.core_store_backend != "postgres":
        raise HTTPException(400, "仅 PostgreSQL 模式支持此功能")

    store = PromptHistoryStorePostgres(settings.database_url)
    if not store.delete(record_id):
        raise HTTPException(404, "记录不存在")

    return {"status": "deleted"}


@router.post("/{employee_id}/generate-manual")
async def generate_employee_manual(employee_id: str):
    """生成员工使用手册（面向接入方 AI 平台）"""
    from llm_provider_service import get_llm_provider_service

    emp = employee_store.get(employee_id)
    if emp is None:
        raise HTTPException(404, f"Employee {employee_id} not found")

    llm_service = get_llm_provider_service()
    providers = llm_service.list_providers(enabled_only=True)

    if not providers:
        raise HTTPException(400, "未配置 LLM 提供商")

    default_provider = next((p for p in providers if p.get("is_default")), providers[0])

    # 获取技能详情
    bound_skills = []
    for skill_id in emp.skills or []:
        skill = skill_store.get(skill_id)
        if skill:
            bound_skills.append({"id": skill_id, "name": skill.name, "description": skill.description or ""})

    skills_text = "\n".join(f"- {s['name']}：{s['description']}" for s in bound_skills) if bound_skills else "无"
    domains_text = "\n".join(f"- {d}" for d in (emp.rule_domains or [])) if emp.rule_domains else "无"
    style_hints_text = "\n".join(f"- {h}" for h in (emp.style_hints or [])) if emp.style_hints else "无"

    system_prompt = f"""你是技术文档撰写专家。请为 AI 员工生成一份使用手册，面向接入方 AI 平台。

员工信息：
- ID：{emp.id}
- 名称：{emp.name}
- 描述：{emp.description}
- 语调：{emp.tone}
- 风格：{emp.verbosity}
- 语言：{emp.language}

绑定技能：
{skills_text}

规则领域：
{domains_text}

风格提示：
{style_hints_text}

记忆配置：
- 作用域：{emp.memory_scope}
- 保留期：{emp.memory_retention_days}天

手册结构：
1. 员工简介（说明定位、适用场景、核心能力）

2. MCP 接入配置
   - SSE 方式配置示例（```json 代码块）
   - HTTP 方式配置示例（```json 代码块）

3. 核心功能

   3.1 技能列表
   - 列出每个技能的名称和用途
   - 说明通过 tools/list 可查看完整参数

   3.2 规则领域
   - 列出每个领域及其适用场景
   - 说明规则优先级：本地规则 > 员工规则

   3.3 风格约束
   - 列出风格提示（用于约束回答表达方式）

   3.4 记忆功能
   - 工具：recall_employee_memory(query, project_id)
   - 作用域：{emp.memory_scope}
   - 保留期：{emp.memory_retention_days}天
   - 使用场景和调用示例（```json 代码块）

   3.5 反馈工单
   - 工具：submit_feedback_bug(title, symptom, expected, project_id, ...)
   - 使用场景和调用示例（```json 代码块）

4. 使用建议
   - project_id 的作用
   - 推荐工作流
   - 注意事项

格式要求：
- 标准 Markdown
- 所有 JSON 必须用 ```json 代码块
- 每个章节之间有空行"""

    user_prompt = f"请为员工「{emp.name}」生成使用手册。"

    try:
        result = await llm_service.chat_completion(
            provider_id=default_provider["id"],
            model_name=default_provider.get("default_model") or "gpt-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=2500,
            timeout=60,
        )

        manual = result.get("content", "").strip()

        return {
            "status": "success",
            "manual": manual,
            "provider": default_provider["name"],
            "model": default_provider.get("default_model") or "gpt-4",
        }
    except Exception as e:
        raise HTTPException(500, f"生成使用手册失败: {str(e)}")


@router.get("/{employee_id}/manual-template")
async def get_manual_template(employee_id: str):
    """获取手册生成提示词模板（供用户复制到其他 AI 使用）"""
    emp = employee_store.get(employee_id)
    if emp is None:
        raise HTTPException(404, f"Employee {employee_id} not found")

    # 获取技能详情
    bound_skills = []
    for skill_id in emp.skills or []:
        skill = skill_store.get(skill_id)
        if skill:
            bound_skills.append({"id": skill_id, "name": skill.name, "description": skill.description or ""})

    skills_text = "\n".join(f"- {s['name']}：{s['description']}" for s in bound_skills) if bound_skills else "无"
    domains_text = "\n".join(f"- {d}" for d in (emp.rule_domains or [])) if emp.rule_domains else "无"
    style_hints_text = "\n".join(f"- {h}" for h in (emp.style_hints or [])) if emp.style_hints else "无"

    template = f"""请为以下 AI 员工生成一份使用手册，面向接入方 AI 平台。

员工信息：
- ID：{emp.id}
- 名称：{emp.name}
- 描述：{emp.description}
- 语调：{emp.tone}
- 风格：{emp.verbosity}
- 语言：{emp.language}

绑定技能：
{skills_text}

规则领域：
{domains_text}

风格提示：
{style_hints_text}

记忆配置：
- 作用域：{emp.memory_scope}
- 保留期：{emp.memory_retention_days}天

手册要求：
1. 员工简介（定位、适用场景）
2. MCP 接入配置（SSE 和 HTTP 两种方式，使用 ```json 代码块）
3. 核心功能：
   - 技能列表（列出每个技能及用途）
   - 规则领域（列出每个领域及适用场景）
   - 风格约束（列出风格提示）
   - 记忆功能：recall_employee_memory(query, project_id)，作用域 {emp.memory_scope}，保留 {emp.memory_retention_days}天
   - 反馈工单：submit_feedback_bug(title, symptom, expected, project_id, ...)
4. 使用建议（project_id 作用、推荐工作流、注意事项）

格式：标准 Markdown，所有 JSON 用 ```json 代码块"""

    return {
        "status": "success",
        "template": template,
        "employee_id": emp.id,
        "employee_name": emp.name,
    }
