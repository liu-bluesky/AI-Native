"""记忆管理 MCP 服务入口"""

from __future__ import annotations

from pathlib import Path
import shutil
import sys

from mcp.server.fastmcp import FastMCP
from store import MemoryStore as LocalMemoryStore

LEGACY_DB_PATH = Path(__file__).parent / "memories.db"
DB_PATH = Path(__file__).parent / "knowledge" / "memories.db"


def _prepare_sqlite_memory_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not DB_PATH.exists() and LEGACY_DB_PATH.exists():
        shutil.copy2(LEGACY_DB_PATH, DB_PATH)


def _load_memory_runtime():
    api_dir = Path(__file__).resolve().parents[1] / "web-admin" / "api"
    if api_dir.is_dir():
        api_dir_str = str(api_dir)
        if api_dir_str not in sys.path:
            sys.path.insert(0, api_dir_str)
        try:
            from core.config import get_settings
            from stores.mcp_bridge import (
                Classification,
                Memory,
                MemoryScope,
                MemoryType,
                memory_store,
                serialize_memory,
            )
        except Exception as exc:  # pragma: no cover - startup failure should be explicit
            raise RuntimeError(f"Failed to load unified memory store from {api_dir}") from exc

        settings = get_settings()
        if settings.core_store_backend == "json":
            _prepare_sqlite_memory_db()
        return {
            "store": memory_store,
            "Memory": Memory,
            "MemoryType": MemoryType,
            "MemoryScope": MemoryScope,
            "Classification": Classification,
            "serialize_memory": serialize_memory,
            "store_backend": f"bridge-{settings.core_store_backend}",
        }

    _prepare_sqlite_memory_db()
    from store import (
        Classification,
        Memory,
        MemoryScope,
        MemoryStore,
        MemoryType,
        serialize_memory,
    )

    return {
        "store": MemoryStore(DB_PATH),
        "Memory": Memory,
        "MemoryType": MemoryType,
        "MemoryScope": MemoryScope,
        "Classification": Classification,
        "serialize_memory": serialize_memory,
        "store_backend": "local-json",
    }


def _sync_sqlite_memories_into_store(target_store, source_db_path: Path) -> int:
    if not source_db_path.exists():
        return 0
    source_store = LocalMemoryStore(source_db_path)
    imported = 0
    for memory in source_store.list_all():
        existing = None
        try:
            existing = target_store.get(memory.id)
        except Exception:
            existing = None
        if existing is not None:
            continue
        target_store.save(memory)
        imported += 1
    return imported


_RUNTIME = _load_memory_runtime()
store = _RUNTIME["store"]
Memory = _RUNTIME["Memory"]
MemoryType = _RUNTIME["MemoryType"]
MemoryScope = _RUNTIME["MemoryScope"]
Classification = _RUNTIME["Classification"]
serialize_memory = _RUNTIME["serialize_memory"]
STORE_BACKEND = _RUNTIME["store_backend"]
BOOTSTRAP_IMPORTED_COUNT = 0
if STORE_BACKEND == "bridge-postgres":
    _prepare_sqlite_memory_db()
    BOOTSTRAP_IMPORTED_COUNT = _sync_sqlite_memories_into_store(store, DB_PATH)

mcp = FastMCP("memory-service")

_IDENTITY_TYPES = {
    MemoryType.LONG_TERM_GOAL, MemoryType.TABOO,
    MemoryType.STABLE_PREFERENCE, MemoryType.DECISION_PATTERN,
}
_USER_QUESTION_PREFIX = "[用户提问]"


def _parse_memory_type(value: str) -> tuple:
    try:
        return MemoryType(value), None
    except ValueError:
        valid = [e.value for e in MemoryType]
        return None, {"error": f"Invalid type: {value}. Valid: {valid}"}


def _format_memory_content(content: str, max_len: int = 80) -> str:
    text = str(content or "")
    if text.startswith(_USER_QUESTION_PREFIX):
        return text
    if len(text) <= max_len:
        return text
    return text[:max_len]


# ── Tools ──

@mcp.tool()
def save_memory(
    employee_id: str, content: str, type: str,
    importance: float = 0.5,
    project_name: str = "",
) -> dict:
    """保存一条记忆"""
    mt, err = _parse_memory_type(type)
    if err:
        return err
    mem = Memory(
        id=store.new_id(), employee_id=employee_id,
        type=mt, content=content, importance=importance,
        project_name=str(project_name or "").strip(),
    )
    store.save(mem)
    return {"status": "saved", "memory_id": mem.id}


