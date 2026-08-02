// Verifiering: renderar fiendeattacker med tärningar genom de RIKTIGA funktionerna.
// Bevisar att `(🎲 d20=14+3=17 · 1d6+2: [4]=6)` blir synlig HTML i stridsloggen.
const fs = require('fs');
const path = require('path');
const html = fs.readFileSync(path.join(__dirname, '..', 'frontend', 'chat.html'), 'utf8');

// ── Mini-DOM (samma mönster som test-combat-split-dom.js) ──
class El {
  constructor(tag) { this.tagName = tag; this.children = []; this._cls = new Set(); this._text = ''; this.innerHTML = ''; this.style = {}; this.scrollTop = 0; this.scrollHeight = 100; this.hidden = false; }
  get classList() { const s = this; return { add: (...c) => c.forEach(x => s._cls.add(x)), remove: (...c) => c.forEach(x => s._cls.delete(x)), contains: c => s._cls.has(c), toggle: (c, f) => { const on = typeof f === 'boolean' ? f : !s._cls.has(c); if (on) s._cls.add(c); else s._cls.delete(c); return on; } }; }
  setAttribute(k, v) { this._attrs = this._attrs || {}; this._attrs[k] = String(v); }
  set className(v) { this._cls = new Set(String(v).split(/\s+/).filter(Boolean)); }
  get className() { return [...this._cls].join(' '); }
  appendChild(c) { c.parentNode = this; this.children.push(c); return c; }
  addEventListener() {}
  querySelector() { return null; }
  querySelectorAll() { return []; }
}
const document = { createElement: t => new El(t), getElementById: () => null, querySelector: () => null, querySelectorAll: () => [], addEventListener() {}, body: new El('body') };
const window = { addEventListener() {} };
const console2 = { log: console.log, warn: () => {}, error: () => {} };
const I18N = { getLang: () => 'sv', t: s => s };
const SFX = { battle(){}, attack(){}, damage(){}, miss(){}, crit(){}, heal(){} };
const localStorage = { getItem: () => null, setItem: () => {} };
const sessionStorage = { getItem: () => null, setItem: () => {} };
const navigator = {};

// Ladda chat.html-koden i en sandlåda
const blocks = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
const vm = require('vm');
const ctx = vm.createContext({ document, window, console: console2, I18N, SFX, localStorage, sessionStorage, navigator, El, Math, JSON, Date, setTimeout, clearTimeout, setInterval, clearInterval, requestAnimationFrame: () => {}, String, Number, Boolean, Array, Object, RegExp, parseInt, parseFloat, isNaN, isFinite });
for (const b of blocks) { try { vm.runInContext(b, ctx); } catch (e) { /* vissa block kräver DOM som inte finns — ignorera */ } }

// Funktionerna vi vill testa
const combatLogHtml = vm.runInContext('combatLogHtml', ctx);
const combatLineClass = vm.runInContext('combatLineClass', ctx);

let pass = 0, fail = 0;
function check(name, cond, extra) {
  if (cond) { pass++; console.log('  ✅ ' + name); }
  else { fail++; console.log('  ❌ ' + name + (extra ? ' — ' + extra : '')); }
}

// ── Test 1: fiendeträff med tärningar renderas ──
const log1 = [
  'Goblin: träffar dig — 5 skada (🎲 d20=14+3=17 · 1d6+2: [4]=6)',
  'Goblin: missar dig (🎲 d20=6+3=9 mot AC 15)',
  'Orc: träffar dig — 12 skada (kritisk!) (🎲 d20=20+4=24 · 1d12+3: [12]=15)',
  'Mimmrick: träffar goblinen — 7 skada (🎲 d20=16+4=20 · 1d6+1: [6]=7)',
];
const html1 = combatLogHtml(log1.join('\n'), { round: 2 });
console.log('— Fiendeattacker (3) + ally (1), runda 2 —');
console.log(html1);
check('fiendeträff: 🎲 d20=14+3=17 synlig', html1.includes('🎲 d20=14+3=17'));
check('fiendemiss: 🎲 d20=6+3=9 synlig', html1.includes('🎲 d20=6+3=9'));
check('kritisk: 🎲 d20=20+4=24 synlig', html1.includes('🎲 d20=20+4=24'));
check('ally: 🎲 d20=16+4=20 synlig', html1.includes('🎲 d20=16+4=20'));
check('skade-tärning [4]=6 synlig', html1.includes('[4]=6'));
check('kritisk-rad får cl-dmg-klass (blodröd)', html1.includes('cl-dmg'));
check('fiendeträff får cl-dmg-klass', /cl-row cl-dmg/.test(html1));
check('alla fyra rader renderade', (html1.match(/cl-row/g) || []).length === 4);

// ── Test 2: klassificering per rad ──
const cHit = combatLineClass('Goblin: träffar dig — 5 skada (🎲 d20=14+3=17)');
check('träff → cl-dmg', cHit.cls === ' cl-dmg');
const cMiss = combatLineClass('Goblin: missar dig (🎲 d20=6+3=9 mot AC 15)');
check('miss → cl-enemy (bone)', cMiss.cls === ' cl-enemy');
const cCrit = combatLineClass('Orc: träffar dig — 12 skada (kritisk!) (🎲 d20=20+4=24)');
check('kritisk → cl-dmg', cCrit.cls === ' cl-dmg');

// ── Test 3: stridslogg-exempel från guardian.py (exakt format) ──
const log3 = [
  'Velbrand Askspott: kastar eldboll mot Auvrel',
  'Goblin: missar dig (nat 1!)',
  'Goblin: träffar dig — 8 skada (🎲 d20=15+3=18 · 1d8+2: [6]=8)',
];
const html3 = combatLogHtml(log3.join('\n'), { round: 3 });
check('nat 1 miss synlig', html3.includes('missar dig (nat 1!)'));
check('d20=15+3=18 synlig i runda 3', html3.includes('d20=15+3=18'));
check('runda 3 rubrik', html3.includes('RUNDA 3'));

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
