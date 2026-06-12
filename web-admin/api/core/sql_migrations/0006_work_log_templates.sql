CREATE TABLE IF NOT EXISTS work_log_templates (
    value TEXT PRIMARY KEY,
    payload JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
