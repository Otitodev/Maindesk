-- Single-tenant clinic configuration set via the /onboarding wizard. One row
-- (id = 1) holding a JSONB blob of clinic-tunable settings (hours, persona,
-- FAQs, answer mode). The agent reads it at runtime, falling back to .env.
CREATE TABLE IF NOT EXISTS clinic_settings (
    id          INTEGER PRIMARY KEY DEFAULT 1,
    config      JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT clinic_settings_singleton CHECK (id = 1)
);
