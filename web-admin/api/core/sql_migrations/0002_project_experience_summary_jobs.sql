CREATE TABLE IF NOT EXISTS project_experience_summary_jobs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_project_experience_summary_jobs_project
ON project_experience_summary_jobs (project_id, updated_at DESC);
