CREATE TABLE IF NOT EXISTS ftp_credentials (
    id TEXT PRIMARY KEY,
    created_by TEXT NOT NULL DEFAULT '',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ftp_credentials_created_by
ON ftp_credentials (created_by, updated_at DESC);
