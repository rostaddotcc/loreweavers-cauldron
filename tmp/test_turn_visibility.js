#!/usr/bin/env node
// Test-harness: extraherar renderTurnTally (chat) och renderQuotaPill (adventure)
// och kör dem mot en minimal DOM-stub med fyra kontofall.
const fs = require('fs');

function extractFn(file, fnName) {
  const src = fs.readFileSync(file, 'utf8');
  const start = src.indexOf('function ' + fnName + '(');
  if (start < 0) throw new Error(fnName + ' saknas i ' + file);
  let depth = 0, i = src.indexOf('{', start);
  const bodyStart = i;
  for (; i < src.length; i++) {
    if (src[i] === '{') depth++;
    else if (src[i] === '}') { depth--; if (depth === 0) { i++; break; } }
  }
  return src.slice(start, i);
}

function makeEl() { return { style: { display: '' }, textContent: '', innerHTML: '' }; }
function makeDom(ids) {
  const els = {};
  for (const id of ids) els[id] = makeEl();
  return {
    els,
    document: {
      getElementById: (id) => els[id] || null,
      querySelector: (sel) => els['__' + sel] || (els['__' + sel] = makeEl()),
    },
  };
}

const cases = [
  { name: 'free nybörjare',     me: { subscription_status: 'free',   turn_cap: 30,  turns_used: 5, turn_bonus: 0,   turns_available: 25, reset_date: '2026-09-29' } },
  { name: 'free nära tak',      me: { subscription_status: 'free',   turn_cap: 30,  turns_used: 27, turn_bonus: 0,  turns_available: 3,  reset_date: '2026-09-29' } },
  { name: 'tier2 betald',       me: { subscription_status: 'tier2',  turn_cap: 30,  turns_used: 4, turn_bonus: 96,  turns_available: 122, reset_date: '2026-09-29' } },
  { name: 'free m. köpta kvar', me: { subscription_status: 'free',   turn_cap: 30,  turns_used: 30, turn_bonus: 50, turns_available: 50, reset_date: '2026-09-29' } },
  { name: 'lifetime',           me: { subscription_status: 'lifetime', turn_cap: 0, turns_used: 0, turn_bonus: 0,   turns_available: 0, reset_date: null } },
];

// ── chat.html renderTurnTally ──
const chatIds = ['rr-turn','rr-day','rr-quota-row','rr-quota','rr-quota-sep','rr-bonus-row','rr-bonus','rr-bonus-sep','rr-warn-row','rr-warn','rr-warn-sep','rr-reset-row','rr-reset','rr-reset-sep'];
const chatFn = extractFn('/home/rostads/dnd-llm/frontend/chat.html', 'renderTurnTally');
console.log('=== chat.html renderTurnTally ===');
for (const c of cases) {
  const dom = makeDom(chatIds);
  const fn = new Function('document', 'I18N', '_meData', '_tier', 'currentTurnNum', 'currentDayNum', 'tallyResetFmt', chatFn + '; return renderTurnTally();');
  fn(dom.document, { getLang: () => 'en' }, c.me, () => c.me.subscription_status,
     () => 12, () => 3, (me) => '🕯 3h 12m');
  const e = dom.els;
  const quotaVis = e['rr-quota-row'].style.display !== 'none' && c.me.turn_cap !== 0 && c.me.subscription_status !== 'lifetime';
  console.log(`${c.name.padEnd(22)} TURNS=${(e['rr-quota'].textContent || '—').padEnd(6)} [${e['rr-quota-row'].style.display === 'none' ? 'dold' : 'SYNLIG'}]  BOUGHT=${(e['rr-bonus'].textContent || '—').padEnd(4)} [${e['rr-bonus-row'].style.display === 'none' ? 'dold' : 'SYNLIG'}]  warn=${e['rr-warn'].textContent || '-'} [${e['rr-warn-row'].style.display === 'none' ? 'dold' : 'SYN'}]`);
}

// ── adventure.html renderQuotaPill ──
const advIds = ['quota-warn','quota-warn-tv','quota-warn-sep','quota-turns-row','quota-turns','quota-turns-sep','quota-bonus-row','quota-bonus','quota-bonus-sep','quota-cd','quota-benefits'];
const advFn = extractFn('/home/rostads/dnd-llm/frontend/adventure.html', 'renderQuotaPill');
console.log('\n=== adventure.html renderQuotaPill ===');
for (const c of cases) {
  const dom = makeDom(advIds);
  const run = new Function('document','isEn','window','quotaNextReset','quotaTick','setInterval','quotaBenefitsFmt','me',
    'let _quotaMe=null,_quotaTimer=null,_quotaNextTs=null;' + advFn + '; renderQuotaPill(me);');
  run(dom.document, () => true, {}, () => Date.now() + 3600e3, () => {}, () => 1, () => null, c.me);
  const e = dom.els;
  console.log(`${c.name.padEnd(22)} TURNS=${(e['quota-turns'].textContent || '—').padEnd(6)} [${e['quota-turns-row'].style.display === 'none' ? 'dold' : 'SYNLIG'}]  BOUGHT=${(e['quota-bonus'].textContent || '—').padEnd(4)} [${e['quota-bonus-row'].style.display === 'none' ? 'dold' : 'SYNLIG'}]  warn=${e['quota-warn-tv'].textContent || '-'} [${e['quota-warn'].style.display === 'none' ? 'dold' : 'SYN'}]`);
}
