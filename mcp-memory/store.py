"""记忆存储层 — SQLite 实现"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Enums ──

class MemoryType(str, Enum):
    PROJECT_CONTEXT = "project-context"
    USER_PREFERENCE = "user-preference"
    KEY_EVENT = "key-event"
    LEARNED_PATTERN = "learned-pattern"
    LONG_TERM_GOAL = "long-term-goal"
    TABOO = "taboo"
    STABLE_PREFERENCE = "stable-preference"
    DECISION_PATTERN = "decision-pattern"


class MemoryScope(str, Enum):
    EMPLOYEE_PRIVATE = "employee-private"
    TEAM_SHARED = "team-shared"
    GLOBAL_VERIFIED = "global-verified"


class Classification(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


# ── Data Models ──

@dataclass(frozen=True)
class Memory:
    id: str
    employee_id: str
    type: MemoryType
    content: str
    project_name: str = ""
    importance: float = 0.5
    scope: MemoryScope = MemoryScope.EMPLOYEE_PRIVATE
    classification: Classification = Classification.INTERNAL
    purpose_tags: tuple[str, ...] = ()
    access_count: int = 0
    last_accessed: str = ""
    ttl_days: int = 90
    related_rules: tuple[str, ...] = ()
    related_memories: tuple[str, ...] = ()
    created_at: str = field(default_factory=_now_iso)
    expires_at: str = ""


# ── SQLite Schema ──

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    employee_id TEXT NOT NULL,
    project_name TEXT DEFAULT '',
    type TEXT NOT NULL,
    content TEXT NOT NULL,
    importance REAL DEFAULT 0.5,
    scope TEXT DEFAULT 'employee-private',
    classification TEXT DEFAULT 'internal',
    purpose_tags TEXT DEFAULT '[]',
    access_count INTEGER DEFAULT 0,
    last_accessed TEXT DEFAULT '',
    ttl_days INTEGER DEFAULT 90,
    related_rules TEXT DEFAULT '[]',
    related_memories TEXT DEFAULT '[]',
    created_at TEXT NOT NULL,
    expires_at TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_employee ON memories(employee_id);
CREATE INDEX IF NOT EXISTS idx_type ON memories(type);
"""


# ── Serialization helpers ──

def _row_to_memory(row: sqlite3.Row) -> Memory:
    return Memory(
        id=row["id"], employee_id=row["employee_id"],
        project_name=row["project_name"] if "project_name" in row.keys() else "",
        type=MemoryType(row["type"]), content=row["content"],
        importance=row["importance"], scope=MemoryScope(row["scope"]),
        classification=Classification(row["classification"]),
        purpose_tags=tuple(json.loads(row["purpose_tags"])),
        access_count=row["access_count"],
        last_accessed=row["last_accessed"],
        ttl_days=row["ttl_days"],
        related_rules=tuple(json.loads(row["related_rules"])),
        related_memories=tuple(json.loads(row["related_memories"])),
        created_at=row["created_at"],
        expires_at=row["expires_at"],
    )


def serialize_memory(m: Memory) -> dict:
    return {
        "id": m.id, "employee_id": m.employee_id,
        "project_name": m.project_name,
        "type": m.type.value, "content": m.content,
        "importance": m.importance, "scope": m.scope.value,
        "classification": m.classification.value,
        "purpose_tags": list(m.purpose_tags),
        "access_count": m.access_count,
        "last_accessed": m.last_accessed,
        "ttl_days": m.ttl_days,
        "related_rules": list(m.related_rules),
        "related_memories": list(m.related_memories),
        "created_at": m.created_at,
        "expires_at": m.expires_at,
    }


# ── MemoryStore ──

