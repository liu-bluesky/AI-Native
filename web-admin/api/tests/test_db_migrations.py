from pathlib import Path

import pytest


class _FakeTransaction:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeCursor:
    def __init__(self, connection):
        self._connection = connection
        self._rows: list[dict[str, str]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query: str, params=None):
        sql = str(query).strip()
        if sql.startswith("CREATE TABLE IF NOT EXISTS schema_migrations"):
            return
        if sql.startswith("SELECT version, checksum FROM schema_migrations"):
            self._rows = [
                {"version": version, "checksum": checksum}
                for version, checksum in sorted(self._connection.schema_migrations.items())
            ]
            return
        if sql.startswith("INSERT INTO schema_migrations"):
            version, checksum = params
            self._connection.schema_migrations[str(version)] = str(checksum)
            return
        self._connection.executed_sql.append(sql)

    def fetchall(self):
        return list(self._rows)


class _FakeConnection:
    def __init__(self):
        self.schema_migrations: dict[str, str] = {}
        self.executed_sql: list[str] = []
        self.closed = False

    def cursor(self):
        return _FakeCursor(self)

    def transaction(self):
        return _FakeTransaction()

    def close(self):
        self.closed = True


def _write_migration(path: Path, sql: str) -> None:
    path.write_text(sql, encoding="utf-8")


def test_run_postgres_migrations_applies_new_versions_without_rewriting_existing_checksums(
    tmp_path,
    monkeypatch,
):
    from core import db_migrations as module

    migration_dir = tmp_path / "sql_migrations"
    migration_dir.mkdir()
    _write_migration(migration_dir / "0001_initial_schema.sql", "CREATE TABLE demo_a(id INT);")
    _write_migration(migration_dir / "0002_project_experience_summary_jobs.sql", "CREATE TABLE demo_b(id INT);")

    connections: dict[str, _FakeConnection] = {}

    def fake_connect(database_url: str, autocommit=True, row_factory=None):
        if database_url not in connections:
            connections[database_url] = _FakeConnection()
        return connections[database_url]

    monkeypatch.setattr(module, "_MIGRATION_DIR", migration_dir)
    monkeypatch.setattr(module, "connect", fake_connect)
    module._APPLIED_DATABASE_URLS.clear()

    database_url = "postgresql://example/app"
    first_applied = module.run_postgres_migrations(database_url, force=True)

    _write_migration(migration_dir / "0003_usage_records_enriched.sql", "ALTER TABLE demo_a ADD COLUMN scope_id TEXT;")
    second_applied = module.run_postgres_migrations(database_url, force=True)

    assert first_applied == [
        "0001_initial_schema.sql",
        "0002_project_experience_summary_jobs.sql",
    ]
    assert second_applied == ["0003_usage_records_enriched.sql"]
    assert set(connections[database_url].schema_migrations) == {
        "0001_initial_schema.sql",
        "0002_project_experience_summary_jobs.sql",
        "0003_usage_records_enriched.sql",
    }
    assert "ALTER TABLE demo_a ADD COLUMN scope_id TEXT;" in connections[database_url].executed_sql


def test_run_postgres_migrations_rejects_modified_applied_migration(tmp_path, monkeypatch):
    from core import db_migrations as module

    migration_dir = tmp_path / "sql_migrations"
    migration_dir.mkdir()
    migration_path = migration_dir / "0001_initial_schema.sql"
    _write_migration(migration_path, "CREATE TABLE demo_a(id INT);")

    connections: dict[str, _FakeConnection] = {}

    def fake_connect(database_url: str, autocommit=True, row_factory=None):
        if database_url not in connections:
            connections[database_url] = _FakeConnection()
        return connections[database_url]

    monkeypatch.setattr(module, "_MIGRATION_DIR", migration_dir)
    monkeypatch.setattr(module, "connect", fake_connect)
    module._APPLIED_DATABASE_URLS.clear()

    database_url = "postgresql://example/app"
    module.run_postgres_migrations(database_url, force=True)

    _write_migration(migration_path, "CREATE TABLE demo_a(id INT, status TEXT);")

    with pytest.raises(RuntimeError, match="Migration checksum mismatch: 0001_initial_schema.sql"):
        module.run_postgres_migrations(database_url, force=True)
