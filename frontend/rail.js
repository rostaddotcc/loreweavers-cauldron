/* ═══════════ RAIL v2 — unified header behavior (2026-09-23) ═══════════
   Menu open/close (click + keyboard + outside + Esc), current-page marking,
   auth-aware #rr-auth link, admin-link auto-detect + window.railSetAdmin(bool).
   Skip-link (a11y): injiceras före allt innehåll — hoppar till <main> eller
   första sektionen efter railen. Se docs/rail-v2-spec-2026-09-23.md. */
(function () {
  /* ── Skip-link — injicera FÖRE railen så den blir första tab-stopp ── */
  (function () {
    if (document.getElementById('rr-skip')) return;
    var a = document.createElement('a');
    a.id = 'rr-skip';
    a.className = 'rr-skip';
    a.href = '#rr-main';
    a.textContent = 'Skip to content';
    var target = document.querySelector('main:not(#rr-main)') ||
                 document.querySelector('.rite-rail + *') ||
                 document.querySelector('section, .content, main');
    if (target) {
      if (!target.id) target.id = 'rr-main';
      if (!target.hasAttribute('tabindex')) target.setAttribute('tabindex', '-1');
    } else {
      a.href = '#top';
    }
    document.body.insertBefore(a, document.body.firstChild);
  })();

  var menu = document.querySelector('.rite-rail .rr-menu');
  var drop = document.getElementById('rr-drop');
  if (!menu || !drop) return;
  var btn = document.getElementById('rr-menu-btn');

  function setOpen(open) {
    drop.classList.toggle('open', open);
    if (btn) btn.setAttribute('aria-expanded', open ? 'true' : 'false');
  }
  if (btn) {
    btn.addEventListener('click', function (e) {
      e.stopPropagation();
      setOpen(!drop.classList.contains('open'));
    });
    btn.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); setOpen(!drop.classList.contains('open')); }
      else if (e.key === 'Escape') { setOpen(false); btn.focus(); }
    });
  }
  drop.addEventListener('click', function (e) { e.stopPropagation(); if (e.target.closest('a')) setOpen(false); });
  document.addEventListener('click', function (e) { if (!menu.contains(e.target)) setOpen(false); });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { if (drop.classList.contains('open') && btn) btn.focus(); setOpen(false); }
  });

  /* ── Tangentbordsnavigering i menyn: ↑↓ flyttar fokus mellan synliga länkar ── */
  drop.addEventListener('keydown', function (e) {
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp' && e.key !== 'Home' && e.key !== 'End') return;
    var links = Array.prototype.filter.call(drop.querySelectorAll('a'), function (a) {
      return !a.hidden && a.offsetParent !== null;
    });
    if (!links.length) return;
    e.preventDefault();
    var i = links.indexOf(document.activeElement);
    if (e.key === 'Home') { links[0].focus(); return; }
    if (e.key === 'End') { links[links.length - 1].focus(); return; }
    if (i === -1) { links[0].focus(); return; }
    var next = e.key === 'ArrowDown' ? (i + 1) % links.length : (i - 1 + links.length) % links.length;
    links[next].focus();
  });

  /* ── Markera aktuell sida ── */
  var here = (location.pathname.split('/').pop() || 'index.html').toLowerCase();
  Array.prototype.forEach.call(drop.querySelectorAll('a[href]'), function (a) {
    var t = (a.getAttribute('href') || '').split('#')[0].split('?')[0].split('/').pop().toLowerCase();
    if (t && t === here) { a.classList.add('cur'); a.setAttribute('aria-current', 'page'); }
  });

  /* ── Plain-English titles på meny-länkarna (2026-09-24) ──
     In-world-namnen (The Crossroads, The Forge, Paths…) är stämningsbärare,
     men nya spelare behöver en sekund av klartext: samma mönster som
     marketing-navens title-attribut. En enda tabell här täcker alla 19 sidor
     (+ book-souls) — inga per-sida-attribut att hålla synkade. */
  var RAIL_TITLES = {
    'chat.html':      'Your game table — the conversation with the DM',
    'adventure.html': 'Adventure select — continue or start',
    'newgame.html':   'Create a new adventurer and campaign',
    'characters.html':'The Forge — manage saved characters',
    'character.html': 'Your character sheet',
    'npcs.html':      'Cast of NPCs met in your adventures',
    'platser.html':   'The world map — places visited',
    'loggbok.html':   'The journal — your story so far',
    'facts.html':     'Extracted facts ledger',
    'help.html':      'How to play — commands and tips',
    'mechanics.html': 'The game rules and mechanics',
    'models.html':    'The AI minds — model comparison',
    'pricing.html':   'Paths — free tier and Patron',
    'releases.html':  'Release notes — what changed',
    'screenshots.html':'Screens from the game',
    'admin.html':     'Admin — Overseer tools',
    'login.html':     'Log out of your account'
  };
  Array.prototype.forEach.call(drop.querySelectorAll('a[href]'), function (a) {
    var t = (a.getAttribute('href') || '').split('#')[0].split('?')[0].split('/').pop().toLowerCase();
    if (RAIL_TITLES[t] && !a.getAttribute('title')) a.setAttribute('title', RAIL_TITLES[t]);
  });

  /* ── Auth-länk: inloggad → Log out, annars → Enter the Table ── */
  // Bas-derivning: nested pages (t.ex. /book-souls/) måste lösa login.html
  // mot rail.js egen URL, inte sidans katalog (annars blir länken /book-souls/login.html).
  var auth = document.getElementById('rr-auth');
  var loginHref = 'login.html';
  try {
    var scriptEl = document.currentScript;
    if (scriptEl && scriptEl.src) loginHref = new URL('login.html', scriptEl.src).pathname;
  } catch (e) {}
  if (auth) {
    var logged = false;
    try { logged = !!sessionStorage.getItem('dnd_user'); } catch (e) {}
    if (logged) {
      auth.textContent = '🔒 Log out';
      auth.setAttribute('href', loginHref);
      auth.addEventListener('click', function (e) {
        e.preventDefault();
        setOpen(false);
        if (typeof window.doLogout === 'function') { window.doLogout(); }
        else { try { sessionStorage.removeItem('dnd_user'); } catch (err) {} location.href = loginHref; }
      });
    } else {
      auth.textContent = '⚔ Enter the Table';
      auth.setAttribute('href', loginHref + '#gate');
    }
  }

  /* ── Admin-länk: auto-detect + explicit hook ── */
  var adm = document.getElementById('rr-admin');
  function showAdmin(v) { if (adm) adm.hidden = !v; }
  window.railSetAdmin = showAdmin;
  try {
    var u = JSON.parse(sessionStorage.getItem('dnd_user') || 'null');
    if (u && (u.role === 'admin' || u.is_admin || u.admin)) showAdmin(true);
  } catch (e) {}

  /* ── Service worker (PWA/installbarhet + asset-cache) ──
     Registreras på root-scope från varje sida (även nested book-souls/).
     sw.js cachar ALDRIG navigation eller /api/ — se filens regler. */
  if ('serviceWorker' in navigator &&
      (location.protocol === 'https:' || location.hostname === 'localhost')) {
    window.addEventListener('load', function () {
      navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(function () {});
    });
  }
})();
