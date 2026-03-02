"""MCP 服务 Store 桥接层 — 用 importlib 按路径加载，消灭 sys.path hack"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType
from urllib.parse import quote

_BASE = Path(__file__).resolve().parent.parent.parent
DEFAULT_DEV_DATABASE_URL = "postgresql://admin:changeme@127.0.0.1:5432/ai_employee"


def _load_store(service_name: str) -> ModuleType:
    """按文件路径加载 mcp-{service}/store.py，避免同名模块冲突"""
    store_path = _BASE / f"mcp-{service_name}" / "store.py"
    module_name = f"mcp_{service_name}_store"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, store_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load store module from: {store_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return mod


# ── 加载各服务 Store 模块 ──

_skills_mod = _load_store("skills")
_rules_mod = _load_store("rules")
_memory_mod = _load_store("memory")
_persona_mod = _load_store("persona")
_evolution_mod = _load_store("evolution")
_sync_mod = _load_store("sync")

# ── 序列化函数 ──

serialize_skill = _skills_mod._serialize_skill
serialize_rule = _rules_mod._serialize_rule
serialize_memory = _memory_mod.serialize_memory
serialize_persona = _persona_mod._serialize_persona
serialize_candidate = _evolution_mod.serialize_candidate
serialize_sync_event = _sync_mod.serialize_event

# ── 数据类（供 router 层使用） ──

EmployeeSkillBinding = _skills_mod.EmployeeSkillBinding

Skill = _skills_mod.Skill
ToolDef = _skills_mod.ToolDef
ResourceDef = _skills_mod.ResourceDef
Rule = _rules_mod.Rule
Persona = _persona_mod.Persona

Severity = _rules_mod.Severity
RiskDomain = _rules_mod.RiskDomain

DecisionPolicy = _persona_mod.DecisionPolicy
DelegationScope = _persona_mod.DelegationScope
DriftControl = _persona_mod.DriftControl

# ── 辅助函数（各模块的 _now_iso，前缀命名避免冲突） ──

skills_now_iso = _skills_mod._now_iso
rules_now_iso = _rules_mod._now_iso
persona_now_iso = _persona_mod._now_iso

# ── 反序列化函数 ──

deserialize_skill = _skills_mod._deserialize_skill
deserialize_rule = _rules_mod._deserialize_rule
deserialize_persona = _persona_mod._deserialize_persona


def _build_database_url_from_env() -> str | None:
    database_url = str(os.environ.get("DATABASE_URL", "")).strip()
    if database_url:
        return database_url

    host = str(os.environ.get("DB_HOST", "")).strip()
    port = str(os.environ.get("DB_PORT", "5432")).strip() or "5432"
    user = str(os.environ.get("DB_USER", "")).strip()
    password = str(os.environ.get("DB_PASSWORD", "")).strip()
    db_name = str(os.environ.get("DB_NAME", "")).strip()
    if not (host and user and password and db_name):
        return DEFAULT_DEV_DATABASE_URL
    return f"postgresql://{quote(user)}:{quote(password)}@{host}:{port}/{quote(db_name)}"


def _create_json_stores() -> tuple:
    return (
        _skills_mod.SkillStore(_BASE / "mcp-skills" / "knowledge"),
        _skills_mod.BindingStore(_BASE / "mcp-skills" / "knowledge"),
        _rules_mod.RuleStore(_BASE / "mcp-rules" / "knowledge"),
        _memory_mod.MemoryStore(_BASE / "mcp-memory" / "knowledge" / "memories.db"),
        _persona_mod.PersonaStore(_BASE / "mcp-persona" / "knowledge"),
        _persona_mod.SnapshotStore(_BASE / "mcp-persona" / "knowledge"),
        _evolution_mod.CandidateStore(_BASE / "mcp-evolution" / "knowledge"),
        _evolution_mod.EventStore(_BASE / "mcp-evolution" / "knowledge"),
        _evolution_mod.UsageLogStore(_BASE / "mcp-evolution" / "knowledge"),
        _sync_mod.SyncEventStore(_BASE / "mcp-sync" / "knowledge"),
    )


def _create_postgres_stores(database_url: str) -> tuple:
    try:
        from stores_pg import (
            PgBindingStore,
            PgCandidateStore,
            PgEventStore,
            PgMemoryStore,
            PgPersonaStore,
            PgRuleStore,
            PgSkillStore,
            PgSnapshotStore,
            PgSyncEventStore,
            PgUsageLogStore,
        )
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "CORE_STORE_BACKEND=postgres 但未安装 PostgreSQL 驱动。"
            "请安装依赖: psycopg[binary]>=3.2。"
        ) from exc

    return (
        PgSkillStore(
            database_url,
            _BASE / "mcp-skills" / "knowledge",
            serialize_skill,
            deserialize_skill,
        ),
        PgBindingStore(database_url, EmployeeSkillBinding),
        PgRuleStore(database_url, serialize_rule, deserialize_rule),
        PgMemoryStore(
            database_url,
            _memory_mod.Memory,
            _memory_mod.MemoryType,
            _memory_mod.MemoryScope,
            _memory_mod.Classification,
            serialize_memory,
        ),
        PgPersonaStore(database_url, serialize_persona, deserialize_persona),
        PgSnapshotStore(database_url, _persona_mod.PersonaSnapshot),
        PgCandidateStore(database_url, serialize_candidate, _evolution_mod._deserialize_candidate),
        PgEventStore(database_url, _evolution_mod.EvolutionEvent),
        PgUsageLogStore(database_url, _evolution_mod.UsageLog),
        PgSyncEventStore(database_url, _sync_mod.SyncEvent, serialize_sync_event),
    )


_core_store_backend = str(os.environ.get("CORE_STORE_BACKEND", "postgres")).strip().lower()
if _core_store_backend == "json":
    (
        skill_store,
        binding_store,
        rule_store,
        memory_store,
        persona_store,
        snapshot_store,
        candidate_store,
        event_store,
        usage_log_store,
        sync_store,
    ) = _create_json_stores()
elif _core_store_backend == "postgres":
    _database_url = _build_database_url_from_env()
    if not _database_url:
        raise RuntimeError(
            "CORE_STORE_BACKEND=postgres 但未提供有效数据库配置。"
            "请设置 DATABASE_URL 或 DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME。"
        )
    (
        skill_store,
        binding_store,
        rule_store,
        memory_store,
        persona_store,
        snapshot_store,
        candidate_store,
        event_store,
        usage_log_store,
        sync_store,
    ) = _create_postgres_stores(_database_url)
else:
    raise RuntimeError(f"Unsupported CORE_STORE_BACKEND: {_core_store_backend}")
