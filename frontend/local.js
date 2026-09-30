// ═══════════════════════════════════════════════════════════════
// 🏮 local.js — Local AI / Ollama relay client (v1), 2026-09-29.
//
// Server är hjärnan, spelarens maskin är munnen: prepare/commit går
// mot huset (dnd.rostad.cc), själva DM-texten genereras lokalt mot
// userstyrd Ollama. base_url lever ALDRIG på servern — blott i denna
// flikens localStorage. Model-ids: 'local:<ollama-name>'.
//
// v2 (2026-09-30): campaign meta local_pipeline 'dm'|'full'. 'full' = the
// whole turn runs through the player's Ollama as a HOP CHAIN: prepare/
// commit responses may carry {kind:'generate', chain:…, ollama:{…}} and
// relay loops hop→hop until the final done JSON (chat-shape, unchanged).
// 'dm'-campaigns see the exact v1 responses (no chain field ⇒ treated as
// the v1 path). PATCH /api/campaign/local-pipeline flips the mode.
//
// Loaded as a classic script AFTER api.js/i18n.js. Public surface:
//   window.LocalAI = { detectOllama, listLocalModels, getNumCtx,
//     buildPickerOptions, renderLocalGroup, renderSettingsRow,
//     onSettingsOpen, relay, getPipeline, setPipeline, setPipelineCache }
// Backend contract (built in parallel, code against EXACTLY):
//   POST /api/chat/local/prepare {message, model_id, num_ctx}
//     → {step_id, kind:'generate', chain:'rollcheck'|'dm',
//        ollama:{model,messages,options[,options.format:'json']}, deadline}
//   POST /api/chat/local/commit  {step_id, content, reasoning}
//     → EXACT same JSON as /api/chat (reply, reasoning, model_id, tokens,
//       turn_count, new_npcs, roll_requests, ascii_art, effects,
//       guardian_pending, world…) OR the next hop
//       {step_id, kind:'generate', chain:'guardian'|'extract'|'repair'|
//       'search', ollama:{…}}. Errors: 409 drift / 410 expired /
//       429 cap (full: ~300/dag) / 503 feature off.
// ═══════════════════════════════════════════════════════════════
(function () {
  'use strict';

  const LS_BASE    = 'dnd_ollama_base';       // user-typed http(s)://host:port
  const LS_LASTBASE = 'dnd_ollama_lastbase';  // last green base (fallback hint)
  const LS_MODELS  = 'dnd_local_models';      // {ts, models:[{name,size}]}
  const LS_NUMCTX  = 'dnd_ollama_num_ctx';    // '8192' | '16384' | '32768'

  const PING_TIMEOUT_MS = 2500;
  const CACHE_TTL_MS    = 5 * 60 * 1000;
  const IDLE_STREAM_MS  = 180 * 1000; // player hardware, no server timeout

  let _detect = null;   // {ts, status:'green'|'yellow'|'gray', base, models?}
  let _models = null;   // {ts, models:[{name,size}]}
  let _dmSel  = null;   // settings select reference (for post-refresh re-render)
  let _curId  = '';     // last known current model id (local:…) for re-renders

  // ── tiny helpers ─────────────────────────────────────────────
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g,
      c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }
  function _get(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }
  function _set(key, val) { try { localStorage.setItem(key, val); } catch (e) { /* private mode */ } }
  // i18n passthrough (2026-09-30 leak-sweep): chrome strings are Swedish-keyed
  // and live in i18n.js's T — EN mode renders English.
  function _t(s) { return (typeof I18N !== 'undefined' && I18N.t) ? I18N.t(s) : s; }

  function normalizeBase(u) {
    let s = String(u || '').trim().replace(/\/+$/, '');
    if (!s) return null;
    if (!/^https?:\/\//i.test(s)) s = 'http://' + s; // '127.0.0.1:11434' accepted
    if (!/^https?:\/\/[\w.\-[::]+(:\d+)?$/i.test(s)) return null;
    return s;
  }

  function originsHint() {
    return 'OLLAMA_ORIGINS=' + location.origin + ' ollama serve';
  }

  function gb(bytes) {
    const n = Number(bytes) || 0;
    return n ? (n / 1073741824).toFixed(1) + ' GB' : '? GB';
  }

  function _terr(kind, detail, status) {
    const e = new Error(detail || kind);
    e.kind = kind;           // 'ollama_down' | 'timeout' | 'server'
    if (status != null) e.status = status;
    return e;
  }

  // Same-origin server call (mirrors api.js req(): cookies + 401 redirect +
  // typed error with .status). Never sends the user's base URL to the server.
  async function serverFetch(path, body, method) {
    let res;
    try {
      res = await fetch(path, {
        method: method || 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
    } catch (e) { throw _terr('server', 'Could not reach the Cauldron (' + path + ')'); }
    if (res.status === 401) {
      if (!location.pathname.includes('login')) location.href = 'login.html';
      throw _terr('server', 'Session expired', 401);
    }
    if (!res.ok) {
      const j = await res.json().catch(() => ({ detail: res.statusText }));
      const msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail || res.statusText);
      throw _terr('server', msg || ('HTTP ' + res.status), res.status);
    }
    return res.json();
  }

  // ── detection ────────────────────────────────────────────────
  // Candidates: user-typed base (explicit host+port control) first, then the
  // 127.0.0.1/localhost defaults (127.0.0.1 BEFORE localhost — Safari edges).
  function candidateBases() {
    const out = [];
    const custom = normalizeBase(_get(LS_BASE));
    if (custom) out.push(custom);
    out.push('http://127.0.0.1:11434', 'http://localhost:11434');
    return out;
  }

  async function withTimeout(url, opts, ms) {
    const ac = new AbortController();
    const t = setTimeout(() => ac.abort(), ms);
    try { return await fetch(url, Object.assign({}, opts, { signal: ac.signal })); }
    finally { clearTimeout(t); }
  }

  // Returns 'ok' + models | 'cors' (port answers, read blocked) | 'dead'.
  async function pingTags(base) {
    try {
      const res = await withTimeout(base + '/api/tags', {}, PING_TIMEOUT_MS);
      if (!res.ok) return 'dead';
      const j = await res.json();
      return { ok: true, models: (j.models || []).map(m => ({ name: m.name, size: m.size || 0 })) };
    } catch (e) {
      if (e && e.name === 'AbortError') return 'dead';
      // TypeError: CORS-blocked or connection refused — look identical to JS.
      // Disambiguate with an opaque no-cors ping: resolves ⇒ port open ⇒ CORS.
      try { await withTimeout(base + '/api/tags', { mode: 'no-cors' }, PING_TIMEOUT_MS); return 'cors'; }
      catch (e2) { return 'dead'; }
    }
  }

  async function detectOllama(force) {
    if (!force && _detect && Date.now() - _detect.ts < CACHE_TTL_MS) return _detect;
    let yellowBase = null;
    for (const base of candidateBases()) {
      const r = await pingTags(base);
      if (r && r.ok) {
        _detect = { ts: Date.now(), status: 'green', base };
        _set(LS_LASTBASE, base);
        _models = { ts: Date.now(), models: r.models };
        _set(LS_MODELS, JSON.stringify(_models));
        updateRowUi();
        if (_dmSel) renderLocalGroup(_dmSel);
        return _detect;
      }
      if (r === 'cors' && !yellowBase) yellowBase = base;
    }
    if (yellowBase) {
      _detect = { ts: Date.now(), status: 'yellow', base: yellowBase };
    } else {
      _detect = { ts: Date.now(), status: 'gray', base: null };
    }
    updateRowUi();
    if (_dmSel) renderLocalGroup(_dmSel);
    return _detect;
  }

  function _readModelCache() {
    if (_models && Date.now() - _models.ts < CACHE_TTL_MS) return _models;
    try {
      const raw = JSON.parse(_get(LS_MODELS) || 'null');
      if (raw && Array.isArray(raw.models)) { _models = raw; return raw; }
    } catch (e) { /* ignore */ }
    return null;
  }

  async function listLocalModels(force) {
    if (!force) { const c = _readModelCache(); if (c) return c.models; }
    const det = await detectOllama(force);
    if (det.status === 'green') {
      const r = await pingTags(det.base);
      if (r && r.ok) {
        _models = { ts: Date.now(), models: r.models };
        _set(LS_MODELS, JSON.stringify(_models));
        updateRowUi();
        if (_dmSel) renderLocalGroup(_dmSel);
        return _models.models;
      }
    }
    const c = _readModelCache();
    return c ? c.models : [];
  }

  function getNumCtx() {
    const v = parseInt(_get(LS_NUMCTX), 10);
    return ([8192, 16384, 32768].includes(v)) ? v : 16384;
  }

  // ── pipeline (v2): 'dm' = house guards/books (v1 chain), 'full' = the
  // whole cauldron runs on the player's machine (DM + rollcheck + guardian
  // + extract + repair + search hops; house only summaries/TTS). Campaign
  // meta via PATCH /api/campaign/local-pipeline; cached per-campaign here.
  let _pipeline = 'dm';
  let _pipelineUnsupported = false; // backend wave older than the PATCH route — 404/405/501
  function getPipeline() { return _pipeline; }
  function setPipelineCache(p) { _pipeline = (p === 'full') ? 'full' : 'dm'; }
  async function setPipeline(p) {
    try {
      const r = await serverFetch('/api/campaign/local-pipeline', { pipeline: p }, 'PATCH');
      setPipelineCache((r && r.pipeline) || p);
      return r;
    } catch (e) {
      if (e && (e.status === 404 || e.status === 405 || e.status === 501)) _pipelineUnsupported = true;
      throw e;
    }
  }

  // ── picker group ─────────────────────────────────────────────
  // Exact contract label (sketch §2b) for the green state; status suffixes
  // otherwise. Gray ⇒ models visible but disabled + install hint.
  // 2026-09-30: labels go through I18N.t() (sv-nyckel + i18n.js-key) — EN-chrome
  // shows English, a Swedish campaign keeps the Swedish group header.
  function buildPickerOptions() {
    const det = _detect || { status: 'gray' };
    const cached = _readModelCache();
    const models = (cached && cached.models) || [];
    const st = det.status;
    const _t = (s) => (typeof I18N !== 'undefined' && I18N.t) ? I18N.t(s) : s;
    const label = st === 'green'
      ? _t('🏮 Lokalt — din egen maskin')
      : st === 'yellow'
        ? _t('🏮 Lokalt — din egen maskin (CORS-blockerad)')
        : _t('🏮 Lokalt — din egen maskin (Ollama hittas inte)');
    const dis = st !== 'green';
    let opts;
    if (models.length) {
      opts = models.map(m =>
        `<option value="local:${esc(m.name)}"${dis ? ' disabled style="color:var(--bone-dim)"' : ''}>${esc(m.name)} · ${gb(m.size)}</option>`
      ).join('');
    } else {
      opts = `<option disabled style="color:var(--bone-dim)">${st === 'green'
        ? 'no models yet — ollama pull qwen3:14b'
        : 'install: curl -fsSL https://ollama.com/install.sh | sh'}</option>`;
    }
    return `<optgroup class="local-og" label="${esc(label)}">${opts}</optgroup>`;
  }

  function renderLocalGroup(selEl, currentModelId) {
    if (!selEl) return;
    _dmSel = selEl;
    if (currentModelId !== undefined) _curId = String(currentModelId || '');
    selEl.querySelectorAll('.local-og').forEach(el => el.remove());
    selEl.insertAdjacentHTML('beforeend', buildPickerOptions());
    const cur = _curId;
    if (cur && cur.indexOf('local:') === 0) {
      try { selEl.value = cur; } catch (e) { /* option may be absent while gray */ }
    }
    try { syncPipelineUi(); } catch (e) { /* row not rendered yet */ }
  }

  // ── settings row (status dot + label, base input, ⟳, num_ctx) ──
  function statusText() {
    const st = (_detect || {}).status || 'gray';
    const n = ((_models && _models.models) || []).length;
    if (st === 'green') return `🟢 ${n} brain${n === 1 ? '' : 's'} at home`;
    if (st === 'yellow') return '🟡 Ollama answered — CORS-blocked';
    return '⚪ Ollama not found on this machine';
  }

  function updateRowUi() {
    const dot = document.getElementById('local-dot');
    const lab = document.getElementById('local-status');
    const corsHint = document.getElementById('local-cors-hint');
    const st = (_detect || {}).status || 'gray';
    if (dot) dot.textContent = st === 'green' ? '🟢' : st === 'yellow' ? '🟡' : '⚪';
    // Strip the leading status emoji correctly — without the 'u' flag a
    // character class clips only the high-surrogate of 🟢/🟡 and leaves a
    // lone surrogate in the label (caught by the 2026-09-30 jsdom pass).
    if (lab) lab.textContent = statusText().replace(/^(?:🟢|🟡|⚪)\s?/u, '');
    if (corsHint) {
      corsHint.style.display = st === 'yellow' ? '' : 'none';
      corsHint.innerHTML = 'Run Ollama with <code style="color:var(--gold)">' + esc(originsHint()) + '</code> so this page may read it. <a href="local-ai.html" target="_blank" rel="noopener" style="color:var(--arcane,#7d95c4)">Full guide: local-ai.html</a>';
    }
    // Keep the static base input in sync with the stored/normalized base
    // (unless the player is mid-edit) — the old injected row did this on
    // render; the card renders once.
    const baseIn = document.getElementById('local-base');
    if (baseIn && document.activeElement !== baseIn) {
      baseIn.value = _get(LS_BASE) || '';
    }
  }

  // ── 🏮 Local brain card (chat.html static markup, 2026-09-30) ──
  // Structure pass: the card used to be injected with
  // dmSel.insertAdjacentHTML('afterend') — ⟳, ctx, pipeline and the base-URL
  // input landed between the DM dropdown and its hint, i.e. "lite överallt".
  // chat.html now ships a dedicated <div id="local-card"> below the models
  // card in a fixed order: header (dot · status · ⟳), base URL, ctx+pipeline,
  // hints. This function only BINDS and SYNCS the static controls.
  function renderSettingsRow(dmSel, campaignPipeline) {
    if (campaignPipeline !== undefined && campaignPipeline !== null) {
      setPipelineCache(campaignPipeline);
    }
    if (!dmSel) return;
    _dmSel = dmSel;
    const card = document.getElementById('local-card');
    if (!card) return; // page without the settings menu (adventure.html)
    card.style.display = '';
    if (card._localWired) { updateRowUi(); syncPipelineUi(); return; }
    card._localWired = true;

    const baseIn = document.getElementById('local-base');
    const ctxSel = document.getElementById('local-num-ctx');
    const refresh = document.getElementById('local-refresh');

    // ctx options are data, not chrome — keep them in sync with getNumCtx.
    if (ctxSel && !ctxSel.options.length) {
      const ctx = getNumCtx();
      ctxSel.innerHTML = [8192, 16384, 32768]
        .map(v => `<option value="${v}"${v === ctx ? ' selected' : ''}>${(v / 1024)}k</option>`).join('');
    }

    // Honest hint: an HTTPS page cannot reach a plain-HTTP non-loopback host
    // (mixed content). Warn as soon as such a base is typed, before the probe.
    const _isLoop = (h) => /^(127\.|localhost|\[?::1\]?)/i.test(h);
    const _baseWarn = () => {
      if (!baseIn) return;
      const v = (baseIn.value || '').trim();
      if (!v) return;
      try {
        const u = new URL(/^https?:\/\//i.test(v) ? v : 'http://' + v);
        if (u.protocol === 'http:' && location.protocol === 'https:' && !_isLoop(u.hostname)) {
          baseIn.style.borderColor = 'var(--blood-bright,#a33)';
          baseIn.title = 'Browsers block plain-HTTP calls from this HTTPS page unless the host is your own machine (127.x/localhost). Use https:// (e.g. tailscale serve) for other boxes.';
          return;
        }
      } catch (e) { /* not a URL yet */ }
      baseIn.style.borderColor = '';
      baseIn.title = '';
    };
    baseIn && baseIn.addEventListener('input', _baseWarn);
    _baseWarn();
    if (baseIn) baseIn.addEventListener('change', async () => {
      const n = normalizeBase(baseIn.value);
      _set(LS_BASE, n || baseIn.value.trim());
      baseIn.value = _get(LS_BASE) || '';
      _baseWarn();
      _detect = null;
      try { await detectOllama(true); await listLocalModels(true); } catch (e) { console.warn('localai:', e); }
    });
    if (ctxSel) ctxSel.addEventListener('change', () => _set(LS_NUMCTX, ctxSel.value));
    if (refresh) refresh.addEventListener('click', async () => {
      refresh.textContent = '⟳…';
      try { _detect = null; await detectOllama(true); await listLocalModels(true); }
      catch (e) { console.warn('localai:', e); }
      refresh.textContent = '⟳';
    });
    // ── pipeline selector ──
    const pipeSel = document.getElementById('local-pipeline');
    if (pipeSel) pipeSel.addEventListener('change', async () => {
      const want = pipeSel.value;
      try {
        await setPipeline(want);
        _localToast('🏮 ' + (want === 'full'
          ? _t('Hela grytan kokar hemma — huset vakar bara över summeringar')
          : _t('Huset vakar över grytan igen')));
      } catch (e) {
        pipeSel.value = getPipeline(); // revert the visual selection
        _localToast('⚠ ' + (e && e.message ? e.message : _t('Kunde inte byta pipeline')));
      }
      syncPipelineUi();
    });
    updateRowUi();
    syncPipelineUi();
  }

  function _localToast(msg) {
    try { if (typeof toast === 'function') toast(msg); } catch (e) { /* noop */ }
  }

  // Reflect campaign state in the pipeline row: value = cached pipeline,
  // disabled unless the chosen DM is a 🏮 local model (the PATCH would also
  // 400 server-side — better to say it before the click fails).
  function syncPipelineUi() {
    const pipeSel = document.getElementById('local-pipeline');
    if (!pipeSel) return;
    const hint = document.getElementById('local-pipeline-hint');
    const cur = String(((_dmSel && _dmSel.value) || _curId || ''));
    const isLocal = cur.indexOf('local:') === 0;
    pipeSel.value = getPipeline();
    // Backend wave may predate the PATCH route (404/405 on first try) — stay
    // honest instead of toasting a raw error on every click.
    if (_pipelineUnsupported) {
      pipeSel.disabled = true;
      if (hint) hint.textContent = 'Whole-Cauldron mode is still being rolled out to the house — try again soon.';
      return;
    }
    pipeSel.disabled = !isLocal;
    if (!isLocal) {
      if (hint) hint.textContent = 'Pick a 🏮 model as your DM first to unlock the pipeline choice.';
    } else if (getPipeline() === 'full') {
      if (hint) hint.textContent = 'Full cauldron at home: DM, dice, Lorekeeper and memory all run on your machine. The house only does summaries + TTS. Cap ~300 turns/day.';
    } else {
      if (hint) hint.textContent = 'House keeps watch: your machine tells the story; the house rolls the dice and keeps the books. Cap ~100 turns/day.';
    }
  }

  // Hooked from toggleSettingsMenu() — detection NEVER runs on the page-load
  // hot path; only when ⚙ opens (or ⟳/base-change above).
  async function onSettingsOpen() {
    try {
      await detectOllama(false); // 5-min cache respected; force-refresh is ⟳'s job
      await listLocalModels(false);
    } catch (e) { console.warn('localai:', e); }
  }

  // ── relay: prepare → stream from the player's Ollama → commit ──
  // onToken/onReasoning receive DELTAS. A call with '' as delta is a RESET
  // signal (a 409-regeneration starts the stream over — caller must clear).
  //
  // v2 (pipeline 'full'): prepare/commit hop responses carry
  // {kind:'generate', chain:'rollcheck'|'dm'|'guardian'|'extract'|'repair'|
  // 'search', ollama:{…}} — run EACH hop through the player's own Ollama
  // exactly like the DM hop, commit, repeat until a done JSON arrives (no
  // 'kind'). Only the 'dm' hop streams visible tokens; JSON hops stream
  // with onToken=null so raw payloads never paint the narration bubble,
  // while thinking deltas still flush to onReasoning. onHop(chain) fires
  // before each non-dm hop so the caller can show a status line.
  //
  // chain_lost tradeoff: hop responses carry no turn_count/effects — the
  // final done JSON is the only house-shape payload. If a hop AFTER the dm
  // hop already committed fails (network/410/503/empty), the turn is
  // valid and saved server-side; only enrichment is missing. Re-running
  // the whole turn or falling back to the house DM would corrupt a
  // committed story — so we resolve with a SYNTHETIC done built from the
  // streamed DM text: {reply, reasoning, model_id, chainIncomplete:true,
  // chainHop}. The caller renders the narration bubble from it; effects
  // etc. were committed server-side and surface on the next turn/refresh.
  const MAX_CHAIN_HOPS = 8;

  async function streamOllama(base, ollama, onToken, onReasoning) {
    const ac = new AbortController();
    let idleTimer = null;
    const armIdle = () => {
      clearTimeout(idleTimer);
      idleTimer = setTimeout(() => ac.abort(), IDLE_STREAM_MS);
    };
    armIdle();
    let resp;
    // Real Ollama honors format at the payload TOP level (not inside options) —
    // json hops would silently return prose otherwise. Verified against ollama
    // 0.15 in the v2 chain E2E 2026-09-30.
    const body = {
      model: ollama.model,
      messages: ollama.messages,
      options: ollama.options || {},
      stream: true,
    };
    if (body.options.format === 'json') {
      body.format = 'json';
      delete body.options.format;
      if (body.options.think === false) {
        body.think = false;
        delete body.options.think;
      }
    }
    try {
      resp = await fetch(base + '/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: ac.signal,
      });
    } catch (e) {
      clearTimeout(idleTimer);
      if (e && e.name === 'AbortError') throw _terr('timeout', 'Ollama did not answer the chat request in time');
      throw _terr('ollama_down', 'Ollama refused the chat request — is it still running?');
    }
    if (!resp.ok || !resp.body) {
      clearTimeout(idleTimer);
      throw _terr('server', 'Ollama returned HTTP ' + resp.status, resp.status);
    }
    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let buf = '', content = '', reasoning = '', evalCount = 0;
    try {
      for (;;) {
        let chunk;
        try { chunk = await reader.read(); }
        catch (e) {
          throw (e && e.name === 'AbortError')
            ? _terr('timeout', 'Your machine went quiet')
            : _terr('ollama_down', 'The stream to your machine broke off');
        }
        armIdle();
        if (chunk.done) break;
        buf += dec.decode(chunk.value, { stream: true });
        let nl;
        while ((nl = buf.indexOf('\n')) >= 0) {
          const line = buf.slice(0, nl).trim();
          buf = buf.slice(nl + 1);
          // Ollama streams bare JSON lines; some proxies prefix "data: ".
          const payload = line.indexOf('data:') === 0 ? line.slice(5).trim() : line;
          if (!payload) continue;
          let j;
          try { j = JSON.parse(payload); } catch (e) { continue; }
          const mc = (j.message && j.message.content) || '';
          // Ollama streams thinking under "thinking" (some builds "reasoning").
          const mr = (j.message && (j.message.reasoning || j.message.thinking)) || '';
          if (mr) { reasoning += mr; if (onReasoning) onReasoning(mr); }
          if (mc) { content += mc; if (onToken) onToken(mc); }
          if (j.done && typeof j.eval_count === 'number') evalCount = j.eval_count;
        }
      }
    } catch (e) {
      clearTimeout(idleTimer);
      if (e.kind) throw e;
      throw _terr('ollama_down', 'The stream to your machine broke off');
    }
    clearTimeout(idleTimer);
    return { content, reasoning, evalCount };
  }

  async function oneTurn(messageText, modelId, det, onToken, onReasoning, onHop) {
    if (onToken) onToken('');      // reset signal
    if (onReasoning) onReasoning('');
    let dmContent = '', dmReasoning = '', dmTokens = 0, dmCommitted = false, hops = 0;
    const synthetic = (hopName) => ({
      reply: dmContent,
      reasoning: dmReasoning || undefined,
      model_id: modelId,
      tokens: dmTokens || undefined,
      chainIncomplete: true,
      chainHop: hopName,
      dmCommitted: true,          // caller must NOT rerun or house-fallback
    });
    let hop = await serverFetch('/api/chat/local/prepare', {
      message: messageText,
      model_id: modelId,
      num_ctx: getNumCtx(),
    });
    for (;;) {
      const chain = hop.chain || 'dm';     // missing chain field ⇒ v1 dm hop
      const isDm = chain === 'dm';
      if (onHop) { try { onHop(chain); } catch (e) { /* cosmetic */ } }
      let gen, next;
      try {
        // JSON hops: no visible tokens (raw payload must never paint the
        // bubble), but stream normally so thinking deltas still flush.
        gen = await streamOllama(det.base, hop.ollama || {}, isDm ? onToken : null, onReasoning);
        if (!gen.content.trim()) {
          // Thinking model burned the whole budget on reasoning (CPU-boxes do
          // this): the server would 400 on empty content → typed error so the
          // chat shows the house-DM fallback menu instead of a hard failure.
          if (dmCommitted) return synthetic(chain);
          throw _terr('ollama_down', gen.reasoning.trim()
            ? 'Your model thought but never spoke — raise the context or pick a faster model'
            : 'Your model returned nothing');
        }
        next = await serverFetch('/api/chat/local/commit', {
          step_id: hop.step_id,
          content: gen.content,
          reasoning: gen.reasoning || undefined,
          tokens: gen.evalCount || undefined,
        });
      } catch (e) {
        if (e && e.status === 409) throw e; // drift ANYWHERE → whole-turn rerun (relay)
        // A hop AFTER the dm hop failed (network/410/429/503/empty): the
        // turn is committed and valid — only enrichment is missing.
        // Never rerun, never house-fallback (that would double-advance).
        if (dmCommitted) return synthetic(chain);
        throw e; // dm-hop failures keep the exact v1 error surface
      }
      if (isDm) {
        dmContent = gen.content;
        dmReasoning = gen.reasoning;
        dmTokens = gen.evalCount;
        dmCommitted = true;
      }
      if (!next || next.kind !== 'generate') return next; // final done JSON
      if (++hops >= MAX_CHAIN_HOPS) {
        if (dmCommitted) return synthetic(next.chain || '?');
        throw _terr('server', 'Local relay chain never ended (' + MAX_CHAIN_HOPS + ' hops)');
      }
      hop = next;
    }
  }

  // Returns the EXACT /api/chat JSON shape. 409 (turn drift) → whole relay
  // re-runs once. 410 (step expired/used) → surfaced, never retried.
  // v2: pass onHop(chain) to receive per-hop progress for full-mode chains.
  async function relay(messageText, modelId, onToken, onReasoning, onHop) {
    const det = await detectOllama(false);
    if (det.status !== 'green' || !det.base) {
      throw _terr('ollama_down',
        det.status === 'yellow'
          ? 'Ollama is blocked by CORS — run: ' + originsHint()
          : 'Ollama not reachable on this machine');
    }
    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        return await oneTurn(messageText, modelId, det, onToken, onReasoning, onHop);
      } catch (e) {
        // 409 turn drift (dm-hop prepare/commit round — post-dm 409s never
        // reach here, oneTurn absorbs them into the chain_lost payload):
        // another tab advanced the campaign mid-stream → re-run the WHOLE
        // relay once (fresh prepare, regenerate).
        if (e && e.status === 409) {
          if (attempt === 0) continue;
          throw _terr('ollama_down', 'The Cauldron rejected the turn twice — something drifted mid-story');
        }
        throw e;
      }
    }
    throw _terr('ollama_down', 'Local relay failed');
  }

  window.LocalAI = {
    detectOllama,
    listLocalModels,
    getNumCtx,
    getPipeline,
    setPipeline,
    setPipelineCache,
    buildPickerOptions,
    renderLocalGroup,
    renderSettingsRow,
    onSettingsOpen,
    relay,
  };
})();
