// DOM-harness-test för combat split v27.1 (battle log = enda platsen för combat).
// Testar: setCombatSplit (ingen merge-back), toggleBattleLog (arkiv + aktiv strid),
// pane behåller innehåll, aria-hidden, body.battle-drawer-open.
// PLUS allierade (v28): ally cards + HP, 🛡️ log-ikon, turn-chip, fallen-state.
// Kör: node scripts/test-combat-split-dom.js
const fs = require('fs');
const path = require('path');
const html = fs.readFileSync(path.join(__dirname, '..', 'frontend', 'chat.html'), 'utf8');

// ── Mini-DOM ──
class El {
  constructor(tag) {
    this.tagName = tag; this.children = []; this.parentNode = null;
    this._cls = new Set(); this._attrs = {};
    this.innerHTML = ''; this._text = '';
    this.style = {};
    this.scrollTop = 0; this.scrollHeight = 100;
  }
  get classList() {
    const self = this;
    return {
      add: (...c) => c.forEach(x => self._cls.add(x)),
      remove: (...c) => c.forEach(x => self._cls.delete(x)),
      contains: c => self._cls.has(c),
      toggle: (c, force) => {
        const on = (typeof force === 'boolean') ? force : !self._cls.has(c);
        if (on) self._cls.add(c); else self._cls.delete(c);
        return on;
      },
    };
  }
  setAttribute(k, v) { this._attrs[k] = String(v); }
  getAttribute(k) { return this._attrs[k]; }
  // className ↔ classList hålls i synk (som i en riktig DOM)
  set className(v) { this._cls = new Set(String(v).split(/\s+/).filter(Boolean)); }
  get className() { return [...this._cls].join(' '); }
  set textContent(v) { this._text = String(v); this.innerHTML = String(v); }
  get textContent() { return this._text; }
  appendChild(c) { if (c.parentNode) c.parentNode.removeChild(c); c.parentNode = this; this.children.push(c); return c; }
  removeChild(c) { const i = this.children.indexOf(c); if (i >= 0) this.children.splice(i, 1); c.parentNode = null; return c; }
  get firstChild() { return this.children[0] || null; }
  querySelector() { return null; }
}

const registry = {};
function reg(id, el) { registry[id] = el; }
const main = new El('main'); main.classList.add('main');
const chat = new El('div');
const pane = new El('aside'); reg('battle-log', pane);
const blBody = new El('div'); reg('battle-log-body', blBody);
const blRound = new El('span'); reg('bl-round', blRound);
const statusBar = new El('div'); reg('combat-status-bar', statusBar);
const tog = new El('button'); reg('battle-drawer-toggle', tog);
document = { getElementById: id => registry[id] || null, querySelector: sel => sel === '.main' ? main : null, createElement: t => new El(t), createDocumentFragment: () => new El('frag'), body: new El('body') };
global.chat = chat;
global.SPR = { html: s => s };
global.I18N = { getLang: () => 'sv' };
global.SFX = {};
global.escapeHtml = s => String(s);
global.mdToHtml = s => String(s);

// ── Slica combat-sektionen ur chat.html ──
const start = html.indexOf('// ── Combat split-view v27 — panelväxling');
const end = html.indexOf('// container = där stridsposterna hamnar');
if (start < 0 || end < 0) { console.error('MARKERS NOT FOUND'); process.exit(1); }
eval(html.slice(start, end));

// ── Tester ──
let pass = 0, fail = 0;
function assert(name, cond) {
  if (cond) { pass++; console.log('  ✅', name); }
  else { fail++; console.log('  ❌', name); }
}

setCombatSplit(true);
assert('setCombatSplit(true) → .combat-split', main.classList.contains('combat-split'));
assert('setCombatSplit(true) → pane aria-hidden=false', pane.getAttribute('aria-hidden') === 'false');

blBody.appendChild(new El('div'));
setCombatSplit(false);
assert('setCombatSplit(false) → .combat-split borttagen', !main.classList.contains('combat-split'));
assert('setCombatSplit(false) → pane BEHÅLLER innehåll', blBody.children.length === 1);
assert('setCombatSplit(false) → pane aria-hidden=true', pane.getAttribute('aria-hidden') === 'true');
assert('setCombatSplit(false) → chat har INGA pane-barn (ingen merge)', chat.children.length === 0);

