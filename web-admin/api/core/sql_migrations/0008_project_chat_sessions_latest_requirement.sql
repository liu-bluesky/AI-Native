ALTER TABLE project_chat_sessions
    ADD COLUMN IF NOT EXISTS latest_requirement TEXT NOT NULL DEFAULT '';
