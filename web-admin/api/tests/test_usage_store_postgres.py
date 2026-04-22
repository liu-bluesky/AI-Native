from stores.postgres.usage_store import UsageStorePostgres


class _FakeCursor:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple]] = []
        self._fetchone_results = [
            {
                "total_events": 3,
                "tool_calls": 2,
                "connections": 1,
                "active_developers": 1,
                "active_employees": 1,
                "active_tools": 1,
            }
        ]
        self._fetchall_results = [
            [{"tool_name": "demo_tool", "cnt": 2}],
            [{"employee_id": "emp-1", "cnt": 2}],
            [{"developer_name": "admin", "cnt": 3}],
            [{"project_id": "proj-1", "project_name": "项目 A", "cnt": 3}],
            [{"date": "2026-04-22", "total_events": 3, "tool_calls": 2, "connections": 1}],
            [{"employee_id": "emp-1", "created_at": "2026-04-22T00:00:00+00:00"}],
        ]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=()):
        self.executed.append((query, params))
        return self

    def fetchone(self):
        return self._fetchone_results.pop(0)

    def fetchall(self):
        return self._fetchall_results.pop(0)


class _FakeConnection:
    def __init__(self) -> None:
        self.cursor_instance = _FakeCursor()

    def cursor(self):
        return self.cursor_instance


def test_postgres_usage_overview_escapes_like_pattern():
    store = UsageStorePostgres.__new__(UsageStorePostgres)
    store._conn = _FakeConnection()

    payload = store.get_overview(7)

    executed_queries = [query for query, _ in store._conn.cursor_instance.executed]
    assert any("employee_id LIKE 'emp-%%'" in query for query in executed_queries)
    assert not any("employee_id LIKE 'emp-%'" in query for query in executed_queries)
    assert payload["summary"]["active_employees"] == 1
    assert payload["top_employees"][0]["employee_id"] == "emp-1"