class MemoryStore:
    """基于 SQLite 的记忆存储"""

    def __init__(self, db_path: Path) -> None:
        self._db = sqlite3.connect(str(db_path))
        self._db.row_factory = sqlite3.Row
        self._db.executescript(_SCHEMA)
        self._ensure_columns()

    def _ensure_columns(self) -> None:
        columns = {
            row["name"]
            for row in self._db.execute("PRAGMA table_info(memories)").fetchall()
        }
        if "project_name" not in columns:
            self._db.execute("ALTER TABLE memories ADD COLUMN project_name TEXT DEFAULT ''")
            self._db.commit()

    def new_id(self) -> str:
        return f"mem-{uuid.uuid4().hex[:8]}"

    def save(self, m: Memory) -> None:
        self._db.execute(
            """INSERT OR REPLACE INTO memories
               (id, employee_id, project_name, type, content, importance, scope,
                classification, purpose_tags, access_count, last_accessed,
                ttl_days, related_rules, related_memories, created_at, expires_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (m.id, m.employee_id, m.project_name, m.type.value, m.content,
             m.importance, m.scope.value, m.classification.value,
             json.dumps(list(m.purpose_tags)),
             m.access_count, m.last_accessed, m.ttl_days,
             json.dumps(list(m.related_rules)),
             json.dumps(list(m.related_memories)),
             m.created_at, m.expires_at),
        )
        self._db.commit()

    def get(self, memory_id: str) -> Optional[Memory]:
        row = self._db.execute(
            "SELECT * FROM memories WHERE id = ?", (memory_id,)
        ).fetchone()
        return _row_to_memory(row) if row else None

    def delete(self, memory_id: str) -> bool:
        cur = self._db.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        self._db.commit()
        return cur.rowcount > 0

    @staticmethod
    def _normalized_project_name(project_name: str = "") -> str:
        return str(project_name or "").strip()

    def recall(self, employee_id: str, query: str = "",
               limit: int = 10, project_name: str = "") -> list[Memory]:
        normalized_project_name = self._normalized_project_name(project_name)
        if query:
            sql = """SELECT * FROM memories WHERE employee_id = ?
                   AND content LIKE ?"""
            params: list[object] = [employee_id, f"%{query}%"]
        else:
            sql = """SELECT * FROM memories WHERE employee_id = ?"""
            params = [employee_id]
        if normalized_project_name:
            sql += " AND project_name = ?"
            params.append(normalized_project_name)
        sql += " ORDER BY importance DESC LIMIT ?"
        params.append(limit)
        rows = self._db.execute(sql, tuple(params)).fetchall()
        # 更新访问计数
        for row in rows:
            self._db.execute(
                """UPDATE memories SET access_count = access_count + 1,
                   last_accessed = ? WHERE id = ?""",
                (_now_iso(), row["id"]),
        )
        self._db.commit()
        return [_row_to_memory(r) for r in rows]

    def recent(self, employee_id: str, limit: int = 10, project_name: str = "") -> list[Memory]:
        normalized_project_name = self._normalized_project_name(project_name)
        sql = """SELECT * FROM memories WHERE employee_id = ?"""
        params: list[object] = [employee_id]
        if normalized_project_name:
            sql += " AND project_name = ?"
            params.append(normalized_project_name)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = self._db.execute(sql, tuple(params)).fetchall()
        return [_row_to_memory(r) for r in rows]

    def important(self, employee_id: str, limit: int = 10, project_name: str = "") -> list[Memory]:
        normalized_project_name = self._normalized_project_name(project_name)
        sql = """SELECT * FROM memories WHERE employee_id = ?
               AND importance >= 0.7"""
        params: list[object] = [employee_id]
        if normalized_project_name:
            sql += " AND project_name = ?"
            params.append(normalized_project_name)
        sql += " ORDER BY importance DESC LIMIT ?"
        params.append(limit)
        rows = self._db.execute(sql, tuple(params)).fetchall()
        return [_row_to_memory(r) for r in rows]

    def compress(self, employee_id: str, keep_top: int = 50) -> int:
        """压缩记忆：保留重要的，删除低价值的"""
        all_mems = self.list_by_employee(employee_id)
        if len(all_mems) <= keep_top:
            return 0
        sorted_mems = sorted(all_mems, key=lambda m: m.importance, reverse=True)
        to_delete = sorted_mems[keep_top:]
        for m in to_delete:
            self.delete(m.id)
        return len(to_delete)

    def update_classification(self, memory_id: str,
                              classification: str,
                              purpose_tags: list[str]) -> bool:
        cur = self._db.execute(
            """UPDATE memories SET classification = ?,
               purpose_tags = ? WHERE id = ?""",
            (classification, json.dumps(purpose_tags), memory_id),
        )
        self._db.commit()
        return cur.rowcount > 0

    def count(self, employee_id: str, project_name: str = "") -> int:
        normalized_project_name = self._normalized_project_name(project_name)
        sql = "SELECT COUNT(*) as cnt FROM memories WHERE employee_id = ?"
        params: list[object] = [employee_id]
        if normalized_project_name:
            sql += " AND project_name = ?"
            params.append(normalized_project_name)
        row = self._db.execute(sql, tuple(params)).fetchone()
        return row["cnt"] if row else 0

    def list_by_employee(self, employee_id: str,
                         mem_type: Optional[MemoryType] = None,
                         project_name: str = "") -> list[Memory]:
        normalized_project_name = self._normalized_project_name(project_name)
        if mem_type:
            sql = "SELECT * FROM memories WHERE employee_id = ? AND type = ?"
            params: list[object] = [employee_id, mem_type.value]
        else:
            sql = "SELECT * FROM memories WHERE employee_id = ?"
            params = [employee_id]
        if normalized_project_name:
            sql += " AND project_name = ?"
            params.append(normalized_project_name)
        rows = self._db.execute(sql, tuple(params)).fetchall()
        return [_row_to_memory(r) for r in rows]

    def list_all(self) -> list[Memory]:
        rows = self._db.execute("SELECT * FROM memories").fetchall()
        return [_row_to_memory(r) for r in rows]
