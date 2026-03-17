"""Helpers for calling user-owned local connectors."""

from __future__ import annotations

from typing import Any

import httpx

LOCAL_CONNECTOR_PROVIDER_PREFIX = "local-connector:"
LOCAL_CONNECTOR_FILE_TOOL_NAMES = {
    "local_connector_list_files",
    "local_connector_search_files",
    "local_connector_read_file",
    "local_connector_write_file",
    "local_connector_run_command",
}


def build_local_connector_provider_id(connector_id: str) -> str:
    normalized = str(connector_id or "").strip()
    return f"{LOCAL_CONNECTOR_PROVIDER_PREFIX}{normalized}" if normalized else ""


def parse_local_connector_provider_id(provider_id: str) -> str:
    normalized = str(provider_id or "").strip()
    if not normalized.startswith(LOCAL_CONNECTOR_PROVIDER_PREFIX):
        return ""
    return normalized[len(LOCAL_CONNECTOR_PROVIDER_PREFIX) :].strip()


def connector_base_url(connector: Any) -> str:
    return str(getattr(connector, "advertised_url", "") or "").strip().rstrip("/")


def connector_headers(connector: Any) -> dict[str, str]:
    token = str(getattr(connector, "connector_token", "") or "").strip()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Connector-Token"] = token
    return headers


