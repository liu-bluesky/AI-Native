"""员工管理路由"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends

from deps import require_auth, employee_store
from employee_store import EmployeeConfig, _now_iso
from models.requests import EmployeeCreateReq, EmployeeUpdateReq

router = APIRouter(prefix="/api/employees", dependencies=[Depends(require_auth)])


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
    )
    employee_store.save(emp)
    return {"status": "created", "employee": vars(emp)}


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
