#!/usr/bin/env python3
"""Sync local employee/rule/skill visibility settings to the remote PostgreSQL database."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import remote_docker_deploy as deploylib


@dataclass(frozen=True)
class VisibilityRecord:
    id: str
    created_by: str
    share_scope: str
    shared_with_usernames: list[str]


def tool_root() -> Path:
    return Path(__file__).resolve().parent


def project_root() -> Path:
    return tool_root().parent


def load_module(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module from {file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync local resource visibility data to remote PostgreSQL.")
    parser.add_argument("--profile", default="default")
    parser.add_argument("--host", default="")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--user", default="")
    parser.add_argument("--remote-dir", default="")
    parser.add_argument("--compose-file", default="")
    parser.add_argument("--env-file", default="")
    parser.add_argument("--artifact-dir", default="")
    parser.add_argument("--backup-prefix", default="visibility-sync")
    parser.add_argument("--healthcheck-url", default="")
    parser.add_argument("--ssh-key", default="")
    parser.add_argument("--password", "--remote-deploy-password", dest="password", default="")
    parser.add_argument("--password-env", default="")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--employee-id", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--save-password", action="store_true")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--source", choices=["auto", "docker-postgres", "json"], default="auto")
    parser.add_argument("--local-postgres-container", default="ai-employee-postgres")
    parser.add_argument("--local-db-user", default="admin")
    parser.add_argument("--local-db-name", default="ai_employee")
    parser.add_argument("--api-data-dir", default="")
    parser.add_argument("--all-users", action="store_true")
    return parser.parse_args()


def normalize_shared_usernames(value: Any) -> list[str]:
    raw = value if isinstance(value, (list, tuple)) else []
    results: list[str] = []
    seen: set[str] = set()
    for item in raw:
        username = str(item or "").strip()
        if not username or username in seen:
            continue
        seen.add(username)
        results.append(username)
    return results


def normalize_share_scope(value: Any, *, force_all_users: bool) -> str:
    if force_all_users:
        return "all_users"
    scope = str(value or "").strip().lower()
    if scope in {"private", "selected_users", "all_users"}:
        return scope
    return "private"


def normalize_record(payload: dict[str, Any], *, force_all_users: bool) -> VisibilityRecord:
    return VisibilityRecord(
        id=str(payload.get("id") or "").strip(),
        created_by=str(payload.get("created_by") or "").strip(),
        share_scope=normalize_share_scope(payload.get("share_scope"), force_all_users=force_all_users),
        shared_with_usernames=[] if force_all_users else normalize_shared_usernames(payload.get("shared_with_usernames")),
    )


def run_local_command(command: list[str], *, timeout: int) -> dict[str, Any]:
    return deploylib.run_local_command(command, timeout=timeout)


def read_local_postgres_records(
    *,
    table_name: str,
    container_name: str,
    db_user: str,
    db_name: str,
    timeout: int,
) -> list[VisibilityRecord]:
    command = [
        "docker",
        "exec",
        container_name,
        "psql",
        "-U",
        db_user,
        "-d",
        db_name,
        "-At",
        "-F",
        "\t",
        "-c",
        f"SELECT id, payload::text FROM {table_name} ORDER BY id",
    ]
    result = run_local_command(command, timeout=timeout)
    if result["status"] != "ok":
        raise RuntimeError(result.get("stderr") or result.get("stdout") or f"failed to read {table_name}")
    records: list[VisibilityRecord] = []
    for line in str(result.get("stdout") or "").splitlines():
        if not line.strip():
            continue
        row_id, payload_text = line.split("\t", 1)
        payload = json.loads(payload_text)
        payload["id"] = payload.get("id") or row_id
        records.append(normalize_record(payload, force_all_users=False))
    return records


def resolve_api_data_dir(api_dir: Path, explicit: str) -> Path:
    if explicit.strip():
        path = Path(explicit).expanduser()
        return path.resolve() if path.is_absolute() else (api_dir / path).resolve()
    config_mod = load_module("sync_visibility_config", api_dir / "core" / "config.py")
    return config_mod.get_api_data_dir(create=False)


def read_local_json_records(*, api_data_dir: Path, force_all_users: bool) -> dict[str, list[VisibilityRecord]]:
    rule_mod = load_module("sync_visibility_rule_store", project_root() / "mcp-rules" / "store.py")
    skill_mod = load_module("sync_visibility_skill_store", project_root() / "mcp-skills" / "store.py")

    rule_store = rule_mod.RuleStore(project_root() / "mcp-rules" / "knowledge")
    skill_store = skill_mod.SkillStore(project_root() / "mcp-skills" / "knowledge")
    employees_dir = api_data_dir / "employees"
    employees: list[VisibilityRecord] = []
    if employees_dir.exists():
        for path in sorted(employees_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["id"] = payload.get("id") or path.stem
            employees.append(normalize_record(payload, force_all_users=force_all_users))

    return {
        "employees": employees,
        "rules": [normalize_record(rule_mod._serialize_rule(item), force_all_users=force_all_users) for item in rule_store.list_all()],
        "skills": [normalize_record(skill_mod._serialize_skill(item), force_all_users=force_all_users) for item in skill_store.list_all()],
    }


def read_local_source(args: argparse.Namespace, config: dict[str, Any]) -> tuple[str, dict[str, list[VisibilityRecord]]]:
    timeout = int(config["timeout"])
    if args.source in {"auto", "docker-postgres"}:
        try:
            records = {
                "employees": read_local_postgres_records(
                    table_name="employees",
                    container_name=args.local_postgres_container,
                    db_user=args.local_db_user,
                    db_name=args.local_db_name,
                    timeout=timeout,
                ),
                "rules": read_local_postgres_records(
                    table_name="rules",
                    container_name=args.local_postgres_container,
                    db_user=args.local_db_user,
                    db_name=args.local_db_name,
                    timeout=timeout,
                ),
                "skills": read_local_postgres_records(
                    table_name="skills",
                    container_name=args.local_postgres_container,
                    db_user=args.local_db_user,
                    db_name=args.local_db_name,
                    timeout=timeout,
                ),
            }
            if args.all_users:
                records = {
                    resource: [
                        VisibilityRecord(
                            id=item.id,
                            created_by=item.created_by,
                            share_scope="all_users",
                            shared_with_usernames=[],
                        )
                        for item in items
                    ]
                    for resource, items in records.items()
                }
            return "docker-postgres", records
        except Exception:
            if args.source == "docker-postgres":
                raise
    api_dir = project_root() / "web-admin" / "api"
    api_data_dir = resolve_api_data_dir(api_dir, args.api_data_dir)
    return "json", read_local_json_records(api_data_dir=api_data_dir, force_all_users=args.all_users)


def sql_text(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def sql_json(value: Any) -> str:
    return "'" + json.dumps(value, ensure_ascii=False).replace("'", "''") + "'::jsonb"


def build_update_sql(table_name: str, records: list[VisibilityRecord]) -> list[str]:
    statements: list[str] = []
    for item in records:
        if not item.id:
            continue
        statements.append(
            "UPDATE {table} "
            "SET payload = jsonb_set("
            "jsonb_set("
            "jsonb_set(payload, '{{created_by}}', to_jsonb({created_by}::text), true), "
            "'{{share_scope}}', to_jsonb({share_scope}::text), true"
            "), "
            "'{{shared_with_usernames}}', {shared_with} , true"
            "), "
            "updated_at = NOW() "
            "WHERE id = {record_id};".format(
                table=table_name,
                created_by=sql_text(item.created_by),
                share_scope=sql_text(item.share_scope),
                shared_with=sql_json(item.shared_with_usernames),
                record_id=sql_text(item.id),
            )
        )
    return statements


def build_sql_script(records: dict[str, list[VisibilityRecord]]) -> str:
    script = ["BEGIN;"]
    script.extend(build_update_sql("employees", records["employees"]))
    script.extend(build_update_sql("rules", records["rules"]))
    script.extend(build_update_sql("skills", records["skills"]))
    script.extend(
        [
            "COMMIT;",
            "SELECT 'employees' AS resource, count(*) AS total, count(*) FILTER (WHERE COALESCE(payload->>'share_scope', 'private') = 'all_users') AS all_users FROM employees",
            "UNION ALL",
            "SELECT 'rules', count(*), count(*) FILTER (WHERE COALESCE(payload->>'share_scope', 'private') = 'all_users') FROM rules",
            "UNION ALL",
            "SELECT 'skills', count(*), count(*) FILTER (WHERE COALESCE(payload->>'share_scope', 'private') = 'all_users') FROM skills;",
        ]
    )
    return "\n".join(script) + "\n"


def build_remote_sql_path(config: dict[str, Any]) -> str:
    remote_root = str(Path(str(config["remote_dir"])).parent)
    return f"{remote_root.rstrip('/')}/remote-resource-visibility-sync.sql"


def build_remote_apply_script(config: dict[str, Any], remote_sql_path: str) -> str:
    remote_dir = deploylib.quote(str(config["remote_dir"]))
    backup_prefix = deploylib.quote(str(config["backup_prefix"]))
    remote_sql = deploylib.quote(remote_sql_path)
    return "; ".join(
        [
            "set -euo pipefail",
            f"cd {remote_dir}",
            "chmod +x ./deploy.sh || true",
            "ts=$(date +%Y%m%d-%H%M%S)",
            f"backup_prefix={backup_prefix}",
            'backup_dir="backup/${backup_prefix}-$ts"',
            'backup_root="$PWD/$backup_dir"',
            'mkdir -p "$backup_root"',
            './deploy.sh backup-db "$backup_root/ai_employee.sql"',
            'echo "BACKUP_DIR=$backup_dir"',
            f'docker exec ai-employee-postgres psql -U admin -d ai_employee -f {remote_sql}',
            f'rm -f {remote_sql}',
        ]
    )


def upload_remote_sql(
    config: dict[str, Any],
    *,
    password: str,
    sql_file: Path,
    remote_sql_path: str,
    dry_run: bool,
) -> dict[str, Any]:
    command = deploylib.build_scp_command(config, sql_file, remote_sql_path)
    wrapped, auth_mode = deploylib.wrap_transport_command(command, password, int(config["timeout"]), dry_run=dry_run)
    if dry_run:
        return {"status": "dry_run", "command": wrapped, "auth_mode": auth_mode}
    result = run_local_command(wrapped, timeout=int(config["timeout"]))
    result["auth_mode"] = auth_mode
    return result


def apply_remote_sql(
    config: dict[str, Any],
    *,
    password: str,
    remote_sql_path: str,
    dry_run: bool,
) -> dict[str, Any]:
    remote_script = build_remote_apply_script(config, remote_sql_path)
    ssh_command = [*deploylib.build_ssh_command(config), remote_script]
    command, auth_mode = deploylib.wrap_transport_command(ssh_command, password, int(config["timeout"]), dry_run=dry_run)
    if dry_run:
        return {
            "status": "dry_run",
            "command": command,
            "ssh_command": ssh_command,
            "remote_script": remote_script,
            "auth_mode": auth_mode,
        }
    result = run_local_command(command, timeout=int(config["timeout"]))
    result["auth_mode"] = auth_mode
    result["ssh_command"] = ssh_command
    result["remote_script"] = remote_script
    return result


def summarize_records(records: dict[str, list[VisibilityRecord]]) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = {}
    for resource, items in records.items():
        summary[resource] = {
            "total": len(items),
            "all_users": sum(1 for item in items if item.share_scope == "all_users"),
            "private": sum(1 for item in items if item.share_scope == "private"),
            "selected_users": sum(1 for item in items if item.share_scope == "selected_users"),
        }
    return summary


def main() -> int:
    args = parse_args()
    cfg_path = deploylib.config_path(
        profile=args.profile.strip(),
        api_key=args.api_key.strip(),
        employee_id=args.employee_id.strip(),
    )
    if args.reset:
        if cfg_path.exists():
            cfg_path.unlink()
        print(json.dumps({"status": "reset", "config_path": str(cfg_path)}, ensure_ascii=False))
        return 0

    stored = deploylib.load_config(cfg_path)
    args.action = "up"
    args.delivery_mode = stored.get("delivery_mode", deploylib.DEFAULT_CONFIG["delivery_mode"])
    args.platform = stored.get("platform", deploylib.DEFAULT_CONFIG["platform"])
    args.api_image = stored.get("api_image", deploylib.DEFAULT_CONFIG["api_image"])
    args.frontend_image = stored.get("frontend_image", deploylib.DEFAULT_CONFIG["frontend_image"])
    args.update_db = False
    args.rollback_from = ""
    config = deploylib.merged_config(args, stored)
    password = deploylib.resolve_password(args, stored)
    deploylib.validate_inputs(config, password, stage="remote")

    if args.save:
        to_store = {
            "host": config["host"],
            "port": config["port"],
            "user": config["user"],
            "remote_dir": config["remote_dir"],
            "compose_file": config["compose_file"],
            "env_file": config["env_file"],
            "artifact_dir": config["artifact_dir"],
            "backup_prefix": config["backup_prefix"],
            "healthcheck_url": config["healthcheck_url"],
            "ssh_key": config["ssh_key"],
            "delivery_mode": config["delivery_mode"],
            "platform": config["platform"],
            "api_image": config["api_image"],
            "frontend_image": config["frontend_image"],
        }
        if args.save_password and password:
            to_store["password"] = password
        deploylib.save_config(cfg_path, to_store)

    source_name, records = read_local_source(args, config)
    summary = summarize_records(records)
    sql_script = build_sql_script(records)
    artifact_dir = Path(str(config["artifact_dir"])).expanduser()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    sql_file = artifact_dir / "remote-resource-visibility-sync.sql"
    sql_file.write_text(sql_script, encoding="utf-8")
    remote_sql_path = build_remote_sql_path(config)

    upload_result = upload_remote_sql(
        config,
        password=password,
        sql_file=sql_file,
        remote_sql_path=remote_sql_path,
        dry_run=args.dry_run,
    )
    apply_result = apply_remote_sql(
        config,
        password=password,
        remote_sql_path=remote_sql_path,
        dry_run=args.dry_run,
    )

    payload: dict[str, Any] = {
        "config_path": str(cfg_path),
        "source": source_name,
        "source_summary": summary,
        "target": {
            "profile": config["profile"],
            "host": config["host"],
            "port": config["port"],
            "user": config["user"],
            "remote_dir": config["remote_dir"],
            "all_users_override": bool(args.all_users),
        },
        "artifacts": {
            "local_sql_file": str(sql_file),
            "remote_sql_file": remote_sql_path,
        },
        "upload": upload_result,
        "apply": apply_result,
    }
    if apply_result.get("stdout"):
        backup_dir = deploylib.extract_backup_dir(str(apply_result["stdout"]))
        if backup_dir:
            payload["backup_dir"] = backup_dir
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if upload_result.get("status") not in {"ok", "dry_run"}:
        return 1
    if apply_result.get("status") not in {"ok", "dry_run"}:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
