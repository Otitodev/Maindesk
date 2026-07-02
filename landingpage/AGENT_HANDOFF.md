# MainDesk — Coding Agent Handoff Prompt

Copy everything below this line and paste it as your first message to the agent,
with the four project files attached as context.

FILES TO ATTACH:
  1. maindesk-ds.css            (design system — 781 lines)
  2. maindesk-landing.html      (full landing page — 1,394 lines)
  3. maindesk-ds.html           (living design system docs — 855 lines)
  4. hero-vanta-fog.html        (original hero + features prototype — 829 lines)

═══════════════════════════════════════════════════════════════════════
PROMPT — PASTE FROM HERE
═══════════════════════════════════════════════════════════════════════

You are taking over a frontend project called **MainDesk**. I have
attached four files that represent the complete current state of the project.
Read all four files carefully before making any changes.

---

## Project overview

MainDesk is a SaaS landing page for an AI-powered clinic front desk
agent that handles voice calls, WhatsApp, and email 24/7. The landing page
is currently a **standalone HTML/CSS prototype** and needs to be ported into
a production codebase.

---

## Files in context

### `maindesk-ds.css` — The design system (source of truth)
All design tokens are CSS custom properties in `:root`. Use only these
tokens for any colour, spacing, radius, or shadow. Never introduce new
hex values unless they extend the existing scales.

Key token groups:
- Ink scale: `--ink`, `--ink-mid`, `--ink-soft` (text hierarchy, all WCAG AA)
- Teal scale: `--teal-text` (text-safe), `--teal-ui` (borders/icons),
  `--teal-vivid` (decorative only — never use for body text),
  `--teal-pale` (surfaces)
