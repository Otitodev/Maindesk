-- Demo seed for MainDesk — Singapore market instance.
-- One clinic: "Marina Bay Family Dental" (a plausible Singaporean private
-- practice name). Patients reflect Singapore's Chinese / Malay / Indian mix,
-- with local phone format (+65) and local context in escalation messages
-- (MRT, ECP, telemed referrals, SGD billing).
--
-- Idempotent: safe to re-run. Uses ON CONFLICT for patients (unique phone)
-- and deletes prior demo rows by marker before re-inserting.
--
-- Usage on the ECS box:
--   docker exec -i healthdesk-pg psql -U healthdesk healthdesk < scripts/seed_demo.sql

BEGIN;

-- ── 0. Clinic identity ──────────────────────────────────────────────────
-- Merges over any existing config, so re-running the seed won't wipe
-- unrelated settings someone may have set via /onboarding.

INSERT INTO clinic_settings (id, config, updated_at)
VALUES (
  1,
  jsonb_build_object(
    'clinic_name', 'Marina Bay Family Dental',
    'agent_name', 'MainDesk',
    'greeting',   'Good day, thank you for calling Marina Bay Family Dental. This is MainDesk — how may I help you today?',
    'timezone',   'Asia/Singapore',
    'open_hour',  9,
    'close_hour', 19,
    'working_days', '[1,2,3,4,5,6]'::jsonb,
    'answer_mode', 'always',
    'faqs', E'Address: 8 Marina Boulevard #B2-15, Singapore 018981.\nHours: Mon–Sat 9am–7pm, closed Sundays and public holidays.\nInsurers accepted: AIA, Great Eastern, Prudential, NTUC Income, direct MediSave-approved.\nDentists: Dr. Tan Wei Jian (partner, oral surgery), Dr. Chen Mei Xin (paediatric + orthodontics), Dr. Rajeshwaran Kumar (implantology).\nParking: 3 hours complimentary at Marina Bay Financial Centre B2.\nMRT: Downtown Line, Marina Bay station Exit E, 4-minute walk.\nAfter-hours emergency: patients call the +65 6100 4800 hotline; MainDesk logs the call and pages the on-call dentist.'
  ),
  NOW()
)
ON CONFLICT (id) DO UPDATE
  SET config = clinic_settings.config || EXCLUDED.config,
      updated_at = NOW();

-- ── 1. Patients (Singapore cross-section) ───────────────────────────────

INSERT INTO patients (full_name, phone, email) VALUES
  ('Tan Wei Ming',                   '+6591234501', 'weiming.tan@gmail.com'),
  ('Lim Hui Ling',                   '+6582345602', NULL),
  ('Priya Ramanathan',               '+6593456703', 'priya.ramanathan@gmail.com'),
  ('Muhammad Faizal bin Rashid',     '+6584567804', 'faizal.rashid@outlook.sg'),
  ('Cheng Yi Xuan',                  '+6595678905', 'yixuan.cheng@gmail.com'),
  ('Aravind Kumar',                  '+6586789006', NULL),
  ('Nur Aisyah binti Ismail',        '+6597890107', 'nur.aisyah@gmail.com'),
  ('Wong Jia Le',                    '+6588901208', 'jiale.wong@gmail.com')
ON CONFLICT (phone) DO UPDATE
  SET full_name = EXCLUDED.full_name,
      email     = EXCLUDED.email;

-- ── 2. Appointments (12: 6 upcoming, 6 handled this month) ──────────────

DELETE FROM appointments WHERE notes LIKE '[demo-seed]%';

