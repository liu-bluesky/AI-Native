"""PostgreSQL-backed adapters for MCP bridge stores."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from psycopg import connect
from psycopg.rows import dict_row


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_dumps(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False)


class _PgStoreBase:
    def __init__(self, database_url: str) -> None:
        self._conn = connect(database_url, autocommit=True, row_factory=dict_row)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        raise NotImplementedError


class PgSkillStore(_PgStoreBase):
    def __init__(
        self,
        database_url: str,
        data_dir: Path,
        serialize_skill: Callable[[Any], dict],
        deserialize_skill: Callable[[dict], Any],
    ) -> None:
        self._serialize_skill = serialize_skill
        self._deserialize_skill = deserialize_skill
        self._packages_dir = data_dir / "skill-packages"
        self._packages_dir.mkdir(parents=True, exist_ok=True)
        super().__init__(database_url)

    def _ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS skills (
                    id TEXT PRIMARY KEY,
                    payload JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )

    def package_path(self, skill_id: str) -> Path:
        return self._packages_dir / skill_id

    def save(self, skill: Any) -> None:
        payload = self._serialize_skill(skill)
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO skills (id, payload, updated_at)
                VALUES (%s, %s::jsonb, NOW())
                ON CONFLICT (id) DO UPDATE
                SET payload = EXCLUDED.payload, updated_at = NOW()
                """,
                (skill.id, _json_dumps(payload)),
            )

    def get(self, skill_id: str) -> Optional[Any]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT payload FROM skills WHERE id = %s", (skill_id,))
            row = cur.fetchone()
        return self._deserialize_skill(row["payload"]) if row else None

    def list_all(self) -> list[Any]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT payload FROM skills ORDER BY id")
            rows = cur.fetchall()
        return [self._deserialize_skill(r["payload"]) for r in rows]

    def query(self, tags: Optional[list[str]] = None, domain: Optional[str] = None) -> list[Any]:
        results = self.list_all()
        if tags:
            tag_set = {t.lower() for t in tags}
            results = [s for s in results if tag_set & {t.lower() for t in s.tags}]
        if domain:
            d = domain.lower()
            results = [
                s for s in results if d in {t.lower() for t in s.tags} or d in s.description.lower()
            ]
        return results

    def delete(self, skill_id: str) -> bool:
        with self._conn.cursor() as cur:
            cur.execute("DELETE FROM skills WHERE id = %s", (skill_id,))
            return cur.rowcount > 0

    def new_id(self) -> str:
        return f"skill-{uuid.uuid4().hex[:8]}"


class PgBindingStore(_PgStoreBase):
    def __init__(self, database_url: str, binding_cls: type) -> None:
        self._binding_cls = binding_cls
        super().__init__(database_url)

    def _ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS skill_bindings (
                    employee_id TEXT NOT NULL,
                    skill_id TEXT NOT NULL,
                    payload JSONB NOT NULL,
                    installed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (employee_id, skill_id)
                );
                """
            )

    def get_bindings(self, employee_id: str) -> list[Any]:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT payload FROM skill_bindings WHERE employee_id = %s ORDER BY installed_at DESC",
                (employee_id,),
            )
            rows = cur.fetchall()
        return [self._binding_cls(**r["payload"]) for r in rows]

    def add(self, binding: Any) -> None:
        payload = asdict(binding)
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO skill_bindings (employee_id, skill_id, payload, installed_at)
                VALUES (%s, %s, %s::jsonb, %s)
                ON CONFLICT (employee_id, skill_id) DO UPDATE
                SET payload = EXCLUDED.payload, installed_at = EXCLUDED.installed_at
                """,
                (binding.employee_id, binding.skill_id, _json_dumps(payload), binding.installed_at),
            )

    def remove(self, employee_id: str, skill_id: str) -> bool:
        with self._conn.cursor() as cur:
            cur.execute(
                "DELETE FROM skill_bindings WHERE employee_id = %s AND skill_id = %s",
                (employee_id, skill_id),
            )
            return cur.rowcount > 0


