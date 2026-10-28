/* ═══════════════════════════════════════════════════════════════════════════
   selfhost.js — build-mode switch for the frontend
   ═══════════════════════════════════════════════════════════════════════════
   The self-host build (SELFHOST=1 in the backend) has no billing, no turn
   economy, no voice narration and no image generation. Rather than fork every
   page, each page loads this file last; it asks /api/config what THIS build can
   do and then hides the controls that would only ever answer 501.

   Hosted behaviour is untouched: when /api/config reports selfhost:false the
   script does nothing but define window.LWC_CONFIG.

   No framework, no dependencies. Everything is guarded so a page without the
   expected elements never throws.
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  window.LWC_CONFIG = null;

  /* Controls that only exist in the hosted build. Ids verified against the
     pages themselves (chat/adventure/login/character). */
  var HIDDEN_IDS = [
    'update-banner',        // "Free every day: 20 turns…"
    'rr-quota-row', 'rr-quota', 'rr-quota-sep', 'rr-turn',
    'turn-pill', 'quota-pill', 'quota-warn',
    'cap-modal', 'cap-backdrop',
    'tts-bar', 'tts-player', 'tts-voice-btn', 'tts-auto-btn', 'tts-speed-btn',
    'tts-popover', 'mic-btn', 'adventure-tts'
  ];

  var HIDDEN_SELECTORS = [
    'a[href*="pricing"]',
    'a[href*="local-ai"]',
    '[data-billing]'
  ];

  function hide(el) {
    if (!el) return;
    el.style.display = 'none';
    el.setAttribute('data-selfhost-hidden', '1');
  }

  function badge(cfg) {
    if (document.getElementById('selfhost-badge')) return;
    var model = (cfg.default_model || '').replace(/^ollama:/, '');
    /* "igorls/gemma-4-e4b-it-heretic-GGUF:q4_k_m" is a sentence, not a badge:
       keep the family name, drop the owner and the quant tag. */
    var short = model ? model.split('/').pop().split(':')[0] : 'no local model';

    var b = document.createElement('div');
    b.id = 'selfhost-badge';
    b.title = 'Self-host build — no billing, no turn limits, local models only.\n'
      + 'Model: ' + (model || 'none found');
    /* A small dot that grows into a label on hover: a permanent chip collides
       with page copy on narrow layouts, which is worse than being quiet. */
    b.style.cssText = [
      'position:fixed', 'left:12px', 'bottom:12px', 'z-index:60',
      'display:flex', 'align-items:center', 'justify-content:center',
      'width:26px', 'height:26px', 'border-radius:50%',
      'font:600 11px/1 ui-monospace,SFMono-Regular,Menlo,monospace',
      'color:#c9a227', 'background:rgba(10,8,14,.8)',
      'border:1px solid rgba(201,162,39,.4)', 'cursor:help',
      'opacity:.55', 'overflow:hidden', 'white-space:nowrap',
      'transition:opacity .18s,width .18s,border-radius .18s,padding .18s'
    ].join(';');
    b.textContent = '⚗';
    b.addEventListener('mouseenter', function () {
      b.textContent = 'self-host · ' + short;
      b.style.width = 'auto';
      b.style.padding = '5px 9px';
      b.style.borderRadius = '3px';
      b.style.opacity = '.95';
      b.style.letterSpacing = '.1em';
      b.style.textTransform = 'uppercase';
    });
    b.addEventListener('mouseleave', function () {
      b.textContent = '⚗';
      b.style.width = '26px';
      b.style.padding = '0';
      b.style.borderRadius = '50%';
      b.style.opacity = '.55';
    });
    document.body.appendChild(b);
  }

  function pricingNotice() {
    if (!/pricing\.html$/.test(location.pathname)) return;
    var main = document.querySelector('main') || document.body;
    main.innerHTML = '';
    var box = document.createElement('div');
    box.style.cssText = 'max-width:640px;margin:18vh auto;padding:2rem 1.6rem;text-align:center;' +
      'color:#f4ebde;font-family:Georgia,serif;line-height:1.7';
    box.innerHTML =
      '<h1 style="font-size:1.4rem;letter-spacing:.06em;color:#ecc468;margin-bottom:1rem">' +
      'Nothing to buy here</h1>' +
      '<p>This is a <b>self-host build</b>: there is no Stripe, no unlock and no turn economy. ' +
      'Every account has unlimited turns, undo and campaign export.</p>' +
      '<p style="margin-top:1.2rem"><a href="adventure.html" ' +
      'style="color:#ecc468;text-decoration:underline">Back to the table →</a></p>';
    main.appendChild(box);
  }

  function apply(cfg) {
    document.documentElement.classList.add('selfhost');
    if (document.body) document.body.classList.add('selfhost');
    HIDDEN_IDS.forEach(function (id) { hide(document.getElementById(id)); });
    HIDDEN_SELECTORS.forEach(function (sel) {
      try {
        Array.prototype.forEach.call(document.querySelectorAll(sel), hide);
      } catch (e) { /* invalid selector on an old engine — ignore */ }
    });
    if (!cfg.unlimited_turns) return;
    badge(cfg);
    pricingNotice();
  }

  /* Any page may call this instead of wiring its own error copy. */
  window.selfhostNotice = function (feature) {
    try {
      if (typeof window.toast === 'function') { window.toast(feature + ' is not part of the self-host build.', 'warn'); return; }
    } catch (e) { /* fall through */ }
    window.alert(feature + ' is not part of the self-host build.');
  };

  fetch('/api/config', { credentials: 'same-origin' })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (cfg) {
      if (!cfg) return;
      window.LWC_CONFIG = cfg;
      if (cfg.selfhost) {
        if (document.body) apply(cfg);
        else document.addEventListener('DOMContentLoaded', function () { apply(cfg); });
      }
    })
    .catch(function () { /* offline / blocked — leave the page alone */ });
})();