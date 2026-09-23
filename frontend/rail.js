/* ═══════════ RAIL v2 — unified header behavior (2026-09-23) ═══════════
   Menu open/close (click + keyboard + outside + Esc), current-page marking,
   auth-aware #rr-auth link, admin-link auto-detect + window.railSetAdmin(bool).
   Se docs/rail-v2-spec-2026-09-23.md. */
(function () {
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
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') setOpen(false); });

  /* ── Markera aktuell sida ── */
  var here = (location.pathname.split('/').pop() || 'index.html').toLowerCase();
  Array.prototype.forEach.call(drop.querySelectorAll('a[href]'), function (a) {
    var t = (a.getAttribute('href') || '').split('#')[0].split('?')[0].split('/').pop().toLowerCase();
    if (t && t === here) a.classList.add('cur');
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
})();
