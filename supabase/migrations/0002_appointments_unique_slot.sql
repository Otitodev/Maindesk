-- Replace per-patient uniqueness with a clinic-wide constraint so no two
-- patients can book the same time slot (single-doctor clinic assumption).
ALTER TABLE appointments
    DROP CONSTRAINT IF EXISTS appointments_patient_id_starts_at_key;

ALTER TABLE appointments
    ADD CONSTRAINT appointments_starts_at_unique UNIQUE (starts_at);
