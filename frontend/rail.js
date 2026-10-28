/* ═══════════ RAIL v2 — unified header behavior (2026-09-23) ═══════════
   Menu open/close (click + keyboard + outside + Esc), focus trap + menu
   header with 44×44 close (2026-10-27), current-page marking,
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

  /* ── Service worker (PWA/installbarhet + asset-cache) ──
     Registreras på root-scope från varje sida (även nested book-souls/).
     sw.js cachar ALDRIG navigation eller /api/ — se filens regler.
     Ligger FÖRE meny-guarden (2026-10-05): sidor utan ☰-meny (login.html:s
     slimma header) ska ändå få skip-link + SW. */
  if ('serviceWorker' in navigator &&
      (location.protocol === 'https:' || location.hostname === 'localhost')) {
    window.addEventListener('load', function () {
      navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(function () {});
    });
  }

  var menu = document.querySelector('.rite-rail .rr-menu');
  var drop = document.getElementById('rr-drop');
  if (!menu || !drop) return;
  var btn = document.getElementById('rr-menu-btn');

  /* ── Fokusbara poster i menyn. ✕ (menyhuvudet) räknas med i fällan men
     hoppas över när vi sätter startfokus — första posten är det man vill nå. ── */
  function visible(el) { return !el.hidden && el.offsetParent !== null; }
  function focusables(withClose) {
    var list = Array.prototype.filter.call(
      drop.querySelectorAll('a[href], button:not([disabled])'), visible);
    if (!withClose) list = list.filter(function (el) { return !el.classList.contains('rr-dclose'); });
    return list;
  }

  /* ── Meny-huvud (2026-10-27): rubrik + 44×44 ✕. Injiceras här — markupen
     ligger i 20+ sidor, en källa räcker (rail.css äger utseendet). ── */
  (function () {
    if (drop.querySelector('.rr-dhead')) return;
    var head = document.createElement('div');
    head.className = 'rr-dhead';
    var lab = document.createElement('span');
    lab.className = 'rr-dhead-t';
    lab.setAttribute('aria-hidden', 'true');
    lab.textContent = 'Menu';
    var dclose = document.createElement('button');
    dclose.type = 'button';
    dclose.className = 'rr-dclose';
    dclose.setAttribute('aria-label', 'Close menu');
    dclose.setAttribute('title', 'Close menu');
    head.appendChild(lab);
    head.appendChild(dclose);
    drop.insertBefore(head, drop.firstChild);
    dclose.addEventListener('click', function (e) {
      e.stopPropagation();
      setOpen(false);
      if (btn) btn.focus();
    });
  })();

  function setOpen(open, opts) {
    var was = drop.classList.contains('open');
    drop.classList.toggle('open', open);
    if (btn) {
      btn.setAttribute('aria-expanded', open ? 'true' : 'false');
      /* ☰-ikonen byts till ✕ i CSS på [aria-expanded="true"] — labeln följer. */
      btn.setAttribute('aria-label', open ? 'Close menu' : 'Menu');
      btn.setAttribute('title', open ? 'Close menu' : 'Menu');
    }
    if (open && !was && !(opts && opts.noFocus)) {
      var f = focusables(false);
      if (f.length) f[0].focus();
    }
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

  /* ── Fokusfälla (2026-10-27): Tab/Shift+Tab cirkulerar inne i menyn medan
     den är öppen. Tidigare lämnade både Tab (framåt från sista posten) och
     Shift+Tab (bakåt från första) menyn medan den stod kvar öppen, så fokus
     hamnade bakom en synlig meny. ☰ räknas som widgetens startpunkt.
     Lyssnaren sitter i capture så vi hinner före webbläsarens egen flytt. ── */
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Tab' || e.altKey || e.ctrlKey || e.metaKey) return;
    if (!drop.classList.contains('open')) return;
    var f = focusables(true);
    if (!f.length) return;
    var first = f[0], last = f[f.length - 1], a = document.activeElement;
    if (e.shiftKey) {
      if (a === first || a === btn) { e.preventDefault(); last.focus(); }
    } else if (a === last) {
      e.preventDefault(); first.focus();
    }
  }, true);

  /* ── Markera aktuell sida ──
     Sidor som inte har en egen post i menyn (reset.html nås från login-gaten)
     markeras via föräldraposten, annars var reset.html den enda sidan utan
     lägesmarkering. aria-current="true" (inte "page") eftersom det inte är
     samma sida — men samma plats i flödet. ── */
  var here = (location.pathname.split('/').pop() || 'index.html').toLowerCase();
  var CUR_ALIAS = { 'reset.html': 'login.html' };
  Array.prototype.forEach.call(drop.querySelectorAll('a[href]'), function (a) {
    var t = (a.getAttribute('href') || '').split('#')[0].split('?')[0].split('/').pop().toLowerCase();
    if (!t) return;
    if (t === here) { a.classList.add('cur'); a.setAttribute('aria-current', 'page'); }
    else if (CUR_ALIAS[here] === t) { a.classList.add('cur'); a.setAttribute('aria-current', 'true'); }
  });

  /* ── Plain-English titles på meny-länkarna (2026-09-24) ──
     In-world-namnen (The Cauldron, Cooked Souls, Paths…) är stämningsbärare,
     men nya spelare behöver en sekund av klartext: samma mönster som
     marketing-navens title-attribut. En enda tabell här täcker alla 19 sidor
     (+ book-souls) — inga per-sida-attribut att hålla synkade. */
  var RAIL_TITLES = {
    'chat.html':      'Your game table — the conversation with the DM',
    'adventure.html': 'Adventure select — continue or start',
    'newgame.html':   'Create a new adventurer and campaign',
    'characters.html':'Cooked Souls — manage saved characters',
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
    'login.html':     'Log out of your account',
    'reset.html':     'Set a new password — re-forge your account'
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
      // RAIL_TITLES satte 'Log out of your account' före denna gren (bugg
      // 2026-10-05, tooltip-audit): utloggad ska title matcha länktexten.
      auth.setAttribute('title', 'Enter the Realm — log in or forge your name');
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
})();
