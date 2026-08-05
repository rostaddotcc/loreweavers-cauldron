/**
 * 🔤 fonts.js — Font switcher for the whole site
 * ------------------------------------------------
 * 5 fonts to cycle through, site-wide, saved in localStorage.
 * Sets a class on <html> + CSS variables that snes.css reads.
 */
const FONTS = (() => {
  // Each theme: id, display name, display font (headings), body font (body text)
  const THEMES = [
    { id: 'pixel',    name: 'Pixel',        display: "'Press Start 2P', monospace", body: "'Silkscreen', monospace" },
    { id: 'terminal', name: 'Terminal',     display: "'VT323', monospace",          body: "'VT323', monospace" },
    { id: 'gothic',   name: 'Gothic',       display: "'Cinzel', serif",             body: "'Spectral', Georgia, serif" },
    { id: 'mono',     name: 'Mono',         display: "'IBM Plex Mono', monospace",  body: "'IBM Plex Mono', monospace" },
    { id: 'dot',      name: 'Dot',          display: "'DotGothic16', sans-serif",   body: "'DotGothic16', sans-serif" },
    { id: 'rune',     name: 'Rune',         display: "'Uncial Antiqua', serif",     body: "'IM Fell English', Georgia, serif" },
    { id: 'scribe',   name: 'Scribe',       display: "'MedievalSharp', cursive",    body: "'Alegreya', Georgia, serif" },
  ];

  const KEY = 'dnd_font';

  // Säkert localStorage — samma guard som themes.js (2026-08-05)
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (_) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (_) {} },
  };

  // Vad som FAKTISKT är applicerat (font-<id>-klassen på <html>)
  function applied() {
    const cls = document.documentElement.className;
    for (const t of THEMES) {
      if (cls.includes('font-' + t.id)) return t;
    }
    return current();
  }

  function current() {
    const id = store.get(KEY) || 'pixel';
    return THEMES.find(t => t.id === id) || THEMES[0];
  }

  function apply(theme) {
    const root = document.documentElement;
    // Remove all theme classes, add the selected one
    THEMES.forEach(t => root.classList.remove('font-' + t.id));
    root.classList.add('font-' + theme.id);
    root.style.setProperty('--font-display', theme.display);
    root.style.setProperty('--font-body', theme.body);
    // Kugghjulets Font-rad: uppdatera hint med aktuellt typsnitt (2026-08-05)
    const fontHint = document.getElementById('settings-font-hint');
    if (fontHint && !/—|–/.test(fontHint.textContent)) fontHint.textContent = 'typeface — ' + theme.name;
  }

  function cycle() {
    const cur = current();
    const idx = THEMES.findIndex(t => t.id === cur.id);
    const next = THEMES[(idx + 1) % THEMES.length];
    apply(next);            // applicera först — bytet måste ALLTID synas
    store.set(KEY, next.id);
    return next;
  }

  // Init
  apply(current());

  return { THEMES, current, applied, cycle, apply };
})();

// ── Global font button (in the topbar, next to music/mute) ──
function fontToggleBtn() {
  const next = FONTS.cycle();
  const btns = document.querySelectorAll('.font-btn');
  btns.forEach(b => { b.textContent = next.name; b.title = 'Font: ' + next.name + ' (click to switch)'; });
  // Uppdatera ev. drop-item-etikett i settings-menyn (🔤 Font)
  document.querySelectorAll('.drop-item .di-name').forEach(n => {
    if (/font/i.test(n.textContent)) {
      const hint = n.parentElement.querySelector('.di-hint');
      if (hint) hint.textContent = 'typeface — ' + next.name;
    }
  });
  // Persista tema+typsnitt till kontot (themes.js äger server-syncen)
  if (typeof THEMES !== 'undefined' && THEMES.syncToServer) THEMES.syncToServer();
  if (typeof toast === 'function') toast('🔤 Font: ' + next.name);
  if (typeof SFX !== 'undefined') SFX.click();
}

// Auto-inject the font button into the topbar on all pages (next to music/mute)
document.addEventListener('DOMContentLoaded', () => {
  const cur = FONTS.current();

  // Update existing font buttons (if any page has a hardcoded one)
  document.querySelectorAll('.font-btn').forEach(b => {
    b.textContent = cur.name;
    b.title = 'Font: ' + cur.name + ' (click to switch)';
  });

  // Sidor med kugghjul (settings-menu / gear-menu) har typsnittet i menyn
  // istället — ingen topbar-knapp injiceras då. (2026-08-04)
  if (document.querySelector('.settings-menu') || document.querySelector('.gear-menu')) return;

  // Find the topbar and inject a font button if one doesn't already exist
  const bar = document.querySelector('.topbar') || document.querySelector('.forge-head');
  if (bar && !bar.querySelector('.font-btn')) {
    const btn = document.createElement('button');
    btn.className = 'top-btn font-btn';
    btn.textContent = cur.name;
    btn.title = 'Font: ' + cur.name + ' (click to switch)';
    btn.onclick = fontToggleBtn;
    // Insert before the settings gear (⚙️) so the gear stays rightmost, next to font
    const gear = Array.from(bar.querySelectorAll('.icon-btn')).find(b => b.onclick && /toggleSettingsMenu/.test(String(b.onclick)));
    if (gear) {
      bar.insertBefore(btn, gear.parentElement || gear);
    } else {
      // Fallback: before the last element (usually the Leave/exit button), otherwise last
      const last = bar.lastElementChild;
      if (last && (last.classList.contains('danger') || /lämna|leave|exit/i.test(last.textContent))) {
        bar.insertBefore(btn, last);
      } else {
        bar.appendChild(btn);
      }
    }
  }
});
