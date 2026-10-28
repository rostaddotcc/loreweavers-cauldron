/* ══════════════════════════════════════════════════════════════════════════════
   Emberwatch — the cauldron, observed (2026-10-22)

   The console stopped being a reporting dashboard. Traffic is Umami's job
   (analytics.rostad.cc); this surface is about the game: turns booked at the
   table, the calls each turn made, and the letters players send in.

   Reads:  /api/admin/overview?window=      turns, series, accounts
           /api/admin/user/{u}/ledger       the call feed (merged client-side)
           /api/admin/user/{u}              player dossier
           /api/admin/model/{model}         model drill-down
           /api/admin/billing               money
           /api/admin/feedback              the letters
   Writes: never directly — every mutation goes through window.AdminActions.
   Numbers are computed server-side; this file only formats and drills down.
   ══════════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  /* ── gate: admin pages require the sessionStorage marker the login flow sets.
     login.html writes a plain username string (sessionStorage.setItem('dnd_user', u.username)),
     so treat the marker as opaque — only its presence matters here. ── */
  if (!sessionStorage.getItem('dnd_user')) { location.href = 'login.html'; return; }

  const PALETTE = ['#E8734A', '#ECC468', '#5FCB9B', '#A78BFA', '#58C7BE', '#E4616F', '#8E8380'];
  const PROV_COLOR = { stepfun:'#ECC468', dashscope:'#58C7BE', deepseek:'#A78BFA', openrouter:'#E8734A', ollama:'#8E8380', 'ollama (relay)':'#8E8380', mimo:'#5FCB9B', unlabelled:'#6F645F', unknown:'#6F645F' };
  const PROV_LABEL = { stepfun:'StepFun', dashscope:'Qwen · DashScope', deepseek:'DeepSeek', openrouter:'OpenRouter', ollama:'Local Ollama', 'ollama (relay)':'Ollama relay', mimo:'MiMo', unlabelled:'Unlabelled', unknown:'Unknown' };
  const MODEL_SKIP = { '__unlabelled':1, '?':1, '':1 };
  const TIER_LABEL = { free:'Free', tier1:'Support', tier2:'Patron', lifetime:'Lifetime' };

  const S = {
    view: 'overview', win: '7d', metric: 'calls', revMode: 'day',
    data: null, billing: null, feedback: null, fbRange: 'all', fbMail: 'all',
    sortKey: 'last_active', sortDir: 'desc', page: 1, pageSize: 10,
    q: '', fRole: 'all', fStatus: 'all', fCountry: 'all', fCode: 'all',
    auto: false, timer: null, degraded: false, loading: false, dossier: null,
    /* Emberwatch (2026-10-22): the call ledger is merged client-side, so its
       view state lives here — how many rows the overview shows, which page and
       filters the Calls view is on, and which letters are expanded. */
    callsShown: 20, callPage: 1, callSize: 50, callAction: 'all', callModel: 'all',
    callQ: '', fbOpen: {},
    /* Hink-filtret i dossiéns ledger-tabell (2026-09-28). Nollställs när en ny
       spelare öppnas, så ett filter aldrig läcker mellan konton. */
    dossierBucket: 'all',
    /* expand = "show all" per panel (referrers, countries, models, players-model-mix).
       Empty = the panel's default cap. Never silently truncate without the control. */
    expand: {}, drawerState: null,
  };

  /* ────────────────────────────── helpers ────────────────────────────── */
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.prototype.slice.call((r || document).querySelectorAll(s));
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c]));
  const num = n => (n == null || n === '' ? '—' : Number(n).toLocaleString('en-US'));
  const sek = n => (n == null ? '—' : Number(n).toLocaleString('en-US') + ' kr');
  const tok = n => { n = Number(n || 0); if (n >= 1e9) return (n / 1e9).toFixed(2) + 'B'; if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M'; if (n >= 1e3) return (n / 1e3).toFixed(1) + 'k'; return String(n); };
  const sum = o => Object.values(o || {}).reduce((a, b) => a + (Number(b) || 0), 0);
  const sumRows = (rows, k) => (rows || []).reduce((a, r) => a + (Number(r[k]) || 0), 0);
  const pct = (a, b) => (b ? (a / b * 100) : 0).toFixed(1) + '%';
  const dayLabel = d => String(d || '').slice(5);
  const stamp = iso => { try { return new Date(iso).toLocaleString('en-GB', { day:'2-digit', month:'short', hour:'2-digit', minute:'2-digit' }); } catch (e) { return iso || ''; } };
  const modelLabel = m => !m || m === '__unlabelled' ? 'unlabelled / legacy'
    : (m === 'undo-voided' ? 'undo-voided (refunded turn)' : m.replace(/^orfree:/, '').replace(/:free$/, ''));
  const provOf = m => { const s = String(m || ''); if (s === '__unlabelled') return 'unlabelled'; if (/^local:/.test(s)) return 'ollama (relay)'; if (/^qwen|^wan|^glm/.test(s)) return 'dashscope'; if (/^deepseek/.test(s)) return 'deepseek'; if (/^step/.test(s)) return 'stepfun'; if (/^orfree:/.test(s)) return 'openrouter'; if (/^mimo/.test(s)) return 'mimo'; return 'unknown'; };
  const provColor = p => PROV_COLOR[p] || '#6b7c92';
  const REGION = (function () { try { return new Intl.DisplayNames(['en'], { type: 'region' }); } catch (e) { return null; } })();
  /* 'SE' → 'Sweden'. '??'/'' → 'Unknown (no geo)': the geo cache is filled offline, so
     unknown origins are a real state, not a bug to hide. */
  function ccName(cc) {
    const c = String(cc || '').toUpperCase();
    if (!c || c === '??' || c === 'UNKNOWN') return 'Unknown (no geo yet)';
    if (c === 'LOCAL') return 'Local / private network';
    if (REGION) { try { const n = REGION.of(c); if (n && n !== c) return n; } catch (e) { /* invalid code */ } }
    return c;
  }

  function toast(msg, kind) {
    const el = document.createElement('div');
    el.className = 'toast' + (kind ? ' ' + kind : '');
    el.textContent = msg;
    $('#toasts').appendChild(el);
    setTimeout(() => el.remove(), 3200);
  }
  function csvDownload(name, rows) {
    const text = (rows || []).map(r => (r || []).map(c => '"' + String(c == null ? '' : c).replace(/"/g, '""') + '"').join(',')).join('\n');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([text], { type: 'text/csv;charset=utf-8' }));
    a.download = name;
    a.click();
    toast('Exported ' + name);
  }

  async function api(path) {
    const res = await fetch(path, { credentials: 'include' });
    if (res.status === 401) { location.href = 'login.html'; throw new Error('HTTP 401: session expired'); }
    const body = await res.text();
    let data = {};
    if (body) { try { data = JSON.parse(body); } catch (e) { data = null; } }
    if (res.status === 403) throw Object.assign(new Error('HTTP 403: this account has no admin access'), { status: 403 });
    if (!res.ok) {
      const detail = data && (data.detail || data.message);
      const msg = typeof detail === 'string' ? detail : (detail ? JSON.stringify(detail) : (data === null ? 'unreadable response' : ''));
      throw Object.assign(new Error('HTTP ' + res.status + (msg ? ': ' + msg : '')), { status: res.status });
    }
    return data || {};
  }

  /* ── payload accessors (defensive: the console must never blank on a missing key) ── */
  const D = () => S.data || {};
  const TOT = () => D().totals || {};
  const REV = () => D().revenue || {};
  const VAL = () => D().value || {};
  const SER = () => D().series || {};
  const USAGE = () => D().usage || {};
  const TIERS = () => D().tiers || {};
  const USERS = () => D().users || [];
  const ledgerRows = () => (S.billing && S.billing.ledger) || REV().ledger || [];
  /* "Show all"-kapning: default N, full lista när panelen är expanderad. */
  function clampList(items, panel, def) {
    const all = items || [];
    if (S.expand[panel] || all.length <= def) return { rows: all, hidden: 0 };
    return { rows: all.slice(0, def), hidden: all.length - def };
  }
  function expandBtn(panel, hidden, noun) {
    if (!hidden && !S.expand[panel]) return '';
    return '<button type="button" class="chip clear" data-expand="' + esc(panel) + '">' +
      (S.expand[panel] ? '▴ Show top ' + esc(noun) : '▾ ' + num(hidden) + ' more ' + esc(noun)) + '</button>';
  }

  /* ────────────────────────────── charts ────────────────────────────── */
  function emptyState(msg, glyph) {
    return '<div class="empty"><span class="g">' + esc(glyph || '✧') + '</span>' + esc(msg) + '</div>';
  }
  function vchart(series, opts) {
    opts = opts || {};
    const keys = Object.keys(series || {});
    if (!keys.length) return emptyState(opts.emptyMsg || 'No data in this window', '◌');
    const max = Math.max.apply(null, keys.map(k => Number(series[k]) || 0)) || 1;
    const lastKey = keys[keys.length - 1];
    // Etikett-glesning: en 30-dagars-serie ger ~23px per kolumn men '08-29' behöver ~30px,
    // så varannan-tredje etikett krockar. Visa var n:te (första + sista alltid) i stället för
    // att klippa/fuska — CSS kan inte lösa det här utan att ljuga om datat.
    const thin = opts.labelEvery ? 1 : (keys.length > 12 ? Math.ceil(keys.length / 8) : 1);
    const keepAt = i => thin === 1 || i % thin === 0 || i === keys.length - 1;
    return '<div class="vchart">' + keys.map((k, i) => {
      const v = Number(series[k]) || 0;
      const h = v ? Math.max(Math.round(v / max * 100), 2) : 0;
      const lab = opts.labelEvery ? opts.labelEvery(k, i, keys.length) : dayLabel(k);
      const kept = keepAt(i);
      const showVal = v && (keys.length <= 16 || v === max || i === keys.length - 1);
      /* Klickbar kolumn: revenue-kurvan (opts.rev) bugar en LEDGER-bucket
         (data-bucket → drawerBucket), alla andra dagserier bugar DEN DAGEN
         (data-day → drawerDay). Forut klickade alla grafer pa data-bucket —
         det ville siga "betalningar denna dag", sa en trafik- eller turns-
         stapel ledde till en tom kassa. (Dod drilldown, rostad 2026-09-30.) */
      const drillAttr = opts.rev
        ? 'data-bucket="' + esc(k) + '" data-val="' + v + '"'
        : 'data-day="' + esc(k) + '"';
      return '<div class="vcol' + (k === lastKey ? ' today' : '') + (opts.rev ? ' rev' : '') + '" ' + drillAttr + ' title="' + esc(k + ' · ' + num(v) + (opts.unit ? ' ' + opts.unit : '')) + '" style="--i:' + i + '">' +
        '<span class="lab">' + (showVal ? num(v) : '') + '</span>' +
        '<span class="track"><span class="fill" style="height:' + h + '%"></span></span>' +
        '<span class="lab">' + (kept ? esc(lab) : '') + '</span></div>';
    }).join('') + '</div>';
  }
  function donut(items, centerLabel, centerSub, opts) {
    opts = opts || {};
    const all = (items || []).filter(Boolean);
    // keepZero: visa hela fördelningen även när en post är 0 (alla tiers/produkter
    // ska synas i legenden — nollor är information i en adminvy, inte brus).
    const items2 = opts.keepZero ? all : all.filter(i => (Number(i.value) || 0) > 0);
    const total = items2.reduce((a, b) => a + (Number(b.value) || 0), 0);
    if (!total) return emptyState(opts.emptyMsg || 'Nothing to split yet', '◌');
    const C = 2 * Math.PI * 70;
    let off = 0;
    const arcs = items2.filter(it => (Number(it.value) || 0) > 0).map((it, i) => {
      const frac = (Number(it.value) || 0) / total;
      const dash = Math.max(frac * C - 2, 0.001);
      const el = '<circle r="70" cx="100" cy="100" fill="none" stroke="' + (it.color || PALETTE[i % PALETTE.length]) + '" stroke-width="26" ' +
        'stroke-dasharray="' + dash + ' ' + (C - dash) + '" stroke-dashoffset="' + (-off) + '" transform="rotate(-90 100 100)">' +
        '<title>' + esc(it.label) + ': ' + num(it.value) + '</title></circle>';
      off += frac * C;
      return el;
    }).join('');
    return '<div class="donut-wrap">' +
      '<svg class="donut" viewBox="0 0 200 200" role="img" aria-label="' + esc(centerLabel) + '">' +
      '<circle r="70" cx="100" cy="100" fill="none" stroke="var(--line)" stroke-width="26"></circle>' + arcs +
      '<text class="donut-center" x="100" y="97" text-anchor="middle" font-size="18" font-weight="600" fill="currentColor">' + esc(centerLabel || num(total)) + '</text>' +
      '<text x="100" y="115" text-anchor="middle" font-size="10" fill="currentColor" opacity=".55">' + esc(centerSub || '') + '</text></svg>' +
      '<div class="legend">' + items2.map((it, i) =>
        '<button type="button" data-slice="' + i + '" data-slicekey="' + esc(it.key || it.label) + '"' +
        (opts.click ? ' ' + opts.click(it) : '') +
        ((Number(it.value) || 0) ? '' : ' class="zero" style="opacity:.55"') + '>' +
        '<span class="dot" style="background:' + (it.color || PALETTE[i % PALETTE.length]) + '"></span>' +
        '<span class="lb">' + esc(it.label) + '</span><span class="val">' + num(it.value) + '</span>' +
        '<span class="pct">' + pct(Number(it.value) || 0, total) + '</span></button>').join('') + '</div></div>';
  }
  function hbars(items, opts) {
    opts = opts || {};
    items = (items || []).filter(Boolean);
    if (!items.length) return emptyState(opts.emptyMsg || 'Nothing here in this window', '◌');
    const max = Math.max.apply(null, items.map(i => Number(i.value) || 0)) || 1;
    return '<div class="hbars' + (opts.className ? ' ' + opts.className : '') + '">' + items.map(i =>
      '<div class="hbar' + (opts.click ? ' clickable' : '') + '" data-key="' + esc(i.key || i.label) + '"' +
      (opts.click ? ' ' + opts.click(i) : '') +
      ' title="' + esc(i.label + ' · ' + num(i.value) + (opts.unit ? ' ' + opts.unit : '') + (opts.click ? ' · click for the records behind it' : '')) + '">' +
      '<div class="row"><span class="nm">' + esc(i.label) + '</span><span class="vl">' + (opts.fmt ? opts.fmt(i.value) : num(i.value)) + '</span></div>' +
      '<span class="track"><span class="fill" style="width:' + Math.max((Number(i.value) || 0) / max * 100, i.value ? 2 : 0) + '%;background:' + (i.color || 'var(--accent)') + '"></span></span></div>').join('') + '</div>';
  }
  function spark(series) {
    const keys = Object.keys(series || {});
    if (!keys.length) return '';
    const max = Math.max.apply(null, keys.map(k => Number(series[k]) || 0)) || 1;
    return '<div class="spark">' + keys.map(k =>
      '<i style="height:' + Math.max((Number(series[k]) || 0) / max * 100, series[k] ? 4 : 1) + '%" title="' + esc(k + ': ' + num(series[k])) + '"></i>').join('') + '</div>';
  }
  /* Färgkodade KPI-rutor (rostad 2026-09-30): varje ton = ett begrepp.
     gold = pengar, good = turns, accent = spelare/konton, violet = trafik/anrop,
     teal = pottar, warn = kostnad. Pricken i rubriken och siffrans färg följer
     samma ton — ögat hittar "intäkter" utan att läsa texten. */
  const TONE_COLOR = { gold:'var(--gold)', good:'var(--good)', accent:'var(--accent)', violet:'var(--violet)', teal:'var(--teal)', warn:'var(--warn)' };
  function kpi(o) {
    return '<div class="card kpi' + (o.drill ? ' clickable' : '') + '"' + (o.drill ? ' data-drill="' + esc(o.drill) + '"' : '') +
      (o.tone && TONE_COLOR[o.tone] ? ' style="--k:' + TONE_COLOR[o.tone] + '"' : '') + '>' +
      '<span class="t">' + (o.tone && TONE_COLOR[o.tone] ? '<span class="tdot"></span>' : '') + esc(o.t) + '</span>' +
      '<span class="v' + (o.tone ? ' ' + o.tone : '') + '">' + o.v + '</span>' +
      (o.delta || '') +
      '<span class="f">' + o.f + '</span>' +
      (o.drill ? '<span class="cta">' + esc(o.cta || 'drill down →') + '</span>' : '') + '</div>';
  }
  function card(span, title, sub, body, opts) {
    opts = opts || {};
    /* opts.drill: hela kortet blir en riktig drilldown (data-drill på kortet,
       samma handler som KPI-rutorna) — utan den var .clickable bara en lögn.
       opts.cls: extra klass, t.ex. 'side' för ett följande sidopanel. */
    return '<div class="card span' + span + (opts.cls ? ' ' + opts.cls : '') + (opts.data ? ' ' + opts.data : '') + (opts.drill ? ' clickable' : '') + '"' +
      (opts.drill ? ' data-drill="' + esc(opts.drill) + '"' : '') + '>' +
      '<h3>' + title + '</h3>' + (sub ? '<div class="sub">' + sub + '</div>' : '') + body + '</div>';
  }
  function ledgerTable(rows, emptyMsg) {
    rows = rows || [];
    if (!rows.length) return emptyState(emptyMsg || 'No transactions yet', '◌');
    return '<div class="tbl-wrap"><table><thead><tr><th>Date</th><th>User</th><th class="num">Amount</th><th>Type</th><th>Note</th></tr></thead><tbody>' +
      rows.map(r => '<tr data-tx="' + esc(r.ts || '') + '"><td>' + esc(String(r.ts || '').slice(0, 10)) + '</td>' +
        '<td>' + esc(r.user || '') + '</td>' +
        '<td class="num" style="color:' + ((r.amount_sek || r.sek) ? 'var(--good)' : 'var(--dim-2)') + '">' + sek(r.amount_sek != null ? r.amount_sek : r.sek) + '</td>' +
        '<td><span class="tag' + ((r.amount_sek || r.sek) ? ' paid' : '') + '">' + ((r.amount_sek || r.sek) ? '' : 'trace · ') + esc(String(r.type || '').replace('stripe:', '').replace('legacy:', 'legacy/')) + '</span></td>' +
        '<td class="note-cell">' + esc(r.note || (r.event_id ? 'event ' + String(r.event_id).slice(0, 14) + '…' : '')) + '</td></tr>').join('') + '</tbody></table></div>';
  }
  function tierTag(t) { t = t || 'free'; return '<span class="tag ' + esc(t) + '">' + esc(TIER_LABEL[t] || t) + '</span>'; }

  /* ── Turn-pott + free/paid-kod (2026-09-28, rostad) ────────────────────────
     Allt kommer SERVER-RÄKNAT (turn_pool/coding i payloaden). Klienten
     formaterar bara — räknade den själv skulle tabellen, dossién och CSV:n
     kunna säga olika saker om samma konto. Saknas fälten (degraded/legacy-
     payload) faller vi tillbaka på den gamla tier-etiketten i stället för att
     hitta på en kod. */
  const CODE_LABEL = { paid:'Paid', granted:'Granted', free:'Free' };
  function codeOf(u) {
    const c = (u && u.coding) || null;
    return (c && c.code) ? c.code : null;
  }
  function codeWhy(u) {
    const c = (u && u.coding) || null;
    return (c && c.why) ? String(c.why) : '';
  }
  function codeTag(u) {
    const code = codeOf(u);
    if (!code) return tierTag(u && u.subscription_status);
    const tier = ((u.coding || {}).tier) || (u && u.subscription_status) || 'free';
    const why = codeWhy(u);
    const tip = CODE_LABEL[code] + (why ? ' · ' + why : '') + ' · tier ' + tier;
    return '<span class="tag ' + esc(code) + '" title="' + esc(tip) + '">' + esc(CODE_LABEL[code]) + '</span>';
  }
  function codeDot(u) {
    const code = codeOf(u);
    const why = codeWhy(u);
    return '<span class="codedot' + (code ? ' ' + esc(code) : '') + '" title="' +
      esc(code ? (CODE_LABEL[code] + (why ? ' · ' + why : '')) : 'No coding in this payload (legacy server)') + '"></span>';
  }
  function poolOf(u) { const tp = (u && u.turn_pool) || null; return (tp && typeof tp === 'object') ? tp : null; }
  /* Potten radvis: "25/30 free left", "464 paid left". Alla siffror visas som
     KVAR — rostad 2026-09-28: "jag vill se free turns left, inte used turns".
     Tabellcellen radbryter hellre än att kapa ett nyckeltal. */
  function poolLines(u) {
    const tp = poolOf(u);
    if (!tp) return [];
    const out = [tp.unlimited ? '∞ free (no cap)' : num(tp.free_left) + '/' + num(tp.free_cap) + ' free left'];
    if (Number(tp.promo_left)) out.push(num(tp.promo_left) + ' promo left');
    if (Number(tp.paid_left)) out.push(num(tp.paid_left) + ' paid left');
    return out;
  }
  /* Potten i en rad — titlar, drawer-tabeller och mobilkortet. */
  function poolText(u) {
    const lines = poolLines(u);
    return lines.length ? lines.join(' · ') : '—';
  }
  /* Pottens rubrik till dossiéns ruta: "469  (5/30 free · 464 paid)". */
  function poolTitle(u) {
    const tp = poolOf(u);
    if (!tp) return '—';
    return (tp.unlimited ? '∞' : num(tp.available)) + ' <small>' + esc(poolText(u)) + '</small>';
  }
  /* Förbrukat i livstid, alla tre hinkar. Finns i både rad och dossier. */
  function poolUsedTotal(u) {
    const life = (poolOf(u) || {}).used_lifetime || {};
    return (Number(life.free) || 0) + (Number(life.promo) || 0) + (Number(life.paid) || 0) + (Number(life.unknown) || 0);
  }
  function poolBar(u) {
    const tp = poolOf(u);
    if (!tp) return '';
    const free = tp.unlimited ? 1 : Math.max(0, Number(tp.free_left) || 0);
    const promo = Math.max(0, Number(tp.promo_left) || 0);
    const paid = Math.max(0, Number(tp.paid_left) || 0);
    const total = free + promo + paid;
    if (!total) return '<span class="poolbar empty" title="No turns left in this pool"><i></i></span>';
    const seg = (cls, v) => v ? '<i class="' + cls + '" style="flex:' + v + '"></i>' : '';
    return '<span class="poolbar" title="' + esc(poolText(u)) + '">' +
      seg('free', free) + seg('promo', promo) + seg('paid', paid) + '</span>';
  }
  /* Relativ tid för last_active. Tom/ogiltig stämpel → "never", aldrig "0 min"
     (dashboarden får inte hitta på en aktivitet). */
  function agoText(iso) {
    const t = Date.parse(iso || '');
    if (!t) return 'never';
    const mins = Math.floor((Date.now() - t) / 60000);
    if (mins < 0) return 'clock skew';        // server-klocka före klienten
    if (mins < 1) return 'just now';
    if (mins < 60) return mins + ' min ago';
    const h = Math.floor(mins / 60);
    if (h < 24) return h + ' h ago';
    const d = Math.floor(h / 24);
    return d === 1 ? 'yesterday' : d + ' days ago';
  }
  /* Staplad graf: en kolumn per dag, hinkarna staplade (fri nederst → köpt →
     promo → legacy/okänd). Samma totalsiffra som vchart — hink-fördelningen
     kommer ur ledgerns `bucket`, och rader före 2026-09-28 är "other" (okänd),
     aldrig påhittade som "free". */
  const POOL_PARTS = ['free', 'paid', 'promo', 'other'];
  function bucketVal(split, part) {
    const s = split || {};
    if (part === 'other') return Number(s.none || 0) + Number(s.unknown || 0);
    return Number(s[part] || 0);
  }
  function poolLegend(byDay) {
    const totals = {};
    POOL_PARTS.forEach(p => { totals[p] = 0; });
    Object.keys(byDay || {}).forEach(d => POOL_PARTS.forEach(p => { totals[p] += bucketVal(byDay[d], p); }));
    const rows = POOL_PARTS.map(p => ({ key:p, label:p === 'other' ? 'legacy / unknown' : p, value:totals[p], color:POOL_PART_COLOR[p] }))
      .filter(r => r.value > 0);
    const sum = rows.reduce((a, r) => a + r.value, 0);
    return '<div class="legend pool-legend">' + rows.map(r =>
      '<span class="lg' + (r.value ? '' : ' zero') + '"><span class="dot" style="background:' + r.color + '"></span>' +
      '<span class="lb">' + esc(r.label) + '</span><span class="val">' + num(r.value) + '</span>' +
      '<span class="pct">' + pct(r.value, sum) + '</span></span>').join('') + '</div>';
  }
  const POOL_PART_COLOR = { free:'var(--good)', paid:'var(--warn)', promo:'var(--violet)', other:'var(--dim)' };
  function vchartStacked(byDay, opts) {
    opts = opts || {};
    const keys = Object.keys(byDay || {});
    if (!keys.length) return emptyState(opts.emptyMsg || 'No turn series in this payload', '◌');
    const totals = keys.map(k => POOL_PARTS.reduce((a, p) => a + bucketVal(byDay[k], p), 0));
    const max = Math.max.apply(null, totals) || 1;
    const lastKey = keys[keys.length - 1];
    const thin = keys.length > 12 ? Math.ceil(keys.length / 8) : 1;
    const keepAt = i => thin === 1 || i % thin === 0 || i === keys.length - 1;
    return '<div class="vchart stacked">' + keys.map((k, i) => {
      const segs = POOL_PARTS.map(p => {
        const v = bucketVal(byDay[k], p);
        if (!v) return '';
        return '<span class="sseg ' + p + '" style="height:' + (v / max * 100) + '%" title="' + esc(k + ' · ' + p + ' · ' + num(v) + ' ' + (opts.unit || 'turns')) + '"></span>';
      }).join('');
      return '<div class="vcol" data-day="' + esc(k) + '" data-val="' + totals[i] + '" title="' + esc(k + ' · ' + num(totals[i]) + ' ' + (opts.unit || 'turns') + ' · click for the day') + '" style="--i:' + i + '">' +
        '<span class="lab">' + (totals[i] && (keys.length <= 16 || totals[i] === max) ? num(totals[i]) : '') + '</span>' +
        '<span class="track stack">' + segs + '</span>' +
        '<span class="lab">' + (keepAt(i) ? esc(dayLabel(k)) : '') + '</span></div>';
    }).join('') + '</div>' + poolLegend(byDay);
  }

  /* ────────────────────────────── views ────────────────────────────── */
  function valueStats() {
    const v = VAL();
    const turns = Number(v.turns) || 0;
    const tokens = Number(v.tokens) || 0;
    const money = Number(REV().total != null ? REV().total : REV().lifetime) || 0;
    const tps = v.tokens_per_sek != null ? Number(v.tokens_per_sek) : (money ? Math.round(tokens / money) : null);
    const kpm = v.kr_per_1m_tokens != null ? Number(v.kr_per_1m_tokens) : (tokens ? (1e6 * money / tokens) : null);
    /* Per hink och dag (2026-09-28): server-räknad ur ledgerns `bucket`.
       Klienten summerar bara för grafen — aldrig för ett nyckeltal. */
    const bucketDay = v.turns_by_bucket_day || {};
    const bucketDayTotals = {};
    POOL_PARTS.forEach(p => { bucketDayTotals[p] = 0; });
    Object.keys(bucketDay).forEach(d => POOL_PARTS.forEach(p => { bucketDayTotals[p] += bucketVal(bucketDay[d], p); }));
    return { turns, tokens, money, tps, kpm, calls: Number(v.ai_calls || TOT().ai_calls) || 0, bucketDay, bucketDayTotals,
      /* Källuppdelningen (2026-09-28) kommer färdigräknad från servern. */
      sources: v.tokens_sources || null };
  }
  function tierItems() {
    const t = TIERS();
    return [
      { label:'Free', value:t.free || 0, color:'#55708f', key:'free' },
      { label:'Patron (tier2)', value:t.tier2 || 0, color:'#a97bff', key:'tier2' },
      { label:'Support (tier1)', value:t.tier1 || 0, color:'#4fc3c8', key:'tier1' },
      { label:'Lifetime', value:t.lifetime || 0, color:'#e0a24a', key:'lifetime' },
    ];
  }
  function modelItems(metric) {
    const models = USAGE().models || {};
    return Object.keys(models).filter(m => !MODEL_SKIP[m]).map(m => ({
      key: m, label: modelLabel(m), value: Number(models[m][metric] || 0), color: provColor(models[m].provider || provOf(m)),
    })).sort((a, b) => b.value - a.value);
  }
  function providerItems() {
    const p = USAGE().providers || {};
    return Object.keys(p).sort((a, b) => (p[b].calls || 0) - (p[a].calls || 0))
      .map(k => ({ key: k, label: (PROV_LABEL[k] || k), value: Number(p[k].calls || 0), color: provColor(k) }));
  }
  function tokenSplitItems() {
    const p = USAGE().providers || {};
    return Object.keys(p).filter(k => (p[k].tokens || 0) > 0).sort((a, b) => p[b].tokens - p[a].tokens)
      .map(k => ({ key: k, label: (PROV_LABEL[k] || k), value: Number(p[k].tokens || 0), color: provColor(k) }));
  }

  /* Nya spelare inom valt datumfilter (rostad 2026-09-30): "+3 players · 7d",
     eller "+1 today" för 24h-fönstret. Räknas client-side ur USERS() med samma
     lokala dags-fönster som servern (24h=idag, 7d=idag+6, 30d=idag+29), men
     BARA roll==player — admins är inga nya spelare. `all` döljer chipt
     (då är summan = alla konton, ingen information). */

/* ═══════════════════════════════ EMBERWATCH ═══════════════════════════════
     The table view (2026-10-22). Traffic moved to Umami, so this console is
     about the game: turns spent, the calls each turn books, and the letters
     players send in.

     The call feed is the one piece the backend does not aggregate: turns are
     booked per account (backend/data/turn_ledgers/<user>.jsonl) and the only
     read route is /api/admin/user/{u}/ledger. So the console merges the
     per-account ledgers itself, starting with the table that was active most
     recently, and states in the panel note how many it has merged. One wave is
     8 parallel GETs and the whole set is a few thousand rows, so the feed fills
     in while the page is already painted.
     ═══════════════════════════════════════════════════════════════════════════ */

  const CALLS = { rows: [], seen: {}, loaded: {}, queue: [], next: 0, busy: false, done: false, error: '', at: 0 };
  const CALL_WAVE = 12;
  /* Action → glyph + short label. The words are the ledger's own action names. */
  const CALL_ACTIONS = {
    dm:{ g:'✦', l:'DM' }, local_dm:{ g:'⌂', l:'Local' }, guardian_pre:{ g:'⚖', l:'Guard' },
    guardian_post:{ g:'⚖', l:'Guard' }, tts:{ g:'♪', l:'Voice' }, image:{ g:'◈', l:'Image' },
    char_gen:{ g:'⚒', l:'Forge' }, logbook:{ g:'✎', l:'Log' }, search:{ g:'⌕', l:'Search' },
    extraction:{ g:'⚗', l:'Extract' }, undo:{ g:'↩', l:'Undo' }, chapter:{ g:'❧', l:'Chapter' },
    threads:{ g:'⁂', l:'Threads' }, repair:{ g:'✚', l:'Repair' }, summary:{ g:'❦', l:'Summary' },
    day_entry:{ g:'☾', l:'Day' }, battle_ai:{ g:'⚔', l:'Battle' },
  };
  function callAction(a) { return CALL_ACTIONS[a] || { g:'·', l:String(a || 'call').replace(/_/g, ' ') }; }
  function pad2(n) { return String(n).padStart(2, '0'); }
  function localDay(iso) {
    const t = new Date(iso);
    if (isNaN(t.getTime())) return '';
    return t.getFullYear() + '-' + pad2(t.getMonth() + 1) + '-' + pad2(t.getDate());
  }
  function todayKey() { return localDay(new Date().toISOString()); }
  function dayStartKey(days) {
    const n = new Date();
    const d = new Date(n.getFullYear(), n.getMonth(), n.getDate() - (days - 1));
    return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate());
  }
  function windowDays() { return { '24h':1, '7d':7, '30d':30 }[S.win] || 0; }
  function inWindow(iso, win) {
    const days = { '24h':1, '7d':7, '30d':30 }[win || S.win] || 0;
    if (!days) return true;
    const day = localDay(iso);
    return !!day && day >= dayStartKey(days);
  }
  function dayShort(day) {
    const t = new Date(day + 'T00:00:00');
    if (isNaN(t.getTime())) return day || '';
    return t.toLocaleDateString('en-GB', { day:'2-digit', month:'short' });
  }
  function dayLabelFull(day) {
    if (!day) return 'unknown day';
    const t = new Date(day + 'T00:00:00');
    if (isNaN(t.getTime())) return day;
    const y = new Date(); y.setDate(y.getDate() - 1);
    const yKey = y.getFullYear() + '-' + pad2(y.getMonth() + 1) + '-' + pad2(y.getDate());
    const mon = dayShort(day);
    if (day === todayKey()) return 'Today · ' + mon;
    if (day === yKey) return 'Yesterday · ' + mon;
    return t.toLocaleDateString('en-GB', { weekday:'short', day:'2-digit', month:'short' });
  }
  /* Local HH:MM. The day headers are local days, so the row clock has to be
     local too — printing the raw UTC slice made "3 h ago" disagree with the
     time shown two columns over. */
  function localClock(iso) {
    const t = new Date(iso);
    if (isNaN(t.getTime())) return '??:??';
    return pad2(t.getHours()) + ':' + pad2(t.getMinutes());
  }
  function modelColor(m) { return provColor(provOf(m)); }

  const USER_BY_NAME = {};
  const USER_BY_EMAIL = {};
  function indexUsers() {
    USERS().forEach(u => {
      USER_BY_NAME[u.username] = u;
      const e = String(u.email || '').trim().toLowerCase();
      if (e && !USER_BY_EMAIL[e]) USER_BY_EMAIL[e] = u.username;
    });
  }
  function isAdminUser(name) { const u = USER_BY_NAME[name]; return !!u && u.role === 'admin'; }
  function emailOwner(email) { return USER_BY_EMAIL[String(email || '').trim().toLowerCase()] || ''; }

  function ledgerUsers() {
    /* Only accounts that have ever played have a ledger file. Filtering here
       keeps the merge at ~90 GETs instead of 183, and the panel note says how
       many of the character ledgers are in. */
    return USERS()
      .filter(u => Number(u.total_turns) > 0 || u.last_active)
      .sort((a, b) => (Date.parse(b.last_active || '') || 0) - (Date.parse(a.last_active || '') || 0))
      .map(u => u.username);
  }
  function pushLedgerRows(user, entries) {
    (entries || []).forEach(e => {
      if (!e || !e.ts) return;
      const key = user + '|' + e.ts + '|' + (e.action || '');
      if (CALLS.seen[key]) return;
      CALLS.seen[key] = 1;
      CALLS.rows.push({
        user: user, ts: e.ts, action: e.action || 'call', model: e.model || '',
        bucket: e.bucket || '', pool_after: (e.pool_after == null ? null : e.pool_after),
        tokens: Number(e.tokens) || 0,
      });
    });
    CALLS.rows.sort((a, b) => String(b.ts).localeCompare(String(a.ts)));
  }
  async function callWave() {
    if (CALLS.busy) return;
    if (!CALLS.queue.length) {
      CALLS.queue = ledgerUsers();
      /* No accounts yet = the overview payload has not landed. Wait for it —
         marking the merge "done" here was why the feed stopped after one wave
         (boot renders the shell before the data arrives). */
      if (!CALLS.queue.length) return;
      CALLS.next = 0;
      CALLS.done = false;
    }
    if (CALLS.next >= CALLS.queue.length) { CALLS.done = true; return; }
    CALLS.busy = true;
    const batch = CALLS.queue.slice(CALLS.next, CALLS.next + CALL_WAVE);
    let failed = 0;
    try {
      const got = await Promise.all(batch.map(u =>
        api('/api/admin/user/' + encodeURIComponent(u) + '/ledger?limit=500')
          .then(j => [u, j.entries || []])
          .catch(() => [u, null])));
      got.forEach(pair => {
        if (pair[1] === null) { failed++; return; }
        CALLS.loaded[pair[0]] = 1;
        pushLedgerRows(pair[0], pair[1]);
      });
    } finally { CALLS.busy = false; }
    CALLS.next += batch.length;
    CALLS.at = Date.now();
    CALLS.error = failed ? failed + ' ledger' + (failed === 1 ? '' : 's') + ' could not be read' : '';
    if (CALLS.next >= CALLS.queue.length) CALLS.done = true;
    /* The heartbeat and the nav badges live outside the ledger panels, so they
       update on every wave even while another view is on screen. */
    paintBeat(); stampFooter();
    paintCalls();
    if (!CALLS.done) setTimeout(callWave, 0);
  }
  function ensureCalls(force) {
    if (force && !CALLS.busy) {
      CALLS.rows = []; CALLS.seen = {}; CALLS.loaded = {}; CALLS.queue = [];
      CALLS.next = 0; CALLS.done = false; CALLS.error = ''; CALLS.at = 0;
    }
    if (CALLS.busy) return;
    if (!force && CALLS.done && CALLS.rows.length && Date.now() - CALLS.at < 60000) return;
    callWave();
  }
  /* Progressive paint: the feed grows while the remaining ledgers arrive. A
     scheduled paint must never steal a click — the merge takes ~2s and the
     console would otherwise re-render the very node under the pointer. */
  let paintTimer = null;
  let lastPointer = 0;
  document.addEventListener('pointerdown', () => { lastPointer = Date.now(); }, true);
  function paintCalls() {
    if (S.view !== 'overview' && S.view !== 'calls') return;
    const dr = document.getElementById('drawer');
    if (dr && dr.classList.contains('on')) return;
    if (paintTimer) return;
    const sincePointer = Date.now() - lastPointer;
    paintTimer = setTimeout(() => {
      paintTimer = null;
      if (Date.now() - lastPointer < 260) { paintCalls(); return; }
      render(); stampFooter();
    }, Math.max(320, 700 - sincePointer));
  }

  /* The authoritative count of booked calls in the window: `value.by_action`
     is aggregated server-side from the same ledgers, one row per booked turn.
     The merged rows below are the detail; this is the total. */
  function callsInWindow() {
    return sum(VAL().by_action || {});
  }
  /* How much of the window the feed actually holds. The server's by_action is
     the authoritative count of booked turns; the detail route serves at most the
     newest 500 rows per character, so the feed can be a subset — say both. */
  function mergeSubtitle(rowsInWindow) {
    const loaded = Object.keys(CALLS.loaded).length;
    const total = ledgerUsers().length;
    const mergeTxt = (CALLS.done && loaded >= total)
      ? 'all ' + num(total) + ' character ledgers'
      : num(loaded) + ' of ' + num(total) + ' character ledgers so far';
    return '<b>' + num(callsInWindow()) + '</b> turns booked in this window · the feed holds the newest <b>' +
      num(rowsInWindow) + '</b> rows (500 per character · ' + mergeTxt + ')';
  }
  function callRows() {
    const q = String(S.callQ || '').trim().toLowerCase();
    return CALLS.rows.filter(r => {
      if (!inWindow(r.ts)) return false;
      if (S.callAction !== 'all' && r.action !== S.callAction) return false;
      if (S.callModel !== 'all' && (r.model || '') !== S.callModel) return false;
      if (q && String(r.user).toLowerCase().indexOf(q) < 0) return false;
      return true;
    });
  }
  function callRowHTML(r) {
    const a = callAction(r.action);
    const bucket = r.bucket || 'unknown';
    const title = localDay(r.ts) + ' ' + localClock(r.ts) + ' · ' + r.user +
      ' · ' + r.action + (r.model ? ' · ' + r.model : '') +
      (r.pool_after != null ? ' · ' + r.pool_after + ' left in the pool' : '');
    return '<button type="button" class="call-row" data-player="' + esc(r.user) + '" title="' + esc(title) + '">' +
      '<span class="ct">' + esc(localClock(r.ts)) + '</span>' +
      '<span class="cn' + (isAdminUser(r.user) ? ' admin' : '') + '">' + esc(r.user) + '</span>' +
      '<span class="ca"><i>' + a.g + '</i>' + esc(a.l) + '</span>' +
      '<span class="cm"><span class="pdot" style="background:' + modelColor(r.model) + '"></span><span class="mt">' +
        esc(r.model || 'no model') + '</span></span>' +
      /* ≤640px fäller ihop raden till två spår (tid · spelare · chevron) och
         gömmer .ca/.cm — modellen hamnade då utanför skärmen helt. .cmeta bär
         action + modell på rad två så "vilken modell" alltid syns. */
      '<span class="cmeta"><i>' + a.g + '</i>' + esc(a.l) + ' · ' + esc(r.model || 'no model') + '</span>' +
      '<span class="cp">' + (r.pool_after == null ? '—' : num(r.pool_after)) + '</span>' +
      '<span class="cb ' + esc(bucket) + '">' + esc(bucket === 'unknown' ? 'legacy' : bucket) + '</span>' +
      '<span class="cg">›</span></button>';
  }
  /* One day rule per local day. A day with no rows is absent on purpose — the
     ledger only knows days that were played. */
  function callListHTML(rows) {
    if (!rows.length) {
      return emptyState(CALLS.done ? 'No calls booked in this window' : 'Reading the turn ledgers…', '◌');
    }
    let out = '', day = '';
    rows.forEach(r => {
      const d = localDay(r.ts);
      if (d !== day) {
        day = d;
        out += '<button type="button" class="call-day" data-day="' + esc(d) + '" title="Open ' + esc(d) + '">' +
          esc(dayLabelFull(d)) + '</button>';
      }
      out += callRowHTML(r);
    });
    return '<div class="call-list">' + out + '</div>';
  }
  function emberRibbon(series) {
    const keys = Object.keys(series || {});
    if (!keys.length) return emptyState('No turns recorded in this window', '◌');
    const max = Math.max.apply(null, keys.map(k => Number(series[k]) || 0)) || 1;
    return '<div class="ribbon">' + keys.map((k, i) => {
      const v = Number(series[k]) || 0;
      const h = v ? Math.max(Math.round(v / max * 100), 3) : 0;
      const cls = (v ? '' : 'zero') + (i === keys.length - 1 ? ' now' : '');
      return '<i class="' + cls + '" style="--h:' + h + '%" data-day="' + esc(k) + '" title="' +
        esc(k + ' · ' + num(v) + ' turn' + (v === 1 ? '' : 's')) + '"></i>';
    }).join('') + '</div>';
  }
  function feedbackItems() {
    const d = S.feedback || {};
    return (d.items || d.feedback || []).slice();
  }
  function letterHTML(f) {
    const msg = String(f.message || f.text || '');
    const key = String(f.ts || msg.slice(0, 24));
    const open = !!S.fbOpen[key];
    const t = Date.parse(f.ts || '');
    const fresh = !!t && (Date.now() - t) < 7 * 864e5;
    const owner = f.email ? emailOwner(f.email) : '';
    return '<div class="letter' + (fresh ? ' fresh' : '') + (open ? '' : ' clamp') + '">' +
      '<div class="letter-head">' +
        (fresh ? '<span class="letter-fresh">new</span>' : '') +
        '<span class="letter-who">' + esc(owner || f.email || 'Anonymous') + '</span>' +
        (owner && f.email ? '<span>' + esc(f.email) + '</span>' : '') +
        '<span class="letter-when">' + esc(f.ts ? agoText(f.ts) : 'unknown time') + '</span>' +
      '</div>' +
      '<p class="letter-text">' + esc(msg) + '</p>' +
      (msg.length > 170 ? '<button type="button" class="letter-more" data-fbkey="' + esc(key) + '">' +
        (open ? 'Show less' : 'Read the whole letter') + '</button>' : '') +
      (owner ? ' <button type="button" class="letter-more" data-player="' + esc(owner) + '">Open ' + esc(owner) + '’s dossier →</button>' : '') +
    '</div>';
  }
  /* Warm tables = accounts that played inside the selected window, newest first.
     `last_active` is a real activity stamp; accounts without one are simply not
     in this list (the Players view says how many of those exist). */
  function warmPlayerList() {
    const days = windowDays();
    const cut = days ? dayStartKey(days) : '';
    return USERS()
      .filter(u => (u.role || 'player') !== 'admin')
      .filter(u => {
        if (!Date.parse(u.last_active || '')) return false;
        return cut ? localDay(u.last_active) >= cut : true;
      })
      .sort((a, b) => (Date.parse(b.last_active) || 0) - (Date.parse(a.last_active) || 0));
  }
  function callsByUser() {
    const out = {};
    CALLS.rows.forEach(r => { if (inWindow(r.ts)) out[r.user] = (out[r.user] || 0) + 1; });
    return out;
  }
  function warmTableRows() {
    const rows = warmPlayerList().slice(0, 6);
    const per = callsByUser();
    if (!rows.length) return emptyState('No table has been warm in this window', '◌');
    return '<div class="recent">' + rows.map(u =>
      '<button type="button" class="recent-row" data-player="' + esc(u.username) + '" title="Open ' + esc(u.username) + '’s dossier">' +
        codeDot(u) +
        '<span class="nm">' + esc(u.username) + '</span>' +
        '<span class="pl">' + (per[u.username] ? num(per[u.username]) + (per[u.username] === 1 ? ' call' : ' calls') : esc(poolText(u))) + '</span>' +
        poolBar(u) +
        '<span class="wh">' + esc(agoText(u.last_active)) + '</span>' +
        '<span class="go">→</span>' +
      '</button>').join('') + '</div>';
  }

  /* Column headers for the ledger — the same tracks as .call-row, so time,
     player, call, model and bucket line up as columns instead of drifting. */
  function callHeadHTML() {
    return '<div class="call-head"><span>Time</span><span>Player</span><span>Action</span>' +
      '<span>Voice</span><span class="r">Left</span><span class="r">Paid by</span><span></span></div>';
  }
  /* Where the turns are: the three buckets every account spends from. */
  function poolCardHTML() {
    const p = D().pool_totals || {};
    const items = [
      { key:'free', label:'Free quota left today', value:Number(p.free_left) || 0, color:'var(--good)' },
      { key:'paid', label:'Bought turns left', value:Number(p.paid_left) || 0, color:'var(--warn)' },
      { key:'promo', label:'Promo / legacy left', value:Number(p.promo_left) || 0, color:'var(--violet)' },
    ].filter(i => i.value > 0);
    if (!items.length) return emptyState('No turn pools recorded', '◌');
    return hbars(items, { fmt: num }) +
      '<div class="note">Free quota resets daily; bought turns never expire. ' +
      num(p.granted_known_accounts) + ' account' + (Number(p.granted_known_accounts) === 1 ? ' has' : 's have') +
      ' a fully known purchase history.</div>';
  }

  function viewOverview() {
    const v = valueStats(), t = TOT(), pool = D().pool_totals || {};
    const turnsDay = SER().turns_day || {};
    const callsDay = SER().api_calls_day || {};
    const days = Object.keys(turnsDay);
    const winTurns = Number(v.turns) || 0;
    const perDay = days.length ? Math.round(winTurns / days.length) : 0;
    const peakDay = days.slice().sort((a, b) => (Number(turnsDay[b]) || 0) - (Number(turnsDay[a]) || 0))[0] || '';
    const todayTurns = Number(turnsDay[todayKey()] || 0);
    const callsWin = sum(callsDay);
    const warm = warmPlayerList();
    const fb = feedbackItems();
    const freshFb = fb.filter(f => { const ts = Date.parse(f.ts || ''); return ts && (Date.now() - ts) < 7 * 864e5; }).length;
    const shown = Math.max(20, Number(S.callsShown) || 20);
    const feed = CALLS.rows.filter(r => inWindow(r.ts));
    const feedRows = feed.slice(0, shown);
    /* undo-voided is the refund marker the undo path writes, not a voice. */
    const models = clampList(modelItems('calls').filter(i => i.key !== 'undo-voided'), 'models', 7);
    const actions = VAL().by_action || {};
    const actionKeys = Object.keys(actions).sort((a, b) => actions[b] - actions[a]);
    const actionItems = actionKeys.map((k, i) => ({
      key: k, label: callAction(k).l, value: actions[k], color: PALETTE[i % PALETTE.length],
    }));
    const topModel = modelItems('calls')[0];
    const winLabel = { '24h':'24 hours', '7d':'7 days', '30d':'30 days', 'all':'all time' }[S.win] || S.win;
    const dayWord = S.win === '24h' ? 'today' : 'per day';
    const todayPlayers = USERS().filter(u => (u.role || 'player') !== 'admin' && localDay(u.last_active || '') === todayKey()).length;
    const voices = Object.keys(CALLS.rows.filter(r => inWindow(r.ts)).reduce((acc, r) => { if (r.model) acc[r.model] = 1; return acc; }, {})).length;

    const hero = '<section class="hero">' +
      '<div class="hero-lead">' +
        '<span class="hero-lab">Turns · ' + esc(winLabel) + '</span>' +
        '<div class="hero-num">' + num(winTurns) + '<span class="u">turns</span></div>' +
        '<div class="hero-meta">' +
          '<span><b>' + num(perDay) + '</b> ' + dayWord + '</span>' +
          (peakDay ? '<span><b>' + num(turnsDay[peakDay]) + '</b> the busiest day</span>' : '') +
          '<span><b>' + num(todayTurns) + '</b> today</span>' +
        '</div>' +
      '</div>' +
      '<div class="hero-ribbon">' +
        '<div class="ribbon-head"><span>One bar per day played</span>' +
          '<span>' + (days.length ? num(days.length) + ' days · peak <b>' + num(turnsDay[peakDay]) + '</b> on ' + esc(dayShort(peakDay)) : 'no days yet') + '</span></div>' +
        emberRibbon(turnsDay) +
        '<div class="ribbon-foot"><span>' + esc(days.length ? dayShort(days[0]) : '—') + '</span>' +
          '<span>' + esc(days.length ? dayShort(days[days.length - 1]) : '—') + '</span></div>' +
      '</div>' +
      '<div class="hero-side">' +
        '<div class="hs"><span class="hs-t">Today at the table</span><span class="hs-v">' + num(todayTurns) + ' turns</span>' +
          '<span class="hs-f">' + num(todayPlayers) + ' player' + (todayPlayers === 1 ? '' : 's') + ' seen since midnight</span></div>' +
        '<div class="hs"><span class="hs-t">Voices in play</span><span class="hs-v">' + (voices ? num(voices) + ' models' : '—') + '</span>' +
          '<span class="hs-f">distinct models booked in this window</span></div>' +
      '</div>' +
    '</section>';

    const tiles = '<div class="tiles">' +
      kpi({ t:'Model calls · ' + winLabel, v: num(callsWin), tone:'violet', drill:'usage',
            f: topModel ? 'from the transcripts · busiest voice <b>' + esc(topModel.label) + '</b>' : 'no calls logged yet' }) +
      kpi({ t:'Warm tables', v: num(warm.length), tone:'good', drill:'players',
            f: '<b>' + num(t.players) + '</b> players · <b>' + num(t.campaigns) + '</b> campaigns on the books' }) +
      kpi({ t:'Turns left in pools', v: num(pool.available), tone:'teal', drill:'pool',
            f: '<b>' + num(pool.free_left) + '</b> free today · <b>' + num(pool.paid_left) + '</b> bought' + (Number(pool.promo_left) ? ' · <b>' + num(pool.promo_left) + '</b> promo' : '') }) +
      kpi({ t:'Letters', v: num(fb.length), tone:'accent', drill:'feedback',
            f: '<b>' + num(freshFb) + '</b> in the last 7 days · click to open the inbox' }) +
    '</div>';

    /* Two editorial columns: the ledger owns the left, the human side (letters +
       narrators + pools) stacks on the right. A wrapper keeps each column's cards
       together so a short panel is not stretched into a hollow box. */
    const leftCol = '<div class="col col8">' +
      card(12, 'The ledger',
        mergeSubtitle(feed.length) + (CALLS.error ? ' · ' + esc(CALLS.error) : ''),
        callHeadHTML() + callListHTML(feedRows) +
        '<div class="call-more">' +
          (feed.length > feedRows.length ? '<button class="icon-btn" data-more="20">Show 20 more</button>' : '') +
          (!CALLS.done ? '<span class="stamp">reading the rest of the ledgers…</span>' : '<span class="stamp">one row = one turn · each turn calls one model</span>') +
          '<span class="spacer"></span>' +
          '<button class="icon-btn" data-view="calls">The full archive →</button>' +
        '</div>') +
      card(12, 'Turns per day, by bucket',
        'free · bought · promo · legacy' + (peakDay ? ' · peak <b>' + num(turnsDay[peakDay]) + '</b> on ' + esc(dayShort(peakDay)) : '') + ' · click a day for its record',
        vchartStacked(v.bucketDay, { unit:'turns', emptyMsg:'No turns booked in this window' }), { drill:'pool' }) +
      '</div>';

    const rightCol = '<div class="col col4">' +
      card(12, 'Letters from the table',
        fb.length ? num(fb.length) + ' received · ' + num(freshFb) + ' in the last 7 days' : 'nothing yet',
        fb.length
          ? '<div class="letters">' + fb.slice(0, 3).map(letterHTML).join('') + '</div>' +
            '<div class="call-more"><span class="spacer"></span><button class="icon-btn" data-view="feedback">Open the inbox →</button></div>'
          : emptyState('No letters yet — the inbox is quiet', '✎')) +
      card(12, 'Who narrates', 'calls per model, lifetime · click a bar for its curve and the players behind it',
        hbars(models.rows, { fmt: num, click: i => 'data-model="' + esc(i.key) + '"' }) + expandBtn('models', models.hidden, 'models')) +
      card(12, 'The pools', num(pool.available) + ' turns left · <b>' + num(pool.free_left) + '</b> free today',
        poolCardHTML()) +
      '</div>';

    const grid = '<div class="grid">' + leftCol + rightCol +
      card(7, 'Warm tables', 'most recently active players in this window' + (Object.keys(callsByUser()).length ? ' · calls counted from the merged ledger' : ''),
        warmTableRows()) +
      card(5, 'What the turns buy', 'turn actions, lifetime · click a bar for the split',
        actionItems.length ? hbars(actionItems, { fmt: num, click: i => 'data-action="' + esc(i.key) + '"' })
                           : emptyState('No action split in this payload', '◌')) +
    '</div>';

    return head('Table', 'The cauldron as it is being played: turns spent, every call they booked, and what the players wrote back.',
        '<button class="icon-btn" data-view="calls">All calls →</button>') +
      banner() + hero + tiles + grid;
  }

  /* ── Calls: the full ledger, filtered and paged ──────────────────────────── */
  function callPager(page, pages, total, size) {
    const nums = [];
    const push = n => { if (nums.indexOf(n) < 0) nums.push(n); };
    if (pages > 1) {
      push(1);
      if (page > 3) nums.push('…');
      for (let n = Math.max(2, page - 1); n <= Math.min(pages - 1, page + 1); n++) push(n);
      if (page < pages - 2) nums.push('…');
      push(pages);
    }
    return '<div class="pager">' +
      '<button class="icon-btn" data-cpage="' + (page - 1) + '"' + (page <= 1 ? ' disabled' : '') + '>◀ Prev</button>' +
      nums.map(n => n === '…' ? '<span class="pager-gap">…</span>'
        : '<button class="icon-btn pager-num' + (n === page ? ' on' : '') + '" data-cpage="' + n + '">' + n + '</button>').join('') +
      '<button class="icon-btn" data-cpage="' + (page + 1) + '"' + (page >= pages ? ' disabled' : '') + '>Next ▶</button>' +
      '<span class="stamp">Page ' + page + ' of ' + pages + ' · ' + num(total) + ' calls · ' + size + ' per page</span>' +
    '</div>';
  }
  function viewCalls() {
    const rows = callRows();
    const size = Math.max(20, Number(S.callSize) || 50);
    const pages = Math.max(1, Math.ceil(rows.length / size));
    const page = Math.min(Math.max(1, Number(S.callPage) || 1), pages);
    const slice = rows.slice((page - 1) * size, page * size);
    const hours = new Array(24).fill(0);
    const daySet = {};
    rows.forEach(r => {
      const t = new Date(r.ts);
      if (!isNaN(t.getTime())) hours[t.getHours()]++;
      const d = localDay(r.ts);
      if (d) daySet[d] = 1;
    });
    const hmax = Math.max.apply(null, hours) || 1;
    const busiest = hours.indexOf(hmax);
    /* The filter chips and the model picker count the whole window (not the
       filtered list), so choosing a model never makes the actions disappear. */
    const winRows = CALLS.rows.filter(r => inWindow(r.ts));
    const modelCounts = {};
    const actionCounts = {};
    winRows.forEach(r => {
      const m = r.model || '(no model)';
      modelCounts[m] = (modelCounts[m] || 0) + 1;
      actionCounts[r.action] = (actionCounts[r.action] || 0) + 1;
    });
    const modelsInLedger = Object.keys(modelCounts).sort((a, b) => modelCounts[b] - modelCounts[a]);
    const topActions = Object.keys(actionCounts).sort((a, b) => actionCounts[b] - actionCounts[a]);
    const dayCount = Object.keys(daySet).length;

    const filterBar = '<div class="filter-bar">' +
      '<div class="chip-group"><span class="chip-label">Action</span><div class="chips">' +
        chip(S.callAction === 'all', 'data-caction="all"', 'All ' + num(winRows.length)) +
        topActions.map(a => chip(S.callAction === a, 'data-caction="' + esc(a) + '"',
          callAction(a).l + ' ' + num(actionCounts[a]))).join('') +
      '</div></div>' +
      '<div class="chip-group"><span class="chip-label">Model</span>' +
        '<select class="filter-input" id="call-model">' +
          ['all'].concat(modelsInLedger).map(m => '<option value="' + esc(m) + '"' + (S.callModel === m ? ' selected' : '') + '>' +
            (m === 'all' ? 'Every model' : esc(m)) + '</option>').join('') +
        '</select></div>' +
      '<div class="chip-group"><span class="chip-label">Player</span>' +
        '<input class="filter-input" id="call-q" type="search" placeholder="name…" value="' + esc(S.callQ) + '"></div>' +
      '<span class="spacer"></span>' +
      '<span class="filter-count">' + num(rows.length) + ' calls · ' + num(dayCount) + ' day' + (dayCount === 1 ? '' : 's') + '</span>' +
      '<button class="icon-btn" data-csv="calls">⇣ CSV</button>' +
    '</div>';

    return head('Calls', 'Every turn the cauldron books, newest first: one row per turn, with the voice that turn called. Click a name for the dossier, a day for its record.',
        '<button class="icon-btn" data-view="overview">← Table</button>') +
      banner() + filterBar +
      '<div class="grid">' +
        card(8, 'The ledger',
          mergeSubtitle(rows.length) + (CALLS.done ? '' : ' · still reading…') + (CALLS.error ? ' · ' + esc(CALLS.error) : ''),
          callHeadHTML() + callListHTML(slice) + callPager(page, pages, rows.length, size) +
          '<div class="note">One row is one <b>turn</b> spent, and every turn books exactly one call — the voice column is the model that turn called. The <b>Model calls</b> tile counts call events from the transcripts instead (DM + lorekeeper + media), which is why it is larger than the turn count. The detail route serves the newest 500 rows per character and each account keeps 2,000, so the feed is the recent past, not a full history.</div>') +
        card(4, 'The clock', 'when the table is alive · calls by hour, local time' +
             (rows.length ? ' · peak <b>' + pad2(busiest) + ':00</b> with <b>' + num(hmax) + '</b> calls' : ''),
          '<div class="clock">' + hours.map((n, h) =>
            '<i style="--h:' + (n ? Math.max(Math.round(n / hmax * 100), 4) : 1) + '%" title="' +
            esc(pad2(h) + ':00 · ' + num(n) + ' call' + (n === 1 ? '' : 's')) + '"></i>').join('') + '</div>' +
          '<div class="clock-x"><span>00</span><span>06</span><span>12</span><span>18</span><span>23</span></div>' +
          '<div class="dgrid">' +
            '<div class="dstat"><span class="t">Calls</span><span class="v">' + num(rows.length) + '</span></div>' +
            '<div class="dstat"><span class="t">Busiest hour</span><span class="v">' + (rows.length ? pad2(busiest) + ':00' : '—') + '</span></div>' +
            '<div class="dstat"><span class="t">Top model</span><span class="v vsmall">' + esc(modelsInLedger[0] || '—') + '</span></div>' +
            '<div class="dstat"><span class="t">Days with calls</span><span class="v">' + num(dayCount) + '</span></div>' +
          '</div>', { cls:'side' }) +
      '</div>';
  }
  function valueGrid(v) {
    return '<div class="dgrid">' +
      '<div class="dstat"><span class="t">Money in</span><span class="v">' + sek(v.money) + '</span></div>' +
      '<div class="dstat"><span class="t">Turns delivered</span><span class="v">' + num(v.turns) + '</span></div>' +
      '<div class="dstat"><span class="t">Tokens served</span><span class="v">' + tok(v.tokens) + '</span></div>' +
      '<div class="dstat"><span class="t">AI calls</span><span class="v">' + num(v.calls) + '</span></div>' +
      '<div class="dstat"><span class="t">Tokens per kr</span><span class="v">' + tok(v.tps) + '</span></div>' +
      '<div class="dstat"><span class="t">kr per 1M tokens</span><span class="v">' + (v.kpm == null ? '—' : v.kpm.toFixed(2)) + '</span></div></div>' +
      /* Token-KPI:ns tre källor (2026-09-28). Siffran blandade förut transkript
         (daterad) med bakgrundsanrop och raderade kampanjer (livstidsräknare utan
         dag), så summan av dagsgrafen kunde aldrig matcha "tokens served". */
      (v.sources ? '<div class="sub">Tokens served · by source (lifetime)</div><div class="dgrid">' +
        '<div class="dstat"><span class="t">Dated · transcripts</span><span class="v">' + tok(v.sources.dated) + '</span></div>' +
        (Number(v.sources.background) ? '<div class="dstat"><span class="t">Background calls · no date</span><span class="v">' + tok(v.sources.background) + '</span></div>' : '') +
        (Number(v.sources.deleted) ? '<div class="dstat"><span class="t">Deleted campaigns · no date</span><span class="v">' + tok(v.sources.deleted) + '</span></div>' : '') +
        '<div class="dstat"><span class="t">Lifetime total</span><span class="v">' + tok(v.sources.lifetime) + '</span></div></div>' +
        '<div class="note">Only transcript calls carry a timestamp — background calls (summaries, extraction, Battle AI) and usage from deleted campaigns are lifetime counters with no day. The day series therefore covers the dated part only.</div>' : '');
  }

  function revenueBuckets() {
    const byDate = REV().by_date || {};
    const day = {};
    Object.keys(byDate).forEach(k => { day[k] = Number(byDate[k]) || 0; });
    if (!Object.keys(day).length) {
      // fall back to the raw ledger when the aggregate is not in the payload yet
      ledgerRows().forEach(r => { const d = String(r.ts || '').slice(0, 10); if (d) day[d] = (day[d] || 0) + (Number(r.amount_sek) || 0); });
    }
    if (S.revMode === 'day') return day;
    const out = {};
    Object.keys(day).forEach(k => {
      let key = k;
      if (S.revMode === 'month') key = k.slice(0, 7);
      else {
        const d = new Date(k + 'T00:00:00');
        d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
        key = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
      }
      out[key] = (out[key] || 0) + day[k];
    });
    return out;
  }

  function viewRevenue() {
    const r = REV(), v = valueStats();
    const products = (r.by_product || []).filter(p => (p.sek || 0) > 0).map((p, i) => ({ key:p.key, label:p.label || p.key, value:p.sek, color:PALETTE[i % PALETTE.length] }));
    const mode = S.revMode;
    const countries = (r.by_country || []).map((c, i) => ({ key:c.cc, label: ccName(c.cc), value:c.sek, color:PALETTE[i % PALETTE.length] }));
    const onlyUnknownGeo = countries.length === 1 && (countries[0].key === '??' || !countries[0].key);
    const customers = r.customers || [];
    const months = (r.by_month || []).map((m, i) => ({ key:m.key, label:m.key, value:m.sek, color:PALETTE[i % PALETTE.length] }));

    return head('Revenue', 'Straight from the billing ledger — the same rows the payment provider writes. One-time purchases only: no subscriptions, so the questions are how much, from where, and what it bought.',
        '<button class="icon-btn" data-csv="ledger">⇣ CSV</button>') +
      banner() +
      '<div class="tiles">' +
        kpi({ t:'This month · ' + (r.month_key || ''), v: sek(r.month_revenue != null ? r.month_revenue : r.month), tone:'gold', drill:'rev:month', f:'calendar month, local time' }) +
        kpi({ t:'Today', v: Number(r.today) ? sek(r.today) : '0 kr', tone:'gold', drill:'rev:today',
              f: Number(r.today) ? 'payments received since midnight' : 'nothing yet today — the ledger is flat' }) +
        kpi({ t:'Lifetime', v: sek(r.total), tone:'gold', drill:'rev:lifetime', f:'<b>' + num(r.transactions) + '</b> payments · ' + num(r.paying_customers) + ' paying accounts' }) +
        kpi({ t:'What it bought', v: num(v.turns) + ' turns', tone:'good', drill:'value', f: tok(v.tokens) + ' tokens · ' + (v.kpm == null ? '—' : v.kpm.toFixed(2) + ' kr per 1M') }) +
      '</div>' +
      '<div class="grid">' +
        card(5, 'Revenue by product', 'one-time products · click a slice',
             (products.length ? donut(products, sek(r.total), 'lifetime', { keepZero: true, click: i => 'data-product="' + esc(i.key) + '"' }) : emptyState('The ledger is quiet — the first sale lands here', '◌')) +
             '<div class="note">Products that are live but unsold stay visible here with 0 kr, so nobody has to guess which ones are actually shipping. Zero-amount ledger rows are trace events and never count as revenue.</div>') +
        card(7, 'Revenue over time', 'buckets from the ledger in local days · flat stretches are real',
             '<div class="seg" id="rev-seg">' + ['day','week','month'].map(m =>
                '<button type="button" data-rev="' + m + '" class="' + (mode === m ? 'on' : '') + '">' + m.charAt(0).toUpperCase() + m.slice(1) + '</button>').join('') + '</div>' +
             vchart(revenueBuckets(), { rev:true, alwaysLabel:true, unit:'kr', labelEvery:(k) => mode === 'month' ? k.slice(2) : dayLabel(k), emptyMsg:'No payments recorded yet' }) +
             '<div class="note">' + (Object.keys(revenueBuckets()).length < 5
                ? esc(num(r.transactions) + ' payments in ' + (r.month_key ? 'the whole life of this ledger' : 'this window') + ' — the flat stretches between the bars are real, not missing data. ')
                : '') + 'Click a bar to list the payments inside that bucket.</div>') +
        card(7, 'Revenue by country', onlyUnknownGeo
               ? 'the geo cache has not resolved a payer yet — this is the honest state, not a missing chart'
               : 'payer country from the cached geo lookup — never a live call · click a bar',
             onlyUnknownGeo
               ? emptyState('All ' + num(r.transactions) + ' ledger rows and ' + num(r.paying_customers)
                   + ' paying accounts are still unresolved in the geo cache, so every kr sits in one bucket. '
                   + 'The payer list below is the real answer until the cache fills in.', '🌍')
                 + '<div class="tbl-wrap"><table><thead><tr><th>Payer</th><th class="num">Paid</th></tr></thead><tbody>'
                 + (r.customers || []).map(c => '<tr data-player="' + esc(c.user) + '"><td><b>' + esc(c.user) + '</b></td>'
                   + '<td class="num">' + sek(c.sek) + '</td></tr>').join('')
                 + '</tbody></table></div>'
               : hbars(countries, { fmt: sek, click: i => 'data-country="' + esc(i.key) + '"', emptyMsg:'No paying customers yet' })
                 + '<div class="note">Drill into a country to see who paid and what they bought.</div>') +
        card(5, 'What the money bought', 'value delivered alongside the revenue', valueGrid(v), { drill:'value' }) +
        card(12, 'Transactions', 'every ledger row, oldest first · click a row for the raw record', ledgerTable(ledgerRows(), 'No transactions in the ledger yet')) +
        card(7, 'Customers by lifetime value', 'click a customer to open the dossier',
             customers.length ? '<div class="tbl-wrap"><table><thead><tr><th>Customer</th><th>Country</th><th class="num">Paid</th><th class="num">Payments</th><th>First</th><th>Last</th><th>Products</th></tr></thead><tbody>' +
               customers.map(c => '<tr data-player="' + esc(c.user) + '"><td><b>' + esc(c.user) + '</b></td>' +
                 '<td>' + esc(c.cc ? c.cc + ' ' + (c.country || '') : (c.country || '—')) + '</td>' +
                 '<td class="num">' + sek(c.sek) + '</td><td class="num">' + num(c.payments) + '</td>' +
                 '<td>' + esc(String(c.first_ts || '').slice(0, 10)) + '</td><td>' + esc(String(c.last_ts || '').slice(0, 10)) + '</td>' +
                 '<td>' + esc((c.products || []).map(p => String(p).replace('stripe:', '')).join(', ')) + '</td></tr>').join('') +
               '</tbody></table></div>' : emptyState('Nobody has paid yet', '◌')) +
        card(5, 'Revenue by month', 'no recurring revenue exists in this model — this replaces MRR entirely',
             hbars(months, { fmt: sek, emptyMsg:'No months with revenue yet' })) +
        card(12, 'Every product, live and legacy', 'the full catalogue with its real sales — click a row for its transactions', productTable()) +
      '</div>';
  }

  /* ── players: filter → sort → page, desktop table + mobile cards ── */
  function playerRows() {
    const q = S.q.trim().toLowerCase();
    return USERS().filter(u => {
      if (q && !((u.username || '').toLowerCase().includes(q) || (u.email || '').toLowerCase().includes(q))) return false;
      if (S.fRole !== 'all' && (u.role || 'player') !== S.fRole) return false;
      if (S.fStatus !== 'all' && (u.subscription_status || 'free') !== S.fStatus) return false;
      if (S.fCountry !== 'all' && (u.country_code || '__none__') !== S.fCountry) return false;
      /* Free/paid-koden (2026-09-28): filtreras på den SERVER-räknade koden, så
         filtret aldrig kan glida ifrån etiketten i kolumnen. */
      if (S.fCode !== 'all' && (codeOf(u) || '__none__') !== S.fCode) return false;
      return true;
    });
  }
  function sortVal(u, key) {
    switch (key) {
      case 'username': return (u.username || '').toLowerCase();
      case 'role': return u.role || 'player';
      case 'email': return (u.email || '').toLowerCase();
      case 'country': return u.country || 'zz';
      case 'subscription_status': return u.subscription_status || 'free';
      case 'last_active': case 'created_at': return Date.parse(u[key] || '') || 0;
      case 'revenue': return Number(u.revenue) || 0;
      case 'total_campaigns': return Number(u.total_campaigns) || 0;
      case 'total_tokens': return Number(u.total_tokens) || 0;
      case 'total_turns': return Number(u.total_turns) || 0;
      case 'coding': return CODE_RANK[codeOf(u) || '__none__'] != null ? CODE_RANK[codeOf(u) || '__none__'] : 0;
      /* Pott-sortering: ∞ (unlimited) sorteras högst — annars vore "unlimited"
         samma som "tom pott" i en lista. */
      case 'pool_left': {
        const tp = poolOf(u);
        if (!tp) return -2;
        if (tp.unlimited) return Number.MAX_SAFE_INTEGER;
        return Number(tp.available) || 0;
      }
      case 'pool_used': {
        const l = (poolOf(u) || {}).used_lifetime || {};
        return (Number(l.free) || 0) + (Number(l.promo) || 0) + (Number(l.paid) || 0);
      }
      default: return 0;
    }
  }
  const CODE_RANK = { paid: 3, granted: 2, free: 1, __none__: 0 };
  function sortedPlayers() {
    const rows = playerRows().slice();
    rows.sort((a, b) => {
      const x = sortVal(a, S.sortKey), y = sortVal(b, S.sortKey);
      if (x === y) return (a.username || '').localeCompare(b.username || '');
      return (x < y ? -1 : 1) * (S.sortDir === 'desc' ? -1 : 1);
    });
    return rows;
  }
  function th(label, key) {
    const on = S.sortKey === key;
    const arrow = on ? (S.sortDir === 'asc' ? '▲' : '▼') : '↕';
    return '<th class="sortable' + (on ? ' active' : '') + '" data-sort="' + key + '" title="Sort by ' + esc(label) + '">' + esc(label) + ' <span class="sort-arrow">' + arrow + '</span></th>';
  }
  function viewPlayers() {
    const all = playerRows().slice().sort((a, b) => sortVal(b, S.sortKey) - sortVal(a, S.sortKey));
    const sorted = sortedPlayers();
    const pages = Math.max(1, Math.ceil(sorted.length / S.pageSize));
    if (S.page > pages) S.page = pages;
    const slice = sorted.slice((S.page - 1) * S.pageSize, S.page * S.pageSize);
    const countries = {};
    USERS().forEach(u => { const k = u.country_code || '__none__'; if (!countries[k]) countries[k] = (u.country_flag || '❓') + ' ' + (u.country || 'Unknown'); });

    return head('Players', 'The full account table: sortable, filterable, 10 per page. A row opens a dossier with usage, revenue and the admin actions.',
        '<button class="icon-btn" data-csv="players">⇣ CSV</button>') +
      banner() +
      '<div class="card span12">' +
        '<div class="create-user-form">' +
          '<span class="chip-label">New account</span>' +
          '<input id="new-user" class="filter-input" type="text" placeholder="username" autocomplete="off">' +
          '<input id="new-pass" class="filter-input" type="password" placeholder="password" autocomplete="new-password">' +
          '<select id="new-role" class="act-input"><option value="player">player</option><option value="admin">admin</option></select>' +
          '<button class="icon-btn" data-act="create">Create account</button>' +
          '<span class="note">Same endpoint as before. You type the password here — the console never stores or echoes it.</span>' +
        '</div>' +
        '<div class="filters-row">' +
          '<input id="f-q" class="filter-input" type="search" placeholder="Search username or e-mail…" value="' + esc(S.q) + '" autocomplete="off">' +
          '<div class="chip-group"><span class="chip-label">Role</span><div class="chips">' +
            [['all','All'],['player','Players'],['admin','Admins']].map(([v, l]) => chip(v === S.fRole, 'data-frole="' + v + '"', l)).join('') + '</div></div>' +
          '<div class="chip-group"><span class="chip-label">Tier</span><div class="chips">' +
            [['all','All'],['free','Free'],['tier1','Support'],['tier2','Patron'],['lifetime','Lifetime']].map(([v, l]) => chip(v === S.fStatus, 'data-fstatus="' + v + '"', l)).join('') + '</div></div>' +
          /* Free/paid-koden är en egen axel (rostad 2026-09-28): tier säger vad
             kontot är, koden säger vad det faktiskt fått turns av. */
          /* Kod-chips (2026-09-28): bara koder som faktiskt har konton visas —
             plus den som är aktivt filtrerad, så filtret aldrig försvinner under
             fingrarna. Antalet står i chipen, samma tal som ftot-raden och CSV:n. */
          '<div class="chip-group"><span class="chip-label">Code</span><div class="chips">' +
            (() => {
              const cc = { paid:0, granted:0, free:0 };
              USERS().forEach(u => { const c = codeOf(u); if (cc[c] != null) cc[c]++; });
              return [['all','All ' + num(USERS().length)]]
                .concat(['paid', 'granted', 'free'].filter(c => cc[c] > 0 || S.fCode === c).map(c => [c, CODE_LABEL[c] + ' · ' + num(cc[c])]))
                .map(([v, l]) => chip(v === S.fCode, 'data-fcode="' + v + '"', l)).join('');
            })() + '</div></div>' +
          '<div class="chip-group"><span class="chip-label">Country</span><div class="chips">' +
            [['all','All']].concat(Object.keys(countries).sort().map(k => [k, countries[k]])).map(([v, l]) => chip(v === S.fCountry, 'data-fcountry="' + esc(v) + '"', l)).join('') + '</div></div>' +
          '<button class="chip clear" data-clear="1" title="Reset all filters">✕ Clear</button>' +
          '<span class="filter-count">' + (sorted.length === USERS().length ? num(sorted.length) + ' players' : num(sorted.length) + ' of ' + num(USERS().length) + ' players') + '</span>' +
        '</div>' +
        '<div class="ftot">' +
          ftot('Accounts', num(sorted.length)) + ftot('Campaigns', num(sumRows(sorted, 'total_campaigns'))) +
          ftot('Tokens', tok(sumRows(sorted, 'total_tokens'))) + ftot('Turns', num(sumRows(sorted, 'total_turns'))) +
          ftot('Revenue', sek(sumRows(sorted, 'revenue'))) +
          /* Pott-raden (2026-09-28): samma tre koder som legenderna — räknade på
             de filtrerade raderna, så "Paid 7" i tabellen matchar chipen. */
          /* Koder utan konton visas inte (2026-09-28): en räknare som alltid står
             på 0 är en död yta, inte information. */
          ['paid', 'granted', 'free'].map(c => ({ c: c, n: sorted.filter(u => codeOf(u) === c).length }))
            .filter(x => x.n > 0).map(x => ftot(CODE_LABEL[x.c], num(x.n))).join('') +
          ftot('Turns left', num(poolSum(sorted, 'available'))) +
          (sorted.some(u => poolOf(u) && poolOf(u).unlimited) ? ftot('Unlimited', num(sorted.filter(u => poolOf(u) && poolOf(u).unlimited).length) + ' acct') : '') +
        '</div>' +
        '<div class="table-scroll"><div class="table-wrap"><table class="player-table"><thead><tr>' +
          th('User','username') + th('Role','role') + th('Code','coding') + th('Tier','subscription_status') + th('Country','country') +
          th('Campaigns','total_campaigns') + th('Tokens','total_tokens') + th('Turns','total_turns') +
          th('Turns left','pool_left') + th('Spent','pool_used') +
          th('Revenue','revenue') + th('Last active','last_active') + '<th></th>' +
        '</tr></thead><tbody>' +
        (slice.length ? slice.map(u => playerRow(u)).join('') : '<tr><td colspan="13">' + emptyState('No players match the current filters', '◌') + '</td></tr>') +
        '</tbody></table></div><div class="table-fade"></div><div class="table-scroll-hint">→ scroll for more</div></div>' +
        '<div class="pager" id="pager">' + pagerHtml(S.page, pages, sorted.length) + '</div>' +
        '<div class="mobile-cards">' + (slice.length ? slice.map(mobCard).join('') : emptyState('No players match the current filters', '◌')) + '</div>' +
      '</div>';
  }
  function chip(on, attr, label) { return '<button type="button" class="chip' + (on ? ' on' : '') + '" ' + attr + '>' + esc(label) + '</button>'; }
  function ftot(k, v) { return '<span>' + esc(k) + ' <b>' + v + '</b></span>'; }
  /* Summerar ett pott-fält över rader. Oändliga konton (cap 0) räknas som 0 —
     de har ingen ändlig pott att summera, och "∞ + 464" går inte att visa. */
  function poolSum(rows, field) {
    return rows.reduce((a, u) => {
      const tp = poolOf(u);
      if (!tp || tp.unlimited) return a;
      return a + (Number(tp[field]) || 0);
    }, 0);
  }
  function playerRow(u) {
    const tp = poolOf(u);
    const life = (tp || {}).used_lifetime || {};
    const spent = poolUsedTotal(u);
    return '<tr data-player="' + esc(u.username) + '">' +
      '<td><b>' + esc(u.username) + '</b></td>' +
      '<td><span class="tag">' + esc(u.role || 'player') + '</span></td>' +
      '<td>' + codeTag(u) + '</td>' +
      '<td>' + tierTag(u.subscription_status) + '</td>' +
      '<td>' + esc((u.country_flag || '') + ' ' + (u.country || 'Unknown')) + '</td>' +
      '<td class="num">' + num(u.total_campaigns) + '</td>' +
      '<td class="num">' + tok(u.total_tokens) + '</td>' +
      '<td class="num">' + num(u.total_turns) + '</td>' +
      (tp
        ? '<td class="pool-cell"><button type="button" class="pool-hit" data-pool="' + esc(u.username) + '" title="' + esc('Turn pool: ' + poolText(u) + ' — click for the full breakdown') + '">' +
            '<span class="pool-txt">' + poolLines(u).map(l => '<span class="ln">' + esc(l) + '</span>').join('') + '</span>' + poolBar(u) + '</button></td>'
        : '<td class="pool-cell">' + emptyState('no pool in payload', '') + '</td>') +
      '<td class="num" title="' + esc('Lifetime turns consumed: ' + num(Number(life.free) || 0) + ' free · ' + num(Number(life.promo) || 0) + ' promo · ' + num(Number(life.paid) || 0) + ' bought · ' + num(Number(life.unknown) || 0) + ' legacy (bucket unknown)') + '">' + (spent ? num(spent) : '—') + '</td>' +
      '<td class="num">' + (u.revenue ? '<span class="tag paid">' + sek(u.revenue) + '</span>' : '—') + '</td>' +
      '<td>' + esc(String(u.last_active || '').slice(0, 10) || '—') + '</td>' +
      '<td><button class="icon-btn" data-player="' + esc(u.username) + '">open →</button></td></tr>';
  }
  function mobCard(u) {
    const tp = poolOf(u);
    const life = (tp || {}).used_lifetime || {};
    const spent = poolUsedTotal(u);
    return '<div class="mobile-card" data-player="' + esc(u.username) + '">' +
      '<div class="mc-head"><b>' + esc(u.username) + '</b>' + codeTag(u) + tierTag(u.subscription_status) + '</div>' +
      '<div class="mc-grid"><span>' + tok(u.total_tokens) + ' tokens</span><span>' + num(u.total_turns) + ' turns</span>' +
      '<span>' + num(u.total_campaigns) + ' campaigns</span><span>' + (u.revenue ? sek(u.revenue) : 'never paid') + '</span></div>' +
      (tp ? '<div class="mc-pool"><span class="pl">' + esc(poolText(u)) + '</span>' + poolBar(u) +
        /* Samma radvisa pottdetaljer som tabellen (2026-09-28) — mobilen ska säga
           exakt samma sak som desktop-kolumnen, inte en tunnare version. */
        '<span class="pool-txt">' + poolLines(u).map(l => '<span class="ln">' + esc(l) + '</span>').join('') + '</span>' +
        '<span class="sp">' + (spent ? num(spent) + ' used in total' + (Number(life.paid) ? ' (' + num(life.paid) + ' bought)' : '') : 'nothing used yet') + '</span></div>' : '') +
      '<div class="mc-foot">' + (Date.parse(u.last_active || '')
        ? esc(String(u.last_active).slice(0, 10)) + ' · ' + esc(agoText(u.last_active))
        : 'never active') + ' · ' + esc(u.country || '') + '</div></div>';
  }
  function pagerHtml(page, pages, total) {
    if (pages <= 1) return '<span class="stamp">' + num(total) + ' players</span>';
    const nums = [];
    if (pages <= 7) { for (let i = 1; i <= pages; i++) nums.push(i); }
    else {
      nums.push(1);
      const a = Math.max(2, page - 1), b = Math.min(pages - 1, page + 1);
      if (a > 2) nums.push('…');
      for (let i = a; i <= b; i++) nums.push(i);
      if (b < pages - 1) nums.push('…');
      nums.push(pages);
    }
    return '<button class="icon-btn" data-page="' + (page - 1) + '"' + (page === 1 ? ' disabled' : '') + '>◀ Prev</button>' +
      nums.map(n => n === '…' ? '<span class="pager-gap">…</span>'
        : '<button class="icon-btn pager-num' + (n === page ? ' on' : '') + '" data-page="' + n + '">' + n + '</button>').join('') +
      '<button class="icon-btn" data-page="' + (page + 1) + '"' + (page === pages ? ' disabled' : '') + '>Next ▶</button>' +
      '<span class="stamp">Page ' + page + ' of ' + pages + ' · ' + num(total) + ' players</span>';
  }

  function viewUsage() {
    const metric = S.metric;
    const models = modelItems(metric);
    return head('Usage', 'Which models actually get called and what they cost in tokens. Unlabelled rows are older transcript entries without a model tag — kept visible on purpose rather than hidden.',
        '<div class="seg">' + ['calls','tokens'].map(m => '<button type="button" data-metric="' + m + '" class="' + (metric === m ? 'on' : '') + '">' + m.charAt(0).toUpperCase() + m.slice(1) + '</button>').join('') + '</div>' +
        '<button class="icon-btn" data-csv="usage">⇣ CSV</button>') +
      banner() +
      '<div class="grid">' +
        card(7, 'Models by ' + metric, 'click a bar for that model’s daily curve and the players who called it',
             hbars(models, { fmt: metric === 'tokens' ? tok : num, click: i => 'data-model="' + esc(i.key) + '"' })) +
        card(5, 'Calls by provider', num(sum(USAGE().providers ? Object.keys(USAGE().providers).reduce((a, k) => { a[k] = USAGE().providers[k].calls; return a; }, {}) : {})) + ' logged calls, lifetime · click a slice for its models',
             donut(providerItems(), num(providerItems().reduce((a, i) => a + i.value, 0)), 'calls', { click: i => 'data-provider="' + esc(i.key) + '"' })) +
        card(6, 'Token share by provider', 'lifetime tokens, including the unlabelled bucket · click a slice for its models',
             donut(tokenSplitItems(), tok(TOT().tokens), 'tokens', { click: i => 'data-provider="' + esc(i.key) + '"' })) +
        card(6, 'Calls per day', 'window ' + S.win, vchart(SER().api_calls_day || {}, { unit:'calls' })) +
      '</div>';
  }

  function fbWindowMs(r) { return { '24h': 864e5, '7d': 6048e5, '30d': 2592e6, 'all': 0 }[r] || 0; }
  function fbItems() {
    const data = S.feedback || {};
    const rows = data.items || data.feedback || [];
    const ms = fbWindowMs(S.fbRange);
    return rows.filter(f => {
      if (ms) { const t = f.ts ? Date.parse(f.ts) : NaN; if (isNaN(t) || (Date.now() - t) > ms) return false; }
      if (S.fbMail === 'with' && !f.email) return false;
      if (S.fbMail === 'without' && f.email) return false;
      return true;
    });
  }
  function viewFeedback() {
    const rows = fbItems();
    const fresh = rows.filter(f => { const t = Date.parse(f.ts || ''); return t && (Date.now() - t) < 7 * 864e5; }).length;
    const withMail = rows.filter(f => f.email).length;
    return head('Feedback', rows.length
          ? 'Every letter players have written in, newest first. A letter with a recognised e-mail opens that account’s dossier; anonymous letters stay read-only.'
          : 'Every letter players have written in. No messages yet — nothing to open.',
        '<button class="icon-btn" data-csv="feedback">⇣ CSV</button>') +
      banner() +
      '<div class="filter-bar">' +
        '<div class="chip-group"><span class="chip-label">Window</span><div class="chips">' +
          [['all','All'],['24h','24h'],['7d','7 days'],['30d','30 days']].map(([v, l]) => chip(v === S.fbRange, 'data-fbrange="' + v + '"', l)).join('') + '</div></div>' +
        '<div class="chip-group"><span class="chip-label">Sender</span><div class="chips">' +
          [['all','All'],['with','Has e-mail'],['without','Anonymous']].map(([v, l]) => chip(v === S.fbMail, 'data-fbmail="' + v + '"', l)).join('') + '</div></div>' +
        '<span class="spacer"></span>' +
        '<span class="filter-count">' + num(rows.length) + ' letters · ' + num(fresh) + ' new · ' + num(withMail) + ' with a reply address</span>' +
      '</div>' +
      '<div class="grid"><div class="card span12">' +
        '<h3>Every letter</h3>' +
        '<div class="sub">' + (rows.length ? 'oldest at the bottom · click a letter to read it whole' : 'the inbox is quiet') + '</div>' +
        (rows.length ? '<div class="letters">' + rows.map(letterHTML).join('') + '</div>'
                     : emptyState('No feedback yet — the inbox is quiet', '✎')) +
      '</div></div>';
  }

  function viewSystem() {
    const t = TOT();
    return head('System', 'What this console reads, and what it deliberately leaves to Umami.', '') +
      banner() +
      '<div class="grid">' +
        card(7, 'Data sources', 'every number on this page is computed from these',
          hbars([
            { key:'campaigns', label:'campaign transcripts (tokens, calls, turns)', value: Number(t.campaigns) || 0, color:'var(--accent)' },
            { key:'accounts', label:'account records (tiers, caps, activity)', value: Number(t.accounts) || 0, color:'var(--teal)' },
            { key:'ledger', label:'billing ledger rows (revenue)', value: ledgerRows().length, color:'var(--gold)' },
            { key:'calls', label:'turn-ledger rows merged into the call feed', value: CALLS.rows.length, color:'var(--violet)' },
            { key:'feedback', label:'letters in the feedback inbox', value: feedbackItems().length, color:'var(--warn)' },
          ], { fmt: num }) +
          '<div class="note">Turn counts come from the per-user turn ledgers, token counts from transcript metadata, money from the billing ledger. Nothing is estimated on the client. Page traffic is measured by Umami (analytics.rostad.cc) and is not part of this console any more.</div>') +
        card(5, 'Endpoints', 'read-only unless you use an action button',
          '<div class="tbl-wrap"><table><thead><tr><th>Endpoint</th><th>Used for</th></tr></thead><tbody>' +
          [['/api/admin/overview', 'turns, series, accounts (windowed)'],
           ['/api/admin/user/{u}/ledger', 'the call feed — merged across accounts'],
           ['/api/admin/user/{u}', 'player dossier'],
           ['/api/admin/model/{model}', 'model curve + who called it'],
           ['/api/admin/billing', 'ledger + customers'],
           ['/api/admin/feedback', 'the letters']].map(r => '<tr><td><code>' + esc(r[0]) + '</code></td><td>' + esc(r[1]) + '</td></tr>').join('') +
          '</tbody></table></div>' +
          '<div class="note">The call feed costs one GET per account ledger (8 at a time, cached for a minute in the tab). The model drawer is the only panel that fetches on demand — it scans the transcripts for one model.</div>' +
          '<div class="acts"><a class="icon-btn" href="chat.html">↩ Open the game</a><button class="icon-btn" id="logout-btn">Log out</button></div>') +
      '</div>';
  }

  function head(title, sub, right) {
    return '<div class="view-head"><div><h1>' + esc(title) + '</h1><p>' + sub + '</p></div><div class="spacer"></div>' + (right || '') + '</div>';
  }
  function banner() {
    if (!S.degraded) return '';
    return '<div class="mock-note"><b>Reduced data.</b> /api/admin/overview did not answer, so this view is assembled from the older endpoints — some panels stay empty until the new aggregate is live.</div>';
  }

  /* ────────────────────────────── drawer ────────────────────────────── */
  /* ── drawer ──
     Varje drawer bär ett STATE ({d, k, t}) som hamnar i hashen
     (#traffic?w=30d&d=referrer&k=Reddit) → djup­länkbar, Back-knappen stänger,
     och en omladdning landar i samma drawer (2026-09-27). */
  function openDrawer(kind, title, html, state) {
    const wasOpen = !!S.drawerState;
    const changed = !S.drawerState || S.drawerState.d !== (state && state.d) || S.drawerState.k !== (state && state.k) || S.drawerState.t !== (state && state.t);
    S.drawerState = state || null;
    $('#dkind').textContent = kind;
    $('#dtitle').textContent = title;
    $('#dbody').innerHTML = html;
    const dr = $('#drawer');
    dr.classList.add('on');
    dr.setAttribute('aria-hidden', 'false');
    $('#scrim').classList.add('on');
    /* En historikpost per drawer-SESSION, inte per steg: öppnar man en ny drawer
       inifrån en öppen drawer (spelare → modell → …) skrivs samma post om i
       stället för att staplas. Då leder Back/Esc alltid UT ur drawer-lagret
       tillbaka till vyn — inte till föregående drawer (2026-09-27). */
    let pushed = false;
    if (changed && wasOpen) { syncHash(false, true); }
    else if (changed) { pushed = syncHash(true, true); S.drawerPushed = pushed; }
    else { syncHash(false, true); }
    const close = $('#dbody [data-close]');
    if (close) close.focus();
  }
  function closeDrawer(opts) {
    opts = opts || {};
    const was = !!S.drawerState;
    const pushed = !!S.drawerPushed;
    S.drawerState = null;
    S.drawerPushed = false;
    const dr = $('#drawer');
    if (dr) { dr.classList.remove('on'); dr.setAttribute('aria-hidden', 'true'); }
    const scrim = $('#scrim');
    if (scrim) scrim.classList.remove('on');
    $('#dkind').textContent = '';
    $('#dtitle').textContent = '';
    $('#dbody').innerHTML = '';
    $$('#view .row-active').forEach(el => el.classList.remove('row-active'));
    /* Esc stänger samma väg som webbläsarens Back — men bara om vi SJÄLVA
       lade en historikpost (en djup­länk har ingen att gå tillbaka till, och
       Back skulle då lämna admin-sidan). */
    if (!opts.fromPop && was) {
      if (pushed) history.back();
      else syncHash(false, true);
    }
    if (was && lastTrigger && lastTrigger.focus) { try { lastTrigger.focus(); } catch (e) {} }
    lastTrigger = null;
  }
  function ledgerFor(pred) { return ledgerRows().filter(pred); }
  function drawerRevenue(kind) {
    const r = REV();
    let rows = ledgerRows(), label = 'Lifetime';
    if (kind === 'today') { const today = new Date().toISOString().slice(0, 10); rows = ledgerFor(x => String(x.ts || '').slice(0, 10) === today); label = 'Today'; }
    else if (kind === 'month') { const mk = r.month_key || new Date().toISOString().slice(0, 7); rows = ledgerFor(x => String(x.ts || '').slice(0, 7) === mk); label = 'This month · ' + mk; }
    if (kind === 'lifetime') rows = ledgerFor(() => true);
    const total = rows.reduce((a, x) => a + (Number(x.amount_sek) || 0), 0);
    openDrawer('revenue · ' + kind, sek(total),
      '<div class="dgrid"><div class="dstat"><span class="t">Rows</span><span class="v">' + num(rows.length) + '</span></div>' +
      '<div class="dstat"><span class="t">Paying accounts</span><span class="v">' + num(new Set(rows.filter(x => (x.amount_sek || 0) > 0).map(x => x.user)).size) + '</span></div>' +
      '<div class="dstat"><span class="t">Window</span><span class="v">' + esc(label) + '</span></div>' +
      '<div class="dstat"><span class="t">Share of lifetime</span><span class="v">' + pct(total, Number(r.total) || 0) + '</span></div></div>' +
      ledgerTable(rows) +
      '<div class="note">Source: the billing ledger, aggregated server-side. This console never adds money up on the client.</div>',
      { d: 'revenue', k: kind });
  }
  function drawerProduct(key) {
    const p = (REV().by_product || []).find(x => x.key === key) || { key: key, label: key, sek: 0, count: 0 };
    const rows = ledgerFor(x => String(x.type || '').replace('stripe:', '') === key);
    openDrawer('revenue · product', p.label || key,
      '<div class="dgrid"><div class="dstat"><span class="t">Revenue</span><span class="v">' + sek(p.sek) + '</span></div>' +
      '<div class="dstat"><span class="t">Payments</span><span class="v">' + num(p.count) + '</span></div>' +
      '<div class="dstat"><span class="t">Share of lifetime</span><span class="v">' + pct(p.sek, Number(REV().total) || 0) + '</span></div>' +
      '<div class="dstat"><span class="t">Status</span><span class="v">' + (p.live === false ? 'legacy' : 'live') + '</span></div></div>' +
      (rows.length ? ledgerTable(rows) : emptyState('No payments recorded for this product yet — it is live, just unused', '◌')) +
      '<div class="note">Products are one-time purchases. Nothing here renews.</div>',
      { d: 'product', k: key });
  }
  function productTable() {
    const rows = REV().by_product || [];
    if (!rows.length) return emptyState('No products in the ledger yet', '◌');
    const total = Number(REV().total) || 0;
    return '<div class="tbl-wrap"><table><thead><tr><th>Product</th><th class="num">Revenue</th><th class="num">Payments</th>' +
      '<th class="num">Share</th><th>Status</th></tr></thead><tbody>' +
      rows.map(p => '<tr data-product="' + esc(p.key) + '"><td>' + esc(p.label || p.key) + '</td>' +
        '<td class="num" style="color:' + (p.sek ? 'var(--good)' : 'var(--dim-2)') + '">' + sek(p.sek) + '</td>' +
        '<td class="num">' + num(p.count) + '</td>' +
        '<td class="num">' + pct(Number(p.sek) || 0, total) + '</td>' +
        '<td><span class="tag' + (p.sek ? ' paid' : '') + '">' + (p.live === false || /legacy/i.test(p.label || '') ? 'legacy' : 'live') + '</span></td></tr>').join('') +
      '</tbody></table></div>';
  }
  function drawerCountry(cc) {
    const c = (REV().by_country || []).find(x => x.cc === cc) || { cc: cc, country: cc, sek: 0, paying: 0 };
    const rows = ledgerFor(x => payerCountry(x.user) === cc);
    openDrawer('revenue · country', ccName(cc) + ' · ' + sek(c.sek),
      '<div class="dgrid"><div class="dstat"><span class="t">Revenue</span><span class="v">' + sek(c.sek) + '</span></div>' +
      '<div class="dstat"><span class="t">Paying accounts</span><span class="v">' + num(c.paying) + '</span></div>' +
      '<div class="dstat"><span class="t">Transactions</span><span class="v">' + num(rows.length) + '</span></div>' +
      '<div class="dstat"><span class="t">Share of lifetime</span><span class="v">' + pct(c.sek, Number(REV().total) || 0) + '</span></div></div>' +
      (rows.length ? ledgerTable(rows) : emptyState('No transactions recorded for this country', '◌')) +
      '<div class="note">Country comes from the cached geo lookup of the payer\'s account — resolved in the background, never during a page load.</div>',
      { d: 'country', k: cc });
  }
  function payerCountry(user) {
    const c = (REV().by_country || []).find(x => ((x.users || x.payers) || []).indexOf(user) >= 0);
    if (c) return c.cc;
    const row = USERS().find(u => u.username === user);
    return row ? (row.country_code || '??') : '??';
  }
  function drawerBucket(bucket, value) {
    const rows = ledgerFor(x => {
      const d = String(x.ts || '').slice(0, 10);
      if (S.revMode === 'day') return d === bucket;
      if (S.revMode === 'month') return d.slice(0, 7) === bucket;
      const dt = new Date(d + 'T00:00:00'); dt.setDate(dt.getDate() - ((dt.getDay() + 6) % 7));
      const wk = dt.getFullYear() + '-' + String(dt.getMonth() + 1).padStart(2, '0') + '-' + String(dt.getDate()).padStart(2, '0');
      return wk === bucket;
    });
    openDrawer('revenue · bucket', bucket + ' · ' + sek(value),
      '<div class="dgrid"><div class="dstat"><span class="t">Revenue</span><span class="v">' + sek(value) + '</span></div>' +
      '<div class="dstat"><span class="t">Granularity</span><span class="v">' + esc(S.revMode) + '</span></div></div>' +
      (rows.length ? ledgerTable(rows) : emptyState('No payments in this bucket', '◌')),
      { d: 'bucket', k: bucket });
  }
  /* ── Usage: en modells kurva + VILKA SPELARE som anropat den ──
     Backend: /api/admin/model/{model}. Lifetimesiffrorna märks som livstid,
     fönstrade siffror märks med fönstret — ingen blandning. */
  async function drawerModel(key) {
    openDrawer('usage · model', modelLabel(key), '<div class="loading">Loading ' + esc(modelLabel(key)) + '…</div>', { d: 'model', k: key });
    let m = null;
    try { m = await api('/api/admin/model/' + encodeURIComponent(key) + '?window=' + encodeURIComponent(S.win)); }
    catch (e) { openDrawer('usage · model', modelLabel(key), '<div class="err-state">⚠ Could not load this model: ' + esc(e.message) + '</div>', { d: 'model', k: key }); return; }
    const provider = m.provider || provOf(key);
    const users = m.users || [];
    const days = m.day || {};
    const dayTotal = Object.keys(days).reduce((a, k) => a + (Number(days[k]) || 0), 0);
    const known = m.known !== false;
    S.lastModel = { key: key, data: m };
    const head = '<div class="dgrid">' +
      '<div class="dstat"><span class="t">Calls · lifetime</span><span class="v">' + num(m.calls) + '</span></div>' +
      '<div class="dstat"><span class="t">Calls · window ' + esc(S.win) + '</span><span class="v">' +
        (m.has_day_series ? num(dayTotal) : '—') + (m.has_day_series ? '' : ' <small>no dated calls</small>') + '</span></div>' +
      '<div class="dstat"><span class="t">Tokens · lifetime</span><span class="v">' + tok(m.tokens) + '</span></div>' +
      '<div class="dstat"><span class="t">Provider</span><span class="v" style="color:' + provColor(provider) + '">' + esc(provider) +
        (m.registered === false && known ? ' <small>not in the active registry</small>' : '') + '</span></div>' +
      '<div class="dstat"><span class="t">Tokens per call</span><span class="v">' + num(m.calls ? Math.round(m.tokens / m.calls) : 0) + '</span></div>' +
      '<div class="dstat"><span class="t">Accounts that called it</span><span class="v">' + num(users.length) + '</span></div></div>';
    const chart = m.has_day_series
      ? '<div class="sub">Calls per day' + (m.windowed ? ' · window ' + esc(S.win) : ' · lifetime') + '</div>' + vchart(days, { alwaysLabel:true, unit:'calls', emptyMsg:'No dated calls in this window — the lifetime totals above include undated background calls' })
      : '<div class="note">This model is called through state counters without a timestamp (TTS / image generation), so there is no per-day curve to draw. The lifetime counts above and the per-player list below are exact.</div>';
    const table = users.length
      ? '<div class="sub">Per player · who called it <button class="icon-btn" data-csvmodel="' + esc(key) + '">⇣ CSV</button></div><div class="tbl-wrap"><table class="mix-table"><thead><tr>' +
        '<th>Player</th><th>Tier</th><th class="num">Calls</th><th class="num">Tokens</th>' +
        (m.has_day_series ? '<th class="num">In window</th>' : '') + '<th>Last active</th></tr></thead><tbody>' +
        users.map(u => '<tr data-player="' + esc(u.username) + '"><td><b>' + esc(u.username) + '</b>' +
          (u.media_calls && !u.calls ? ' <span class="tag">media</span>' : '') + '</td>' +
          '<td>' + tierTag(u.subscription_status) + '</td>' +
          '<td class="num">' + num(u.calls || u.media_calls) + '</td><td class="num">' + (u.tokens ? tok(u.tokens) : '—') + '</td>' +
          (m.has_day_series ? '<td class="num">' + num(u.calls_window) + '</td>' : '') +
          '<td>' + esc(String(u.last_active || '').slice(0, 10) || '—') + '</td></tr>').join('') +
        '</tbody></table></div><div class="note">Click a player for the full dossier. Lifetime counts come from the transcripts; “in window” is counted per local day.</div>'
      : emptyState(!known ? 'This name is not in the model registry and has no calls — check the spelling'
                          : (m.registered === false ? 'This model is not in the active registry (a pinned or historical model) and has no calls in this window'
                                                    : 'No calls recorded for this model yet'), '◌');
    openDrawer('usage · model', modelLabel(key), head + chart + table +
      '<div class="note">Source: transcript <code>meta.model</code> + <code>meta.tokens</code>, attributed to a provider through the model registry. Undated background calls count in the lifetime totals but cannot be placed on a day.</div>',
      { d: 'model', k: key });
  }
  /* Provider-drawern (rostad 2026-09-30): Usage-donutens legend-knappar var
     knappar utan handler — ett klick som inte hände något. Nu: vilka modeller
     lever hos providern, deras anrop/tokens, klick → modell-drawern. */
  function drawerProvider(key) {
    const p = (USAGE().providers || {})[key] || { calls: 0, tokens: 0 };
    const models = USAGE().models || {};
    const rows = Object.keys(models).filter(m => !MODEL_SKIP[m] && (models[m].provider || provOf(m)) === key)
      .map(m => ({ m: m, calls: Number(models[m].calls || 0), tokens: Number(models[m].tokens || 0) }))
      .sort((a, b) => b.calls - a.calls);
    openDrawer('usage · provider', (PROV_LABEL[key] || key),
      '<div class="dgrid">' +
      '<div class="dstat"><span class="t">Calls · lifetime</span><span class="v">' + num(p.calls) + '</span></div>' +
      '<div class="dstat"><span class="t">Tokens · lifetime</span><span class="v">' + tok(p.tokens) + '</span></div>' +
      '<div class="dstat"><span class="t">Tokens per call</span><span class="v">' + num(p.calls ? Math.round((p.tokens || 0) / p.calls) : 0) + '</span></div>' +
      '<div class="dstat"><span class="t">Models</span><span class="v">' + num(rows.length) + '</span></div></div>' +
      (rows.length ? '<div class="sub">Models at this provider</div><div class="tbl-wrap"><table class="mix-table"><thead><tr><th>Model</th><th class="num">Calls</th><th class="num">Tokens</th><th></th></tr></thead><tbody>' +
        rows.map(r => '<tr data-model="' + esc(r.m) + '"><td><b>' + esc(modelLabel(r.m)) + '</b></td><td class="num">' + num(r.calls) + '</td><td class="num">' + tok(r.tokens) + '</td><td class="num"><button class="icon-btn" data-model="' + esc(r.m) + '">open →</button></td></tr>').join('') +
        '</tbody></table></div>' : emptyState('No models tagged to this provider in the payload', '◌')) +
      '<div class="note">Attribution is the server\'s model registry (same split as the Usage view). Click a model for its daily curve and the players who called it.</div>',
      { d: 'provider', k: key });
  }
  function drawerValue() {
    const v = valueStats();
    openDrawer('value delivered', num(v.turns) + ' turns',
      '<div class="dgrid"><div class="dstat"><span class="t">Turns (window ' + S.win + ')</span><span class="v">' + num(v.turns) + '</span></div>' +
      '<div class="dstat"><span class="t">Tokens served</span><span class="v">' + tok(v.tokens) + '</span></div>' +
      '<div class="dstat"><span class="t">Tokens per kr</span><span class="v">' + tok(v.tps) + '</span></div>' +
      '<div class="dstat"><span class="t">kr per 1M tokens</span><span class="v">' + (v.kpm == null ? '—' : v.kpm.toFixed(2)) + '</span></div></div>' +
      actionTable() +
      (SER().turns_day ? '<div class="sub">Turns delivered per day</div>' + vchart(SER().turns_day, { unit:'turns' }) : '') +
      '<div class="note">Turns are counted from the per-user turn ledgers (one row per consumed turn, with action and model). Tokens come from transcript metadata. Money comes from the billing ledger. All three are server-side counts.</div>',
      { d: 'value' });
  }
  /* Turn-actions (dm/tts/image/undo …) som en tabell — klick öppnar just den
     actionens sida av turn-ledgern i stället för den generiska värde-drawern. */
  function actionTable() {
    const acts = VAL().by_action || {};
    const keys = Object.keys(acts).sort((a, b) => acts[b] - acts[a]);
    if (!keys.length) return '';
    const total = keys.reduce((a, k) => a + (Number(acts[k]) || 0), 0) || 1;
    return '<div class="sub">What the turns bought · lifetime</div><div class="tbl-wrap"><table class="mix-table"><thead><tr>' +
      '<th>Action</th><th class="num">Turns</th><th class="num">Share</th></tr></thead><tbody>' +
      keys.map(k => '<tr data-action="' + esc(k) + '"><td><b>' + esc(String(k).replace(/_/g, ' ')) + '</b></td>' +
        '<td class="num">' + num(acts[k]) + '</td><td class="num">' + pct(acts[k], total) + '</td></tr>').join('') +
      '</tbody></table></div>';
  }
  function drawerAction(key) {
    const acts = VAL().by_action || {};
    const total = Object.keys(acts).reduce((a, k) => a + (Number(acts[k]) || 0), 0) || 1;
    const n = Number(acts[key] || 0);
    openDrawer('value · action', String(key).replace(/_/g, ' '),
      '<div class="dgrid"><div class="dstat"><span class="t">Turns</span><span class="v">' + num(n) + '</span></div>' +
      '<div class="dstat"><span class="t">Share of all turns</span><span class="v">' + pct(n, total) + '</span></div>' +
      '<div class="dstat"><span class="t">Window</span><span class="v">' + esc(S.win) + ' · lifetime counter</span></div></div>' +
      '<div class="note">One row per consumed turn in <code>backend/data/turn_ledgers/*.jsonl</code>, counted server-side. The per-player split for this action is in each dossier’s Usage tab; the raw rows are not exposed as JSON yet, so this drawer deliberately stops at the count.</div>',
      { d: 'action', k: key });
  }
  function drawerLedger(ts) {
    const row = ledgerRows().find(r => r.ts === ts) || ledgerRows()[0] || {};
    openDrawer('ledger row', String(row.type || '').replace('stripe:', '').replace('legacy:', 'legacy/'),
      '<div class="dgrid"><div class="dstat"><span class="t">Date</span><span class="v">' + esc(String(row.ts || '').slice(0, 10)) + '</span></div>' +
      '<div class="dstat"><span class="t">Amount</span><span class="v">' + sek(row.amount_sek) + '</span></div>' +
      '<div class="dstat"><span class="t">User</span><span class="v">' + esc(row.user || '') + '</span></div>' +
      '<div class="dstat"><span class="t">Raw type</span><span class="v">' + esc(row.type || '') + '</span></div></div>' +
      '<div class="note">Ledger rows are append-only. Cancellations and other trace events carry amount 0 and never count as revenue.' +
      (row.stripe_sub_id || row.event_id ? ' Reference ids: <code>' + esc(String(row.stripe_sub_id || '—')) + '</code> / <code>' + esc(String(row.event_id || '—')) + '</code>.' : '') + '</div>' +
      '<div class="acts"><button data-act="copy" data-copyref="' + esc(row.stripe_sub_id || '') + '" data-event="' + esc(row.event_id || '') + '">Copy ids</button><button data-act="who" data-player="' + esc(row.user || '') + '">Open player dossier</button></div>',
      { d: 'tx', k: ts });
  }
  /* ── Day drawer: everything the console knows about one local day ────────── */
  function drawerDay(day) {
    const rev = Number((REV().by_date || {})[day] || 0);
    const turns = Number((SER().turns_day || {})[day] || 0);
    const calls = Number((SER().api_calls_day || {})[day] || 0);
    const signups = Number((SER().signups_day || {})[day] || 0);
    /* Hinkfördelningen för dagen (2026-09-28): samma server-räknade serie som
       Table-grafen, så siffran här och stapeln där aldrig kan gå isär. */
    const split = (valueStats().bucketDay || {})[day] || null;
    /* Vilka konton skapades denna dag — gör "New accounts"-rutan till en riktig
       drilldown, inte bara en siffra. */
    const joined = USERS().filter(x => String(x.created_at || '').slice(0, 10) === day);
    /* The booked calls of this day, from the merged ledger. */
    const dayRows = CALLS.rows.filter(r => localDay(r.ts) === day);
    const perUser = {};
    dayRows.forEach(r => { perUser[r.user] = (perUser[r.user] || 0) + 1; });
    const topUsers = Object.keys(perUser).sort((a, b) => perUser[b] - perUser[a]).slice(0, 8)
      .map(k => ({ key: k, label: k, value: perUser[k], color: 'var(--accent)' }));
    openDrawer('day', dayLabelFull(day),
      '<div class="dgrid">' +
      '<div class="dstat"><span class="t">Turns booked</span><span class="v">' + num(turns) + '</span></div>' +
      '<div class="dstat"><span class="t">Calls read from transcripts</span><span class="v">' + num(calls) + '</span></div>' +
      '<div class="dstat"><span class="t">Calls in the ledger</span><span class="v">' + (CALLS.done || dayRows.length ? num(dayRows.length) : '—') + '</span></div>' +
      '<div class="dstat"><span class="t">Players at the table</span><span class="v">' + num(Object.keys(perUser).length) + '</span></div>' +
      '<div class="dstat"><span class="t">New accounts</span><span class="v">' + num(signups) + '</span></div>' +
      '<div class="dstat"><span class="t">Revenue</span><span class="v">' + (rev ? sek(rev) : '—') + '</span></div></div>' +
      (topUsers.length ? '<div class="sub">Who played this day · calls booked</div>' +
        hbars(topUsers, { fmt: num, click: i => 'data-player="' + esc(i.key) + '"' }) : '') +
      bucketSplit(split, 'this day') +
      (joined.length ? '<div class="sub">Accounts created this day</div><div class="tbl-wrap"><table class="mix-table"><thead><tr><th>Player</th><th>Role</th><th>Code</th><th>Tier</th><th>Country</th><th class="num">Turns</th></tr></thead><tbody>' +
        joined.map(x => '<tr data-player="' + esc(x.username) + '"><td><b>' + esc(x.username) + '</b></td><td>' + esc(x.role || 'player') + '</td><td>' + codeTag(x) + '</td><td>' + tierTag(x.subscription_status) + '</td><td>' + esc((x.country_flag || '') + ' ' + (x.country || 'Unknown')) + '</td><td class="num">' + num(x.total_turns) + '</td></tr>').join('') +
        '</tbody></table></div>' + '<div class="note">Click an account for the full dossier.</div>' : '') +
      (rev ? '<div class="sub">Payments this day</div>' + ledgerTable(ledgerFor(x => String(x.ts || '').slice(0, 10) === day)) : '') +
      '<div class="note">Turns and transcript calls are server-counted for this local day; the ledger rows are the calls this tab has merged so far. Page traffic for the day lives in Umami.</div>',
      { d: 'day', k: day });
  }
  /* ── turn-pott: blocket, drawern och kod-drawern (2026-09-28, rostad) ──────
     rostad: "Nu vet jag inte riktigt hur mycket en spelare köpt eller hur
     mycket som gått åt, eller det är väldigt svårtläst." Därför EN tabell som
     svarar på allt i ett svep: kvar per hink, förbrukat per hink, och noten
     som säger var gränsen för ärlig data går (pool_data_since). Talen kommer
     ur turn_pool (platt form, samma nycklar i raden som i dossién). */
  function poolBreakdown(u) {
    const tp = poolOf(u);
    if (!tp) return emptyState('No turn pool in this payload', '◌');
    const life = u && u.turn_pool && u.turn_pool.used_lifetime ? u.turn_pool.used_lifetime : (tp.used_lifetime || {});
    const unlimited = !!tp.unlimited;
    const freeLeft = Number(tp.free_left) || 0;
    const promoLeft = Number(tp.promo_left) || 0;
    const paidLeft = Number(tp.paid_left) || 0;
    const usedFree = Number(life.free) || 0;
    const usedPromo = Number(life.promo) || 0;
    const usedPaid = Number(life.paid) || 0;
    const usedUnknown = Number(life.unknown) || 0;
    const usedTotal = usedFree + usedPromo + usedPaid + usedUnknown;
    const granted = Number(tp.paid_granted) || 0;
    const known = !!tp.paid_granted_known;
    const since = tp.data_since || tp.tracked_since || '';
    const reset = tp.period_reset ? 'resets ' + esc(String(tp.period_reset)) + ' (00:00 UTC)' : 'no period reset recorded';
    const row = (what, left, used, note) => '<tr><td>' + what + '</td><td class="num">' + left + '</td><td class="num">' + used + '</td><td class="note-cell">' + note + '</td></tr>';
    return '<div class="pool-block">' +
      '<div class="pool-head">' +
        '<span class="pool-total">' + (unlimited ? '∞' : num(tp.available)) + '</span>' +
        '<span class="pool-sub">turns left' + (unlimited ? ' · unlimited account' : '') + ' · ' + esc(poolText(u)) + '</span>' +
        poolBar(u) +
      '</div>' +
      '<div class="tbl-wrap"><table class="pool-table"><thead><tr><th>Bucket</th><th class="num">Left</th><th class="num">Used</th><th>Note</th></tr></thead><tbody>' +
        row('Free quota', unlimited ? '∞' : num(freeLeft) + ' / ' + num(tp.free_cap), num(tp.free_used_period),
            unlimited ? 'this account is not capped' : reset) +
        (promoLeft || usedPromo
          ? row('Promo / legacy', num(promoLeft), num(usedPromo), 'spent before the free quota — why "0 used" never meant "played nothing"')
          : '') +
        row('Bought / granted', num(paidLeft) + (granted ? ' <span class="dim">of ' + num(granted) + '</span>' : ''), num(usedPaid),
            granted ? (known ? 'granted per the purchase log' : '<b>buy unknown before ' + esc(since || '2026-09-28') + '</b>') : (paidLeft ? '<b>buy unknown before ' + esc(since || '2026-09-28') + '</b>' : 'never bought')) +
        (usedUnknown
          ? row('Legacy / unknown', '—', num(usedUnknown),
                'played before ' + esc(since || '2026-09-28') + ' — those ledger rows carry no bucket, so they are never counted as "free"')
          : '') +
        row('<b>Total</b>', '<b>' + (unlimited ? '∞' : num(tp.available)) + '</b>', '<b>' + num(usedTotal) + '</b>',
            num(usedFree) + ' free · ' + num(usedPromo) + ' promo · ' + num(usedPaid) + ' bought' + (usedUnknown ? ' · ' + num(usedUnknown) + ' legacy' : '') + ', since tracking started') +
      '</tbody></table></div>' +
      '<div class="note">One source of truth: this table, the Players table and the CSV are all the same server-computed numbers. ' +
        (known ? '' : 'Nothing in the logs says how many turns this account bought before ' + esc(since || tp.tracked_since || '2026-09-28') + ', so "left" is exact while "bought" says unknown. ') +
        'Undo does not refund a turn, and the daily quota resets at 00:00 UTC.</div>' +
      '</div>';
  }

  function grantsTable(grants) {
    const rows = Array.isArray(grants) ? grants : [];
    if (!rows.length) return '<div class="sub">Purchases and grants</div>' + emptyState('No purchase or grant recorded for this account — anything bought before 2026-09-28 was never logged', '◌');
    const total = rows.reduce((a, r) => a + (Number(r.turns) || 0), 0);
    return '<div class="sub">Purchases and grants · ' + num(total) + ' turns in ' + num(rows.length) + ' row' + (rows.length === 1 ? '' : 's') + '</div>' +
      '<div class="tbl-wrap"><table class="mix-table"><thead><tr><th>When</th><th>Source</th><th class="num">Turns</th><th class="num">Left after</th><th>Note</th></tr></thead><tbody>' +
      rows.slice().reverse().map(r => '<tr><td>' + esc(String(r.ts || '').replace('T', ' ').slice(0, 16)) + '</td>' +
        '<td><span class="tag' + (String(r.source || '').indexOf('stripe') === 0 ? ' paid' : '') + '">' + esc(r.source || 'unknown') + '</span></td>' +
        '<td class="num">' + num(r.turns) + '</td>' +
        '<td class="num">' + (r.left_after == null ? '—' : num(r.left_after)) + '</td>' +
        '<td class="note-cell">' + esc(r.note || '') + '</td></tr>').join('') +
      '</tbody></table></div>';
  }

  function bucketSplit(bd, label) {
    if (!bd) return '';
    const order = ['free', 'paid', 'promo', 'unknown'];
    const total = order.reduce((a, k) => a + (Number(bd[k]) || 0), 0);
    if (!total) return emptyState('No turns in the ledger for ' + esc(label), '◌');
    return '<div class="sub">Which bucket paid · ' + esc(label) + '</div>' +
      hbars(order.map(k => ({ key: k, label: k === 'unknown' ? 'legacy / unknown' : k, value: Number(bd[k]) || 0, color: POOL_PART_COLOR[k === 'unknown' ? 'other' : k] }))
        .filter(i => i.value > 0), { fmt: num, unit:'turns' }) +
      '<div class="note">Rows written before 2026-09-28 carry no bucket and are counted as unknown — never guessed into "free".</div>';
  }

  /* Pott-översikten: alla konton, hur mycket som är kvar och var det tog vägen. */
  function drawerPool(username) {
    if (username) return drawerPoolFor(username);
    const pool = D().pool_totals || {};
    const codes = D().coding_summary || {};
    const rows = USERS().filter(u => poolOf(u)).slice().sort((a, b) => {
      const av = poolOf(a).unlimited ? Number.MAX_SAFE_INTEGER : (Number(poolOf(a).available) || 0);
      const bv = poolOf(b).unlimited ? Number.MAX_SAFE_INTEGER : (Number(poolOf(b).available) || 0);
      return bv - av;
    });
    const bucketDay = (valueStats().bucketDay) || {};
    openDrawer('turn pools', (Number(pool.unlimited_accounts) ? '∞ + ' : '') + num(pool.available) + ' turns left',
      '<div class="dgrid">' +
      '<div class="dstat"><span class="t">Turns left · all accounts</span><span class="v">' + num(pool.available) + '</span></div>' +
      '<div class="dstat"><span class="t">Free quota today</span><span class="v">' + num(pool.free_left) + '</span></div>' +
      (Number(pool.promo_left) ? '<div class="dstat"><span class="t">Promo / legacy</span><span class="v">' + num(pool.promo_left) + '</span></div>' : '') +
      '<div class="dstat"><span class="t">Bought / granted</span><span class="v">' + num(pool.paid_left) + '</span></div>' +
      (Number(pool.unlimited_accounts) ? '<div class="dstat"><span class="t">Unlimited accounts</span><span class="v">' + num(pool.unlimited_accounts) + '</span></div>' : '') +
      (Number(pool.granted_known_accounts) ? '<div class="dstat"><span class="t">Accounts with a real purchase log</span><span class="v">' + num(pool.granted_known_accounts) + '</span></div>' : '') +
      '<div class="dstat"><span class="t">Coding</span><span class="v">' +
        ['paid', 'granted', 'free'].filter(c => Number(codes[c]) > 0).map(c => CODE_LABEL[c] + ' ' + num(codes[c])).join(' · ') + '</span></div>' +
      '<div class="dstat"><span class="t">Turns delivered · window ' + esc(S.win) + '</span><span class="v">' + num(valueStats().turns) + '</span></div></div>' +
      '<div class="sub">Where the turns went · window ' + esc(S.win) + '</div>' + vchartStacked(bucketDay, { unit:'turns', emptyMsg:'No turn series in this payload' }) +
      '<div class="sub">Biggest pools</div>' +
      (rows.length ? '<div class="tbl-wrap"><table class="mix-table"><thead><tr><th>Player</th><th>Code</th><th>Pool</th><th class="num">Left</th><th>Last active</th></tr></thead><tbody>' +
        rows.slice(0, 20).map(u => '<tr data-player="' + esc(u.username) + '"><td><b>' + esc(u.username) + '</b></td><td>' + codeTag(u) + '</td>' +
          '<td class="pool-cell">' + esc(poolText(u)) + poolBar(u) + '</td><td class="num">' + (poolOf(u).unlimited ? '∞' : num(poolOf(u).available)) + '</td>' +
          '<td>' + esc(agoText(u.last_active)) + '</td></tr>').join('') + '</tbody></table></div>' +
        (rows.length > 20 ? '<div class="note">Showing the 20 biggest of ' + num(rows.length) + ' pools — the Players view has the full list with filters.</div>' : '')
        : emptyState('No pools in this payload', '◌')) +
      '<div class="note">Every number here is computed server-side from users.json plus the turn ledger, so the drawer, the table, the code chips and the CSV can never disagree.</div>',
      { d: 'pool' });
  }
  async function drawerPoolFor(username) {
    openDrawer('turn pool', username, '<div class="loading">Loading the pool for ' + esc(username) + '…</div>', { d: 'pool', k: username });
    let detail = null;
    try { detail = await api('/api/admin/user/' + encodeURIComponent(username)); }
    catch (e) { openDrawer('turn pool', username, '<div class="err-state">⚠ Could not load this pool: ' + esc(e.message) + '</div>', { d: 'pool', k: username }); return; }
    const tp = detail.turn_pool || {};
    const title = username + ' · ' + (tp.unlimited ? '∞' : num(tp.available)) + ' turns left';
    const codes = detail.coding || {};
    openDrawer('turn pool', title,
      '<div class="dgrid">' +
      '<div class="dstat"><span class="t">Code</span><span class="v">' + esc(CODE_LABEL[codes.code] || codes.code || '—') + '</span></div>' +
      '<div class="dstat"><span class="t">Why</span><span class="v">' + esc(codes.why || '—') + '</span></div>' +
      '<div class="dstat"><span class="t">Tier</span><span class="v">' + esc(codes.tier || '—') + '</span></div>' +
      '<div class="dstat"><span class="t">Used in total</span><span class="v">' + num(Object.keys(tp.used_lifetime || {}).reduce((a, k) => a + (Number(tp.used_lifetime[k]) || 0), 0)) + '</span></div></div>' +
      poolBreakdown(detail) +
      grantsTable(detail.turn_grants) +
      bucketSplit(detail.turn_ledger_buckets, 'all time') +
      bucketSplit(detail.turn_ledger_buckets_today, 'today') +
      '<div class="note">Open the dossier for this player to see models, campaigns and the admin actions: ' +
        '<button type="button" class="icon-btn" data-player="' + esc(username) + '">open dossier →</button></div>',
      { d: 'pool', k: username });
  }
  /* Kontona bakom en free/paid-kod. Reglerna står i noten — samma regler som
     servern räknar med, så etiketten aldrig är en gissning. */
  function drawerCode(code) {
    const label = CODE_LABEL[code] || code;
    const users = USERS().filter(u => codeOf(u) === code);
    const left = poolSum(users, 'available');
    const revenue = users.reduce((a, u) => a + (Number(u.revenue) || 0), 0);
    const rule = code === 'paid'
      ? '<b>Paid</b>: a payment row in the billing ledger, or a lifetime / patron account. These accounts have actually put money in.'
      : (code === 'granted'
        ? '<b>Granted</b>: turns beyond the free quota without a payment row — legacy promo, an admin top-up, or a hand-raised cap. Shown as its own code on purpose: 7 accounts hold 300 bonus turns with no payment row, and calling them "paid" would be a lie.'
        : '<b>Free</b>: the free daily quota only. Nothing bought, nothing granted.');
    openDrawer('players · code', label + ' · ' + num(users.length) + ' account' + (users.length === 1 ? '' : 's'),
      '<div class="dgrid">' +
      '<div class="dstat"><span class="t">Accounts</span><span class="v">' + num(users.length) + '</span></div>' +
      '<div class="dstat"><span class="t">Share of all accounts</span><span class="v">' + pct(users.length, Number(TOT().accounts) || 0) + '</span></div>' +
      '<div class="dstat"><span class="t">Turns left in these pools</span><span class="v">' + num(left) + '</span></div>' +
      '<div class="dstat"><span class="t">Revenue from these accounts</span><span class="v">' + sek(revenue) + '</span></div></div>' +
      (users.length ? '<div class="tbl-wrap"><table class="mix-table"><thead><tr><th>Player</th><th>Tier</th><th>Pool</th><th class="num">Left</th><th class="num">Spent</th><th class="num">Revenue</th><th>Last active</th></tr></thead><tbody>' +
        users.slice().sort((a, b) => (Number(b.total_turns) || 0) - (Number(a.total_turns) || 0)).slice(0, 40).map(u => {
          const spent = poolUsedTotal(u);
          return '<tr data-player="' + esc(u.username) + '"><td><b>' + esc(u.username) + '</b></td><td>' + tierTag(u.subscription_status) + '</td>' +
            '<td class="pool-cell">' + esc(poolText(u)) + poolBar(u) + '</td>' +
            '<td class="num">' + (poolOf(u) && poolOf(u).unlimited ? '∞' : num((poolOf(u) || {}).available)) + '</td>' +
            '<td class="num">' + (spent ? num(spent) : '—') + '</td>' +
            '<td class="num">' + (u.revenue ? sek(u.revenue) : '—') + '</td>' +
            '<td>' + esc(agoText(u.last_active)) + '</td></tr>';
        }).join('') + '</tbody></table></div>' +
        (users.length > 40 ? '<div class="note">Showing the 40 most active of ' + num(users.length) + ' accounts.</div>' : '')
        : emptyState('No accounts with this code', '◌')) +
      '<div class="note">' + rule + ' The code is computed server-side per request — filter the Players view by Code to see the same list with the full table and CSV export.</div>',
      { d: 'code', k: code });
  }
  async function drawerPlayer(username, tab) {
    /* Ny spelare = nytt hink-filter. Görs här och inte i drawerTab, så att
       filtervalet överlever byte av flik för samma spelare. */
    if (!S.dossier || S.dossier.username !== username) S.dossierBucket = 'all';
    openDrawer('player dossier', username, '<div class="loading">Loading ' + esc(username) + '…</div>', { d: 'player', k: username, t: tab || 'summary' });
    let detail = null, turnLedger = null;
    try { detail = await api('/api/admin/user/' + encodeURIComponent(username)); }
    catch (e) { openDrawer('player dossier', username, '<div class="err-state">⚠ Could not load this player: ' + esc(e.message) + '</div>', { d: 'player', k: username }); return; }
    try { turnLedger = await api('/api/admin/user/' + encodeURIComponent(username) + '/ledger?limit=200'); } catch (e) { turnLedger = null; }
    S.dossier = { username: username, detail: detail, ledger: turnLedger };
    return drawerTab(tab || 'summary', username, detail, turnLedger);
  }
  /* ── dossier building blocks (real keys from /api/admin/user/{u}) ── */
  const ROLE_LABEL = { assistant:'DM replies', guardian:'Guardian checks', user:'Player input', background:'Background work' };
  const ROLE_COLOR = { assistant:'#5b8cff', guardian:'#e0a24a', user:'#3fbf8f', background:'#8d9db3' };
  function roleItems(campaigns) {
    const agg = {};
    (campaigns || []).forEach(c => Object.keys(c.role_breakdown || {}).forEach(r => {
      const rb = c.role_breakdown[r] || {};
      agg[r] = (agg[r] || 0) + (Number(rb.prompt_tokens) || 0) + (Number(rb.completion_tokens) || 0);
    }));
    return Object.keys(agg).filter(r => agg[r] > 0).sort((a, b) => agg[b] - agg[a])
      .map(r => ({ key: r, label: ROLE_LABEL[r] || r, value: agg[r], color: ROLE_COLOR[r] || '#8d9db3' }));
  }
  function mixItems(mix, metric) {
    return Object.keys(mix || {}).map(m => {
      const v = mix[m] || {};
      const tokens = (Number(v.prompt_tokens) || 0) + (Number(v.completion_tokens) || 0);
      return { key: m, label: modelLabel(m), value: metric === 'tokens' ? tokens : (Number(v.calls) || 0), color: provColor(provOf(m)), tokens: tokens, calls: Number(v.calls) || 0 };
    }).sort((a, b) => b.value - a.value);
  }
  /* Spelarens egna modellistan — en RAD PER MODELL (anrop + tokens + andel),
     klickbar → modellens drawer (som visar vilka andra spelare som anropat den).
     Ersätter den kapade 8-staplars-listan (2026-09-27). */
  function modelMixTable(mix) {
    const totalCalls = mix.reduce((a, m) => a + (Number(m.calls) || 0), 0) || 1;
    const totalTokens = mix.reduce((a, m) => a + (Number(m.tokens) || 0), 0) || 1;
    return '<div class="sub">Models this player called</div><div class="tbl-wrap"><table class="mix-table"><thead><tr>' +
      '<th>Model</th><th>Provider</th><th class="num">Calls</th><th class="num">Tokens</th><th class="num">Share of calls</th></tr></thead><tbody>' +
      mix.map(m => '<tr data-model="' + esc(m.key) + '"><td><b>' + esc(m.label) + '</b></td>' +
        '<td><span style="color:' + m.color + '">' + esc(provOf(m.key)) + '</span></td>' +
        '<td class="num">' + num(m.calls) + '</td><td class="num">' + (m.tokens ? tok(m.tokens) : '—') + '</td>' +
        '<td class="num">' + pct(m.calls, totalCalls) + '</td></tr>').join('') +
      '</tbody></table></div><div class="note">Lifetime transcript counts. Click a model to see its daily curve and which other players called it (' +
      num(mix.length) + ' models, ' + tok(totalTokens) + ' tokens).</div>';
  }
  function ledgerActionItems(bd) {
    if (!bd) return [];
    const rows = Array.isArray(bd) ? bd : Object.keys(bd).map(k => ({ action: k, turns: (bd[k] && bd[k].turns != null) ? bd[k].turns : bd[k] }));
    return rows.map((r, i) => ({ key: r.action || r.key, label: String(r.action || r.key || '').replace(/_/g, ' '), value: Number(r.turns || r.value || 0), color: PALETTE[i % PALETTE.length] }))
      .filter(r => r.value > 0).sort((a, b) => b.value - a.value);
  }
  function daySeries(obj, field) {
    const d = {};
    Object.keys(obj || {}).sort().forEach(k => { d[k] = Number((obj[k] || {})[field] || 0) || 0; });
    return d;
  }
  /* Ledger-raderna bakom hinksiffran (2026-09-28). Servern skickar redan
     `entries` (senaste 200) + `by_bucket`/`by_bucket_today` i
     /api/admin/user/{u}/ledger — tidigare visades bara antalet rader. Här listas
     de, med hink-filter som bara filtrerar listan: inga nyckeltal räknas i
     klienten, siffrorna i chipen kommer från serverns `bucket`-fält per rad. */
  const LEDGER_BUCKETS = ['all', 'free', 'paid', 'promo', 'unknown'];
  function bucketOf(e) { const b = (e && e.bucket) || ''; return (b && b !== 'none') ? b : 'unknown'; }
  function ledgerBucketTable(turnLedger, filter) {
    const entries = (turnLedger && turnLedger.entries) || [];
    if (!entries.length) {
      return emptyState('No turn ledger rows for this account — the per-user ledger starts with the first turn played after it was introduced', '◌');
    }
    const active = LEDGER_BUCKETS.indexOf(filter) >= 0 ? filter : 'all';
    const counts = { all: entries.length };
    entries.forEach(e => { const b = bucketOf(e); counts[b] = (counts[b] || 0) + 1; });
    const rows = active === 'all' ? entries.slice() : entries.filter(e => bucketOf(e) === active);
    /* Ledger-filen appendas oldest→newest, så `entries` kommer i stigande tid.
       Den som öppnar Usage vill se de SENASTE anropen (och därmed den senaste
       modellen) först — slice(0,60) på den råa ordningen visade de ÄLDSTA 60
       raderna medan noten påstod "newest". Vänd före snittet. */
    const newest = rows.slice().reverse();
    const label = b => b === 'all' ? 'All' : (b === 'unknown' ? 'legacy / unknown' : b);
    return '<div class="sub">Ledger rows · ' + (active === 'all' ? 'all buckets' : esc(label(active))) +
        ' (' + num(rows.length) + ' of ' + num(entries.length) + ' loaded) · newest first</div>' +
      '<div class="chips">' + LEDGER_BUCKETS.filter(b => b === 'all' || counts[b] > 0 || active === b)
        .map(b => '<button type="button" class="chip' + (b === active ? ' on' : '') + '" data-ledgerbucket="' + b + '">' +
          esc(label(b)) + ' · ' + num(counts[b] || 0) + '</button>').join('') + '</div>' +
      '<div class="tbl-wrap"><table class="mix-table ledger-rows"><thead><tr><th>When</th><th>Action</th><th>Model</th>' +
        '<th class="num">Tokens</th><th>Bucket</th><th class="num">Pool after</th></tr></thead><tbody>' +
        newest.slice(0, 60).map(e => '<tr><td>' + esc(String(e.ts || '').replace('T', ' ').slice(0, 16)) + '</td>' +
          '<td>' + esc(e.action || '—') + '</td><td>' + esc(e.model || '—') + '</td>' +
          '<td class="num">' + (e.tokens ? num(e.tokens) : '—') + '</td>' +
          '<td>' + esc(label(bucketOf(e))) + '</td>' +
          '<td class="num">' + (e.pool_after == null ? '—' : num(e.pool_after)) + '</td></tr>').join('') +
      '</tbody></table></div>' +
      (rows.length > 60 ? '<div class="note">Showing the newest 60 of ' + num(rows.length) + ' matching rows. ' : '<div class="note">') +
      'Rows written before 2026-09-28 carry no bucket and are counted as legacy / unknown — never guessed into "free".</div>';
  }
  async function drawerTab(tab, username, detail, turnLedger) {
    detail = detail || {};
    const campaigns = detail.campaigns || [];
    const tier = detail.subscription_status || 'free';
    const revenue = Number(detail.revenue || 0);
    const dailyCalls = daySeries(detail.daily, 'calls');
    const tabs = ['summary', 'usage', 'revenue', 'campaigns'];
    const header = '<div class="tabs">' + tabs.map(t =>
      '<button type="button" data-drawer-player="' + esc(username) + '" data-tab="' + t + '" class="' + (t === tab ? 'on' : '') + '">' +
      t.charAt(0).toUpperCase() + t.slice(1) + '</button>').join('') + '</div>';
    let body = '';

    if (tab === 'summary') {
      const feat = [];
      const tts = detail.tts_usage || {};
      if (Number(tts.calls || 0) > 0) feat.push('🔊 TTS × ' + num(tts.calls) + ' · ' + num(Math.round(Number(tts.seconds) || 0)) + ' s');
      if (Number((detail.image_gen || {}).calls || 0) > 0) feat.push('🖼 Images × ' + num(detail.image_gen.calls));
      if (Number((detail.character_creation || {}).calls || 0) > 0) feat.push('🎭 Characters × ' + num(detail.character_creation.calls));
      const until = String(detail.subscription_until || '').slice(0, 10);
      body = '<div class="dgrid">' +
        '<div class="dstat"><span class="t">Tokens</span><span class="v">' + tok(detail.total_tokens) + '</span></div>' +
        '<div class="dstat"><span class="t">Turns</span><span class="v">' + num(detail.total_turns) + '</span></div>' +
        '<div class="dstat"><span class="t">Campaigns</span><span class="v">' + num(detail.total_campaigns != null ? detail.total_campaigns : campaigns.length) + '</span></div>' +
        '<div class="dstat"><span class="t">Paid lifetime</span><span class="v" style="color:' + (revenue ? 'var(--good)' : 'var(--dim)') + '">' + (revenue ? sek(revenue) : '—') + '</span></div>' +
        '<div class="dstat"><span class="t">Tier</span><span class="v">' + esc(TIER_LABEL[tier] || tier) + (until ? ' <small>to ' + esc(until) + '</small>' : '') + '</span></div>' +
        /* Turn-pott (2026-09-28): koden + potten ersätter de två gamla
           "Daily cap"/"Bonus turns"-rutorna, som visade kvarvarande tal utan att
           säga vad de hörde till (det var just den oläsligheten rostad pekade på). */
        '<div class="dstat"><span class="t">Code</span><span class="v">' + codeTag(detail) + ' <small>' + esc(codeWhy(detail) || '—') + '</small></span></div>' +
        '<div class="dstat"><span class="t">Turns left in the pool</span><span class="v">' + poolTitle(detail) + '</span></div>' +
        '<div class="dstat"><span class="t">Used in total</span><span class="v">' + num(poolUsedTotal(detail)) + ' <small>free · promo · bought</small></span></div>' +
        '<div class="dstat"><span class="t">Created</span><span class="v">' + esc(String(detail.created_at || '').slice(0, 10) || '—') + '</span></div>' +
        '<div class="dstat"><span class="t">Last active</span><span class="v">' + esc(String(detail.last_active || '').slice(0, 10) || 'never') + '</span></div>' +
        '<div class="dstat"><span class="t">Last login</span><span class="v">' + esc(String(detail.last_login || '').slice(0, 10) || '—') + '</span></div>' +
        '<div class="dstat"><span class="t">Country</span><span class="v">' + esc((detail.country_flag || '') + ' ' + (detail.country || 'unknown')) + '</span></div>' +
        '<div class="dstat"><span class="t">Role</span><span class="v">' + esc(detail.role || 'player') + '</span></div>' +
        '</div>' +
        (feat.length ? '<div class="chips feat">' + feat.map(f => '<span class="chip static">' + esc(f) + '</span>').join('') + '</div>' : '') +
        '<div class="sub">Turn pool · free vs bought</div>' + poolBreakdown(detail) +
        grantsTable(detail.turn_grants) +
        '<div class="sub">AI calls per day · ' + num(sum(dailyCalls)) + ' calls logged</div>' +
        vchart(dailyCalls, { emptyMsg:'No transcript activity for this account', unit:'calls' }) +
        adminActions(username, tier);
    } else if (tab === 'usage') {
      const roles = roleItems(campaigns);
      const mix = mixItems(detail.model_mix, 'calls');
      const actions = ledgerActionItems(turnLedger && (turnLedger.breakdown_all || turnLedger.breakdown));
      body = '<div class="dgrid">' +
          '<div class="dstat"><span class="t">Tokens</span><span class="v">' + tok(detail.total_tokens) + '</span></div>' +
          '<div class="dstat"><span class="t">Prompt</span><span class="v">' + tok(detail.prompt_tokens) + '</span></div>' +
          '<div class="dstat"><span class="t">Completion</span><span class="v">' + tok(detail.completion_tokens) + '</span></div>' +
          '<div class="dstat"><span class="t">Turns consumed</span><span class="v">' + num(turnLedger && turnLedger.entries ? turnLedger.entries.length : detail.turns_used) + '</span></div>' +
        '</div>' +
        (roles.length ? '<div class="sub">Who burns the tokens</div>' + donut(roles, tok(roles.reduce((a, r) => a + r.value, 0)), 'tokens') : '') +
        (mix.length ? modelMixTable(mix) : emptyState('No model mix recorded', '◌')) +
        bucketSplit(detail.turn_ledger_buckets, 'all time') +
        bucketSplit(detail.turn_ledger_buckets_today, 'today') +
        ledgerBucketTable(turnLedger, S.dossierBucket) +
        (actions.length ? '<div class="sub">Turn ledger actions · all ' + num(actions.length) + '</div>' + hbars(actions, { fmt: num, class:"ref-list" }) + '<div class="note">Only turns consumed since the per-user turn ledger was introduced are counted here — older turns show up in the campaign totals instead.</div>' : '');
    } else if (tab === 'revenue') {
      const hist = detail.revenue_history || [];
      body = '<div class="dgrid"><div class="dstat"><span class="t">Paid lifetime</span><span class="v" style="color:' + (revenue ? 'var(--good)' : 'var(--dim)') + '">' + sek(revenue) + '</span></div>' +
        '<div class="dstat"><span class="t">Payments</span><span class="v">' + num(hist.filter(r => (Number(r.amount_sek) || 0) > 0).length) + '</span></div>' +
        '<div class="dstat"><span class="t">Products</span><span class="v">' + esc(Array.from(new Set(hist.map(r => String(r.type || '').replace('stripe:', '')))).join(', ') || '—') + '</span></div></div>' +
        (hist.length ? ledgerTable(hist) : emptyState('This player has never paid — free tier', '◌'));
    } else {
      body = campaigns.length ? '<div class="tbl-wrap"><table><thead><tr><th>Campaign</th><th>Character</th><th class="num">Lvl</th><th>Location</th><th class="num">Turns</th><th class="num">Tokens</th><th>Updated</th></tr></thead><tbody>' +
        campaigns.map(c => '<tr><td>' + esc(c.name || c.campaign_id || '') + '</td>' +
          '<td>' + esc((c.character_icon || '') + ' ' + (c.character_name || '—')) + '</td>' +
          '<td class="num">' + num(c.level) + '</td>' +
          '<td>' + esc(c.location || '—') + '</td>' +
          '<td class="num">' + num(c.turns != null ? c.turns : c.turn_count) + '</td>' +
          '<td class="num">' + tok(c.total_tokens) + '</td>' +
          '<td>' + esc(String(c.last_updated || c.last_active || '').slice(0, 10)) + '</td></tr>').join('') + '</tbody></table></div>'
        : emptyState('No campaigns on this account', '◌');
      const del = detail.deleted_campaigns || {};
      if (Number(del.turns || 0) > 0) body += '<div class="note">Deleted campaigns: ' + num(del.turns) + ' turns · ' + tok(del.total_tokens) + ' tokens.</div>';
    }
    openDrawer('player dossier', username, header + body, { d: 'player', k: username, t: tab });
    return true;
  }
  function adminActions(username, tier) {
    const busy = window.AdminActions && AdminActions.isBusy && AdminActions.isBusy(username);
    return '<div class="acts" data-actions="' + esc(username) + '">' +
      '<input class="act-input" type="number" min="0" placeholder="cap" id="act-cap" title="Daily turn cap (0 = unlimited)">' +
      '<button data-act="cap" ' + (busy ? 'disabled' : '') + '>Set cap</button>' +
      '<input class="act-input" type="number" min="1" placeholder="+turns" id="act-topup" title="Add turn bonus">' +
      '<button data-act="topup" ' + (busy ? 'disabled' : '') + '>Add turns</button>' +
      '<span class="presets">' + [100, 300, 500].map(n =>
        '<button class="chip" data-act="topup-preset" data-n="' + n + '" title="Add ' + n + ' bonus turns">+' + n + '</button>').join('') + '</span>' +
      '<select class="act-input" id="act-tier">' + ['free','tier1','tier2','lifetime'].map(t => '<option value="' + t + '"' + (t === tier ? ' selected' : '') + '>' + (TIER_LABEL[t] || t) + '</option>').join('') + '</select>' +
      '<button data-act="tier" ' + (busy ? 'disabled' : '') + '>Set tier</button>' +
      '<select class="act-input" id="act-role">' + ['player','admin'].map(t => '<option value="' + t + '">' + t + '</option>').join('') + '</select>' +
      '<button data-act="role" ' + (busy ? 'disabled' : '') + '>Set role</button>' +
      '<button data-act="reset" ' + (busy ? 'disabled' : '') + '>Reset turns</button>' +
      '<button class="danger" data-act="delete" ' + (busy ? 'disabled' : '') + '>Delete account</button>' +
      '</div>' +
      '<div class="note">Actions hit the same endpoints as before, with the same bodies. Deleting asks once, then it is gone.</div>';
  }

  /* ────────────────────────────── data loading ────────────────────────────── */

  async function loadOverview() {
    try {
      const data = await api('/api/admin/overview?window=' + encodeURIComponent(S.win));
      S.degraded = false;
      return data;
    } catch (e) {
      if (e.status !== 404 && e.status !== 405 && e.status !== 500) throw e;
      // the new aggregate is not deployed yet — keep the console usable on the old endpoints
      const [stats, billing] = await Promise.all([api('/api/admin/stats'), api('/api/admin/billing')]);
      S.degraded = true;
      return adaptLegacy(stats, billing);
    }
  }
  function adaptLegacy(stats, billing) {
    const users = (stats.users || []).map(u => ({
      username: u.username, role: u.role, email: u.email, subscription_status: u.subscription_status,
      country: u.country, country_code: u.country_code, country_flag: u.country_flag,
      total_campaigns: u.total_campaigns, total_tokens: u.total_tokens, total_turns: u.total_turns,
      revenue: u.revenue, last_active: u.last_active, created_at: u.created_at, tier: u.subscription_status,
    }));
    const tiers = { free:0, tier1:0, tier2:0, lifetime:0 };
    users.forEach(u => { const k = u.subscription_status === 'premium' ? 'tier2' : (u.subscription_status || 'free'); if (tiers[k] != null) tiers[k] += 1; });
    const rev = billing || {};
    const byDate = {};
    (rev.ledger || []).forEach(r => { const d = String(r.ts || '').slice(0, 10); if (d) byDate[d] = (byDate[d] || 0) + (Number(r.amount_sek) || 0); });
    const customers = {};
    (rev.ledger || []).forEach(r => {
      const c = customers[r.user] = customers[r.user] || { user:r.user, sek:0, payments:0, first_ts:r.ts, last_ts:r.ts, products:[] };
      c.sek += Number(r.amount_sek) || 0; if ((r.amount_sek || 0) > 0) c.payments += 1;
      if (String(r.ts) < String(c.first_ts)) c.first_ts = r.ts;
      if (String(r.ts) > String(c.last_ts)) c.last_ts = r.ts;
      const p = String(r.type || '').replace('stripe:', ''); if (c.products.indexOf(p) < 0) c.products.push(p);
    });
    return {
      generated_at: new Date().toISOString(), window: S.win, degraded: true,
      totals: { accounts: stats.total_users, players: users.filter(u => (u.role || 'player') !== 'admin').length, admins: users.filter(u => u.role === 'admin').length,
                campaigns: stats.total_campaigns, tokens: stats.total_tokens, ai_calls: Object.values(stats.providers || {}).reduce((a, p) => a + (p.calls || 0), 0) },
      revenue: { total: rev.total || 0, mrr: rev.mrr || 0, transactions: rev.transactions || 0, month_revenue: rev.month_revenue || 0, month_key: rev.month_key || '', today: byDate[new Date().toISOString().slice(0, 10)] || 0,
                 paying_customers: Object.keys(customers).filter(u => customers[u].sek > 0).length, by_date: byDate, by_product: [], by_country: [], customers: Object.values(customers).sort((a, b) => b.sek - a.sek),
                 conversion_pct: users.length ? +(Object.keys(customers).filter(u => customers[u].sek > 0).length / users.length * 100).toFixed(1) : 0 },
      value: { turns: 0, tokens: stats.total_tokens, ai_calls: 0, tokens_per_sek: null, kr_per_1m_tokens: null },
      series: { api_calls_day: stats.api_daily ? Object.keys(stats.api_daily).reduce((a, k) => { a[k] = stats.api_daily[k].calls; return a; }, {}) : {},
                revenue_day: byDate, signups_day: {} },
      usage: { providers: stats.providers || {}, models: stats.models || {} },
      tiers: tiers, users: users, ledger: rev.ledger || [],
    };
  }

  async function load(opts) {
    if (S.loading) return;
    S.loading = true;
    const btn = $('#refresh-btn');
    if (btn) btn.textContent = '↻ …';
    try {
      S.data = await loadOverview();
      indexUsers();
      if (!S.billing) { try { S.billing = await api('/api/admin/billing'); } catch (e) { S.billing = null; } }
      if (!S.feedback) loadFeedback(false).then(() => { render(); });
      if (S.view === 'overview' || S.view === 'calls') ensureCalls(!!(opts && opts.refreshCalls));
      render();
      stampFooter();
      if (opts && opts.quiet) toast('Refreshed');
    } catch (e) {
      $('#view').innerHTML = '<div class="err-state"><h2>⚠ Could not light the console</h2><p>' + esc(e.message) + '</p>' +
        '<p class="note">If this says 403, the signed-in account has no admin role. If it says 401, the session expired.</p>' +
        '<button class="icon-btn" id="retry-btn">Try again</button> <a class="icon-btn" href="login.html">Sign in</a></div>';
      const retry = $('#retry-btn');
      if (retry) retry.addEventListener('click', () => load());
    } finally {
      S.loading = false;
      if (btn) btn.textContent = '↻ Refresh';
    }
  }
  function stampFooter() {
    const iso = D().generated_at || new Date().toISOString();
    const el = $('#stamp');
    if (el) el.textContent = 'numbers as of ' + stamp(iso);
    const nf = $('#nav-stamp');
    if (nf) nf.textContent = 'updated ' + stamp(iso);
    const nr = $('#nav-rev');
    if (nr) nr.textContent = sek(REV().total);
    const np = $('#nav-players');
    if (np) np.textContent = num(TOT().accounts);
    const nfb = $('#nav-fb');
    if (nfb) nfb.textContent = S.feedback && S.feedback.items ? num(S.feedback.items.length) : '';
    const nc = $('#nav-calls');
    if (nc) nc.textContent = D().value ? num(callsInWindow()) : '…';
    const nl = $('#nav-live');
    if (nl) {
      const newest = CALLS.rows.length ? Date.parse(CALLS.rows[0].ts || '') : 0;
      nl.textContent = newest && (Date.now() - newest) < 3600000 ? '●' : '';
      nl.title = newest ? 'last call ' + agoText(CALLS.rows[0].ts) : 'no calls booked yet';
      nl.style.color = 'var(--good)';
    }
  }

  async function loadFeedback(force) {
    if (S.feedback && !force) return;
    try { S.feedback = await api('/api/admin/feedback'); } catch (e) { S.feedback = { items: [], error: e.message }; }
  }

  /* ────────────────────────────── render + router ────────────────────────────── */
  const VIEWS = { overview: viewOverview, calls: viewCalls, players: viewPlayers, revenue: viewRevenue, usage: viewUsage, feedback: viewFeedback, system: viewSystem };

  function render() {
    $$('#nav .nav-item').forEach(b => {
      const on = b.dataset.view === S.view;
      b.classList.toggle('cur', on);
      if (on) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
    });
    $$('#win-seg button').forEach(b => b.classList.toggle('on', b.dataset.win === S.win));
    const fn = VIEWS[S.view] || viewOverview;
    $('#view').innerHTML = fn();
    wireView();
    paintBeat();
    stampFooter();
    syncHash(false, true);
  }
  /* The heartbeat in the top bar: the newest booked call and how many tables
     played in the last hour. It is derived from the merged ledger, so it is
     empty until the first wave lands — say so instead of faking "live". */
  function paintBeat() {
    const el = $('#beat-text'), box = $('#beat');
    if (!el || !box) return;
    if (!CALLS.rows.length) {
      /* Before (or without) the ledger merge the newest account stamp still
         answers "is anyone at the table?" — say "last seen", not "last call". */
      const u = USERS().filter(x => Date.parse(x.last_active || ''))
        .sort((a, b) => (Date.parse(b.last_active) || 0) - (Date.parse(a.last_active) || 0))[0];
      if (u) {
        const mins = (Date.now() - Date.parse(u.last_active)) / 60000;
        el.innerHTML = 'last seen <b>' + esc(agoText(u.last_active)) + '</b> · <b>' + esc(u.username) + '</b>';
        box.className = 'beat' + (mins <= 60 ? ' warm' : (mins > 1440 ? ' cold' : ''));
        return;
      }
      el.textContent = CALLS.done ? 'no calls booked yet' : 'reading the ledger…';
      box.className = 'beat cold';
      return;
    }
    const newest = CALLS.rows.length ? Date.parse(CALLS.rows[0].ts || '') : 0;
    if (!newest) { el.textContent = CALLS.done ? 'no calls booked yet' : 'reading the ledger…'; box.className = 'beat cold'; return; }
    const mins = Math.max(0, Math.round((Date.now() - newest) / 60000));
    const hourAgo = Date.now() - 3600000;
    const warm = CALLS.rows.filter(r => Date.parse(r.ts || '') >= hourAgo).length;
    const who = CALLS.rows[0].user;
    el.innerHTML = 'last call <b>' + esc(agoText(CALLS.rows[0].ts)) + '</b> · <b>' + esc(who) + '</b>' +
      ' · ' + (warm ? '<b>' + num(warm) + '</b> call' + (warm === 1 ? '' : 's') + ' in the last hour'
                    : 'nothing in the last hour');
    box.className = 'beat' + (mins <= 60 ? ' warm' : (mins > 60 * 24 ? ' cold' : ''));
  }
  /* ── hash-router (2026-09-27): #view?w=<win>&d=<kind>&k=<key>&t=<tab>
     Varje drilldown hamnar i URL:en → delbar, Back stänger, reload landar rätt.
     pushState används när användaren öppnar/byter (så Back går tillbaka), och
     popstate återställer exakt samma läge utan att skriva historik igen. */
  let lastTrigger = null;      // elementet som öppnade drawern (fokus tillbaka)
  let suppressHash = false;    // sant medan popstate återställer → ingen ny historik
  function buildHash() {
    const parts = ['w=' + encodeURIComponent(S.win)];
    if (S.drawerState && S.drawerState.d) {
      parts.push('d=' + encodeURIComponent(S.drawerState.d));
      if (S.drawerState.k != null) parts.push('k=' + encodeURIComponent(S.drawerState.k));
      if (S.drawerState.t) parts.push('t=' + encodeURIComponent(S.drawerState.t));
    }
    return '#' + S.view + '?' + parts.join('&');
  }
  function syncHash(push, force) {
    if (suppressHash) return false;               // popstate/boot: rör inte historiken
    const h = buildHash();
    if (h === location.hash) return false;
    try {
      if (push) { history.pushState({ h: h }, '', h); return true; }
      history.replaceState({ h: h }, '', h);
    } catch (e) { /* file:// / sandbox — djup­länkar är inte kritiska */ }
    return false;
  }
  function parseHash() {
    const raw = String(location.hash || '').replace(/^#\/?/, '');
    const [view, query] = raw.split('?');
    const q = {};
    (query || '').split('&').forEach(kv => { const i = kv.indexOf('='); if (i > 0) q[kv.slice(0, i)] = decodeURIComponent(kv.slice(i + 1)); });
    return {
      view: VIEWS[view] ? view : S.view,
      win: ['24h', '7d', '30d', 'all'].indexOf(q.w) >= 0 ? q.w : S.win,
      d: q.d || '', k: q.k || '', t: q.t || '',
    };
  }
  async function applyHash(state, opts) {
    opts = opts || {};
    const needLoad = state.win !== S.win;
    S.view = state.view;
    S.win = state.win;
    if (needLoad) await load();
    else if (!$('#view').innerHTML || VIEWS[S.view]) render();
    suppressHash = true;
    try {
      if (state.d) await openByState(state, opts);
      else if (S.drawerState) closeDrawer({ fromPop: true });
    } finally { suppressHash = false; }
  }
  /* Djup­länk → drawer. Sammma funktioner som klicken använder, så en delad
     länk visar exakt samma innehåll som ett klick gjorde. */
  async function openByState(state, opts) {
    const k = state.k;
    switch (state.d) {
      case 'revenue': return drawerRevenue(k || 'lifetime');
      case 'product': return drawerProduct(k);
      case 'country': return drawerCountry(k);
      case 'tx': return drawerLedger(k);
      case 'tier': return drawerTier(k);
      case 'bucket': return drawerBucket(k, Number((revenueBuckets() || {})[k]) || 0);
      case 'value': return drawerValue();
      case 'pool': return drawerPool(k);
      case 'code': return drawerCode(k);
      case 'action': return drawerAction(k);
      case 'model': return drawerModel(k);
      case 'provider': return drawerProvider(k);
      case 'player': return drawerPlayer(k, state.t || 'summary');
      case 'day': return drawerDay(k);
      default: return;
    }
  }
  window.addEventListener('popstate', () => {
    const st = parseHash();
    // stänger drawern först om hashen inte längre bär något state
    if (!st.d) closeDrawer({ fromPop: true });
    applyHash(st, { fromPop: true });
  });
  function wireView() {
    const q = $('#f-q');
    if (q) {
      q.addEventListener('input', () => { S.q = q.value; S.page = 1; refreshPlayersOnly(); });
    }
    /* Calls view: the player search and the model picker are the two filters
       that cannot be chips (open-ended), so they re-render on change. */
    const cq = $('#call-q');
    if (cq) {
      cq.addEventListener('input', () => {
        S.callQ = cq.value; S.callPage = 1;
        const active = document.activeElement === cq;
        const pos = active ? cq.selectionStart : null;
        if (S.view === 'calls') {
          $('#view').innerHTML = viewCalls();
          wireView();
          if (active && pos != null) { const el = $('#call-q'); if (el) { el.focus(); try { el.setSelectionRange(pos, pos); } catch (e) {} } }
        }
      });
    }
    const cm = $('#call-model');
    if (cm) cm.addEventListener('change', () => { S.callModel = cm.value; S.callPage = 1; render(); });
  }
  function refreshPlayersOnly() {
    if (S.view !== 'players') return;
    const active = document.activeElement && document.activeElement.id === 'f-q';
    const pos = active ? document.activeElement.selectionStart : null;
    $('#view').innerHTML = viewPlayers();
    wireView();
    if (active && pos != null) { const el = $('#f-q'); el.focus(); try { el.setSelectionRange(pos, pos); } catch (e) {} }
  }

  function go(view, opts) {
    S.view = view;
    if (!VIEWS[view]) S.view = 'overview';
    if (view === 'feedback') { loadFeedback(!!(opts && opts.force)).then(() => { render(); }); return; }
    if ((view === 'calls' || view === 'overview') && S.data) ensureCalls(false);
    render();
  }

  /* ────────────────────────────── events ────────────────────────────── */
  function openWith(t, fn) { lastTrigger = t; return fn(); }
  document.addEventListener('click', async function (ev) {
    const t = ev.target.closest('[data-view],[data-win],[data-metric],[data-rev],[data-expand],' +
      '[data-drill],[data-slice],[data-key],[data-tx],[data-player],[data-model],[data-action],[data-country],[data-tier],[data-day],[data-ledgerbucket],[data-csvmodel],' +
      '[data-provider],[data-caction],[data-cpage],[data-more],[data-fbkey],' +
      '[data-csv],[data-sort],[data-page],[data-frole],[data-fstatus],[data-fcountry],[data-fcode],[data-clear],[data-fbrange],[data-fbmail],[data-tab],[data-act],[data-bucket],[data-product],[data-pool],[data-code]');
    if (!t) return;
    const d = t.dataset;

    if (d.view) { go(d.view); return; }
    if (d.win) { S.win = d.win; syncHash(true, true); S.callPage = 1; S.callsShown = 20; load(); return; }
    if (d.metric) { S.metric = d.metric; render(); return; }
    if (d.caction) { S.callAction = d.caction; S.callPage = 1; render(); return; }
    if (d.cpage) { S.callPage = Math.max(1, Number(d.cpage) || 1); render(); const vw = $('#view'); if (vw && vw.scrollIntoView) vw.scrollIntoView({ block:'start' }); return; }
    if (d.more) { S.callsShown = (Number(S.callsShown) || 20) + Number(d.more); render(); return; }
    if (d.fbkey) { S.fbOpen[d.fbkey] = !S.fbOpen[d.fbkey]; render(); return; }
    if (d.rev) { S.revMode = d.rev; render(); return; }
    if (d.expand) { S.expand[d.expand] = !S.expand[d.expand]; render(); return; }
    if (d.sort) { const k = d.sort; if (S.sortKey === k) S.sortDir = S.sortDir === 'desc' ? 'asc' : 'desc'; else { S.sortKey = k; S.sortDir = 'desc'; } S.page = 1; refreshPlayersOnly(); return; }
    if (d.page) {
      S.page = Math.max(1, Number(d.page) || 1);
      render();
      const v = $('#view');
      if (v && typeof v.scrollIntoView === 'function') v.scrollIntoView({ block: 'start' });
      return;
    }
    if (d.frole) { S.fRole = d.frole; S.page = 1; render(); return; }
    if (d.fstatus) { S.fStatus = d.fstatus; S.page = 1; render(); return; }
    if (d.fcountry) { S.fCountry = d.fcountry; S.page = 1; render(); return; }
    if (d.fcode) { S.fCode = d.fcode; S.page = 1; render(); return; }
    if (d.clear) { S.q = ''; S.fRole = 'all'; S.fStatus = 'all'; S.fCountry = 'all'; S.fCode = 'all'; S.page = 1; render(); return; }
    if (d.fbrange) { S.fbRange = d.fbrange; render(); return; }
    if (d.fbmail) { S.fbMail = d.fbmail; render(); return; }
    if (d.csv) { exportCsv(d.csv); return; }
    if (d.csvmodel) { exportModelCsv(d.csvmodel); return; }
    /* Hink-filter i dossiéns ledger-tabell (2026-09-28): filtrerar bara de rader
       klienten redan har — inget nyckeltal räknas om här. */
    if (d.ledgerbucket && S.dossier && S.dossier.username) {
      S.dossierBucket = d.ledgerbucket;
      return drawerTab('usage', S.dossier.username, S.dossier.detail, S.dossier.ledger);
    }

    if (d.drill) {
      const v = d.drill;
      if (v.indexOf('rev:') === 0) return openWith(t, () => drawerRevenue(v.slice(4)));
      if (v.indexOf('day:') === 0) return openWith(t, () => drawerDay(v.slice(4)));
      if (v === 'value') return openWith(t, drawerValue);
      if (v === 'pool') return openWith(t, drawerPool);
      /* A drill that names a view simply goes there — KPI tiles link to Calls,
         Models, Players and Feedback without inventing drawer kinds. */
      if (VIEWS[v]) { S.view = v; return render(); }
      if (v === 'usage:calls' || v.indexOf('usage') === 0) { S.view = 'usage'; return render(); }
      return;
    }
    /* Donut-slices: egen data-nyckel först (data-slicekey sätts alltid av donut()),
       sedan label-texten som sista utväg. Utan nyckeln gissade vi på text. */
    if (d.slice != null && t.closest('.card')) {
      if (d.product || d.action || d.tier || d.model || d.provider) { /* faller igenom nedan */ }
      else {
        const key = d.slicekey || '';
        const item = (t.closest('.card').querySelectorAll('.legend button')[Number(d.slice)]) || null;
        const label = item ? (item.querySelector('.lb') ? item.querySelector('.lb').textContent.trim() : item.textContent.trim()) : '';
        if (key && (USAGE().models || {})[key]) return openWith(t, () => drawerModel(key));
        if (key && (TIERS()[key] != null)) return openWith(t, () => drawerTier(key));
        if (key && (VAL().by_action || {})[key] != null) return openWith(t, () => drawerAction(key));
        const product = (REV().by_product || []).find(p => p.key === key || (p.label || p.key) === label);
        const country = (REV().by_country || []).find(c => c.cc === key || c.cc === label || (c.country || '') === label);
        if (product) return openWith(t, () => drawerProduct(product.key));
        if (country) return openWith(t, () => drawerCountry(country.cc));
      }
    }
    if (d.model) return openWith(t, () => drawerModel(d.model));
    if (d.provider) return openWith(t, () => drawerProvider(d.provider));
    if (d.country) return openWith(t, () => drawerCountry(d.country));
    if (d.tier) return openWith(t, () => drawerTier(d.tier));
    /* Before data-key: bars and rows carry BOTH a key (their own label) and a
       player (the drill). Resolving key first made every player drill a no-op. */
    if (d.player) return openWith(t, () => drawerPlayer(d.player));
    if (d.action) return openWith(t, () => drawerAction(d.action));
    if (d.day) return openWith(t, () => drawerDay(d.day));
    if (d.key) {
      const k = d.key;
      if ((USAGE().models || {})[k]) return openWith(t, () => drawerModel(k));
      if ((REV().by_country || []).some(c => c.cc === k)) return openWith(t, () => drawerCountry(k));
      if ((REV().by_month || []).some(m => m.key === k)) return openWith(t, () => drawerBucket(k, (REV().by_month || []).find(m => m.key === k).sek));
      return;
    }
    if (d.product) return openWith(t, () => drawerProduct(d.product));
    if (d.tx) return openWith(t, () => drawerLedger(d.tx));
    if (d.bucket != null && t.classList.contains('vcol')) return openWith(t, () => drawerBucket(d.bucket, Number(d.val) || 0));
    /* Turn-pott (2026-09-28): pott-kolumnen/KPI:n → pott-drawer, koden → kontona. */
    if (d.pool) return openWith(t, () => drawerPool(d.pool));
    if (d.code) return openWith(t, () => drawerCode(d.code));
    if (d.tab) {
      const u = d.drawerPlayer;
      if (!S.dossier || S.dossier.username !== u) {
        const det = await api('/api/admin/user/' + encodeURIComponent(u));
        let led = null;
        try { led = await api('/api/admin/user/' + encodeURIComponent(u) + '/ledger?limit=200'); } catch (e) { led = null; }
        S.dossier = { username: u, detail: det, ledger: led };
      }
      return drawerTab(d.tab, u, S.dossier.detail, S.dossier.ledger);
    }
    if (d.act) return handleAction(t, d);
  });

  function drawerTier(arg) {
    const item = tierItems().find(i => i.key === arg || i.label === arg) || { key: arg, label: arg, value: 0 };
    const key = item.key;
    const users = USERS().filter(u => (u.subscription_status || 'free') === key);
    openDrawer('membership · tier', (item.label || key) + ' · ' + num(item.value) + ' accounts',
      '<div class="dgrid"><div class="dstat"><span class="t">Accounts</span><span class="v">' + num(item.value) + '</span></div>' +
      '<div class="dstat"><span class="t">Share</span><span class="v">' + pct(item.value, Number(TOT().accounts) || 0) + '</span></div></div>' +
      (users.length ? '<div class="tbl-wrap"><table><thead><tr><th>Player</th><th class="num">Tokens</th><th class="num">Turns</th><th class="num">Paid</th><th>Last active</th></tr></thead><tbody>' +
        users.slice(0, 40).map(u => '<tr data-player="' + esc(u.username) + '"><td>' + esc(u.username) + '</td><td class="num">' + tok(u.total_tokens) + '</td>' +
          '<td class="num">' + num(u.total_turns) + '</td><td class="num">' + (u.revenue ? sek(u.revenue) : '—') + '</td><td>' + esc(String(u.last_active || '').slice(0, 10)) + '</td></tr>').join('') +
        '</tbody></table></div>' + (users.length > 40 ? '<div class="note">Showing the first 40 of ' + num(users.length) + ' accounts — the full table with filters is on the Players view.</div>' : '') : emptyState('No accounts in this tier', '◌')) +
      '<div class="note">Tiers in the current model are one-time unlocks and admin grants — nothing renews.</div>',
      { d: 'tier', k: key });
  }

  function exportCsv(what) {
    if (what === 'players') return csvDownload('players.csv', [['username','role','code','coding_why','tier','country','campaigns','tokens','turns','pool_free_left','pool_free_cap','pool_free_used_period','pool_promo_left','pool_paid_left','pool_paid_granted','pool_paid_granted_known','pool_available','pool_unlimited','used_total_free','used_total_promo','used_total_paid','revenue','last_active']]
      .concat(sortedPlayers().map(u => {
        const tp = poolOf(u) || {};
        const life = tp.used_lifetime || {};
        const c = u.coding || {};
        return [u.username, u.role, c.code || '', c.why || '', u.subscription_status, u.country,
          u.total_campaigns, u.total_tokens, u.total_turns,
          tp.free_left == null ? '' : tp.free_left, tp.free_cap || 0, tp.free_used_period || 0,
          tp.promo_left || 0, tp.paid_left || 0, tp.paid_granted || 0, tp.paid_granted_known ? 'yes' : 'no',
          /* Oändlig pott får ingen siffra i CSV:n — annars läser kalkylbladet
             "∞" som 0 och nyckeltalet blir fel i stället för "unlimited". */
          tp.unlimited ? '' : (tp.available == null ? '' : tp.available), tp.unlimited ? 'yes' : 'no',
          life.free || 0, life.promo || 0, life.paid || 0, u.revenue, u.last_active];
      })));
    if (what === 'ledger') return csvDownload('ledger.csv', [['date','user','sek','type','reference']]
      .concat(ledgerRows().map(r => [String(r.ts||'').slice(0,10), r.user, r.amount_sek, r.type, r.event_id || r.stripe_sub_id || ''])));
    if (what === 'calls') return csvDownload('calls.csv', [['ts','player','action','model','bucket','turns_after']]
      .concat(callRows().map(r => [r.ts, r.user, r.action, r.model || '', r.bucket || 'unknown', r.pool_after == null ? '' : r.pool_after])));
    if (what === 'usage') return csvDownload('usage.csv', [['model','provider','calls','tokens']].concat(Object.keys(USAGE().models || {}).map(m => [m, (USAGE().models[m] || {}).provider || provOf(m), (USAGE().models[m] || {}).calls, (USAGE().models[m] || {}).tokens])));
    if (what === 'feedback') return csvDownload('feedback.csv', [['ts','email','message']].concat((S.feedback && S.feedback.items || []).map(f => [f.ts, f.email || '', f.message || ''])));
    return csvDownload('ai_calls.csv', [['day','calls']].concat(Object.entries(SER().api_calls_day || {})));
  }
  /* Per-spelare-CSV för modellen som är öppen i drawern — anrop per spelare
     är kärnan i "modellanrop per spelare"-frågan, så den ska gå att ta med sig. */
  function exportModelCsv(key) {
    const m = (S.lastModel && S.lastModel.key === key && S.lastModel.data) || null;
    if (!m) return toast('Open the model first, then export', 'bad');
    const rows = [['player','tier','calls_lifetime','tokens_lifetime','calls_in_window','window','last_active']]
      .concat((m.users || []).map(u => [u.username, u.subscription_status, u.calls, u.tokens, u.calls_window, m.window, u.last_active]));
    return csvDownload('model-' + String(key).replace(/[^a-z0-9._-]/gi, '_') + '-players.csv', rows);
  }

  async function handleAction(btn, d) {
    const A = window.AdminActions;
    if (!A) return;
    if (d.act === 'create') {
      const uEl = $('#new-user'), pEl = $('#new-pass'), rEl = $('#new-role');
      const u = uEl ? uEl.value.trim() : '', pw = pEl ? pEl.value : '', role = rEl ? rEl.value : 'player';
      if (!u || !pw) return toast('Fill in a username and a password');
      btn.disabled = true;
      try {
        await A.createUser(u, pw, role);
        toast('Account created: ' + u);
        uEl.value = ''; pEl.value = '';
        S.data = null;
        await load();
      } catch (e) {
        btn.disabled = false;
        toast(e.message || 'Could not create the account', 'bad');
      }
      return;
    }
    const wrap = btn.closest('[data-actions]');
    const username = wrap ? wrap.dataset.actions : (d.drawerPlayer || '');
    if (!username) return;
    const val = id => { const el = wrap && wrap.querySelector('#' + id); return el ? el.value : ''; };
    try {
      if (d.act === 'cap') { const cap = Number(val('act-cap')); if (isNaN(cap) || cap < 0) return toast('Enter a cap of 0 or more'); disableActions(wrap, true); await A.setCap(username, cap); toast('Daily cap set for ' + username); S.data = null; }
      else if (d.act === 'topup') { const n = Number(val('act-topup')); if (!n || n <= 0) return toast('Enter how many turns to add'); disableActions(wrap, true); await A.topUp(username, n); toast('+' + n + ' turns for ' + username); S.data = null; }
      else if (d.act === 'topup-preset') { const n = Number(d.n); disableActions(wrap, true); await A.topUp(username, n); toast('+' + n + ' turns for ' + username); S.data = null; }
      else if (d.act === 'tier') { const tier = val('act-tier'); disableActions(wrap, true); await A.setTier(username, tier, 30); toast(username + ' → ' + (TIER_LABEL[tier] || tier)); S.data = null; }
      else if (d.act === 'role') { const role = val('act-role'); disableActions(wrap, true); await A.setRole(username, role); toast(username + ' is now ' + role); S.data = null; }
      else if (d.act === 'reset') { disableActions(wrap, true); await A.resetTurns(username); toast('Turns reset for ' + username); S.data = null; }
      else if (d.act === 'delete') { if (!confirm('Delete ' + username + ' permanently? This removes the account.')) return; disableActions(wrap, true); await A.deleteUser(username); toast(username + ' deleted'); closeDrawer(); S.data = null; }
      else if (d.act === 'copy') {
        /* data-copyref, INTE data-ref: data-ref betyder "öppna referrer-drawern"
           i routern och läses före data-act — knappen öppnade en påhittad källa. */
        const refs = [d.copyref, d.event].filter(Boolean).join(' ');
        if (!refs) return toast('Nothing to copy on this row');
        try { await navigator.clipboard.writeText(refs); toast('Reference ids copied'); }
        catch (err) { toast('Clipboard blocked by the browser', 'bad'); }
        return;
      }
      else if (d.act === 'who') { return drawerPlayer(d.player); }
      else return;
      await load();
      if (username) drawerPlayer(username);
    } catch (e) {
      if (wrap) disableActions(wrap, false);
      toast(e.message || 'Action failed', 'bad');
    }
  }
  function disableActions(wrap, on) {
    if (!wrap) return;
    wrap.querySelectorAll('button').forEach(b => { b.disabled = !!on; });
  }

  /* ── chrome: theme / auto-refresh / keys / logout ── */
  function applyTheme(theme) {
    document.documentElement.dataset.theme = theme === 'light' ? 'light' : 'dark';
    try { localStorage.setItem('admin_theme', theme); } catch (e) {}
  }
  function toggleAuto() {
    S.auto = !S.auto;
    const b = $('#auto-btn');
    if (b) b.textContent = '⟲ Auto: ' + (S.auto ? 'on' : 'off');
    if (S.timer) { clearInterval(S.timer); S.timer = null; }
    if (S.auto) S.timer = setInterval(() => { if (!$('#drawer').classList.contains('on')) load({ quiet: true }); }, 60000);
  }
  document.addEventListener('keydown', function (e) {
    const open = S.drawerState && $('#drawer').classList.contains('on');
    if (e.key === 'Escape') { if (open) { e.preventDefault(); closeDrawer(); } return; }
    /* Fokusfälla: Tab ska stanna i drawern medan den är öppen (planens Fas 4.3). */
    if (e.key === 'Tab' && open) {
      const focusables = $$('#drawer a[href],#drawer button,#drawer input,#drawer select,#drawer textarea,#drawer [tabindex]:not([tabindex="-1"])')
        .filter(el => !el.disabled && el.offsetParent !== null);
      if (!focusables.length) return;
      const first = focusables[0], last = focusables[focusables.length - 1];
      const active = document.activeElement;
      if (e.shiftKey && (active === first || !$('#drawer').contains(active))) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && (active === last || !$('#drawer').contains(active))) { e.preventDefault(); first.focus(); }
      return;
    }
    if (e.key === 'r' && e.altKey) { load({ quiet: true }); }
    if (e.key === 't' && e.altKey) { toggleThemeFromKey(); }
  });
  function toggleThemeFromKey() { applyTheme(document.documentElement.dataset.theme === 'light' ? 'dark' : 'light'); }

  function wireChrome() {
    const themeBtn = $('#theme-btn');
    if (themeBtn) themeBtn.addEventListener('click', () => { applyTheme(document.documentElement.dataset.theme === 'light' ? 'dark' : 'light'); });
    const autoBtn = $('#auto-btn');
    if (autoBtn) autoBtn.addEventListener('click', toggleAuto);
    const refresh = $('#refresh-btn');
    if (refresh) refresh.addEventListener('click', () => load({ quiet: true }));
    const close = $('#dclose');
    if (close) close.addEventListener('click', closeDrawer);
    const scrim = $('#scrim');
    if (scrim) scrim.addEventListener('click', closeDrawer);
    document.addEventListener('click', function (e) {
      if (e.target && e.target.id === 'logout-btn') {
        try { localStorage.removeItem('morkrets_token'); } catch (err) {}
        sessionStorage.clear();
        location.href = 'login.html';
      }
    });
    // hash deep links: #players, #revenue?w=7d, #usage?w=30d&d=model&k=qwen3.8-flash
    let theme = 'dark';
    try { theme = localStorage.getItem('admin_theme') || 'dark'; } catch (e) {}
    applyTheme(theme);
  }

  wireChrome();
  /* Djup­länk vid kallstart: parsa hashen FÖRST (view/window/drawer), måla
     skalet, hämta datat och öppna drawern när payloaden finns. Under boot rör
     vi inte historiken (URL:en bär redan hela läget). */
  const boot = parseHash();
  S.view = boot.view;
  S.win = boot.win;
  suppressHash = true;
  go(S.view);          // paint the shell from whatever we have (empty states are real UI)
  const bootDrawer = boot.d ? { view: boot.view, win: boot.win, d: boot.d, k: boot.k, t: boot.t } : null;
  Promise.resolve(load())
    .then(() => (bootDrawer ? applyHash(bootDrawer, { fromPop: true }) : null))
    .then(() => { suppressHash = false; syncHash(false, true); });
})();
