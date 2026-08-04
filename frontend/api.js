/**
 * 🌐 api.js — Frontend ↔ Backend bridge for The Lore Weaver's Cauldron
 *
 * MOCK mode: Set MOCK = false when the backend runs.
 * In MOCK mode every page works standalone with localStorage data.
 */
const API = (() => {
  const MOCK = false; // Backend live at dnd.rostad.cc
  const BASE = '';   // Same origin in Docker (backend serves frontend)

  // ── Debug log (Ctrl+Shift+D) ──
  const _debugLog = [];
  let _debugPanel = null;
  let _debugVisible = false;

  function _dbg(type, msg, detail) {
    const entry = { t: new Date().toLocaleTimeString('en-GB'), type, msg, detail };
    _debugLog.push(entry);
    if (_debugLog.length > 200) _debugLog.shift();
    if (_debugVisible) _renderDebug();
    console.log(`[DEBUG ${type}]`, msg, detail || '');
  }

  function _renderDebug() {
    if (!_debugPanel) return;
    const body = _debugPanel.querySelector('.dbg-body');
    if (!body) return;
    body.innerHTML = _debugLog.slice(-80).map(e =>
      `<div class="dbg-line dbg-${e.type}"><span class="dbg-t">${e.t}</span> ${e.msg}${e.detail ? ' <span class="dbg-d">' + String(e.detail).slice(0, 120) + '</span>' : ''}</div>`
    ).join('');
    body.scrollTop = body.scrollHeight;
  }

  function _toggleDebug() {
    _debugVisible = !_debugVisible;
    if (_debugVisible && !_debugPanel) {
      _debugPanel = document.createElement('div');
      _debugPanel.id = 'debug-panel';
      _debugPanel.innerHTML = `
        <div class="dbg-header">🐛 Debug <button class="dbg-clear">Clear</button><button class="dbg-close">✕</button></div>
        <div class="dbg-body"></div>`;
      _debugPanel.querySelector('.dbg-close').onclick = _toggleDebug;
      _debugPanel.querySelector('.dbg-clear').onclick = () => { _debugLog.length = 0; _renderDebug(); };
      document.body.appendChild(_debugPanel);
      const style = document.createElement('style');
      style.textContent = `
        #debug-panel{position:fixed;bottom:0;right:0;width:420px;max-height:45vh;z-index:99999;
          background:#0a0a12;border:1px solid #333;border-radius:8px 0 0 0;font-family:'IBM Plex Mono',monospace;
          font-size:11px;display:flex;flex-direction:column;box-shadow:0 -4px 20px rgba(0,0,0,.6)}
        .dbg-header{padding:6px 10px;background:#111;color:#8f8;display:flex;gap:8px;align-items:center;font-size:12px}
        .dbg-header button{background:#222;border:1px solid #444;color:#aaa;padding:2px 8px;border-radius:3px;cursor:pointer;font-size:10px}
        .dbg-header button:hover{background:#333;color:#fff}
        .dbg-body{overflow-y:auto;padding:6px 10px;flex:1;max-height:38vh}
        .dbg-line{padding:2px 0;border-bottom:1px solid #1a1a2a;line-height:1.4}
        .dbg-t{color:#555;margin-right:6px}
        .dbg-d{color:#666;font-style:italic}
        .dbg-ok{color:#6d6}.dbg-err{color:#f66}.dbg-warn{color:#fa0}.dbg-info{color:#8af}.dbg-api{color:#a8f}`;
      document.head.appendChild(style);
    }
    if (_debugPanel) _debugPanel.style.display = _debugVisible ? 'flex' : 'none';
    if (_debugVisible) _renderDebug();
  }

  document.addEventListener('keydown', e => {
    if (e.ctrlKey && e.shiftKey && e.key === 'D') { e.preventDefault(); _toggleDebug(); }
  });

  // ── Fetch wrapper with error handling + debug ──
  async function req(path, opts = {}) {
    const t0 = performance.now();
    _dbg('api', `${opts.method || 'GET'} ${path}`);
    try {
      // FormData (file upload) sets its own Content-Type with boundary
      const isForm = typeof FormData !== 'undefined' && opts.body instanceof FormData;
      const headers = isForm
        ? { ...opts.headers }
        : { 'Content-Type': 'application/json', ...opts.headers };
      const res = await fetch(BASE + path, {
        credentials: 'include',
        headers,
        ...opts,
      });
      const ms = Math.round(performance.now() - t0);
      if (res.status === 401) {
        _dbg('err', `${path} → 401 (${ms}ms)`);
        if (!location.pathname.includes('login')) location.href = 'login.html';
        throw new Error('Session expired');
      }
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        let msg = typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail);
        if (!msg || msg === 'null') msg = res.statusText || 'error';
        // Visa alltid HTTP-statusen så spelaren ser "HTTP 429", "HTTP 500" etc.
        const full = `HTTP ${res.status}: ${msg}`;
        _dbg('err', `${path} → ${res.status} (${ms}ms)`, full);
        const e = new Error(full);
        e.status = res.status;
        throw e;
      }
      if (res.status === 204) return {};
      let data;
      try {
        data = await res.json();
      } catch (parseErr) {
        // 200 med tom kropp → "tomt svar" istället för kryptiskt SyntaxError
        const e = new Error(`HTTP ${res.status}: empty response from server`);
        _dbg('err', `${path} → EMPTY BODY (${ms}ms)`);
        throw e;
      }
      _dbg('ok', `${path} → 200 (${ms}ms)`);
      return data;
    } catch (e) {
      // Nätverksfel (fetch itself failed) — ersätt "Failed to fetch" med något tydligt
      if (e && e.name === 'TypeError' && /fetch/i.test(e.message || '')) {
        const netErr = new Error('Connection lost — network error. Check your connection.');
        _dbg('err', `${path} NETWORK FAILURE`, e.message);
        if (typeof toast === 'function') toast('⚠ ' + netErr.message);
        throw netErr;
      }
      if (e.message !== 'Session expired') {
        _dbg('err', `${path} CAUGHT`, e.message);
        if (typeof toast === 'function') toast('⚠ ' + e.message);
      }
      throw e;
    }
  }

  // ── MOCK data (localStorage) ──
  const mock = {
    campaign: null,
    _load() {
      const raw = localStorage.getItem('dnd_mock_campaign');
      if (raw) this.campaign = JSON.parse(raw);
      return this.campaign;
    },
    _save() {
      if (this.campaign) localStorage.setItem('dnd_mock_campaign', JSON.stringify(this.campaign));
    },
  };

  return {
    get mockMode() { return MOCK; },

    // ── Auth ──
    async login(username, password) {
      if (MOCK) {
        const USERS = { admin: 'rostad2026', rostad: 'drake2026', hastis: 'enhorn2026' };
        if (USERS[username] === password) {
          sessionStorage.setItem('dnd_user', username);
          return { ok: true, username, role: username === 'admin' ? 'admin' : 'player' };
        }
        throw new Error('Invalid username or password');
      }
      return req('/api/login', { method: 'POST', body: JSON.stringify({ username, password }) });
    },

    async register(username, password, email) {
      if (MOCK) throw new Error('Account creation is only available on the live server');
      return req('/api/register', { method: 'POST', body: JSON.stringify({ username, password, email: email || null }) });
    },

    async resetPassword(username, password) {
      if (MOCK) throw new Error('Password reset is only available on the live server');
      return req('/api/auth/reset-password', { method: 'POST', body: JSON.stringify({ username, password }) });
    },

    async setTurnCap(username, turnCap) {
      if (MOCK) return { ok: true };
      return req('/api/admin/user/' + encodeURIComponent(username) + '/turn-cap', {
        method: 'PUT', body: JSON.stringify({ turn_cap: turnCap }),
      });
    },

    async logout() {
      sessionStorage.removeItem('dnd_user');
      sessionStorage.removeItem('dnd_token');
      if (!MOCK) await req('/api/logout', { method: 'POST' }).catch(() => {});
    },

    async me() {
      if (MOCK) {
        const u = sessionStorage.getItem('dnd_user');
        return u ? { username: u, role: u === 'admin' ? 'admin' : 'player' } : null;
      }
      return req('/api/me');
    },

    // ── Models ──
    async models() {
      if (MOCK) {
        return [
          { id: 'qwen3.8-max', name: 'Qwen 3.8 Max', provider: 'dashscope', vision: true, local: false },
          { id: 'qwen3.7-plus', name: 'Qwen 3.7 Plus', provider: 'dashscope', vision: true, local: false },
          { id: 'deepseek-v4-pro', name: 'DeepSeek V4 Pro', provider: 'deepseek', vision: false, local: false },
          { id: 'deepseek-v4-flash', name: 'DeepSeek V4 Flash', provider: 'deepseek', vision: false, local: false },
          { id: 'mimo-v2.5', name: 'MiMo 2.5', provider: 'mimo', vision: true, local: false },
          { id: 'mimo-v2.5-pro', name: 'MiMo 2.5 Pro', provider: 'mimo', vision: true, local: false },
          { id: 'ollama:qwen3:8b', name: 'Qwen3 8B (local)', provider: 'ollama', vision: false, local: true },
        ];
      }
      return req('/api/models');
    },

    // ── Campaign (multiple per user) ──
    async getCampaign() {
      if (MOCK) {
        const c = mock._load();
        return { campaign: c ? this._shapeCampaign(c) : null };
      }
      try {
        const state = await req('/api/campaign');
        return { campaign: this._shapeCampaign(state) };
      } catch (e) {
        if (e.message.includes('404') || e.message.includes('Ingen') || e.message.includes('No campaign') || e.message.includes('not found')) return { campaign: null };
        throw e;
      }
    },

    async getUsage() {
      if (MOCK) {
        return { campaign_id: 'mock', campaign_name: 'Mock', turns: 0, active_campaign: { models: {}, background_tokens: 0 }, account_total: { models: {}, prompt_tokens: 0, completion_tokens: 0, total_tokens: 0, background_tokens: 0 } };
      }
      return req('/api/campaign/usage');
    },

    async listCampaigns() {
      if (MOCK) {
        const c = mock._load();
        return { campaigns: c ? [this._shapeCampaign(c)] : [] };
      }
      return req('/api/campaigns');
    },

    // Normalize backend state → frontend view
    _shapeCampaign(s) {
      if (!s) return null;
      return {
        id: s.meta?.campaign_id ?? s.campaign_id,
        name: s.meta?.campaign_name ?? s.name ?? 'The Lore Weaver\'s Cauldron',
        character: s.character || {},
        sessions: s.meta?.session_count || 1,
        day: s.world?.time || '—',
        location: s.world?.current_location ?? s.location ?? 'Unknown',
        turn_count: s.meta?.turn_count ?? s.turn_count ?? 0,
        opening_key: s.opening_key || s.meta?.opening_key || 'default',
        world: s.world || {},
        _raw: s,
      };
    },

    async createCampaign(name = '', language = 'sv') {
      // Default to "An Untitled Adventure" if name empty
      const campaignName = (name && name.trim()) ? name.trim() : 'An Untitled Adventure';
      if (MOCK) {
        mock.campaign = {
          meta: { campaign_id: 'mock-' + Date.now(), campaign_name: campaignName, turn_count: 0, session_count: 1, created: new Date().toISOString(), last_updated: new Date().toISOString(), language },
          character: {}, inventory: [], currency: { pp: 0, gp: 0, ep: 0, sp: 0, cp: 0 },
          npcs: [], quests: [], world: { current_location: '', time: '', weather: '' },
        };
        mock._save();
        return { ok: true, campaign_id: mock.campaign.meta.campaign_id };
      }
      return req('/api/campaign', { method: 'POST', body: JSON.stringify({ name: campaignName, language }) });
    },

    async endCampaign(campaignId) {
      if (MOCK) {
        mock.campaign = null;
        localStorage.removeItem('dnd_mock_campaign');
        return { ok: true };
      }
      if (!campaignId) throw new Error('campaign_id required');
      return req('/api/campaign?campaign_id=' + encodeURIComponent(campaignId), { method: 'DELETE' });
    },

    async activateCampaign(campaignId) {
      if (MOCK) return { ok: true };
      return req('/api/campaign/activate', { method: 'POST', body: JSON.stringify({ campaign_id: campaignId }) });
    },

    // ── Character updates (HP, inventory, etc.) ──
    async updateCharacter(data) {
      if (MOCK) {
        const c = mock._load();
        if (c) {
          c.character = { ...c.character, ...data };
          mock._save();
        }
        return { ok: true };
      }
      return req('/api/campaign/character', { method: 'PATCH', body: JSON.stringify(data) });
    },

    // ── Campaign language (DM narration language) ──
    async updateCampaignLanguage(language) {
      if (MOCK) {
        const c = mock._load();
        if (c) { c.meta = c.meta || {}; c.meta.language = language; mock._save(); }
        return { ok: true, language };
      }
      return req('/api/campaign/language', { method: 'PATCH', body: JSON.stringify({ language }) });
    },

    // ── Lorekeeper model (admin only, per campaign) ──
    async setGuardianModel(modelId) {
      if (MOCK) return { ok: true, guardian_model: modelId };
      return req('/api/campaign/guardian-model', { method: 'PATCH', body: JSON.stringify({ guardian_model: modelId }) });
    },

    // ── Extraction model (per campaign — bakgrund: fakta, dagbok, summaries) ──
    async setExtractionModel(modelId) {
      if (MOCK) return { ok: true, extraction_model: modelId };
      return req('/api/campaign/extraction-model', { method: 'PATCH', body: JSON.stringify({ extraction_model: modelId }) });
    },
    async setDmModel(modelId) {
      if (MOCK) return { ok: true, dm_model: modelId };
      return req('/api/campaign/dm-model', { method: 'PATCH', body: JSON.stringify({ dm_model: modelId }) });
    },

    // ── Attachments (pdf/md/txt) ──
    async uploadAttachment(file) {
      if (MOCK) throw new Error('Not available in mock mode');
      const fd = new FormData();
      fd.append('file', file);
      return req('/api/campaign/attachments', { method: 'POST', body: fd });
    },

    attachmentUrl(attId) {
      return MOCK ? null : BASE + '/api/campaign/attachments/' + attId;
    },

    async deleteAttachment(attId) {
      if (MOCK) throw new Error('Not available in mock mode');
      return req('/api/campaign/attachments/' + attId, { method: 'DELETE' });
    },

    // ── Avatars (player, DM, NPCs) ──
    async uploadAvatar(kind, file) {
      if (MOCK) throw new Error('Not available in mock mode');
      const fd = new FormData();
      fd.append('kind', kind);
      fd.append('file', file);
      return req('/api/campaign/avatar', { method: 'POST', body: fd });
    },

    avatarUrl(kind) {
      return MOCK ? null : BASE + '/api/campaign/avatar/' + encodeURIComponent(kind);
    },

    async deleteAvatar(kind) {
      if (MOCK) throw new Error('Not available in mock mode');
      return req('/api/campaign/avatar/' + encodeURIComponent(kind), { method: 'DELETE' });
    },

    // ── AI-avatar (StepFun step-image-edit-2 — prompt byggs automatiskt i backend) ──
    // mode: "new" = full generation (ny bild), "edit" = image-edit på befintlig
    // prompt: valfri fri text från användaren — väger tyngst, auto-prompten blir kontext.
    async generateAvatar(kind, seed, mode, prompt) {
      if (MOCK) throw new Error('Not available in mock mode');
      return req('/api/campaign/avatar/generate', {
        method: 'POST',
        body: JSON.stringify({ kind, seed, mode: mode || 'new', prompt: prompt || '' }),
      });
    },

    // ── Transcript (latest messages) ──
    async getTranscript() {
      if (MOCK) {
        return { messages: [] };
      }
      return req('/api/campaign/transcript');
    },

    // ── Fact registry (Phase 3: extracted facts) ──
    async getFacts(category = null) {
      if (MOCK) return { facts: [], stats: {} };
      const q = category ? '?category=' + encodeURIComponent(category) : '';
      return req('/api/facts' + q);
    },

    // ── Engine room (live debug logs) ──
    async getDebugLogs(since = 0, level = null) {
      if (MOCK) return { logs: [], now: Date.now() / 1000, buffered: 0 };
      let q = '?since=' + since;
      if (level) q += '&level=' + encodeURIComponent(level);
      return req('/api/debug/logs' + q);
    },

    // ── World building (prompt + optional files → structured world data) ──
    async buildWorld(prompt, fileList = [], modelId = 'step-3.7-flash') {
      if (MOCK) {
        await new Promise(r => setTimeout(r, 1800));
        return {
          ok: true,
          merged: { characters: 1, npcs: 4, locations: 3, quests: 1, lore: 6, items: 2 },
        };
      }
      const fd = new FormData();
      fd.append('prompt', prompt || '');
      fd.append('model_id', modelId);
      for (const f of fileList) fd.append('files', f);
      return req('/api/world/build', { method: 'POST', body: fd });
    },

    // ── Chat ──
    async chat(message, modelId) {
      if (MOCK) {
        // Simulated DM reply
        await new Promise(r => setTimeout(r, 1200 + Math.random() * 800));
        const replies = [
          'The darkness thickens around you. Something moves in the shadows — you hear a low, hissing breath.',
          'You step forward. The floor creaks. Ahead of you, a faint green light glows.',
          'A voice whispers your name. It comes from inside the walls. Or from inside you.',
        ];
        return { reply: replies[Math.floor(Math.random() * replies.length)], turn_count: (mock.campaign?.meta?.turn_count || 0) + 1, summary_generated: false };
      }
      return req('/api/chat', { method: 'POST', body: JSON.stringify({ message, model_id: modelId }) });
    },

    // ── Character generation ──
    async generateCharacter(prompt, modelId) {
      if (MOCK) {
        await new Promise(r => setTimeout(r, 2000));
        return { ok: true, character: { name: 'The Wanderer', race: 'Human', class: 'Adventurer', level: 5, hp: { current: 38, max: 38 }, abilities: { STR: { score: 13, mod: 1 }, DEX: { score: 14, mod: 2 }, CON: { score: 13, mod: 1 }, INT: { score: 12, mod: 1 }, WIS: { score: 13, mod: 1 }, CHA: { score: 12, mod: 1 } }, ac: 14, traits: ['Versatile', 'Survival Instinct'] } };
      }
      return req('/api/character/generate', { method: 'POST', body: JSON.stringify({ prompt, model_id: modelId }) });
    },

    // SSE-streaming variant — onEvent({type:'reasoning'|'content', text}) kallas
    // live; resolvar med {character, inventory} när 'done' kommer.
    async generateCharacterStream(prompt, modelId, onEvent = () => {}) {
      if (MOCK) {
        await new Promise(r => setTimeout(r, 1200));
        onEvent({ type: 'reasoning', text: 'The wanderer\'s fate unfolds…' });
        await new Promise(r => setTimeout(r, 800));
        return { character: { name: 'The Wanderer', race: 'Human', class: 'Adventurer', level: 5, hp: { current: 38, max: 38 }, abilities: { STR: { score: 13, mod: 1 }, DEX: { score: 14, mod: 2 }, CON: { score: 13, mod: 1 }, INT: { score: 12, mod: 1 }, WIS: { score: 13, mod: 1 }, CHA: { score: 12, mod: 1 } }, ac: 14, traits: ['Versatile', 'Survival Instinct'] }, inventory: [] };
      }
      const res = await fetch('/api/character/generate/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt, model_id: modelId }),
      });
      if (!res.ok) {
        let msg = 'HTTP ' + res.status;
        try { const j = await res.json(); msg = j.detail || j.error || msg; } catch (e) {}
        throw new Error(msg);
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let result = null;
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buffer.indexOf('\n\n')) >= 0) {
          const raw = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);
          for (const line of raw.split('\n')) {
            if (!line.startsWith('data:')) continue;
            try {
              const ev = JSON.parse(line.slice(5).trim());
              if (ev.type === 'done') result = ev;
              else onEvent(ev);
            } catch (e) {}
          }
        }
      }
      if (!result) throw new Error('Stream ended without result');
      if (result.type === 'error') throw new Error(result.message || 'unknown error');
      return result;
    },

    // ── The Forge: character vault (fristående karaktärsvalv) ──
    // Fristående karaktärsgenerering — kräver ingen aktiv kampanj.
    // Samma SSE-protokoll som generateCharacterStream.
    async vaultGenerateStream(prompt, modelId, lang, onEvent = () => {}) {
      if (MOCK) throw new Error('Not available in mock mode');
      const res = await fetch('/api/vault/generate/stream', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt, model_id: modelId, lang: lang || 'en' }),
      });
      if (!res.ok) {
        let msg = 'HTTP ' + res.status;
        try { const j = await res.json(); msg = j.detail || j.error || msg; } catch (e) {}
        throw new Error(msg);
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let result = null;
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buffer.indexOf('\n\n')) >= 0) {
          const raw = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);
          for (const line of raw.split('\n')) {
            if (!line.startsWith('data:')) continue;
            try {
              const ev = JSON.parse(line.slice(5).trim());
              if (ev.type === 'done') result = ev;
              else onEvent(ev);
            } catch (e) {}
          }
        }
      }
      if (!result) throw new Error('Stream ended without result');
      if (result.type === 'error') throw new Error(result.message || 'unknown error');
      return result;
    },

    vaultList() {
      return req('/api/vault/characters');
    },

    vaultGet(charId) {
      return req('/api/vault/characters/' + encodeURIComponent(charId));
    },

    vaultSave(payload) {
      return req('/api/vault/characters', { method: 'POST', body: JSON.stringify(payload) });
    },

    vaultDelete(charId) {
      return req('/api/vault/characters/' + encodeURIComponent(charId), { method: 'DELETE' });
    },

    vaultUse(charId) {
      return req('/api/vault/characters/' + encodeURIComponent(charId) + '/use', { method: 'POST', body: '{}' });
    },

    vaultGenerateAvatar(charId, seed, mode, prompt) {
      const body = { prompt: prompt || '' };
      if (typeof seed === 'number') body.seed = seed;
      if (mode) body.mode = mode;
      return req('/api/vault/characters/' + encodeURIComponent(charId) + '/avatar/generate', {
        method: 'POST', body: JSON.stringify(body),
      });
    },

    vaultAvatarUrl(charId) {
      return MOCK ? null : BASE + '/api/vault/characters/' + encodeURIComponent(charId) + '/avatar';
    },

    // ── Rules Oracle (Qwen-driven) ──
    async oracle(question, modelId = 'step-3.7-flash') {
      if (MOCK) {
        await new Promise(r => setTimeout(r, 900));
        return { answer: "Roll a d20 and add the relevant modifier against the DM's DC." };
      }
      return req('/api/oracle', { method: 'POST', body: JSON.stringify({ question, model_id: modelId }) });
    },

    // ── Feedback ──
    async sendFeedback({ email, message }) {
      if (MOCK) return { ok: true };
      return req('/api/feedback', { method: 'POST', body: JSON.stringify({ email: email || null, message }) });
    },

    // ── Export ──
    exportUrl() {
      return MOCK ? null : BASE + '/api/campaign/export';
    },

    // ── Save / Load / Pin / Lore / Chapter ──
    async saveCheckpoint(description = '') {
      if (MOCK) return { ok: true, save_id: 'mock-save', description };
      return req('/api/campaign/save', { method: 'POST', body: JSON.stringify({ description }) });
    },

    async listSaves() {
      if (MOCK) return { saves: [] };
      return req('/api/campaign/saves');
    },

    async loadSave(saveId) {
      if (MOCK) throw new Error('Not available in mock mode');
      return req('/api/campaign/load', { method: 'POST', body: JSON.stringify({ save_id: saveId }) });
    },

    async pinFact(fact) {
      if (MOCK) return { ok: true, pinned_facts: [fact] };
      return req('/api/campaign/pin', { method: 'POST', body: JSON.stringify({ fact }) });
    },

    async unpinFact(fact) {
      if (MOCK) return { ok: true, pinned_facts: [] };
      return req('/api/campaign/pin', { method: 'DELETE', body: JSON.stringify({ fact }) });
    },

    async addLore(text) {
      if (MOCK) return { ok: true, lore_count: 1 };
      return req('/api/campaign/lore', { method: 'POST', body: JSON.stringify({ text }) });
    },

    async consumeResource(label) {
      if (MOCK) return { ok: true };
      return req('/api/campaign/consume-resource', { method: 'POST', body: JSON.stringify({ text: label }) });
    },

    async triggerChapter(title) {
      if (MOCK) return { ok: true, title, summary: 'Chapter ended.', chapter_count: 1 };
      return req('/api/campaign/chapter', { method: 'POST', body: JSON.stringify({ title }) });
    },

    // ── TTS ──
    async ttsVoices() {
      if (MOCK) return { voices: [{ id: 'male', name: 'Narrator (male)' }, { id: 'female', name: 'Narrator (female)' }] };
      return req('/api/tts/voices');
    },

    // Live-pipeline-aktivitet (senaste loggentry för loading-animationen)
    async activity() {
      if (MOCK) return { entries: [] };
      return req('/api/campaign/activity');
    },

    async tts(text, voice, provider) {
      const res = await fetch(BASE + '/api/tts', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, voice, provider }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        const msg = typeof err.detail === 'string' ? err.detail : 'TTS error';
        throw new Error(msg);
      }
      return res.blob();
    },

    // Spara TTS-leverantör per kampanj (state.meta.tts_provider)
    async setTtsProvider(provider) {
      return req('/api/campaign/tts-settings', { method: 'POST', body: JSON.stringify({ provider }) });
    },

    // ── Combat (v25 — stridsmotorn) ──
    async combatAttack(targetId, attackRoll, damageNotation = '1d8') {
      return req('/api/combat/attack', {
        method: 'POST',
        body: JSON.stringify({ target_id: targetId, attack_roll: attackRoll, damage_notation: damageNotation }),
      });
    },

    async combatCast(opts) {
      return req('/api/combat/cast', { method: 'POST', body: JSON.stringify(opts) });
    },

    async combatBonus(action) {
      return req('/api/combat/bonus', { method: 'POST', body: JSON.stringify({ action }) });
    },

    async combatFlee(dexCheck) {
      return req('/api/combat/flee', { method: 'POST', body: JSON.stringify({ dex_check: dexCheck }) });
    },

    async combatEndTurn() {
      return req('/api/combat/end-turn', { method: 'POST' });
    },

    async combatState() {
      return req('/api/combat/state');
    },

    // ── Auth guard for pages ──
    guard() {
      if (!sessionStorage.getItem('dnd_user')) {
        location.href = 'login.html';
        return false;
      }
      return true;
    },
  };
})();
