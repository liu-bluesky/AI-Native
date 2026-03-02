"""MCP 服务 Store 桥接层 — 用 importlib 按路径加载，消灭 sys.path hack"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

_BASE = Path(__file__).resolve().parent.parent.parent


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

# ── Store 实例 ──

skill_store = _skills_mod.SkillStore(_BASE / "mcp-skills" / "knowledge")
binding_store = _skills_mod.BindingStore(_BASE / "mcp-skills" / "knowledge")
rule_store = _rules_mod.RuleStore(_BASE / "mcp-rules" / "knowledge")
memory_store = _memory_mod.MemoryStore(_BASE / "mcp-memory" / "knowledge" / "memories.db")
persona_store = _persona_mod.PersonaStore(_BASE / "mcp-persona" / "knowledge")
snapshot_store = _persona_mod.SnapshotStore(_BASE / "mcp-persona" / "knowledge")
candidate_store = _evolution_mod.CandidateStore(_BASE / "mcp-evolution" / "knowledge")
event_store = _evolution_mod.EventStore(_BASE / "mcp-evolution" / "knowledge")
usage_log_store = _evolution_mod.UsageLogStore(_BASE / "mcp-evolution" / "knowledge")
sync_store = _sync_mod.SyncEventStore(_BASE / "mcp-sync" / "knowledge")

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
