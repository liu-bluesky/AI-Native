"""员工管理路由"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4
from fastapi import APIRouter, HTTPException, Depends

from deps import require_auth, employee_store, system_config_store
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


def _assert_employee_manual_generation_enabled() -> None:
    cfg = system_config_store.get_global()
    if not bool(getattr(cfg, "enable_employee_manual_generation", False)):
        raise HTTPException(403, "Employee manual generation is disabled by system config")


@router.post("/{employee_id}/generate-manual")
async def generate_employee_manual(employee_id: str):
    """生成员工使用手册（面向接入方 AI 平台）"""
    from llm_provider_service import get_llm_provider_service

    _assert_employee_manual_generation_enabled()

    llm_service = get_llm_provider_service()
    providers = llm_service.list_providers(enabled_only=True)

    if not providers:
        raise HTTPException(400, "未配置 LLM 提供商")

    default_provider = next((p for p in providers if p.get("is_default")), providers[0])
    template_payload = await get_manual_template(employee_id)
    template = str(template_payload.get("template") or "").strip()
    if not template:
        raise HTTPException(500, "手册模板为空，无法生成使用手册")

    system_prompt = (
        "你是技术文档撰写专家。请严格根据用户提供的手册模板要求生成最终使用手册，"
        "输出标准 Markdown，不要解释过程。"
    )

    try:
        result = await llm_service.chat_completion(
            provider_id=default_provider["id"],
            model_name=default_provider.get("default_model") or "gpt-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": template},
            ],
            temperature=0.2,
            max_tokens=2500,
            timeout=60,
        )

        manual = result.get("content", "").strip()

        return {
            "status": "success",
            "manual": manual,
            "template": template,
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

    template = f"""请根据以下信息，为"{emp.name}"AI 员工生成一份完整的使用手册。

## 员工基本信息

- **员工 ID**：`{emp.id}`
- **员工名称**：{emp.name}
- **员工描述**：{emp.description or "AI 开发助手"}
- **语调**：{emp.tone}
- **风格**：{emp.verbosity}
- **语言**：{emp.language}

## 员工能力

### 绑定技能
{skills_text}

### 规则领域
{domains_text}

### 风格提示
{style_hints_text}

### 记忆配置
- **作用域**：{emp.memory_scope}
- **保留期**：{emp.memory_retention_days}天

---

## 手册生成要求

**重要：自动记忆规则**

在生成的使用手册中，必须在开头添加以下强制规则：

> **每次对话流程（强制执行）：**
> 1. 收到用户提问后，第一步必须先记录“用户问题”（至少包含：问题原文、问题摘要、检索关键词）
> 2. 完成问题记录后，必须先自动识别任务类型，并判断是否属于当前员工职责范围
> 3. 若属于当前员工职责范围：调用 `recall_employee_memory` 检索相关记忆（`query` 必须来自问题摘要/关键词）
> 4. 若不属于当前员工职责范围：输出“转交建议”，并要求转到项目层按员工分配流程处理
> 5. 解决问题之前的关键信息会自动保存到记忆系统
> 6. 问题解决后，系统会自动记录本次对话的要点
> 
> **问题记录格式（必须写入手册并要求严格执行）：**
> ```text
> 【问题记录】
> - 问题原文：<用户原始提问>
> - 问题摘要：<一句话归纳>
> - 检索关键词：<3-5个关键词>
> ```
> 
> **任务类型与归属分配规则（必须写入手册并严格执行）：**
> 1. 根据问题内容识别任务类型：当前员工主责类型 / 非主责类型
> 2. 当前员工主责类型：继续执行员工内流程（记忆检索、规则检索、技能调用）
> 3. 非主责类型：必须给出“转交建议”，建议转到项目层由 AI 自动分配合适员工
> 
> **类型判断输出格式（必须写入手册）：**
> ```text
> 【类型判断】
> - 任务类型：<类型名称>
> - 处理归属：<当前员工处理 | 转交项目层>
> - 判断依据：<命中的技能/规则领域或不匹配原因>
> ```
> 
> **记忆检索调用示例（必须写入手册）：**
> ```json
> recall_employee_memory({{
>   "query": "<问题摘要或关键词组合>"
> }})
> ```
> 
> **转交建议格式（必须写入手册）：**
> ```text
> 【转交建议】
> - 建议动作：转项目层处理
> - 原因：当前员工能力与任务类型不匹配
> - 下一步：在项目层执行“任务类型识别 -> 自动分配员工 -> 写入并检索记忆”
> ```
> 
> **记忆自动保存的内容包括：**
> - 用户提出的问题
> - 使用的解决方案
> - 调用的工具和参数
> - 遇到的问题和解决方法
> - 重要的技术决策
> 
> **注意：**
> - 记忆系统会自动工作，无需手动调用保存
> - 如果遇到重要问题或发现 Bug，可手动提交反馈工单（`submit_feedback_bug`）用于规则进化

