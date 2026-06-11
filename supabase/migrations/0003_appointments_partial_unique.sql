-- Fix migration 0002: the full UNIQUE(starts_at) constraint rejects inserts
-- even when the conflicting row is cancelled, but suggest_slots only excludes
-- booked rows. Replace with a partial index so the two paths agree.
ALTER TABLE appointments
    DROP CONSTRAINT IF EXISTS appointments_starts_at_unique;

CREATE UNIQUE INDEX IF NOT EXISTS appointments_starts_at_booked_idx
    ON appointments (starts_at)
    WHERE status = 'booked';
