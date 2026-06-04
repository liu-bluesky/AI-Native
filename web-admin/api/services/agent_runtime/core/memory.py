"""Memory and session-search boundaries for agent runtimes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class MemoryQuery:
    query: str
    project_id: str = ""
    chat_session_id: str = ""
    session_id: str = ""
    user_id: str = ""
    source: str = ""
    tags: tuple[str, ...] = ()
    limit: int = 10
    metadata_filter: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MemoryRecord:
    memory_id: str
    content: str
    source: str = "runtime"
    score: float = 0.0
    project_id: str = ""
    chat_session_id: str = ""
    session_id: str = ""
    user_id: str = ""
    tags: tuple[str, ...] = ()
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "content": self.content,
            "source": self.source,
            "score": self.score,
            "project_id": self.project_id,
            "chat_session_id": self.chat_session_id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "tags": list(self.tags),
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class MemorySearchResult:
    query: MemoryQuery
    records: tuple[MemoryRecord, ...] = ()
    backend: str = ""

    @property
    def total(self) -> int:
        return len(self.records)

    def summary(self) -> dict[str, Any]:
        return {
            "query": self.query.query,
            "backend": self.backend,
            "total": self.total,
            "records": [record.summary() for record in self.records],
        }


class AgentMemoryIndex(Protocol):
    """Search boundary for future project memory and session stores."""

    def search(self, query: MemoryQuery) -> MemorySearchResult:
        ...

    def remember(self, record: MemoryRecord) -> MemoryRecord:
        ...


class InMemoryAgentMemoryIndex:
    """Small test adapter for the memory boundary."""

    def __init__(self, records: list[MemoryRecord] | None = None, *, backend: str = "memory"):
        self._backend = backend
        self._records: list[MemoryRecord] = list(records or [])

    def remember(self, record: MemoryRecord) -> MemoryRecord:
        self._records.append(record)
        return record

    def search(self, query: MemoryQuery) -> MemorySearchResult:
        text = str(query.query or "").strip().lower()
        records = [
            record
            for record in self._records
            if _record_matches_query(record, query, text=text)
        ][: max(0, int(query.limit))]
        return MemorySearchResult(
            query=query,
            records=tuple(records),
            backend=self._backend,
        )


def _record_matches_query(record: MemoryRecord, query: MemoryQuery, *, text: str) -> bool:
    if query.project_id and record.project_id != query.project_id:
        return False
    if query.chat_session_id and record.chat_session_id != query.chat_session_id:
        return False
    if query.session_id and record.session_id != query.session_id:
        return False
    if query.user_id and record.user_id != query.user_id:
        return False
    if query.source and record.source != query.source:
        return False
    if query.tags and not set(query.tags).issubset(set(record.tags)):
        return False
    for key, value in query.metadata_filter.items():
        if record.metadata.get(key) != value:
            return False
    return not text or text in record.content.lower()


__all__ = [
    "AgentMemoryIndex",
    "InMemoryAgentMemoryIndex",
    "MemoryQuery",
    "MemoryRecord",
    "MemorySearchResult",
]
