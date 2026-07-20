/**
 * MainDesk Embeddable Voice & Chat Widget
 * Deploy to any clinic website with a single script tag.
 *
 * No external SDK, no third-party vendor — voice runs over a direct
 * WebRTC connection to MainDesk's own Pipecat backend (self-hosted,
 * see app/voice/webrtc_router.py), and chat POSTs straight to
 * /webhooks/web. Adapted from a previous Retell-based widget; the FAB,
 * panel, orb animation, and theming are unchanged, only the backend
 * integration layer (this file's "MAINDESK INTEGRATION" section) differs.
 *
 * Usage:
 * <script src="https://maindesk.otito.site/widget/maindesk-widget.js"
 *         data-api-base="https://maindesk.otito.site"
 *         data-mode="dual"
 *         data-color="#3d8f96"
 *         data-title="MainDesk"
 *         data-subtitle="Voice & Chat Support"
 *         data-agent-name="Danny"></script>
 */

(function() {
  'use strict';

  // Capture script reference synchronously before any async work (document.currentScript is null after defer/async)
  const currentScript = document.currentScript || document.querySelector('script[src*="maindesk-widget"]');

  const config = {
    apiBase:      (currentScript?.getAttribute('data-api-base') || '').replace(/\/+$/, ''),
    color:        currentScript?.getAttribute('data-color') || '#3d8f96',
    position:     currentScript?.getAttribute('data-position') || 'bottom-right',
    title:        currentScript?.getAttribute('data-title') || 'MainDesk',
    subtitle:     currentScript?.getAttribute('data-subtitle') || 'Voice & Chat Support',
    mode:         currentScript?.getAttribute('data-mode') || 'dual',
    defaultMode:  currentScript?.getAttribute('data-default-mode') || 'voice',
    agentName:    currentScript?.getAttribute('data-agent-name') || 'Danny',
    greeting:     currentScript?.getAttribute('data-greeting') || '',
    chatGreeting: currentScript?.getAttribute('data-chat-greeting') || '',
    fabText:      currentScript?.getAttribute('data-fab-text') || 'Chat or Talk to...',
    fabStyle:     currentScript?.getAttribute('data-fab-style') || 'pill', // 'pill' | 'circle'
  };

  // Prevent multiple instances
  if (window.MainDeskWidgetLoaded) {
    console.warn('MainDesk Widget already loaded');
    return;
  }
  window.MainDeskWidgetLoaded = true;

  // ── C3: API base URL validation ─────────────────────────────────────────────
  function isValidApiBase(url) {
    try {
      const parsed = new URL(url);
      return parsed.protocol === 'https:';
    } catch {
      return false;
    }
  }

  // ── C1/C2: HTML escaping — never interpolate dynamic data into innerHTML ────
  function esc(str) {
    return String(str == null ? '' : str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  // ── H1: Promise with timeout ────────────────────────────────────────────────
  function withTimeout(promise, ms, fallback) {
    const timer = new Promise((resolve) => setTimeout(() => resolve(fallback), ms));
    return Promise.race([promise, timer]);
  }


  // Inline SVGs — eliminates the Lucide CDN dependency entirely.
  // Icons used: Phone, PhoneOff, MessageCircle, X, Bot, User, Send
  const ICONS = {
    Phone: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07A19.5 19.5 0 0 1 4.69 14a19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 3.62 3h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 10.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/></svg>',
    PhoneOff: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.68 13.31a16 16 0 0 0 3.41 2.6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.42 19.42 0 0 1-3.33-2.67m-2.67-3.34a19.79 19.79 0 0 1-3.07-8.63A2 2 0 0 1 3.62 3h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 10.91"/><line x1="2" y1="2" x2="22" y2="22"/></svg>',
    MessageCircle: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
    X: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
    Bot: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="10" x="3" y="11" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M12 7v4"/><line x1="8" y1="16" x2="8" y2="16"/><line x1="16" y1="16" x2="16" y2="16"/></svg>',
    User: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>',
    Send: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>',
    Menu: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="4" y1="6" x2="20" y2="6"/><line x1="4" y1="12" x2="20" y2="12"/><line x1="4" y1="18" x2="20" y2="18"/></svg>',
  };

  function createIcon(name) {
    return ICONS[name] || ICONS.MessageCircle;
  }

  // No-op retained so any remaining call sites don't throw
  function initializeLucideIcons() {}

  // Derive orb palette from config.color (hex) — primary + two complementary hues
  function orbPalette(hex) {
    hex = hex.replace('#', '');
    if (hex.length === 3) hex = hex.split('').map(c => c + c).join('');
    const r = parseInt(hex.slice(0,2),16)/255, g = parseInt(hex.slice(2,4),16)/255, b = parseInt(hex.slice(4,6),16)/255;
    const max = Math.max(r,g,b), min = Math.min(r,g,b), d = max - min;
    let h = 0, s = 0;
    const l = (max + min) / 2;
    if (d > 0) {
      s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
      if (max === r) h = ((g - b) / d + (g < b ? 6 : 0)) / 6;
      else if (max === g) h = ((b - r) / d + 2) / 6;
      else h = ((r - g) / d + 4) / 6;
    }
    const hd = Math.round(h * 360);
    // Jewel look: vivid saturated base, lighter shimmer blobs on top.
    const vs = Math.round(Math.min(1, (s || 0.7) * 1.3) * 100);
    const h2 = (hd + 150) % 360;
    const h3 = (hd + 240) % 360;
    const c = (h, sat, lit, alpha) => alpha != null
      ? `hsl(${h} ${sat}% ${lit}% / ${alpha})`
      : `hsl(${h} ${sat}% ${lit}%)`;
    return {
      // Shimmer facet blobs — lighter than base so they catch "light"
      b1:   c(hd, vs, 78),
      b1b:  c(hd, vs, 62),
      b2:   c(h2, 82, 74),
      b2b:  c(h2, 82, 58),
      b3:   c(h3, 86, 72),
      b3b:  c(h3, 86, 56),
      b4:   c(hd, 50, 92),   // near-white top specular facet
      b4b:  c(hd, 55, 80),
      // Base: rich saturated jewel color, darker at the edges for depth
      base: c(hd, 90, 48),
      mid:  c(hd, 85, 32),
      deep: c(hd, 78, 18),
      glow: c(hd, 90, 55, 0.55),
      glowListen: c(h3, 88, 65, 0.65),
      glowTalk:   c(hd, 95, 62, 0.70),
    };
  }

  // Inject CSS styles
  function injectStyles() {
    const orb = orbPalette(config.color);
    const css = `
      /* ── FAB: pill shape ── */
      #fluvio-fab {
        position: fixed;
        bottom: 20px;
        right: 20px;
        height: min(48px, 9vh);
        padding: min(7px, 1.4vh) min(16px, 3vh) min(7px, 1.4vh) min(7px, 1.4vh);
        border-radius: 999px;
        background: ${config.color};
        color: #fff;
        display: flex;
        align-items: center;
        gap: min(9px, 1.8vh);
        cursor: pointer;
        z-index: 999999;
        box-shadow: 0 6px 24px ${orb.glow};
        transition: box-shadow 0.25s ease, transform 0.25s ease;
        animation: fluvio-fab-float 3s ease-in-out infinite;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        border: none;
        white-space: nowrap;
      }
      #fluvio-fab:hover,
      #fluvio-fab[aria-expanded="true"] {
        animation-play-state: paused;
        transform: translateY(-4px);
        box-shadow: 0 12px 40px ${orb.glowListen};
      }
      /* ── Circle FAB variant ── */
      #fluvio-fab.fluvio-fab--circle {
        width: 56px;
        height: 56px;
        padding: 0;
        justify-content: center;
        gap: 0;
        border-radius: 50%;
      }
      .fluvio-fab-chevron {
        transition: transform 0.3s ease;
        flex-shrink: 0;
      }
      #fluvio-fab[aria-expanded="true"] .fluvio-fab-chevron {
        transform: rotate(180deg);
      }

      @keyframes fluvio-fab-float {
        0%, 100% { transform: translateY(0); }
        50%       { transform: translateY(-6px); }
      }
      .fluvio-fab-orb {
        width: min(32px, 6vh);
        height: min(32px, 6vh);
        border-radius: 50%;
        flex-shrink: 0;
        background:
          radial-gradient(circle at 30% 30%, rgba(255,255,255,0.42) 0%, transparent 50%),
          conic-gradient(from 200deg at 50% 50%, ${orb.b4}, ${orb.b1}, ${orb.b2}, ${orb.b1b}, ${orb.b4});
      }
      .fluvio-fab-text {
        font-size: min(14px, 2.6vh);
        font-weight: 600;
        color: #fff;
        max-width: 140px;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      /* Collapse to icon-only on very short viewports (e.g. small iframes) */
      @media (max-height: 450px) {
        .fluvio-fab-text { display: none; }
        #fluvio-fab { padding: min(10px, 2vh); gap: 0; }
      }

      /* ── Panel (transitions-dev panel reveal) ── */
      /* Universal install: panel reveal custom properties */
      :root {
        --panel-open-dur: 400ms;
        --panel-close-dur: 350ms;
        --panel-translate-y: 100px;
        --panel-blur: 2px;
        --panel-ease: cubic-bezier(0.22, 1, 0.36, 1);
      }
      #fluvio-panel {
        position: fixed;
        bottom: 84px;
        right: 20px;
        width: 380px;
        max-width: calc(100vw - 40px);
        height: min(560px, calc(100vh - 130px));
        max-height: calc(100vh - 130px);
        background: #fff;
        border-radius: 20px;
        box-shadow: 0 20px 60px rgba(0,0,0,0.15);
        z-index: 999999;
        display: flex;
        flex-direction: column;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        overflow: hidden;
        /* Hidden by default — shown via data-open */
        visibility: hidden;
        opacity: 0;
        transform: translateY(var(--panel-translate-y));
        filter: blur(var(--panel-blur));
        transition:
          opacity var(--panel-open-dur) var(--panel-ease),
          transform var(--panel-open-dur) var(--panel-ease),
          filter var(--panel-open-dur) var(--panel-ease),
          visibility 0s var(--panel-open-dur);
      }
      /* Open state */
      #fluvio-panel[data-open] {
        visibility: visible;
        opacity: 1;
        transform: translateY(0);
        filter: blur(0);
        transition:
          opacity var(--panel-open-dur) var(--panel-ease),
          transform var(--panel-open-dur) var(--panel-ease),
          filter var(--panel-open-dur) var(--panel-ease),
          visibility 0s 0s;
      }
      /* Closing state — slides down + blur out */
      #fluvio-panel.is-closing {
        opacity: 0;
        transform: translateY(var(--panel-translate-y));
        filter: blur(var(--panel-blur));
        transition:
          opacity var(--panel-close-dur) var(--panel-ease),
          transform var(--panel-close-dur) var(--panel-ease),
          filter var(--panel-close-dur) var(--panel-ease),
          visibility 0s var(--panel-close-dur);
      }
      @media (prefers-reduced-motion: reduce) {
        #fluvio-panel,
        #fluvio-panel[data-open],
        #fluvio-panel.is-closing {
          transition: opacity 0.15s ease, visibility 0s 0s;
          transform: none;
          filter: none;
        }
      }

      /* ── Header: white ── */
      #fluvio-header {
        background: #fff;
        padding: 14px 16px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        border-bottom: 1px solid #E5E7EB;
        flex-shrink: 0;
        min-height: 52px;
      }
      #fluvio-header-brand {
        font-size: 14px;
        font-weight: 700;
        color: #1F2937;
        letter-spacing: -0.01em;
      }
      #fluvio-back {
        all: unset;
        box-sizing: border-box;
        background: none;
        border: none;
        color: #6B7280;
        cursor: pointer;
        padding: 4px;
        border-radius: 6px;
        display: none;
        align-items: center;
        justify-content: center;
        width: 32px;
        height: 32px;
        transition: background 0.2s;
        flex-shrink: 0;
      }
      #fluvio-back:hover { background: #F3F4F6; }
      #fluvio-back svg { width: 18px; height: 18px; }
      #fluvio-close {
        all: unset;
        box-sizing: border-box;
        background: none;
        border: none;
        color: #6B7280;
        cursor: pointer;
        padding: 4px;
        border-radius: 6px;
        transition: background 0.2s ease;
        width: 32px;
        height: 32px;
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
      }
      #fluvio-close svg { width: 18px; height: 18px; }
      #fluvio-close:hover { background: #F3F4F6; }

      /* ── Content area (flex column, fills space between header and tabs/footer) ── */
      #fluvio-content {
        flex: 1;
        display: flex;
        flex-direction: column;
        overflow: hidden;
        min-height: 0;
      }

      /* ── Content containers ── */
      #fluvio-voice-container,
      #fluvio-chat-container {
        display: none;
        flex: 1;
        min-height: 0;
      }
      #fluvio-voice-container.active {
        display: flex;
        flex-direction: column;
        align-items: center;
        overflow-y: auto;
        padding: 14px 20px 16px;
      }
      #fluvio-timer {
        font-size: 13px;
        color: #9CA3AF;
        text-align: center;
        margin-bottom: 6px;
        font-variant-numeric: tabular-nums;
        letter-spacing: 0.06em;
        font-weight: 500;
      }
      #fluvio-voice-title {
        font-size: 17px;
        font-weight: 700;
        color: #111827;
        text-align: center;
        margin-bottom: 4px;
        line-height: 1.3;
      }
      #fluvio-voice-subtitle {
        font-size: 12px;
        color: #6B7280;
        text-align: center;
        margin-bottom: 14px;
        line-height: 1.4;
      }
      #fluvio-status-section {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 12px;
        padding: 8px 14px;
        background: #F9FAFB;
        border-radius: 10px;
        width: 100%;
      }
      #fluvio-status-label {
        font-size: 13px;
        color: #6B7280;
        font-weight: 500;
      }
      #fluvio-status {
        font-size: 13px;
        font-weight: 600;
        color: #374151;
      }
      #fluvio-status.offline   { color: #6B7280; }
      #fluvio-status.connecting { color: #F59E0B; }
      #fluvio-status.online    { color: #10B981; }

      #fluvio-call-button {
        all: unset;
        box-sizing: border-box;
        width: 100%;
        padding: 14px 24px;
        border: none;
        border-radius: 999px;
        font-size: 15px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.2s ease;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      }
      #fluvio-call-button svg { width: 18px; height: 18px; }
      #fluvio-call-button.start {
        background: ${config.color};
        color: #fff;
      }
      #fluvio-call-button.start:hover:not(:disabled) {
        background: ${config.color}dd;
        transform: translateY(-1px);
      }
      #fluvio-call-button.end {
        background: #EF4444;
        color: #fff;
      }
      #fluvio-call-button.end:hover:not(:disabled) {
        background: #DC2626;
        transform: translateY(-1px);
      }
      #fluvio-call-button:disabled {
        opacity: 0.55;
        cursor: not-allowed;
        transform: none !important;
      }

      /* ── Gradient-mesh orb ── */
      #fluvio-orb-wrapper {
        position: relative;
        width: min(130px, 22vh);
        height: min(130px, 22vh);
        display: flex;
        align-items: center;
        justify-content: center;
        margin: 4px auto 10px;
        flex-shrink: 0;
      }
      #fluvio-orb-ripple, #fluvio-orb-ripple2 {
        position: absolute;
        inset: -8px;
        border-radius: 50%;
        border: 2px solid rgba(168,139,250,0.3);
        opacity: 0;
      }

      /* ── Core: vivid jewel sphere — shimmer blobs on top ── */
      #fluvio-orb-core {
        position: relative;
        width: min(110px, 18.5vh);
        height: min(110px, 18.5vh);
        border-radius: 50%;
        overflow: hidden;
        background: radial-gradient(circle at 42% 36%, ${orb.base} 0%, ${orb.mid} 55%, ${orb.deep} 100%);
        box-shadow:
          0 0 52px 10px ${orb.glow},
          inset 0 0 30px ${orb.deep};
        animation: fluvio-orb-breathe 5s ease-in-out infinite;
        flex-shrink: 0;
      }

      /* ── Coloured blobs — alpha-composite on branded base ── */
      .fluvio-orb-blob {
        position: absolute;
        border-radius: 50%;
      }
      /* Primary shimmer — center */
      #fluvio-blob-1 {
        width: min(100px, 17vh); height: min(100px, 17vh);
        background: radial-gradient(circle, ${orb.b1} 0%, ${orb.b1b} 50%, transparent 75%);
        top: 28%; left: 22%;
        opacity: 0.75;
        filter: blur(16px);
        animation: fluvio-blob-1 8s ease-in-out infinite;
      }
      /* Complementary shimmer — top-left facet */
      #fluvio-blob-2 {
        width: min(95px, 16vh); height: min(95px, 16vh);
        background: radial-gradient(circle, ${orb.b2} 0%, ${orb.b2b} 45%, transparent 72%);
        top: 2%; left: -2%;
        opacity: 0.70;
        filter: blur(14px);
        animation: fluvio-blob-2 10s ease-in-out infinite;
      }
      /* Triad shimmer — bottom-right facet */
      #fluvio-blob-3 {
        width: min(85px, 14.5vh); height: min(85px, 14.5vh);
        background: radial-gradient(circle, ${orb.b3} 0%, ${orb.b3b} 45%, transparent 72%);
        top: 48%; left: 20%;
        opacity: 0.68;
        filter: blur(18px);
        animation: fluvio-blob-3 12s ease-in-out infinite;
      }
      /* Near-white top specular — crown of the gem */
      #fluvio-blob-4 {
        width: min(70px, 12vh); height: min(55px, 9.5vh);
        background: radial-gradient(circle, ${orb.b4} 0%, ${orb.b4b} 40%, transparent 70%);
        top: 0%; left: 20%;
        opacity: 0.65;
        filter: blur(12px);
        animation: fluvio-blob-4 14s ease-in-out infinite;
      }
      /* Glossy specular highlight */
      #fluvio-orb-shine {
        position: absolute;
        width: 52px; height: 34px;
        background: radial-gradient(ellipse, rgba(255,255,255,0.55) 0%, rgba(255,255,255,0.08) 55%, transparent 100%);
        top: 13px; left: 17px;
        border-radius: 50%;
        filter: blur(3px);
        transform: rotate(-22deg);
        pointer-events: none;
      }

      /* Blob drift keyframes */
      @keyframes fluvio-blob-1 {
        0%,100% { transform: translate(0,0) scale(1); }
        35%      { transform: translate(-28px,-18px) scale(1.18); }
        68%      { transform: translate(12px, 16px) scale(0.88); }
      }
      @keyframes fluvio-blob-2 {
        0%,100% { transform: translate(0,0) scale(1); }
        42%      { transform: translate(26px, 14px) scale(1.22); }
        72%      { transform: translate(-8px,-10px) scale(0.9); }
      }
      @keyframes fluvio-blob-3 {
        0%,100% { transform: translate(0,0) scale(1); }
        50%      { transform: translate(18px,-22px) scale(1.12); }
      }
      @keyframes fluvio-blob-4 {
        0%,100% { transform: translate(0,0); }
        55%      { transform: translate(22px, 14px); }
      }
      @keyframes fluvio-orb-breathe {
        0%,100% { transform: scale(1);    box-shadow: 0 0 52px 10px ${orb.glow}, inset 0 0 30px ${orb.deep}; }
        50%      { transform: scale(1.04); box-shadow: 0 0 72px 16px ${orb.glow}, inset 0 0 30px ${orb.deep}; }
      }

      /* ── State variants ── */
      /* Listening: faster blobs, triad-hue outer glow */
      #fluvio-orb-core[data-state="listening"] {
        animation: fluvio-orb-breathe 2.4s ease-in-out infinite;
        box-shadow: 0 0 56px 12px ${orb.glowListen}, inset 0 0 30px ${orb.deep};
      }
      #fluvio-orb-core[data-state="listening"] #fluvio-blob-1 { animation-duration: 3.5s; }
      #fluvio-orb-core[data-state="listening"] #fluvio-blob-2 { animation-duration: 4.5s; }
      #fluvio-orb-core[data-state="listening"] #fluvio-blob-3 { animation-duration: 5.5s; }
      #fluvio-orb-core[data-state="listening"] #fluvio-blob-4 { animation-duration: 6s; }

      /* Ripple ring during listening */
      #fluvio-orb-wrapper.listening #fluvio-orb-ripple {
        animation: fluvio-orb-ripple-out 1.8s ease-out infinite;
        border-color: ${orb.glowListen};
      }

      /* Talking: fast pulse */
      #fluvio-orb-core[data-state="talking"] {
        animation: fluvio-orb-talk-pulse 0.9s ease-in-out infinite alternate;
      }
      #fluvio-orb-core[data-state="talking"] #fluvio-blob-1 { animation-duration: 1.5s; opacity: 1; }
      #fluvio-orb-core[data-state="talking"] #fluvio-blob-2 { animation-duration: 1.9s; }
      #fluvio-orb-core[data-state="talking"] #fluvio-blob-3 { animation-duration: 2.3s; }
      #fluvio-orb-core[data-state="talking"] #fluvio-blob-4 { animation-duration: 2.8s; }

      #fluvio-orb-wrapper.talking #fluvio-orb-ripple {
        animation: fluvio-orb-ripple-out 1.1s ease-out infinite;
        border-color: ${orb.glow};
      }
      #fluvio-orb-wrapper.talking #fluvio-orb-ripple2 {
        animation: fluvio-orb-ripple-out 1.1s ease-out infinite 0.55s;
        border-color: ${orb.glow};
      }

      @keyframes fluvio-orb-talk-pulse {
        from { transform: scale(1);    box-shadow: 0 0 56px 10px ${orb.glowTalk}, inset 0 0 30px ${orb.deep}; }
        to   { transform: scale(1.06); box-shadow: 0 0 80px 22px ${orb.glowTalk}, inset 0 0 30px ${orb.deep}; }
      }
      @keyframes fluvio-orb-ripple-out {
        0%   { transform: scale(0.9); opacity: 0.5; }
        100% { transform: scale(1.65); opacity: 0; }
      }

      #fluvio-orb-label {
        font-size: 11px;
        color: #9CA3AF;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        font-weight: 500;
        margin-bottom: 10px;
        text-align: center;
        transition: color 0.4s ease;
        min-height: 16px;
      }

      /* ── Chat container ── */
      #fluvio-chat-container.active {
        display: flex !important;
        flex-direction: column;
        overflow: hidden;
      }
      #fluvio-chat-messages {
        flex: 1;
        min-height: 0;
        overflow-y: auto;
        overflow-x: hidden;
        padding: 16px;
        background: #FAFAFA;
        color: #374151;
        border-bottom: 1px solid #E5E7EB;
      }
      .fluvio-message {
        margin-bottom: 14px;
        display: flex;
        align-items: flex-start;
        gap: 8px;
      }
      .fluvio-message.user { flex-direction: row-reverse; }
      .fluvio-message-avatar {
        width: 30px;
        height: 30px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
      }
      .fluvio-message-avatar svg { width: 15px; height: 15px; }
      .fluvio-message.agent .fluvio-message-avatar { background: ${config.color}; color: #fff; }
      .fluvio-message.user  .fluvio-message-avatar { background: #6B7280; color: #fff; }
      .fluvio-message-content {
        background: #fff;
        padding: 10px 14px;
        border-radius: 12px;
        max-width: 72%;
        font-size: 14px;
        line-height: 1.45;
        border: 1px solid #E5E7EB;
        color: #374151;
        word-break: break-word;
        overflow-wrap: break-word;
        min-width: 0;
      }
      .fluvio-message.user .fluvio-message-content {
        background: ${config.color};
        color: #fff;
        border-color: ${config.color};
      }
      .fluvio-message.agent .fluvio-message-content {
        background: #fff;
        color: #1F2937 !important;
        border-color: #E5E7EB;
      }
      .fluvio-typing-indicator {
        display: none;
        align-items: center;
        gap: 8px;
        color: #6B7280;
        font-size: 13px;
        font-style: italic;
        padding: 8px 16px;
        flex-shrink: 0;
      }
      .fluvio-typing-indicator.show { display: flex; }
      .fluvio-typing-dots { display: flex; gap: 4px; }
      .fluvio-typing-dot {
        width: 6px; height: 6px;
        border-radius: 50%;
        background: #9CA3AF;
        animation: fluvio-typing 1.4s infinite ease-in-out;
      }
      .fluvio-typing-dot:nth-child(1) { animation-delay: -0.32s; }
      .fluvio-typing-dot:nth-child(2) { animation-delay: -0.16s; }
      @keyframes fluvio-typing {
        0%, 80%, 100% { transform: scale(0.8); opacity: 0.5; }
        40%            { transform: scale(1);   opacity: 1; }
      }
      #fluvio-chat-input-container {
        display: flex;
        gap: 8px;
        padding: 12px 16px;
        flex-shrink: 0;
        background: #fff;
      }
      #fluvio-chat-input {
        all: unset;
        box-sizing: border-box;
        display: block;
        flex: 1;
        padding: 10px 14px;
        border: 1px solid #D1D5DB;
        border-radius: 8px;
        font-size: 14px !important;
        resize: none !important;
        height: 42px !important;
        min-height: 42px !important;
        max-height: 120px !important;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        color: #111827;
        background: #fff !important;
        overflow-y: hidden;
        line-height: 1.4 !important;
        width: 100%;
      }
      #fluvio-chat-input:focus {
        outline: none;
        border-color: ${config.color};
        box-shadow: 0 0 0 3px ${config.color}20;
      }
      #fluvio-chat-send {
        all: unset;
        box-sizing: border-box;
        padding: 10px 14px;
        background: ${config.color};
        color: #fff;
        border: none;
        border-radius: 8px;
        cursor: pointer;
        font-size: 14px;
        font-weight: 600;
        transition: background 0.2s ease;
        display: flex;
        align-items: center;
        gap: 6px;
        flex-shrink: 0;
      }
      #fluvio-chat-send svg { width: 16px; height: 16px; }
      #fluvio-chat-send:hover:not(:disabled) { background: ${config.color}dd; }
      #fluvio-chat-send:disabled { background: #9CA3AF; cursor: not-allowed; }

      /* ── Top tab bar ── */
      #fluvio-mode-selector {
        display: flex;
        background: #fff;
        border-bottom: 1px solid #E5E7EB;
        padding: 0 16px;
        gap: 0;
        flex-shrink: 0;
      }
      #fluvio-panel .fluvio-mode-btn {
        all: unset;
        box-sizing: border-box;
        flex: 1;
        padding: 10px 12px 9px;
        border: none;
        border-bottom: 2.5px solid transparent;
        border-radius: 0;
        font-size: 13px;
        font-weight: 600;
        cursor: pointer;
        transition: color 0.2s ease, border-color 0.2s ease;
        background: transparent !important;
        color: #6B7280;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 6px;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        margin-bottom: -1px;
        line-height: 1 !important;
        text-align: center;
        white-space: nowrap;
        box-shadow: none !important;
      }
      #fluvio-panel .fluvio-mode-btn svg { width: 14px; height: 14px; }
      #fluvio-panel .fluvio-mode-btn.active {
        color: ${config.color};
        border-bottom-color: ${config.color};
      }
      #fluvio-panel .fluvio-mode-btn:hover:not(.active) {
        color: ${config.color};
      }

      /* ── Footer ── */
      #fluvio-footer {
        padding: 9px 24px 12px;
        text-align: center;
        border-top: 1px solid #F3F4F6;
        background: #FAFAFA;
        flex-shrink: 0;
      }
      #fluvio-branding {
        font-size: 12px;
        color: #9CA3AF;
        text-decoration: none;
        font-weight: 500;
        transition: color 0.2s ease;
      }
      #fluvio-branding:hover { color: ${config.color}; }

      /* ── Mobile ── */
      @media (max-width: 420px) {
        #fluvio-fab {
          bottom: 16px;
          right: 16px;
        }
        .fluvio-fab-text { max-width: 110px; }
        #fluvio-panel {
          width: calc(100vw - 32px) !important;
          max-width: calc(100vw - 32px) !important;
          right: 16px !important;
          left: 16px !important;
          bottom: 74px !important;
          top: auto !important;
          height: min(560px, calc(100vh - 110px)) !important;
          max-height: calc(100vh - 110px) !important;
        }
        #fluvio-chat-input { font-size: 16px; }
        #fluvio-footer { padding: 7px 16px 10px !important; }
      }
      @media (max-width: 360px) {
        #fluvio-fab { bottom: 12px; right: 12px; }
        #fluvio-panel {
          width: calc(100vw - 24px) !important;
          max-width: calc(100vw - 24px) !important;
          right: 12px !important;
          left: 12px !important;
          bottom: 68px !important;
          border-radius: 16px;
          height: min(560px, calc(100vh - 96px)) !important;
          max-height: calc(100vh - 96px) !important;
        }
      }

      /* ── Position variants ── */
      .fluvio-position-bottom-left #fluvio-fab   { left: 20px; right: auto; }
      .fluvio-position-bottom-left #fluvio-panel { left: 20px; right: auto; }
      .fluvio-position-top-right #fluvio-fab     { top: 20px; bottom: auto; }
      .fluvio-position-top-right #fluvio-panel   { top: 84px; bottom: auto; }
      .fluvio-position-top-left  #fluvio-fab     { top: 20px; left: 20px; bottom: auto; right: auto; }
      .fluvio-position-top-left  #fluvio-panel   { top: 84px; left: 20px; bottom: auto; right: auto; }
      .fluvio-position-center    #fluvio-fab     { left: 0; right: 0; margin: 0 auto; width: fit-content; }
      .fluvio-position-center    #fluvio-panel   { left: 0; right: 0; margin: 0 auto; width: 380px; }
    `;

    const style = document.createElement('style');
    style.textContent = css;
    document.head.appendChild(style);
  }

  // Create widget UI
  function createWidget() {
    document.body.classList.add(`fluvio-position-${config.position}`);

    const fab = document.createElement('div');
    fab.id = 'fluvio-fab';
    if (config.fabStyle === 'circle') {
      fab.classList.add('fluvio-fab--circle');
      fab.innerHTML = `<svg class="fluvio-fab-chevron" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9"></polyline></svg>`;
    } else {
      fab.innerHTML = `<div class="fluvio-fab-orb"></div><span class="fluvio-fab-text">${esc(config.fabText)}</span>`;
    }
    fab.setAttribute('aria-label', 'Open AI assistant');
    fab.setAttribute('aria-expanded', 'false');
    fab.setAttribute('role', 'button');
    fab.setAttribute('tabindex', '0');

    const panel = document.createElement('div');
    panel.id = 'fluvio-panel';

    const showVoiceTab = config.mode === 'dual' || config.mode === 'voice';
    const showChatTab = config.mode === 'dual' || config.mode === 'chat';
    const showTabs = showVoiceTab && showChatTab; // Only show tab bar when both available
    const defaultActive = config.mode === 'chat' ? 'chat' : 'voice';
    const voiceInitActive = defaultActive === 'voice';
    const chatInitActive  = defaultActive === 'chat';

    panel.innerHTML = `
      <div id="fluvio-header">
        <div id="fluvio-header-brand">${esc(config.title)}</div>
        <button id="fluvio-close" aria-label="Close">${createIcon('X')}</button>
      </div>

      ${showTabs ? `
      <div id="fluvio-mode-selector" role="tablist">
        <button class="fluvio-mode-btn active" data-mode="voice" role="tab" aria-selected="${voiceInitActive}">
          ${createIcon('Phone')} Voice
        </button>
        <button class="fluvio-mode-btn" data-mode="chat" role="tab" aria-selected="${chatInitActive}">
          ${createIcon('MessageCircle')} Chat
        </button>
      </div>
      ` : ''}

      <div id="fluvio-content">
        <div id="fluvio-voice-container" class="${voiceInitActive ? 'active' : ''}">
          <div id="fluvio-timer" aria-live="off">00:00</div>
          <div id="fluvio-orb-wrapper" aria-hidden="true">
            <div id="fluvio-orb-glow"></div>
            <div id="fluvio-orb-ripple"></div>
            <div id="fluvio-orb-ripple2"></div>
            <div id="fluvio-orb-core">
              <div class="fluvio-orb-blob" id="fluvio-blob-1"></div>
              <div class="fluvio-orb-blob" id="fluvio-blob-2"></div>
              <div class="fluvio-orb-blob" id="fluvio-blob-3"></div>
              <div class="fluvio-orb-blob" id="fluvio-blob-4"></div>
              <div id="fluvio-orb-shine"></div>
            </div>
          </div>
          <div id="fluvio-orb-label">Ready</div>
          <div id="fluvio-voice-title">${esc(config.title)}</div>
          <div id="fluvio-voice-subtitle">${esc(config.subtitle)}</div>
          <div id="fluvio-status-section">
            <span id="fluvio-status-label">Status:</span>
            <span id="fluvio-status" class="offline" aria-live="polite">Loading...</span>
          </div>
          <button id="fluvio-call-button" class="start" disabled>
            <span id="fluvio-call-icon">${createIcon('Phone')}</span>
            <span id="fluvio-call-text">Start to call</span>
          </button>
        </div>

        <div id="fluvio-chat-container" class="${chatInitActive ? 'active' : ''}">
          <div id="fluvio-chat-messages" aria-live="polite" aria-label="Chat messages"></div>
          <div class="fluvio-typing-indicator" id="fluvio-typing-indicator" aria-live="polite">
            <span>${esc(config.agentName || 'AI')} is typing...</span>
            <div class="fluvio-typing-dots">
              <div class="fluvio-typing-dot"></div>
              <div class="fluvio-typing-dot"></div>
              <div class="fluvio-typing-dot"></div>
            </div>
          </div>
          <div id="fluvio-chat-input-container">
            <textarea id="fluvio-chat-input" placeholder="Type your message..." rows="1"
                      aria-label="Type a message"></textarea>
            <button id="fluvio-chat-send" aria-label="Send message">${createIcon('Send')}</button>
          </div>
        </div>
      </div>

      <div id="fluvio-footer">
        <a href="https://maindesk.otito.site" target="_blank" rel="noopener noreferrer" id="fluvio-branding">Powered by MainDesk</a>
      </div>
    `;

    document.body.appendChild(fab);
    document.body.appendChild(panel);

    function adjustPanelPosition() {
      const fabRect = fab.getBoundingClientRect();
      const panelWidth = Math.min(380, window.innerWidth - 40);
      const panelMaxHeight = Math.min(540, window.innerHeight - 120);
      const margin = 20;

      let left = fabRect.right - panelWidth;
      let right = 'auto';
      let bottom = window.innerHeight - fabRect.top + 12;
      let top = 'auto';

      if (left < margin) { left = margin; right = 'auto'; }
      if (left + panelWidth > window.innerWidth - margin) { left = 'auto'; right = margin; }
      if (bottom + panelMaxHeight > window.innerHeight - margin) { bottom = 'auto'; top = margin; }

      panel.style.left      = left   === 'auto' ? 'auto' : left + 'px';
      panel.style.right     = right  === 'auto' ? 'auto' : right + 'px';
      panel.style.bottom    = bottom === 'auto' ? 'auto' : bottom + 'px';
      panel.style.top       = top    === 'auto' ? 'auto' : top + 'px';
      panel.style.maxHeight = panelMaxHeight + 'px';
      panel.style.width     = panelWidth + 'px';
    }

    panel.adjustPosition = adjustPanelPosition;

    return {
      fab,
      panel,
      statusEl:       document.getElementById('fluvio-status'),
      callButton:     document.getElementById('fluvio-call-button'),
      callText:       document.getElementById('fluvio-call-text'),
      callIcon:       document.getElementById('fluvio-call-icon'),
      chatContainer:  document.getElementById('fluvio-chat-container'),
      chatMessages:   document.getElementById('fluvio-chat-messages'),
      chatInput:      document.getElementById('fluvio-chat-input'),
      chatSend:       document.getElementById('fluvio-chat-send'),
      typingIndicator:document.getElementById('fluvio-typing-indicator'),
      voiceContainer: document.getElementById('fluvio-voice-container'),
      modeSelector:   document.getElementById('fluvio-mode-selector'),
      timerEl:        document.getElementById('fluvio-timer'),
    };
  }
  // ── MAINDESK INTEGRATION: voice ─────────────────────────────────────────────
  // No external SDK, no third-party vendor. Speaks WebRTC directly to
  // MainDesk's own self-hosted Pipecat backend (SmallWebRTCTransport, see
  // app/voice/webrtc_router.py) — the exact same offer/answer/ICE dance as
  // app/voice/templates/web_widget.html, wrapped in an event-emitter shape
  // (`on`, `startCall`, `stopCall`) matching what the panel UI code below
  // already expects, so none of that UI logic needed to change.
  class MainDeskVoiceClient {
    constructor(apiBase) {
      this._apiBase = apiBase;
      this._handlers = {};
      this._pc = null;
      this._audioEl = null;
      this._speakingRaf = null;
      this._audioCtx = null;
      this._isAgentSpeaking = false;
    }

    on(event, handler) {
      (this._handlers[event] = this._handlers[event] || []).push(handler);
    }

    _emit(event, ...args) {
      for (const h of (this._handlers[event] || [])) {
        try { h(...args); } catch (e) { console.error('MainDesk Widget: handler error', e); }
      }
    }

    async startCall() {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const pc = new RTCPeerConnection({
        iceServers: [{ urls: 'stun:stun.l.google.com:19302' }],
      });
      this._pc = pc;
      pc.pendingIceCandidates = [];
      pc.canSendIceCandidates = false;

      pc.onconnectionstatechange = () => {
        const state = pc.connectionState;
        if (state === 'connected') this._emit('call_started');
        else if (state === 'disconnected' || state === 'failed' || state === 'closed') {
          this._emit('call_ended');
        }
      };
      pc.onicecandidate = async (e) => {
        if (!e.candidate) return;
        if (pc.canSendIceCandidates && pc.pc_id) {
          await this._sendIceCandidate(pc, e.candidate);
        } else {
          pc.pendingIceCandidates.push(e.candidate);
        }
      };
      pc.ontrack = (e) => {
        if (!this._audioEl) {
          this._audioEl = document.createElement('audio');
          this._audioEl.autoplay = true;
          this._audioEl.style.display = 'none';
          document.body.appendChild(this._audioEl);
        }
        this._audioEl.srcObject = e.streams[0];
        this._watchAgentSpeaking(e.streams[0]);
      };

      // SmallWebRTCTransport expects both transceivers even for audio-only calls.
      pc.addTransceiver(stream.getAudioTracks()[0], { direction: 'sendrecv' });
      pc.addTransceiver('video', { direction: 'sendrecv' });

      await pc.setLocalDescription(await pc.createOffer());
      const offer = pc.localDescription;
      const response = await fetch(`${this._apiBase}/voice/web/offer`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sdp: offer.sdp, type: offer.type }),
      });
      if (!response.ok) throw new Error(`offer rejected: ${response.status}`);
      const answer = await response.json();
      pc.pc_id = answer.pc_id;
      await pc.setRemoteDescription(answer);

      pc.canSendIceCandidates = true;
      for (const candidate of pc.pendingIceCandidates) {
        await this._sendIceCandidate(pc, candidate);
      }
      pc.pendingIceCandidates = [];
    }

    async _sendIceCandidate(pc, candidate) {
      await fetch(`${this._apiBase}/voice/web/offer`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pc_id: pc.pc_id,
          candidates: [{
            candidate: candidate.candidate,
            sdp_mid: candidate.sdpMid,
            sdp_mline_index: candidate.sdpMLineIndex,
          }],
        }),
      });
    }

    // Approximates Retell's agent_start_talking/agent_stop_talking by
    // watching the incoming audio track's volume — there's no equivalent
    // signal from a plain WebRTC audio track, so we derive one.
    _watchAgentSpeaking(stream) {
      try {
        const Ctx = window.AudioContext || window.webkitAudioContext;
        this._audioCtx = new Ctx();
        const source = this._audioCtx.createMediaStreamSource(stream);
        const analyser = this._audioCtx.createAnalyser();
        analyser.fftSize = 512;
        source.connect(analyser);
        const data = new Uint8Array(analyser.frequencyBinCount);
        const threshold = 12;
        const poll = () => {
          if (!this._pc) return; // call ended, stop polling
          analyser.getByteFrequencyData(data);
          const avg = data.reduce((a, b) => a + b, 0) / data.length;
          const speaking = avg > threshold;
          if (speaking !== this._isAgentSpeaking) {
            this._isAgentSpeaking = speaking;
            this._emit(speaking ? 'agent_start_talking' : 'agent_stop_talking');
          }
          this._speakingRaf = requestAnimationFrame(poll);
        };
        poll();
      } catch (e) {
        console.warn('MainDesk Widget: speaking detection unavailable', e);
      }
    }

    stopCall() {
      if (this._speakingRaf) cancelAnimationFrame(this._speakingRaf);
      this._speakingRaf = null;
      if (this._audioCtx) { try { this._audioCtx.close(); } catch (e) {} this._audioCtx = null; }
      if (this._pc) { try { this._pc.close(); } catch (e) {} this._pc = null; }
      if (this._audioEl) { this._audioEl.remove(); this._audioEl = null; }
      this._emit('call_ended');
    }
  }

  // Initialize widget functionality
  function initializeWidget(elements) {
    let client;
    let isCallActive = false;
    let currentMode = config.defaultMode;
    let currentChatId = null;
    let chatHistory = [];
    let hasShownChatGreeting = false;

    const orbEl    = document.getElementById('fluvio-orb-wrapper');
    const orbLabel = document.getElementById('fluvio-orb-label');

    // ── Timer ──────────────────────────────────────────────────────────────────
    let timerInterval = null;
    let elapsedSeconds = 0;

    function formatTime(s) {
      return String(Math.floor(s / 60)).padStart(2, '0') + ':' + String(s % 60).padStart(2, '0');
    }
    function startTimer() {
      elapsedSeconds = 0;
      if (elements.timerEl) elements.timerEl.textContent = '00:00';
      timerInterval = setInterval(() => {
        elapsedSeconds++;
        if (elements.timerEl) elements.timerEl.textContent = formatTime(elapsedSeconds);
      }, 1000);
    }
    function stopTimer() {
      clearInterval(timerInterval);
      timerInterval = null;
      elapsedSeconds = 0;
      if (elements.timerEl) elements.timerEl.textContent = '00:00';
    }

    function setOrbState(state) {
      if (!orbEl) return;
      orbEl.className = state;
      const labels = { idle: 'Ready', listening: 'Listening…', talking: 'Speaking…' };
      if (orbLabel) orbLabel.textContent = labels[state] || '';
      const core = document.getElementById('fluvio-orb-core');
      if (core) core.dataset.state = state;
    }

    function getAgentDisplayName() {
      const name = (config.agentName || '').trim();
      return name || 'AI';
    }

    function ensureChatGreeting() {
      if (hasShownChatGreeting) return;

      // Prefer dedicated chat greeting, fall back to legacy greeting, then default.
      const greeting = ((config.chatGreeting || config.greeting) || `Hello! How can I help you today?`).trim();

      // Only show greeting when entering chat the first time.
      addChatMessage(greeting, 'agent');
      hasShownChatGreeting = true;
    }

    // M3: Fetch with AbortController timeout
    function fetchWithTimeout(url, options, timeoutMs = 15000) {
      const controller = new AbortController();
      const id = setTimeout(() => controller.abort(), timeoutMs);
      return fetch(url, { ...options, signal: controller.signal })
        .finally(() => clearTimeout(id));
    }

    // ── MAINDESK INTEGRATION: chat ──────────────────────────────────────────
    // No separate "create session" round trip — /webhooks/web just needs a
    // stable session_id, generated once client-side, to key its own
    // conversation state (LangGraph checkpoint) server-side.
    function ensureSessionId() {
      if (!currentChatId) {
        currentChatId = 'widget-' + Math.random().toString(36).slice(2, 11);
      }
      return currentChatId;
    }

    async function sendChatMessage(message) {
      try {
        const response = await fetchWithTimeout(`${config.apiBase}/webhooks/web`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: ensureSessionId(),
            content: message,
          })
        });

        if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);

        const data = await response.json();
        return data && typeof data.content === 'string' && data.content
          ? [{ role: 'agent', content: data.content }]
          : [];
      } catch (error) {
        console.error('Failed to send chat message:', error);
        throw error;
      }
    }

    // C1: Build message bubbles with DOM nodes — never innerHTML for dynamic content
    function addChatMessage(content, role = 'user') {
      if (!elements.chatMessages) return;

      const messageDiv = document.createElement('div');
      messageDiv.className = `fluvio-message ${role}`;

      const avatar = document.createElement('div');
      avatar.className = 'fluvio-message-avatar';
      avatar.innerHTML = role === 'agent' ? createIcon('Bot') : createIcon('User');

      const bubble = document.createElement('div');
      bubble.className = 'fluvio-message-content';
      if (role === 'agent') {
        bubble.style.background = 'white';
        bubble.style.color = '#1F2937';
      }
      bubble.textContent = content; // Safe — no HTML injection possible

      messageDiv.appendChild(avatar);
      messageDiv.appendChild(bubble);

      elements.chatMessages.appendChild(messageDiv);
      elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
      chatHistory.push({ role, content, timestamp: Date.now() });
    }

    function showTypingIndicator() {
      const labelEl = elements.typingIndicator?.querySelector('span');
      if (labelEl) {
        labelEl.textContent = `${getAgentDisplayName()} is typing...`;
      }
      elements.typingIndicator.classList.add('show');
      elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
    }

    function hideTypingIndicator() {
      elements.typingIndicator.classList.remove('show');
    }

    async function handleChatMessage() {
      const message = elements.chatInput.value.trim();
      if (!message) return;


      // Add user message to UI
      addChatMessage(message, 'user');
      elements.chatInput.value = '';
      elements.chatInput.style.height = 'auto';
      elements.chatSend.disabled = true;
      
      showTypingIndicator();

      try {
        // Send message and get response
        const response = await sendChatMessage(message);
        
        hideTypingIndicator();
        
        // Process and display agent responses
        
        if (response && response.length > 0) {
          response.forEach((msg, index) => {
            if (msg.role === 'agent' && msg.content) {
              addChatMessage(msg.content, 'agent');
            } else {
            }
          });
        } else {
          addChatMessage('I received your message. Let me help you with that.', 'agent');
        }
        
        elements.chatSend.disabled = false;
        
      } catch (error) {
        console.error('Chat error:', error);
        hideTypingIndicator();
        
        // Show user-friendly error message
        let errorMessage = 'Sorry, I encountered an error. Please try again.';
        if (error.message.includes('500')) {
          errorMessage = 'The chat service is temporarily unavailable. Please try again in a moment.';
        } else if (error.message.includes('404')) {
          errorMessage = 'Chat service not found. Please check your configuration.';
        }
        
        addChatMessage(errorMessage, 'agent');
        elements.chatSend.disabled = false;
      }
    }

    function switchMode(mode) {
      currentMode = mode;
      if (elements.modeSelector) {
        elements.modeSelector.querySelectorAll('.fluvio-mode-btn').forEach(btn => {
          const active = btn.dataset.mode === mode;
          btn.classList.toggle('active', active);
          btn.setAttribute('aria-selected', active);
        });
      }
      if (elements.voiceContainer) {
        elements.voiceContainer.classList.toggle('active', mode === 'voice');
      }
      if (elements.chatContainer) {
        elements.chatContainer.classList.toggle('active', mode === 'chat');
        if (mode === 'chat') ensureChatGreeting();
      }
    }

    function switchView(view) {
      switchMode(view);
    }

    try {
      if (navigator.mediaDevices && window.RTCPeerConnection) {
        client = new MainDeskVoiceClient(config.apiBase);
      }

      elements.statusEl.textContent = client ? 'Offline' : 'Voice unavailable';
      elements.statusEl.className = client ? 'offline' : 'offline';
      elements.callButton.disabled = !client;

    } catch (error) {
      console.error('MainDesk Widget: failed to create voice client', error);
      elements.statusEl.textContent = 'Voice unavailable';
      elements.statusEl.className = 'offline';
      elements.callButton.disabled = true;
    }

    function closePanel() {
      if (isCallActive) {
        isCallActive = false;
        if (client && client.stopCall) { try { client.stopCall(); } catch (e) {} }
        elements.callButton.className = 'start';
        elements.callButton.disabled = false;
        elements.callText.textContent = 'Start to call';
        elements.callIcon.innerHTML = createIcon('Phone');
        setOrbState('idle');
        elements.statusEl.textContent = 'Offline';
        elements.statusEl.className = 'offline';
        stopTimer();
      }
      // Panel reveal close: add .is-closing, remove data-open after transition
      var panel = elements.panel;
      if (!panel.hasAttribute('data-open')) return;
      panel.classList.add('is-closing');
      panel.removeAttribute('data-open');
      var closeDur = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--panel-close-dur')) || 350;
      setTimeout(function () {
        panel.classList.remove('is-closing');
      }, closeDur);
      elements.fab.setAttribute('aria-expanded', 'false');
      elements.fab.focus();
    }

    function openPanel() {
      if (elements.panel.adjustPosition) elements.panel.adjustPosition();
      var panel = elements.panel;
      // Remove lingering close class, then set data-open
      panel.classList.remove('is-closing');
      // Force reflow so transition replays from closed state
      void panel.offsetWidth;
      panel.setAttribute('data-open', '');
      elements.fab.setAttribute('aria-expanded', 'true');
      switchMode(defaultActive);
      var closeBtn = document.getElementById('fluvio-close');
      if (closeBtn) setTimeout(function () { closeBtn.focus(); }, 50);
    }

    elements.fab.addEventListener('click', () => {
      elements.panel.hasAttribute('data-open') ? closePanel() : openPanel();
    });

    elements.fab.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); elements.fab.click(); }
    });

    // M5: Escape key closes panel
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && elements.panel.hasAttribute('data-open')) closePanel();
    });

    // Mode selector event handlers
    let rafPending = false;
    function throttledAdjust() {
      if (rafPending || !elements.panel.hasAttribute('data-open')) return;
      rafPending = true;
      requestAnimationFrame(() => {
        if (elements.panel.adjustPosition) elements.panel.adjustPosition();
        rafPending = false;
      });
    }
    window.addEventListener('resize', throttledAdjust, { passive: true });
    window.addEventListener('scroll', throttledAdjust, { passive: true });

    document.getElementById('fluvio-close').addEventListener('click', closePanel);

    // H4: Stop call and canvas loop on page navigation
    window.addEventListener('pagehide', () => {
      if (isCallActive && client && client.stopCall) { isCallActive = false; try { client.stopCall(); } catch (e) {} }
    });

    // Mode selector event handlers
    if (elements.modeSelector) {
      elements.modeSelector.addEventListener('click', (e) => {
        if (e.target.classList.contains('fluvio-mode-btn')) {
          const mode = e.target.dataset.mode;
          switchMode(mode);
        }
      });
    }

    // Chat event handlers
    if (elements.chatSend) {
      elements.chatSend.addEventListener('click', handleChatMessage);
    }

    if (elements.chatInput) {
      elements.chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          handleChatMessage();
        }
      });

      // Auto-resize textarea
      elements.chatInput.addEventListener('input', (e) => {
        e.target.style.height = 'auto';
        const maxHeight = window.innerWidth <= 768 ? 96 : 120;
        const newHeight = Math.min(e.target.scrollHeight, maxHeight);
        e.target.style.height = newHeight + 'px';
        e.target.style.overflowY = newHeight >= maxHeight ? 'auto' : 'hidden';
        
        if (elements.panel.hasAttribute('data-open') && elements.panel.adjustPosition) {
          setTimeout(() => {
            elements.panel.adjustPosition();
          }, 10);
        }
      });
    } else {
    }

    // In single chat mode show greeting shortly after init
    if (config.mode === 'chat') {
      setTimeout(() => ensureChatGreeting(), 500);
    }

    elements.callButton.addEventListener('click', async (e) => {
      
      if (elements.callButton.disabled) {
        return;
      }
      
      // MAINDESK INTEGRATION: no token webhook round trip — startCall() does
      // the whole WebRTC offer/answer/ICE dance directly against apiBase.
      if (!isCallActive) {
        try {
          elements.statusEl.textContent = 'Connecting...';
          elements.statusEl.className = 'connecting';
          elements.callButton.disabled = true;

          await client.startCall();

        } catch (error) {
          console.error('Call failed:', error);
          
          // Provide more specific error messages
          let errorMessage = 'Connection failed';
          if (error.message.includes('CORS')) {
            errorMessage = 'CORS error - check webhook';
          } else if (error.message.includes('404')) {
            errorMessage = 'Webhook not found';
          } else if (error.message.includes('Failed to fetch')) {
            errorMessage = 'Network error';
          }
          
          elements.statusEl.textContent = errorMessage;
          elements.statusEl.className = 'offline';
          elements.callButton.disabled = false;
        }
      } else {
        // Reset UI immediately — don't wait for call_ended event
        elements.statusEl.textContent = 'Offline';
        elements.statusEl.className = 'offline';
        isCallActive = false;
        elements.callButton.className = 'start';
        elements.callButton.disabled = false;
        elements.callText.textContent = 'Start to call';
        elements.callIcon.innerHTML = createIcon('Phone');
        setOrbState('idle');
        stopTimer();
        if (client && client.stopCall) {
          try { client.stopCall(); } catch (e) { console.warn('MainDesk Widget: stopCall error', e); }
        }
      }
    });

    // MainDeskVoiceClient event listeners
    if (client) {
      client.on('call_started', () => {
        elements.statusEl.textContent = 'Connected';
        elements.statusEl.className = 'online';
        isCallActive = true;
        elements.callButton.className = 'end';
        elements.callButton.disabled = false;
        elements.callText.textContent = 'End call';
        elements.callIcon.innerHTML = createIcon('PhoneOff');
        setOrbState('listening');
        startTimer();
      });

      client.on('call_ended', () => {
        // Guard: if user already clicked End Call, UI is already reset
        if (!isCallActive) return;
        elements.statusEl.textContent = 'Offline';
        elements.statusEl.className = 'offline';
        isCallActive = false;
        elements.callButton.className = 'start';
        elements.callButton.disabled = false;
        elements.callText.textContent = 'Start to call';
        elements.callIcon.innerHTML = createIcon('Phone');
        setOrbState('idle');
        stopTimer();
      });

      client.on('agent_start_talking', () => {
        elements.statusEl.textContent = 'Agent speaking...';
        elements.statusEl.className = 'online';
        setOrbState('talking');
      });

      client.on('agent_stop_talking', () => {
        elements.statusEl.textContent = 'Listening...';
        elements.statusEl.className = 'online';
        setOrbState('listening');
      });

      client.on('error', (error) => {
        console.error('MainDesk Widget: call error:', error);
        elements.statusEl.textContent = 'Error occurred';
        elements.statusEl.className = 'offline';
        isCallActive = false;
        elements.callButton.className = 'start';
        elements.callButton.disabled = false;
        elements.callText.textContent = 'Start to call';
        elements.callIcon.innerHTML = createIcon('Phone');
        setOrbState('idle');
        stopTimer();
      });
    }

  }

  // Main initialization
  async function init() {
    // C3: Validate the API base before doing anything
    if (!config.apiBase || !isValidApiBase(config.apiBase)) {
      console.error('MainDesk Widget: data-api-base must be a valid https:// URL');
      return;
    }

    try {
      injectStyles();
      const elements = createWidget();
      initializeWidget(elements);
    } catch (error) {
      console.error('MainDesk Widget: initialization failed', error);
    }
  }

  // Start when DOM is ready
  function initWhenReady() {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', init);
    } else {
      // DOM is already ready, but let's wait a tick to ensure all scripts are loaded
      setTimeout(init, 0);
    }
  }

  // Call initialization
  initWhenReady();

})();