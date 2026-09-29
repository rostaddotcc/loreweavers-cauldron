// ═══════════════════════════════════════════════════════════════
// 🏮 local.js — Local AI / Ollama relay client (v1), 2026-09-29.
//
// Server är hjärnan, spelarens maskin är munnen: prepare/commit går
// mot huset (dnd.rostad.cc), själva DM-texten genereras lokalt mot
// userstyrd Ollama. base_url lever ALDRIG på servern — blott i denna
// flikens localStorage. Model-ids: 'local:<ollama-name>'.
//
// Loaded as a classic script AFTER api.js/i18n.js. Public surface:
//   window.LocalAI = { detectOllama, listLocalModels, getNumCtx,
//     buildPickerOptions, renderLocalGroup, renderSettingsRow,
//     onSettingsOpen, relay }
// Backend contract (built in parallel, code against EXACTLY):
//   POST /api/chat/local/prepare {message, model_id, num_ctx}
//     → {step_id, kind:'generate', ollama:{model,messages,options}, deadline}
//   POST /api/chat/local/commit  {step_id, content, reasoning}
//     → EXACT same JSON as /api/chat (reply, reasoning, model_id, tokens,
//       turn_count, new_npcs, roll_requests, ascii_art, effects,
//       guardian_pending, world…). Errors: 409 drift / 410 expired /
//       429 cap / 503 feature off.
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
  async function serverFetch(path, body) {
    let res;
    try {
      res = await fetch(path, {
        method: 'POST',
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

  // ── picker group ─────────────────────────────────────────────
  // Exact contract label (sketch §2b) for the green state; status suffixes
  // otherwise. Gray ⇒ models visible but disabled + install hint.
  function buildPickerOptions() {
    const det = _detect || { status: 'gray' };
    const cached = _readModelCache();
    const models = (cached && cached.models) || [];
    const st = det.status;
    const label = st === 'green'
      ? '🏮 Lokalt — din egen maskin'
      : st === 'yellow'
        ? '🏮 Lokalt — din egen maskin (CORS-blockerad)'
        : '🏮 Lokalt — din egen maskin (Ollama hittas inte)';
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
    if (lab) lab.textContent = statusText().replace(/^[🟢🟡⚪]\s*/, '');
    if (corsHint) {
      corsHint.style.display = st === 'yellow' ? '' : 'none';
      corsHint.innerHTML = 'Run Ollama with <code style="color:var(--gold)">' + esc(originsHint()) + '</code> so this page may read it.';
    }
  }

  const BTN_STYLE = 'background:rgba(0,0,0,.3);border:1px solid var(--edge,var(--gold));color:var(--bone-bright);padding:.25rem .6rem;border-radius:4px;cursor:pointer;font-size:.78rem';
  const IN_STYLE = 'width:100%;box-sizing:border-box;background:rgba(0,0,0,.35);border:1px solid var(--edge,#3a3550);color:var(--bone-bright);padding:.3rem .5rem;border-radius:4px;font-size:.72rem';

  function renderSettingsRow(dmSel) {
    if (!dmSel || document.getElementById('local-row')) { updateRowUi(); return; }
    _dmSel = dmSel;
    const ctx = getNumCtx();
    dmSel.insertAdjacentHTML('afterend', `
      <div class="mpc-hint" id="local-row" style="display:flex;flex-direction:column;gap:.35rem;margin-top:.4rem">
        <div style="display:flex;align-items:center;gap:.4rem;flex-wrap:wrap">
          <span id="local-dot" aria-hidden="true">⚪</span>
          <span id="local-status">Ollama not found on this machine</span>
          <button type="button" id="local-refresh" title="Re-scan this machine for Ollama" style="${BTN_STYLE}">⟳</button>
          <label style="margin-left:auto;display:flex;align-items:center;gap:.3rem">ctx
            <select id="local-num-ctx" title="Model context window sent with every local turn" style="${BTN_STYLE}">
              ${[8192, 16384, 32768].map(v => `<option value="${v}"${v === ctx ? ' selected' : ''}>${(v / 1024)}k</option>`).join('')}
            </select>
          </label>
        </div>
        <div id="local-cors-hint" style="display:none"></div>
        <input id="local-base" type="text" spellcheck="false" autocomplete="off"
          placeholder="http://127.0.0.1:11434 — set host and port if you run Ollama somewhere else"
          value="${esc(_get(LS_BASE) || '')}" style="${IN_STYLE}" />
      </div>`);
    const baseIn = document.getElementById('local-base');
    const ctxSel = document.getElementById('local-num-ctx');
    const refresh = document.getElementById('local-refresh');
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
    updateRowUi();
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
  async function streamOllama(base, ollama, onToken, onReasoning) {
    const ac = new AbortController();
    let idleTimer = null;
    const armIdle = () => {
      clearTimeout(idleTimer);
      idleTimer = setTimeout(() => ac.abort(), IDLE_STREAM_MS);
    };
    armIdle();
    let resp;
    try {
      resp = await fetch(base + '/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: ollama.model,
          messages: ollama.messages,
          options: ollama.options || {},
          stream: true,
        }),
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
    let buf = '', content = '', reasoning = '';
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
          if (line.indexOf('data:') !== 0) continue;
          let j;
          try { j = JSON.parse(line.slice(5)); } catch (e) { continue; }
          const mc = (j.message && j.message.content) || '';
          const mr = (j.message && j.message.reasoning) || '';
          if (mr) { reasoning += mr; if (onReasoning) onReasoning(mr); }
          if (mc) { content += mc; if (onToken) onToken(mc); }
          // j.done / eval_count: token stats are the server's job at commit.
        }
      }
    } catch (e) {
      clearTimeout(idleTimer);
      if (e.kind) throw e;
      throw _terr('ollama_down', 'The stream to your machine broke off');
    }
    clearTimeout(idleTimer);
    return { content, reasoning };
  }

  async function oneTurn(messageText, modelId, det, onToken, onReasoning) {
    if (onToken) onToken('');      // reset signal
    if (onReasoning) onReasoning('');
    const step = await serverFetch('/api/chat/local/prepare', {
      message: messageText,
      model_id: modelId,
      num_ctx: getNumCtx(),
    });
    const gen = await streamOllama(det.base, step.ollama || {}, onToken, onReasoning);
    return await serverFetch('/api/chat/local/commit', {
      step_id: step.step_id,
      content: gen.content,
      reasoning: gen.reasoning || undefined,
    });
  }

  // Returns the EXACT /api/chat JSON shape. 409 (turn drift) → whole relay
  // re-runs once. 410 (step expired/used) → surfaced, never retried.
  async function relay(messageText, modelId, onToken, onReasoning) {
    const det = await detectOllama(false);
    if (det.status !== 'green' || !det.base) {
      throw _terr('ollama_down',
        det.status === 'yellow'
          ? 'Ollama is blocked by CORS — run: ' + originsHint()
          : 'Ollama not reachable on this machine');
    }
    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        return await oneTurn(messageText, modelId, det, onToken, onReasoning);
      } catch (e) {
        // 409 turn drift: another tab advanced the campaign mid-stream →
        // re-run the WHOLE relay once (fresh prepare, regenerate).
        if (e && e.status === 409 && attempt === 0) continue;
        throw e;
      }
    }
    throw _terr('server', 'Local relay failed');
  }

  window.LocalAI = {
    detectOllama,
    listLocalModels,
    getNumCtx,
    buildPickerOptions,
    renderLocalGroup,
    renderSettingsRow,
    onSettingsOpen,
    relay,
  };
})();
