"""Single LLM streaming step for agent_runtime_v2."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from services.agent_runtime_v2.tool_call_collector import CollectedToolCall, ToolCallCollector


@dataclass
class LLMStepResult:
    content: str = ""
    tool_calls: list[CollectedToolCall] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    provider_id: str = ""
    model_name: str = ""
    error: dict[str, Any] | None = None

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "tool_calls": [item.to_dict() for item in self.tool_calls],
            "usage": dict(self.usage),
            "provider_id": self.provider_id,
            "model_name": self.model_name,
            "error": dict(self.error or {}) if self.error else None,
        }


class LLMStep:
    def __init__(self, llm_service: Any):
        self._llm_service = llm_service

    async def run(
        self,
        *,
        provider_id: str,
        model_name: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        timeout: int = 120,
        max_tool_calls: int = 6,
    ) -> LLMStepResult:
        collector = ToolCallCollector()
        content_parts: list[str] = []
        usage: dict[str, Any] = {}
        resolved_provider_id = str(provider_id or "").strip()
        resolved_model_name = str(model_name or "").strip()
        try:
            async for chunk in self._llm_service.chat_completion_stream(
                provider_id=provider_id,
                model_name=model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
                tools=self._format_tools(tools or []) if tools else None,
            ):
                if not isinstance(chunk, dict):
                    continue
                if isinstance(chunk.get("usage"), dict):
                    usage = dict(chunk["usage"])
                    resolved_provider_id = str(chunk.get("provider_id") or resolved_provider_id).strip()
                    resolved_model_name = str(chunk.get("model_name") or resolved_model_name).strip()
                if str(chunk.get("type") or "").strip().lower() == "error":
                    return LLMStepResult(
                        content="".join(content_parts),
                        tool_calls=collector.list_tool_calls(limit=max_tool_calls),
                        usage=usage,
                        provider_id=resolved_provider_id,
                        model_name=resolved_model_name,
                        error=dict(chunk),
                    )
                if "tool_calls" in chunk:
                    collector.add_chunk(chunk)
                if "content" in chunk:
                    content_parts.append(str(chunk.get("content") or ""))
        except Exception as exc:
            return LLMStepResult(
                content="".join(content_parts),
                tool_calls=collector.list_tool_calls(limit=max_tool_calls),
                usage=usage,
                provider_id=resolved_provider_id,
                model_name=resolved_model_name,
                error={
                    "type": "error",
                    "message": _format_llm_stream_exception_message(exc),
                    "raw_error": str(exc),
                    "error_type": exc.__class__.__name__,
                    "provider_id": resolved_provider_id,
                    "model_name": resolved_model_name,
                },
            )
        return LLMStepResult(
            content="".join(content_parts),
            tool_calls=collector.list_tool_calls(limit=max_tool_calls),
            usage=usage,
            provider_id=resolved_provider_id,
            model_name=resolved_model_name,
        )

    def _format_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        formatted: list[dict[str, Any]] = []
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            tool_name = str(tool.get("tool_name") or tool.get("name") or "").strip()
            if not tool_name:
                continue
            formatted.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "description": str(tool.get("description") or ""),
                        "parameters": tool.get(
                            "parameters_schema",
                            {"type": "object", "properties": {}},
                        ),
                    },
                }
            )
        return formatted


def _format_llm_stream_exception_message(exc: Exception) -> str:
    raw = str(exc or "").strip() or exc.__class__.__name__
    lowered = raw.lower()
    if (
        "nodename nor servname provided" in lowered
        or "name or service not known" in lowered
        or "temporary failure in name resolution" in lowered
        or "failed to resolve" in lowered
    ):
        return (
            "模型服务地址无法解析，请检查当前 LLM provider 的 base_url、域名、"
            f"DNS 或网络代理配置。原始错误：{raw}"
        )
    return f"LLM stream request failed: {raw}"
