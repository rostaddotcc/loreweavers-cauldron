// DOM-harness-test för combat split v27.1 (battle log = enda platsen för combat).
// Testar: setCombatSplit (ingen merge-back), toggleBattleLog (arkiv + aktiv strid),
// pane behåller innehåll, aria-hidden, body.battle-drawer-open.
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

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
