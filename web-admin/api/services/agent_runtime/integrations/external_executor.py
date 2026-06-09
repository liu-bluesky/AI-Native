"""Adapters for external executor runner streams."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator

from services.agent_runtime.shared.external_executor_protocol import (
    ExternalExecutorEvent,
    ExternalExecutorTaskInput,
    ExternalExecutorType,
    normalize_external_executor_type,
)


@dataclass(frozen=True)
class CodexRunnerStreamAdapter:
    """Normalizes Codex runner NDJSON events into the external executor protocol."""

    task_node_id: str = ""
    executor_type: str = ExternalExecutorType.CODEX_CLI.value
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_task_input(
        cls,
        task_input: ExternalExecutorTaskInput | dict[str, Any],
    ) -> "CodexRunnerStreamAdapter":
        source = (
            task_input.to_dict()
            if isinstance(task_input, ExternalExecutorTaskInput)
            else dict(task_input or {})
        )
        return cls(
            task_node_id=str(source.get("task_node_id") or "").strip(),
            executor_type=normalize_external_executor_type(source.get("executor_type")),
            metadata=dict(source.get("metadata") or {})
            if isinstance(source.get("metadata"), dict)
            else {},
        )

    def normalize_event(self, payload: dict[str, Any] | Any) -> ExternalExecutorEvent:
        source = payload if isinstance(payload, dict) else {"type": "chunk", "data": payload}
        return ExternalExecutorEvent.from_runner_event(
            source,
            task_node_id=self.task_node_id,
            executor_type=self.executor_type,
        )

    def iter_events(
        self,
        payloads: Iterable[dict[str, Any] | Any],
    ) -> Iterator[ExternalExecutorEvent]:
        for payload in payloads:
            yield self.normalize_event(payload)

    def iter_event_dicts(
        self,
        payloads: Iterable[dict[str, Any] | Any],
    ) -> Iterator[dict[str, Any]]:
        for event in self.iter_events(payloads):
            yield event.to_dict()

    def iter_ndjson_lines(
        self,
        payloads: Iterable[dict[str, Any] | Any],
    ) -> Iterator[str]:
        for event in self.iter_event_dicts(payloads):
            yield json.dumps(event, ensure_ascii=False)


def normalize_codex_runner_events(
    payloads: Iterable[dict[str, Any] | Any],
    *,
    task_node_id: str = "",
    executor_type: str = ExternalExecutorType.CODEX_CLI.value,
) -> tuple[dict[str, Any], ...]:
    adapter = CodexRunnerStreamAdapter(
        task_node_id=task_node_id,
        executor_type=executor_type,
    )
    return tuple(adapter.iter_event_dicts(payloads))


__all__ = [
    "CodexRunnerStreamAdapter",
    "normalize_codex_runner_events",
]
