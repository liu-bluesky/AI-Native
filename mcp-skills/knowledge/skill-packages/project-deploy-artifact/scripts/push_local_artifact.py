#!/usr/bin/env python3
"""Upload a client-local deploy artifact to the project deploy artifact module."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import sys
import uuid
from pathlib import Path
from urllib import error, request


def _env_first(*names: str) -> str:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value.strip()
    return ""


def _api_url(api_base: str, path: str) -> str:
    base = str(api_base or "").strip().rstrip("/")
    if not base:
        raise ValueError("--api-base or AI_EMPLOYEE_API_BASE_URL is required")
    if base.endswith("/api"):
        return f"{base}{path}"
    return f"{base}/api{path}"


def _json_request(url: str, *, token: str, payload: dict) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(url, data=data, headers=headers, method="POST")
    return _read_json_response(req)


def _read_json_response(req: request.Request) -> dict:
    try:
        with request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(body)
        except Exception:
            detail = body
        raise RuntimeError(json.dumps({"status": exc.code, "error": detail}, ensure_ascii=False)) from exc


def _multipart_body(fields: dict[str, str], file_field: str, file_path: Path) -> tuple[bytes, str]:
    boundary = f"----ai-employee-artifact-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for key, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"))
        chunks.append(str(value).encode("utf-8"))
        chunks.append(b"\r\n")
    filename = file_path.name
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    chunks.append(f"--{boundary}\r\n".encode("utf-8"))
    chunks.append(
        (
            f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8")
    )
    chunks.append(file_path.read_bytes())
    chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), boundary


def _upload(args: argparse.Namespace) -> dict:
    artifact_path = Path(args.file).expanduser()
    if not artifact_path.is_file():
        raise FileNotFoundError(f"artifact file does not exist: {artifact_path}")
    content = artifact_path.read_bytes()
    checksum = "sha256:" + hashlib.sha256(content).hexdigest()
    artifact_name = args.artifact_name or artifact_path.name
    manifest = {
        "checksum": checksum,
        "size": len(content),
        **({"version": args.version} if args.version else {}),
    }
    if args.dry_run:
        return {
            "status": "dry_run",
            "project_id": args.project_id,
            "profile": args.profile,
            "component": args.component,
            "artifact_name": artifact_name,
            "artifact_kind": args.artifact_kind,
            "size": len(content),
            "checksum": checksum,
            "auto_deploy": args.auto_deploy,
        }
    fields = {
        "profile": args.profile,
        "component": args.component,
        "artifact_name": artifact_name,
        "artifact_kind": args.artifact_kind,
        "version": args.version or "",
        "size": str(len(content)),
        "checksum": checksum,
        "manifest_json": json.dumps(manifest, ensure_ascii=False),
        "chat_session_id": args.chat_session_id or "",
        "task_tree_node_id": args.task_tree_node_id or "",
    }
    body, boundary = _multipart_body(fields, "file", artifact_path)
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    if args.token:
        headers["Authorization"] = f"Bearer {args.token}"
    upload_url = _api_url(args.api_base, f"/projects/{args.project_id}/deploy-artifacts/upload")
    req = request.Request(upload_url, data=body, headers=headers, method="POST")
    upload_result = _read_json_response(req)
    deploy_result = None
    artifact_id = str((upload_result.get("artifact") or {}).get("id") or "").strip()
    if args.auto_deploy and artifact_id:
        deploy_endpoint = "deploy" if args.plain_deploy else "deploy/ai-execute"
        deploy_url = _api_url(
            args.api_base,
            f"/projects/{args.project_id}/deploy-artifacts/{artifact_id}/{deploy_endpoint}",
        )
        deploy_result = _json_request(
            deploy_url,
            token=args.token,
            payload={
                "chat_session_id": args.chat_session_id or "",
                "task_tree_node_id": args.task_tree_node_id or "",
                "requirement": args.requirement or "",
                "plan": args.plan or "",
            },
        )
    return {
        "status": "uploaded",
        "project_id": args.project_id,
        "artifact_id": artifact_id,
        "checksum": checksum,
        "size": len(content),
        "upload": upload_result,
        "deployment": deploy_result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default=_env_first("AI_EMPLOYEE_API_BASE_URL", "API_BASE_URL"))
    parser.add_argument("--token", default=_env_first("AI_EMPLOYEE_AUTH_TOKEN", "AI_EMPLOYEE_TOKEN", "AUTH_TOKEN"))
    parser.add_argument("--project-id", default=_env_first("AI_EMPLOYEE_PROJECT_ID"))
    parser.add_argument("--file", required=True, help="Local artifact file path on this client/Runner host.")
    parser.add_argument("--profile", default="prod")
    parser.add_argument("--component", default="")
    parser.add_argument("--artifact-name", default="")
    parser.add_argument("--artifact-kind", default="source-bundle")
    parser.add_argument("--version", default="")
    parser.add_argument("--chat-session-id", default="")
    parser.add_argument("--task-tree-node-id", default="")
    parser.add_argument("--requirement", default="", help="Deployment requirement, e.g. 解压后部署.")
    parser.add_argument("--plan", default="", help="Optional deployment plan summary.")
    parser.add_argument("--no-auto-deploy", dest="auto_deploy", action="store_false")
    parser.add_argument(
        "--plain-deploy",
        action="store_true",
        help="Use the plain deploy endpoint instead of the project detail AI deploy endpoint.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.set_defaults(auto_deploy=True)
    args = parser.parse_args()
    if not args.project_id:
        parser.error("--project-id or AI_EMPLOYEE_PROJECT_ID is required")
    try:
        print(json.dumps(_upload(args), ensure_ascii=False, indent=2))
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
