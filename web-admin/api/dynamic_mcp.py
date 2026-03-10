"""动态 Micro-MCP 服务生成器"""
from __future__ import annotations

import asyncio
from contextvars import ContextVar
from dataclasses import asdict
from datetime import timedelta
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

import requests
from urllib.parse import parse_qs

from fastapi.responses import JSONResponse, Response
from mcp.server.fastmcp import FastMCP
from starlette.types import ASGIApp, Receive, Scope, Send

from deps import employee_store, external_mcp_store, project_store, usage_store
from feedback_service import get_feedback_service
from stores import (
    Classification,
    Memory,
    MemoryScope,
    MemoryType,
    memory_store,
    rule_store,
    serialize_memory,
    serialize_rule,
    serialize_skill,
    skill_store,
)


def _load_project_config() -> dict:
    """从项目根目录读取 .mcp-project.json 配置，不存在则创建"""
    try:
        config_path = Path.cwd() / ".mcp-project.json"
        if config_path.exists():
            return json.loads(config_path.read_text(encoding="utf-8"))
        else:
            # 首次使用，创建示例配置
            default_config = {
                "project_id": "default",
                "project_name": "Default Project",
                "description": "请修改此文件，设置你的项目名称"
            }
            config_path.write_text(json.dumps(default_config, ensure_ascii=False, indent=2), encoding="utf-8")
            return default_config
    except Exception:
        pass
    return {}


# 缓存动态生成的 ASGI App
_rule_apps = {}
_skill_apps = {}
_employee_apps = {}
_project_apps = {}
_employee_app_signatures = {}
_project_app_signatures = {}
_external_mcp_tool_cache: dict[str, list[dict]] = {}
_external_mcp_tool_signatures: dict[str, tuple] = {}
_session_keys: dict[str, tuple[str, str]] = {}  # session_id -> (api_key, developer_name)
_current_api_key: ContextVar[str] = ContextVar("_current_api_key", default="")
_current_developer_name: ContextVar[str] = ContextVar("_current_developer_name", default="")
_EMPLOYEE_MCP_APP_REV = "2026-03-04-sse-post-bridge"
_PROJECT_MCP_APP_REV = "2026-03-05-project-mcp-v1"
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_EXECUTABLE_SUFFIXES = {".py", ".js"}
_FASTMCP_HOST = os.environ.get("FASTMCP_HOST", "0.0.0.0")

# 启动时加载底层安全策略（不可运行时修改，需重启生效）
_SYSTEM_POLICY_PATH = Path(__file__).parent / "system-policy.md"
_SYSTEM_POLICY = _SYSTEM_POLICY_PATH.read_text(encoding="utf-8") if _SYSTEM_POLICY_PATH.exists() else ""


def _patch_mcp_arguments_body(body: bytes) -> bytes:
    try:
        payload = json.loads(body)
    except Exception:
        return body
    if not isinstance(payload, dict):
        return body

    params = payload.get("params")
    if not isinstance(params, dict):
        return body

    arguments = params.get("arguments")
    patched_arguments = None
    if isinstance(arguments, str):
        text = arguments.strip()
        if not text:
            patched_arguments = {}
        else:
            try:
                parsed = json.loads(text)
            except Exception:
                return body
            if not isinstance(parsed, dict):
                return body
            patched_arguments = parsed
    elif isinstance(arguments, dict) and set(arguments.keys()) == {"arguments"}:
        inner = arguments.get("arguments")
        if isinstance(inner, str):
            text = inner.strip()
            if not text:
                patched_arguments = {}
            else:
                try:
                    parsed = json.loads(text)
                except Exception:
                    return body
                if not isinstance(parsed, dict):
                    return body
                patched_arguments = parsed
    if patched_arguments is None:
        return body

    params["arguments"] = patched_arguments
    return json.dumps(payload).encode("utf-8")


class _McpArgumentsCompatApp:
    def __init__(self, app: ASGIApp):
        self.app = app
        self._arguments_compat_enabled = True

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        method = str(scope.get("method", "")).upper()
        path = str(scope.get("path", ""))
        if method != "POST" or not path.rstrip("/").endswith("/messages"):
            await self.app(scope, receive, send)
            return

        chunks: list[bytes] = []
        while True:
            message = await receive()
            if message.get("type") != "http.request":
                break
            chunks.append(message.get("body", b""))
            if not message.get("more_body", False):
                break
        raw_body = b"".join(chunks)
        patched_body = _patch_mcp_arguments_body(raw_body)

        consumed = False

        async def replay_receive():
            nonlocal consumed
            if consumed:
                return {"type": "http.request", "body": b"", "more_body": False}
            consumed = True
            return {"type": "http.request", "body": patched_body, "more_body": False}

        await self.app(scope, replay_receive, send)


def _apply_mcp_arguments_compat(app: ASGIApp) -> ASGIApp:
    """兼容部分客户端把 MCP call arguments 错传成 JSON 字符串。"""
    if getattr(app, "_arguments_compat_enabled", False):
        return app
    return _McpArgumentsCompatApp(app)


def _replace_path_suffix(path: str, old_suffix: str, new_suffix: str) -> str:
    if path == old_suffix:
        return new_suffix
    if path.endswith(old_suffix):
        return path[: -len(old_suffix)] + new_suffix
    return path


class _DualTransportMcpApp:
    """Expose both legacy SSE and streamable-http transports under one mount."""

    def __init__(self, sse_app: ASGIApp, streamable_http_app: ASGIApp):
        self.sse_app = sse_app
        self.streamable_http_app = streamable_http_app
        self._streamable_lifespan_started = False
        self._streamable_lifespan_lock = asyncio.Lock()
        self._streamable_manager_task: asyncio.Task | None = None
        self._streamable_ready = asyncio.Event()

    def _get_streamable_session_manager(self):
        routes = getattr(self.streamable_http_app, "routes", None) or []
        for route in routes:
            endpoint = getattr(route, "endpoint", None)
            session_manager = getattr(endpoint, "session_manager", None)
            if session_manager is not None:
                return session_manager
        return None

    async def _run_streamable_session_manager(self, session_manager) -> None:
        try:
            async with session_manager.run():
                self._streamable_ready.set()
                await asyncio.Event().wait()
        except Exception:
            self._streamable_ready.set()
            raise

    async def _ensure_streamable_lifespan(self) -> None:
        if self._streamable_lifespan_started:
            return
        async with self._streamable_lifespan_lock:
            if self._streamable_lifespan_started:
                return
            task = self._streamable_manager_task
            if task and task.done():
                await task
            session_manager = self._get_streamable_session_manager()
            if session_manager is None:
                self._streamable_lifespan_started = True
                return
            self._streamable_ready.clear()
            self._streamable_manager_task = asyncio.create_task(
                self._run_streamable_session_manager(session_manager)
            )
            await self._streamable_ready.wait()
            task = self._streamable_manager_task
            if task and task.done():
                await task
            self._streamable_lifespan_started = True

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope.get("type") != "http":
            await self.sse_app(scope, receive, send)
            return

        method = str(scope.get("method", "")).upper()
        path = str(scope.get("path", ""))
        normalized = path.rstrip("/") or "/"
        is_sse = normalized.endswith("/sse")
        is_streamable = normalized.endswith("/mcp")

        if is_streamable:
            await self._ensure_streamable_lifespan()
            await self.streamable_http_app(scope, receive, send)
            return

        # Some clients probe streamable-http by POSTing to /sse.
        # Bridge these requests to /mcp for compatibility.
        if is_sse and method != "GET":
            await self._ensure_streamable_lifespan()
            rewritten = _replace_path_suffix(path, "/sse", "/mcp")
            rewritten_scope = dict(scope)
            rewritten_scope["path"] = rewritten
            rewritten_scope["raw_path"] = rewritten.encode("utf-8")
            await self.streamable_http_app(rewritten_scope, receive, send)
            return

        await self.sse_app(scope, receive, send)


def _normalize_domain(value: str) -> str:
    return str(value or "").strip().lower()


def _query_rules_by_employee(employee, keyword: str = "") -> list:
    rule_ids = [str(item or "").strip() for item in (getattr(employee, "rule_ids", []) or []) if str(item or "").strip()]
    kw = str(keyword or "").strip().lower()
    if rule_ids:
        seen: set[str] = set()
        results = []
        for rule_id in rule_ids:
            if rule_id in seen:
                continue
            seen.add(rule_id)
            rule = rule_store.get(rule_id)
            if rule is None:
                continue
            if kw and kw not in rule.title.lower() and kw not in rule.content.lower():
                continue
            results.append(rule)
        return results

    domains = {_normalize_domain(d) for d in employee.rule_domains or [] if str(d).strip()}
    if not domains:
        return []
    results = []
    for rule in rule_store.list_all():
        if _normalize_domain(rule.domain) not in domains:
            continue
        if kw and kw not in rule.title.lower() and kw not in rule.content.lower():
            continue
        results.append(rule)
    return results


def _employee_rule_summary(employee, limit: int = 50) -> list[dict[str, str]]:
    rules = _query_rules_by_employee(employee)
    rule_bindings: list[dict[str, str]] = []
    seen_ids: set[str] = set()

    for rule in rules:
        if len(rule_bindings) >= limit:
            break
        rid = str(getattr(rule, "id", "") or "").strip()
        if not rid or rid in seen_ids:
            continue
        seen_ids.add(rid)
        rule_bindings.append(
            {
                "id": rid,
                "title": str(getattr(rule, "title", "") or "").strip(),
                "domain": str(getattr(rule, "domain", "") or "").strip(),
            }
        )
    return rule_bindings


def _employee_skill_summary(employee) -> tuple[list[str], list[str]]:
    skill_ids: list[str] = []
    skill_names: list[str] = []
    seen: set[str] = set()
    for item in getattr(employee, "skills", []) or []:
        skill_id = str(item or "").strip()
        if not skill_id or skill_id in seen:
            continue
        seen.add(skill_id)
        skill_ids.append(skill_id)
        skill = skill_store.get(skill_id)
        skill_name = str(getattr(skill, "name", "") or "").strip() or skill_id
        skill_names.append(skill_name)
    if not skill_names:
        skill_names = list(skill_ids)
    return skill_ids, skill_names


def _serialize_project_member_profile(
    member,
    employee,
    *,
    project_id: str,
    rule_limit: int,
) -> dict:
    employee_id = str(getattr(member, "employee_id", "") or "").strip()
    if employee is None:
        return {
            "project_id": project_id,
            "employee_id": employee_id,
            "id": employee_id,
            "employee_name": "",
            "name": "",
            "description": "",
            "role": str(getattr(member, "role", "member") or "member"),
            "enabled": bool(getattr(member, "enabled", True)),
            "joined_at": str(getattr(member, "joined_at", "") or ""),
            "skills": [],
            "skill_names": [],
            "rule_bindings": [],
            "tone": "",
            "verbosity": "",
            "language": "",
            "mcp_enabled": False,
            "feedback_upgrade_enabled": False,
            "employee_exists": False,
        }

    resolved_employee_id = str(getattr(employee, "id", "") or employee_id).strip()
    employee_name = str(getattr(employee, "name", "") or "").strip()
    skill_ids, skill_names = _employee_skill_summary(employee)
    rule_bindings = _employee_rule_summary(employee, limit=rule_limit)
    return {
        "project_id": project_id,
        "employee_id": resolved_employee_id,
        "id": resolved_employee_id,
        "employee_name": employee_name,
        "name": employee_name,
        "description": str(getattr(employee, "description", "") or ""),
        "role": str(getattr(member, "role", "member") or "member"),
        "enabled": bool(getattr(member, "enabled", True)),
        "joined_at": str(getattr(member, "joined_at", "") or ""),
        "skills": skill_ids,
        "skill_names": skill_names,
        "rule_bindings": rule_bindings,
        "tone": str(getattr(employee, "tone", "") or ""),
        "verbosity": str(getattr(employee, "verbosity", "") or ""),
        "language": str(getattr(employee, "language", "") or ""),
        "mcp_enabled": bool(getattr(employee, "mcp_enabled", False)),
        "feedback_upgrade_enabled": bool(getattr(employee, "feedback_upgrade_enabled", False)),
        "employee_exists": True,
    }