@mcp.tool()
def recall(employee_id: str, query: str = "", limit: int = 10) -> list[dict]:
    """检索记忆"""
    results = store.recall(employee_id, query, limit)
    return [serialize_memory(m) for m in results]


@mcp.tool()
def forget(memory_id: str) -> dict:
    """删除一条记忆"""
    if store.delete(memory_id):
        return {"status": "deleted", "memory_id": memory_id}
    return {"error": f"Memory {memory_id} not found"}


@mcp.tool()
def compress_memories(employee_id: str, keep_top: int = 50) -> dict:
    """压缩记忆：保留重要的，删除低价值的"""
    deleted = store.compress(employee_id, keep_top)
    remaining = store.count(employee_id)
    return {"status": "compressed", "deleted": deleted, "remaining": remaining}


@mcp.tool()
def save_identity_signal(
    employee_id: str, signal_type: str, content: str,
    importance: float = 0.9,
    project_name: str = "",
) -> dict:
    """保存身份信号记忆（数字分身核心）"""
    mt, err = _parse_memory_type(signal_type)
    if err:
        return err
    if mt not in _IDENTITY_TYPES:
        valid = [t.value for t in _IDENTITY_TYPES]
        return {"error": f"Not an identity signal type. Valid: {valid}"}
    mem = Memory(
        id=store.new_id(), employee_id=employee_id,
        type=mt, content=content, importance=importance,
        project_name=str(project_name or "").strip(),
    )
    store.save(mem)
    return {"status": "saved", "memory_id": mem.id, "signal_type": mt.value}


@mcp.tool()
def list_identity_signals(
    employee_id: str, signal_type: str = "",
) -> list[dict]:
    """查询身份信号记忆"""
    if signal_type:
        mt, err = _parse_memory_type(signal_type)
        if err:
            return err
        results = store.list_by_employee(employee_id, mt)
    else:
        results = []
        for t in _IDENTITY_TYPES:
            results.extend(store.list_by_employee(employee_id, t))
    return [serialize_memory(m) for m in results]


@mcp.tool()
def set_memory_classification(
    memory_id: str, level: str, purpose_tags: str = "",
) -> dict:
    """设置记忆分级与用途标签"""
    try:
        Classification(level)
    except ValueError:
        valid = [e.value for e in Classification]
        return {"error": f"Invalid level: {level}. Valid: {valid}"}
    tags = [t.strip() for t in purpose_tags.split(",") if t.strip()] if purpose_tags else []
    if store.update_classification(memory_id, level, tags):
        return {"status": "updated", "memory_id": memory_id}
    return {"error": f"Memory {memory_id} not found"}


# ── Resources ──

@mcp.resource("memory://{employee_id}/all")
def all_memories(employee_id: str) -> str:
    """所有记忆"""
    mems = store.list_by_employee(employee_id)
    lines = [f"[{m.id}] ({m.type.value}) {_format_memory_content(m.content)}" for m in mems]
    return "\n".join(lines) if lines else "暂无记忆"


@mcp.resource("memory://{employee_id}/recent")
def recent_memories(employee_id: str) -> str:
    """最近记忆"""
    mems = store.recent(employee_id)
    lines = [f"[{m.id}] ({m.type.value}) {_format_memory_content(m.content)}" for m in mems]
    return "\n".join(lines) if lines else "暂无记忆"


@mcp.resource("memory://{employee_id}/important")
def important_memories(employee_id: str) -> str:
    """重要记忆"""
    mems = store.important(employee_id)
    lines = [f"[{m.id}] importance={m.importance} | {_format_memory_content(m.content)}" for m in mems]
    return "\n".join(lines) if lines else "暂无重要记忆"


@mcp.resource("memory://{employee_id}/identity-signals")
def identity_signals(employee_id: str) -> str:
    """数字分身身份信号"""
    mems = []
    for t in _IDENTITY_TYPES:
        mems.extend(store.list_by_employee(employee_id, t))
    lines = [f"[{m.type.value}] {m.content}" for m in mems]
    return "\n".join(lines) if lines else "暂无身份信号"


@mcp.resource("memory://{employee_id}/isolation-policy")
def isolation_policy(employee_id: str) -> str:
    """隔离策略"""
    count = store.count(employee_id)
    return (
        f"员工 {employee_id} | 记忆总数: {count} | 隔离模式: tenant_per_employee"
        f" | backend: {STORE_BACKEND} | bootstrap_imported: {BOOTSTRAP_IMPORTED_COUNT}"
    )


# ── Entry Point ──

if __name__ == "__main__":
    mcp.run()
