#!/usr/bin/env python3
"""Sync local PostgreSQL business tables to the remote PostgreSQL database."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import remote_docker_deploy as deploylib

DEFAULT_EXCLUDED_TABLES = {"schema_migrations"}


@dataclass(frozen=True)
class ColumnMeta:
    name: str
    data_type: str
    udt_name: str


@dataclass(frozen=True)
class TableMeta:
    name: str
    columns: list[ColumnMeta]
    primary_key: list[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync local PostgreSQL tables to the remote PostgreSQL database.")
    parser.add_argument("--profile", default="default")
    parser.add_argument("--host", default="")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--user", default="")
    parser.add_argument("--remote-dir", default="")
    parser.add_argument("--compose-file", default="")
    parser.add_argument("--env-file", default="")
    parser.add_argument("--artifact-dir", default="")
    parser.add_argument("--backup-prefix", default="pg-data-sync")
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
    parser.add_argument("--tables", default="", help="Comma separated public table names to sync; default is all public tables except schema_migrations.")
    parser.add_argument("--exclude-tables", default="", help="Comma separated public table names to skip.")
    parser.add_argument("--replace", action="store_true", help="Truncate selected remote tables before importing local rows.")
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--local-postgres-container", default="ai-employee-postgres")
    parser.add_argument("--local-db-user", default="admin")
    parser.add_argument("--local-db-name", default="ai_employee")
    parser.add_argument("--remote-postgres-container", default="ai-employee-postgres")
    parser.add_argument("--remote-db-user", default="admin")
    parser.add_argument("--remote-db-name", default="ai_employee")
    return parser.parse_args()


def normalize_names(raw_value: str) -> list[str]:
    results: list[str] = []
    seen: set[str] = set()
    for item in str(raw_value or "").split(","):
        name = item.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        results.append(name)
    return results


def sql_quote(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def run_local_command(command: list[str], *, timeout: int) -> dict[str, Any]:
    return deploylib.run_local_command(command, timeout=timeout)


def run_local_psql(
    sql: str,
    *,
    container_name: str,
    db_user: str,
    db_name: str,
    timeout: int,
) -> str:
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
        sql,
    ]
    result = run_local_command(command, timeout=timeout)
    if result["status"] != "ok":
        raise RuntimeError(result.get("stderr") or result.get("stdout") or f"failed to execute SQL: {sql}")
    return str(result.get("stdout") or "")


def list_public_tables(
    *,
    container_name: str,
    db_user: str,
    db_name: str,
    timeout: int,
) -> list[str]:
    sql = (
        "SELECT tablename "
        "FROM pg_tables "
        "WHERE schemaname = 'public' "
        "ORDER BY tablename"
    )
    output = run_local_psql(
        sql,
        container_name=container_name,
        db_user=db_user,
        db_name=db_name,
        timeout=timeout,
    )
    return [line.strip() for line in output.splitlines() if line.strip()]


def describe_table(
    table_name: str,
    *,
    container_name: str,
    db_user: str,
    db_name: str,
    timeout: int,
) -> TableMeta:
    columns_sql = f"""
SELECT column_name, data_type, udt_name
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = {sql_quote(table_name)}
ORDER BY ordinal_position
"""
    pk_sql = f"""
SELECT kcu.column_name
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON tc.constraint_name = kcu.constraint_name
 AND tc.table_schema = kcu.table_schema
WHERE tc.table_schema = 'public'
  AND tc.table_name = {sql_quote(table_name)}
  AND tc.constraint_type = 'PRIMARY KEY'
