-- Baseline PostgreSQL schema.
-- Fresh databases should be created from this migration set.

CREATE TABLE IF NOT EXISTS agent_templates (
    id TEXT PRIMARY KEY,
    payload JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    payload JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS employees (
    id TEXT PRIMARY KEY,
    payload JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS roles (
    id TEXT PRIMARY KEY,
    payload JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    payload JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS project_members (
    project_id TEXT NOT NULL,
    employee_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (project_id, employee_id)
);

CREATE INDEX IF NOT EXISTS idx_project_members_project
ON project_members (project_id, joined_at DESC);

CREATE TABLE IF NOT EXISTS project_user_members (
    project_id TEXT NOT NULL,
    username TEXT NOT NULL,
    payload JSONB NOT NULL,
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (project_id, username)
);

CREATE INDEX IF NOT EXISTS idx_project_user_members_project
ON project_user_members (project_id, joined_at DESC);

CREATE TABLE IF NOT EXISTS project_chat_messages (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    username TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS project_chat_sessions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    username TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '新对话',
    preview TEXT NOT NULL DEFAULT '',
    message_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_message_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_project_chat_lookup
ON project_chat_messages (project_id, username, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_project_chat_sessions_lookup
ON project_chat_sessions (project_id, username, updated_at DESC);

CREATE TABLE IF NOT EXISTS project_material_assets (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_project_material_assets_project
ON project_material_assets (project_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS project_studio_export_jobs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_project_studio_export_jobs_project
ON project_studio_export_jobs (project_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS system_configs (
    id TEXT PRIMARY KEY,
    payload JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS external_mcp_modules (
    id TEXT PRIMARY KEY,
    payload JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS local_connector_pair_codes (
    code TEXT PRIMARY KEY,
    payload JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS local_connectors (
    id TEXT PRIMARY KEY,
    payload JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS local_connector_workspace_pick_sessions (
    id TEXT PRIMARY KEY,
    payload JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

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

CREATE TABLE IF NOT EXISTS skills (
    id TEXT PRIMARY KEY,
    payload JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS skill_bindings (
    employee_id TEXT NOT NULL,
    skill_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    installed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (employee_id, skill_id)
);

CREATE TABLE IF NOT EXISTS rules (
    id TEXT PRIMARY KEY,
    domain TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    payload JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rules_domain ON rules(domain);
CREATE INDEX IF NOT EXISTS idx_rules_confidence ON rules(confidence DESC);

CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    employee_id TEXT NOT NULL,
    importance DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payload JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_memories_employee ON memories(employee_id);
CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(employee_id, importance DESC);
CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(employee_id, created_at DESC);

CREATE TABLE IF NOT EXISTS personas (
    id TEXT PRIMARY KEY,
    payload JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS persona_snapshots (
    id TEXT PRIMARY KEY,
    persona_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payload JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_persona_snapshots_persona
ON persona_snapshots (persona_id, created_at DESC);

CREATE TABLE IF NOT EXISTS evolution_candidates (
    id TEXT PRIMARY KEY,
    employee_id TEXT NOT NULL,
    status TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payload JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_evolution_candidates_employee_status
ON evolution_candidates (employee_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_evolution_candidates_confidence
ON evolution_candidates (confidence DESC);

CREATE TABLE IF NOT EXISTS evolution_events (
    id TEXT PRIMARY KEY,
    employee_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payload JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_evolution_events_employee
ON evolution_events (employee_id, created_at DESC);

CREATE TABLE IF NOT EXISTS evolution_usage_logs (
    id TEXT PRIMARY KEY,
    employee_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payload JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_evolution_usage_logs_employee
ON evolution_usage_logs (employee_id, created_at DESC);

CREATE TABLE IF NOT EXISTS sync_events (
    id TEXT PRIMARY KEY,
    employee_id TEXT NOT NULL,
    delivered BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payload JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sync_events_employee_created
ON sync_events (employee_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_sync_events_employee_delivered
ON sync_events (employee_id, delivered);

CREATE TABLE IF NOT EXISTS llm_providers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    provider_type TEXT NOT NULL,
    base_url TEXT NOT NULL,
    default_model TEXT NOT NULL DEFAULT '',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payload JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_llm_providers_enabled_updated
ON llm_providers (enabled, updated_at DESC);

CREATE TABLE IF NOT EXISTS feedback_reflection_configs (
    project_id TEXT NOT NULL,
    employee_id TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    model_name TEXT NOT NULL,
    temperature DOUBLE PRECISION NOT NULL DEFAULT 0.2,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payload JSONB NOT NULL,
    PRIMARY KEY (project_id, employee_id)
);

CREATE INDEX IF NOT EXISTS idx_feedback_reflection_configs_provider
ON feedback_reflection_configs (provider_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS feedback_bugs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    employee_id TEXT NOT NULL,
    status TEXT NOT NULL,
    severity TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payload JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_feedback_bugs_project_status_created
ON feedback_bugs (project_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_feedback_bugs_project_employee
ON feedback_bugs (project_id, employee_id, created_at DESC);

CREATE TABLE IF NOT EXISTS feedback_analyses (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    feedback_id TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payload JSONB NOT NULL,
    UNIQUE (project_id, feedback_id)
);

CREATE INDEX IF NOT EXISTS idx_feedback_analyses_project_feedback
ON feedback_analyses (project_id, feedback_id);

CREATE TABLE IF NOT EXISTS feedback_candidates (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    feedback_id TEXT NOT NULL,
    employee_id TEXT NOT NULL,
    status TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payload JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_feedback_candidates_project_status_created
ON feedback_candidates (project_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_feedback_candidates_project_feedback
ON feedback_candidates (project_id, feedback_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_feedback_candidates_project_employee
ON feedback_candidates (project_id, employee_id, created_at DESC);

CREATE TABLE IF NOT EXISTS feedback_reviews (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    feedback_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payload JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_feedback_reviews_project_feedback
ON feedback_reviews (project_id, feedback_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_feedback_reviews_project_candidate
ON feedback_reviews (project_id, candidate_id, created_at DESC);

CREATE TABLE IF NOT EXISTS feedback_project_configs (
    project_id TEXT PRIMARY KEY,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS prompt_history (
    id TEXT PRIMARY KEY,
    employee_id TEXT NOT NULL,
    prompt TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by TEXT
);

CREATE INDEX IF NOT EXISTS idx_prompt_history_employee ON prompt_history(employee_id);
CREATE INDEX IF NOT EXISTS idx_prompt_history_created ON prompt_history(created_at DESC);
