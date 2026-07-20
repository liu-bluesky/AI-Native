CREATE TABLE IF NOT EXISTS user_feedback_tickets (
    id TEXT PRIMARY KEY,
    reporter_id TEXT NOT NULL,
    category TEXT NOT NULL,
    status TEXT NOT NULL,
    priority TEXT NOT NULL,
    project_id TEXT NOT NULL DEFAULT '',
    assignee_id TEXT NOT NULL DEFAULT '',
    idempotency_key TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payload JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_user_feedback_reporter_created
ON user_feedback_tickets (reporter_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_user_feedback_status_priority_created
ON user_feedback_tickets (status, priority, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_user_feedback_category_updated
ON user_feedback_tickets (category, status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_user_feedback_project_created
ON user_feedback_tickets (project_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_user_feedback_assignee_updated
ON user_feedback_tickets (assignee_id, status, updated_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_user_feedback_idempotency
ON user_feedback_tickets (reporter_id, idempotency_key)
WHERE idempotency_key <> '';
