/** 
 * 🔤 fonts.js — FIXED typography hierarchy (font switcher removed 2026-08)
 * ------------------------------------------------------------------------
 * The site now uses ONE fixed 4-role typeface system defined in snes.css :root:
 *   --font-display  → headings, section labels, buttons        ('Cinzel')
 *   --font-body     → narration, body text, chat messages      ('Spectral')
 *   --font-mono     → numbers, system lines, technical chrome  ('IBM Plex Mono')
 *   --font-accent   → chips, tabs, DOS-style micro labels      ('Silkscreen')
 *   --cli-mono      → CLI chat mode mono stack
 *
 * This module only (a) guarantees the vars exist at runtime as belt-and-
 * suspenders (CSS :root is the source of truth), and (b) keeps legacy
 * no-op entry points (fontToggleBtn) so old inline handlers never throw.
 * Saved 'dnd_font' localStorage values are deliberately IGNORED.
 */
const FONTS = (() => {
  // Fixed hierarchy — must mirror snes.css :root exactly.
  const VARS = {
    '--font-display': "'Cinzel', serif",
    '--font-body': "'Spectral', Georgia, serif",
    '--font-mono': "'IBM Plex Mono', ui-monospace, monospace",
    '--font-accent': "'Silkscreen', monospace",
    '--cli-mono': "ui-monospace, 'Cascadia Code', 'JetBrains Mono', Menlo, Consolas, monospace",
  };

  // Legacy API — kept as harmless no-ops so nothing that still calls these
  // (themes.js, old inline handlers) breaks. The typeface is FIXED now.
  const fixed = { id: 'fixed', name: 'Fixed' };
  function apply() { /* no-op — hierarkin är fixerad i CSS */ }
  function cycle() { return fixed; }
  function current() { return fixed; }
  function applied() { return fixed; }

  // Belt & suspenders: se till att hierarki-var:na finns vid runtime.
  document.addEventListener('DOMContentLoaded', () => {
    try {
      const root = document.documentElement;
      Object.entries(VARS).forEach(([v, val]) => {
        if (!root.style.getPropertyValue(v)) root.style.setProperty(v, val);
      });
    } catch (_) { /* CSS :root räcker */ }
  });

  return { THEMES: [], current, applied, cycle, apply };
})();

// ── Legacy no-op: gamla sidor (t.ex. adventure.html) har fortfarande en
// 🔤 Font-knapp som anropar fontToggleBtn(). Switchern är borttagen — knappen
// bekräftar bara den fixerade typografin. (2026-08)
function fontToggleBtn() {
  // Kugghjulets Font-rad (chat.html) — null-safe om raden tagits bort.
  const fontHint = document.getElementById('settings-font-hint');
  if (fontHint) fontHint.textContent = 'typeface — fixed';
  document.querySelectorAll('.drop-item .di-name').forEach(n => {
    if (/font/i.test(n.textContent)) {
      const hint = n.parentElement.querySelector('.di-hint');
      if (hint) hint.textContent = 'typeface — fixed';
    }
  });
  if (typeof toast === 'function') toast('🔤 Typeface: fixed Cinzel/Spectral');
}
