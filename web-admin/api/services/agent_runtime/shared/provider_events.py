"""Provider-neutral stream event contract for agent runtime model IO."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable

from services.agent_runtime.shared.tool_calls import ToolCallCollector


class ProviderStreamEventType(str, Enum):
    CONTENT_DELTA = "content_delta"
    TOOL_CALL_DELTA = "tool_call_delta"
    USAGE = "usage"
    ERROR = "error"
    RAW = "raw"


@dataclass(frozen=True)
class ProviderCapabilityMetadata:
    provider_id: str = ""
    model_name: str = ""
    native_tool_calls: bool = False
    vision: bool = False
    reasoning: bool = False
    json_mode: bool = False
    stream_usage: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "model_name": self.model_name,
            "native_tool_calls": self.native_tool_calls,
            "vision": self.vision,
            "reasoning": self.reasoning,
            "json_mode": self.json_mode,
            "stream_usage": self.stream_usage,
        }


@dataclass(frozen=True)
class ProviderStreamEvent:
    event_type: ProviderStreamEventType
    provider_id: str = ""
    model_name: str = ""
    text: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    error: dict[str, Any] = field(default_factory=dict)
    retryable: bool = False
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "provider_id": self.provider_id,
            "model_name": self.model_name,
            "text": self.text,
            "tool_calls": [dict(item) for item in self.tool_calls],
            "usage": dict(self.usage),
            "error": dict(self.error),
            "retryable": self.retryable,
            "raw": dict(self.raw),
        }


class ProviderStreamAdapter:
    """Normalize provider chunks into stable runtime stream events."""

    def __init__(
        self,
        *,
        provider_id: str = "",
        model_name: str = "",
        capabilities: ProviderCapabilityMetadata | dict[str, Any] | None = None,
    ):
        self.provider_id = str(provider_id or "").strip()
        self.model_name = str(model_name or "").strip()
        self.capabilities = self._resolve_capabilities(capabilities)

    def _resolve_capabilities(
        self,
        capabilities: ProviderCapabilityMetadata | dict[str, Any] | None,
    ) -> ProviderCapabilityMetadata:
        if isinstance(capabilities, ProviderCapabilityMetadata):
            return capabilities
        guessed = self._guess_capabilities()
        if not isinstance(capabilities, dict):
            return guessed
        values = guessed.to_dict()
        values.update({key: value for key, value in capabilities.items() if key in values})
        values["provider_id"] = str(values.get("provider_id") or self.provider_id).strip()
        values["model_name"] = str(values.get("model_name") or self.model_name).strip()
        return ProviderCapabilityMetadata(
            provider_id=values["provider_id"],
            model_name=values["model_name"],
            native_tool_calls=bool(values.get("native_tool_calls")),
            vision=bool(values.get("vision")),
            reasoning=bool(values.get("reasoning")),
            json_mode=bool(values.get("json_mode")),
            stream_usage=bool(values.get("stream_usage")),
        )

    def _guess_capabilities(self) -> ProviderCapabilityMetadata:
        provider = self.provider_id.lower()
        model = self.model_name.lower()
        native_tool_calls = provider in {"openai", "responses", "anthropic", "gemini"}
        json_mode = provider in {"openai", "responses", "gemini"}
        stream_usage = provider in {"openai", "responses"}
        reasoning = any(token in model for token in ("o1", "o3", "o4", "reason", "deepseek-r1"))
        vision = any(token in model for token in ("vision", "gpt-4o", "claude-3", "gemini"))
        return ProviderCapabilityMetadata(
            provider_id=self.provider_id,
            model_name=self.model_name,
            native_tool_calls=native_tool_calls,
            vision=vision,
            reasoning=reasoning,
            json_mode=json_mode,
            stream_usage=stream_usage,
        )

    def normalize_chunk(self, chunk: dict[str, Any]) -> list[ProviderStreamEvent]:
        if not isinstance(chunk, dict):
            return []
        provider_id = str(chunk.get("provider_id") or self.provider_id).strip()
        model_name = str(chunk.get("model_name") or self.model_name).strip()
        events: list[ProviderStreamEvent] = []
        raw = dict(chunk)
        response_events = self._normalize_responses_chunk(
            chunk,
            provider_id=provider_id,
            model_name=model_name,
            raw=raw,
        )
        if response_events:
            return response_events
        if str(chunk.get("type") or "").strip().lower() == "error":
            events.append(
                ProviderStreamEvent(
                    event_type=ProviderStreamEventType.ERROR,
                    provider_id=provider_id,
                    model_name=model_name,
                    error=dict(chunk),
                    retryable=bool(chunk.get("retryable")),
                    raw=raw,
                )
            )
            return events
        openai_delta = self._extract_openai_choice_delta(chunk)
        if openai_delta:
            events.extend(
                self._events_from_content_tool_usage(
                    openai_delta,
                    provider_id=provider_id,
                    model_name=model_name,
                    raw=raw,
                    usage=chunk.get("usage"),
                )
            )
        else:
            events.extend(
                self._events_from_content_tool_usage(
                    chunk,
                    provider_id=provider_id,
                    model_name=model_name,
                    raw=raw,
                    usage=chunk.get("usage"),
                )
            )
        if not events:
            events.append(
                ProviderStreamEvent(
                    event_type=ProviderStreamEventType.RAW,
                    provider_id=provider_id,
                    model_name=model_name,
                    raw=raw,
                )
            )
        return events

    def _events_from_content_tool_usage(
        self,
        payload: dict[str, Any],
        *,
        provider_id: str,
        model_name: str,
        raw: dict[str, Any],
        usage: Any = None,
    ) -> list[ProviderStreamEvent]:
        events: list[ProviderStreamEvent] = []
        if "content" in payload:
            events.append(
                ProviderStreamEvent(
                    event_type=ProviderStreamEventType.CONTENT_DELTA,
                    provider_id=provider_id,
                    model_name=model_name,
                    text=str(payload.get("content") or ""),
                    raw=raw,
                )
            )
        if "tool_calls" in payload:
            tool_calls = [
                dict(item)
                for item in (payload.get("tool_calls") or [])
                if isinstance(item, dict)
            ]
            events.append(
                ProviderStreamEvent(
                    event_type=ProviderStreamEventType.TOOL_CALL_DELTA,
                    provider_id=provider_id,
                    model_name=model_name,
                    tool_calls=tool_calls,
                    raw=raw,
                )
            )
        resolved_usage = usage if usage is not None else payload.get("usage")
        if isinstance(resolved_usage, dict):
            events.append(
                ProviderStreamEvent(
                    event_type=ProviderStreamEventType.USAGE,
                    provider_id=provider_id,
                    model_name=model_name,
                    usage=dict(resolved_usage),
                    raw=raw,
                )
            )
        return events

    def _extract_openai_choice_delta(self, chunk: dict[str, Any]) -> dict[str, Any]:
        choices = chunk.get("choices")
        if not isinstance(choices, list) or not choices:
            return {}
        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            return {}
        delta = first_choice.get("delta")
        if isinstance(delta, dict):
            return dict(delta)
        message = first_choice.get("message")
        if isinstance(message, dict):
            return dict(message)
        return {}

    def _normalize_responses_chunk(
        self,
        chunk: dict[str, Any],
        *,
        provider_id: str,
        model_name: str,
        raw: dict[str, Any],
    ) -> list[ProviderStreamEvent]:
        event_type = str(chunk.get("type") or "").strip()
        if not event_type.startswith("response."):
            return []
        if event_type in {"response.output_text.delta", "response.refusal.delta"}:
            return [
                ProviderStreamEvent(
                    event_type=ProviderStreamEventType.CONTENT_DELTA,
                    provider_id=provider_id,
                    model_name=model_name,
                    text=str(chunk.get("delta") or ""),
                    raw=raw,
                )
            ]
        if event_type == "response.function_call_arguments.delta":
            return [
                ProviderStreamEvent(
                    event_type=ProviderStreamEventType.TOOL_CALL_DELTA,
                    provider_id=provider_id,
                    model_name=model_name,
                    tool_calls=[
                        {
                            "index": self._coerce_index(chunk.get("output_index")),
                            "id": str(chunk.get("item_id") or chunk.get("call_id") or "").strip(),
                            "function": {
                                "name": str(chunk.get("name") or "").strip(),
                                "arguments": str(chunk.get("delta") or ""),
                            },
                        }
                    ],
                    raw=raw,
                )
            ]
        response = chunk.get("response") if isinstance(chunk.get("response"), dict) else {}
        usage = response.get("usage") if isinstance(response, dict) else None
        if isinstance(usage, dict):
            return [
                ProviderStreamEvent(
                    event_type=ProviderStreamEventType.USAGE,
                    provider_id=provider_id,
                    model_name=model_name,
                    usage=dict(usage),
                    raw=raw,
                )
            ]
        return [
            ProviderStreamEvent(
                event_type=ProviderStreamEventType.RAW,
                provider_id=provider_id,
                model_name=model_name,
                raw=raw,
            )
        ]

    def _coerce_index(self, value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def normalize_chunks(self, chunks: Iterable[dict[str, Any]]) -> list[ProviderStreamEvent]:
        events: list[ProviderStreamEvent] = []
        for chunk in chunks:
            events.extend(self.normalize_chunk(chunk))
        return events

    def build_step_result(
        self,
        events: Iterable[ProviderStreamEvent],
        *,
        max_tool_calls: int | None = None,
    ) -> Any:
        from services.agent_runtime.v2.llm_step import LLMStepResult

        collector = ToolCallCollector()
        content_parts: list[str] = []
        usage: dict[str, Any] = {}
        provider_id = self.provider_id
        model_name = self.model_name
        error: dict[str, Any] | None = None
        for event in events:
            provider_id = str(event.provider_id or provider_id).strip()
            model_name = str(event.model_name or model_name).strip()
            if event.event_type == ProviderStreamEventType.CONTENT_DELTA:
                content_parts.append(event.text)
            elif event.event_type == ProviderStreamEventType.TOOL_CALL_DELTA:
                collector.add_chunk({"tool_calls": event.tool_calls})
            elif event.event_type == ProviderStreamEventType.USAGE:
                usage = dict(event.usage)
            elif event.event_type == ProviderStreamEventType.ERROR:
                error = dict(event.error)
                break
        return LLMStepResult(
            content="".join(content_parts),
            tool_calls=collector.list_tool_calls(limit=max_tool_calls),
            usage=usage,
            provider_id=provider_id,
            model_name=model_name,
            error=error,
        )