class PgRuleStore(_PgStoreBase):
    def __init__(
        self,
        database_url: str,
        serialize_rule: Callable[[Any], dict],
        deserialize_rule: Callable[[dict], Any],
    ) -> None:
        self._serialize_rule = serialize_rule
        self._deserialize_rule = deserialize_rule
        super().__init__(database_url)

    def _ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS rules (
                    id TEXT PRIMARY KEY,
                    domain TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    confidence DOUBLE PRECISION NOT NULL DEFAULT 0.5,
                    payload JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_rules_domain ON rules(domain);
                CREATE INDEX IF NOT EXISTS idx_rules_confidence ON rules(confidence DESC);
                """
            )

    def save(self, rule: Any) -> None:
        payload = self._serialize_rule(rule)
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO rules (id, domain, title, content, confidence, payload, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, NOW())
                ON CONFLICT (id) DO UPDATE
                SET domain = EXCLUDED.domain,
                    title = EXCLUDED.title,
                    content = EXCLUDED.content,
                    confidence = EXCLUDED.confidence,
                    payload = EXCLUDED.payload,
                    updated_at = NOW()
                """,
                (rule.id, rule.domain, rule.title, rule.content, float(rule.confidence), _json_dumps(payload)),
            )

    def get(self, rule_id: str) -> Optional[Any]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT payload FROM rules WHERE id = %s", (rule_id,))
            row = cur.fetchone()
        return self._deserialize_rule(row["payload"]) if row else None

    def delete(self, rule_id: str) -> bool:
        with self._conn.cursor() as cur:
            cur.execute("DELETE FROM rules WHERE id = %s", (rule_id,))
            return cur.rowcount > 0

    def list_all(self) -> list[Any]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT payload FROM rules ORDER BY id")
            rows = cur.fetchall()
        return [self._deserialize_rule(r["payload"]) for r in rows]

    def list_by_project(self, project_id: str) -> list[Any]:
        """兼容接口：当前规则模型未按 project 维度存储，先返回全量规则。"""
        _ = project_id
        return self.list_all()

    def query(self, keyword: str, domain: str = None) -> list[Any]:
        kw = f"%{keyword.lower()}%"
        if domain:
            sql = (
                "SELECT payload FROM rules WHERE domain = %s "
                "AND (LOWER(title) LIKE %s OR LOWER(content) LIKE %s) ORDER BY confidence DESC"
            )
            params = (domain, kw, kw)
        else:
            sql = "SELECT payload FROM rules WHERE LOWER(title) LIKE %s OR LOWER(content) LIKE %s ORDER BY confidence DESC"
            params = (kw, kw)
        with self._conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return [self._deserialize_rule(r["payload"]) for r in rows]

    def domains(self) -> list[str]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT DISTINCT domain FROM rules ORDER BY domain")
            rows = cur.fetchall()
        return [r["domain"] for r in rows]

    def record_usage(self, rule_id: str, adopted: bool) -> None:
        rule = self.get(rule_id)
        if rule is None:
            return
        new_use = rule.use_count + 1
        new_adopt = rule.adopt_count + (1 if adopted else 0)
        new_conf = round(new_adopt / new_use, 2) if new_use > 0 else rule.confidence
        updated = replace(
            rule,
            use_count=new_use,
            adopt_count=new_adopt,
            confidence=new_conf,
            updated_at=_now_iso(),
        )
        self.save(updated)

    def new_id(self) -> str:
        return f"rule-{uuid.uuid4().hex[:8]}"


