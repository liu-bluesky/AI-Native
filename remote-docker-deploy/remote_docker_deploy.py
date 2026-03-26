#!/usr/bin/env python3
"""Deploy a remote Docker stack over SSH with backup-first workflow."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.error
import urllib.request
from pathlib import Path
from shlex import quote
from typing import Any

DEFAULT_CONFIG = {
    "host": "64.81.113.174",
    "port": 22,
    "user": "root",
    "remote_dir": "/www/aiEmployee/docker",
    "compose_file": "compose.prod.yml",
    "env_file": ".env.prod",
    "action": "deploy",
    "delivery_mode": "offline",
    "backup_prefix": "auto-deploy",
    "healthcheck_url": "",
    "ssh_key": "",
    "platform": "linux/amd64",
    "api_image": "ai_employee-api:latest",
    "frontend_image": "ai_employee-frontend:latest",
    "artifact_dir": "/tmp/remote-docker-deploy",
}


def tool_root() -> Path:
    return Path(__file__).resolve().parent


def project_root() -> Path:
    return tool_root().parent


def normalize_profile_name(name: str) -> str:
    raw = str(name or "").strip().lower()
    if not raw:
        return "default"
    normalized = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in raw)
    normalized = normalized.strip(".-") or "default"
    return normalized


def config_path(profile: str = "default", api_key: str = "", employee_id: str = "") -> Path:
    root = tool_root()
    normalized_profile = normalize_profile_name(profile)
    if normalized_profile != "default":
        return root / f".remote-deploy.{normalized_profile}.json"
    if api_key:
        return root / f".remote-deploy-{api_key}.json"
    if employee_id:
        return root / f".remote-deploy-{employee_id}.json"
    return root / ".remote-deploy.json"


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"INVALID_CONFIG: {exc}") from exc
    return data if isinstance(data, dict) else {}


def save_config(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deploy remote Docker services over SSH.")
    parser.add_argument("--profile", default="default")
    parser.add_argument("--host", default="")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--user", default="")
    parser.add_argument("--remote-dir", default="")
    parser.add_argument("--compose-file", default="")
    parser.add_argument("--env-file", default="")
    parser.add_argument("--action", choices=["deploy", "up", "pull", "rollback"], default="")
    parser.add_argument("--delivery-mode", choices=["offline", "registry", "remote-build"], default="")
    parser.add_argument("--platform", default="")
    parser.add_argument("--api-image", default="")
    parser.add_argument("--frontend-image", default="")
    parser.add_argument("--artifact-dir", default="")
    parser.add_argument("--rollback-from", default="")
    parser.add_argument("--backup-prefix", default="")
    parser.add_argument("--healthcheck-url", default="")
    parser.add_argument("--ssh-key", default="")
    parser.add_argument("--password", default="")
    parser.add_argument("--password-env", default="REMOTE_DEPLOY_PASSWORD")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--employee-id", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--update-db", action="store_true")
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--save-password", action="store_true")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--skip-backup", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def merged_config(args: argparse.Namespace, stored: dict[str, Any]) -> dict[str, Any]:
    merged = dict(DEFAULT_CONFIG)
    merged.update({k: v for k, v in stored.items() if k != "update_db" and v not in (None, "")})
    for key in (
        "host",
        "user",
        "remote_dir",
        "compose_file",
        "env_file",
        "action",
        "delivery_mode",
        "platform",
        "api_image",
        "frontend_image",
        "artifact_dir",
        "backup_prefix",
        "healthcheck_url",
        "ssh_key",
    ):
        value = getattr(args, key)
        if value:
            merged[key] = value
    if args.port:
        merged["port"] = args.port
    merged["update_db"] = bool(args.update_db)
    merged["rollback_from"] = str(args.rollback_from or "").strip()
    merged["profile"] = normalize_profile_name(args.profile)
    merged["timeout"] = max(30, min(int(args.timeout or 600), 3600))
    return merged


def resolve_password(args: argparse.Namespace, stored: dict[str, Any]) -> str:
    if args.password:
        return args.password
    env_name = str(args.password_env or "REMOTE_DEPLOY_PASSWORD").strip()
    if env_name:
        env_value = os.getenv(env_name, "")
        if env_value:
            return env_value
    return str(stored.get("password") or "")


def validate_inputs(config: dict[str, Any], password: str) -> None:
    if not str(config.get("host") or "").strip():
        raise SystemExit("NO_CONFIG: host is required")
    if not str(config.get("user") or "").strip():
        raise SystemExit("NO_CONFIG: user is required")
    if not str(config.get("remote_dir") or "").strip():
        raise SystemExit("NO_CONFIG: remote_dir is required")
    ssh_key = str(config.get("ssh_key") or "").strip()
    if not password and not ssh_key:
        raise SystemExit("NO_AUTH: provide --password, --password-env, or --ssh-key")
    if ssh_key:
        ssh_key_path = Path(ssh_key).expanduser()
        if not ssh_key_path.exists():
            raise SystemExit(f"NO_SSH_KEY: ssh key not found: {ssh_key_path}")
    if str(config.get("action") or "").strip() == "rollback" and not str(config.get("rollback_from") or "").strip():
        raise SystemExit("NO_ROLLBACK_SOURCE: provide --rollback-from")
    delivery_mode = str(config.get("delivery_mode") or "registry").strip()
    if delivery_mode not in {"offline", "registry", "remote-build"}:
        raise SystemExit("INVALID_DELIVERY_MODE: choose offline, registry, or remote-build")
    if delivery_mode == "offline" and str(config.get("action") or "").strip() == "pull":
        raise SystemExit("INVALID_ACTION: offline delivery does not support action=pull")
    if delivery_mode == "remote-build" and str(config.get("action") or "").strip() == "pull":
        raise SystemExit("INVALID_ACTION: remote-build delivery does not support action=pull")


def build_ssh_command(config: dict[str, Any]) -> list[str]:
    command: list[str] = []
    ssh_key = str(config.get("ssh_key") or "").strip()
    command.extend(
        [
            "ssh",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            "ServerAliveInterval=30",
            "-p",
            str(config["port"]),
        ]
    )
    if ssh_key:
        command.extend(["-i", str(Path(ssh_key).expanduser())])
    command.append(f'{config["user"]}@{config["host"]}')
    return command


def tcl_quote(value: str) -> str:
    escaped = (
        str(value)
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("$", "\\$")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )
    return f'"{escaped}"'


def build_expect_command(command_args: list[str], password: str, timeout: int) -> list[str]:
    send_password = tcl_quote(f"{password}\r")
    cmd_items = " ".join(tcl_quote(arg) for arg in command_args)
    script = "\n".join(
        [
            f"set timeout {int(timeout)}",
            f"set cmd [list {cmd_items}]",
            "eval spawn $cmd",
            "expect {",
            '    -re "(?i)are you sure you want to continue connecting.*" { send "yes\\r"; exp_continue }',
            f'    -re "(?i)(password|passphrase).*:" {{ send -- {send_password}; exp_continue }}',
            "    eof",
            "}",
            "catch wait result",
            "set exit_status [lindex $result 3]",
            "exit $exit_status",
        ]
    )
    return ["expect", "-c", script]


def wrap_transport_command(command_args: list[str], password: str, timeout: int, *, dry_run: bool) -> tuple[list[str], str]:
    if not password:
        return command_args, "ssh_key_or_agent"
    sshpass = shutil.which("sshpass")
    if sshpass:
        return [sshpass, "-p", password, *command_args], "sshpass"
    expect_path = shutil.which("expect")
    if expect_path:
        return build_expect_command(command_args, password, timeout), "expect"
    if dry_run:
        return command_args, "ssh_key_or_agent"
    raise SystemExit("SSH_TOOL_MISSING: password auth requires local sshpass or expect")


def slugify_image_name(image: str) -> str:
    raw = str(image or "").strip()
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in raw)
    return safe or "image"


def local_artifact_paths(config: dict[str, Any]) -> dict[str, Path]:
    artifact_dir = Path(str(config["artifact_dir"])).expanduser()
    return {
        "dir": artifact_dir,
        "api_tar": artifact_dir / f"{slugify_image_name(str(config['api_image']))}.tar",
        "frontend_tar": artifact_dir / f"{slugify_image_name(str(config['frontend_image']))}.tar",
        "source_tar": artifact_dir / f"{project_root().name}-src.tar.gz",
    }


def remote_artifact_paths(config: dict[str, Any]) -> dict[str, str]:
    remote_dir = str(config["remote_dir"]).rstrip("/")
    remote_root = str(Path(remote_dir).parent).rstrip("/")
    api_tar_name = local_artifact_paths(config)["api_tar"].name
    frontend_tar_name = local_artifact_paths(config)["frontend_tar"].name
    source_tar_name = local_artifact_paths(config)["source_tar"].name
    return {
        "api_tar": f"{remote_dir}/{api_tar_name}",
        "frontend_tar": f"{remote_dir}/{frontend_tar_name}",
        "source_tar": f"{remote_root}/{source_tar_name}",
        "remote_root": remote_root,
        "build_dir": f"{remote_root}/build-src-live",
    }


def run_local_command(command: list[str], *, timeout: int) -> dict[str, Any]:
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return {
        "status": "ok" if result.returncode == 0 else "error",
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "command": command,
    }


def build_scp_command(config: dict[str, Any], source: Path, remote_target: str) -> list[str]:
    command = [
        "scp",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "ServerAliveInterval=30",
        "-P",
        str(config["port"]),
    ]
    ssh_key = str(config.get("ssh_key") or "").strip()
    if ssh_key:
        command.extend(["-i", str(Path(ssh_key).expanduser())])
    command.extend([str(source), f'{config["user"]}@{config["host"]}:{remote_target}'])
    return command


def should_skip_source_path(relative_path: Path) -> bool:
    parts = relative_path.parts
    if not parts:
        return False
    if parts[0] == ".git":
        return True
    if "__pycache__" in parts:
        return True
    if ".pytest_cache" in parts:
        return True
    if parts[:2] == ("docker", "backup"):
        return True
    if parts[:3] == ("web-admin", "frontend", "node_modules"):
        return True
    if parts[:3] == ("web-admin", "frontend", "dist"):
        return True
    name = relative_path.name
    if name in {".DS_Store"}:
        return True
    if name.endswith((".pyc", ".pyo")):
        return True
    return False


def create_source_bundle(bundle_path: Path) -> dict[str, Any]:
    root = project_root()
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    if bundle_path.exists():
        bundle_path.unlink()
    added_files = 0
    with tarfile.open(bundle_path, "w:gz") as archive:
        for path in sorted(root.rglob("*")):
            relative = path.relative_to(root)
            if should_skip_source_path(relative):
                continue
            archive.add(path, arcname=str(relative), recursive=False)
            if path.is_file():
                added_files += 1
    return {
        "status": "ok",
        "command": ["python-tarfile", str(bundle_path)],
        "stdout": f"created {bundle_path} with {added_files} files",
        "stderr": "",
        "path": str(bundle_path),
    }


def prepare_offline_artifacts(config: dict[str, Any], *, password: str, dry_run: bool) -> dict[str, Any]:
    paths = local_artifact_paths(config)
    remote_paths = remote_artifact_paths(config)
    commands = {
        "build_api": [
            "docker",
            "buildx",
            "build",
            "--platform",
            str(config["platform"]),
            "-f",
            str(project_root() / "docker" / "Dockerfile.api"),
            "-t",
            str(config["api_image"]),
            "--load",
            str(project_root()),
        ],
        "build_frontend": [
            "docker",
            "buildx",
            "build",
            "--platform",
            str(config["platform"]),
            "-f",
            str(project_root() / "docker" / "Dockerfile.frontend"),
            "-t",
            str(config["frontend_image"]),
            "--load",
            str(project_root()),
        ],
        "save_api": ["docker", "save", "-o", str(paths["api_tar"]), str(config["api_image"])],
        "save_frontend": ["docker", "save", "-o", str(paths["frontend_tar"]), str(config["frontend_image"])],
        "upload_api": build_scp_command(config, paths["api_tar"], remote_paths["api_tar"]),
        "upload_frontend": build_scp_command(config, paths["frontend_tar"], remote_paths["frontend_tar"]),
    }
    wrapped_upload_api, upload_api_auth_mode = wrap_transport_command(
        commands["upload_api"], password, int(config["timeout"]), dry_run=dry_run
    )
    wrapped_upload_frontend, upload_frontend_auth_mode = wrap_transport_command(
        commands["upload_frontend"], password, int(config["timeout"]), dry_run=dry_run
    )
    plan = {
        "delivery_mode": "offline",
        "platform": config["platform"],
        "local_artifacts": {key: str(value) for key, value in paths.items()},
        "remote_artifacts": remote_paths,
        "commands": {
            "build_api": commands["build_api"],
            "build_frontend": commands["build_frontend"],
            "save_api": commands["save_api"],
            "save_frontend": commands["save_frontend"],
            "upload_api": wrapped_upload_api,
            "upload_frontend": wrapped_upload_frontend,
        },
        "upload_auth_modes": {
            "api": upload_api_auth_mode,
            "frontend": upload_frontend_auth_mode,
        },
    }
    if dry_run:
        plan["status"] = "dry_run"
        return plan
    paths["dir"].mkdir(parents=True, exist_ok=True)
    steps: list[dict[str, Any]] = []
    for key in ("build_api", "build_frontend", "save_api", "save_frontend"):
        step_result = run_local_command(plan["commands"][key], timeout=int(config["timeout"]))
        step_result["step"] = key
        steps.append(step_result)
        if step_result["status"] != "ok":
            return {
                **plan,
                "status": "error",
                "failed_step": key,
                "steps": steps,
            }
    for key in ("upload_api", "upload_frontend"):
        step_result = run_local_command(plan["commands"][key], timeout=int(config["timeout"]))
        step_result["step"] = key
        steps.append(step_result)
        if step_result["status"] != "ok":
            return {
                **plan,
                "status": "error",
                "failed_step": key,
                "steps": steps,
            }
    return {
        **plan,
        "status": "ok",
        "steps": steps,
    }


def prepare_remote_build_artifacts(config: dict[str, Any], *, password: str, dry_run: bool) -> dict[str, Any]:
    paths = local_artifact_paths(config)
    remote_paths = remote_artifact_paths(config)
    commands = {
        "bundle_source": ["python-tarfile", str(paths["source_tar"])],
        "upload_source": build_scp_command(config, paths["source_tar"], remote_paths["source_tar"]),
    }
    wrapped_upload_source, upload_auth_mode = wrap_transport_command(
        commands["upload_source"], password, int(config["timeout"]), dry_run=dry_run
    )
    plan = {
        "delivery_mode": "remote-build",
        "local_artifacts": {
            "dir": str(paths["dir"]),
            "source_tar": str(paths["source_tar"]),
        },
        "remote_artifacts": {
            "source_tar": remote_paths["source_tar"],
            "build_dir": remote_paths["build_dir"],
            "remote_root": remote_paths["remote_root"],
        },
        "commands": {
            "bundle_source": commands["bundle_source"],
            "upload_source": wrapped_upload_source,
        },
        "upload_auth_modes": {
            "source": upload_auth_mode,
        },
    }
    if dry_run:
        plan["status"] = "dry_run"
        return plan
    steps: list[dict[str, Any]] = []
    bundle_result = create_source_bundle(paths["source_tar"])
    bundle_result["step"] = "bundle_source"
    steps.append(bundle_result)
    if bundle_result["status"] != "ok":
        return {
            **plan,
            "status": "error",
            "failed_step": "bundle_source",
            "steps": steps,
        }
    upload_result = run_local_command(plan["commands"]["upload_source"], timeout=int(config["timeout"]))
    upload_result["step"] = "upload_source"
    steps.append(upload_result)
    if upload_result["status"] != "ok":
        return {
            **plan,
            "status": "error",
            "failed_step": "upload_source",
            "steps": steps,
        }
    return {
        **plan,
        "status": "ok",
        "steps": steps,
    }


def build_remote_script(config: dict[str, Any], *, skip_backup: bool) -> str:
    remote_dir = quote(str(config["remote_dir"]))
    env_file = quote(str(config["env_file"]))
    compose_file = quote(str(config["compose_file"]))
    backup_prefix = quote(str(config["backup_prefix"]))
    rollback_from = quote(str(config.get("rollback_from") or ""))
    delivery_mode = str(config.get("delivery_mode") or "registry").strip()
    action = str(config["action"])
    auto_run_db_migrations = "true" if bool(config.get("update_db")) else "false"
    remote_paths = remote_artifact_paths(config)
    api_tar = quote(remote_paths["api_tar"])
    frontend_tar = quote(remote_paths["frontend_tar"])
    source_tar = quote(remote_paths["source_tar"])
    remote_root = quote(remote_paths["remote_root"])
    build_dir = quote(remote_paths["build_dir"])
    commands = [
        "set -euo pipefail",
        f"cd {remote_dir}",
        f"env_file={env_file}",
        f"compose_file={compose_file}",
        f"backup_prefix={backup_prefix}",
        f"rollback_from={rollback_from}",
        f"delivery_mode={quote(delivery_mode)}",
        f"api_tar={api_tar}",
        f"frontend_tar={frontend_tar}",
        f"source_tar={source_tar}",
        f"remote_root={remote_root}",
        f"build_dir={build_dir}",
        f"api_image={quote(str(config['api_image']))}",
        f"frontend_image={quote(str(config['frontend_image']))}",
        f"auto_run_db_migrations={quote(auto_run_db_migrations)}",
        "if ! command -v docker >/dev/null 2>&1; then echo 'REMOTE_FAILED: docker not found' >&2; exit 11; fi",
        "if ! docker compose version >/dev/null 2>&1; then echo 'REMOTE_FAILED: docker compose not available' >&2; exit 12; fi",
        "if [ ! -f ./deploy.sh ]; then echo 'REMOTE_FAILED: deploy.sh not found' >&2; exit 10; fi",
        'if [ ! -f "$env_file" ]; then echo "REMOTE_FAILED: env file not found: $env_file" >&2; exit 13; fi',
        'if [ ! -f "$compose_file" ]; then echo "REMOTE_FAILED: compose file not found: $compose_file" >&2; exit 14; fi',
        "chmod +x ./deploy.sh || true",
        'docker compose --env-file "$env_file" -f "$compose_file" config >/dev/null',
        'lock_dir=".remote-docker-deploy.lock"',
        'cleanup(){ rm -rf "$lock_dir"; }',
        'if ! mkdir "$lock_dir" 2>/dev/null; then echo "REMOTE_FAILED: deployment lock exists at $PWD/$lock_dir" >&2; exit 20; fi',
        'trap cleanup EXIT INT TERM',
        'printf "%s\\n" "host=$(hostname)" "pid=$$" "started_at=$(date -Iseconds)" > "$lock_dir/info.txt"',
    ]
    if action == "rollback":
        commands.extend(
            [
                'if [ -z "$rollback_from" ]; then echo "REMOTE_FAILED: rollback source required" >&2; exit 15; fi',
                'rollback_dir="$rollback_from"',
                'case "$rollback_dir" in /*) ;; *) rollback_dir="$PWD/$rollback_dir" ;; esac',
                'if [ ! -d "$rollback_dir" ]; then echo "REMOTE_FAILED: rollback dir not found: $rollback_dir" >&2; exit 16; fi',
            ]
        )
    if action == "deploy" and delivery_mode == "remote-build":
        commands.extend(
            [
                'if [ ! -f "$source_tar" ]; then echo "REMOTE_FAILED: missing uploaded source bundle: $source_tar" >&2; exit 17; fi',
                'mkdir -p "$remote_root"',
                'rm -rf "$build_dir"',
                'mkdir -p "$build_dir"',
                'tar -xzf "$source_tar" -C "$build_dir"',
                'cd "$build_dir"',
                'docker build -f docker/Dockerfile.api -t "$api_image" .',
                'docker build -f docker/Dockerfile.frontend -t "$frontend_image" .',
                'cp -f docker/deploy.sh "$remote_root/docker/deploy.sh"',
                'cp -f docker/compose.prod.yml "$remote_root/docker/compose.prod.yml"',
                'cp -f docker/.env.prod.example "$remote_root/docker/.env.prod.example"',
                'cp -f docker/nginx.conf "$remote_root/docker/nginx.conf"',
                'cd "$remote_root/docker"',
                'rm -f "$source_tar"',
            ]
        )
    should_backup = not skip_backup and action in {"deploy", "up", "rollback"}
    if should_backup:
        commands.extend(
            [
                "ts=$(date +%Y%m%d-%H%M%S)",
                'backup_dir="backup/${backup_prefix}-$ts"',
                'backup_root="$PWD/$backup_dir"',
                'mkdir -p "$backup_root"',
                './deploy.sh backup-db "$backup_root/ai_employee.sql"',
                './deploy.sh backup-skill-volume "$backup_root/mcp-skills-knowledge"',
                './deploy.sh backup-api-data-volume "$backup_root/api-data"',
                'echo "BACKUP_DIR=$backup_dir"',
            ]
        )
    if action == "deploy":
        if delivery_mode == "offline":
            commands.extend(
                [
                    'if [ ! -f "$api_tar" ]; then echo "REMOTE_FAILED: missing uploaded api image tar: $api_tar" >&2; exit 18; fi',
                    'if [ ! -f "$frontend_tar" ]; then echo "REMOTE_FAILED: missing uploaded frontend image tar: $frontend_tar" >&2; exit 19; fi',
                    'docker load -i "$api_tar"',
                    'docker load -i "$frontend_tar"',
                    'rm -f "$api_tar" "$frontend_tar"',
                    'AUTO_RUN_DB_MIGRATIONS=$auto_run_db_migrations ./deploy.sh up',
                ]
            )
        elif delivery_mode == "remote-build":
            commands.append('AUTO_RUN_DB_MIGRATIONS=$auto_run_db_migrations ./deploy.sh up')
        else:
            commands.append('AUTO_RUN_DB_MIGRATIONS=$auto_run_db_migrations ./deploy.sh deploy')
    elif action == "up":
        commands.append('AUTO_RUN_DB_MIGRATIONS=$auto_run_db_migrations ./deploy.sh up')
    elif action == "pull":
        commands.append("./deploy.sh pull")
    elif action == "rollback":
        commands.extend(
            [
                "AUTO_RUN_DB_MIGRATIONS=false ./deploy.sh up",
                'docker compose --env-file "$env_file" -f "$compose_file" stop api frontend || true',
                './deploy.sh restore-skill-volume "$rollback_dir/mcp-skills-knowledge"',
                './deploy.sh restore-api-data-volume "$rollback_dir/api-data"',
                './deploy.sh restore-db "$rollback_dir/ai_employee.sql"',
                'AUTO_RUN_DB_MIGRATIONS=$auto_run_db_migrations ./deploy.sh up',
            ]
        )
    commands.extend(
        [
            "./deploy.sh ps",
            'docker compose --env-file "$env_file" -f "$compose_file" ps',
        ]
    )
    return "; ".join(commands)


def run_remote(config: dict[str, Any], *, password: str, skip_backup: bool, dry_run: bool) -> dict[str, Any]:
    remote_script = build_remote_script(config, skip_backup=skip_backup)
    ssh_command = [*build_ssh_command(config), remote_script]
    command, auth_mode = wrap_transport_command(ssh_command, password, int(config["timeout"]), dry_run=dry_run)
    if dry_run:
        return {
            "status": "dry_run",
            "auth_mode": auth_mode,
            "command": command,
            "ssh_command": ssh_command,
            "remote_script": remote_script,
        }
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=int(config["timeout"]),
        check=False,
    )
    return {
        "status": "ok" if result.returncode == 0 else "error",
        "auth_mode": auth_mode,
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "command": command,
        "ssh_command": ssh_command,
        "remote_script": remote_script,
    }


def extract_backup_dir(stdout: str) -> str:
    for line in stdout.splitlines():
        if line.startswith("BACKUP_DIR="):
            return line.split("=", 1)[1].strip()
    return ""


def run_healthcheck(url: str, timeout: int) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=min(timeout, 30)) as response:
            body = response.read(400).decode("utf-8", errors="replace")
            return {
                "status": "ok",
                "code": response.status,
                "body_preview": body,
            }
    except urllib.error.HTTPError as exc:
        return {"status": "error", "code": exc.code, "message": str(exc)}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def main() -> int:
    args = parse_args()
    cfg_path = config_path(
        profile=args.profile.strip(),
        api_key=args.api_key.strip(),
        employee_id=args.employee_id.strip(),
    )
    if args.reset:
        if cfg_path.exists():
            cfg_path.unlink()
        print(json.dumps({"status": "reset", "config_path": str(cfg_path)}, ensure_ascii=False))
        return 0

    stored = load_config(cfg_path)
    config = merged_config(args, stored)
    password = resolve_password(args, stored)
    validate_inputs(config, password)
    delivery_result: dict[str, Any] | None = None

    if args.save:
        to_store = {
            "host": config["host"],
            "port": config["port"],
            "user": config["user"],
            "remote_dir": config["remote_dir"],
            "compose_file": config["compose_file"],
            "env_file": config["env_file"],
            "action": config["action"],
            "delivery_mode": config["delivery_mode"],
            "platform": config["platform"],
            "api_image": config["api_image"],
            "frontend_image": config["frontend_image"],
            "artifact_dir": config["artifact_dir"],
            "backup_prefix": config["backup_prefix"],
            "healthcheck_url": config["healthcheck_url"],
            "ssh_key": config["ssh_key"],
        }
        if args.save_password and password:
            to_store["password"] = password
        save_config(cfg_path, to_store)

    delivery_mode = str(config.get("delivery_mode") or "").strip()
    action = str(config.get("action") or "").strip()
    if delivery_mode == "offline" and action == "deploy":
        delivery_result = prepare_offline_artifacts(config, password=password, dry_run=args.dry_run)
    elif delivery_mode == "remote-build" and action == "deploy":
        delivery_result = prepare_remote_build_artifacts(config, password=password, dry_run=args.dry_run)
    if delivery_result is not None and delivery_result.get("status") == "error":
            payload = {
                "config_path": str(cfg_path),
                "target": {
                    "profile": config["profile"],
                    "host": config["host"],
                    "port": config["port"],
                    "user": config["user"],
                    "remote_dir": config["remote_dir"],
                    "action": config["action"],
                    "delivery_mode": config["delivery_mode"],
                    "rollback_from": str(config.get("rollback_from") or ""),
                    "update_db": bool(config.get("update_db")),
                },
                "delivery": delivery_result,
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 1

    deploy_result = run_remote(
        config,
        password=password,
        skip_backup=args.skip_backup,
        dry_run=args.dry_run,
    )
    payload: dict[str, Any] = {
        "config_path": str(cfg_path),
        "target": {
            "profile": config["profile"],
            "host": config["host"],
            "port": config["port"],
            "user": config["user"],
            "remote_dir": config["remote_dir"],
            "action": config["action"],
            "delivery_mode": config["delivery_mode"],
            "rollback_from": str(config.get("rollback_from") or ""),
            "update_db": bool(config.get("update_db")),
        },
        "deploy": deploy_result,
    }
    if delivery_result is not None:
        payload["delivery"] = delivery_result
    backup_dir = extract_backup_dir(str(deploy_result.get("stdout") or ""))
    if backup_dir:
        payload["backup_dir"] = backup_dir
    if deploy_result["status"] == "dry_run":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if deploy_result["status"] != "ok":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1

    healthcheck_url = str(config.get("healthcheck_url") or "").strip()
    if healthcheck_url:
        health = run_healthcheck(healthcheck_url, int(config["timeout"]))
        payload["healthcheck"] = health
        if health.get("status") != "ok":
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 1

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