- Surfaces: `--white`, `--bg-mist` (#f0fafb), `--surface` (frosted glass)
- Borders: `--border` (decorative), `--border-strong` (interactive)
- Fonts: `--font-display` (Sora), `--font-body` (DM Sans)
- Spacing: `--space-1` through `--space-10` (base-8 scale)
- Radius: `--radius-sm/md/lg/xl/pill`
- Shadows: `--shadow-sm/md/lg/xl`
- Semantic: `--green-live` (#22c55e) — ONLY for "active/live" status dots
- Keyframes: `hd-pulse`, `hd-draw`, `hd-drip`

Typography classes: `.text-hero`, `.text-h2`, `.text-h3`, `.text-sub`,
`.text-body`, `.text-sm`, `.text-eyebrow`, `.accent`, `.accent.draw`

Component classes (all documented in `maindesk-ds.html`):
`.hd-nav`, `.hd-nav__logo`, `.hd-nav__links`, `.hd-nav__cta`,
`.badge`, `.badge__dot`,
`.btn`, `.btn--primary`, `.btn--ghost`, `.btn--teal`, `.btn--sm`, `.btn--lg`,
`.section-eyebrow`, `.section-headline`, `.section-sub`,
`.stack-container`, `.feat-card`, `.card-body`, `.feat-icon`,
`.feat-channel`, `.feat-heading`, `.feat-list`, `.feat-footer`,
`.live-dot`, `.status-dot`, `.trust`, `.trust__avatars`, `.trust__avatar`,
`.scroll-hint`, `.scroll-hint__label`, `.scroll-hint__line`

### `maindesk-landing.html` — The full landing page prototype
This is the single file you will be porting. It contains:
1. Nav (fixed, frosted glass on scroll)
2. Hero (Vanta.js fog background)
3. Logos strip (clinic names, mask-fade edges)
4. Features — sticky stack scroll pattern (3 cards: Voice, WhatsApp, Email)
5. How it works (3-step with dashed connector line)
6. Stats (dark navy section, 4 large numbers)
7. Testimonials (3 clinic owner quotes)
8. Pricing (3 tiers: Starter $299 / Growth $599 / Enterprise custom)
9. FAQ (accordion, one-open-at-a-time)
10. Final CTA (dark, teal glow, 3 trust items)
11. Footer (4-col grid, socials, legal)

### `maindesk-ds.html` — Living design system documentation
Use this as a reference for component markup, usage rules, and
copy-paste snippets. It is NOT part of the production build.

### `hero-vanta-fog.html` — Original prototype
Earlier iteration. Superseded by `maindesk-landing.html`.
Use only if you need to diff an earlier version of a component.

---

## Critical patterns — read before touching any code

### 1. Sticky stack cards
```
RULE: The parent section of .stack-container must NEVER have
overflow:hidden or overflow:clip — it silently breaks position:sticky.

HTML structure:
<div class="stack-container">
  <div class="feat-card">...</div>  <!-- z-index:1, margin-bottom:44vh -->
  <div class="feat-card">...</div>  <!-- z-index:2, margin-bottom:44vh -->
  <div class="feat-card">...</div>  <!-- z-index:3, no margin-bottom  -->
</div>

JS (runs on scroll, passive):
const STICKY_TOP = 96;
cards.forEach((card, i) => {
  const next = cards[i + 1];
  if (!next) return;
  card.classList.toggle('buried',
    next.getBoundingClientRect().top <= STICKY_TOP + 2);
});

.buried applies: scale(0.96) translateY(-10px) brightness(0.94)
```

### 2. Vanta fog config (hero background)
```js
VANTA.FOG({
  el: '#vanta-bg',
  mouseControls: true, touchControls: true, gyroControls: false,
  minHeight: 200, minWidth: 200,
  highlightColor: 0x00b4bc,   // --teal-vivid
  midtoneColor:   0xe4f6f7,   // light mist
  lowlightColor:  0x008c97,   // --teal-ui
  baseColor:      0xfafffe,   // near-white
  blurFactor: 0.62, speed: 1.2, zoom: 0.9
});
// CDN deps (load before init):
// three.js r134: cdnjs.cloudflare.com/ajax/libs/three.js/r134/three.min.js
// vanta 0.5.24:  cdn.jsdelivr.net/npm/vanta@0.5.24/dist/vanta.fog.min.js
```

### 3. Nav scroll behaviour
```js
// Adds .scrolled class → background:rgba(255,255,255,0.88) + blur(20px)
window.addEventListener('scroll', () => {
  nav.classList.toggle('scrolled', window.scrollY > 40);
}, { passive: true });
```

### 4. FAQ accordion
```js
// One item open at a time. .open triggers max-height + opacity transition.
document.querySelectorAll('.faq-question').forEach(btn => {
  btn.addEventListener('click', () => {
    const item = btn.closest('.faq-item');
    const isOpen = item.classList.contains('open');
    document.querySelectorAll('.faq-item.open')
      .forEach(i => i.classList.remove('open'));
    if (!isOpen) item.classList.add('open');
  });
});
```

### 5. Accessibility rules (do not break these)
- All text-use teal is `--teal-text` (#006e78, 5.9:1 contrast). Never use
  `--teal-vivid` or `--teal-ui` for body-size text.
- All ink scale tokens pass WCAG AA on white.
- `prefers-reduced-motion` is handled in the DS: all animations disabled.
- Focus ring: `outline: 2px solid var(--teal-ui); outline-offset: 3px`
- `.btn:focus-visible` is defined — do not remove it.

---

## Section background rhythm (do not change)
Hero (white fog) → Logos (white) → Features (#f0fafb) →
How it works (white) → Stats (#0c1c2e dark) → Testimonials (#f0fafb) →
Pricing (white) → FAQ (#f0fafb) → CTA (#0c1c2e dark) → Footer (#060e1a)

---

## Your task

[REPLACE THIS BLOCK WITH YOUR SPECIFIC INSTRUCTION]

Examples:
- "Port this to Next.js 14 with the App Router. Use CSS Modules for the
  design system tokens. Keep all component class names identical."

- "Convert to a React component library. Export each section as a named
  component. Vanta should lazy-load client-side only."

- "Add a working contact form to the CTA section that POSTs to /api/demo.
  Validate name, email (required), clinic name (required), phone (optional).
  Show inline errors using the existing colour tokens."

- "Animate the stats section: numbers count up from 0 when the section
  enters the viewport. Use IntersectionObserver, no external libraries."

- "Make the pricing toggle between monthly and annual billing (20% discount
  on annual). Update displayed prices with JS, no page reload."

---

## Constraints for the agent
- Use only `--token` names from the DS for all colours, spacing, and type.
  No raw hex values or px values that duplicate existing tokens.
- Do not add new npm packages without flagging them first.
- Do not change copy (headlines, body text, testimonials, pricing tiers)
  unless explicitly asked.
- Do not change the section order or remove sections.
- Keep all JS passive event listeners.
- Test sticky stack: inspect that no ancestor of .stack-container has
  overflow:hidden before shipping.

═══════════════════════════════════════════════════════════════════════
END OF PROMPT
═══════════════════════════════════════════════════════════════════════
