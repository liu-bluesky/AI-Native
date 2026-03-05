"""项目管理路由"""

from __future__ import annotations

from dataclasses import asdict, replace

from fastapi import APIRouter, Depends, HTTPException

from deps import employee_store, project_store, require_auth, system_config_store
from feedback_service import get_feedback_service
from models.requests import ProjectCreateReq, ProjectMemberAddReq, ProjectUpdateReq
from project_store import ProjectConfig, ProjectMember, _now_iso
from stores import skill_store

router = APIRouter(prefix="/api/projects", dependencies=[Depends(require_auth)])


def _serialize_project(project: ProjectConfig) -> dict:
    data = asdict(project)
    data["member_count"] = len(project_store.list_members(project.id))
    return data


def _sync_feedback_project_flag(project_id: str, enabled: bool) -> None:
    try:
        get_feedback_service().update_project_config(project_id, enabled=enabled)
    except Exception:
        # 反馈升级能力在非 PG/禁用场景可能不可用；项目主流程不阻断。
        return


def _project_member_details(project_id: str) -> list[dict]:
    items: list[dict] = []
    for member in project_store.list_members(project_id):
        employee = employee_store.get(member.employee_id)
        if employee is None:
            continue
        skill_items = []
        for skill_id in employee.skills or []:
            skill = skill_store.get(skill_id)
            skill_items.append(
                {
                    "id": skill_id,
                    "name": getattr(skill, "name", "") or skill_id,
                    "description": getattr(skill, "description", "") if skill else "",
                }
            )
        items.append(
            {
                "member": member,
                "employee": employee,
                "skills": skill_items,
                "rule_domains": list(employee.rule_domains or []),
            }
        )
    return items


def _assert_project_manual_generation_enabled() -> None:
    cfg = system_config_store.get_global()
    if not bool(getattr(cfg, "enable_project_manual_generation", False)):
        raise HTTPException(403, "Project manual generation is disabled by system config")


@router.get("")
async def list_projects():
    projects = project_store.list_all()
    return {"projects": [_serialize_project(item) for item in projects]}


@router.post("")
async def create_project(req: ProjectCreateReq):
    project = ProjectConfig(
        id=project_store.new_id(),
        name=str(req.name or "").strip(),
        description=req.description,
        mcp_enabled=req.mcp_enabled,
        feedback_upgrade_enabled=req.feedback_upgrade_enabled,
    )
    if not project.name:
        raise HTTPException(400, "name is required")
    project_store.save(project)
    _sync_feedback_project_flag(project.id, project.feedback_upgrade_enabled)
    return {"status": "created", "project": _serialize_project(project)}


@router.get("/{project_id}")
async def get_project(project_id: str):
    project = project_store.get(project_id)
    if project is None:
        raise HTTPException(404, f"Project {project_id} not found")
    return {"project": _serialize_project(project)}


def _apply_project_update(project_id: str, req: ProjectUpdateReq) -> dict:
    project = project_store.get(project_id)
    if project is None:
        raise HTTPException(404, f"Project {project_id} not found")
    updates = req.model_dump(exclude_none=True)
    if not updates:
        return {"status": "no_change", "project": _serialize_project(project)}
    if "name" in updates:
        updates["name"] = str(updates["name"] or "").strip()
        if not updates["name"]:
            raise HTTPException(400, "name cannot be empty")
    updates["updated_at"] = _now_iso()
    updated = replace(project, **updates)
    project_store.save(updated)
    if "feedback_upgrade_enabled" in updates:
        _sync_feedback_project_flag(updated.id, bool(updated.feedback_upgrade_enabled))
    return {"status": "updated", "project": _serialize_project(updated)}


@router.put("/{project_id}")
async def update_project(project_id: str, req: ProjectUpdateReq):
    return _apply_project_update(project_id, req)


@router.patch("/{project_id}")
async def patch_project(project_id: str, req: ProjectUpdateReq):
    return _apply_project_update(project_id, req)


@router.delete("/{project_id}")
async def delete_project(project_id: str):
    if not project_store.delete(project_id):
        raise HTTPException(404, f"Project {project_id} not found")
    return {"status": "deleted", "project_id": project_id}


@router.get("/{project_id}/members")
async def list_project_members(project_id: str):
    project = project_store.get(project_id)
    if project is None:
        raise HTTPException(404, f"Project {project_id} not found")
    members = []
    for member in project_store.list_members(project_id):
        employee = employee_store.get(member.employee_id)
        members.append(
            {
                **asdict(member),
                "employee_exists": employee is not None,
                "employee_name": getattr(employee, "name", ""),
                "employee_mcp_enabled": bool(getattr(employee, "mcp_enabled", False)) if employee else False,
            }
        )
    return {"members": members}


