"""迁移 usage 数据：SQLite -> PostgreSQL

用法示例：
    python scripts/migrate_usage_to_pg.py \
        --sqlite-path ~/.ai-native/web-admin-api/usage.db \
        --database-url postgresql://admin:changeme@localhost:5432/ai_employee
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from core.config import get_api_data_dir
from psycopg import connect


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS api_keys (
    key TEXT PRIMARY KEY,
    developer_name TEXT NOT NULL,
    created_by TEXT NOT NULL DEFAULT '',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS usage_records (
    id TEXT PRIMARY KEY,
    employee_id TEXT NOT NULL,
    api_key TEXT NOT NULL DEFAULT '',
    developer_name TEXT NOT NULL DEFAULT 'anonymous',
    event_type TEXT NOT NULL,
    tool_name TEXT NOT NULL DEFAULT '',
    client_ip TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_usage_employee ON usage_records(employee_id);
CREATE INDEX IF NOT EXISTS idx_usage_created ON usage_records(created_at);
"""


def migrate(sqlite_path: Path, database_url: str) -> None:
    if not sqlite_path.exists():
        raise FileNotFoundError(f"SQLite file not found: {sqlite_path}")

    sqlite_conn = sqlite3.connect(str(sqlite_path))
    sqlite_conn.row_factory = sqlite3.Row

    pg_conn = connect(database_url, autocommit=True)
    try:
        with pg_conn.cursor() as cur:
            cur.execute(_SCHEMA_SQL)

        sqlite_keys = sqlite_conn.execute(
            "SELECT key, developer_name, created_by, is_active, created_at FROM api_keys"
        ).fetchall()
        sqlite_records = sqlite_conn.execute(
            """
            SELECT id, employee_id, api_key, developer_name, event_type, tool_name, client_ip, created_at
            FROM usage_records
            """
        ).fetchall()

        with pg_conn.cursor() as cur:
            if sqlite_keys:
                cur.executemany(
                    """
                    INSERT INTO api_keys (key, developer_name, created_by, is_active, created_at)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (key) DO UPDATE
                    SET developer_name = EXCLUDED.developer_name,
                        created_by = EXCLUDED.created_by,
                        is_active = EXCLUDED.is_active,
                        created_at = EXCLUDED.created_at
                    """,
                    [
                        (
                            row["key"],
                            row["developer_name"],
                            row["created_by"],
                            bool(row["is_active"]),
                            row["created_at"],
                        )
                        for row in sqlite_keys
                    ],
                )
            if sqlite_records:
                cur.executemany(
                    """
                    INSERT INTO usage_records
                        (id, employee_id, api_key, developer_name, event_type, tool_name, client_ip, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    [
                        (
                            row["id"],
                            row["employee_id"],
                            row["api_key"],
                            row["developer_name"],
                            row["event_type"],
                            row["tool_name"],
                            row["client_ip"],
                            row["created_at"],
                        )
                        for row in sqlite_records
                    ],
                )

        print(
            f"Migration completed: api_keys={len(sqlite_keys)}, "
            f"usage_records={len(sqlite_records)}"
        )
    finally:
        sqlite_conn.close()
        pg_conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate usage SQLite data to PostgreSQL")
    parser.add_argument(
        "--sqlite-path",
        default=str(get_api_data_dir(create=False) / "usage.db"),
        help="Path to SQLite usage.db；旧仓库内 ./data/usage.db 已废弃，请显式传参",
    )
    parser.add_argument("--database-url", required=True, help="PostgreSQL DSN")
    args = parser.parse_args()
    migrate(Path(args.sqlite_path), args.database_url)


if __name__ == "__main__":
    main()
