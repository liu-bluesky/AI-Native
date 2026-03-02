"""员工管理路由"""

from __future__ import annotations

from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends

from deps import require_auth, employee_store
from employee_store import EmployeeConfig, _now_iso
from stores import rule_store, skill_store
from models.requests import EmployeeCreateReq, EmployeeUpdateReq

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


@router.put("/{employee_id}")
async def update_employee(employee_id: str, req: EmployeeUpdateReq):
    emp = employee_store.get(employee_id)
    if emp is None:
        raise HTTPException(404, f"Employee {employee_id} not found")
    for field_name, val in req.model_dump(exclude_none=True).items():
        setattr(emp, field_name, val)
    emp.updated_at = _now_iso()
    employee_store.save(emp)
    return {"status": "updated", "employee": vars(emp)}


@router.delete("/{employee_id}")
async def delete_employee(employee_id: str):
    if not employee_store.delete(employee_id):
        raise HTTPException(404, f"Employee {employee_id} not found")
    return {"status": "deleted", "employee_id": employee_id}
