/**
 * 🎨 themes.js — Color theme switcher for the whole site
 * ------------------------------------------------------
 * 5 dark-fantasy palettes, site-wide, saved in localStorage.
 * Overrides the CSS variables on <html> (inline style beats every
 * stylesheet, including snes.css's :root). Same pattern as fonts.js.
 *
 * Semantic accent mapping is preserved in EVERY theme:
 *   gold = sacred/UI · blood = HP/danger · arcane = magic/player
 *   ember = warmth/quests · poison = success/equipped
 *
 * v30: Server-persistence — theme (+ font) is also stored on the user
 * account (PUT /api/me/appearance) so it survives across devices and
 * origins (LAN IP vs dnd.rostad.cc vs mobile). On load, if localStorage
 * has no saved choice, the server value hydrates it.
 *
 * v31: Swatch popover — the theme button now opens a small palette menu
 * (5 swatches) instead of cycling on every click. Empty-button click
 * still cycles (accessibility). The injection logic (.theme-btn) stays.
 */
const THEMES = (() => {
  // id, name (shown on the button), palette (CSS variables)
  const PALETTES = [
    {
      id: 'terminal', name: 'Terminal',
      colors: {
        '--ink': '#0b0812', '--stone': '#161020', '--stone-2': '#1d1529', '--stone-3': '#241a33',
        '--edge': '#463a60', '--edge-hi': '#5a4a7a',
        '--bone': '#d9c9a6', '--bone-bright': '#f2e6c8', '--bone-dim': '#9d8a6a',
        '--gold': '#d4a92c', '--gold-bright': '#f0d675',
        '--blood': '#a32433', '--blood-bright': '#e0485a',
        '--ember': '#d4691e', '--arcane': '#9a6fe0', '--arcane-bright': '#c9a6ff', '--arcane-deep': '#3a1f66',
        '--poison': '#7aa35e', '--teal': '#5e9aa3',
        '--term-green': '#33cc33', '--term-amber': '#ccaa33',
      },
    },
    {
      id: 'blood', name: 'Blood',
      colors: {
        '--ink': '#0d0508', '--stone': '#190a10', '--stone-2': '#22101a', '--stone-3': '#2c1622',
        '--edge': '#5a2330', '--edge-hi': '#7a3345',
        '--bone': '#e0c0a8', '--bone-bright': '#f8e0cc', '--bone-dim': '#a07860',
        '--gold': '#d4552f', '--gold-bright': '#f0875a',
        '--blood': '#8f1426', '--blood-bright': '#e0455e',
        '--ember': '#e06a1e', '--arcane': '#c05aa0', '--arcane-bright': '#e8a6d0', '--arcane-deep': '#4a1f40',
        '--poison': '#7aa35e', '--teal': '#5e9aa3',
        '--term-green': '#3fbf4f', '--term-amber': '#dda33a',
      },
    },
    {
      id: 'arcane', name: 'Arcane',
      colors: {
        '--ink': '#070512', '--stone': '#110c24', '--stone-2': '#171034', '--stone-3': '#1e1542',
        '--edge': '#3d2f6e', '--edge-hi': '#54409a',
        '--bone': '#c8c8e8', '--bone-bright': '#e8e6ff', '--bone-dim': '#8a86b8',
        '--gold': '#c9a227', '--gold-bright': '#e8c65a',
        '--blood': '#a32433', '--blood-bright': '#e0485a',
        '--ember': '#d4691e', '--arcane': '#b07df5', '--arcane-bright': '#d4b8ff', '--arcane-deep': '#3a1f66',
        '--poison': '#7aa35e', '--teal': '#5ec8d4',
        '--term-green': '#33cc33', '--term-amber': '#ccaa33',
      },
    },
    {
      id: 'ember', name: 'Ember',
      colors: {
        '--ink': '#0b0705', '--stone': '#17100a', '--stone-2': '#1f1610', '--stone-3': '#281d14',
        '--edge': '#5a4433', '--edge-hi': '#7a5c44',
        '--bone': '#d9c9a6', '--bone-bright': '#f2e6c8', '--bone-dim': '#9d8a6a',
        '--gold': '#d4a92c', '--gold-bright': '#f0d675',
        '--blood': '#a32433', '--blood-bright': '#e0485a',
        '--ember': '#e07a2a', '--arcane': '#9a6fe0', '--arcane-bright': '#c9a6ff', '--arcane-deep': '#3a1f66',
        '--poison': '#7aa35e', '--teal': '#5e9aa3',
        '--term-green': '#33cc33', '--term-amber': '#ccaa33',
      },
    },
    {
      id: 'iron', name: 'Iron',
      colors: {
        '--ink': '#070a0e', '--stone': '#0e141c', '--stone-2': '#141c28', '--stone-3': '#1a2434',
        '--edge': '#33465e', '--edge-hi': '#47607e',
        '--bone': '#b8c8d8', '--bone-bright': '#dce8f4', '--bone-dim': '#6f8098',
        '--gold': '#c9a227', '--gold-bright': '#e8c65a',
        '--blood': '#a32433', '--blood-bright': '#e0485a',
        '--ember': '#d4691e', '--arcane': '#7ea8f0', '--arcane-bright': '#b8d4ff', '--arcane-deep': '#1f3a66',
        '--poison': '#7aa35e', '--teal': '#5ec8d4',
        '--term-green': '#33cc33', '--term-amber': '#ccaa33',
      },
    },
  ];

  const KEY = 'dnd_theme';

  function current() {
    const id = localStorage.getItem(KEY) || 'terminal';
    return PALETTES.find(p => p.id === id) || PALETTES[0];
  }

  function apply(palette) {
    const root = document.documentElement;
    const all = new Set();
    PALETTES.forEach(p => Object.keys(p.colors).forEach(v => all.add(v)));
    // Rensa tidigare tema-värden (så :root-fallbacken gäller om något saknas)
    all.forEach(v => root.style.removeProperty(v));
    Object.entries(palette.colors).forEach(([v, val]) => root.style.setProperty(v, val));
    root.setAttribute('data-theme', palette.id);
    // Uppdatera knappetiketter om de finns
    document.querySelectorAll('.theme-btn').forEach(b => {
      b.textContent = '🎨 ' + palette.name;
      b.title = 'Theme: ' + palette.name + ' (click to switch)';
    });
  }

  function cycle() {
    const cur = current();
    const idx = PALETTES.findIndex(p => p.id === cur.id);
    const next = PALETTES[(idx + 1) % PALETTES.length];
    localStorage.setItem(KEY, next.id);
    apply(next);
    syncToServer();
    return next;
  }

  // ── Server-persistens (v30) ──
  // Spara tema + typsnitt på kontot så valet följer med mellan enheter/origins.
  function syncToServer() {
    try {
      const body = { theme: current().id };
      if (typeof FONTS !== 'undefined') body.font = FONTS.current().id;
      fetch('/api/me/appearance', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }).catch(() => {});
    } catch (_) { /* inte inloggad / offline — localStorage gäller */ }
  }

  // Hydrata: om localStorage saknar tema (ny enhet/webbläsare) — hämta kontots
  // sparade tema + typsnitt från servern och applicera. Körs async i init.
  async function hydrateFromServer() {
    const hadLocalTheme = !!localStorage.getItem(KEY);
    const hadLocalFont = !!localStorage.getItem('dnd_font');
    if (hadLocalTheme && hadLocalFont) return; // lokalt val vinner
    try {
      const res = await fetch('/api/me');
      if (!res.ok) return;
      const me = await res.json();
      if (!hadLocalTheme && me.theme) {
        const p = PALETTES.find(x => x.id === me.theme);
        if (p) { localStorage.setItem(KEY, p.id); apply(p); }
      }
      if (!hadLocalFont && me.font && typeof FONTS !== 'undefined') {
        const f = FONTS.THEMES.find(x => x.id === me.font);
        if (f) { localStorage.setItem('dnd_font', f.id); FONTS.apply(f); }
      }
    } catch (_) { /* ej inloggad — hoppa över */ }
  }

  // ── v31: Swatch popover ──
  // Build & show a small palette menu anchored to the clicked button.
  let _pop = null;
  function _swatchVars(p) {
    return [p.colors['--gold'], p.colors['--arcane'], p.colors['--blood'], p.colors['--teal']];
  }
  function _closePop() {
    if (_pop) { _pop.remove(); _pop = null; }
    document.removeEventListener('click', _outside);
  }
  function _outside(e) {
    if (_pop && !_pop.contains(e.target) && !(e.target.closest && e.target.closest('.theme-btn'))) _closePop();
  }
  function openPopover(anchor) {
    _closePop();
    const pop = document.createElement('div');
    pop.className = 'theme-pop';
    const frag = document.createElement('div');
    PALETTES.forEach(p => {
      const row = document.createElement('button');
      row.type = 'button';
      row.className = 'theme-row' + (p.id === current().id ? ' active' : '');
      row.setAttribute('data-id', p.id);
      const sw = document.createElement('span');
      sw.className = 'theme-swatches';
      _swatchVars(p).forEach(c => {
        const d = document.createElement('i');
        d.style.background = c;
        sw.appendChild(d);
      });
      const nm = document.createElement('span');
      nm.className = 'theme-name';
      nm.textContent = p.name;
      row.appendChild(sw);
      row.appendChild(nm);
      row.onclick = (e) => {
        e.stopPropagation();
        localStorage.setItem(KEY, p.id);
        apply(p);
        syncToServer();
        _closePop();
        if (typeof SFX !== 'undefined') SFX.click();
      };
      frag.appendChild(row);
    });
    pop.appendChild(frag);
    document.body.appendChild(pop);
    // Positiona precis under/över knappen
    const r = anchor.getBoundingClientRect();
    const pRect = pop.offsetHeight;
    let top = r.bottom + 8;
    if (top + pRect > window.innerHeight - 8) top = r.top - pRect - 8;
    pop.style.top = Math.max(8, top) + 'px';
    pop.style.left = Math.min(r.left, window.innerWidth - pop.offsetWidth - 8) + 'px';
    _pop = pop;
    setTimeout(() => document.addEventListener('click', _outside), 0);
  }

  // Init — applicera direkt så tema sitter vid första paint
  apply(current());

  return { PALETTES, current, cycle, apply, hydrateFromServer, syncToServer, openPopover };
})();