class PgMemoryStore(_PgStoreBase):
    def __init__(
        self,
        database_url: str,
        memory_cls: type,
        memory_type_cls: type,
        memory_scope_cls: type,
        classification_cls: type,
        serialize_memory: Callable[[Any], dict],
    ) -> None:
        self._memory_cls = memory_cls
        self._memory_type_cls = memory_type_cls
        self._memory_scope_cls = memory_scope_cls
        self._classification_cls = classification_cls
        self._serialize_memory = serialize_memory
        super().__init__(database_url)

    def _ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    employee_id TEXT NOT NULL,
                    importance DOUBLE PRECISION NOT NULL DEFAULT 0.5,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    payload JSONB NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_memories_employee ON memories(employee_id);
                CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(employee_id, importance DESC);
                CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(employee_id, created_at DESC);
                """
            )

    def _deserialize_memory(self, data: dict) -> Any:
        return self._memory_cls(
            id=data["id"],
            employee_id=data["employee_id"],
            type=self._memory_type_cls(data["type"]),
            content=data["content"],
            project_name=str(data.get("project_name") or ""),
            importance=data.get("importance", 0.5),
            scope=self._memory_scope_cls(data.get("scope", "employee-private")),
            classification=self._classification_cls(data.get("classification", "internal")),
            purpose_tags=tuple(data.get("purpose_tags", [])),
            access_count=data.get("access_count", 0),
            last_accessed=data.get("last_accessed", ""),
            ttl_days=data.get("ttl_days", 90),
            related_rules=tuple(data.get("related_rules", [])),
            related_memories=tuple(data.get("related_memories", [])),
            created_at=data.get("created_at", _now_iso()),
            expires_at=data.get("expires_at", ""),
        )

    def new_id(self) -> str:
        return f"mem-{uuid.uuid4().hex[:8]}"

    def save(self, memory: Any) -> None:
        payload = self._serialize_memory(memory)
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO memories (id, employee_id, importance, created_at, payload)
                VALUES (%s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (id) DO UPDATE
                SET employee_id = EXCLUDED.employee_id,
                    importance = EXCLUDED.importance,
                    created_at = EXCLUDED.created_at,
                    payload = EXCLUDED.payload
                """,
                (
                    memory.id,
                    memory.employee_id,
                    float(memory.importance),
                    memory.created_at or _now_iso(),
                    _json_dumps(payload),
                ),
            )

    def get(self, memory_id: str) -> Optional[Any]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT payload FROM memories WHERE id = %s", (memory_id,))
            row = cur.fetchone()
        return self._deserialize_memory(row["payload"]) if row else None

    def delete(self, memory_id: str) -> bool:
        with self._conn.cursor() as cur:
            cur.execute("DELETE FROM memories WHERE id = %s", (memory_id,))
            return cur.rowcount > 0

    def list_by_employee(self, employee_id: str, mem_type: Optional[Any] = None) -> list[Any]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT payload FROM memories WHERE employee_id = %s", (employee_id,))
            rows = cur.fetchall()
        mems = [self._deserialize_memory(r["payload"]) for r in rows]
        if mem_type:
            mems = [m for m in mems if m.type == mem_type]
        return mems

    def recall(self, employee_id: str, query: str = "", limit: int = 10) -> list[Any]:
        mems = self.list_by_employee(employee_id)
        if query:
            q = query.lower()
            mems = [m for m in mems if q in m.content.lower()]
        mems = sorted(mems, key=lambda m: m.importance, reverse=True)[:limit]
        for memory in mems:
            updated = replace(memory, access_count=memory.access_count + 1, last_accessed=_now_iso())
            self.save(updated)
        return mems

    def recent(self, employee_id: str, limit: int = 10) -> list[Any]:
        mems = self.list_by_employee(employee_id)
        return sorted(mems, key=lambda m: m.created_at, reverse=True)[:limit]

    def important(self, employee_id: str, limit: int = 10) -> list[Any]:
        mems = [m for m in self.list_by_employee(employee_id) if m.importance >= 0.7]
        return sorted(mems, key=lambda m: m.importance, reverse=True)[:limit]

    def compress(self, employee_id: str, keep_top: int = 50) -> int:
        all_mems = self.list_by_employee(employee_id)
        if len(all_mems) <= keep_top:
            return 0
        sorted_mems = sorted(all_mems, key=lambda m: m.importance, reverse=True)
        to_delete = sorted_mems[keep_top:]
        for memory in to_delete:
            self.delete(memory.id)
        return len(to_delete)

    def update_classification(self, memory_id: str, classification: str, purpose_tags: list[str]) -> bool:
        memory = self.get(memory_id)
        if memory is None:
            return False
        updated = replace(
            memory,
            classification=self._classification_cls(classification),
            purpose_tags=tuple(purpose_tags),
        )
        self.save(updated)
        return True

    def count(self, employee_id: str) -> int:
        with self._conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM memories WHERE employee_id = %s", (employee_id,))
            row = cur.fetchone()
        return int(row["cnt"]) if row else 0


