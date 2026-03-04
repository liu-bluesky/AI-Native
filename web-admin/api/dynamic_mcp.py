"""动态 Micro-MCP 服务生成器"""
from __future__ import annotations

import asyncio
from contextvars import ContextVar
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import sys

from urllib.parse import parse_qs

from fastapi.responses import JSONResponse, Response
from mcp.server.fastmcp import FastMCP
from starlette.types import ASGIApp, Receive, Scope, Send

from deps import employee_store, usage_store
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
_employee_app_signatures = {}
_session_keys: dict[str, tuple[str, str]] = {}  # session_id -> (api_key, developer_name)
_current_api_key: ContextVar[str] = ContextVar("_current_api_key", default="")
_current_developer_name: ContextVar[str] = ContextVar("_current_developer_name", default="")
_EMPLOYEE_MCP_APP_REV = "2026-03-04-sse-post-bridge"
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
    domains = {_normalize_domain(d) for d in employee.rule_domains or [] if str(d).strip()}
    if not domains:
        return []
    kw = str(keyword or "").strip().lower()
    results = []
    for rule in rule_store.list_all():
        if domains and _normalize_domain(rule.domain) not in domains:
            continue
        if kw and kw not in rule.title.lower() and kw not in rule.content.lower():
            continue
        results.append(rule)
    return results


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
        return asdict(employee)

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
        rules = _query_rules_by_employee(employee)
        return {
            "employee_id": employee.id,
            "name": employee.name,
            "tone": employee.tone,
            "verbosity": employee.verbosity,
            "language": employee.language,
            "style_hints": list(employee.style_hints or []),
            "skills": list(employee.skills or []),
            "proxy_tools": sorted(proxy_specs_by_name.keys()),
            "rule_domains": list(employee.rule_domains or []),
            "rule_count": len(rules),
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
                detail = get_feedback_service().get_bug_detail(project_id, feedback_id)
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
                result = get_feedback_service().analyze_bug(project_id, feedback_id)
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
            tuple(employee.rule_domains or []),
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
employee_mcp_proxy_app = _EmployeeMcpProxyApp()