main.classList.remove('combat-split'); main.classList.remove('battle-log-open');
_lastCombatStatus = null;
toggleBattleLog();
assert('toggleBattleLog() utan strid → .battle-log-open (arkiv)', main.classList.contains('battle-log-open'));
assert('toggleBattleLog() öppen → body.battle-drawer-open', document.body.classList.contains('battle-drawer-open'));

toggleBattleLog(false);
assert('toggleBattleLog(false) → .battle-log-open borttagen', !main.classList.contains('battle-log-open'));

_lastCombatStatus = { active: true, round: 2 };
toggleBattleLog();
assert('toggleBattleLog() med aktiv strid → .combat-split', main.classList.contains('combat-split'));
toggleBattleLog(false);
assert('minimera under strid → .combat-split borttagen', !main.classList.contains('combat-split'));
toggleBattleLog();
assert('återöppna under strid → .combat-split', main.classList.contains('combat-split'));

// ═══════════════════════════════════════════
// ALLIERADE (v28) — ally rendering tests
// ═══════════════════════════════════════════

// Slice B: combat-renderarna (renderCombatInline, updateCombatStatusBar,
// renderRoundSummary, combatLogHtml, maybeInitiativeReveal, …).
const startB = html.indexOf('// container = där stridsposterna hamnar');
const endB = html.indexOf('// C5 — Resume-recap');
if (startB < 0 || endB < 0) { console.error('MARKERS B NOT FOUND'); process.exit(1); }
// Dedup-tillstånd som deklareras UTANFÖR slice B (L3817-18 / L3742 i chat.html)
// → måste finnas som globals här, annars ReferenceError vid anrop.
global._lastCombatRound = 0;
global._lastCombatEnemyHp = {};
global._lastCombatAllyHp = {};
global._allyCardEls = {};
global._lastInitShown = null;
eval(html.slice(startB, endB));

// _formatCombatLogEntry (activity feed) — egen liten slice
const startF = html.indexOf('function _formatCombatLogEntry');
const endF = html.indexOf('// Live-aktivitet: rendera senaste kampanjlogg-entryn');
if (startF < 0 || endF < 0) { console.error('MARKERS F NOT FOUND'); process.exit(1); }
eval(html.slice(startF, endF));

const blTurn = new El('span'); reg('bl-turn', blTurn);

function textOf(el) {
  let t = el._text || '';
  (el.children || []).forEach(c => { t += textOf(c); });
  return t;
}
function widthsOf(el) {
  const out = (el.style && el.style.width) ? [el.style.width] : [];
  (el.children || []).forEach(c => { out.push(...widthsOf(c)); });
  return out;
}

// ── Ally cards + HP i stridspanelen ──
const battle = new El('div');
renderCombatInline({
  active: true, round: 2, enemies: [],
  allies: [{ id: 'ally-0', name: 'Mimmrick', hp: 12, max_hp: 15, ac: 14, alive: true, statuses: ['gift'] }],
  player_hp: { current: 20, max: 24 },
}, '', battle);
const mim = _allyCardEls['Mimmrick'];
assert('ally card rendered in battle pane', !!mim && mim.card.classList.contains('combat-ally-card'));
assert('ally card shows name', mim && textOf(mim.card).includes('Mimmrick'));
assert('ally card shows HP hp/max_hp', mim && textOf(mim.card).includes('HP 12/15'));
assert('ally card HP bar width = 80%', mim && widthsOf(mim.card).includes('80%'));
assert('ally card shows AC + status rune', mim && textOf(mim.card).includes('AC 14') && textOf(mim.card).includes('☠'));

// ── Dead ally → fallen-state ──
const battle2 = new El('div');
renderCombatInline({ active: true, round: 1, enemies: [], allies: [{ id: 'ally-1', name: 'Borin', hp: 3, max_hp: 10, ac: 12, alive: true }], player_hp: {} }, '', battle2);
renderCombatInline({ active: true, round: 2, enemies: [], allies: [{ id: 'ally-1', name: 'Borin', hp: 0, max_hp: 10, ac: 12, alive: false }], player_hp: {} }, '', battle2);
const borin = _allyCardEls['Borin'];
assert('dead ally card gets .fallen class', borin && borin.card.classList.contains('fallen'));
assert('dead ally card shows Fallen marker', borin && borin.sub.textContent.includes('Fallen'));

