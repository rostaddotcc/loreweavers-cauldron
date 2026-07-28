/**
 * 🔤 fonts.js — Typsnittsväxlare för hela sajten
 * ------------------------------------------------
 * 5 typsnitt att cykla igenom, site-wide, sparas i localStorage.
 * Sätter en klass på <html> + CSS-variabler som snes.css läser.
 */
const FONTS = (() => {
  // Varje tema: id, visningsnamn, display-font (rubriker), body-font (brödtext)
  const THEMES = [
    { id: 'pixel',    name: 'Pixel',        display: "'Press Start 2P', monospace", body: "'Silkscreen', monospace" },
    { id: 'terminal', name: 'Terminal',     display: "'VT323', monospace",          body: "'VT323', monospace" },
    { id: 'gothic',   name: 'Gothic',       display: "'Cinzel', serif",             body: "'Spectral', Georgia, serif" },
    { id: 'mono',     name: 'Mono',         display: "'IBM Plex Mono', monospace",  body: "'IBM Plex Mono', monospace" },
    { id: 'dot',      name: 'Dot',          display: "'DotGothic16', sans-serif",   body: "'DotGothic16', sans-serif" },
  ];

  const KEY = 'dnd_font';

  function current() {
    const id = localStorage.getItem(KEY) || 'pixel';
    return THEMES.find(t => t.id === id) || THEMES[0];
  }

  function apply(theme) {
    const root = document.documentElement;
    // Ta bort alla tema-klasser, lägg till den valda
    THEMES.forEach(t => root.classList.remove('font-' + t.id));
    root.classList.add('font-' + theme.id);
    root.style.setProperty('--font-display', theme.display);
    root.style.setProperty('--font-body', theme.body);
  }

  function cycle() {
    const cur = current();
    const idx = THEMES.findIndex(t => t.id === cur.id);
    const next = THEMES[(idx + 1) % THEMES.length];
    localStorage.setItem(KEY, next.id);
    apply(next);
    return next;
  }

  // Init
  apply(current());

  return { THEMES, current, cycle, apply };
})();

// ── Global font-knapp (i topbaren, bredvid musik/mute) ──
function fontToggleBtn() {
  const next = FONTS.cycle();
  const btns = document.querySelectorAll('.font-btn');
  btns.forEach(b => { b.textContent = next.name; b.title = 'Typsnitt: ' + next.name + ' (klicka för att byta)'; });
  if (typeof toast === 'function') toast('🔤 Typsnitt: ' + next.name);
  if (typeof SFX !== 'undefined') SFX.click();
}

// Auto-injicera font-knappen i topbaren på alla sidor (bredvid musik/mute)
document.addEventListener('DOMContentLoaded', () => {
  const cur = FONTS.current();

  // Uppdatera befintliga font-knappar (om någon sida har en hårdkodad)
  document.querySelectorAll('.font-btn').forEach(b => {
    b.textContent = cur.name;
    b.title = 'Typsnitt: ' + cur.name + ' (klicka för att byta)';
  });

  // Hitta topbaren och injicera en font-knapp om det inte redan finns en
  const bar = document.querySelector('.topbar') || document.querySelector('.forge-head');
  if (bar && !bar.querySelector('.font-btn')) {
    const btn = document.createElement('button');
    btn.className = 'top-btn font-btn';
    btn.textContent = cur.name;
    btn.title = 'Typsnitt: ' + cur.name + ' (klicka för att byta)';
    btn.onclick = fontToggleBtn;
    // Sätt in före sista elementet (oftast Lämna/exit-knappen) om det finns, annars sist
    const last = bar.lastElementChild;
    if (last && (last.classList.contains('danger') || /lämna|exit/i.test(last.textContent))) {
      bar.insertBefore(btn, last);
    } else {
      bar.appendChild(btn);
    }
  }
});