async def _request_json(
    connector: Any,
    method: str,
    path: str,
    *,
    timeout: float = 10.0,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base_url = connector_base_url(connector)
    if not base_url:
        raise RuntimeError("Local connector is missing advertised_url")
    url = f"{base_url}{path if path.startswith('/') else f'/{path}'}"
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.request(
            method.upper(),
            url,
            headers=connector_headers(connector),
            json=json_body,
        )
        response.raise_for_status()
        payload = response.json() if response.content else {}
    return payload if isinstance(payload, dict) else {}


async def list_connector_llm_models(connector: Any) -> dict[str, Any]:
    payload = await _request_json(connector, "GET", "/llm/models", timeout=12.0)
    models = [
        str(item or "").strip()
        for item in (payload.get("models") or [])
        if str(item or "").strip()
    ]
    default_model = str(payload.get("default_model") or "").strip()
    if default_model and default_model not in models:
        models = [default_model, *models]
    return {
        "enabled": bool(payload.get("enabled")),
        "base_url": str(payload.get("base_url") or "").strip(),
        "default_model": default_model or (models[0] if models else ""),
        "models": models,
    }


async def probe_connector_workspace(
    connector: Any,
    workspace_path: str,
    sandbox_mode: str = "workspace-write",
) -> dict[str, Any]:
    payload = await _request_json(
        connector,
        "POST",
        "/probe-workspace",
        timeout=12.0,
        json_body={
            "workspace_path": str(workspace_path or "").strip(),
            "sandbox_mode": str(sandbox_mode or "workspace-write").strip()
            or "workspace-write",
        },
    )
    payload["source"] = "local_connector"
    return payload


async def materialize_connector_workspace(
    connector: Any,
    workspace_path: str,
    sandbox_mode: str,
    files: list[dict[str, Any]] | None,
    copies: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    payload = await _request_json(
        connector,
        "POST",
        "/workspace/materialize",
        timeout=20.0,
        json_body={
            "workspace_path": str(workspace_path or "").strip(),
            "sandbox_mode": str(sandbox_mode or "workspace-write").strip()
            or "workspace-write",
            "files": list(files or []),
            "copies": list(copies or []),
        },
    )
    if isinstance(payload.get("workspace_access"), dict):
        payload["workspace_access"]["source"] = "local_connector"
    return payload


async def chat_completion_via_connector(
    connector: Any,
    *,
    model_name: str,
    messages: list[dict[str, Any]],
    temperature: float = 0.2,
    max_tokens: int | None = None,
    timeout: float = 120.0,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": str(model_name or "").strip(),
        "messages": list(messages or []),
        "temperature": float(temperature or 0.0),
        "stream": False,
    }
    if max_tokens is not None:
        body["max_tokens"] = int(max_tokens)
    payload = await _request_json(
        connector,
        "POST",
        "/llm/chat/completions",
        timeout=timeout,
        json_body=body,
    )
    return {
        "content": str(payload.get("content") or "").strip(),
        "model": str(payload.get("model") or model_name or "").strip(),
        "raw": payload.get("raw"),
    }


async def chat_completion_stream_via_connector(
    connector: Any,
    *,
    model_name: str,
    messages: list[dict[str, Any]],
    temperature: float = 0.2,
    max_tokens: int = 1024,
    timeout: float = 120.0,
    tools: list[dict[str, Any]] | None = None,
):
    from services.llm_provider_service import LlmProviderService

    url = f"{connector_base_url(connector)}/llm/chat/completions/stream"
    body: dict[str, Any] = {
        "model": str(model_name or "").strip(),
        "messages": list(messages or []),
        "temperature": float(temperature or 0.0),
        "max_tokens": int(max_tokens),
        "stream": True,
    }
    if tools:
        body["tools"] = tools
    headers = connector_headers(connector)
    headers["Accept"] = "text/event-stream"
    async for chunk in LlmProviderService._stream_request(url, headers, body, int(timeout)):
        yield chunk


class LocalConnectorLlmAdapter:
    def __init__(self, connector: Any) -> None:
        self._connector = connector

    async def chat_completion_stream(
        self,
        provider_id: str,
        model_name: str,
        messages: list[dict[str, Any]],
        temperature: float = 0.2,
        max_tokens: int = 1024,
        timeout: int = 120,
        tools: list[dict[str, Any]] | None = None,
    ):
        async for chunk in chat_completion_stream_via_connector(
            self._connector,
            model_name=model_name,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=float(timeout),
            tools=tools,
        ):
            yield chunk


def build_local_connector_file_tools() -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = [
        {
            "tool_name": "local_connector_list_files",
            "description": "列出本地连接器工作区内的目录与文件，适合先了解项目结构。",
            "parameters_schema": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "相对工作区的目录路径，留空表示工作区根目录。",
                    },
                    "depth": {
                        "type": "integer",
                        "description": "递归目录深度，默认 3，范围 0-8。",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "最多返回条目数，默认 200，范围 1-1000。",
                    },
                    "include_hidden": {
                        "type": "boolean",
                        "description": "是否包含以 . 开头的隐藏文件，默认 false。",
                    },
                },
                "required": [],
            },
        },
        {
            "tool_name": "local_connector_search_files",
            "description": "在本地连接器工作区内搜索文本内容，返回命中的文件路径、行号和文本片段。",
            "parameters_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "必填，要搜索的关键词或代码片段。",
                    },
                    "path": {
                        "type": "string",
                        "description": "可选，相对工作区的子目录路径，留空表示全工作区。",
                    },
                    "depth": {
                        "type": "integer",
                        "description": "搜索目录深度，默认 8，范围 0-32。",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "最多返回命中条数，默认 100，范围 1-1000。",
                    },
                    "case_sensitive": {
                        "type": "boolean",
                        "description": "是否区分大小写，默认 false。",
                    },
                    "include_hidden": {
                        "type": "boolean",
                        "description": "是否搜索隐藏文件，默认 false。",
                    },
                },
                "required": ["query"],
            },
        },
        {
            "tool_name": "local_connector_read_file",
            "description": "读取本地连接器工作区内的单个文本文件，可按行号范围截取。",
            "parameters_schema": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "必填，相对工作区的文件路径。",
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "起始行号，默认 1。",
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "结束行号，默认读取到 start_line 后 200 行内。",
                    },
                },
                "required": ["path"],
            },
        },
    ]
    tools.append(
        {
            "tool_name": "local_connector_write_file",
            "description": "覆盖写入本地连接器工作区内的单个文本文件，会自动创建缺失目录。",
            "parameters_schema": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "必填，相对工作区的文件路径。",
                    },
                    "content": {
                        "type": "string",
                        "description": "必填，要写入的新文件内容。",
                    },
                },
                "required": ["path", "content"],
            },
        }
    )
    tools.append(
        {
            "tool_name": "local_connector_run_command",
            "description": "在本地连接器工作区内执行命令，适合运行测试、构建或代码格式检查。",
            "parameters_schema": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "必填，要执行的 shell 命令。",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "可选，相对工作区的子目录；留空表示工作区根目录。",
                    },
                    "timeout_sec": {
                        "type": "integer",
                        "description": "超时时间秒数，默认 20，范围 1-120。",
                    },
                    "max_output_chars": {
                        "type": "integer",
                        "description": "stdout/stderr 各自最多保留的字符数，默认 12000。",
                    },
                },
                "required": ["command"],
            },
        }
    )
    return tools


