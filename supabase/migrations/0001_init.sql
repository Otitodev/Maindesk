-- HealthDesk AI — initial schema (TRD §9.1).
-- Embedding dim 1024 matches Qwen text-embedding-v3 default output.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS patients (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name   TEXT,
    phone       TEXT UNIQUE,
    email       TEXT,
    preferences JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS patient_memories (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id        UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    content           TEXT NOT NULL,
    memory_type       TEXT NOT NULL DEFAULT 'unknown',
    importance_score  REAL NOT NULL DEFAULT 0.5,
    access_count      INTEGER NOT NULL DEFAULT 0,
    last_accessed_at  TIMESTAMPTZ,
    source_session_id TEXT,
    embedding         VECTOR(1024),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS patient_memories_patient_idx
    ON patient_memories (patient_id);

-- ivfflat needs ANALYZE first; lists=100 is a sane default up to ~1M rows.
CREATE INDEX IF NOT EXISTS patient_memories_embedding_idx
    ON patient_memories USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE TABLE IF NOT EXISTS appointments (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id  UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    starts_at   TIMESTAMPTZ NOT NULL,
    status      TEXT NOT NULL DEFAULT 'booked',
    notes       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (patient_id, starts_at)
);

CREATE INDEX IF NOT EXISTS appointments_starts_at_idx
    ON appointments (starts_at);

CREATE TABLE IF NOT EXISTS escalations (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id   TEXT NOT NULL,
    reason       TEXT,
    payload      JSONB NOT NULL DEFAULT '{}'::jsonb,
    delivered    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
