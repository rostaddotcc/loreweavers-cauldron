/* ══════════════════════════════════════════════════════════════════════════════
   Mission Control — admin console v2 (2026-09-27)
   Reads:  /api/admin/overview?window=  (new aggregate payload)
           /api/admin/billing, /api/admin/feedback, /api/admin/user/{u},
           /api/admin/user/{u}/ledger, /api/admin/visits_country
   Writes: never directly — every mutation goes through window.AdminActions.
   Money is computed server-side; this file only formats and drills down.
   ══════════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  /* ── gate: admin pages require the sessionStorage marker the login flow sets.
     login.html writes a plain username string (sessionStorage.setItem('dnd_user', u.username)),
     so treat the marker as opaque — only its presence matters here. ── */
  if (!sessionStorage.getItem('dnd_user')) { location.href = 'login.html'; return; }

  const PALETTE = ['#5b8cff', '#e0a24a', '#3fbf8f', '#a97bff', '#4fc3c8', '#e0605e', '#8d9db3'];
  const PROV_COLOR = { stepfun:'#e0a24a', dashscope:'#5b8cff', deepseek:'#3fbf8f', openrouter:'#a97bff', ollama:'#8d9db3', 'ollama (relay)':'#8d9db3', mimo:'#4fc3c8', unlabelled:'#6b7c92', unknown:'#6b7c92' };
  const PROV_LABEL = { stepfun:'⚗ StepFun', dashscope:'🌊 Qwen / DashScope', deepseek:'🧠 DeepSeek', openrouter:'🎲 OpenRouter', ollama:'🖥 Local', 'ollama (relay)':'🏮 Ollama (relay)', mimo:'📱 MiMo', unlabelled:'· Unlabelled', unknown:'? Unknown' };
  const MODEL_SKIP = { '__unlabelled':1, '?':1, '':1 };
  const TIER_LABEL = { free:'Free', tier1:'Support', tier2:'Patron', lifetime:'Lifetime' };

  const S = {
    view: 'overview', win: '30d', metric: 'calls', revMode: 'day', trafficMetric: 'requests',
    data: null, billing: null, feedback: null, fbRange: 'all', fbMail: 'all',
    sortKey: 'tokens', sortDir: 'desc', page: 1, pageSize: 10,
    q: '', fRole: 'all', fStatus: 'all', fCountry: 'all', fCode: 'all',
    auto: false, timer: null, degraded: false, loading: false, dossier: null,
    /* Hink-filtret i dossiéns ledger-tabell (2026-09-28). Nollställs när en ny
       spelare öppnas, så ett filter aldrig läcker mellan konton. */
    dossierBucket: 'all',
    /* expand = "show all" per panel (referrers, countries, models, players-model-mix).
       Empty = the panel's default cap. Never silently truncate without the control. */
    expand: {}, drawerState: null, geoRange: '', geoOverride: null,
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
  const TRAF = () => D().traffic || {};
  const REFD = () => TRAF().referrer_detail || {};
  const UNIQ = () => TRAF().uniques || {};
  const TIERS = () => D().tiers || {};
  const USERS = () => D().users || [];
  const ledgerRows = () => (S.billing && S.billing.ledger) || REV().ledger || [];
  /* Besöksserier: requests per dag vs UNIKA per dag. Två olika tal — grafens
     etikett följer S.trafficMetric så ingen blandar ihop dem. */
  const visitsSeries = () => SER().visits_day || {};
  const uniquesSeries = () => SER().visits_unique_day || {};
  /* Referrer-källor, FÖNSTRADE (referrer_detail) och sorterade på unika
     besökare. Fallback till den gamla by_referrer-dicten om en äldre backend
     svarar (då är talen livstid — det står i etiketten). */
  function refItems() {
    const det = REFD();
    const keys = Object.keys(det);
    if (keys.length) {
      return keys.map(k => ({
        key: k, label: k, value: Number((det[k] || {}).uniques || 0), detail: det[k] || {},
      })).sort((a, b) => b.value - a.value);
    }
    const refs = TRAF().referrers || {};
    return Object.keys(refs).map(k => ({
      key: k, label: k, detail: null,
      value: typeof refs[k] === 'object' ? Object.keys(refs[k]).length : Number(refs[k]) || 0,
    })).sort((a, b) => b.value - a.value);
  }
  /* Länder i besöksloggen: backend skickar en dict {cc: n} men äldre payloadar
     kan skicka en lista. Hantera båda — annars är klicket dött (bugg 2026-09-27). */
  function geoItems() {
    const bc = S.geoOverride || TRAF().by_country || {};
    const rows = Array.isArray(bc) ? bc.map(c => ({ cc: c.cc, value: Number(c.value || c.count || 0) }))
                                   : Object.keys(bc).map(cc => ({ cc: cc, value: Number(bc[cc]) || 0 }));
    return rows.map(r => ({ key: r.cc, label: ccName(r.cc), value: r.value, color: geoColor(r.cc) }));
  }
  /* Land-grafens EGEN tidsväljare (1h/12h/…/all) — den enda panelen som
     hämtar på begäran via /api/admin/visits_country, så man kan titta snävare
     än dashboardens globala fönster (2026-09-27). */
  const GEO_RANGES = [['1h','1h'],['12h','12h'],['24h','24h'],['7d','7d'],['30d','30d'],['all','All time']];
  async function loadGeoRange(range) {
    S.geoRange = range || '';
    S.geoOverride = null;
    if (range) {
      try {
        const j = await api('/api/admin/visits_country?window=' + encodeURIComponent(range));
        S.geoOverride = j.by_country || {};
      } catch (e) { toast('Country window failed: ' + e.message, 'bad'); S.geoRange = ''; }
    }
    render();
  }
  const GEO_BUCKETS = { '??': 1, 'LOCAL': 1, 'UNKNOWN': 1, 'UN': 1, 'XX': 1 };
  const isRealCC = cc => /^[A-Z]{2}$/.test(String(cc || '')) && !GEO_BUCKETS[String(cc).toUpperCase()];
  function geoColor(cc) {
    const c = String(cc || '');
    if (c === '??') return '#6b7c92';
    if (c === 'LOCAL') return '#8d9db3';
    let h = 0; for (let i = 0; i < c.length; i++) h = (h * 31 + c.charCodeAt(i)) % 360;
    return 'hsl(' + h + ' 52% 58%)';
  }
  /* Källor som pekar på ett land — inverterad referrer_detail. Gör land-drawern
     till en riktig drilldown i stället för en återvändsgränd. */
  function sourcesForCountry(cc) {
    const out = [];
    const det = REFD();
    Object.keys(det).forEach(src => {
      const n = Number(((det[src] || {}).countries || {})[cc] || 0);
      if (n) out.push({ key: src, label: src, value: n });
    });
    return out.sort((a, b) => b.value - a.value);
  }
  /* "Show all"-kapning: default N, full lista när panelen är expanderad. */
  function clampList(items, panel, def) {
    const all = items || [];
    if (S.expand[panel] || all.length <= def) return { rows: all, hidden: 0 };
    return { rows: all.slice(0, def), hidden: all.length - def };
  }
  function expandBtn(panel, hidden, noun) {
    if (!hidden && !S.expand[panel]) return '';
    return '<button type="button" class="chip clear" data-expand="' + esc(panel) + '">' +
      (S.expand[panel] ? '▴ Show top ' + esc(noun) : '▾ Show all ' + num(hidden) + ' more ' + esc(noun)) + '</button>';
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
      const showVal = v && (keys.length <= 16 ? true : (opts.alwaysLabel && kept));
      return '<div class="vcol' + (k === lastKey ? ' today' : '') + (opts.rev ? ' rev' : '') + '" data-bucket="' + esc(k) + '" data-val="' + v + '" title="' + esc(k + ' · ' + num(v) + (opts.unit ? ' ' + opts.unit : '')) + '" style="--i:' + i + '">' +
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
  function kpi(o) {
    return '<div class="card kpi' + (o.drill ? ' clickable' : '') + '"' + (o.drill ? ' data-drill="' + esc(o.drill) + '"' : '') + '>' +
      '<span class="t">' + esc(o.t) + '</span>' +
      '<span class="v' + (o.tone ? ' ' + o.tone : '') + '">' + o.v + '</span>' +
      '<span class="f">' + o.f + '</span>' +
      (o.drill ? '<span class="cta">' + esc(o.cta || 'drill down →') + '</span>' : '') + '</div>';
  }
  function card(span, title, sub, body, opts) {
    opts = opts || {};
    return '<div class="card span' + span + (opts.data ? ' ' + opts.data : '') + '">' +
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
        return '<span class="seg ' + p + '" style="height:' + (v / max * 100) + '%" title="' + esc(k + ' · ' + p + ' · ' + num(v) + ' ' + (opts.unit || 'turns')) + '"></span>';
      }).join('');
      return '<div class="vcol" data-bucket="' + esc(k) + '" data-val="' + totals[i] + '" title="' + esc(k + ' · ' + num(totals[i]) + ' ' + (opts.unit || 'turns')) + '" style="--i:' + i + '">' +
        '<span class="lab">' + (totals[i] && keys.length <= 16 ? num(totals[i]) : '') + '</span>' +
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

  function viewOverview() {
    const t = TOT(), r = REV(), v = valueStats();
    const callsDay = SER().api_calls_day || {};
    const visitsDay = SER().visits_day || {};
    const turnsDay = SER().turns_day || {};
    const bucketDay = v.bucketDay || {};
    const pool = D().pool_totals || {};
    const codes = D().coding_summary || {};
    const modelClamp = clampList(modelItems('calls'), 'models', 6);
    const conv = r.conversion_pct != null ? Number(r.conversion_pct) : (Number(r.paying_customers) || 0) / (Number(t.accounts) || 1) * 100;
    const actions = VAL().by_action || {};
    const actionItems = Object.keys(actions).sort((a, b) => actions[b] - actions[a])
      .map((k, i) => ({ key:k, label:k.replace(/_/g, ' '), value: actions[k], color: PALETTE[i % PALETTE.length] }));

    return head('Overview', 'Money and value side by side — click any tile, bar or slice to open the records behind it.',
        '<button class="icon-btn" data-csv="overview">⇣ CSV</button>') +
      banner() +
      '<div class="tiles">' +
        kpi({ t:'Revenue · ' + (r.month_key || 'this month'), v: sek(r.month_revenue != null ? r.month_revenue : r.month), tone:'accent', drill:'rev:month',
              f: (Number(r.today) ? '<b>' + sek(r.today) + '</b> today · ' : 'no payments today · ') + 'one-time products' }) +
        kpi({ t:'Lifetime revenue', v: sek(r.total), drill:'rev:lifetime',
              f: '<b>' + num(r.paying_customers) + '</b> paying accounts · ' + num(r.transactions) + ' payments · ' + conv.toFixed(1) + '%' }) +
        kpi({ t:'Turns delivered', v: num(v.turns) + ' turns', tone:'good', drill:'value',
              f: 'window ' + S.win + ' · <b>' + num(v.bucketDayTotals.free) + '</b> free / <b>' + num(v.bucketDayTotals.paid) + '</b> paid' }) +
        kpi({ t:'Turns left in pools', v: (Number(pool.unlimited_accounts) ? '' : '') + num(pool.available) + ' turns', drill:'pool',
              f: '<b>' + num(pool.free_left) + '</b> free today · <b>' + num(pool.paid_left) + '</b> bought · <b>' + num(pool.promo_left) + '</b> promo' + (Number(pool.unlimited_accounts) ? ' · ' + num(pool.unlimited_accounts) + ' unlimited accounts' : '') }) +
        kpi({ t:'Cost of play', v: v.kpm == null ? '—' : v.kpm.toFixed(2) + ' kr', drill:'value',
              f: 'per 1M tokens · <b>' + tok(v.tps) + '</b> tokens per kr' }) +
        kpi({ t:'Accounts', v: num(t.accounts), drill:'players',
              f: '<b>' + num(t.players) + '</b> players · ' + num(t.admins) + ' admin' }) +
        kpi({ t:'Campaigns', v: num(t.campaigns), drill:'players',
              f: '<b>' + (t.accounts ? (t.campaigns / t.accounts).toFixed(2) : '—') + '</b> per account' }) +
        kpi({ t:'AI calls', v: num(sum(callsDay)), drill:'usage:calls', cta:'open Usage →',
              f: 'window ' + S.win + ' · lifetime <b>' + num(t.ai_calls) + '</b>' }) +
        kpi({ t:'Unique visitors', v: num(UNIQ().total), drill:'traffic', cta:'open Traffic →',
              f: 'lifetime distinct IPs · <b>' + num(UNIQ().last_7) + '</b> in 7 days · ' + num(sum(SER().visits_unique_day || {})) + ' visitor-days in this window' }) +
      '</div>' +
      '<div class="grid">' +
        card(8, 'AI calls per day', 'DM, Lorekeeper and auxiliary calls read from the transcripts · window ' + S.win,
             vchart(callsDay, { unit:'calls', emptyMsg:'No calls logged in this window' })) +
        card(4, 'Membership', 'active accounts by tier · click a slice for the accounts', donut(tierItems(), num(t.accounts), 'accounts', { keepZero: true, click: i => 'data-tier="' + esc(i.key) + '"' })) +
        card(7, 'Turns delivered per day, by bucket', 'fri / köpt / promo / legacy staplade — click a bar for that day', vchartStacked(bucketDay, { unit:'turns', emptyMsg:'No turn series in this payload' }), { data:'clickable', attrs:1 }) +
        card(5, 'What the turns bought', 'turn actions, lifetime · click a slice for the split', actionItems.length ? donut(actionItems, num(v.turns), 'turns', { click: i => 'data-action="' + esc(i.key) + '"' }) : emptyState('No action split in this payload', '◌')) +
        card(5, 'Players by code', 'free / granted / paid — server-counted, click a slice for the accounts',
             codeDonut(codes)) +
        recentActiveCard() +
        card(6, 'Revenue vs value delivered', 'what came in, and what players got for it', valueGrid(v), { data:'clickable' }) +
        card(6, 'Most used models', 'by calls · click a bar for that model', hbars(modelClamp.rows, { fmt: num, click: i => 'data-model="' + esc(i.key) + '"' }) + expandBtn('models', modelClamp.hidden, 'models')) +
        card(7, 'Requests per day', 'every request counted · click a bar for the day', vchart(visitsDay, { emptyMsg:'No visits in this window' })) +
        card(5, 'New accounts per day', num(sum(SER().signups_day || {})) + ' signups in this window · click a bar for the day',
             vchart(SER().signups_day || {}, { emptyMsg:'No signups in this window' })) +
        card(12, 'Recent transactions', 'click a row for the raw record', ledgerTable(ledgerRows().slice(-5).reverse())) +
      '</div>';
  }

  /* Free/paid-fördelningen (rostad 2026-09-28): räknas server-side i
     /api/admin/overview som coding_summary. Klick → kontona bakom koden. */
  function codeDonut(codes) {
    /* Koder utan konton ritas inte (2026-09-28): en slice som alltid står på 0
       är en död yta. Reglerna och etiketterna finns kvar i CODE_LABEL. */
    const items = ['paid', 'granted', 'free'].map(k => ({
      key:k, label:CODE_LABEL[k], value:Number(codes[k] || 0), color:POOL_PART_COLOR[k === 'free' ? 'free' : (k === 'paid' ? 'paid' : 'promo')],
    })).filter(i => i.value > 0);
    const total = items.reduce((a, i) => a + i.value, 0);
    if (!total) return emptyState('No coding in this payload', '◌');
    return donut(items, num(total), 'accounts', { click: i => 'data-code="' + esc(i.key) + '"' });
  }

  /* "Senast 5 aktiva spelarna" (rostad 2026-09-28). Källan är last_active som
     redan finns per konto i den kompletta tabellen — ingen ny endpoint.
     Admins exkluderas (det är spelarna som avses) och konton utan
     aktivitetsstämpel räknas i notisen i stället för att visas med påhittad tid. */
  function recentActiveCard() {
    const players = USERS().filter(u => (u.role || 'player') !== 'admin');
    const stamped = players.filter(u => Date.parse(u.last_active || ''));
    const missing = players.length - stamped.length;
    const top = stamped.slice().sort((a, b) => (Date.parse(b.last_active) || 0) - (Date.parse(a.last_active) || 0)).slice(0, 5);
    const notes = ['last 5 players · admins excluded'];
    if (missing) notes.push(num(missing) + ' account' + (missing === 1 ? '' : 's') + ' without an activity stamp');
    const body = top.length
      ? '<div class="recent">' + top.map(u =>
          '<button type="button" class="recent-row" data-player="' + esc(u.username) + '" title="Open ' + esc(u.username) + '’s dossier">' +
            codeDot(u) +
            '<span class="nm">' + esc(u.username) + '</span>' +
            '<span class="pl">' + esc(poolText(u)) + '</span>' + poolBar(u) +
            '<span class="wh">' + esc(agoText(u.last_active)) + '</span>' +
            '<span class="go">→</span>' +
          '</button>').join('') + '</div>'
      : emptyState('No player activity recorded yet', '◌');
    return card(7, 'Recently active', notes.join(' · '), body);
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
        kpi({ t:'This month · ' + (r.month_key || ''), v: sek(r.month_revenue != null ? r.month_revenue : r.month), tone:'accent', drill:'rev:month', f:'calendar month, local time' }) +
        kpi({ t:'Today', v: Number(r.today) ? sek(r.today) : '0 kr', tone:'good', drill:'rev:today',
              f: Number(r.today) ? 'payments received since midnight' : 'nothing yet today — the ledger is flat' }) +
        kpi({ t:'Lifetime', v: sek(r.total), drill:'rev:lifetime', f:'<b>' + num(r.transactions) + '</b> payments · ' + num(r.paying_customers) + ' paying accounts' }) +
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
        card(5, 'What the money bought', 'value delivered alongside the revenue', valueGrid(v), { data:'clickable' }) +
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
        card(5, 'Calls by provider', num(sum(USAGE().providers ? Object.keys(USAGE().providers).reduce((a, k) => { a[k] = USAGE().providers[k].calls; return a; }, {}) : {})) + ' logged calls, lifetime',
             donut(providerItems(), num(providerItems().reduce((a, i) => a + i.value, 0)), 'calls')) +
        card(6, 'Token share by provider', 'lifetime tokens, including the unlabelled bucket', donut(tokenSplitItems(), tok(TOT().tokens), 'tokens')) +
        card(6, 'Calls per day', 'window ' + S.win, vchart(SER().api_calls_day || {}, { unit:'calls' })) +
      '</div>';
  }

  function viewTraffic() {
    const visitsDay = visitsSeries();
    const uniqueDay = uniquesSeries();
    const uniq = UNIQ();
    const metric = S.trafficMetric;
    const series = metric === 'unique' ? uniqueDay : visitsDay;
    const windowVisits = sum(visitsDay);
    const windowDays = sum(uniqueDay);
    const allRefs = refItems();
    const liveRefs = allRefs.filter(r => r.value > 0);
    const refClamp = clampList(liveRefs, 'refs', 8);
    const allGeo = geoItems();
    const geoClamp = clampList(allGeo, 'geo', 10);
    const geoCountries = allGeo.filter(i => isRealCC(i.key));
    const peak = Object.keys(visitsDay).sort((a, b) => visitsDay[b] - visitsDay[a])[0];
    const refWindowed = Object.keys(REFD()).length > 0;

    return head('Traffic', 'Nobody logged in: visits and where they come from. Counted per request; geo is resolved in the background and never inline. Every source and every country is listed — click one for the numbers behind it.',
        '<div class="seg">' + ['requests','unique'].map(m =>
          '<button type="button" data-tmetric="' + m + '" class="' + (metric === m ? 'on' : '') + '">' +
          (m === 'unique' ? 'Unique visitors' : 'Requests') + '</button>').join('') + '</div>' +
        '<button class="icon-btn" data-csv="visits">⇣ CSV</button>') +
      banner() +
      '<div class="tiles">' +
        kpi({ t:'Visits in window', v: num(windowVisits), tone:'accent', drill:'traffic',
              f: 'requests · lifetime <b>' + num(TRAF().total || TOT().visits) + '</b>' }) +
        kpi({ t:'Unique visitors (lifetime)', v: num(uniq.total), drill:'traffic',
              f: '<b>' + num(uniq.last_7) + '</b> in 7 days · <b>' + num(uniq.today) + '</b> today · ' + num(windowDays) + ' visitor-days in this window' }) +
        kpi({ t:'Peak day', v: peak ? num(visitsDay[peak]) : '—', drill: peak ? 'day:' + peak : '',
              f: peak ? esc(peak) + ' · <b>' + num(uniqueDay[peak] || 0) + '</b> unique' : 'no visits logged' }) +
        kpi({ t:'Countries resolved', v: num(geoCountries.length), drill:'geo',
              f: geoCountries.length ? num(allGeo.length - geoCountries.length) + ' bucket(s) still unresolved'
                                     : 'none yet — ' + num(allGeo.length) + ' unresolved bucket(s)' }) +
      '</div>' +
      '<div class="grid">' +
        card(12, metric === 'unique' ? 'Unique visitors per day' : 'Visits per day',
             'window ' + S.win + ' · ' + (metric === 'unique' ? 'distinct IPs per day' : 'every request counted') + ' · click a bar for that day',
             vchart(series, { unit: metric === 'unique' ? 'unique' : 'visits', emptyMsg:'No visits in this window' })) +
        card(7, 'Visits by country', (S.geoRange ? 'unique visitors whose last visit was within ' + S.geoRange + ' (its own window, not the page window)'
                                                  : 'unique visitors per country, resolved from the IP cache — never inline') + ' · ' + num(allGeo.length) + ' buckets',
             '<div class="panel-tools">' +
               '<div class="seg small">' + GEO_RANGES.map(([v, l]) =>
                 '<button type="button" data-georange="' + v + '" class="' + (S.geoRange === v ? 'on' : '') + '">' + esc(l) + '</button>').join('') +
                 (S.geoRange ? '<button type="button" data-georange="" title="Follow the page window again">↺ page window</button>' : '') + '</div>' +
               '<button class="icon-btn" data-csv="countries">⇣ CSV</button>' + expandBtn('geo', geoClamp.hidden, 'countries') + '</div>' +
             hbars(geoClamp.rows, { fmt: num, unit:'visitors', class:"geo-list", click: i => 'data-geo="' + esc(i.key) + '"', emptyMsg:'No visits with a resolved country yet' }) +
             '<div class="note">Every country is listed — click one for its sources and accounts. Visits whose country has not been resolved yet stay visible as “Unknown (no geo yet)” instead of being dropped, so the total always matches the visit log.</div>') +
        card(5, 'Referrers', (refWindowed ? 'unique visitors per source in window ' + S.win : 'unique visitors per source (lifetime)') + ' · ' + num(allRefs.length) + ' sources',
             '<div class="panel-tools"><button class="icon-btn" data-csv="referrers">⇣ CSV</button>' + expandBtn('refs', refClamp.hidden, 'sources') + '</div>' +
             hbars(refClamp.rows, { fmt: num, unit:'visitors', class:"ref-list", click: i => 'data-ref="' + esc(i.key) + '"', emptyMsg:'No referrers recorded' }) +
             '<div class="note">' + (refWindowed
               ? 'A source counts an IP once, and the window filters on that visitor’s last visit from the source. ' + num(liveRefs.length) + ' of ' + num(allRefs.length) + ' sources are active in this window — the table below lists all of them.'
               : 'This backend payload carries only lifetime counts per source.') + '</div>') +
        card(12, 'Every referrer source', 'the full list — ' + num(allRefs.length) + ' sources recorded, ' +
             num(allRefs.length - liveRefs.length) + ' of them quiet in this window · click a row',
             referrerTable(allRefs)) +
      '</div>';
  }
  function referrerTable(rows) {
    rows = rows || [];
    if (!rows.length) return emptyState('No referrers recorded yet', '◌');
    const totalWindow = sum(uniquesSeries()) || 1;
    return '<div class="tbl-wrap"><table class="ref-table"><thead><tr><th>Source</th><th class="num">Visitors in window</th>' +
      '<th class="num">Share</th><th>Top countries</th><th>First seen</th><th>Last seen</th></tr></thead><tbody>' +
      rows.map(r => {
        const det = r.detail || {};
        const ccKeys = Object.keys(det.countries || {}).filter(isRealCC).slice(0, 3);
        const ccTxt = ccKeys.length ? ccKeys.map(c => (ccFlag(c) + ' ' + c + ' ' + num(det.countries[c]))).join(' · ')
                                    : (det.countries ? 'bucket only (no geo)' : '—');
        return '<tr data-ref="' + esc(r.key) + '"' + (r.value ? '' : ' class="quiet"') + '>' +
          '<td><b>' + esc(r.key) + '</b></td>' +
          '<td class="num">' + (r.value ? num(r.value) : '—') + '</td>' +
          '<td class="num">' + (r.value ? pct(r.value, totalWindow) : '—') + '</td>' +
          '<td>' + esc(ccTxt) + '</td>' +
          '<td>' + esc(dayOf(det.first_seen)) + '</td>' +
          '<td>' + esc(dayOf(det.last_seen)) + '</td></tr>';
      }).join('') + '</tbody></table></div>';
  }
  /* Sekundstämplar ur visit-loggen → lokal dag (faller tillbaka på '—'). */
  function dayOf(ts) {
    const n = Number(ts || 0);
    if (!n) return '—';
    try { return new Date(n * 1000).toISOString().slice(0, 10); } catch (e) { return '—'; }
  }
  function ccFlag(cc) {
    const c = String(cc || '').toUpperCase();
    if (c === 'LOCAL') return '🏠';
    if (!/^[A-Z]{2}$/.test(c)) return '❓';
    return String.fromCodePoint.apply(null, c.split('').map(ch => 0x1F1E6 + ch.charCodeAt(0) - 65));
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
    return head('Feedback', 'Everything players sent in. Click a row to open the sender\'s dossier.',
        '<button class="icon-btn" data-csv="feedback">⇣ CSV</button>') +
      banner() +
      '<div class="card span12">' +
        '<div class="filters-row">' +
          '<div class="chip-group"><span class="chip-label">Window</span><div class="chips">' +
            [['all','All'],['24h','24h'],['7d','7 days'],['30d','30 days']].map(([v, l]) => chip(v === S.fbRange, 'data-fbrange="' + v + '"', l)).join('') + '</div></div>' +
          '<div class="chip-group"><span class="chip-label">Sender</span><div class="chips">' +
            [['all','All'],['with','Has e-mail'],['without','Anonymous']].map(([v, l]) => chip(v === S.fbMail, 'data-fbmail="' + v + '"', l)).join('') + '</div></div>' +
          '<span class="filter-count">' + num(rows.length) + ' messages</span>' +
        '</div>' +
        '<div class="feedback-inbox">' + (rows.length ? rows.map(f => {
          const t = f.ts ? new Date(f.ts) : null;
          return '<div class="fb-item">' +
            '<div class="fb-when">' + esc(t ? t.toLocaleString('en-GB') : 'unknown time') + (f.email ? ' · ' + esc(f.email) : ' · anonymous') + '</div>' +
            '<div class="fb-text">' + esc(f.message || f.text || '') + '</div>' +
            (f.email ? '<div class="fb-tag">has reply address</div>' : '') + '</div>';
        }).join('') : emptyState('No feedback yet — the inbox is quiet', '🕊')) + '</div>' +
      '</div>';
  }

  function viewSystem() {
    const t = TOT();
    return head('System', 'What this console reads, and what it deliberately does not do.', '') +
      banner() +
      '<div class="grid">' +
        card(7, 'Data sources', 'every number on this page is computed server-side from these', 
          hbars([
            { key:'campaigns', label:'campaign transcripts (tokens, calls, turns)', value: Number(t.campaigns) || 0, color:'var(--accent)' },
            { key:'accounts', label:'account records (tiers, geo, caps)', value: Number(t.accounts) || 0, color:'var(--teal)' },
            { key:'ledger', label:'billing ledger rows (revenue)', value: ledgerRows().length, color:'var(--gold)' },
            { key:'visits', label:'visit records in the traffic log', value: Number(TRAF().total || t.visits) || 0, color:'var(--violet)' },
          ], { fmt: num }) +
          '<div class="note">Turn counts come from the per-user turn ledgers, token counts from transcript metadata, money from the billing ledger, visits from the traffic log. Nothing is estimated on the client.</div>') +
        card(5, 'Endpoints', 'read-only unless you use an action button',
          '<div class="tbl-wrap"><table><thead><tr><th>Endpoint</th><th>Used for</th></tr></thead><tbody>' +
          [['/api/admin/overview', 'the whole first paint (windowed)'],
           ['/api/admin/model/{model}', 'model curve + who called it'],
           ['/api/admin/billing', 'ledger + customers'],
           ['/api/admin/user/{u}', 'player dossier'],
           ['/api/admin/user/{u}/ledger', 'turn-level usage'],
           ['/api/admin/feedback', 'inbox'],
           ['/api/admin/visits_country', 'unique visitors per country and window']].map(r => '<tr><td><code>' + esc(r[0]) + '</code></td><td>' + esc(r[1]) + '</td></tr>').join('') +
          '</tbody></table></div>' +
          '<div class="note">The model drawer is the only panel that fetches on demand — it scans the transcripts for one model, so it loads when you open it instead of on every page load.</div>' +
          '<div class="acts"><a class="icon-btn" href="chat.html">⚔ Back to the table</a><button class="icon-btn" id="logout-btn">Log out</button></div>') +
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
  /* ── Traffic-drawers: alla siffror ur visit-loggen, cache-lästa ── */
  function drawerTraffic() {
    const uniq = UNIQ();
    const visitsDay = visitsSeries();
    const uniqueDay = uniquesSeries();
    const rows = Object.keys(visitsDay).sort();
    const refs = refItems();
    openDrawer('traffic · summary', num(TRAF().total || TOT().visits) + ' requests',
      '<div class="dgrid">' +
      '<div class="dstat"><span class="t">Requests · lifetime</span><span class="v">' + num(TRAF().total || TOT().visits) + '</span></div>' +
      '<div class="dstat"><span class="t">Requests · today</span><span class="v">' + num(TRAF().today) + '</span></div>' +
      '<div class="dstat"><span class="t">Unique visitors · lifetime</span><span class="v">' + num(uniq.total) + '</span></div>' +
      '<div class="dstat"><span class="t">Unique visitors · 7 days</span><span class="v">' + num(uniq.last_7) + '</span></div>' +
      '<div class="dstat"><span class="t">Unique visitors · today</span><span class="v">' + num(uniq.today) + '</span></div>' +
      '<div class="dstat"><span class="t">Sources recorded</span><span class="v">' + num(refs.length) + '</span></div></div>' +
      '<div class="sub">Requests and unique visitors per day (' + num(rows.length) + ' days logged)</div>' +
      '<div class="tbl-wrap"><table class="mix-table"><thead><tr><th>Day</th><th class="num">Requests</th><th class="num">Unique</th></tr></thead><tbody>' +
      rows.slice().reverse().map(d => '<tr data-day="' + esc(d) + '"><td>' + esc(d) + '</td><td class="num">' + num(visitsDay[d]) +
        '</td><td class="num">' + num(uniqueDay[d] || 0) + '</td></tr>').join('') + '</tbody></table></div>' +
      '<div class="note">A request is one page request; a unique visitor is one distinct IP that day. Nothing is estimated on the client.</div>',
      { d: 'traffic' });
  }
  function drawerDay(day) {
    const v = Number((visitsSeries() || {})[day] || 0);
    const u = Number((uniquesSeries() || {})[day] || 0);
    const rev = Number((REV().by_date || {})[day] || 0);
    const turns = Number((SER().turns_day || {})[day] || 0);
    const calls = Number((SER().api_calls_day || {})[day] || 0);
    /* Hinkfördelningen för dagen (2026-09-28): samma server-räknade serie som
       Overview-grafen, så siffran här och stapeln där aldrig kan gå isär. */
    const split = (valueStats().bucketDay || {})[day] || null;
    openDrawer('traffic · day', day,
      '<div class="dgrid">' +
      '<div class="dstat"><span class="t">Requests</span><span class="v">' + num(v) + '</span></div>' +
      '<div class="dstat"><span class="t">Unique visitors</span><span class="v">' + num(u) + '</span></div>' +
      '<div class="dstat"><span class="t">AI calls</span><span class="v">' + num(calls) + '</span></div>' +
      '<div class="dstat"><span class="t">Turns delivered</span><span class="v">' + num(turns) + '</span></div>' +
      '<div class="dstat"><span class="t">Revenue</span><span class="v">' + (rev ? sek(rev) : '—') + '</span></div></div>' +
      bucketSplit(split, 'this day') +
      '<div class="note">Everything the logs know about this single day, side by side. Per-source and per-country detail is only kept as a rolling window (geo and referrer are resolved from the cache), so those breakdowns are shown for the current window on the Traffic view rather than per day.</div>',
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
  function drawerGeo(cc) {
    const items = geoItems();
    const item = items.find(i => i.key === cc) || { key: cc, value: 0 };
    const totalVisitors = sum(uniquesSeries()) || 0;
    const sources = sourcesForCountry(cc);
    const users = USERS().filter(u => (u.country_code || '??') === cc);
    openDrawer('traffic · country', ccName(cc) + ' · ' + num(item.value) + ' visitors',
      '<div class="dgrid">' +
      '<div class="dstat"><span class="t">Unique visitors · window ' + esc(S.win) + '</span><span class="v">' + num(item.value) + '</span></div>' +
      '<div class="dstat"><span class="t">Share of visitor-days</span><span class="v">' + pct(item.value, totalVisitors) + '</span></div>' +
      '<div class="dstat"><span class="t">Sources</span><span class="v">' + num(sources.length) + '</span></div>' +
      '<div class="dstat"><span class="t">Registered accounts</span><span class="v">' + num(users.length) + '</span></div></div>' +
      (sources.length ? '<div class="sub">Where they came from · all ' + num(sources.length) + '</div>' + hbars(sources, { fmt: num, unit:'visitors', class:"ref-list", click: i => 'data-ref="' + esc(i.key) + '"' }) : emptyState('No source recorded for this country', '◌')) +
      (users.length ? '<div class="sub">Accounts registered here</div><div class="tbl-wrap"><table class="mix-table"><thead><tr><th>Player</th><th>Tier</th><th class="num">Tokens</th><th class="num">Turns</th><th>Last active</th></tr></thead><tbody>' +
        users.slice(0, 40).map(u => '<tr data-player="' + esc(u.username) + '"><td><b>' + esc(u.username) + '</b></td><td>' + tierTag(u.subscription_status) + '</td>' +
          '<td class="num">' + tok(u.total_tokens) + '</td><td class="num">' + num(u.total_turns) + '</td><td>' + esc(String(u.last_active || '').slice(0, 10) || '—') + '</td></tr>').join('') +
        '</tbody></table></div>' + (users.length > 40 ? '<div class="note">First 40 of ' + num(users.length) + ' accounts — the Players view has the full, filterable list.</div>' : '') : '') +
      '<div class="note">Visitors are counted from the IP cache (one IP = one visitor, resolved in the background — never inline). ' + esc(ccName(cc)) + ' is a bucket, not a country, when no geo lookup has succeeded yet.</div>',
      { d: 'geo', k: cc });
  }
  function drawerReferrer(src) {
    const refs = refItems();
    const item = refs.find(r => r.key === src) || { key: src, value: 0, detail: null };
    const det = item.detail || {};
    const totalRefs = sum(uniquesSeries()) || 0;
    const countries = Object.keys(det.countries || {}).map(cc => ({ key: cc, label: ccName(cc), value: Number(det.countries[cc]) || 0 }))
      .sort((a, b) => b.value - a.value);
    openDrawer('traffic · referrer', src,
      '<div class="dgrid">' +
      '<div class="dstat"><span class="t">Unique visitors · window ' + esc(S.win) + '</span><span class="v">' + num(item.value) + '</span></div>' +
      '<div class="dstat"><span class="t">Share of visitor-days</span><span class="v">' + pct(item.value, totalRefs) + '</span></div>' +
      '<div class="dstat"><span class="t">First seen</span><span class="v">' + esc(dayOf(det.first_seen)) + '</span></div>' +
      '<div class="dstat"><span class="t">Last seen</span><span class="v">' + esc(dayOf(det.last_seen)) + '</span></div></div>' +
      (countries.length ? '<div class="sub">Where these visitors are · all ' + num(countries.length) + '</div>' + hbars(countries, { fmt: num, unit:'visitors', class:"geo-list", click: i => 'data-geo="' + esc(i.key) + '"' })
        : emptyState('No geo resolved for this source yet', '◌')) +
      '<div class="note">A source counts each IP once, and the window filters on that visitor’s last visit from the source. There is no per-day history per source in the visit log — first/last seen is the honest answer, and it is read straight from the log.</div>' +
      (item.value === 0 ? '<div class="note">Nothing from this source in the current window — switch the window to <b>All</b> to see its lifetime visitors.</div>' : ''),
      { d: 'referrer', k: src });
  }
  function drawerGeos() {
    const items = geoItems();
    const totalVisitors = sum(uniquesSeries()) || 0;
    openDrawer('traffic · countries', num(items.length) + ' buckets',
      '<div class="sub">Every country in the visit log · window ' + esc(S.win) + '</div>' +
      '<div class="tbl-wrap"><table class="mix-table"><thead><tr><th>Country</th><th class="num">Visitors</th><th class="num">Share</th><th class="num">Accounts</th><th></th></tr></thead><tbody>' +
      items.map(i => {
        const n = USERS().filter(u => (u.country_code || '??') === i.key).length;
        return '<tr data-geo="' + esc(i.key) + '"><td>' + esc(ccFlag(i.key)) + ' ' + esc(i.label) + '</td>' +
          '<td class="num">' + num(i.value) + '</td><td class="num">' + pct(i.value, totalVisitors) + '</td>' +
          '<td class="num">' + num(n) + '</td><td><button class="icon-btn" data-geo="' + esc(i.key) + '">open →</button></td></tr>';
      }).join('') + '</tbody></table></div>' +
      '<div class="note">One IP = one visitor, resolved from the geo cache in the background. Buckets like “Unknown (no geo yet)” are shown as themselves, never dropped.</div>',
      { d: 'geos' });
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
    const rows = active === 'all' ? entries : entries.filter(e => bucketOf(e) === active);
    const label = b => b === 'all' ? 'All' : (b === 'unknown' ? 'legacy / unknown' : b);
    return '<div class="sub">Ledger rows · ' + (active === 'all' ? 'all buckets' : esc(label(active))) +
        ' (' + num(rows.length) + ' of ' + num(entries.length) + ' loaded)</div>' +
      '<div class="chips">' + LEDGER_BUCKETS.filter(b => b === 'all' || counts[b] > 0 || active === b)
        .map(b => '<button type="button" class="chip' + (b === active ? ' on' : '') + '" data-ledgerbucket="' + b + '">' +
          esc(label(b)) + ' · ' + num(counts[b] || 0) + '</button>').join('') + '</div>' +
      '<div class="tbl-wrap"><table class="mix-table ledger-rows"><thead><tr><th>When</th><th>Action</th><th>Model</th>' +
        '<th class="num">Tokens</th><th>Bucket</th><th class="num">Pool after</th></tr></thead><tbody>' +
        rows.slice(0, 60).map(e => '<tr><td>' + esc(String(e.ts || '').replace('T', ' ').slice(0, 16)) + '</td>' +
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
                campaigns: stats.total_campaigns, tokens: stats.total_tokens, ai_calls: Object.values(stats.providers || {}).reduce((a, p) => a + (p.calls || 0), 0), visits: (stats.visits || {}).total },
      revenue: { total: rev.total || 0, mrr: rev.mrr || 0, transactions: rev.transactions || 0, month_revenue: rev.month_revenue || 0, month_key: rev.month_key || '', today: byDate[new Date().toISOString().slice(0, 10)] || 0,
                 paying_customers: Object.keys(customers).filter(u => customers[u].sek > 0).length, by_date: byDate, by_product: [], by_country: [], customers: Object.values(customers).sort((a, b) => b.sek - a.sek),
                 conversion_pct: users.length ? +(Object.keys(customers).filter(u => customers[u].sek > 0).length / users.length * 100).toFixed(1) : 0 },
      value: { turns: 0, tokens: stats.total_tokens, ai_calls: 0, tokens_per_sek: null, kr_per_1m_tokens: null },
      series: { api_calls_day: stats.api_daily ? Object.keys(stats.api_daily).reduce((a, k) => { a[k] = stats.api_daily[k].calls; return a; }, {}) : {},
                visits_day: (stats.visits || {}).by_day || {}, revenue_day: byDate, signups_day: {} },
      usage: { providers: stats.providers || {}, models: stats.models || {} },
      traffic: { total: (stats.visits || {}).total, by_country: [], referrers: (stats.visits || {}).by_referrer || {} },
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
      if (!S.billing) { try { S.billing = await api('/api/admin/billing'); } catch (e) { S.billing = null; } }
      render();
      stampFooter();
      if (opts && opts.quiet) toast('Refreshed');
    } catch (e) {
      $('#view').innerHTML = '<div class="err-state"><h2>⚠ Could not load the console</h2><p>' + esc(e.message) + '</p>' +
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
    if (el) el.textContent = 'data as of ' + stamp(iso) + ' · window ' + S.win;
    const nf = $('#nav-stamp');
    if (nf) nf.textContent = 'updated ' + stamp(iso);
    const nr = $('#nav-rev');
    if (nr) nr.textContent = sek(REV().total);
    const np = $('#nav-players');
    if (np) np.textContent = num(TOT().accounts);
    const nfb = $('#nav-fb');
    if (nfb) nfb.textContent = S.feedback && S.feedback.items ? num(S.feedback.items.length) : '';
  }

  async function loadFeedback(force) {
    if (S.feedback && !force) return;
    try { S.feedback = await api('/api/admin/feedback'); } catch (e) { S.feedback = { items: [], error: e.message }; }
  }

  /* ────────────────────────────── render + router ────────────────────────────── */
  const VIEWS = { overview: viewOverview, revenue: viewRevenue, players: viewPlayers, usage: viewUsage, traffic: viewTraffic, feedback: viewFeedback, system: viewSystem };

  function render() {
    $$('#nav .nav-item').forEach(b => {
      const on = b.dataset.view === S.view;
      b.classList.toggle('cur', on);
      if (on) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
    });
    $$('#win-seg button').forEach(b => b.classList.toggle('on', b.dataset.win === S.win));
    const crumb = $('#crumbs');
    if (crumb) crumb.innerHTML = '<b>' + esc(S.view.charAt(0).toUpperCase() + S.view.slice(1)) + '</b><span class="sep">/</span>' + esc(S.win);
    const fn = VIEWS[S.view] || viewOverview;
    $('#view').innerHTML = fn();
    wireView();
    stampFooter();
    syncHash(false, true);
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
      case 'player': return drawerPlayer(k, state.t || 'summary');
      case 'traffic': return drawerTraffic();
      case 'day': return drawerDay(k);
      case 'geo': return drawerGeo(k);
      case 'geos': return drawerGeos();
      case 'referrer': return drawerReferrer(k);
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
    render();
  }

  /* ────────────────────────────── events ────────────────────────────── */
  function openWith(t, fn) { lastTrigger = t; return fn(); }
  document.addEventListener('click', async function (ev) {
    const t = ev.target.closest('[data-view],[data-win],[data-metric],[data-rev],[data-tmetric],[data-expand],' +
      '[data-drill],[data-slice],[data-key],[data-tx],[data-player],[data-model],[data-action],[data-ref],[data-geo],[data-country],[data-georange],[data-tier],[data-day],[data-ledgerbucket],[data-csvmodel],' +
      '[data-csv],[data-sort],[data-page],[data-frole],[data-fstatus],[data-fcountry],[data-fcode],[data-clear],[data-fbrange],[data-fbmail],[data-tab],[data-act],[data-bucket],[data-product],[data-pool],[data-code]');
    if (!t) return;
    const d = t.dataset;

    if (d.view) { go(d.view); return; }
    if (d.win) { S.win = d.win; syncHash(true, true); load(); return; }
    if (d.metric) { S.metric = d.metric; render(); return; }
    if (d.tmetric) { S.trafficMetric = d.tmetric; render(); return; }
    if ('georange' in d) { loadGeoRange(d.georange); return; }
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
      if (v === 'traffic') return openWith(t, drawerTraffic);
      if (v === 'geo') return openWith(t, drawerGeos);
      if (v === 'usage:calls' || v.indexOf('usage') === 0) { S.view = 'usage'; return render(); }
      if (v === 'players') { S.view = 'players'; return render(); }
      return;
    }
    /* Donut-slices: egen data-nyckel först (data-slicekey sätts alltid av donut()),
       sedan label-texten som sista utväg. Utan nyckeln gissade vi på text. */
    if (d.slice != null && t.closest('.card')) {
      if (d.product || d.action || d.tier || d.ref || d.geo || d.model) { /* faller igenom nedan */ }
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
    if (d.ref) return openWith(t, () => drawerReferrer(d.ref));
    if (d.geo) return openWith(t, () => drawerGeo(d.geo));
    if (d.country) return openWith(t, () => drawerCountry(d.country));
    if (d.tier) return openWith(t, () => drawerTier(d.tier));
    if (d.action) return openWith(t, () => drawerAction(d.action));
    if (d.day) return openWith(t, () => drawerDay(d.day));
    if (d.key) {
      const k = d.key;
      if ((USAGE().models || {})[k]) return openWith(t, () => drawerModel(k));
      if (refItems().some(r => r.key === k)) return openWith(t, () => drawerReferrer(k));
      if (geoItems().some(g => g.key === k)) return openWith(t, () => drawerGeo(k));
      if ((REV().by_country || []).some(c => c.cc === k)) return openWith(t, () => drawerCountry(k));
      if ((REV().by_month || []).some(m => m.key === k)) return openWith(t, () => drawerBucket(k, (REV().by_month || []).find(m => m.key === k).sek));
      return;
    }
    if (d.product) return openWith(t, () => drawerProduct(d.product));
    if (d.tx) return openWith(t, () => drawerLedger(d.tx));
    if (d.bucket != null && t.classList.contains('vcol')) return openWith(t, () => drawerBucket(d.bucket, Number(d.val) || 0));
    if (d.player) return openWith(t, () => drawerPlayer(d.player));
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
    if (what === 'visits') return csvDownload('visits.csv', [['day','requests','unique_visitors']]
      .concat(Object.keys(visitsSeries()).sort().map(d => [d, visitsSeries()[d], (uniquesSeries()[d] || 0)])));
    if (what === 'referrers') return csvDownload('referrers.csv', [['source','visitors_in_window','share_of_visitor_days','top_countries','first_seen','last_seen']]
      .concat(refItems().map(r => {
        const det = r.detail || {};
        const cc = Object.keys(det.countries || {}).sort((a, b) => det.countries[b] - det.countries[a]).slice(0, 4)
          .map(c => c + ':' + det.countries[c]).join(' ');
        return [r.key, r.value, pct(r.value, sum(uniquesSeries())), cc, dayOf(det.first_seen), dayOf(det.last_seen)];
      })));
    if (what === 'countries') return csvDownload('countries.csv', [['cc','country','visitors','share_of_visitor_days','accounts']]
      .concat(geoItems().map(i => [i.key, i.label, i.value, pct(i.value, sum(uniquesSeries())),
        USERS().filter(u => (u.country_code || '??') === i.key).length])));
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