INSERT INTO appointments (patient_id, starts_at, status, notes, created_at)
SELECT p.id, ts, st, note, created
FROM (VALUES
  -- Upcoming (next 14 days)
  ('+6591234501', NOW() + INTERVAL '1 day 10 hours',   'booked',    '[demo-seed] scale & polish',        NOW() - INTERVAL '2 days'),
  ('+6582345602', NOW() + INTERVAL '1 day 14 hours',   'booked',    '[demo-seed] wisdom tooth review',   NOW() - INTERVAL '1 day'),
  ('+6593456703', NOW() + INTERVAL '2 days 9 hours',   'booked',    '[demo-seed] Invisalign consult',    NOW() - INTERVAL '3 days'),
  ('+6588901208', NOW() + INTERVAL '3 days 11 hours',  'booked',    '[demo-seed] first visit — child',   NOW() - INTERVAL '1 day'),
  ('+6597890107', NOW() + INTERVAL '5 days 15 hours',  'booked',    '[demo-seed] filling replacement',   NOW() - INTERVAL '2 days'),
  ('+6586789006', NOW() + INTERVAL '9 days 10 hours',  'booked',    '[demo-seed] implant crown fitting', NOW() - INTERVAL '4 days'),
  -- Past-this-month (completed)
  ('+6584567804', date_trunc('month', NOW()) + INTERVAL '4 days 10 hours',  'completed', '[demo-seed] extraction',                 date_trunc('month', NOW()) + INTERVAL '2 days'),
  ('+6595678905', date_trunc('month', NOW()) + INTERVAL '6 days 15 hours',  'completed', '[demo-seed] scale & polish',             date_trunc('month', NOW()) + INTERVAL '3 days'),
  ('+6593456703', date_trunc('month', NOW()) + INTERVAL '9 days 11 hours',  'completed', '[demo-seed] Invisalign refinement',      date_trunc('month', NOW()) + INTERVAL '5 days'),
  ('+6597890107', date_trunc('month', NOW()) + INTERVAL '11 days 9 hours',  'completed', '[demo-seed] paediatric check-up',        date_trunc('month', NOW()) + INTERVAL '8 days'),
  ('+6591234501', date_trunc('month', NOW()) + INTERVAL '13 days 14 hours', 'completed', '[demo-seed] filling',                    date_trunc('month', NOW()) + INTERVAL '10 days'),
  ('+6586789006', date_trunc('month', NOW()) + INTERVAL '15 days 16 hours', 'completed', '[demo-seed] implant surgery stage 1',    date_trunc('month', NOW()) + INTERVAL '13 days')
) AS raw(phone, ts, st, note, created)
JOIN patients p ON p.phone = raw.phone;

-- ── 3. Escalations (8, all channels, all statuses, local context) ───────

DELETE FROM escalations WHERE payload->>'seed' = 'demo';

-- Open (3) — these drive the "Waiting for you" tile + inbox top.
INSERT INTO escalations (session_id, reason, channel, patient_id, message_preview, status, created_at, payload)
SELECT
  'voice:' || p.phone,
  'Patient asked about a specific antibiotic dosage while breastfeeding — safer to have a clinician confirm.',
  'voice',
  p.id,
  'Hi, Dr. Tan prescribed amoxicillin — is 500mg safe if I am breastfeeding my 4-month-old?',
  'open',
  NOW() - INTERVAL '18 minutes',
  '{"seed":"demo"}'::jsonb
FROM patients p WHERE p.phone = '+6591234501';

INSERT INTO escalations (session_id, reason, channel, patient_id, message_preview, status, created_at, payload)
SELECT
  'whatsapp:' || p.phone,
  'Patient described jaw swelling and fever — red-flag intent, needs same-day triage.',
  'whatsapp',
  p.id,
  'The right side of my jaw is swollen since last night and I feel feverish — should I come to the clinic today or go to A&E?',
  'open',
  NOW() - INTERVAL '42 minutes',
  '{"seed":"demo"}'::jsonb
FROM patients p WHERE p.phone = '+6584567804';

INSERT INTO escalations (session_id, reason, channel, patient_id, message_preview, status, created_at, payload)
SELECT
  'email:' || p.email,
  'Billing dispute — patient sees two charges for one procedure. Out of scope for MainDesk.',
  'email',
  p.id,
  'The AIA claim from my visit on 22 May shows two SGD 180 charges for the same scale & polish. Could someone double-check with the finance team?',
  'open',
  NOW() - INTERVAL '2 hours 5 minutes',
  '{"seed":"demo"}'::jsonb
FROM patients p WHERE p.phone = '+6586789006';

-- Approved (2) — recent staff resolutions.
INSERT INTO escalations (session_id, reason, channel, patient_id, message_preview, status, note, created_at, resolved_at, payload)
SELECT
  'web:kwame-session-x1',
  'Patient asked whether MediSave covers Invisalign.',
  'web',
  p.id,
  'Does MediSave cover Invisalign or only medically-necessary orthodontic work?',
  'approved',
  'Confirmed with Aisha at reception — MediSave covers medically-indicated ortho only; Invisalign for aesthetic reasons is self-pay or Prudential PruShield rider.',
  NOW() - INTERVAL '2 days 3 hours',
  NOW() - INTERVAL '2 days 2 hours',
  '{"seed":"demo"}'::jsonb
