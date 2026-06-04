"""Shared transport helpers for dynamic MCP apps."""

from __future__ import annotations

import asyncio
import json

from starlette.types import ASGIApp, Receive, Scope, Send


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


class McpArgumentsCompatApp:
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


def apply_mcp_arguments_compat(app: ASGIApp) -> ASGIApp:
    if getattr(app, "_arguments_compat_enabled", False):
        return app
    return McpArgumentsCompatApp(app)


def replace_path_suffix(path: str, old_suffix: str, new_suffix: str) -> str:
    if path == old_suffix:
        return new_suffix
    if path.endswith(old_suffix):
        return path[: -len(old_suffix)] + new_suffix
    return path


class DualTransportMcpApp:
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

        if is_sse and method != "GET":
            await self._ensure_streamable_lifespan()
            rewritten = replace_path_suffix(path, "/sse", "/mcp")
            rewritten_scope = dict(scope)
            rewritten_scope["path"] = rewritten
            rewritten_scope["raw_path"] = rewritten.encode("utf-8")
            await self.streamable_http_app(rewritten_scope, receive, send)
            return

        await self.sse_app(scope, receive, send)
