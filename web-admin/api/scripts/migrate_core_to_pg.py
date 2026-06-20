"""迁移 core 数据：JSON/SQLite -> PostgreSQL

覆盖域：
    - users / employees
    - skills / skill_bindings
    - rules
    - memories

用法示例：
    python scripts/migrate_core_to_pg.py \\
        --api-data-dir ~/.ai-native/web-admin-api \\
        --database-url postgresql://admin:changeme@localhost:5432/ai_employee
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType


def _load_store_module(project_root: Path, service_name: str) -> ModuleType:
    store_path = project_root / f"mcp-{service_name}" / "store.py"
    module_name = f"migrate_mcp_{service_name}_store"
    spec = importlib.util.spec_from_file_location(module_name, store_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load store module: {store_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


def _iter_json_files(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(p for p in directory.glob("*.json") if p.is_file())


def main() -> None:
    default_project_root = Path(__file__).resolve()
    for candidate in default_project_root.parents:
        if all((candidate / name).exists() for name in ("mcp-skills", "mcp-rules", "mcp-memory")):
            default_project_root = candidate
            break
    parser = argparse.ArgumentParser(description="迁移 core 数据到 PostgreSQL")
    parser.add_argument("--database-url", required=True, help="PostgreSQL 连接串")
    parser.add_argument(
        "--project-root",
        default=str(default_project_root),
        help="项目根目录（默认自动推断）",
    )
    parser.add_argument(
        "--api-data-dir",
        default="",
        help="Core JSON 数据目录；默认读取 API_DATA_DIR 或 ~/.ai-native/web-admin-api",
    )
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    api_dir = project_root / "web-admin" / "api"
    sys.path.insert(0, str(api_dir))

    from core.config import get_api_data_dir

    if args.api_data_dir.strip():
        data_dir = Path(args.api_data_dir).expanduser()
        if not data_dir.is_absolute():
            data_dir = (api_dir / data_dir).resolve()
        else:
            data_dir = data_dir.resolve()
    else:
        data_dir = get_api_data_dir(create=False)

    from stores.json.employee_store import EmployeeStore
    from stores.postgres.employee_store import EmployeeStorePostgres
    from stores.postgres.mcp_bridge import (
        PgBindingStore,
        PgMemoryStore,
        PgRuleStore,
        PgSkillStore,
    )
    from stores.json.user_store import UserStore
    from stores.postgres.user_store import UserStorePostgres

    skills_mod = _load_store_module(project_root, "skills")
    rules_mod = _load_store_module(project_root, "rules")
    memory_mod = _load_store_module(project_root, "memory")

    skills_dir = project_root / "mcp-skills" / "knowledge"
    rules_dir = project_root / "mcp-rules" / "knowledge"
    memory_db = project_root / "mcp-memory" / "knowledge" / "memories.db"

    user_source = UserStore(data_dir)
    employee_source = EmployeeStore(data_dir)
    skill_source = skills_mod.SkillStore(skills_dir)
    binding_source = skills_mod.BindingStore(skills_dir)
    rule_source = rules_mod.RuleStore(rules_dir)
    memory_source = memory_mod.MemoryStore(memory_db)

    user_target = UserStorePostgres(args.database_url)
    employee_target = EmployeeStorePostgres(args.database_url)
    skill_target = PgSkillStore(
        args.database_url,
        skills_dir,
        skills_mod._serialize_skill,
        skills_mod._deserialize_skill,
    )
    binding_target = PgBindingStore(args.database_url, skills_mod.EmployeeSkillBinding)
    rule_target = PgRuleStore(args.database_url, rules_mod._serialize_rule, rules_mod._deserialize_rule)
    memory_target = PgMemoryStore(
        args.database_url,
        memory_mod.Memory,
        memory_mod.MemoryType,
        memory_mod.MemoryScope,
        memory_mod.Classification,
        memory_mod.serialize_memory,
    )

    migrated: dict[str, int] = {
        "users": 0,
        "employees": 0,
        "skills": 0,
        "skill_bindings": 0,
        "rules": 0,
        "memories": 0,
    }

    for p in _iter_json_files(data_dir / "users"):
        user = user_source.get(p.stem)
        if user is None:
            continue
        user_target.save(user)
        migrated["users"] += 1

    for employee in employee_source.list_all():
        employee_target.save(employee)
        migrated["employees"] += 1

    for skill in skill_source.list_all():
        skill_target.save(skill)
        migrated["skills"] += 1

    for p in _iter_json_files(skills_dir / "bindings"):
        for binding in binding_source.get_bindings(p.stem):
            binding_target.add(binding)
            migrated["skill_bindings"] += 1

    for rule in rule_source.list_all():
        rule_target.save(rule)
        migrated["rules"] += 1

    employee_rows = memory_source._db.execute(
        "SELECT DISTINCT employee_id FROM memories"
    ).fetchall()
    for row in employee_rows:
        employee_id = row["employee_id"] if isinstance(row, dict) else row[0]
        for memory in memory_source.list_by_employee(employee_id):
            memory_target.save(memory)
            migrated["memories"] += 1

    print("Core migration completed.")
    print(f"- api_data_dir: {data_dir}")
    for key, value in migrated.items():
        print(f"- {key}: {value}")


if __name__ == "__main__":
    main()