// ── combat_log entry actor "ally" → 🛡️ i live battle pane (round summary) ──
const battle3 = new El('div');
renderRoundSummary({ round: 4, log: [{ round: 4, actor: 'ally', name: 'Mimmrick', text: 'träffar goblinen — 5 skada (hugg) (🎲 d20=14+4=18 · 1d6+2: [5]=7)' }] }, battle3);
const rsMsg = battle3.children[0];
assert('round summary renders ally entry with .ally class', !!rsMsg && rsMsg.innerHTML.includes('crs-line ally'));
assert('round summary uses 🛡️ icon for ally', !!rsMsg && rsMsg.innerHTML.includes('🛡️'));
assert('ally dice badge gets .ally-dice-badge', !!rsMsg && rsMsg.innerHTML.includes('ally-dice-badge'));

// ── Activity feed: _formatCombatLogEntry ──
const feed = _formatCombatLogEntry({ round: 4, actor: 'ally', name: 'Mimmrick', text: 'träffar goblinen — 5 skada (hugg)' });
assert('activity feed: ally entry gets 🛡️ icon', feed === '🛡️ Mimmrick: träffar goblinen — 5 skada (hugg)');
assert('activity feed: player/enemy/system unchanged',
  _formatCombatLogEntry({ actor: 'player', name: 'Du', text: 'x' }) === '🗡️ Du: x' &&
  _formatCombatLogEntry({ actor: 'enemy', name: 'Goblin', text: 'y' }) === '⚔️ Goblin: y' &&
  _formatCombatLogEntry({ actor: 'system', text: 'z' }) === '📜 z');

// ── Turn chip: ally-{id} i turn_order ──
updateCombatStatusBar({
  active: true, round: 3, enemies: [],
  allies: [{ id: 'ally-0', name: 'Mimmrick', hp: 12, max_hp: 15, alive: true }],
  player_hp: { current: 20, max: 24 },
  turn_order: [{ key: 'ally-0', name: 'Mimmrick', initiative: 18, acted: false }], current_index: 0,
});
assert('turn chip shows 🎯 {ally name}', blTurn.textContent === '🎯 Mimmrick');
assert('turn chip gets .turn-ally class', blTurn.classList.contains('turn-ally'));
assert('status bar shows ally HP (🛡️ Mimmrick 12/15)', statusBar.innerHTML.includes('🛡️ Mimmrick 12/15'));

// ── Regression: player/enemy turn chips oförändrade ──
updateCombatStatusBar({ active: true, round: 3, enemies: [], allies: [], player_hp: { current: 20, max: 24 }, turn_order: [{ key: 'player', name: 'Du', initiative: 22, acted: false }], current_index: 0 });
assert('player turn chip unchanged (Din tur / .turn-player)', blTurn.textContent === '🎯 Din tur' && blTurn.classList.contains('turn-player'));
updateCombatStatusBar({ active: true, round: 3, enemies: [{ name: 'Goblin', hp: 5, max_hp: 7, alive: true }], allies: [], player_hp: { current: 20, max: 24 }, turn_order: [{ key: 'goblin-0', name: 'Goblin', initiative: 5, acted: false }], current_index: 0 });
assert('enemy turn chip unchanged (🎯 name / .turn-enemy)', blTurn.textContent === '🎯 Goblin' && blTurn.classList.contains('turn-enemy'));

// ── Initiative reveal: ally-entry med .ir-ally ──
const battle4 = new El('div');
maybeInitiativeReveal({ initiative: [{ key: 'player', name: 'Du', value: 20 }, { key: 'ally-0', name: 'Mimmrick', value: 18 }, { key: 'goblin-0', name: 'Goblin', value: 5 }] }, battle4);
const ir = battle4.children[0];
assert('initiative reveal lists ally with .ir-ally class', !!ir && ir.innerHTML.includes('ir-ally') && ir.innerHTML.includes('Mimmrick'));

// ── Regression: fiende-kort renderas fortfarande ──
const battle5 = new El('div');
renderCombatInline({ active: true, round: 5, enemies: [{ name: 'Goblin', hp: 4, max_hp: 7, alive: true }], allies: [], player_hp: {} }, '', battle5);
assert('enemy cards still render (regression)', Object.keys(_lastCombatEnemyHp).includes('Goblin'));

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
