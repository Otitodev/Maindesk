-- HealthDesk AI — staff dashboard columns for escalations (PRD human-in-the-loop).
-- Fresh volumes pick this up via docker-entrypoint-initdb.d; existing volumes:
--   docker exec -i healthdesk-pg psql -U healthdesk healthdesk < supabase/migrations/0002_escalation_dashboard.sql

ALTER TABLE escalations
    ADD COLUMN IF NOT EXISTS channel         TEXT,
    ADD COLUMN IF NOT EXISTS patient_id      UUID REFERENCES patients(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS message_preview TEXT,
    ADD COLUMN IF NOT EXISTS status          TEXT NOT NULL DEFAULT 'open',
    ADD COLUMN IF NOT EXISTS note            TEXT,
    ADD COLUMN IF NOT EXISTS resolved_at     TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS escalations_status_idx
    ON escalations (status, created_at DESC);
