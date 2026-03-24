"""Apply pending PostgreSQL schema migrations."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from core.config import get_settings
from core.db_migrations import run_postgres_migrations


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply pending PostgreSQL schema migrations")
    parser.add_argument("--database-url", default="", help="Target PostgreSQL DATABASE_URL")
    args = parser.parse_args()
    database_url = str(args.database_url or "").strip() or get_settings().database_url
    if not database_url:
        raise SystemExit("Missing DATABASE_URL")
    applied = run_postgres_migrations(database_url, force=True)
    if applied:
        print("Applied migrations:")
        for version in applied:
            print(f"- {version}")
        return
    print("No pending migrations.")


if __name__ == "__main__":
    main()