def list_project_member_profiles_runtime(
    project_id: str,
    *,
    include_disabled: bool = True,
    include_missing: bool = True,
    rule_limit: int = 30,
) -> list[dict]:
    """构建项目成员统一画像，供 MCP 与聊天等路径复用。"""
    project = project_store.get(project_id)
    if project is None:
        return []
    profiles: list[dict] = []
    for member in project_store.list_members(project_id):
        if not include_disabled and not bool(getattr(member, "enabled", True)):
            continue
        employee = employee_store.get(member.employee_id)
        if employee is None and not include_missing:
            continue
        profiles.append(
            _serialize_project_member_profile(
                member,
                employee,
                project_id=project_id,
                rule_limit=rule_limit,
            )
        )
    return profiles


def _tool_token(value: str) -> str:
    text = "".join(ch if ch.isalnum() else "_" for ch in str(value or "").strip().lower())
    text = "_".join(part for part in text.split("_") if part)
    if not text:
        return "tool"
    if text[0].isdigit():
        return f"t_{text}"
    return text


_QUESTION_FIELD_KEYS = {
    "question",
    "query",
    "prompt",
    "content",
    "message",
    "text",
    "input",
    "user_input",
    "symptom",
    "expected",
    "title",
}
_PROJECT_FIELD_KEYS = {
    "project",
    "project_id",
    "project_name",
    "workspace",
    "workspace_id",
    "repo",
    "repository",
}
_RECALL_EMPLOYEE_MEMORY_LIMIT = 100


def _normalize_text(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def _extract_text_nodes(node: object) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, list):
        out: list[str] = []
        for item in node:
            out.extend(_extract_text_nodes(item))
        return out
    if isinstance(node, dict):
        out: list[str] = []
        if isinstance(node.get("text"), str):
            out.append(node["text"])
        if isinstance(node.get("content"), (str, list, dict)):
            out.extend(_extract_text_nodes(node["content"]))
        return out
    return []


def _join_text_nodes(node: object) -> str:
    parts = _extract_text_nodes(node)
    if not parts:
        return ""
    return "".join(parts)


def _collect_question_values(node: object, key_hint: str = "") -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    if isinstance(node, dict):
        for key, val in node.items():
            key_name = str(key or "").strip().lower()
            if isinstance(val, str) and key_name in _QUESTION_FIELD_KEYS:
                values.append((key_name, val))
            else:
                values.extend(_collect_question_values(val, key_name))
    elif isinstance(node, list):
        for item in node:
            values.extend(_collect_question_values(item, key_hint))
    elif isinstance(node, str) and key_hint in _QUESTION_FIELD_KEYS:
        values.append((key_hint, node))
    return values


def _collect_project_values(node: object, key_hint: str = "") -> list[str]:
    values: list[str] = []
    if isinstance(node, dict):
        for key, val in node.items():
            key_name = str(key or "").strip().lower()
            if isinstance(val, str) and key_name in _PROJECT_FIELD_KEYS:
                values.append(val)
            else:
                values.extend(_collect_project_values(val, key_name))
    elif isinstance(node, list):
        for item in node:
            values.extend(_collect_project_values(item, key_hint))
    elif isinstance(node, str) and key_hint in _PROJECT_FIELD_KEYS:
        values.append(node)
    return values


def _normalize_project_name(value: str) -> str:
    return _normalize_text(value)


def _extract_user_questions_from_rpc_payload(rpc_payload: dict) -> tuple[str, str, list[str], str]:
    method_name = str(rpc_payload.get("method") or "")
    params = rpc_payload.get("params")
    if not isinstance(params, dict):
        return method_name, "", [], ""

    tool_name = ""
    user_values: list[str] = []
    context_values: list[str] = []
    query_values: list[str] = []
    project_values: list[str] = []
    if method_name == "tools/call":
        tool_name = str(params.get("name") or "")
        arguments = params.get("arguments")
        parsed_arguments = arguments
        if isinstance(arguments, str):
            text = arguments
            stripped = text.strip()
            parsed_arguments = None
            if stripped:
                try:
                    candidate = json.loads(stripped)
                    if isinstance(candidate, (dict, list)):
                        parsed_arguments = candidate
                    elif isinstance(candidate, str):
                        context_values.append(candidate)
                    else:
                        context_values.append(text)
                except Exception:
                    context_values.append(text)
            else:
                context_values.append(text)
        if parsed_arguments is None:
            parsed_arguments = {}
        for key_name, text in _collect_question_values(parsed_arguments):
            if key_name == "query":
                query_values.append(text)
            else:
                context_values.append(text)
        project_values.extend(_collect_project_values(parsed_arguments))

    messages = params.get("messages")
    if isinstance(messages, list):
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            role = str(msg.get("role") or "").strip().lower()
            if role == "user":
                merged = _join_text_nodes(msg.get("content"))
                if merged:
                    user_values.append(merged)

    if "message" in params:
        merged = _join_text_nodes(params.get("message"))
        if merged:
            user_values.append(merged)
    if "content" in params:
        merged = _join_text_nodes(params.get("content"))
        if merged:
            user_values.append(merged)
    project_values.extend(_collect_project_values(params))

    captured: list[str] = []
    seen: set[str] = set()
    for raw in user_values + context_values + query_values:
        if not isinstance(raw, str):
            continue
        text = raw
        if text == "":
            continue
        if text in seen:
            continue
        seen.add(text)
        captured.append(text)
    project_name = ""
    for raw in project_values:
        project_name = _normalize_project_name(raw)
        if project_name:
            break
    return method_name, tool_name, captured, project_name


def _save_auto_user_question_memory(
    employee_id: str,
    questions: list[str],
    source: str,
    project_name: str = "",
) -> None:
    if not questions:
        return
    normalized_project_name = _normalize_project_name(project_name) or "default"
    existing: set[str] = set()
    try:
        for mem in memory_store.recent(employee_id, 10):
            existing.add(
                f"{_normalize_project_name(str(getattr(mem, 'project_name', '')))}|"
                f"{str(getattr(mem, 'content', ''))}"
            )
    except Exception:
        existing = set()

    normalized_questions: list[str] = []
    for question in questions:
        if not isinstance(question, str) or question == "":
            continue
        if question in normalized_questions:
            continue
        normalized_questions.append(question)
    if not normalized_questions:
        return

    primary_question = normalized_questions[0]
    primary_norm = _normalize_text(primary_question).lower()
    auxiliary_queries: list[str] = []
    for question in normalized_questions[1:]:
        question_norm = _normalize_text(question).lower()
        if question_norm == "":
            continue
        # query 作为辅助信息记录；若只是主问题的子串，跳过避免噪声。
        if primary_norm and question_norm in primary_norm:
            continue
        if question in auxiliary_queries:
            continue
        auxiliary_queries.append(question)

    content = f"[用户提问] {primary_question}"
    if auxiliary_queries:
        content = f"{content}\n[辅助query] {' | '.join(auxiliary_queries)}"
    content_key = f"{normalized_project_name}|{content}"
    if content_key in existing:
        return
    try:
        memory_store.save(
            Memory(
                id=memory_store.new_id(),
                employee_id=employee_id,
                type=MemoryType.PROJECT_CONTEXT,
                content=content,
                project_name=normalized_project_name,
                importance=0.55,
                scope=MemoryScope.EMPLOYEE_PRIVATE,
                classification=Classification.INTERNAL,
                purpose_tags=("auto-capture", "user-question", source),
            )
        )
    except Exception:
        return


def _skill_package_path(skill) -> Path | None:
    package_dir = str(getattr(skill, "package_dir", "") or "").strip()
    if not package_dir:
        return None
    path = Path(package_dir)
    if not path.is_absolute():
        path = (_PROJECT_ROOT / path).resolve()
    else:
        path = path.resolve()
    if not path.exists() or not path.is_dir():
        return None
    return path


def _discover_skill_proxy_specs(skill) -> list[dict]:
    package_path = _skill_package_path(skill)
    if package_path is None:
        return []
    specs: list[dict] = []
    for base_dir in ("tools", "scripts"):
        root = package_path / base_dir
        if not root.exists():
            continue
        for file in sorted(root.rglob("*")):
            if not file.is_file() or file.suffix.lower() not in _EXECUTABLE_SUFFIXES:
                continue
            rel_name = file.relative_to(root).with_suffix("").as_posix().replace("/", "-")
            specs.append(
                {
                    "skill_id": skill.id,
                    "skill_name": skill.name,
                    "entry_name": rel_name,
                    "script_path": str(file),
                    "script_type": file.suffix.lower().lstrip("."),
                    "description": f"Proxy tool for {skill.id}:{rel_name}",
                }
            )
    return specs


def _active_project_member_employees(project_id: str) -> list[tuple[object, object]]:
    project = project_store.get(project_id)
    if not project:
        return []
    members = []
    for member in project_store.list_members(project_id):
        if not bool(getattr(member, "enabled", True)):
            continue
        employee = employee_store.get(member.employee_id)
        if not employee:
            continue
        members.append((member, employee))
    return members


def _list_visible_external_mcp_modules(project_id: str) -> list[object]:
    visible: list[object] = []
    project_id_value = str(project_id or "").strip()
    for module in external_mcp_store.list_all():
        if not bool(getattr(module, "enabled", True)):
            continue
        module_project_id = str(getattr(module, "project_id", "") or "").strip()
        if module_project_id and module_project_id != project_id_value:
            continue
        visible.append(module)
    return visible


def _external_mcp_signature(module: object) -> tuple:
    return (
        str(getattr(module, "updated_at", "") or ""),
        str(getattr(module, "endpoint_http", "") or ""),
        str(getattr(module, "endpoint_sse", "") or ""),
        str(getattr(module, "project_id", "") or ""),
        bool(getattr(module, "enabled", True)),
    )


def _external_mcp_candidate_endpoints(module: object) -> list[tuple[str, str]]:
    endpoints: list[tuple[str, str]] = []
    endpoint_http = str(getattr(module, "endpoint_http", "") or "").strip()
    endpoint_sse = str(getattr(module, "endpoint_sse", "") or "").strip()
    if endpoint_http:
        endpoints.append(("http", endpoint_http))
    if endpoint_sse:
        endpoints.append(("sse", endpoint_sse))
    return endpoints


