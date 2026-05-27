"""Collect streaming tool call chunks into executable tool calls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class CollectedToolCall:
    call_id: str
    tool_name: str
    arguments: str
    raw: dict[str, Any]

    def to_openai_tool_call(self) -> dict[str, Any]:
        return {
            "id": self.call_id,
            "type": "function",
            "function": {
                "name": self.tool_name,
                "arguments": self.arguments,
            },
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "raw": dict(self.raw),
        }


class ToolCallCollector:
    def __init__(self):
        self._buffer: dict[int, dict[str, Any]] = {}

    def add_chunk(self, chunk: dict[str, Any]) -> None:
        for item in chunk.get("tool_calls") or []:
            if not isinstance(item, dict):
                continue
            index = self._coerce_index(item.get("index"))
            current = self._buffer.setdefault(
                index,
                {
                    "id": str(item.get("id") or "").strip(),
                    "type": "function",
                    "function": {"name": "", "arguments": ""},
                },
            )
            if item.get("id"):
                current["id"] = str(item.get("id") or "").strip()
            function = current.setdefault("function", {"name": "", "arguments": ""})
            if "name" in item:
                function["name"] = str(function.get("name") or "") + str(item.get("name") or "")
            if "arguments" in item:
                function["arguments"] = str(function.get("arguments") or "") + str(item.get("arguments") or "")
            nested = item.get("function")
            if isinstance(nested, dict):
                if "name" in nested:
                    function["name"] = str(function.get("name") or "") + str(nested.get("name") or "")
                if "arguments" in nested:
                    function["arguments"] = str(function.get("arguments") or "") + str(nested.get("arguments") or "")

    def list_tool_calls(self, *, limit: int | None = None) -> list[CollectedToolCall]:
        calls: list[CollectedToolCall] = []
        for index in sorted(self._buffer):
            raw = self._buffer[index]
            function = raw.get("function") if isinstance(raw.get("function"), dict) else {}
            tool_name = str(function.get("name") or "").strip()
            if not tool_name:
                continue
            call_id = str(raw.get("id") or "").strip() or f"call_{index}"
            calls.append(
                CollectedToolCall(
                    call_id=call_id,
                    tool_name=tool_name,
                    arguments=str(function.get("arguments") or ""),
                    raw={
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": str(function.get("arguments") or ""),
                        },
                    },
                )
            )
            if limit is not None and len(calls) >= max(1, int(limit)):
                break
        return calls

    def has_tool_calls(self) -> bool:
        return bool(self.list_tool_calls())

    def _coerce_index(self, value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0
