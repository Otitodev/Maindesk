-- Mirror appointments into an external calendar (Google) while Postgres stays
-- the source of truth. Stores the provider's event id so reschedule/cancel can
-- move/delete the matching calendar event. Nullable: empty when no calendar is
-- configured or a best-effort mirror call failed.
ALTER TABLE appointments
    ADD COLUMN IF NOT EXISTS calendar_event_id TEXT;