FROM patients p WHERE p.phone = '+6593456703';

INSERT INTO escalations (session_id, reason, channel, patient_id, message_preview, status, note, created_at, resolved_at, payload)
SELECT
  'voice:' || p.phone,
  'First-time visitor asked to speak with Dr. Chen before booking a paediatric appointment.',
  'voice',
  p.id,
  'I was referred by my sister — could I speak briefly with Dr. Chen before booking my daughter''s first check-up?',
  'approved',
  'Dr. Chen called back same afternoon. Paediatric slot booked for next Wednesday 4pm.',
  NOW() - INTERVAL '4 days 1 hour',
  NOW() - INTERVAL '4 days',
  '{"seed":"demo"}'::jsonb
FROM patients p WHERE p.phone = '+6588901208';

-- Redirected (1) — patient sent to the doctor for a telemed consult.
INSERT INTO escalations (session_id, reason, channel, patient_id, message_preview, status, note, created_at, resolved_at, payload)
SELECT
  'whatsapp:' || p.phone,
  'Patient asked for a video follow-up instead of coming in.',
  'whatsapp',
  p.id,
  'Can I do the follow-up over video? Rush hour on the ECP is impossible and I am WFH the rest of the week.',
  'redirected',
  'Routed to Dr. Rajeshwaran for a telemed slot Thursday 4pm. Zoom link sent from clinic.',
  NOW() - INTERVAL '1 day 6 hours',
  NOW() - INTERVAL '1 day 5 hours',
  '{"seed":"demo"}'::jsonb
FROM patients p WHERE p.phone = '+6595678905';

-- Closed (2) — wrong number + spam.
INSERT INTO escalations (session_id, reason, channel, patient_id, message_preview, status, note, created_at, resolved_at, payload)
SELECT
  'voice:' || p.phone,
  'Unrelated — caller was trying to reach a nearby physiotherapy clinic.',
  'voice',
  p.id,
  'Hello ah, is this Marina Physio Wellness at Raffles Place?',
  'closed',
  'Wrong number, wished them well and gave the physio''s direct line.',
  NOW() - INTERVAL '3 days 2 hours',
  NOW() - INTERVAL '3 days 2 hours',
  '{"seed":"demo"}'::jsonb
FROM patients p WHERE p.phone = '+6582345602';

INSERT INTO escalations (session_id, reason, channel, patient_id, message_preview, status, note, created_at, resolved_at, payload)
SELECT
  'email:' || p.email,
  'Marketing pitch, not a patient query.',
  'email',
  p.id,
  'Introducing DentSupply Asia — 20% off consumables for your first order. Reach 500+ practices across SG, MY, and ID.',
  'closed',
  'Marked as spam and unsubscribed.',
  NOW() - INTERVAL '5 days',
  NOW() - INTERVAL '5 days',
  '{"seed":"demo"}'::jsonb
FROM patients p WHERE p.phone = '+6597890107';

COMMIT;

-- ── 4. Sanity report ─────────────────────────────────────────────────────
\echo '=== Marina Bay Family Dental seed applied ==='
SELECT 'patients'      AS what, COUNT(*) AS n FROM patients
UNION ALL
SELECT 'appointments (this month + upcoming)', COUNT(*) FROM appointments WHERE notes LIKE '[demo-seed]%'
UNION ALL
SELECT 'escalations open',      COUNT(*) FROM escalations WHERE status = 'open'       AND payload->>'seed' = 'demo'
UNION ALL
SELECT 'escalations approved',  COUNT(*) FROM escalations WHERE status = 'approved'   AND payload->>'seed' = 'demo'
UNION ALL
SELECT 'escalations redirected',COUNT(*) FROM escalations WHERE status = 'redirected' AND payload->>'seed' = 'demo'
UNION ALL
SELECT 'escalations closed',    COUNT(*) FROM escalations WHERE status = 'closed'     AND payload->>'seed' = 'demo';