@router.post("/{project_id}/members")
async def add_project_member(project_id: str, req: ProjectMemberAddReq):
    project = project_store.get(project_id)
    if project is None:
        raise HTTPException(404, f"Project {project_id} not found")

    employee_id = str(req.employee_id or "").strip()
    if not employee_id:
        raise HTTPException(400, "employee_id is required")
    employee = employee_store.get(employee_id)
    if employee is None:
        raise HTTPException(404, f"Employee {employee_id} not found")

    existing = project_store.get_member(project_id, employee_id)
    if existing is not None:
        return {
            "status": "exists",
            "message": f"Employee {employee_id} already exists in project {project_id}",
            "member": asdict(existing),
        }
    member = ProjectMember(
        project_id=project_id,
        employee_id=employee_id,
        role=str(req.role or "member").strip() or "member",
        enabled=bool(req.enabled),
        joined_at=_now_iso(),
    )
    project_store.upsert_member(member)
    return {"status": "created", "member": asdict(member)}


@router.delete("/{project_id}/members/{employee_id}")
async def remove_project_member(project_id: str, employee_id: str):
    project = project_store.get(project_id)
    if project is None:
        raise HTTPException(404, f"Project {project_id} not found")
    if not project_store.remove_member(project_id, employee_id):
        raise HTTPException(404, f"Employee {employee_id} is not a member of project {project_id}")
    return {"status": "deleted", "project_id": project_id, "employee_id": employee_id}


@router.post("/{project_id}/generate-manual")
async def generate_project_manual(project_id: str):
    """生成项目使用手册（面向接入方 AI 平台）"""
    from llm_provider_service import get_llm_provider_service

    _assert_project_manual_generation_enabled()

    llm_service = get_llm_provider_service()
    providers = llm_service.list_providers(enabled_only=True)
    if not providers:
        raise HTTPException(400, "未配置 LLM 提供商")
    default_provider = next((p for p in providers if p.get("is_default")), providers[0])

    template_payload = await get_project_manual_template(project_id)
    template = str(template_payload.get("template") or "").strip()
    if not template:
        raise HTTPException(500, "项目手册模板为空，无法生成使用手册")

    project_name = str(template_payload.get("project_name") or "")
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
            max_tokens=2800,
            timeout=60,
        )
        manual = str(result.get("content") or "").strip()
        return {
            "status": "success",
            "manual": manual,
            "template": template,
            "provider": default_provider["name"],
            "model": default_provider.get("default_model") or "gpt-4",
            "project_id": project_id,
            "project_name": project_name,
        }
    except Exception as exc:
        raise HTTPException(500, f"生成项目使用手册失败: {str(exc)}") from exc


