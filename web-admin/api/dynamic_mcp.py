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
from stores import (
    memory_store,
    rule_store,
    serialize_memory,
    serialize_rule,
    serialize_skill,
    skill_store,
)

# 缓存动态生成的 ASGI App
_rule_apps = {}
_skill_apps = {}
_employee_apps = {}
_employee_app_signatures = {}
_session_keys: dict[str, tuple[str, str]] = {}  # session_id -> (api_key, developer_name)
_current_api_key: ContextVar[str] = ContextVar("_current_api_key", default="")
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
    return FastMCP(service_name, host=_FASTMCP_HOST)

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
    def recall_employee_memory(query: str = "", limit: int = 10) -> list[dict]:
        """检索员工记忆，query 为空时按最近记忆返回"""
        employee = _get_employee()
        if not employee:
            return []
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 10
        limit = max(1, min(limit, 100))
        query = str(query or "").strip()
        if query:
            memories = memory_store.recall(employee.id, query, limit)
        else:
            memories = memory_store.recent(employee.id, limit)
        return [serialize_memory(mem) for mem in memories]

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

        async def tracking_receive():
            message = await original_receive()
            if message.get("type") == "http.request":
                body = message.get("body", b"")
                if body:
                    try:
                        payload = json.loads(body)
                        if isinstance(payload, dict) and payload.get("method") == "tools/call":
                            tool_name = (payload.get("params") or {}).get("name", "")
                            usage_store.record_event(
                                employee_id, api_key, developer_name,
                                "tool_call", tool_name=tool_name, client_ip=client_ip,
                            )
                    except Exception:
                        pass
            return message

        signature = (
            tuple(employee.skills or []),
            tuple(employee.rule_domains or []),
            bool(getattr(employee, "mcp_enabled", True)),
            employee.updated_at,
        )
        if employee_id not in _employee_apps or _employee_app_signatures.get(employee_id) != signature:
            _employee_apps[employee_id] = _create_employee_mcp(employee_id)
            _employee_app_signatures[employee_id] = signature
        await _employee_apps[employee_id](scope, tracking_receive, tracking_send)


rule_mcp_proxy_app = _RuleMcpProxyApp()
skill_mcp_proxy_app = _SkillMcpProxyApp()
employee_mcp_proxy_app = _EmployeeMcpProxyApp()