async def list_connector_workspace_files(
    connector: Any,
    *,
    workspace_path: str,
    path: str = "",
    depth: int = 3,
    limit: int = 200,
    include_hidden: bool = False,
    sandbox_mode: str = "workspace-write",
) -> dict[str, Any]:
    payload = await _request_json(
        connector,
        "POST",
        "/workspace/files/list",
        timeout=20.0,
        json_body={
            "workspace_path": str(workspace_path or "").strip(),
            "path": str(path or "").strip(),
            "depth": int(depth),
            "limit": int(limit),
            "include_hidden": bool(include_hidden),
            "sandbox_mode": str(sandbox_mode or "workspace-write").strip()
            or "workspace-write",
        },
    )
    return payload


async def search_connector_workspace_files(
    connector: Any,
    *,
    workspace_path: str,
    query: str,
    path: str = "",
    depth: int = 8,
    limit: int = 100,
    case_sensitive: bool = False,
    include_hidden: bool = False,
    sandbox_mode: str = "workspace-write",
) -> dict[str, Any]:
    payload = await _request_json(
        connector,
        "POST",
        "/workspace/files/search",
        timeout=30.0,
        json_body={
            "workspace_path": str(workspace_path or "").strip(),
            "query": str(query or "").strip(),
            "path": str(path or "").strip(),
            "depth": int(depth),
            "limit": int(limit),
            "case_sensitive": bool(case_sensitive),
            "include_hidden": bool(include_hidden),
            "sandbox_mode": str(sandbox_mode or "workspace-write").strip()
            or "workspace-write",
        },
    )
    return payload


async def read_connector_file(
    connector: Any,
    *,
    workspace_path: str,
    path: str,
    start_line: int = 1,
    end_line: int | None = None,
    sandbox_mode: str = "workspace-write",
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "workspace_path": str(workspace_path or "").strip(),
        "path": str(path or "").strip(),
        "start_line": int(start_line),
        "sandbox_mode": str(sandbox_mode or "workspace-write").strip()
        or "workspace-write",
    }
    if end_line is not None:
        body["end_line"] = int(end_line)
    payload = await _request_json(
        connector,
        "POST",
        "/workspace/files/read",
        timeout=20.0,
        json_body=body,
    )
    return payload


async def write_connector_file(
    connector: Any,
    *,
    workspace_path: str,
    path: str,
    content: str,
    sandbox_mode: str = "workspace-write",
) -> dict[str, Any]:
    payload = await _request_json(
        connector,
        "POST",
        "/workspace/files/write",
        timeout=20.0,
        json_body={
            "workspace_path": str(workspace_path or "").strip(),
            "path": str(path or "").strip(),
            "content": str(content or ""),
            "sandbox_mode": str(sandbox_mode or "workspace-write").strip()
            or "workspace-write",
        },
    )
    return payload


async def run_connector_command(
    connector: Any,
    *,
    workspace_path: str,
    command: str,
    cwd: str = "",
    timeout_sec: int = 20,
    max_output_chars: int = 12000,
    sandbox_mode: str = "workspace-write",
) -> dict[str, Any]:
    payload = await _request_json(
        connector,
        "POST",
        "/workspace/command/run",
        timeout=max(float(timeout_sec) + 5.0, 10.0),
        json_body={
            "workspace_path": str(workspace_path or "").strip(),
            "command": str(command or "").strip(),
            "cwd": str(cwd or "").strip(),
            "timeout_sec": int(timeout_sec),
            "max_output_chars": int(max_output_chars),
            "sandbox_mode": str(sandbox_mode or "workspace-write").strip()
            or "workspace-write",
        },
    )
    return payload
