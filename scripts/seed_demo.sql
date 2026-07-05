-- Demo seed for MainDesk.
-- Populates enough patients, bookings, and escalations to make /staff,
-- /staff/inbox, and /staff/analytics look like a working clinic on demo day.
--
-- Idempotent: safe to re-run. Uses ON CONFLICT for patients (unique phone)
-- and deletes prior demo escalations by a marker text before re-inserting.
--
-- Usage on the ECS box:
--   docker exec -i healthdesk-pg psql -U healthdesk healthdesk < scripts/seed_demo.sql

BEGIN;

-- ── 1. Patients ─────────────────────────────────────────────────────────
-- Use ON CONFLICT (phone) DO UPDATE so names/emails refresh if the seed evolves.

INSERT INTO patients (full_name, phone, email) VALUES
  ('Amina Okafor',    '+2348035550101', 'amina.okafor@example.com'),
  ('Fatima Bello',    '+2348125550102', NULL),
  ('Kwame Adeyemi',   '+2348065550103', 'kwame.adeyemi@example.com'),
  ('Nkechi Eze',      '+2348025550104', 'nkechi.eze@example.com'),
  ('Tunde Ogundimu',  '+2348075550105', NULL),
  ('Rachel Nnamdi',   '+2348095550106', 'rachel.nnamdi@example.com'),
  ('Michael Adeboye', '+2348155550107', 'michael.adeboye@example.com'),
  ('Sarah Idowu',     '+2348135550108', 'sarah.idowu@example.com')
ON CONFLICT (phone) DO UPDATE
  SET full_name = EXCLUDED.full_name,
      email     = EXCLUDED.email;

-- ── 2. Appointments (12: 6 upcoming, 6 handled this month) ──────────────
-- Delete any prior seed appointments so re-running doesn't duplicate.
-- We identify seed rows by their note prefix "[demo-seed]".

DELETE FROM appointments WHERE notes LIKE '[demo-seed]%';

INSERT INTO appointments (patient_id, starts_at, status, notes, created_at)
SELECT p.id, ts, st, note, created
FROM (VALUES
  -- Upcoming (next 14 days)
  ('+2348035550101', NOW() + INTERVAL '1 day 10 hours',   'booked',    '[demo-seed] cleaning',            NOW() - INTERVAL '2 days'),
  ('+2348125550102', NOW() + INTERVAL '1 day 14 hours',   'booked',    '[demo-seed] toothache follow-up', NOW() - INTERVAL '1 day'),
  ('+2348065550103', NOW() + INTERVAL '2 days 9 hours',   'booked',    '[demo-seed] whitening consult',   NOW() - INTERVAL '3 days'),
  ('+2348135550108', NOW() + INTERVAL '3 days 11 hours',  'booked',    '[demo-seed] first visit',         NOW() - INTERVAL '1 day'),
  ('+2348095550106', NOW() + INTERVAL '5 days 15 hours',  'booked',    '[demo-seed] filling',             NOW() - INTERVAL '2 days'),
  ('+2348155550107', NOW() + INTERVAL '9 days 10 hours',  'booked',    '[demo-seed] root canal review',   NOW() - INTERVAL '4 days'),
  -- Past-this-month (completed)
  ('+2348075550105', date_trunc('month', NOW()) + INTERVAL '4 days 10 hours',  'completed', '[demo-seed] extraction',       date_trunc('month', NOW()) + INTERVAL '2 days'),
  ('+2348025550104', date_trunc('month', NOW()) + INTERVAL '6 days 15 hours',  'completed', '[demo-seed] cleaning',         date_trunc('month', NOW()) + INTERVAL '3 days'),
  ('+2348065550103', date_trunc('month', NOW()) + INTERVAL '9 days 11 hours',  'completed', '[demo-seed] check-up',         date_trunc('month', NOW()) + INTERVAL '5 days'),
  ('+2348095550106', date_trunc('month', NOW()) + INTERVAL '11 days 9 hours',  'completed', '[demo-seed] whitening',        date_trunc('month', NOW()) + INTERVAL '8 days'),
  ('+2348035550101', date_trunc('month', NOW()) + INTERVAL '13 days 14 hours', 'completed', '[demo-seed] filling',          date_trunc('month', NOW()) + INTERVAL '10 days'),
  ('+2348155550107', date_trunc('month', NOW()) + INTERVAL '15 days 16 hours', 'completed', '[demo-seed] root canal',       date_trunc('month', NOW()) + INTERVAL '13 days')
) AS raw(phone, ts, st, note, created)
JOIN patients p ON p.phone = raw.phone;

-- ── 3. Escalations (8 across channels + statuses) ───────────────────────
DELETE FROM escalations WHERE payload->>'seed' = 'demo';

-- 3 open — these drive the "Waiting for you" tile + inbox top.
INSERT INTO escalations (session_id, reason, channel, patient_id, message_preview, status, created_at, payload)
SELECT
  'voice:' || p.phone,
  'Patient asking about specific antibiotic dosage — safer to have a clinician confirm.',
  'voice',
  p.id,
  'Hi, my dentist said take amoxicillin — how many mg is safe if I''m breastfeeding?',
  'open',
  NOW() - INTERVAL '18 minutes',
  '{"seed":"demo"}'::jsonb
FROM patients p WHERE p.phone = '+2348035550101';