// ── Global theme button (topbar, bredvid font-knappen) ──
function themeToggleBtn() {
  const btn = document.querySelector('.theme-btn');
  if (btn) {
    THEMES.openPopover(btn);
    return;
  }
  // Fallback (ingen knapp i DOM): cykla
  const next = THEMES.cycle();
  if (typeof toast === 'function') toast('🎨 Theme: ' + next.name);
  if (typeof SFX !== 'undefined') SFX.click();
}

// Rapid cycle (used by compact mobile menu items — no popover, just switch).
function themeCycle() {
  const next = THEMES.cycle();
  if (typeof toast === 'function') toast('🎨 Theme: ' + next.name);
  if (typeof SFX !== 'undefined') SFX.click();
}

document.addEventListener('DOMContentLoaded', () => {
  const cur = THEMES.current();

  // Uppdatera befintliga theme-buttons
  document.querySelectorAll('.theme-btn').forEach(b => {
    b.textContent = '🎨 ' + cur.name;
    b.title = 'Theme: ' + cur.name + ' (click to switch)';
  });

  // Injicera en theme-knapp i topbaren om ingen finns
  const bar = document.querySelector('.topbar') || document.querySelector('.forge-head') || document.querySelector('nav.nav');
  if (bar && !bar.querySelector('.theme-btn')) {
    const btn = document.createElement('button');
    btn.className = bar.classList.contains('nav') ? 'theme-btn nav-theme-btn' : 'top-btn theme-btn';
    btn.textContent = '🎨 ' + cur.name;
    btn.title = 'Theme: ' + cur.name + ' (click to switch)';
    btn.onclick = (e) => { e.stopPropagation(); THEMES.openPopover(btn); };

    // Login-sidans .nav — lägg knappen i nav-links före Enter-CTA:n
    const navLinks = bar.querySelector('.nav-links');
    if (navLinks) {
      const cta = navLinks.querySelector('.nav-cta');
      if (cta) navLinks.insertBefore(btn, cta); else navLinks.appendChild(btn);
    } else {
      // Före font-knappen (och settings-gearet) så ordningen blir: [font] [theme] ⚙️
      const fontBtn = bar.querySelector('.font-btn');
      if (fontBtn) {
        bar.insertBefore(btn, fontBtn);
      } else {
        const gear = Array.from(bar.querySelectorAll('.icon-btn')).find(b => b.onclick && /toggleSettingsMenu/.test(String(b.onclick)));
        if (gear) {
          bar.insertBefore(btn, gear.parentElement || gear);
        } else {
          const last = bar.lastElementChild;
          if (last && (last.classList.contains('danger') || /lämna|leave|exit/i.test(last.textContent))) {
            bar.insertBefore(btn, last);
          } else {
            bar.appendChild(btn);
          }
        }
      }
    }
  }

  // Hämta kontots sparade tema om localStorage är tomt (ny enhet)
  THEMES.hydrateFromServer();
});