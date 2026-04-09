from __future__ import annotations

from types import SimpleNamespace

import pytest


class FakeCursor:
    def __init__(self, conn: "FakeConn") -> None:
        self._conn = conn
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeConn:
    def __init__(self) -> None:
        self.closed = False
        self.close_calls = 0

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def close(self) -> None:
        self.closed = True
        self.close_calls += 1


def test_postgres_connections_run_migrations_before_creating_wrapper(monkeypatch):
    from stores.postgres import _connection as module

    captured: dict[str, object] = {}
    fake_conn = FakeConn()
    migration_calls: list[str] = []

    def fake_connect(database_url: str, *args, **kwargs):
        captured["database_url"] = database_url
        captured["kwargs"] = kwargs
        return fake_conn

    monkeypatch.setattr(module, "get_settings", lambda: SimpleNamespace(auto_run_db_migrations=True))
    monkeypatch.setattr(module, "run_postgres_migrations", lambda database_url: migration_calls.append(database_url))
    monkeypatch.setattr(module, "_psycopg_connect", fake_connect)

    conn = module.connect("postgres://unit-test")

    assert isinstance(conn, module.ReconnectingConnection)
    assert migration_calls == ["postgres://unit-test"]
    assert captured["database_url"] == "postgres://unit-test"
    assert captured["kwargs"]["autocommit"] is True
    assert "row_factory" in captured["kwargs"]
    assert conn.cursor().__class__ is module.ReconnectingCursor


def test_postgres_connections_reconnect_when_underlying_cursor_creation_fails(monkeypatch):
    from stores.postgres import _connection as module

    class CursorStub:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    class FakeCursorConnection:
        def __init__(self, *, closed: bool = False, fail_cursor: bool = False) -> None:
            self.closed = closed
            self.fail_cursor = fail_cursor
            self.close_calls = 0

        def cursor(self):
            if self.fail_cursor:
                self.fail_cursor = False
                self.closed = True
                raise module.OperationalError("the connection is closed")
            return CursorStub()

        def close(self) -> None:
            self.close_calls += 1
            self.closed = True

    first = FakeCursorConnection(fail_cursor=True)
    second = FakeCursorConnection()
    created: list[FakeCursorConnection] = []

    def fake_connect(database_url: str, *args, **kwargs):
        conn = first if not created else second
        created.append(conn)
        return conn

    monkeypatch.setattr(module, "get_settings", lambda: SimpleNamespace(auto_run_db_migrations=False))
    monkeypatch.setattr(module, "_psycopg_connect", fake_connect)

    conn = module.connect("postgres://unit-test")
    cursor = conn.cursor()

    assert len(created) == 2
    assert cursor.__class__ is module.ReconnectingCursor
    assert first.closed is True


def test_postgres_connections_retry_read_queries_after_stale_socket_failure(monkeypatch):
    from stores.postgres import _connection as module

    class ReadCursor:
        def __init__(self, conn: "FakeReadConnection") -> None:
            self._conn = conn
            self.closed = False

        def execute(self, query: str, params=None) -> None:
            if self._conn.fail_next_execute:
                self._conn.fail_next_execute = False
                self._conn.closed = True
                raise module.OperationalError("server closed the connection unexpectedly")
            self._conn.executed.append((query, params))

        def close(self) -> None:
            self.closed = True

    class FakeReadConnection:
        def __init__(self, *, fail_next_execute: bool = False) -> None:
            self.fail_next_execute = fail_next_execute
            self.executed: list[tuple[str, object]] = []
            self.closed = False
            self.close_calls = 0

        def cursor(self) -> ReadCursor:
            return ReadCursor(self)

        def close(self) -> None:
            self.close_calls += 1
            self.closed = True

    first = FakeReadConnection(fail_next_execute=True)
    second = FakeReadConnection()
    created: list[FakeReadConnection] = []

    def fake_connect(database_url: str, *args, **kwargs):
        conn = first if not created else second
        created.append(conn)
        return conn

    monkeypatch.setattr(module, "get_settings", lambda: SimpleNamespace(auto_run_db_migrations=False))
    monkeypatch.setattr(module, "_psycopg_connect", fake_connect)

    conn = module.connect("postgres://unit-test")
    with conn.cursor() as cur:
        cur.execute("SELECT payload FROM employees WHERE id = %s", ("emp-1",))

    assert len(created) == 2
    assert first.closed is True
    assert second.executed == [("SELECT payload FROM employees WHERE id = %s", ("emp-1",))]


def test_postgres_connections_do_not_retry_write_queries_after_socket_failure(monkeypatch):
    from stores.postgres import _connection as module

    class WriteCursor:
        def execute(self, query: str, params=None) -> None:
            raise module.OperationalError("server closed the connection unexpectedly")

        def close(self) -> None:
            return None

    class FakeWriteConnection:
        def __init__(self) -> None:
            self.closed = False

        def cursor(self) -> WriteCursor:
            return WriteCursor()

        def close(self) -> None:
            self.closed = True

    created: list[FakeWriteConnection] = []

    def fake_connect(database_url: str, *args, **kwargs):
        conn = FakeWriteConnection()
        created.append(conn)
        return conn

    monkeypatch.setattr(module, "get_settings", lambda: SimpleNamespace(auto_run_db_migrations=False))
    monkeypatch.setattr(module, "_psycopg_connect", fake_connect)

    conn = module.connect("postgres://unit-test")
    with pytest.raises(module.OperationalError):
        with conn.cursor() as cur:
            cur.execute("INSERT INTO employees (id) VALUES (%s)", ("emp-1",))

    assert len(created) == 1
