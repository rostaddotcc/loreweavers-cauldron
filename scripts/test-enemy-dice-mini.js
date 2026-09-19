// Verifiering: fiende-tärningsceremonin (enemyDiceMini) via vm-sandbox.
// Bevisar att en fiende-rulle MOT spelaren (röd badge) triggar en kompakt
// inline-d20-ceremoni som rullar och landar på det FAKTISKA d20-värdet,
// att ally-rullar INTE animeras, att dedupen blockerar re-leveranser av
// samma combat-state, och att CLI-läget hoppar över animationen.
// Kör: node scripts/test-enemy-dice-mini.js
const fs = require('fs');
const path = require('path');
const html = fs.readFileSync(path.join(__dirname, '..', 'frontend', 'chat.html'), 'utf8');
const vm = require('vm');

// ── Mini-DOM (rika nog för enemyDiceMini) ──
class El {
  constructor(tag) {
    this.tagName = tag; this.children = []; this.parentNode = null;
    this._cls = new Set(); this._text = ''; this.innerHTML = '';
    this.style = {}; this._attrs = {};
  }
  get classList() {
    const s = this;
    return {
      add: (...c) => c.forEach(x => s._cls.add(x)),
      remove: (...c) => c.forEach(x => s._cls.delete(x)),
      contains: c => s._cls.has(c),
      toggle: (c, f) => { const on = typeof f === 'boolean' ? f : !s._cls.has(c); if (on) s._cls.add(c); else s._cls.delete(c); return on; },
    };
  }
  set className(v) { this._cls = new Set(String(v).split(/\s+/).filter(Boolean)); }
  get className() { return [...this._cls].join(' '); }
  set textContent(v) { this._text = String(v); this.innerHTML = String(v); }
  get textContent() { return this._text; }
  appendChild(c) { c.parentNode = this; this.children.push(c); return c; }
  insertBefore(el, ref) {
    el.parentNode = this;
    const i = ref ? this.children.indexOf(ref) : -1;
    if (i >= 0) this.children.splice(i, 0, el); else this.children.push(el);
    return el;
  }
  removeChild(c) { const i = this.children.indexOf(c); if (i >= 0) this.children.splice(i, 1); c.parentNode = null; return c; }
  remove() { if (this.parentNode) this.parentNode.removeChild(this); }
  setAttribute(k, v) { this._attrs[k] = String(v); }
  getAttribute(k) { return this._attrs[k]; }
  get nextSibling() { const i = this.parentNode ? this.parentNode.children.indexOf(this) : -1; return (i >= 0) ? (this.parentNode.children[i + 1] || null) : null; }
  querySelector() { return null; }
  querySelectorAll() { return []; }
  addEventListener() {}
  getBoundingClientRect() { return { width: 0, left: 0, top: 0, height: 0 }; }
}

const body = new El('body');
const miniDoc = {
  createElement: t => {
    const el = new El(t);
    el._num = new El('text'); el._num.style = {};
    el._tension = new El('div'); el._tension.style = {};
    el._result = new El('div'); el._result.style = {};
    el.querySelector = sel => {
      if (sel === '.d20 .num') return el._num;
      if (sel === '.id-tension') return el._tension;
      if (sel === '.id-result') return el._result;
      return null;
    };
    el.getBoundingClientRect = () => ({ width: 90, left: 10, top: 10, height: 30 });
    return el;
  },
  getElementById: () => null,
  querySelector: () => null,
  querySelectorAll: () => [],
  body,
  addEventListener() {},
};

let sfxDice = 0, sfxCrit = 0, sfxFail = 0;
const SFX = { dice: () => sfxDice++, crit: () => sfxCrit++, fail: () => sfxFail++ };
const I18N = { getLang: () => 'sv', t: s => s };

