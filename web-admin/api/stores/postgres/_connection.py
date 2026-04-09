"""PostgreSQL connection helpers."""

from __future__ import annotations

import re
from threading import Lock
from typing import Any

from psycopg import OperationalError
from psycopg import connect as _psycopg_connect
from psycopg.rows import dict_row

from core.config import get_settings
from core.db_migrations import run_postgres_migrations

_LEADING_SQL_COMMENT_RE = re.compile(r"^(?:\s|--[^\n]*\n|/\*.*?\*/)*", re.S)
_RETRYABLE_READ_KEYWORDS = {"SELECT", "SHOW"}


def _leading_sql_keyword(query: Any) -> str:
    normalized = _LEADING_SQL_COMMENT_RE.sub("", str(query or ""), count=1).lstrip()
    if not normalized:
        return ""
    return normalized.split(None, 1)[0].upper()


class ReconnectingCursor:
    """Retry one read query on a fresh connection when the server drops a stale socket."""

    def __init__(self, owner: "ReconnectingConnection", *args: Any, **kwargs: Any) -> None:
        self._owner = owner
        self._args = args
        self._kwargs = dict(kwargs)
        self._cursor = owner._open_cursor(*args, **kwargs)

    def _swap_cursor(self) -> None:
        old_cursor = self._cursor
        self._cursor = self._owner._open_cursor(*self._args, **self._kwargs)
        try:
            old_cursor.close()
        except Exception:
            pass

    def __enter__(self) -> "ReconnectingCursor":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()
        return None

    def close(self) -> None:
        try:
            self._cursor.close()
        except Exception:
            pass

    def execute(self, query: Any, *args: Any, **kwargs: Any):
        try:
            return self._cursor.execute(query, *args, **kwargs)
        except OperationalError:
            if not self._owner._should_retry_query(query):
                raise
            self._owner._replace_connection()
            self._swap_cursor()
            return self._cursor.execute(query, *args, **kwargs)

    def executemany(self, query: Any, params_seq: Any):
        try:
            return self._cursor.executemany(query, params_seq)
        except OperationalError:
            if not self._owner._should_retry_query(query):
                raise
            self._owner._replace_connection()
            self._swap_cursor()
            return self._cursor.executemany(query, params_seq)

    def __getattr__(self, item: str) -> Any:
        return getattr(self._cursor, item)


class ReconnectingConnection:
    """Reconnect transparently when the underlying psycopg connection is closed."""

    def __init__(self, database_url: str, *args: Any, **kwargs: Any) -> None:
        self._database_url = database_url
        self._args = args
        self._kwargs = dict(kwargs)
        self._lock = Lock()
        self._conn = self._open()

    def _open(self):
        return _psycopg_connect(self._database_url, *self._args, **self._kwargs)

    def _open_cursor(self, *args: Any, **kwargs: Any):
        conn = self._get_connection()
        try:
            return conn.cursor(*args, **kwargs)
        except OperationalError:
            conn = self._replace_connection()
            return conn.cursor(*args, **kwargs)

    def _is_closed(self, conn: Any) -> bool:
        return bool(conn is None or getattr(conn, "closed", False))

    def _get_connection(self):
        conn = self._conn
        if self._is_closed(conn):
            with self._lock:
                conn = self._conn
                if self._is_closed(conn):
                    self._conn = self._open()
                    conn = self._conn
        return conn

    def _replace_connection(self):
        with self._lock:
            old_conn = self._conn
            self._conn = self._open()
            if old_conn is not None and not self._is_closed(old_conn):
                try:
                    old_conn.close()
                except Exception:
                    pass
            return self._conn

    def _call_with_reconnect(self, method_name: str, *args: Any, **kwargs: Any):
        conn = self._get_connection()
        try:
            return getattr(conn, method_name)(*args, **kwargs)
        except OperationalError:
            conn = self._replace_connection()
            return getattr(conn, method_name)(*args, **kwargs)

    def cursor(self, *args: Any, **kwargs: Any):
        return ReconnectingCursor(self, *args, **kwargs)

    def transaction(self, *args: Any, **kwargs: Any):
        return self._call_with_reconnect("transaction", *args, **kwargs)

    def _should_retry_query(self, query: Any) -> bool:
        return _leading_sql_keyword(query) in _RETRYABLE_READ_KEYWORDS

    def close(self) -> None:
        with self._lock:
            conn = self._conn
            self._conn = None
        if conn is None or self._is_closed(conn):
            return
        conn.close()

    @property
    def closed(self) -> bool:
        return self._is_closed(self._conn)

    def __getattr__(self, item: str) -> Any:
        return getattr(self._get_connection(), item)


def connect(database_url: str, *args: Any, **kwargs: Any) -> ReconnectingConnection:
    if get_settings().auto_run_db_migrations:
        run_postgres_migrations(database_url)
    kwargs.setdefault("autocommit", True)
    kwargs.setdefault("row_factory", dict_row)
    return ReconnectingConnection(database_url, *args, **kwargs)