def _external_mcp_request(url: str, method: str, params: dict | None = None, timeout_sec: int = 15) -> dict:
    payload = {
        "jsonrpc": "2.0",
        "id": f"ext-{secrets.token_hex(4)}",
        "method": method,
    }
    if params is not None:
        payload["params"] = params
    response = requests.post(
        url,
        json=payload,
        headers={
            "Accept": "application/json, text/event-stream;q=0.9, */*;q=0.8",
            "Content-Type": "application/json",
        },
        timeout=(3, timeout_sec),
    )
    status_code = int(response.status_code)
    if status_code >= 400:
        raise RuntimeError(f"HTTP {status_code}: {response.text[:300]}")
    try:
        data = response.json()
    except Exception as exc:
        raise RuntimeError(f"Invalid JSON response: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("Invalid JSON-RPC response body")
    if data.get("error"):
        error = data.get("error")
        if isinstance(error, dict):
            raise RuntimeError(str(error.get("message") or error))
        raise RuntimeError(str(error))
    return data


def _normalize_parameters_schema(schema: object) -> dict:
    if isinstance(schema, dict) and str(schema.get("type") or "").strip():
        return schema
    if isinstance(schema, dict):
        normalized = dict(schema)
        normalized.setdefault("type", "object")
        normalized.setdefault("properties", {})
        return normalized
    return {"type": "object", "properties": {}}


def _extract_external_mcp_tools_payload(module: object, timeout_sec: int = 15) -> list[dict]:
    errors: list[str] = []
    module_name = str(getattr(module, "name", "") or getattr(module, "id", "") or "external")
    module_id = str(getattr(module, "id", "") or "")
    for transport, endpoint in _external_mcp_candidate_endpoints(module):
        try:
            payload = _external_mcp_request(endpoint, "tools/list", {}, timeout_sec=timeout_sec)
            result = payload.get("result")
            tools = result.get("tools") if isinstance(result, dict) else None
            if not isinstance(tools, list):
                raise RuntimeError("tools/list missing tools array")
            items: list[dict] = []
            for tool in tools:
                if not isinstance(tool, dict):
                    continue
                remote_name = str(tool.get("name") or "").strip()
                if not remote_name:
                    continue
                tool_name = f"external__{_tool_token(module_id or module_name)}__{_tool_token(remote_name)}"
                items.append(
                    {
                        "tool_name": tool_name,
                        "remote_tool_name": remote_name,
                        "module_id": module_id,
                        "module_name": module_name,
                        "employee_id": "",
                        "base_tool_name": remote_name,
                        "scoped_tool_name": tool_name,
                        "entry_name": remote_name,
                        "script_type": f"external_{transport}",
                        "description": f"外部 MCP[{module_name}]：{str(tool.get('description') or remote_name)}",
                        "parameters_schema": _normalize_parameters_schema(tool.get("inputSchema") or tool.get("parameters")),
                        "module_type": "external_mcp_tool",
                        "builtin": False,
                    }
                )
            return items
        except Exception as exc:
            errors.append(f"{transport}:{exc}")
    if errors:
        return [
            {
                "tool_name": f"external__{_tool_token(module_id or module_name)}__unavailable",
                "remote_tool_name": "",
                "module_id": module_id,
                "module_name": module_name,
                "employee_id": "",
                "base_tool_name": "",
                "scoped_tool_name": "",
                "entry_name": "",
                "script_type": "external_error",
                "description": f"外部 MCP[{module_name}] 暂不可用：{' | '.join(errors)}",
                "parameters_schema": {"type": "object", "properties": {}},
                "module_type": "external_mcp_tool",
                "builtin": False,
                "disabled": True,
            }
        ]
    return []


def list_project_external_tools_runtime(project_id: str) -> list[dict]:
    tools: list[dict] = []
    for module in _list_visible_external_mcp_modules(project_id):
        module_id = str(getattr(module, "id", "") or "")
        signature = _external_mcp_signature(module)
        cached = _external_mcp_tool_cache.get(module_id)
        if cached is None or _external_mcp_tool_signatures.get(module_id) != signature:
            cached = _extract_external_mcp_tools_payload(module)
            _external_mcp_tool_cache[module_id] = cached
            _external_mcp_tool_signatures[module_id] = signature
        tools.extend(item for item in cached if not bool(item.get("disabled")))
    return tools


def _resolve_external_tool_spec(project_id: str, tool_name: str) -> tuple[dict | None, str]:
    normalized_tool_name = str(tool_name or "").strip()
    if not normalized_tool_name:
        return None, "tool_name is required"
    for item in list_project_external_tools_runtime(project_id):
        if str(item.get("tool_name") or "").strip() == normalized_tool_name:
            return item, ""
    return None, f"External tool not found: {normalized_tool_name}"


def invoke_external_mcp_tool_runtime(
    project_id: str,
    tool_name: str,
    args: dict | None = None,
    args_json: str = "{}",
    timeout_sec: int = 30,
) -> dict:
    spec, err = _resolve_external_tool_spec(project_id, tool_name)
    if spec is None:
        return {"error": err}

    if args is not None:
        if not isinstance(args, dict):
            return {"error": "args must be an object"}
        payload = args
    else:
        try:
            payload = json.loads(args_json or "{}")
        except Exception as exc:
            return {"error": f"Invalid args_json: {exc}"}
        if not isinstance(payload, dict):
            return {"error": "args_json must be a JSON object"}

    try:
        timeout_value = max(3, min(int(timeout_sec), 120))
    except (TypeError, ValueError):
        timeout_value = 30

    module_id = str(spec.get("module_id") or "")
    module = external_mcp_store.get(module_id) if module_id else None
    if module is None:
        return {"error": f"External MCP module {module_id or '-'} not found"}

    errors: list[str] = []
    for _transport, endpoint in _external_mcp_candidate_endpoints(module):
        try:
            rpc_payload = _external_mcp_request(
                endpoint,
                "tools/call",
                {
                    "name": str(spec.get("remote_tool_name") or tool_name),
                    "arguments": payload,
                },
                timeout_sec=timeout_value,
            )
            result = rpc_payload.get("result")
            if isinstance(result, dict) and bool(result.get("isError")):
                return {
                    "error": _join_text_nodes(result.get("content")) or str(result),
                    "tool_name": tool_name,
                    "module_id": module_id,
                    "module_name": str(spec.get("module_name") or ""),
                    "remote_tool_name": str(spec.get("remote_tool_name") or tool_name),
                }
            response = {
                "tool_name": tool_name,
                "module_id": module_id,
                "module_name": str(spec.get("module_name") or ""),
                "remote_tool_name": str(spec.get("remote_tool_name") or tool_name),
                "result": result,
            }
            if isinstance(result, dict):
                text = _join_text_nodes(result.get("content"))
                if text:
                    response["text"] = text
            return response
        except Exception as exc:
            errors.append(str(exc))
    return {"error": f"External MCP call failed: {' | '.join(errors)}"}


def invoke_project_tool_runtime(
    project_id: str,
    tool_name: str,
    employee_id: str = "",
    args: dict | None = None,
    args_json: str = "{}",
    timeout_sec: int = 30,
) -> dict:
    spec, _ = _resolve_external_tool_spec(project_id, tool_name)
    if spec is not None:
        return invoke_external_mcp_tool_runtime(
            project_id=project_id,
            tool_name=tool_name,
            args=args,
            args_json=args_json,
            timeout_sec=timeout_sec,
        )
    return invoke_project_skill_tool_runtime(
        project_id=project_id,
        tool_name=tool_name,
        employee_id=employee_id,
        args=args,
        args_json=args_json,
        timeout_sec=timeout_sec,
    )


def _build_project_proxy_specs(project_id: str) -> tuple[dict[str, dict], dict[str, dict[str, dict]]]:
    by_scoped_name: dict[str, dict] = {}
    by_employee_base_name: dict[str, dict[str, dict]] = {}
    for _member, employee in _active_project_member_employees(project_id):
        name_counter: dict[str, int] = {}
        employee_map = by_employee_base_name.setdefault(employee.id, {})
        for skill_id in employee.skills or []:
            skill = skill_store.get(skill_id)
            if not skill:
                continue
            for spec in _discover_skill_proxy_specs(skill):
                base_name = f"{_tool_token(skill.id)}__{_tool_token(spec['entry_name'])}"
                idx = name_counter.get(base_name, 0) + 1
                name_counter[base_name] = idx
                base_key = base_name if idx == 1 else f"{base_name}_{idx}"
                scoped_name = f"{_tool_token(employee.id)}__{base_key}"
                wrapped = {
                    **spec,
                    "employee_id": employee.id,
                    "base_tool_name": base_key,
                    "scoped_tool_name": scoped_name,
                }
                by_scoped_name[scoped_name] = wrapped
                employee_map[base_key] = wrapped
    return by_scoped_name, by_employee_base_name


def _resolve_project_proxy_tool_spec(
    project_id: str,
    tool_name: str,
    employee_id: str = "",
) -> tuple[dict | None, str]:
    scoped_proxy_specs, employee_proxy_specs = _build_project_proxy_specs(project_id)
    normalized_tool_name = str(tool_name or "").strip()
    employee_id_value = str(employee_id or "").strip()
    if not normalized_tool_name:
        return None, "tool_name is required"

    if employee_id_value:
        employee_specs = employee_proxy_specs.get(employee_id_value, {})
        if normalized_tool_name in employee_specs:
            return employee_specs[normalized_tool_name], ""
        scoped_name = f"{_tool_token(employee_id_value)}__{normalized_tool_name}"
        scoped_spec = scoped_proxy_specs.get(scoped_name)
        if scoped_spec:
            return scoped_spec, ""
        return None, f"Tool not found for employee {employee_id_value}: {normalized_tool_name}"

    if normalized_tool_name in scoped_proxy_specs:
        return scoped_proxy_specs[normalized_tool_name], ""

    matched: list[dict] = []
    for specs in employee_proxy_specs.values():
        if normalized_tool_name in specs:
            matched.append(specs[normalized_tool_name])
    if not matched:
        return None, f"Tool not found: {normalized_tool_name}"
    if len(matched) > 1:
        employee_ids = sorted({item["employee_id"] for item in matched})
        return None, f"Ambiguous tool_name, provide employee_id. Candidates: {employee_ids}"
    return matched[0], ""


def list_project_proxy_tools_runtime(project_id: str, employee_id: str = "") -> list[dict]:
    """列出项目技能代理工具，供非 MCP 路径（如聊天路由）复用。"""
    scoped_proxy_specs, employee_proxy_specs = _build_project_proxy_specs(project_id)
    employee_id_value = str(employee_id or "").strip()
    tools: list[dict] = []
    if employee_id_value:
        specs = employee_proxy_specs.get(employee_id_value, {})
        for base_tool_name, spec in sorted(specs.items()):
            tools.append(
                {
                    "tool_name": base_tool_name,
                    "employee_id": spec["employee_id"],
                    "base_tool_name": spec["base_tool_name"],
                    "scoped_tool_name": spec["scoped_tool_name"],
                    "skill_id": spec["skill_id"],
                    "entry_name": spec["entry_name"],
                    "script_type": spec["script_type"],
                    "description": spec["description"],
                }
            )
    else:
        for scoped_tool_name, spec in sorted(scoped_proxy_specs.items()):
            tools.append(
                {
                    "tool_name": scoped_tool_name,
                    "employee_id": spec["employee_id"],
                    "base_tool_name": spec["base_tool_name"],
                    "scoped_tool_name": spec["scoped_tool_name"],
                    "skill_id": spec["skill_id"],
                    "entry_name": spec["entry_name"],
                    "script_type": spec["script_type"],
                    "description": spec["description"],
                }
            )

    existing_names = {str(item.get("tool_name") or "") for item in tools}
    if "query_project_rules" not in existing_names:
        tools.append(
            {
                "tool_name": "query_project_rules",
                "employee_id": employee_id_value,
                "base_tool_name": "query_project_rules",
                "scoped_tool_name": "query_project_rules",
                "skill_id": "__builtin__",
                "entry_name": "query_project_rules",
                "script_type": "builtin",
                "description": "检索项目规则内容，可按 keyword 与 employee_id 过滤。",
                "builtin": True,
                "parameters_schema": {
                    "type": "object",
                    "properties": {
                        "keyword": {
                            "type": "string",
                            "description": "用于检索规则的关键词，如“UI设计”或“数据库设计”。",
                        },
                        "employee_id": {
                            "type": "string",
                            "description": "可选，指定项目成员 employee_id 进行过滤。",
                        },
                    },
                    "required": [],
                },
            }
        )
    if "query_project_members" not in existing_names:
        tools.append(
            {
                "tool_name": "query_project_members",
                "employee_id": employee_id_value,
                "base_tool_name": "query_project_members",
                "scoped_tool_name": "query_project_members",
                "skill_id": "__builtin__",
                "entry_name": "query_project_members",
                "script_type": "builtin",
                "description": "查询项目的成员列表，返回成员的姓名、ID、角色等信息。",
                "builtin": True,
                "parameters_schema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            }
        )
    if "search_project_context" not in existing_names:
        tools.append(
            {
                "tool_name": "search_project_context",
                "employee_id": employee_id_value,
                "base_tool_name": "search_project_context",
                "scoped_tool_name": "search_project_context",
                "skill_id": "__builtin__",
                "entry_name": "search_project_context",
                "script_type": "builtin",
                "description": (
                    "统一检索项目上下文，支持按 scope/keyword/employee_id 查询"
                    "项目信息、成员详情、规则内容、MCP 模块。"
                ),
                "builtin": True,
                "parameters_schema": {
                    "type": "object",
                    "properties": {
                        "scope": {
                            "type": "string",
                            "description": "检索范围：all/project/members/rules/mcp，默认 all。",
                        },
                        "keyword": {
                            "type": "string",
                            "description": "可选，关键词过滤。",
                        },
                        "employee_id": {
                            "type": "string",
                            "description": "可选，按员工 ID 过滤成员与规则。",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "每类结果最大返回条数，默认 20，范围 1-100。",
                        },
                    },
                    "required": [],
                },
            }
        )
    return tools


def query_project_mcp_modules_runtime(project_id: str, keyword: str = "", limit: int = 20) -> dict:
    """查询项目可见 MCP 模块（内置工具）"""
    project = project_store.get(project_id)
    if project is None:
        return {"error": f"项目 {project_id} 不存在"}

    keyword_lower = str(keyword or "").strip().lower()
    try:
        limit_value = int(limit)
    except (TypeError, ValueError):
        limit_value = 20
    limit_value = max(1, min(limit_value, 100))

    def _matches(values: list[str]) -> bool:
        if not keyword_lower:
            return True
        for value in values:
            if keyword_lower in str(value or "").strip().lower():
                return True
        return False

    project_related: list[dict] = []
    for item in list_project_proxy_tools_runtime(project_id, ""):
        tool_name = str(item.get("tool_name") or "").strip()
        if not tool_name:
            continue
        values = [
            tool_name,
            str(item.get("description") or ""),
            str(item.get("skill_id") or ""),
            str(item.get("entry_name") or ""),
        ]
        if not _matches(values):
            continue
        project_related.append(
            {
                "name": tool_name,
                "module_type": "builtin_tool" if bool(item.get("builtin")) else "project_skill_tool",
                "tool_name": tool_name,
                "employee_id": str(item.get("employee_id") or ""),
                "description": str(item.get("description") or ""),
            }
        )
    project_related = project_related[:limit_value]

    system_global: list[dict] = []
    for item in project_store.list_all():
        if not bool(getattr(item, "mcp_enabled", True)):
            continue
        name = str(getattr(item, "name", "") or getattr(item, "id", "") or "")
        values = [name, str(getattr(item, "description", "") or ""), str(getattr(item, "id", "") or ""), "project_mcp_service"]
        if not _matches(values):
            continue
        system_global.append(
            {
                "name": name,
                "module_type": "project_mcp_service",
                "resource_id": str(getattr(item, "id", "") or ""),
            }
        )

    for item in employee_store.list_all():
        if not bool(getattr(item, "mcp_enabled", True)):
            continue
        name = str(getattr(item, "name", "") or getattr(item, "id", "") or "")
        values = [name, str(getattr(item, "description", "") or ""), str(getattr(item, "id", "") or ""), "employee_mcp_service"]
        if not _matches(values):
            continue
        system_global.append(
            {
                "name": name,
                "module_type": "employee_mcp_service",
                "resource_id": str(getattr(item, "id", "") or ""),
            }
        )

    for item in skill_store.list_all():
        if not bool(getattr(item, "mcp_enabled", False)):
            continue
        name = str(getattr(item, "name", "") or getattr(item, "id", "") or "")
        values = [name, str(getattr(item, "description", "") or ""), str(getattr(item, "id", "") or ""), "skill_mcp_service"]
        if not _matches(values):
            continue
        system_global.append(
            {
                "name": name,
                "module_type": "skill_mcp_service",
                "resource_id": str(getattr(item, "id", "") or ""),
            }
        )

    for item in rule_store.list_all():
        if not bool(getattr(item, "mcp_enabled", False)):
            continue
        name = str(getattr(item, "title", "") or getattr(item, "id", "") or "")
        values = [name, str(getattr(item, "content", "") or ""), str(getattr(item, "id", "") or ""), "rule_mcp_service"]
        if not _matches(values):
            continue
        system_global.append(
            {
                "name": name,
                "module_type": "rule_mcp_service",
                "resource_id": str(getattr(item, "id", "") or ""),
            }
        )
    system_global = system_global[:limit_value]

    external_modules: list[dict] = []
    for item in external_mcp_store.list_all():
        if not bool(getattr(item, "enabled", True)):
            continue
        module_project_id = str(getattr(item, "project_id", "") or "").strip()
        if module_project_id and module_project_id != project_id:
            continue
        name = str(getattr(item, "name", "") or getattr(item, "id", "") or "")
        values = [
            name,
            str(getattr(item, "description", "") or ""),
            str(getattr(item, "endpoint_http", "") or ""),
            str(getattr(item, "endpoint_sse", "") or ""),
            "external_mcp_service",
        ]
        if not _matches(values):
            continue
        external_modules.append(
            {
                "name": name,
                "module_type": "external_mcp_service",
                "project_id": module_project_id,
                "endpoint_http": str(getattr(item, "endpoint_http", "") or ""),
                "endpoint_sse": str(getattr(item, "endpoint_sse", "") or ""),
            }
        )
    external_modules = external_modules[:limit_value]

    return {
        "project_id": project_id,
        "project_name": str(getattr(project, "name", "") or ""),
        "system": {
            "project_related": project_related,
            "system_global": system_global,
        },
        "external": {"modules": external_modules},
        "summary": {
            "system_project_related_total": len(project_related),
            "system_global_total": len(system_global),
            "external_total": len(external_modules),
        },
    }


def search_project_context_runtime(
    project_id: str,
    scope: str = "all",
    keyword: str = "",
    employee_id: str = "",
    limit: int = 20,
) -> dict:
    """统一检索项目上下文（内置工具）"""
    project = project_store.get(project_id)
    if project is None:
        return {"error": f"项目 {project_id} 不存在"}

    scope_value = str(scope or "all").strip().lower() or "all"
    if scope_value not in {"all", "project", "members", "rules", "mcp"}:
        return {"error": f"Invalid scope: {scope_value}. Valid: ['all','project','members','rules','mcp']"}

    keyword_value = str(keyword or "").strip()
    keyword_lower = keyword_value.lower()
    employee_id_value = str(employee_id or "").strip()
    try:
        limit_value = int(limit)
    except (TypeError, ValueError):
        limit_value = 20
    limit_value = max(1, min(limit_value, 100))

    def _matches_text(values: list[str]) -> bool:
        if not keyword_lower:
            return True
        for value in values:
            if keyword_lower in str(value or "").strip().lower():
                return True
        return False

    result: dict[str, object] = {
        "project_id": project_id,
        "scope": scope_value,
        "keyword": keyword_value,
        "employee_id": employee_id_value,
    }

    if scope_value in {"all", "project"}:
        result["project"] = {
            "id": project_id,
            "name": str(getattr(project, "name", "") or ""),
            "description": str(getattr(project, "description", "") or ""),
            "workspace_path": str(getattr(project, "workspace_path", "") or ""),
            "mcp_enabled": bool(getattr(project, "mcp_enabled", True)),
            "feedback_upgrade_enabled": bool(getattr(project, "feedback_upgrade_enabled", False)),
        }

    if scope_value in {"all", "members"}:
        profiles = list_project_member_profiles_runtime(
            project_id,
            include_disabled=True,
            include_missing=True,
            rule_limit=50,
        )
        filtered_profiles: list[dict] = []
        for item in profiles:
            item_employee_id = str(item.get("employee_id") or "").strip()
            if employee_id_value and item_employee_id != employee_id_value:
                continue
            rule_bindings = list(item.get("rule_bindings") or [])
            values = [
                item_employee_id,
                str(item.get("name") or ""),
                str(item.get("description") or ""),
                " ".join(str(v or "") for v in (item.get("skill_names") or [])),
                " ".join(str(v.get("title") or v.get("id") or "") for v in rule_bindings),
                " ".join(str(v.get("domain") or "") for v in rule_bindings),
            ]
            if not _matches_text(values):
                continue
            filtered_profiles.append(item)
        result["members"] = filtered_profiles[:limit_value]
        result["members_total"] = len(filtered_profiles)

    if scope_value in {"all", "rules"}:
        rules = query_project_rules_runtime(project_id, keyword=keyword_value, employee_id=employee_id_value)
        result["rules"] = rules[:limit_value]
        result["rules_total"] = len(rules)

    if scope_value in {"all", "mcp"}:
        mcp_modules = query_project_mcp_modules_runtime(project_id, keyword=keyword_value, limit=limit_value)
        result["mcp_modules"] = mcp_modules

    return result


def query_project_rules_runtime(project_id: str, keyword: str = "", employee_id: str = "") -> list[dict]:
    """查询项目规则（内置工具）"""
    project = project_store.get(project_id)
    if project is None:
        return []
    keyword_value = str(keyword or "").strip()
    keyword_lower = keyword_value.lower()
    employee_id_value = str(employee_id or "").strip()
    selected_employees = []
    for member in project_store.list_members(project_id):
        member_employee_id = str(getattr(member, "employee_id", "") or "").strip()
        if not member_employee_id:
            continue
        if employee_id_value and member_employee_id != employee_id_value:
            continue
        employee = employee_store.get(member_employee_id)
        if employee is None:
            continue
        selected_employees.append(employee)

    results: list[dict] = []
    seen_rule_ids: set[str] = set()
    for employee in selected_employees:
        for rule in _query_rules_by_employee(employee, keyword_value):
            rid = str(getattr(rule, "id", "") or "").strip()
            if rid and rid in seen_rule_ids:
                continue
            if rid:
                seen_rule_ids.add(rid)
            results.append(serialize_rule(rule))

    if results:
        return results

    if employee_id_value:
        return []

    # 兜底：当项目成员未绑定规则时，按关键词检索全局规则库，避免空返回。
    fallback_rules = (
        rule_store.query(keyword_value)
        if keyword_value and hasattr(rule_store, "query")
        else rule_store.list_all()
    )
    for rule in fallback_rules:
        title_lower = str(getattr(rule, "title", "") or "").lower()
        content_lower = str(getattr(rule, "content", "") or "").lower()
        if keyword_lower and keyword_lower not in title_lower and keyword_lower not in content_lower:
            continue
        rid = str(getattr(rule, "id", "") or "").strip()
        if rid and rid in seen_rule_ids:
            continue
        if rid:
            seen_rule_ids.add(rid)
        results.append(serialize_rule(rule))
    return results


def query_project_members_runtime(project_id: str) -> dict:
    """查询项目成员列表（内置工具）"""
    project = project_store.get(project_id)
    if project is None:
        return {"error": f"项目 {project_id} 不存在"}
    members = list_project_member_profiles_runtime(
        project_id,
        include_disabled=True,
        include_missing=True,
        rule_limit=20,
    )
    return {"project_id": project_id, "project_name": project.name, "members": members, "total": len(members)}


def invoke_project_skill_tool_runtime(
    project_id: str,
    tool_name: str,
    employee_id: str = "",
    args: dict | None = None,
    args_json: str = "{}",
    timeout_sec: int = 30,
) -> dict:
    """执行项目成员技能脚本，供非 MCP 路径（如聊天路由）复用。"""
    normalized_tool_name = str(tool_name or "").strip()
    employee_id_value = str(employee_id or "").strip()

    if normalized_tool_name == "query_project_rules":
        payload: dict = {}
        if args is not None:
            if not isinstance(args, dict):
                return {"error": "args must be an object"}
            payload = args
        else:
            try:
                payload = json.loads(args_json or "{}")
            except Exception as exc:
                return {"error": f"Invalid args_json: {exc}"}
            if not isinstance(payload, dict):
                return {"error": "args_json must be a JSON object"}
        keyword = str(payload.get("keyword") or "").strip()
        target_employee_id = str(payload.get("employee_id") or employee_id_value).strip()
        result = query_project_rules_runtime(
            project_id=project_id,
            keyword=keyword,
            employee_id=target_employee_id,
        )
        return {
            "tool_name": "query_project_rules",
            "employee_id": target_employee_id,
            "result": result,
            "total": len(result),
        }

    if normalized_tool_name == "query_project_members":
        result = query_project_members_runtime(project_id)
        if isinstance(result, dict):
            return {
                "tool_name": "query_project_members",
                "employee_id": employee_id_value,
                **result,
            }
        return {
            "tool_name": "query_project_members",
            "employee_id": employee_id_value,
            "result": result,
        }

    if normalized_tool_name == "search_project_context":
        payload: dict = {}
        if args is not None:
            if not isinstance(args, dict):
                return {"error": "args must be an object"}
            payload = args
        else:
            try:
                payload = json.loads(args_json or "{}")
            except Exception as exc:
                return {"error": f"Invalid args_json: {exc}"}
            if not isinstance(payload, dict):
                return {"error": "args_json must be a JSON object"}
        scope_value = str(payload.get("scope") or "all").strip()
        keyword_value = str(payload.get("keyword") or "").strip()
        target_employee_id = str(payload.get("employee_id") or employee_id_value).strip()
        limit_value = payload.get("limit", 20)
        result = search_project_context_runtime(
            project_id=project_id,
            scope=scope_value,
            keyword=keyword_value,
            employee_id=target_employee_id,
            limit=limit_value,
        )
        return {
            "tool_name": "search_project_context",
            "employee_id": target_employee_id,
            **result,
        }

    spec, err = _resolve_project_proxy_tool_spec(project_id, tool_name, employee_id)
    if spec is None:
        return {"error": err}
    result = _execute_skill_proxy(
        spec,
        args=args,
        args_json=args_json,
        timeout_sec=timeout_sec,
        employee_id=spec["employee_id"],
    )
    if isinstance(result, dict):
        return {
            "tool_name": str(spec.get("base_tool_name") or tool_name),
            "employee_id": str(spec.get("employee_id") or employee_id),
            **result,
        }
    return {"result": result}


def _build_cli_args(payload: dict) -> list[str]:
    argv: list[str] = []
    for key, value in payload.items():
        name = str(key or "").strip()
        if not name:
            continue
        flag = f"--{name.replace('_', '-')}"
        if isinstance(value, bool):
            if value:
                argv.append(flag)
            continue
        if value is None:
            continue
        if isinstance(value, list):
            for item in value:
                argv.extend((flag, str(item)))
            continue
        argv.extend((flag, str(value)))
    return argv


def _execute_skill_proxy(
    spec: dict,
    args: dict | None = None,
    args_json: str | None = None,
    timeout_sec: int = 30,
    employee_id: str | None = None,
) -> dict:
    script_path = Path(spec["script_path"]).resolve()
    if not script_path.exists():
        return {"error": f"Script not found: {script_path}"}

    if args is not None:
        if not isinstance(args, dict):
            return {"error": "args must be an object"}
        payload = args
    else:
        try:
            payload = json.loads(args_json or "{}")
        except Exception as exc:
            return {"error": f"Invalid args_json: {exc}"}
        if not isinstance(payload, dict):
            return {"error": "args_json must be a JSON object"}

    try:
        timeout = int(timeout_sec)
    except (TypeError, ValueError):
        timeout = 30
    timeout = max(1, min(timeout, 600))
    if spec["script_type"] == "py":
        cmd = [sys.executable, str(script_path)]
    elif spec["script_type"] == "js":
        cmd = ["node", str(script_path)]
    else:
        return {"error": f"Unsupported script type: {spec['script_type']}"}

    cmd.extend(_build_cli_args(payload))
    if employee_id:
        cmd.extend(["--employee-id", employee_id])
    current_key = _current_api_key.get("")
    if current_key:
        cmd.extend(["--api-key", current_key])
    try:
        result = subprocess.run(
            cmd,
            cwd=str(_PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        return {"error": str(exc), "command": cmd}
    except subprocess.TimeoutExpired:
        return {
            "error": "Skill execution timed out",
            "timeout_sec": timeout,
            "command": cmd,
        }

    return {
        "status": "ok" if result.returncode == 0 else "error",
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "command": cmd,
    }


def _new_mcp(service_name: str) -> FastMCP:
    """Use non-localhost host to avoid FastMCP localhost-only host header checks on LAN access."""
    # Stateless HTTP avoids session-id coupling for clients that POST directly to /sse (bridged to /mcp).
    return FastMCP(service_name, host=_FASTMCP_HOST, stateless_http=True)

def _create_rule_mcp(rule_id: str):
    r = rule_store.get(rule_id)
    service_name = getattr(r, "mcp_service", "") or rule_id
    mcp = _new_mcp(service_name)

    @mcp.resource(f"rule://{rule_id}")
    def get_this_rule() -> str:
        """获取本规则的详细内容和约束"""
        rule = rule_store.get(rule_id)
        if not rule or not rule.mcp_enabled:
            return "Rule disabled or deleted."
        return f"[{rule.id}] {rule.title}\nSeverity: {rule.severity.value}\nContent:\n{rule.content}"

    @mcp.tool()
    def get_rule_info() -> dict:
        """获取本规则的元信息"""
        rule = rule_store.get(rule_id)
        if not rule or not rule.mcp_enabled:
            return {"error": "Rule not available"}
        return {"id": rule.id, "title": rule.title, "domain": rule.domain}

    # 该 app 已经被挂载在 /mcp/rules/{rule_id}，这里不要再传 mount_path，
    # 否则 endpoint 事件会把路径重复拼接成 /mcp/.../mcp/.../messages。
    return _DualTransportMcpApp(
        _apply_mcp_arguments_compat(mcp.sse_app()),
        mcp.streamable_http_app(),
    )


def _create_skill_mcp(skill_id: str):
    s = skill_store.get(skill_id)
    service_name = getattr(s, "mcp_service", "") or skill_id
    mcp = _new_mcp(service_name)

    @mcp.resource(f"skill://{skill_id}/info")
    def get_skill_info() -> str:
        s = skill_store.get(skill_id)
        if not s or not s.mcp_enabled:
            return "Skill disabled or deleted."
        return f"[{s.id}] {s.name}\nDescription: {s.description}"

    @mcp.tool()
    def get_skill_tools() -> list[dict]:
        """获取本技能包含的所有底层工具"""
        s = skill_store.get(skill_id)
        if not s or not s.mcp_enabled:
            return []
        return [{"name": t.name, "description": t.description} for t in s.tools]
        
    # 同上：由外层 app.mount 提供前缀，避免 messages 路径重复。
    return _DualTransportMcpApp(
        _apply_mcp_arguments_compat(mcp.sse_app()),
        mcp.streamable_http_app(),
    )


def _create_employee_mcp(employee_id: str):
    mcp = _new_mcp(f"employee-{employee_id}")
    proxy_specs_by_name: dict[str, dict] = {}
    employee = employee_store.get(employee_id)
    if employee:
        name_counter: dict[str, int] = {}
        for skill_id in employee.skills or []:
            skill = skill_store.get(skill_id)
            if not skill:
                continue
            for spec in _discover_skill_proxy_specs(skill):
                base_name = f"{_tool_token(skill.id)}__{_tool_token(spec['entry_name'])}"
                idx = name_counter.get(base_name, 0) + 1
                name_counter[base_name] = idx
                tool_name = base_name if idx == 1 else f"{base_name}_{idx}"
                spec["tool_name"] = tool_name
                proxy_specs_by_name[tool_name] = spec

    def _get_employee():
        return employee_store.get(employee_id)

    def _get_feedback_actor() -> str:
        actor = _current_developer_name.get("").strip()
        return actor or "unknown"

    feedback_enabled = bool(getattr(employee, "feedback_upgrade_enabled", False)) if employee else False

    @mcp.resource(f"employee://{employee_id}/system-policy")
    def system_policy() -> str:
        """底层安全策略（不可修改，重启生效）"""
        return _SYSTEM_POLICY or "No system policy configured."

    @mcp.resource(f"employee://{employee_id}/profile")
    def employee_profile() -> str:
        employee = _get_employee()
        if not employee:
            return "Employee deleted or unavailable."
        style = " / ".join(employee.style_hints or []) or "none"
        return (
            f"[{employee.id}] {employee.name}\n"
            f"description: {employee.description or '-'}\n"
            f"tone={employee.tone} verbosity={employee.verbosity} language={employee.language}\n"
            f"memory_scope={employee.memory_scope} retention_days={employee.memory_retention_days}\n"
            f"auto_evolve={employee.auto_evolve} evolve_threshold={employee.evolve_threshold}\n"
            f"style_hints: {style}"
        )

    @mcp.resource(f"employee://{employee_id}/skills")
    def employee_skills() -> str:
        employee = _get_employee()
        if not employee:
            return "Employee deleted or unavailable."
        if not employee.skills:
            return "No bound skills."
        lines = []
        for skill_id in employee.skills:
            skill = skill_store.get(skill_id)
            if skill is None:
                lines.append(f"- {skill_id}: missing")
                continue
            lines.append(f"- {skill.id}: {skill.name} ({len(skill.tools)} tools)")
        return "\n".join(lines)

    @mcp.resource(f"employee://{employee_id}/rules")
    def employee_rules() -> str:
        employee = _get_employee()
        if not employee:
            return "Employee deleted or unavailable."
        rules = _query_rules_by_employee(employee)
        if not rules:
            return "No matched rules for current employee domains."
        lines = [
            f"- [{rule.id}] ({rule.domain}) {rule.title} "
            f"| severity={rule.severity.value} risk={rule.risk_domain.value}"
            for rule in rules
        ]
        return "\n".join(lines)

    @mcp.resource(f"employee://{employee_id}/proxy-tools")
    def employee_proxy_tools() -> str:
        employee = _get_employee()
        if not employee:
            return "Employee deleted or unavailable."
        if not proxy_specs_by_name:
            return "No executable skill tools discovered."
        lines = []
        for tool_name, spec in sorted(proxy_specs_by_name.items()):
            lines.append(
                f"- {tool_name}: {spec['skill_id']} / {spec['entry_name']} ({spec['script_type']})"
            )
        return "\n".join(lines)

    @mcp.tool()
    def get_employee_profile() -> dict:
        """获取员工画像与行为配置"""
        employee = _get_employee()
        if not employee:
            return {"error": "Employee not found"}
        payload = asdict(employee)
        payload.pop("rule_ids", None)
        payload.pop("rule_domains", None)
        payload["rule_bindings"] = _employee_rule_summary(employee, limit=200)
        return payload

    @mcp.tool()
    def list_employee_skills() -> list[dict]:
        """列出员工绑定技能详情"""
        employee = _get_employee()
        if not employee:
            return []
        results = []
        for skill_id in employee.skills:
            skill = skill_store.get(skill_id)
            if skill is None:
                results.append({"id": skill_id, "error": "Skill not found"})
                continue
            results.append(serialize_skill(skill))
        return results

    @mcp.tool()
    def query_employee_rules(keyword: str = "") -> list[dict]:
        """按员工绑定领域检索规则，可选关键词过滤"""
        employee = _get_employee()
        if not employee:
            return []
        rules = _query_rules_by_employee(employee, keyword)
        return [serialize_rule(rule) for rule in rules]

    @mcp.tool()
    def recall_employee_memory(query: str = "", project_name: str = "") -> list[dict]:
        """检索员工记忆（支持项目隔离）

        Args:
            query: 检索关键词（为空则返回最近记忆）
            project_name: 项目名称（为空则自动读取 .mcp-project.json）
        """
        employee = _get_employee()
        if not employee:
            return []
        query = str(query or "").strip()

        # 自动读取项目配置
        if not project_name:
            project_config = _load_project_config()
            project_name = project_config.get("project_name") or "default"
        project_name = str(project_name).strip()

        if query:
            memories = memory_store.recall(employee.id, query, _RECALL_EMPLOYEE_MEMORY_LIMIT)
        else:
            memories = memory_store.recent(employee.id, _RECALL_EMPLOYEE_MEMORY_LIMIT)

        # 按 project_name 过滤记忆
        filtered = [m for m in memories if getattr(m, "project_name", "") == project_name]
        return [serialize_memory(mem) for mem in filtered]

    @mcp.tool()
    def get_employee_runtime_context() -> dict:
        """返回员工运行时上下文摘要（技能、规则、记忆统计）"""
        employee = _get_employee()
        if not employee:
            return {"error": "Employee not found"}
        rule_bindings = _employee_rule_summary(employee, limit=200)
        return {
            "employee_id": employee.id,
            "name": employee.name,
            "tone": employee.tone,
            "verbosity": employee.verbosity,
            "language": employee.language,
            "style_hints": list(employee.style_hints or []),
            "skills": list(employee.skills or []),
            "proxy_tools": sorted(proxy_specs_by_name.keys()),
            "rule_bindings": rule_bindings,
            "rule_count": len(rule_bindings),
            "memory_count": memory_store.count(employee.id),
            "auto_evolve": employee.auto_evolve,
            "evolve_threshold": employee.evolve_threshold,
        }

    @mcp.tool()
    def list_employee_proxy_tools() -> list[dict]:
        """列出该员工可直接调用的技能代理工具"""
        tools = []
        for tool_name, spec in sorted(proxy_specs_by_name.items()):
            tools.append(
                {
                    "tool_name": tool_name,
                    "skill_id": spec["skill_id"],
                    "entry_name": spec["entry_name"],
                    "script_type": spec["script_type"],
                    "description": spec["description"],
                }
            )
        return tools

    if feedback_enabled:
        @mcp.tool()
        def submit_feedback_bug(
            title: str,
            symptom: str,
            expected: str,
            project_name: str = "",
            category: str = "general",
            severity: str = "medium",
            session_id: str = "",
            rule_id: str = "",
            source_context: dict | None = None,
        ) -> dict:
            """提交当前员工的结构化反馈工单（支持项目隔离）

            Args:
                project_name: 项目名称（为空则自动读取 .mcp-project.json）
            """
            employee = _get_employee()
            if not employee:
                return {"error": "Employee not found"}

            # 自动读取项目配置
            if not project_name:
                project_config = _load_project_config()
                project_name = project_config.get("project_name") or "default"

            try:
                bug = get_feedback_service().create_bug(
                    project_id=project_name,
                    payload={
                        "employee_id": employee_id,
                        "title": title,
                        "symptom": symptom,
                        "expected": expected,
                        "category": category,
                        "severity": severity,
                        "session_id": session_id,
                        "rule_id": rule_id,
                        "source_context": source_context or {},
                    },
                    actor=_get_feedback_actor(),
                )
                return {"status": "created", "bug": bug}
            except (ValueError, RuntimeError) as exc:
                return {"error": str(exc)}

        @mcp.tool()
        def list_feedback_bugs(
            project_id: str = "default",
            status: str = "",
            severity: str = "",
            limit: int = 20,
        ) -> list[dict]:
            """查询当前员工在项目内的反馈工单列表"""
            employee = _get_employee()
            if not employee:
                return []
            try:
                return get_feedback_service().list_bugs(
                    project_id=project_id,
                    employee_id=employee_id,
                    status=status,
                    severity=severity,
                    limit=limit,
                )
            except (ValueError, RuntimeError):
                return []

        @mcp.tool()
        def get_feedback_bug_detail(feedback_id: str, project_id: str = "default") -> dict:
            """查看单条反馈的详情（含反思、候选、审核日志）"""
            employee = _get_employee()
            if not employee:
                return {"error": "Employee not found"}
            try:
                detail = get_feedback_service().get_bug_detail(
                    project_id,
                    feedback_id,
                    employee_id=employee_id,
                )
            except LookupError as exc:
                return {"error": str(exc)}
            except RuntimeError as exc:
                return {"error": str(exc)}
            bug = detail.get("bug") or {}
            if bug.get("employee_id") != employee_id:
                return {"error": f"Feedback {feedback_id} does not belong to employee {employee_id}"}
            return detail

        @mcp.tool()
        def analyze_feedback_bug(feedback_id: str, project_id: str = "default") -> dict:
            """触发反馈反思并生成规则升级候选"""
            employee = _get_employee()
            if not employee:
                return {"error": "Employee not found"}
            detail = get_feedback_bug_detail(feedback_id=feedback_id, project_id=project_id)
            if detail.get("error"):
                return detail
            try:
                result = get_feedback_service().analyze_bug(
                    project_id,
                    feedback_id,
                    employee_id=employee_id,
                )
                return {"status": "analyzed", **result}
            except ValueError as exc:
                return {"error": str(exc)}
            except LookupError as exc:
                return {"error": str(exc)}
            except RuntimeError as exc:
                return {"error": str(exc)}

        @mcp.tool()
        def list_feedback_candidates(
            project_id: str = "default",
            status: str = "pending",
            limit: int = 20,
        ) -> list[dict]:
            """查询当前员工在项目内的反馈候选规则"""
            employee = _get_employee()
            if not employee:
                return []
            try:
                return get_feedback_service().list_candidates(
                    project_id=project_id,
                    status=status,
                    employee_id=employee_id,
                    limit=limit,
                )
            except (ValueError, RuntimeError):
                return []

        def _find_candidate_in_employee_scope(project_id: str, candidate_id: str) -> dict:
            candidates = get_feedback_service().list_candidates(
                project_id=project_id,
                status="",
                employee_id=employee_id,
                limit=200,
            )
            for candidate in candidates:
                if candidate.get("id") == candidate_id:
                    return candidate
            return {}

        @mcp.tool()
        def review_feedback_candidate(
            candidate_id: str,
            action: str,
            project_id: str = "default",
            comment: str = "",
            edited_content: str = "",
            edited_executable_content: str = "",
        ) -> dict:
            """审核反馈候选（approve/edit/reject）"""
            employee = _get_employee()
            if not employee:
                return {"error": "Employee not found"}
            candidate = _find_candidate_in_employee_scope(project_id, candidate_id)
            if not candidate:
                return {"error": f"Candidate {candidate_id} not found for employee {employee_id}"}
            try:
                updated = get_feedback_service().review_candidate(
                    project_id=project_id,
                    candidate_id=candidate_id,
                    reviewed_by=_get_feedback_actor(),
                    action=action,
                    comment=comment,
                    edited_content=edited_content,
                    edited_executable_content=edited_executable_content,
                    employee_id=employee_id,
                )
                return {"status": updated.get("status", ""), "candidate": updated}
            except (ValueError, LookupError, RuntimeError) as exc:
                return {"error": str(exc)}

        @mcp.tool()
        def publish_feedback_candidate(
            candidate_id: str,
            project_id: str = "default",
            comment: str = "",
        ) -> dict:
            """发布已审核通过的反馈候选到规则库"""
            employee = _get_employee()
            if not employee:
                return {"error": "Employee not found"}
            candidate = _find_candidate_in_employee_scope(project_id, candidate_id)
            if not candidate:
                return {"error": f"Candidate {candidate_id} not found for employee {employee_id}"}
            try:
                updated = get_feedback_service().publish_candidate(
                    project_id=project_id,
                    candidate_id=candidate_id,
                    published_by=_get_feedback_actor(),
                    comment=comment,
                    employee_id=employee_id,
                )
                return {"status": "published", "candidate": updated}
            except (ValueError, LookupError, RuntimeError) as exc:
                return {"error": str(exc)}

        @mcp.tool()
        def rollback_feedback_candidate(
            candidate_id: str,
            project_id: str = "default",
            comment: str = "",
        ) -> dict:
            """回滚已发布的反馈候选规则版本"""
            employee = _get_employee()
            if not employee:
                return {"error": "Employee not found"}
            candidate = _find_candidate_in_employee_scope(project_id, candidate_id)
            if not candidate:
                return {"error": f"Candidate {candidate_id} not found for employee {employee_id}"}
            try:
                updated = get_feedback_service().rollback_candidate(
                    project_id=project_id,
                    candidate_id=candidate_id,
                    rolled_back_by=_get_feedback_actor(),
                    comment=comment,
                    employee_id=employee_id,
                )
                return {"status": "rolled_back", "candidate": updated}
            except (ValueError, LookupError, RuntimeError) as exc:
                return {"error": str(exc)}

    @mcp.tool()
    def invoke_employee_skill_tool(
        tool_name: str,
        args: dict | None = None,
        args_json: str = "{}",
        timeout_sec: int = 30,
    ) -> dict:
        """按工具名调用员工绑定技能脚本（参数使用 JSON 对象）"""
        spec = proxy_specs_by_name.get(str(tool_name or "").strip())
        if spec is None:
            return {"error": f"Tool not found: {tool_name}"}
        return _execute_skill_proxy(spec, args=args, args_json=args_json, timeout_sec=timeout_sec, employee_id=employee_id)
    for tool_name, spec in sorted(proxy_specs_by_name.items()):
        def _make_proxy_tool(spec_item: dict, tool_name_value: str):
            def _proxy_tool(args: dict | None = None, args_json: str = "{}", timeout_sec: int = 30) -> dict:
                return _execute_skill_proxy(spec_item, args=args, args_json=args_json, timeout_sec=timeout_sec, employee_id=employee_id)
            _proxy_tool.__name__ = f"proxy_{tool_name_value}"
            return _proxy_tool
        mcp.tool(
            name=tool_name,
            description=(
                f"Proxy of {spec['skill_id']}:{spec['entry_name']}. "
                "Pass CLI args via args(object) or args_json(string), e.g. args={\"sql\":\"SHOW TABLES\"}."
            ),
        )(_make_proxy_tool(spec, tool_name))

    return _DualTransportMcpApp(
        _apply_mcp_arguments_compat(mcp.sse_app()),
        mcp.streamable_http_app(),
    )


def _create_project_mcp(project_id: str):
    mcp = _new_mcp(f"project-{project_id}")
    scoped_proxy_specs, employee_proxy_specs = _build_project_proxy_specs(project_id)
    external_tool_specs = list_project_external_tools_runtime(project_id)

    def _get_project():
        return project_store.get(project_id)

    def _list_member_pairs() -> list[tuple[object, object]]:
        return _active_project_member_employees(project_id)

    def _feedback_actor() -> str:
        actor = _current_developer_name.get("").strip()
        return actor or "unknown"

    def _member_employee_ids() -> set[str]:
        return {employee.id for _member, employee in _list_member_pairs()}

    @mcp.resource(f"project://{project_id}/profile")
    def project_profile() -> str:
        project = _get_project()
        if not project:
            return "Project deleted or unavailable."
        return (
            f"[{project.id}] {project.name}\n"
            f"description: {project.description or '-'}\n"
            f"mcp_enabled={project.mcp_enabled} "
            f"feedback_upgrade_enabled={project.feedback_upgrade_enabled}"
        )

    @mcp.resource(f"project://{project_id}/members")
    def project_members() -> str:
        project = _get_project()
        if not project:
            return "Project deleted or unavailable."
        pairs = _list_member_pairs()
        if not pairs:
            return "No active project members."
        lines = []
        for member, employee in pairs:
            lines.append(
                f"- {employee.id}: {employee.name} | role={member.role} enabled={member.enabled}"
            )
        return "\n".join(lines)

    @mcp.resource(f"project://{project_id}/proxy-tools")
    def project_proxy_tools() -> str:
        project = _get_project()
        if not project:
            return "Project deleted or unavailable."
        if not scoped_proxy_specs:
            return "No executable skill tools discovered from project members."
        lines = []
        for tool_name, spec in sorted(scoped_proxy_specs.items()):
            lines.append(
                f"- {tool_name}: {spec['employee_id']} / {spec['skill_id']} / "
                f"{spec['entry_name']} ({spec['script_type']})"
            )
        return "\n".join(lines)

    @mcp.resource(f"project://{project_id}/external-mcp-tools")
    def project_external_tools() -> str:
        project = _get_project()
        if not project:
            return "Project deleted or unavailable."
        if not external_tool_specs:
            return "No external MCP tools available."
        lines = []
        for item in external_tool_specs:
            lines.append(
                f"- {item['tool_name']}: {item.get('module_name', '-')} / {item.get('remote_tool_name', '-')}"
            )
        return "\n".join(lines)

    @mcp.tool()
    def get_project_profile() -> dict:
        """获取项目画像配置"""
        project = _get_project()
        if not project:
            return {"error": "Project not found"}
        return asdict(project)

    @mcp.tool()
    def list_project_members() -> list[dict]:
        """列出项目成员详情"""
        project = _get_project()
        if not project:
            return []
        return list_project_member_profiles_runtime(
            project.id,
            include_disabled=False,
            include_missing=False,
            rule_limit=30,
        )

    @mcp.tool()
    def get_project_runtime_context() -> dict:
        """返回项目运行时上下文摘要（成员、技能、规则、记忆统计）"""
        project = _get_project()
        if not project:
            return {"error": "Project not found"}
        pairs = _list_member_pairs()
        rule_ids: set[str] = set()
        for _member, employee in pairs:
            for rule in _query_rules_by_employee(employee):
                rule_ids.add(rule.id)
        return {
            "project_id": project.id,
            "project_name": project.name,
            "member_count": len(pairs),
            "members": [employee.id for _member, employee in pairs],
            "scoped_proxy_tool_count": len(scoped_proxy_specs),
            "rule_count": len(rule_ids),
        }

    @mcp.tool()
    def recall_project_memory(
        query: str = "",
        employee_id: str = "",
        project_name: str = "",
        limit: int = 100,
    ) -> list[dict]:
        """检索项目记忆（支持项目隔离）"""
        project = _get_project()
        if not project:
            return []
        query = str(query or "").strip()
        employee_id = str(employee_id or "").strip()
        normalized_project_name = str(project_name or "").strip() or str(project.name or "").strip() or "default"
        max_limit = max(1, min(int(limit), 200))

        member_ids = _member_employee_ids()
        if employee_id and employee_id not in member_ids:
            return []
        targets = [employee_id] if employee_id else sorted(member_ids)
        memories = []
        for eid in targets:
            if query:
                employee_mems = memory_store.recall(eid, query, _RECALL_EMPLOYEE_MEMORY_LIMIT)
            else:
                employee_mems = memory_store.recent(eid, _RECALL_EMPLOYEE_MEMORY_LIMIT)
            for memory in employee_mems:
                if str(getattr(memory, "project_name", "")) != normalized_project_name:
                    continue
                memories.append(memory)
        memories = sorted(memories, key=lambda item: str(getattr(item, "created_at", "")), reverse=True)
        return [serialize_memory(item) for item in memories[:max_limit]]

    @mcp.tool()
    def save_project_memory(
        employee_id: str,
        content: str,
        type: str = "project-context",
        importance: float = 0.6,
        project_name: str = "",
    ) -> dict:
        """向项目下指定员工写入记忆"""
        project = _get_project()
        if not project:
            return {"error": "Project not found"}
        employee_id_value = str(employee_id or "").strip()
        if employee_id_value not in _member_employee_ids():
            return {"error": f"Employee {employee_id_value} is not an active project member"}
        content_value = str(content or "").strip()
        if not content_value:
            return {"error": "content is required"}
        memory_type_value = str(type or "").strip() or "project-context"
        try:
            memory_type = MemoryType(memory_type_value)
        except ValueError:
            return {"error": f"Invalid type: {memory_type_value}. Valid: {[item.value for item in MemoryType]}"}
        try:
            importance_value = float(importance)
        except (TypeError, ValueError):
            return {"error": "importance must be a number"}
        importance_value = max(0.0, min(1.0, importance_value))
        normalized_project_name = str(project_name or "").strip() or str(project.name or "").strip() or "default"
        memory = Memory(
            id=memory_store.new_id(),
            employee_id=employee_id_value,
            type=memory_type,
            content=content_value,
            project_name=normalized_project_name,
            importance=importance_value,
            scope=MemoryScope.EMPLOYEE_PRIVATE,
            classification=Classification.INTERNAL,
            purpose_tags=("project-mcp", "manual-write"),
        )
        memory_store.save(memory)
        return {
            "status": "saved",
            "memory_id": memory.id,
            "employee_id": employee_id_value,
            "project_name": normalized_project_name,
            "type": memory_type.value,
            "importance": importance_value,
        }

    @mcp.tool()
    def submit_project_feedback_bug(
        employee_id: str,
        title: str,
        symptom: str,
        expected: str,
        category: str = "general",
        severity: str = "medium",
        session_id: str = "",
        rule_id: str = "",
        source_context: dict | None = None,
    ) -> dict:
        """提交项目下员工反馈工单"""
        project = _get_project()
        if not project:
            return {"error": "Project not found"}
        employee_id_value = str(employee_id or "").strip()
        if employee_id_value not in _member_employee_ids():
            return {"error": f"Employee {employee_id_value} is not an active project member"}
        try:
            bug = get_feedback_service().create_bug(
                project_id=project.id,
                payload={
                    "employee_id": employee_id_value,
                    "title": title,
                    "symptom": symptom,
                    "expected": expected,
                    "category": category,
                    "severity": severity,
                    "session_id": session_id,
                    "rule_id": rule_id,
                    "source_context": source_context or {},
                },
                actor=_feedback_actor(),
            )
            return {"status": "created", "bug": bug}
        except (ValueError, RuntimeError, LookupError) as exc:
            return {"error": str(exc)}

    @mcp.tool()
    def query_project_rules(keyword: str = "", employee_id: str = "") -> list[dict]:
        """检索项目成员规则（支持按 employee_id 过滤）"""
        project = _get_project()
        if not project:
            return []
        employee_id_value = str(employee_id or "").strip()
        results = []
        seen: set[str] = set()
        for _member, employee in _list_member_pairs():
            if employee_id_value and employee.id != employee_id_value:
                continue
            for rule in _query_rules_by_employee(employee, keyword):
                if rule.id in seen:
                    continue
                seen.add(rule.id)
                results.append(serialize_rule(rule))
        return results

    @mcp.tool()
    def list_project_proxy_tools() -> list[dict]:
        """列出项目成员可执行技能脚本代理工具"""
        tools = []
        for tool_name, spec in sorted(scoped_proxy_specs.items()):
            tools.append(
                {
                    "tool_name": tool_name,
                    "employee_id": spec["employee_id"],
                    "base_tool_name": spec["base_tool_name"],
                    "skill_id": spec["skill_id"],
                    "entry_name": spec["entry_name"],
                    "script_type": spec["script_type"],
                    "description": spec["description"],
                }
            )
        return tools

    @mcp.tool()
    def list_external_mcp_tools() -> list[dict]:
        """列出当前项目可用的外部 MCP 工具"""
        return list_project_external_tools_runtime(project_id)

    @mcp.tool()
    def invoke_external_mcp_tool(
        tool_name: str,
        arguments: dict | None = None,
        timeout_sec: int = 30,
    ) -> dict:
        """调用当前项目配置的外部 MCP 工具"""
        return invoke_external_mcp_tool_runtime(
            project_id=project_id,
            tool_name=tool_name,
            args=arguments,
            args_json=json.dumps(arguments or {}, ensure_ascii=False),
            timeout_sec=timeout_sec,
        )

    def _resolve_project_tool_spec(tool_name: str, employee_id: str = "") -> tuple[dict | None, str]:
        normalized_tool_name = str(tool_name or "").strip()
        employee_id_value = str(employee_id or "").strip()
        if not normalized_tool_name:
            return None, "tool_name is required"
        if employee_id_value:
            employee_specs = employee_proxy_specs.get(employee_id_value, {})
            if normalized_tool_name in employee_specs:
                return employee_specs[normalized_tool_name], ""
            scoped_name = f"{_tool_token(employee_id_value)}__{normalized_tool_name}"
            scoped_spec = scoped_proxy_specs.get(scoped_name)
            if scoped_spec:
                return scoped_spec, ""
            return None, f"Tool not found for employee {employee_id_value}: {normalized_tool_name}"

        if normalized_tool_name in scoped_proxy_specs:
            return scoped_proxy_specs[normalized_tool_name], ""

        matched = []
        for specs in employee_proxy_specs.values():
            if normalized_tool_name in specs:
                matched.append(specs[normalized_tool_name])
        if not matched:
            return None, f"Tool not found: {normalized_tool_name}"
        if len(matched) > 1:
            employee_ids = sorted({item["employee_id"] for item in matched})
            return None, (
                "Ambiguous tool_name, provide employee_id. "
                f"Candidates: {employee_ids}"
            )
        return matched[0], ""

    @mcp.tool()
    def invoke_project_skill_tool(
        tool_name: str,
        employee_id: str = "",
        args: dict | None = None,
        args_json: str = "{}",
        timeout_sec: int = 30,
    ) -> dict:
        """按工具名直接调用项目成员技能脚本（支持 employee_id 消歧）"""
        spec, err = _resolve_project_tool_spec(tool_name, employee_id)
        if spec is None:
            return {"error": err}
        return _execute_skill_proxy(
            spec,
            args=args,
            args_json=args_json,
            timeout_sec=timeout_sec,
            employee_id=spec["employee_id"],
        )

    for tool_name, spec in sorted(scoped_proxy_specs.items()):
        def _make_proxy_tool(spec_item: dict):
            def _proxy_tool(args: dict | None = None, args_json: str = "{}", timeout_sec: int = 30) -> dict:
                return _execute_skill_proxy(
                    spec_item,
                    args=args,
                    args_json=args_json,
                    timeout_sec=timeout_sec,
                    employee_id=spec_item["employee_id"],
                )
            _proxy_tool.__name__ = f"project_proxy_{tool_name}"
            return _proxy_tool

        mcp.tool(
            name=tool_name,
            description=(
                f"Proxy of {spec['employee_id']}:{spec['skill_id']}:{spec['entry_name']}. "
                "Pass CLI args via args(object) or args_json(string), e.g. args={\"sql\":\"SHOW TABLES\"}."
            ),
        )(_make_proxy_tool(spec))

    for external_spec in external_tool_specs:
        scoped_tool_name = str(external_spec.get("tool_name") or "").strip()
        remote_tool_name = str(external_spec.get("remote_tool_name") or "").strip()
        if not scoped_tool_name or not remote_tool_name:
            continue

        def _make_external_proxy(tool_name_value: str):
            def _proxy_tool(arguments: dict | None = None, timeout_sec: int = 30) -> dict:
                return invoke_external_mcp_tool_runtime(
                    project_id=project_id,
                    tool_name=tool_name_value,
                    args=arguments,
                    args_json=json.dumps(arguments or {}, ensure_ascii=False),
                    timeout_sec=timeout_sec,
                )

            _proxy_tool.__name__ = f"project_external_{tool_name_value}"
            return _proxy_tool

        mcp.tool(
            name=scoped_tool_name,
            description=(
                f"Proxy of external MCP {external_spec.get('module_name', '-')}:{remote_tool_name}. "
                "Pass remote tool arguments via arguments(object)."
            ),
        )(_make_external_proxy(scoped_tool_name))

    return _DualTransportMcpApp(
        _apply_mcp_arguments_compat(mcp.sse_app()),
        mcp.streamable_http_app(),
    )


class _RuleMcpProxyApp:
    async def __call__(self, scope, receive, send):
        rule_id = scope.get("path_params", {}).get("rule_id")
        if not rule_id:
            response = JSONResponse({"detail": "Missing rule_id"}, status_code=400)
            await response(scope, receive, send)
            return

        rule = rule_store.get(rule_id)
        if not rule or not getattr(rule, "mcp_enabled", False):
            response = JSONResponse(
                {"detail": "Rule MCP service is disabled or rule not found."},
                status_code=404,
            )
            await response(scope, receive, send)
            return

        if rule_id not in _rule_apps:
            _rule_apps[rule_id] = _create_rule_mcp(rule_id)
        await _rule_apps[rule_id](scope, receive, send)


class _SkillMcpProxyApp:
    async def __call__(self, scope, receive, send):
        skill_id = scope.get("path_params", {}).get("skill_id")
        if not skill_id:
            response = JSONResponse({"detail": "Missing skill_id"}, status_code=400)
            await response(scope, receive, send)
            return

        skill = skill_store.get(skill_id)
        if not skill or not getattr(skill, "mcp_enabled", False):
            response = JSONResponse(
                {"detail": "Skill MCP service is disabled or skill not found."},
                status_code=404,
            )
            await response(scope, receive, send)
            return

        if skill_id not in _skill_apps:
            _skill_apps[skill_id] = _create_skill_mcp(skill_id)
        await _skill_apps[skill_id](scope, receive, send)


class _ProjectMcpProxyApp:
    async def __call__(self, scope, receive, send):
        project_id = scope.get("path_params", {}).get("project_id")
        if not project_id:
            response = JSONResponse({"detail": "Missing project_id"}, status_code=400)
            await response(scope, receive, send)
            return

        path = str(scope.get("path", ""))
        if (
            "/.well-known/oauth-authorization-server" in path
            or "/.well-known/openid-configuration" in path
            or "/.well-known/oauth-protected-resource" in path
        ):
            response = Response(status_code=204)
            await response(scope, receive, send)
            return

        project = project_store.get(project_id)
        if not project:
            response = JSONResponse({"detail": "Project not found."}, status_code=404)
            await response(scope, receive, send)
            return
        if not getattr(project, "mcp_enabled", True):
            response = JSONResponse({"detail": "Project MCP service is disabled."}, status_code=404)
            await response(scope, receive, send)
            return

        path = scope.get("path", "")
        method = str(scope.get("method", "")).upper()
        qs = parse_qs(scope.get("query_string", b"").decode())
        api_key = (qs.get("key") or [""])[0]
        session_id = (qs.get("session_id") or [""])[0]
        is_sse = path.rstrip("/").endswith("/sse")
        is_streamable = path.rstrip("/").endswith("/mcp")
        is_messages = path.rstrip("/").endswith("/messages") or "/messages/" in path

        if is_sse or is_streamable:
            if not api_key:
                response = JSONResponse(
                    {"detail": "Missing API key. Add ?key=YOUR_API_KEY to the URL."},
                    status_code=401,
                )
                await response(scope, receive, send)
                return
            developer_name = usage_store.validate_key(api_key)
            if not developer_name:
                response = JSONResponse({"detail": "Invalid or deactivated API key."}, status_code=403)
                await response(scope, receive, send)
                return
        elif is_messages:
            if session_id and session_id in _session_keys:
                api_key, developer_name = _session_keys[session_id]
            else:
                response = JSONResponse({"detail": "Unauthorized session."}, status_code=401)
                await response(scope, receive, send)
                return
        else:
            api_key = ""
            developer_name = ""

        client_ip = ""
        for header_name, header_val in scope.get("headers", []):
            if header_name == b"x-forwarded-for":
                client_ip = header_val.decode().split(",")[0].strip()
                break
        if not client_ip:
            client_addr = scope.get("client")
            if client_addr:
                client_ip = client_addr[0]

        _current_api_key.set(api_key)
        _current_developer_name.set(developer_name)

        usage_scope_id = f"project:{project_id}"
        if is_sse and method == "GET":
            usage_store.record_event(usage_scope_id, api_key, developer_name, "connection", client_ip=client_ip)

        original_send = send

        async def tracking_send(message):
            if is_sse and method == "GET" and message.get("type") == "http.response.body":
                body = message.get("body", b"")
                if b"endpoint" in body and b"session_id=" in body:
                    try:
                        text = body.decode()
                        for line in text.split("\n"):
                            if "session_id=" in line:
                                sid = line.split("session_id=")[-1].split("&")[0].split("\n")[0].split("\r")[0].strip()
                                if sid:
                                    _session_keys[sid] = (api_key, developer_name)
                                break
                    except Exception:
                        pass
            await original_send(message)

        original_receive = receive
        request_body_buffer = bytearray()
        request_body_captured = False

        async def tracking_receive():
            nonlocal request_body_captured
            message = await original_receive()
            if request_body_captured or message.get("type") != "http.request":
                return message
            body = message.get("body", b"")
            if body:
                request_body_buffer.extend(body)
            if message.get("more_body", False):
                return message
            if not request_body_buffer:
                return message
            request_body_captured = True
            try:
                payload = json.loads(bytes(request_body_buffer))
                rpc_payloads = payload if isinstance(payload, list) else [payload]
                for rpc_payload in rpc_payloads:
                    if not isinstance(rpc_payload, dict):
                        continue
                    method_name, tool_name, _questions, _project_name = _extract_user_questions_from_rpc_payload(rpc_payload)
                    if method_name == "tools/call":
                        usage_store.record_event(
                            usage_scope_id,
                            api_key,
                            developer_name,
                            "tool_call",
                            tool_name=tool_name,
                            client_ip=client_ip,
                        )
            except Exception:
                pass
            return message

        members = project_store.list_members(project_id)
        active_members = [m for m in members if bool(getattr(m, "enabled", True))]
        member_signature = tuple(
            sorted(
                (
                    str(getattr(m, "employee_id", "")),
                    bool(getattr(m, "enabled", True)),
                    str(getattr(m, "role", "")),
                )
                for m in members
            )
        )
        employee_signature = tuple(
            sorted(
                (
                    employee.id,
                    employee.updated_at,
                    tuple(employee.skills or []),
                    tuple(employee.rule_ids or []),
                )
                for m in active_members
                for employee in [employee_store.get(m.employee_id)]
                if employee is not None
            )
        )
        external_signature = tuple(
            sorted(
                (
                    str(getattr(module, "id", "") or ""),
                    str(getattr(module, "updated_at", "") or ""),
                    str(getattr(module, "endpoint_http", "") or ""),
                    str(getattr(module, "endpoint_sse", "") or ""),
                    str(getattr(module, "project_id", "") or ""),
                    bool(getattr(module, "enabled", True)),
                )
                for module in _list_visible_external_mcp_modules(project_id)
            )
        )
        signature = (
            _PROJECT_MCP_APP_REV,
            project.updated_at,
            bool(getattr(project, "mcp_enabled", True)),
            member_signature,
            employee_signature,
            external_signature,
        )
        cached_app = _project_apps.get(project_id)
        if (
            cached_app is None
            or not isinstance(cached_app, _DualTransportMcpApp)
            or _project_app_signatures.get(project_id) != signature
        ):
            _project_apps[project_id] = _create_project_mcp(project_id)
            _project_app_signatures[project_id] = signature

        downstream_scope = scope
        if is_sse and method != "GET":
            rewritten_path = _replace_path_suffix(str(scope.get("path", "")), "/sse", "/mcp")
            rewritten_scope = dict(scope)
            rewritten_scope["path"] = rewritten_path
            rewritten_scope["raw_path"] = rewritten_path.encode("utf-8")
            downstream_scope = rewritten_scope
        await _project_apps[project_id](downstream_scope, tracking_receive, tracking_send)


class _EmployeeMcpProxyApp:
    async def __call__(self, scope, receive, send):
        employee_id = scope.get("path_params", {}).get("employee_id")
        if not employee_id:
            response = JSONResponse({"detail": "Missing employee_id"}, status_code=400)
            await response(scope, receive, send)
            return

        path = str(scope.get("path", ""))
        # Compatibility: OAuth/OIDC metadata probing for SSE URLs.
        if (
            "/.well-known/oauth-authorization-server" in path
            or "/.well-known/openid-configuration" in path
            or "/.well-known/oauth-protected-resource" in path
        ):
            response = Response(status_code=204)
            await response(scope, receive, send)
            return

        employee = employee_store.get(employee_id)
        if not employee:
            response = JSONResponse(
                {"detail": "Employee not found."},
                status_code=404,
            )
            await response(scope, receive, send)
            return
        if not getattr(employee, "mcp_enabled", True):
            response = JSONResponse(
                {"detail": "Employee MCP service is disabled."},
                status_code=404,
            )
            await response(scope, receive, send)
            return

        # 解析请求路径和 query
        path = scope.get("path", "")
        method = str(scope.get("method", "")).upper()
        qs = parse_qs(scope.get("query_string", b"").decode())
        api_key = (qs.get("key") or [""])[0]
        session_id = (qs.get("session_id") or [""])[0]
        project_name_from_query = (
            (qs.get("project_name") or qs.get("project_id") or qs.get("project") or [""])[0]
        ).strip()
        is_sse = path.rstrip("/").endswith("/sse")
        is_streamable = path.rstrip("/").endswith("/mcp")
        is_messages = path.rstrip("/").endswith("/messages") or "/messages/" in path

        if is_sse or is_streamable:
            # SSE/Streamable 入口：必须带有效 key
            if not api_key:
                response = JSONResponse({"detail": "Missing API key. Add ?key=YOUR_API_KEY to the URL."}, status_code=401)
                await response(scope, receive, send)
                return
            developer_name = usage_store.validate_key(api_key)
            if not developer_name:
                response = JSONResponse({"detail": "Invalid or deactivated API key."}, status_code=403)
                await response(scope, receive, send)
                return
        elif is_messages:
            if session_id and session_id in _session_keys:
                api_key, developer_name = _session_keys[session_id]
            else:
                response = JSONResponse({"detail": "Unauthorized session."}, status_code=401)
                await response(scope, receive, send)
                return
        else:
            # 其他路径（OAuth 发现等）直接放行
            api_key = ""
            developer_name = ""

        # 提取 client_ip
        client_ip = ""
        for header_name, header_val in scope.get("headers", []):
            if header_name == b"x-forwarded-for":
                client_ip = header_val.decode().split(",")[0].strip()
                break
        if not client_ip:
            client_addr = scope.get("client")
            if client_addr:
                client_ip = client_addr[0]

        # 设置当前请求的 api_key 到 contextvar（供技能脚本读取）
        _current_api_key.set(api_key)
        _current_developer_name.set(developer_name)

        # 记录 connection 事件
        if is_sse and method == "GET":
            usage_store.record_event(employee_id, api_key, developer_name, "connection", client_ip=client_ip)

        # 包装 send 拦截 SSE endpoint event 提取 session_id
        original_send = send

        async def tracking_send(message):
            if is_sse and method == "GET" and message.get("type") == "http.response.body":
                body = message.get("body", b"")
                if b"endpoint" in body and b"session_id=" in body:
                    try:
                        text = body.decode()
                        for line in text.split("\n"):
                            if "session_id=" in line:
                                sid = line.split("session_id=")[-1].split("&")[0].split("\n")[0].split("\r")[0].strip()
                                if sid:
                                    _session_keys[sid] = (api_key, developer_name)
                                break
                    except Exception:
                        pass
            await original_send(message)

        # 包装 receive 拦截 tools/call
        original_receive = receive
        request_body_buffer = bytearray()
        request_body_captured = False

        async def tracking_receive():
            nonlocal request_body_captured
            message = await original_receive()
            if request_body_captured or message.get("type") != "http.request":
                return message
            body = message.get("body", b"")
            if body:
                request_body_buffer.extend(body)
            if message.get("more_body", False):
                return message
            if not request_body_buffer:
                return message
            request_body_captured = True
            try:
                payload = json.loads(bytes(request_body_buffer))
                rpc_payloads = payload if isinstance(payload, list) else [payload]
                for rpc_payload in rpc_payloads:
                    if not isinstance(rpc_payload, dict):
                        continue
                    method_name, tool_name, questions, project_name = _extract_user_questions_from_rpc_payload(rpc_payload)
                    if method_name == "tools/call":
                        usage_store.record_event(
                            employee_id, api_key, developer_name,
                            "tool_call", tool_name=tool_name, client_ip=client_ip,
                        )
                    if questions:
                        source = f"mcp:{method_name or 'unknown'}:{tool_name or '-'}"
                        _save_auto_user_question_memory(
                            employee_id,
                            questions,
                            source,
                            project_name=project_name or project_name_from_query or "default",
                        )
            except Exception:
                pass
            return message

        signature = (
            _EMPLOYEE_MCP_APP_REV,
            tuple(employee.skills or []),
            tuple(employee.rule_ids or []),
            bool(getattr(employee, "mcp_enabled", True)),
            employee.updated_at,
        )
        cached_app = _employee_apps.get(employee_id)
        if (
            cached_app is None
            or not isinstance(cached_app, _DualTransportMcpApp)
            or _employee_app_signatures.get(employee_id) != signature
        ):
            _employee_apps[employee_id] = _create_employee_mcp(employee_id)
            _employee_app_signatures[employee_id] = signature
        downstream_scope = scope
        if is_sse and method != "GET":
            rewritten_path = _replace_path_suffix(str(scope.get("path", "")), "/sse", "/mcp")
            rewritten_scope = dict(scope)
            rewritten_scope["path"] = rewritten_path
            rewritten_scope["raw_path"] = rewritten_path.encode("utf-8")
            downstream_scope = rewritten_scope
        await _employee_apps[employee_id](downstream_scope, tracking_receive, tracking_send)


rule_mcp_proxy_app = _RuleMcpProxyApp()
skill_mcp_proxy_app = _SkillMcpProxyApp()
project_mcp_proxy_app = _ProjectMcpProxyApp()
employee_mcp_proxy_app = _EmployeeMcpProxyApp()
