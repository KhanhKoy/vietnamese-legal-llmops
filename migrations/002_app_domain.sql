-- App domain tables (ported from legal_chat.db) on the same RDS used for RAG.
-- Safe to run multiple times.

BEGIN;

CREATE TABLE IF NOT EXISTS app_users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    status TEXT NOT NULL DEFAULT 'Active',
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app_chat_sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES app_users(id),
    title TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_app_chat_sessions_user
    ON app_chat_sessions (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS app_chat_messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES app_chat_sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    sources_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    feedback TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_app_chat_messages_session
    ON app_chat_messages (session_id, created_at ASC);

CREATE TABLE IF NOT EXISTS app_feedback_events (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES app_users(id),
    session_id TEXT NOT NULL REFERENCES app_chat_sessions(id),
    message_id TEXT,
    feedback TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_app_feedback_events_user
    ON app_feedback_events (user_id, created_at DESC);

COMMIT;