ORDER BY kcu.ordinal_position
"""
    columns_output = run_local_psql(
        columns_sql,
        container_name=container_name,
        db_user=db_user,
        db_name=db_name,
        timeout=timeout,
    )
    pk_output = run_local_psql(
        pk_sql,
        container_name=container_name,
        db_user=db_user,
        db_name=db_name,
        timeout=timeout,
    )
    columns: list[ColumnMeta] = []
    for line in columns_output.splitlines():
        if not line.strip():
            continue
        name, data_type, udt_name = line.split("\t", 2)
        columns.append(ColumnMeta(name=name, data_type=data_type, udt_name=udt_name))
    primary_key = [line.strip() for line in pk_output.splitlines() if line.strip()]
    if not columns:
        raise RuntimeError(f"table has no visible columns: {table_name}")
    if not primary_key:
        raise RuntimeError(f"table has no primary key: {table_name}")
    return TableMeta(name=table_name, columns=columns, primary_key=primary_key)


def fetch_table_rows(
    meta: TableMeta,
    *,
    container_name: str,
    db_user: str,
    db_name: str,
    timeout: int,
) -> list[dict[str, Any]]:
    order_clause = ", ".join(f'"{name}"' for name in meta.primary_key)
    sql = (
        f'SELECT row_to_json(t)::text '
        f'FROM (SELECT * FROM public."{meta.name}" ORDER BY {order_clause}) t'
    )
    output = run_local_psql(
        sql,
        container_name=container_name,
        db_user=db_user,
        db_name=db_name,
        timeout=timeout,
    )
    rows: list[dict[str, Any]] = []
    for line in output.splitlines():
        text = line.strip()
        if not text:
            continue
        rows.append(json.loads(text))
    return rows


def sql_literal(value: Any, column: ColumnMeta) -> str:
    if value is None:
        return "NULL"
    udt_name = str(column.udt_name or "").strip().lower()
    data_type = str(column.data_type or "").strip().lower()
    if udt_name == "jsonb":
        return sql_quote(json.dumps(value, ensure_ascii=False)) + "::jsonb"
    if udt_name == "json":
        return sql_quote(json.dumps(value, ensure_ascii=False)) + "::json"
    if udt_name in {"bool"} or data_type == "boolean":
        return "TRUE" if bool(value) else "FALSE"
    if udt_name in {"int2", "int4", "int8", "float4", "float8", "numeric"} or data_type in {
        "smallint",
        "integer",
        "bigint",
        "real",
        "double precision",
        "numeric",
    }:
        return str(value)
    return sql_quote(str(value))


def build_insert_statements(meta: TableMeta, rows: list[dict[str, Any]], *, batch_size: int) -> list[str]:
    if not rows:
        return []
    safe_batch_size = max(1, min(int(batch_size or 200), 1000))
    column_names = [column.name for column in meta.columns]
    insert_columns = ", ".join(f'"{name}"' for name in column_names)
    conflict_columns = ", ".join(f'"{name}"' for name in meta.primary_key)
    update_columns = [name for name in column_names if name not in set(meta.primary_key)]
    update_clause = ", ".join(f'"{name}" = EXCLUDED."{name}"' for name in update_columns)
    statements: list[str] = []
    for start in range(0, len(rows), safe_batch_size):
        chunk = rows[start : start + safe_batch_size]
        values_sql: list[str] = []
        for row in chunk:
            literals = [
                sql_literal(row.get(column.name), column)
                for column in meta.columns
            ]
            values_sql.append("(" + ", ".join(literals) + ")")
        statement = (
            f'INSERT INTO public."{meta.name}" ({insert_columns}) VALUES\n'
            + ",\n".join(values_sql)
            + f'\nON CONFLICT ({conflict_columns}) DO UPDATE SET {update_clause};'
        )
        statements.append(statement)
    return statements


def build_sync_sql(
    tables: list[tuple[TableMeta, list[dict[str, Any]]]],
    *,
    batch_size: int,
    replace: bool,
) -> str:
    lines = ["BEGIN;"]
    if replace:
        for meta, _rows in tables:
            lines.append(f'TRUNCATE TABLE public."{meta.name}" RESTART IDENTITY;')
    for meta, rows in tables:
        lines.append(f"-- {meta.name}: {len(rows)} rows")
        lines.extend(build_insert_statements(meta, rows, batch_size=batch_size))
    lines.append("COMMIT;")
    lines.extend(
        [
            "SELECT table_name, total_rows FROM (",
            *[
                (
                    f"  SELECT {sql_quote(meta.name)} AS table_name, COUNT(*)::bigint AS total_rows "
                    f'FROM public."{meta.name}"'
                )
                + (" UNION ALL" if index < len(tables) - 1 else "")
                for index, (meta, _rows) in enumerate(tables)
            ],
            ") summary ORDER BY table_name;",
        ]
    )
    return "\n".join(lines) + "\n"


def build_remote_sql_path(config: dict[str, Any]) -> str:
    remote_root = str(Path(str(config["remote_dir"])).parent)
    return f"{remote_root.rstrip('/')}/remote-pg-data-sync.sql"


def build_remote_apply_script(
    config: dict[str, Any],
    remote_sql_path: str,
    *,
    remote_postgres_container: str,
    remote_db_user: str,
    remote_db_name: str,
) -> str:
    remote_dir = deploylib.quote(str(config["remote_dir"]))
    backup_prefix = deploylib.quote(str(config["backup_prefix"]))
    remote_sql = deploylib.quote(remote_sql_path)
    remote_container = deploylib.quote(remote_postgres_container)
    db_user = deploylib.quote(remote_db_user)
    db_name = deploylib.quote(remote_db_name)
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
            f'cat {remote_sql} | docker exec -i {remote_container} psql -v ON_ERROR_STOP=1 -U {db_user} -d {db_name}',
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
    remote_postgres_container: str,
    remote_db_user: str,
    remote_db_name: str,
    dry_run: bool,
) -> dict[str, Any]:
    remote_script = build_remote_apply_script(
        config,
        remote_sql_path,
        remote_postgres_container=remote_postgres_container,
        remote_db_user=remote_db_user,
        remote_db_name=remote_db_name,
    )
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


def resolve_table_selection(
    args: argparse.Namespace,
    *,
    container_name: str,
    db_user: str,
    db_name: str,
    timeout: int,
) -> list[str]:
    all_tables = list_public_tables(
        container_name=container_name,
        db_user=db_user,
        db_name=db_name,
        timeout=timeout,
    )
    requested_tables = normalize_names(args.tables)
    excluded_tables = set(DEFAULT_EXCLUDED_TABLES)
    excluded_tables.update(normalize_names(args.exclude_tables))
    if requested_tables:
        selected = [name for name in requested_tables if name not in excluded_tables]
    else:
        selected = [name for name in all_tables if name not in excluded_tables]
    missing = [name for name in selected if name not in all_tables]
    if missing:
        raise SystemExit(f"UNKNOWN_TABLES: {', '.join(missing)}")
    if not selected:
        raise SystemExit("NO_TABLES_SELECTED")
    return selected


def summarize_tables(tables: list[tuple[TableMeta, list[dict[str, Any]]]]) -> dict[str, int]:
    return {meta.name: len(rows) for meta, rows in tables}


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

    selected_tables = resolve_table_selection(
        args,
        container_name=args.local_postgres_container,
        db_user=args.local_db_user,
        db_name=args.local_db_name,
        timeout=int(config["timeout"]),
    )
    table_payloads: list[tuple[TableMeta, list[dict[str, Any]]]] = []
    for table_name in selected_tables:
        meta = describe_table(
            table_name,
            container_name=args.local_postgres_container,
            db_user=args.local_db_user,
            db_name=args.local_db_name,
            timeout=int(config["timeout"]),
        )
        rows = fetch_table_rows(
            meta,
            container_name=args.local_postgres_container,
            db_user=args.local_db_user,
            db_name=args.local_db_name,
            timeout=int(config["timeout"]),
        )
        table_payloads.append((meta, rows))

    sql_script = build_sync_sql(
        table_payloads,
        batch_size=args.batch_size,
        replace=bool(args.replace),
    )
    artifact_dir = Path(str(config["artifact_dir"])).expanduser()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    sql_file = artifact_dir / "remote-pg-data-sync.sql"
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
        remote_postgres_container=args.remote_postgres_container,
        remote_db_user=args.remote_db_user,
        remote_db_name=args.remote_db_name,
        dry_run=args.dry_run,
    )

    payload: dict[str, Any] = {
        "config_path": str(cfg_path),
        "source": {
            "local_postgres_container": args.local_postgres_container,
            "database": args.local_db_name,
            "user": args.local_db_user,
            "tables": summarize_tables(table_payloads),
        },
        "target": {
            "profile": config["profile"],
            "host": config["host"],
            "port": config["port"],
            "user": config["user"],
            "remote_dir": config["remote_dir"],
            "remote_postgres_container": args.remote_postgres_container,
            "database": args.remote_db_name,
            "db_user": args.remote_db_user,
            "replace": bool(args.replace),
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
