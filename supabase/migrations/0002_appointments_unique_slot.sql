-- Replace per-patient uniqueness with a clinic-wide partial unique index on
-- booked rows only. A cancelled slot at a given time does not block a new
-- booking at that time — keeping suggest_slots (which filters status='booked')
-- and book() (which the index enforces) in exact agreement.
ALTER TABLE appointments
    DROP CONSTRAINT IF EXISTS appointments_patient_id_starts_at_key;

CREATE UNIQUE INDEX IF NOT EXISTS appointments_starts_at_booked_idx
    ON appointments (starts_at)
    WHERE status = 'booked';
