"""Gateway adapter boundaries for runtime entry points."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


@dataclass(frozen=True)
class RuntimeIntegrationEnvelope:
    source: str
    prompt: str = ""
    project_id: str = ""
    chat_session_id: str = ""
    session_id: str = ""
    user_id: str = ""
    channel_id: str = ""
    thread_id: str = ""
    delivery_target: str = ""
    schedule: str = ""
    context_from: tuple[str, ...] = ()
    attachments: tuple[dict[str, Any], ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def resume_key(self) -> str:
        parts = [self.project_id, self.chat_session_id, self.session_id, self.source]
        return ":".join(part for part in parts if part)

    def to_runtime_input(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "message": self.prompt,
            "project_id": self.project_id,
            "chat_session_id": self.chat_session_id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "channel_id": self.channel_id,
            "thread_id": self.thread_id,
            "delivery_target": self.delivery_target,
            "schedule": self.schedule,
            "context_from": list(self.context_from),
            "attachments": list(self.attachments),
            "metadata": dict(self.metadata),
            "resume_key": self.resume_key,
        }


@dataclass(frozen=True)
class RuntimeGatewayMessage:
    source: str
    text: str
    channel_id: str = ""
    user_id: str = ""
    project_id: str = ""
    chat_session_id: str = ""
    session_id: str = ""
    thread_id: str = ""
    delivery_target: str = ""
    schedule: str = ""
    context_from: tuple[str, ...] = ()
    attachments: tuple[dict[str, Any], ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def envelope(self) -> RuntimeIntegrationEnvelope:
        metadata = dict(self.metadata)
        delivery_target = str(
            metadata.get("delivery_target") or self.delivery_target or ""
        ).strip()
        schedule = str(metadata.get("schedule") or self.schedule or "").strip()
        raw_context_from = metadata.get("context_from") or self.context_from or ()
        if isinstance(raw_context_from, (list, tuple)):
            context_from = tuple(
                str(item or "").strip()
                for item in raw_context_from
                if str(item or "").strip()
            )
        else:
            context_from = ()
        return RuntimeIntegrationEnvelope(
            source=self.source,
            prompt=self.text,
            project_id=self.project_id,
            chat_session_id=self.chat_session_id,
            session_id=self.session_id,
            user_id=self.user_id,
            channel_id=self.channel_id,
            thread_id=self.thread_id,
            delivery_target=delivery_target,
            schedule=schedule,
            context_from=context_from,
            attachments=self.attachments,
            metadata=metadata,
        )

    def runtime_input(self) -> dict[str, Any]:
        return self.envelope().to_runtime_input()


@dataclass(frozen=True)
class RuntimeGatewayResponse:
    text: str = ""
    events: tuple[dict[str, Any], ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def empty(self) -> bool:
        return not self.text and not self.events


class RuntimeGatewayAdapter(Protocol):
    source: str

    def can_handle(self, message: RuntimeGatewayMessage) -> bool:
        ...

    def to_runtime_input(self, message: RuntimeGatewayMessage) -> dict[str, Any]:
        ...

    def from_runtime_output(self, output: dict[str, Any]) -> RuntimeGatewayResponse:
        ...


class BasicRuntimeGatewayAdapter:
    """Default adapter for CLI, project chat, and platform messages."""

    def __init__(self, source: str):
        self.source = str(source or "").strip()

    def can_handle(self, message: RuntimeGatewayMessage) -> bool:
        return not self.source or message.source == self.source

    def to_runtime_input(self, message: RuntimeGatewayMessage) -> dict[str, Any]:
        return message.runtime_input()

    def from_runtime_output(self, output: dict[str, Any]) -> RuntimeGatewayResponse:
        if not isinstance(output, dict):
            return RuntimeGatewayResponse(text=str(output or ""))
        events = output.get("events") or ()
        if isinstance(events, list):
            events = tuple(event for event in events if isinstance(event, dict))
        return RuntimeGatewayResponse(
            text=str(output.get("text") or output.get("content") or ""),
            events=tuple(events),
            metadata=dict(output.get("metadata") or {}),
        )


class RuntimeGatewayRouter:
    """Routes platform messages into a single runtime input shape."""

    def __init__(self, adapters: list[RuntimeGatewayAdapter] | None = None):
        self._adapters: list[RuntimeGatewayAdapter] = list(adapters or [])

    def register(self, adapter: RuntimeGatewayAdapter) -> RuntimeGatewayAdapter:
        self._adapters.append(adapter)
        return adapter

    def adapter_for(self, message: RuntimeGatewayMessage) -> RuntimeGatewayAdapter | None:
        for adapter in self._adapters:
            if adapter.can_handle(message):
                return adapter
        return None

    def to_runtime_input(self, message: RuntimeGatewayMessage) -> dict[str, Any]:
        adapter = self.adapter_for(message)
        if adapter is None:
            return message.runtime_input()
        return adapter.to_runtime_input(message)

    def from_runtime_output(
        self,
        message: RuntimeGatewayMessage,
        output: dict[str, Any],
    ) -> RuntimeGatewayResponse:
        adapter = self.adapter_for(message)
        if adapter is None:
            return BasicRuntimeGatewayAdapter(message.source).from_runtime_output(output)
        return adapter.from_runtime_output(output)

    def dispatch(
        self,
        message: RuntimeGatewayMessage,
        handler: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> RuntimeGatewayResponse:
        runtime_input = self.to_runtime_input(message)
        return self.from_runtime_output(message, handler(runtime_input))


__all__ = [
    "BasicRuntimeGatewayAdapter",
    "RuntimeGatewayAdapter",
    "RuntimeGatewayMessage",
    "RuntimeGatewayResponse",
    "RuntimeGatewayRouter",
]