@router.get("/{project_id}/manual-template")
async def get_project_manual_template(project_id: str):
    """获取项目手册提示词模板（供用户复制到其他 AI 使用）"""
    project = project_store.get(project_id)
    if project is None:
        raise HTTPException(404, f"Project {project_id} not found")

    member_items = _project_member_details(project_id)
    member_lines = []
    all_domains: set[str] = set()
    unique_skills: dict[str, dict] = {}
    for item in member_items:
        employee = item["employee"]
        member = item["member"]
        domains = item["rule_domains"]
        skills = item["skills"]
        for domain in domains:
            all_domains.add(str(domain))
        for skill in skills:
            unique_skills[str(skill["id"])] = skill
        member_lines.append(
            f"- {employee.name} ({employee.id}) role={member.role} "
            f"skills={len(skills)} domains={len(domains)}"
        )

    members_text = "\n".join(member_lines) if member_lines else "无"
    skills_text = (
        "\n".join(f"- {s['name']}:{s.get('description', '')}" for s in unique_skills.values())
        if unique_skills
        else "无"
    )
    domains_text = "\n".join(f"- {d}" for d in sorted(all_domains)) if all_domains else "无"
    employee_template_lines: list[str] = []
    for item in member_items:
        employee = item["employee"]
        member = item["member"]
        skills = item["skills"]
        domains = item["rule_domains"]
        style_hints = list(getattr(employee, "style_hints", []) or [])
        employee_skills_text = (
            "\n".join(f"  - {s['name']}:{s.get('description', '')}" for s in skills)
            if skills
            else "  - 无"
        )
        employee_domains_text = (
            "\n".join(f"  - {d}" for d in domains)
            if domains
            else "  - 无"
        )
        style_text = (
            "\n".join(f"  - {text}" for text in style_hints)
            if style_hints
            else "  - 无"
        )
        employee_template_lines.append(
            f"""### {employee.name}（{employee.id}）
- 角色:{member.role}
- 语调:{getattr(employee, "tone", "-")} / 风格:{getattr(employee, "verbosity", "-")} / 语言:{getattr(employee, "language", "-")}
- 记忆:scope={getattr(employee, "memory_scope", "-")}，保留{getattr(employee, "memory_retention_days", "-")}天

技能:
{employee_skills_text}

规则领域:
{employee_domains_text}

风格提示:
{style_text}
"""
        )
    employee_templates_text = "\n".join(employee_template_lines) if employee_template_lines else "无成员"

    template = f"""请根据以下信息，为"{project.name}"AI 项目模块生成一份完整的使用手册。

## 项目基本信息

- **项目 ID**：`{project.id}`
- **项目名称**：{project.name}
- **项目定位**：{project.description or "AI 开发团队"}
- **反馈升级**：{"已启用" if project.feedback_upgrade_enabled else "未启用"}

## 项目成员

{employee_templates_text}

---

## 手册生成要求

**重要：自动记忆规则**

在生成的使用手册中，必须在开头添加以下强制规则：

> **每次对话流程（强制执行）：**
> 1. 收到用户提问后，先检索相关记忆（`recall_project_memory`）
> 2. 解决问题过程中的关键信息会自动保存到记忆系统
> 3. 问题解决后，系统会自动记录本次对话的要点
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
> - 如果遇到重要问题或发现 Bug，可手动提交反馈工单（`submit_project_feedback_bug`）用于规则进化

请按以下结构生成完整的使用手册：

### 第一部分：项目总览

#### 1. 项目简介
- **定位**：{project.name}是什么项目？解决什么问题？
- **适用场景**：什么时候应该使用这个项目？
- **能力边界**：项目能做什么，不能做什么？

#### 2. 核心工具说明

逐个说明以下工具的用途、参数、返回值和使用场景：

- **`list_project_members`**：列出项目所有成员
- **`get_project_profile`**：获取项目配置信息
- **`get_project_runtime_context`**：获取项目运行时上下文
- **`recall_project_memory`**：检索项目记忆
- **`query_project_rules`**：查询项目规则
- **`list_project_proxy_tools`**：列出项目可用技能工具
- **`invoke_project_skill_tool`**：调用项目技能
- **`submit_project_feedback_bug`**：提交反馈问题

---

### 第二部分：项目成员能力清单

为每个成员详细说明：
- 职责定位
- 核心技能
- 规则领域
- 风格特点（如有）

---

### 第三部分：推荐工作流

#### 标准开发流程

```
1. 获取项目上下文 → get_project_runtime_context
2. 记忆检索 → recall_project_memory
3. 规则检索 → query_project_rules
4. 技能调用 → invoke_project_skill_tool
5. 反馈闭环 → submit_project_feedback_bug
```

#### 典型场景示例

**场景 1：新增数据库表**
1. 获取上下文
2. 检索记忆（"数据库表设计"）
3. 检索规则（"数据库设计"）
4. 查看现有表结构（db-query）
5. 提交反馈

**场景 2：开发新的 Vue 组件**
1. 获取上下文
2. 检索记忆（"Element Plus 表格组件"）
3. 检索规则（"UI 设计"）
4. 查询数据结构（db-query）
5. 提交反馈

**场景 3：跨端协作（前后端联调）**
1. 获取项目成员
2. 检索后端记忆（"API 接口设计"）
3. 检索前端记忆（"API 调用"）
4. 查看数据库结构（db-query）
5. 提交联调反馈

---

### 第四部分：常见问题与故障排查

#### Q1：数据库查询失败
- 首次使用需提供数据库配置
- 检查连接信息是否正确
- 仅支持 SELECT 语句
- 单次查询最多返回 1000 行

#### Q2：记忆检索无结果
- 尝试更换关键词
- 检查 `project_name` 参数（必须是"{project.name}"）
- 确认记忆保留期（90 天）内是否有记录
- 尝试不指定 `employee_id` 进行全局检索

#### Q3：规则查询返回多条结果
- 优先使用最近更新的规则
- 根据 `domain` 字段筛选
- 可以同时参考多条规则

#### Q4：技能调用参数错误
- 查看错误信息中的参数提示
- 确认 `employee_id` 是否正确
- 确认技能名称是否正确
- 确认 `args` 参数格式正确（JSON 对象）

#### Q5：反馈提交失败
- 检查必填参数是否完整
- 确认项目反馈升级功能已启用
- 检查 `employee_id` 是否属于该项目成员

---

### 第五部分：最佳实践

#### 1. 参数规范
- 调用记忆时，必须传 `project_name="{project.name}"`
- 调用技能时，必须传 `employee_id`
- 提交反馈时，必须传 `employee_id`、`title`、`symptom`、`expected`

#### 2. 员工选择
- 根据任务类型选择合适的员工
- 跨端任务：分别调用相关员工的能力

#### 3. 记忆管理
- 定期检索记忆，避免重复踩坑
- 及时提交反馈，积累项目经验
- 使用精确的关键词提高检索准确率

#### 4. 规则遵循
- 开发前先检索相关规则
- 遵循规则中的最佳实践
- 发现规则不适用时及时反馈

#### 5. 技能使用
- 首次使用技能时注意配置要求
- 数据库查询注意安全限制
- 技能调用失败时查看详细错误信息

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
        "project_id": project.id,
        "project_name": project.name,
    }
