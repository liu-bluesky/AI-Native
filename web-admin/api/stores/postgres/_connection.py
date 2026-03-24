"""PostgreSQL connection helpers with migration bootstrap."""

from __future__ import annotations

from typing import Any

from psycopg import connect as _psycopg_connect
from psycopg.rows import dict_row

from core.db_migrations import run_postgres_migrations


def connect(database_url: str, *args: Any, **kwargs: Any):
    run_postgres_migrations(database_url)
    kwargs.setdefault("autocommit", True)
    kwargs.setdefault("row_factory", dict_row)
    return _psycopg_connect(database_url, *args, **kwargs)