class PgPersonaStore(_PgStoreBase):
    def __init__(self, database_url: str, serialize_persona: Callable[[Any], dict], deserialize_persona: Callable[[dict], Any]) -> None:
        self._serialize_persona = serialize_persona
        self._deserialize_persona = deserialize_persona
        super().__init__(database_url)

    def _ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS personas (
                    id TEXT PRIMARY KEY,
                    payload JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )

    def save(self, persona: Any) -> None:
        payload = self._serialize_persona(persona)
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO personas (id, payload, updated_at)
                VALUES (%s, %s::jsonb, NOW())
                ON CONFLICT (id) DO UPDATE
                SET payload = EXCLUDED.payload, updated_at = NOW()
                """,
                (persona.id, _json_dumps(payload)),
            )

    def get(self, persona_id: str) -> Optional[Any]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT payload FROM personas WHERE id = %s", (persona_id,))
            row = cur.fetchone()
        return self._deserialize_persona(row["payload"]) if row else None

    def list_all(self) -> list[Any]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT payload FROM personas ORDER BY id")
            rows = cur.fetchall()
        return [self._deserialize_persona(r["payload"]) for r in rows]

    def delete(self, persona_id: str) -> bool:
        with self._conn.cursor() as cur:
            cur.execute("DELETE FROM personas WHERE id = %s", (persona_id,))
            return cur.rowcount > 0

    def new_id(self) -> str:
        return f"persona-{uuid.uuid4().hex[:8]}"


class PgSnapshotStore(_PgStoreBase):
    def __init__(self, database_url: str, snapshot_cls: type) -> None:
        self._snapshot_cls = snapshot_cls
        super().__init__(database_url)

    def _ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS persona_snapshots (
                    id TEXT PRIMARY KEY,
                    persona_id TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    payload JSONB NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_persona_snapshots_persona
                ON persona_snapshots (persona_id, created_at DESC);
                """
            )

    def save(self, snap: Any) -> None:
        payload = asdict(snap)
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO persona_snapshots (id, persona_id, created_at, payload)
                VALUES (%s, %s, %s, %s::jsonb)
                ON CONFLICT (id) DO UPDATE
                SET persona_id = EXCLUDED.persona_id,
                    created_at = EXCLUDED.created_at,
                    payload = EXCLUDED.payload
                """,
                (snap.id, snap.persona_id, snap.created_at, _json_dumps(payload)),
            )

    def list_by_persona(self, persona_id: str) -> list[Any]:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT payload FROM persona_snapshots WHERE persona_id = %s ORDER BY created_at DESC",
                (persona_id,),
            )
            rows = cur.fetchall()
        return [self._snapshot_cls(**r["payload"]) for r in rows]

    def get(self, snap_id: str) -> Optional[Any]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT payload FROM persona_snapshots WHERE id = %s", (snap_id,))
            row = cur.fetchone()
        return self._snapshot_cls(**row["payload"]) if row else None

    def new_id(self) -> str:
        return f"snap-{uuid.uuid4().hex[:8]}"


class PgCandidateStore(_PgStoreBase):
    def __init__(
        self,
        database_url: str,
        serialize_candidate: Callable[[Any], dict],
        deserialize_candidate: Callable[[dict], Any],
    ) -> None:
        self._serialize_candidate = serialize_candidate
        self._deserialize_candidate = deserialize_candidate
        super().__init__(database_url)

    def _ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS evolution_candidates (
                    id TEXT PRIMARY KEY,
                    employee_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    payload JSONB NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_evolution_candidates_employee_status
                ON evolution_candidates (employee_id, status, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_evolution_candidates_confidence
                ON evolution_candidates (confidence DESC);
                """
            )

    def save(self, candidate: Any) -> None:
        payload = self._serialize_candidate(candidate)
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO evolution_candidates (id, employee_id, status, confidence, created_at, payload)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (id) DO UPDATE
                SET employee_id = EXCLUDED.employee_id,
                    status = EXCLUDED.status,
                    confidence = EXCLUDED.confidence,
                    created_at = EXCLUDED.created_at,
                    payload = EXCLUDED.payload
                """,
                (
                    candidate.id,
                    candidate.employee_id,
                    candidate.status,
                    float(candidate.confidence),
                    candidate.created_at,
                    _json_dumps(payload),
                ),
            )

    def get(self, cid: str) -> Optional[Any]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT payload FROM evolution_candidates WHERE id = %s", (cid,))
            row = cur.fetchone()
        return self._deserialize_candidate(row["payload"]) if row else None

    def list_by_employee(self, employee_id: str, status: str = "") -> list[Any]:
        if status:
            sql = (
                "SELECT payload FROM evolution_candidates WHERE employee_id = %s AND status = %s ORDER BY created_at DESC"
            )
            params = (employee_id, status)
        else:
            sql = "SELECT payload FROM evolution_candidates WHERE employee_id = %s ORDER BY created_at DESC"
            params = (employee_id,)
        with self._conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return [self._deserialize_candidate(r["payload"]) for r in rows]

    def list_pending(self, min_confidence: float = 0.0, limit: int = 200) -> list[Any]:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT payload FROM evolution_candidates
                WHERE status = 'pending' AND confidence >= %s
                ORDER BY confidence DESC
                LIMIT %s
                """,
                (min_confidence, limit),
            )
            rows = cur.fetchall()
        return [self._deserialize_candidate(r["payload"]) for r in rows]

    def delete(self, cid: str) -> bool:
        with self._conn.cursor() as cur:
            cur.execute("DELETE FROM evolution_candidates WHERE id = %s", (cid,))
            return cur.rowcount > 0

    def new_id(self) -> str:
        return f"cand-{uuid.uuid4().hex[:8]}"