const ctx = vm.createContext({
  document: miniDoc, window: { addEventListener() {} }, console,
  location: { href: '', reload() {}, search: '' },
  I18N, SFX, localStorage: { getItem: () => null, setItem: () => {} },
  sessionStorage: { getItem: () => null, setItem: () => {} }, navigator: {}, El,
  Math, JSON, Date, setTimeout, clearTimeout, setInterval, clearInterval,
  requestAnimationFrame: () => {},
  String, Number, Boolean, Array, Object, RegExp, parseInt, parseFloat, isNaN, isFinite,
});
// Block 1 kastar tidigt i sandlådan (top-level `API.me()` → `API is not defined`),
// så alla top-level let/const EFTER kastpunkten initieras aldrig — funktionerna
// finns (hoistade) men `_enemyDiceSeen` hamnar i TDZ. Samma kända pitfall som
// `_combatEndSeen`/`_lastCombatRound` (se enemy-dice-render-2026-08): deklarera
// set:et själva i kontexten och stryk filens egen deklaration ur laddningen.
let source = html.replace(/let _enemyDiceSeen = new Set\(\);.*\n/, '');
// Partiklarna (block 1, efter embers-canvasen) deklareras efter kastpunkten →
// TDZ på `_pxLive`/`_pxBurst` när _pxSpawn anropas. Samma pitfall-mönster:
// deklarera registret i kontexten och stryk filens egen deklaration.
source = source.replace(/const _pxLive = new Set\(\);.*\n/, '');
source = source.replace(/let _pxBurst = \[\];.*\n/, '');
source = source.replace(/let _pxRafId = null;.*\n/, '');
vm.runInContext('let _pxLive = new Set(); let _pxBurst = []; let _pxRafId = null;', ctx);
// Ladda BARA block 0 + 1: block 3 är app-boot-kod (loadCampaign().then(...) på
// toppnivå) som aldrig kan fungera i en sandlåda — dess asynkrona fortsättning
// kastar utanför try/catch (mikrotask-kön) och kraschar processen. Alla
// funktioner som testas ligger i block 1.
const allBlocks = [...source.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
const blocks = allBlocks.slice(0, 2);
vm.runInContext('let _enemyDiceSeen = new Set();', ctx);
for (const b of blocks) { try { vm.runInContext(b, ctx); } catch (e) { /* block som kräver riktig DOM — ignorera */ } }

const decorateCombatDice = vm.runInContext('decorateCombatDice', ctx);
const extractDiceFromText = vm.runInContext('extractDiceFromText', ctx);

let pass = 0, fail = 0;
function check(name, cond, extra) {
  if (cond) { pass++; console.log('  ✅ ' + name); }
  else { fail++; console.log('  ❌ ' + name + (extra ? ' — ' + extra : '')); }
}

function makeRow(cls, text) {
  const r = new El('div');
  r.className = 'cl-row ' + cls;
  r._text = text; r.innerHTML = text;
  r.getBoundingClientRect = () => ({ width: 300, left: 0, top: 0, height: 20 });
  r.querySelectorAll = () => [];
  return r;
}
function makeRoot(rows) {
  const root = new El('div');
  rows.forEach(r => root.appendChild(r));
  root.querySelectorAll = sel => [...root.children]; // statisk snapshot (som NodeList)
  return root;
}

// ═══ Synkron fas: triggning + dedup + CLI ═══
const enemyRow = makeRow('cl-dmg', 'Goblin: träffar dig — 6 skada (piercing) (🎲 d20=16+3=19 · 1d6+1: [5]=6)');
const allyRow = makeRow('cl-dmg', 'Mimmrick: träffar goblinen — 7 skada (🎲 d20=16+4=20 · 1d6+1: [6]=7)');
const root = makeRoot([enemyRow, allyRow]);
decorateCombatDice(root);
check('fiende-rad mot spelare → 1 mini-ceremoni infogad', root.children.length === 3, 'children=' + root.children.length);
const mini = root.children[1];
check('mini har klasser inline-dice enemy-dice-mini rolling',
  mini.className.includes('inline-dice') && mini.className.includes('enemy-dice-mini') && mini.className.includes('rolling'),
  mini.className);
check('mini-etikett = aktörsnamnet (Goblin)', mini.innerHTML.includes('Goblin'));
check('ally-rad → INGEN ceremoni (children = 3)', root.children.length === 3);
check('SFX.dice spelades', sfxDice === 1, 'calls=' + sfxDice);

// Re-leverans av SAMMA combat-state → dedupen blockerar
decorateCombatDice(root);
check('dedup: samma rad igen → ingen andra mini', root.children.length === 3, 'children=' + root.children.length);

// Två OLIKA fiende-rullar i samma logg → två ceremonier
// (nya roll-texter — samma text+radindex som tidigare faser skulle dedupas)
const rootA = makeRoot([
  makeRow('cl-dmg', 'Goblin: träffar dig — 4 skada (🎲 d20=9+3=12 · 1d6+1: [3]=4)'),
  makeRow('cl-dmg', 'Orc: träffar dig — 8 skada (🎲 d20=17+4=21 · 1d8+3: [5]=8)'),
]);
decorateCombatDice(rootA);
check('två olika fiende-rullar → två ceremonier', rootA.children.length === 4, 'children=' + rootA.children.length);

// CLI-läge → ingen animation (tärningen finns redan som text i loggraden)
body.classList.add('cli-chat');
const rootCli = makeRoot([makeRow('cl-dmg', 'Goblin: träffar dig — 6 skada (🎲 d20=16+3=19 · 1d6+1: [5]=6)')]);
decorateCombatDice(rootCli);
check('CLI-läge → ingen ceremoni', rootCli.children.length === 1, 'children=' + rootCli.children.length);
body.classList.remove('cli-chat');

// ═══ Asynkron fas: rull → avslöjande → borttagning ═══
// Fas 1: vanlig träff ensam (så vi kan bevisa att den INTE spelar crit/fail-ljud).
// (nya roll-texter — samma text+radindex som tidigare faser skulle dedupas)
const root16 = makeRoot([makeRow('cl-dmg', 'Goblin: träffar dig — 6 skada (🎲 d20=14+3=17 · 1d6+2: [4]=6)')]);
decorateCombatDice(root16);
const mini16 = root16.children[1];

// Rull ~1.3s + kort marginal → check avslöjandet av den vanliga träffen
setTimeout(() => {
  console.log('— Livscykel fas 1 (efter ~1.7s) —');
  check('vanlig träff: tärningen landar på d20=14', mini16._num._text === '14', mini16._num._text);
  check('vanlig träff: reveal utan crit/fail-klass',
    mini16.className.includes('reveal') && !mini16.className.includes('crit') && !mini16.className.includes('fail'),
    mini16.className);
  check('vanlig träff: resultatraden visar badge-texten', mini16._result._text === 'd20=14+3=17 · 1d6+2: [4]=6', mini16._result._text);
  check('vanlig träff: ingen SFX.crit/fail', sfxCrit === 0 && sfxFail === 0, 'crit=' + sfxCrit + ' fail=' + sfxFail);
  check('spänningstexten dold vid avslöjande', mini16._tension.style.display === 'none');

  // ── Fas 2: krit + fumble (körs efter fas 1:s kontroller) ──
  const rootCrit = makeRoot([makeRow('cl-dmg', 'Orc: träffar dig — 12 skada (kritisk!) (🎲 d20=20+4=24 · 1d12+3: [12]=15)')]);
  decorateCombatDice(rootCrit);
  const miniCrit = rootCrit.children[1];
  const rootFail = makeRoot([makeRow('cl-enemy', 'Goblin: missar dig (🎲 d20=1+3=4)')]);
  decorateCombatDice(rootFail);
  const miniFail = rootFail.children[1];

  setTimeout(() => {
    console.log('— Livscykel fas 2 (efter ~2.6s till) —');
    check('krit: landar på d20=20 + crit-klass', miniCrit._num._text === '20' && miniCrit.className.includes('crit'), miniCrit._num._text);
    check('krit: SFX.crit spelades', sfxCrit === 1, 'calls=' + sfxCrit);
    check('fumble: landar på d20=1 + fail-klass', miniFail._num._text === '1' && miniFail.className.includes('fail'), miniFail._num._text);
    check('fumble: SFX.fail spelades', sfxFail === 1, 'calls=' + sfxFail);
    check('ceremonin raderas efter avslöjandet (mini borta ur loggen)',
      !root16.children.includes(mini16) && !rootCrit.children.includes(miniCrit) && !rootFail.children.includes(miniFail));
    check('loggraden finns kvar (badge-chippet är den permanenta posten)',
      root16.children.length === 1 && rootCrit.children.length === 1 && rootFail.children.length === 1);

    console.log(`\n${pass} passed, ${fail} failed`);
    process.exit(fail ? 1 : 0);
  }, 2600);
}, 1700);
