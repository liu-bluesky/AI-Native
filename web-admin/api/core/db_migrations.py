"""PostgreSQL schema migrations."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from threading import Lock

from psycopg import connect
from psycopg.rows import dict_row

_MIGRATION_DIR = Path(__file__).resolve().parent / "sql_migrations"
_MIGRATION_LOCK = Lock()
_APPLIED_DATABASE_URLS: set[str] = set()


def _iter_migration_files() -> list[Path]:
    if not _MIGRATION_DIR.is_dir():
        return []
    return sorted(
        path
        for path in _MIGRATION_DIR.iterdir()
        if path.is_file() and path.suffix.lower() == ".sql"
    )


def _migration_checksum(sql: str) -> str:
    return sha256(sql.encode("utf-8")).hexdigest()


def run_postgres_migrations(database_url: str, *, force: bool = False) -> list[str]:
    normalized_database_url = str(database_url or "").strip()
    if not normalized_database_url:
        return []
    with _MIGRATION_LOCK:
        if not force and normalized_database_url in _APPLIED_DATABASE_URLS:
            return []
    files = _iter_migration_files()
    if not files:
        with _MIGRATION_LOCK:
            _APPLIED_DATABASE_URLS.add(normalized_database_url)
        return []

    applied_versions: list[str] = []
    conn = connect(
        normalized_database_url,
        autocommit=True,
        row_factory=dict_row,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    checksum TEXT NOT NULL,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            cur.execute("SELECT version, checksum FROM schema_migrations ORDER BY version")
            rows = cur.fetchall()
        applied = {
            str(row.get("version") or "").strip(): str(row.get("checksum") or "").strip()
            for row in rows
            if isinstance(row, dict)
        }
        for path in files:
            version = path.name
            sql = path.read_text(encoding="utf-8")
            checksum = _migration_checksum(sql)
            existing_checksum = applied.get(version)
            if existing_checksum:
                if existing_checksum != checksum:
                    raise RuntimeError(
                        f"Migration checksum mismatch: {version}. "
                        "请不要直接改已执行过的 migration，新增一个新的 migration 文件。"
                    )
                continue
            with conn.transaction():
                with conn.cursor() as cur:
                    if sql.strip():
                        cur.execute(sql)
                    cur.execute(
                        """
                        INSERT INTO schema_migrations (version, checksum)
                        VALUES (%s, %s)
                        """,
                        (version, checksum),
                    )
            applied_versions.append(version)
    finally:
        conn.close()
    with _MIGRATION_LOCK:
        _APPLIED_DATABASE_URLS.add(normalized_database_url)
    return applied_versions