INSERT INTO escalations (session_id, reason, channel, patient_id, message_preview, status, created_at, payload)
SELECT
  'whatsapp:' || p.phone,
  'Patient described swelling + fever — red-flag intent, needs triage.',
  'whatsapp',
  p.id,
  'The right side of my jaw is swollen since yesterday and I feel feverish — should I come in?',
  'open',
  NOW() - INTERVAL '42 minutes',
  '{"seed":"demo"}'::jsonb
FROM patients p WHERE p.phone = '+2348075550105';

INSERT INTO escalations (session_id, reason, channel, patient_id, message_preview, status, created_at, payload)
SELECT
  'email:' || p.email,
  'Billing dispute for last visit — out of scope for MainDesk.',
  'email',
  p.id,
  'The receipt from May 22 shows two charges for the same cleaning, can someone double-check?',
  'open',
  NOW() - INTERVAL '2 hours 5 minutes',
  '{"seed":"demo"}'::jsonb
FROM patients p WHERE p.phone = '+2348155550107';

-- 2 approved — recent staff resolutions, feed the "escalations_this_month" analytic.
INSERT INTO escalations (session_id, reason, channel, patient_id, message_preview, status, note, created_at, resolved_at, payload)
SELECT
  'web:' || 'kwame-session-x1',
  'Patient asked about insurance coverage for whitening.',
  'web',
  p.id,
  'Does Hygeia cover cosmetic whitening or only cleaning?',
  'approved',
  'Confirmed with Aisha at reception — whitening is out of pocket, cleaning covered.',
  NOW() - INTERVAL '2 days 3 hours',
  NOW() - INTERVAL '2 days 2 hours',
  '{"seed":"demo"}'::jsonb
FROM patients p WHERE p.phone = '+2348065550103';

INSERT INTO escalations (session_id, reason, channel, patient_id, message_preview, status, note, created_at, resolved_at, payload)
SELECT
  'voice:' || p.phone,
  'First-time visitor asked to speak to Dr. Adaeze directly.',
  'voice',
  p.id,
  'I was referred by my sister — could I speak with Dr. Adaeze before booking?',
  'approved',
  'Dr. Adaeze called back same day. Booked for next Wednesday.',
  NOW() - INTERVAL '4 days 1 hour',
  NOW() - INTERVAL '4 days',
  '{"seed":"demo"}'::jsonb
FROM patients p WHERE p.phone = '+2348135550108';

-- 1 redirected — patient sent to the doctor for a telemed consult.
INSERT INTO escalations (session_id, reason, channel, patient_id, message_preview, status, note, created_at, resolved_at, payload)
SELECT
  'whatsapp:' || p.phone,
  'Patient asked for a telemedicine call rather than in-person.',
  'whatsapp',
  p.id,
  'Can I do the follow-up on video? Traffic on Third Mainland is terrible.',
  'redirected',
  'Routed to Dr. Ola — telemed slot Thursday 4pm.',
  NOW() - INTERVAL '1 day 6 hours',
  NOW() - INTERVAL '1 day 5 hours',
  '{"seed":"demo"}'::jsonb
FROM patients p WHERE p.phone = '+2348095550106';

-- 2 closed — one wrong-number, one spam. Rounds out the mix.
INSERT INTO escalations (session_id, reason, channel, patient_id, message_preview, status, note, created_at, resolved_at, payload)
SELECT
  'voice:' || p.phone,
  'Unrelated to clinic — caller was trying to reach a pharmacy.',
  'voice',
  p.id,
  'Hello — is this Green Cross Pharmacy Yaba?',
  'closed',
  'Wrong number, wished them well.',
  NOW() - INTERVAL '3 days 2 hours',
  NOW() - INTERVAL '3 days 2 hours',
  '{"seed":"demo"}'::jsonb
FROM patients p WHERE p.phone = '+2348125550102';

INSERT INTO escalations (session_id, reason, channel, patient_id, message_preview, status, note, created_at, resolved_at, payload)
SELECT
  'email:' || p.email,
  'Marketing pitch, not a patient query.',
  'email',
  p.id,
  'Introducing SmilePlus dental supplies — 20% off first order for your practice.',
  'closed',
  'Marked as spam.',
  NOW() - INTERVAL '5 days',
  NOW() - INTERVAL '5 days',
  '{"seed":"demo"}'::jsonb
FROM patients p WHERE p.phone = '+2348025550104';

COMMIT;

-- ── 4. Sanity report ─────────────────────────────────────────────────────
\echo '=== Seeded ==='
SELECT 'patients'      AS what, COUNT(*) AS n FROM patients
UNION ALL
SELECT 'appointments (this month + upcoming)', COUNT(*) FROM appointments WHERE notes LIKE '[demo-seed]%'
UNION ALL
SELECT 'escalations open',      COUNT(*) FROM escalations WHERE status = 'open'      AND payload->>'seed' = 'demo'
UNION ALL
SELECT 'escalations approved',  COUNT(*) FROM escalations WHERE status = 'approved'  AND payload->>'seed' = 'demo'
UNION ALL
SELECT 'escalations redirected',COUNT(*) FROM escalations WHERE status = 'redirected' AND payload->>'seed' = 'demo'
UNION ALL
SELECT 'escalations closed',    COUNT(*) FROM escalations WHERE status = 'closed'    AND payload->>'seed' = 'demo';