请按以下结构生成完整的使用手册：

### 第一部分：员工总览

#### 1. 员工简介
- **定位**：{emp.name}是什么角色？负责什么工作？
- **适用场景**：什么时候应该使用这个员工？
- **能力边界**：员工能做什么，不能做什么？

#### 2. 核心工具说明

逐个说明以下工具的用途、参数、返回值和使用场景：

- **`recall_employee_memory`**：检索员工记忆
- **`query_employee_rules`**：查询员工规则
- **`list_employee_tools`**：列出员工可用技能工具
- **`invoke_employee_skill_tool`**：调用员工技能
- **`submit_feedback_bug`**：提交反馈问题

---

### 第二部分：员工能力清单

详细说明：
- 职责定位
- 核心技能（每个技能的用途和触发条件）
- 规则领域（每个领域的适用场景）
- 风格特点（如何影响回答方式）
- 记忆策略（作用域和保留期）

---

### 第三部分：推荐工作流

#### 标准开发流程

```
1. 问题登记（记录问题原文/摘要/关键词）
2. 类型识别与归属判断（当前员工处理 / 转交项目层）
3. 记忆检索（仅当前员工处理时）→ recall_employee_memory
4. 规则检索 → query_employee_rules
5. 技能调用 → invoke_employee_skill_tool
6. 反馈闭环 → submit_feedback_bug
```

#### 典型场景示例

提供 2-3 个具体的使用场景，包含完整的工具调用示例；每个场景都必须先给出“问题记录”和“类型判断”，并体现“当前员工处理”或“转交项目层”的分配结果。

---

### 第四部分：常见问题与故障排查

#### Q1：记忆检索无结果
- 排查步骤和解决方案

#### Q2：规则查询返回多条结果
- 如何选择合适的规则

#### Q3：技能调用参数错误
- 常见错误和修正方法

#### Q4：反馈提交失败
- 检查必填参数

---

### 第五部分：最佳实践

#### 1. 参数规范
- 调用记忆时的参数要求
- 调用技能时的参数要求
- 提交反馈时的参数要求

#### 2. 记忆管理
- 检索策略
- 记忆自动保存机制

#### 3. 规则遵循
- 开发前检索规则
- 遵循最佳实践

#### 4. 技能使用
- 首次使用注意事项
- 失败处理建议

#### 5. 类型分配
- 先识别任务类型，再判断是否属于当前员工主责范围
- 非主责类型必须给出转交建议，不得强行在当前员工内处理

---

## 生成要求

1. **语言**：全部使用中文
2. **格式**：标准 Markdown
3. **完整性**：必须包含以上所有章节
4. **实用性**：提供具体的使用场景和示例
5. **清晰度**：每个工具的用途、参数、返回值都要说明清楚

请开始生成完整的使用手册。"""


    return {
        "status": "success",
        "template": template,
        "employee_id": emp.id,
        "employee_name": emp.name,
    }