class PgEventStore(_PgStoreBase):
    def __init__(self, database_url: str, event_cls: type) -> None:
        self._event_cls = event_cls
        super().__init__(database_url)

    def _ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS evolution_events (
                    id TEXT PRIMARY KEY,
                    employee_id TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    payload JSONB NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_evolution_events_employee
                ON evolution_events (employee_id, created_at DESC);
                """
            )

    def save(self, event: Any) -> None:
        payload = asdict(event)
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO evolution_events (id, employee_id, created_at, payload)
                VALUES (%s, %s, %s, %s::jsonb)
                ON CONFLICT (id) DO UPDATE
                SET employee_id = EXCLUDED.employee_id,
                    created_at = EXCLUDED.created_at,
                    payload = EXCLUDED.payload
                """,
                (event.id, event.employee_id, event.created_at, _json_dumps(payload)),
            )

    def list_by_employee(self, employee_id: str, limit: int = 50) -> list[Any]:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT payload FROM evolution_events
                WHERE employee_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (employee_id, limit),
            )
            rows = cur.fetchall()
        return [self._event_cls(**r["payload"]) for r in rows]

    def new_id(self) -> str:
        return f"evt-{uuid.uuid4().hex[:8]}"


class PgUsageLogStore(_PgStoreBase):
    def __init__(self, database_url: str, usage_log_cls: type) -> None:
        self._usage_log_cls = usage_log_cls
        super().__init__(database_url)

    def _ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS evolution_usage_logs (
                    id TEXT PRIMARY KEY,
                    employee_id TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    payload JSONB NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_evolution_usage_logs_employee
                ON evolution_usage_logs (employee_id, created_at DESC);
                """
            )

    def save(self, log: Any) -> None:
        payload = asdict(log)
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO evolution_usage_logs (id, employee_id, created_at, payload)
                VALUES (%s, %s, %s, %s::jsonb)
                ON CONFLICT (id) DO UPDATE
                SET employee_id = EXCLUDED.employee_id,
                    created_at = EXCLUDED.created_at,
                    payload = EXCLUDED.payload
                """,
                (log.id, log.employee_id, log.created_at, _json_dumps(payload)),
            )

    def list_by_employee(self, employee_id: str, limit: int = 500) -> list[Any]:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT payload FROM evolution_usage_logs
                WHERE employee_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (employee_id, limit),
            )
            rows = cur.fetchall()
        return [self._usage_log_cls(**r["payload"]) for r in rows]

    def new_id(self) -> str:
        return f"log-{uuid.uuid4().hex[:8]}"


class PgSyncEventStore(_PgStoreBase):
    def __init__(self, database_url: str, sync_event_cls: type, serialize_event: Callable[[Any], dict]) -> None:
        self._sync_event_cls = sync_event_cls
        self._serialize_event = serialize_event
        super().__init__(database_url)

    def _ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS sync_events (
                    id TEXT PRIMARY KEY,
                    employee_id TEXT NOT NULL,
                    delivered BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    payload JSONB NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_sync_events_employee_created
                ON sync_events (employee_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_sync_events_employee_delivered
                ON sync_events (employee_id, delivered);
                """
            )

    def save(self, event: Any) -> None:
        payload = self._serialize_event(event)
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO sync_events (id, employee_id, delivered, created_at, payload)
                VALUES (%s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (id) DO UPDATE
                SET employee_id = EXCLUDED.employee_id,
                    delivered = EXCLUDED.delivered,
                    created_at = EXCLUDED.created_at,
                    payload = EXCLUDED.payload
                """,
                (event.id, event.employee_id, bool(event.delivered), event.created_at, _json_dumps(payload)),
            )

    def get(self, eid: str) -> Optional[Any]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT payload FROM sync_events WHERE id = %s", (eid,))
            row = cur.fetchone()
        return self._sync_event_cls(**row["payload"]) if row else None

    def list_by_employee(self, employee_id: str, limit: int = 20) -> list[Any]:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT payload FROM sync_events
                WHERE employee_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (employee_id, limit),
            )
            rows = cur.fetchall()
        return [self._sync_event_cls(**r["payload"]) for r in rows]

    def count(self, employee_id: str) -> int:
        with self._conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM sync_events WHERE employee_id = %s", (employee_id,))
            row = cur.fetchone()
        return int(row["cnt"]) if row else 0

    def pending_count(self, employee_id: str) -> int:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM sync_events WHERE employee_id = %s AND delivered = FALSE",
                (employee_id,),
            )
            row = cur.fetchone()
        return int(row["cnt"]) if row else 0

    def new_id(self) -> str:
        return f"sync-{uuid.uuid4().hex[:8]}"
