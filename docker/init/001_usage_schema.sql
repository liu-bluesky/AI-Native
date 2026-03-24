-- Legacy bootstrap SQL for first-time PostgreSQL container initialization only.
-- Canonical schema migrations now live under web-admin/api/core/sql_migrations/.

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
