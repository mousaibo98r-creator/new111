-- ============================================================
--  Antigravity :: B2B Cold Email Outreach System
--  Database Schema  –  Supabase / PostgreSQL
-- ============================================================

-- Enable uuid generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ────────────────────────────────────────────────────────────
--  TABLE: mousa   (primary leads table)
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS mousa (
    id          UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT            NOT NULL,
    company     TEXT            NOT NULL,
    email       TEXT            NOT NULL UNIQUE,
    status      TEXT            NOT NULL DEFAULT 'pending'
                                CHECK (status IN (
                                    'pending',
                                    'sent',
                                    'opened',
                                    'replied',
                                    'bounced',
                                    'unsubscribed',
                                    'interested',
                                    'not_interested',
                                    'follow_up'
                                )),
    created_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- Auto-update updated_at on any row change
CREATE OR REPLACE FUNCTION update_mousa_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_mousa_updated_at
    BEFORE UPDATE ON mousa
    FOR EACH ROW EXECUTE FUNCTION update_mousa_updated_at();

-- ────────────────────────────────────────────────────────────
--  TABLE: logs   (sending history & AI classifications)
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS logs (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id         UUID        REFERENCES mousa(id) ON DELETE SET NULL,
    email           TEXT        NOT NULL,
    event_type      TEXT        NOT NULL
                                CHECK (event_type IN (
                                    'email_sent',
                                    'email_failed',
                                    'reply_received',
                                    'reply_classified',
                                    'auto_response_sent',
                                    'status_changed'
                                )),
    subject         TEXT,
    body_preview    TEXT,           -- first 500 chars of email body
    ai_classification TEXT,         -- e.g. "interested", "not_interested", "follow_up"
    ai_confidence   NUMERIC(4,3),   -- 0.000 – 1.000
    metadata        JSONB,          -- flexible bag for extra data
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for fast lead-based log lookups
CREATE INDEX IF NOT EXISTS idx_logs_lead_id   ON logs(lead_id);
CREATE INDEX IF NOT EXISTS idx_logs_event     ON logs(event_type);
CREATE INDEX IF NOT EXISTS idx_mousa_status   ON mousa(status);
CREATE INDEX IF NOT EXISTS idx_mousa_email    ON mousa(email);
