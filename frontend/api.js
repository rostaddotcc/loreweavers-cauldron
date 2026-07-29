/**
 * 🌐 api.js — Frontend ↔ Backend-brygga för Mörkrets Rike
 *
 * MOCK-läge: Sätt MOCK = false när backend körs.
 * I MOCK-läge fungerar alla sidor fristående med localStorage-data.
 */
const API = (() => {
  const MOCK = false; // Backend live på dnd.rostad.cc
  const BASE = '';   // Samma origin i Docker (backend servar frontend)

  // ── Fetch-wrapper med felhantering ──
  async function req(path, opts = {}) {
    try {
      // FormData (filuppladdning) sätter sin egen Content-Type med boundary
      const isForm = typeof FormData !== 'undefined' && opts.body instanceof FormData;
      const headers = isForm
        ? { ...opts.headers }
        : { 'Content-Type': 'application/json', ...opts.headers };
      const res = await fetch(BASE + path, {
        credentials: 'include',
        headers,
        ...opts,
      });
      if (res.status === 401) {
        // Session utgången → tillbaka till porten
        if (!location.pathname.includes('login')) location.href = 'login.html';
        throw new Error('Session utgången');
      }
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail));
      }
      return await res.json();
    } catch (e) {
      if (e.message !== 'Session utgången' && typeof toast === 'function') {
        toast('⚠ ' + e.message);
      }
      throw e;
    }
  }

  // ── MOCK-data (localStorage) ──
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
        throw new Error('Fel användarnamn eller lösenord');
      }
      return req('/api/login', { method: 'POST', body: JSON.stringify({ username, password }) });
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

    // ── Modeller ──
    async models() {
      if (MOCK) {
        return [
          { id: 'qwen3.8-max', name: 'Qwen 3.8 Max', provider: 'dashscope', vision: true, local: false },
          { id: 'qwen3.7-plus', name: 'Qwen 3.7 Plus', provider: 'dashscope', vision: true, local: false },
          { id: 'deepseek-v4-pro', name: 'DeepSeek V4 Pro', provider: 'deepseek', vision: false, local: false },
          { id: 'deepseek-v4-flash', name: 'DeepSeek V4 Flash', provider: 'deepseek', vision: false, local: false },
          { id: 'mimo-v2.5', name: 'MiMo 2.5', provider: 'mimo', vision: true, local: false },
          { id: 'mimo-v2.5-pro', name: 'MiMo 2.5 Pro', provider: 'mimo', vision: true, local: false },
          { id: 'ollama:qwen3:8b', name: 'Qwen3 8B (lokal)', provider: 'ollama', vision: false, local: true },
        ];
      }
      return req('/api/models');
    },

    // ── Kampanj (ett spel per användare) ──
    async getCampaign() {
      if (MOCK) {
        const c = mock._load();
        return { campaign: c ? this._shapeCampaign(c) : null };
      }
      try {
        const state = await req('/api/campaign');
        return { campaign: this._shapeCampaign(state) };
      } catch (e) {
        if (e.message.includes('404') || e.message.includes('Ingen')) return { campaign: null };
        throw e;
      }
    },

    // Normalisera backend-state → frontend-vy
    _shapeCampaign(s) {
      if (!s) return null;
      return {
        id: s.meta?.campaign_id,
        name: s.meta?.campaign_name || 'Mörkrets Rike',
        character: s.character || {},
        sessions: s.meta?.session_count || 1,
        day: s.world?.time || '—',
        location: s.world?.current_location || 'Okänd',
        turn_count: s.meta?.turn_count || 0,
        opening_key: s.opening_key || s.meta?.opening_key || 'default',
        world: s.world || {},
        _raw: s,
      };
    },

    async createCampaign(mode = 'freestyle') {
      if (MOCK) {
        if (mock._load()) throw new Error('Du har redan ett aktivt äventyr');
        mock.campaign = {
          meta: { campaign_id: 'mock-' + Date.now(), campaign_name: 'Mörkrets Rike', turn_count: 0, session_count: 1, created: new Date().toISOString(), last_updated: new Date().toISOString() },
          character: {}, inventory: [], currency: { pp: 0, gp: 0, ep: 0, sp: 0, cp: 0 },
          npcs: [], quests: [], world: { current_location: '', time: '', weather: '' },
          mode,
        };
        mock._save();
        return { ok: true, campaign_id: mock.campaign.meta.campaign_id };
      }
      return req('/api/campaign', { method: 'POST' });
    },

    async endCampaign() {
      if (MOCK) {
        mock.campaign = null;
        localStorage.removeItem('dnd_mock_campaign');
        return { ok: true };
      }
      return req('/api/campaign', { method: 'DELETE' });
    },

    // ── Karaktärsuppdatering (HP, inventory m.m.) ──
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

    // ── Bilagor (pdf/md/txt) ──
    async uploadAttachment(file) {
      if (MOCK) throw new Error('Ej i mock-läge');
      const fd = new FormData();
      fd.append('file', file);
      return req('/api/campaign/attachments', { method: 'POST', body: fd });
    },

    attachmentUrl(attId) {
      return MOCK ? null : BASE + '/api/campaign/attachments/' + attId;
    },

    async deleteAttachment(attId) {
      if (MOCK) throw new Error('Ej i mock-läge');
      return req('/api/campaign/attachments/' + attId, { method: 'DELETE' });
    },

    // ── Avatarer (spelare, DM, NPCs) ──
    async uploadAvatar(kind, file) {
      if (MOCK) throw new Error('Ej i mock-läge');
      const fd = new FormData();
      fd.append('kind', kind);
      fd.append('file', file);
      return req('/api/campaign/avatar', { method: 'POST', body: fd });
    },

    avatarUrl(kind) {
      return MOCK ? null : BASE + '/api/campaign/avatar/' + encodeURIComponent(kind);
    },

    async deleteAvatar(kind) {
      if (MOCK) throw new Error('Ej i mock-läge');
      return req('/api/campaign/avatar/' + encodeURIComponent(kind), { method: 'DELETE' });
    },

    // ── Transkript (senaste meddelandena) ──
    async getTranscript() {
      if (MOCK) {
        return { messages: [] };
      }
      return req('/api/campaign/transcript');
    },

    // ── Faktaregister (Fas 3: extraherade fakta) ──
    async getFacts(category = null) {
      if (MOCK) return { facts: [], stats: {} };
      const q = category ? '?category=' + encodeURIComponent(category) : '';
      return req('/api/facts' + q);
    },

    // ── Maskinrummet (live debug-loggar) ──
    async getDebugLogs(since = 0, level = null) {
      if (MOCK) return { logs: [], now: Date.now() / 1000, buffered: 0 };
      let q = '?since=' + since;
      if (level) q += '&level=' + encodeURIComponent(level);
      return req('/api/debug/logs' + q);
    },

    // ── Världsbygge (prompt → strukturerad världdata) ──
    async buildWorld(prompt, modelId = 'qwen3.8-max') {
      if (MOCK) {
        await new Promise(r => setTimeout(r, 1800));
        return {
          ok: true,
          merged: { locations: 3, npcs: 4, lore: 6 },
          locations: [
            { name: 'Askans Dal', description: 'En dal där askan aldrig slutar falla' },
            { name: 'Den Övergivna Kvarnen', description: 'Ett ruttnande landmärke med grönt sken' },
            { name: 'Värdshuset Sista Ljuset', description: 'Det enda stället med levande eld' },
          ],
          npcs: [
            { name: 'Morvaine', role: 'Den gåtfulla trollkarlen' },
            { name: 'Kael Asksvärd', role: 'Legosoldat' },
            { name: 'Lyra Vindviska', role: 'Skogsalv, jägare' },
            { name: 'Borg Stenhand', role: 'Värdshusvärd' },
          ],
          lore: ['Askfallet började för hundra år sedan', 'Något viskar namn i mörkret'],
        };
      }
      return req('/api/world/build', { method: 'POST', body: JSON.stringify({ prompt, model_id: modelId }) });
    },

    // ── Filimport (multipart FormData → extraherad kampanjdata) ──
    async importFile(file, modelId = 'qwen3.8-max') {
      if (MOCK) {
        await new Promise(r => setTimeout(r, 1200 + Math.random() * 800));
        return {
          ok: true,
          filename: file.name,
          merged: { characters: 1, npcs: 3, locations: 2, lore: 4, items: 2 },
        };
      }
      const fd = new FormData();
      fd.append('file', file);
      fd.append('model_id', modelId);
      return req('/api/import', { method: 'POST', body: fd });
    },

    // ── Chat ──
    async chat(message, modelId) {
      if (MOCK) {
        // Simulerat DM-svar
        await new Promise(r => setTimeout(r, 1200 + Math.random() * 800));
        const replies = [
          'Mörkret tätnar runt dig. Något rör sig i skuggorna — du hör ett lågt, väsande andetag.',
          'Du kliver framåt. Golvet knakar. Framför dig glöder ett svagt, grönt ljus.',
          'En röst viskar ditt namn. Den kommer inifrån väggarna. Eller inifrån dig.',
        ];
        return { reply: replies[Math.floor(Math.random() * replies.length)], turn_count: (mock.campaign?.meta?.turn_count || 0) + 1, summary_generated: false };
      }
      return req('/api/chat', { method: 'POST', body: JSON.stringify({ message, model_id: modelId }) });
    },

    // ── Karaktärsgenerering ──
    async generateCharacter(prompt, modelId) {
      if (MOCK) {
        await new Promise(r => setTimeout(r, 2000));
        return { ok: true, character: { name: 'Vandraren', race: 'Människa', class: 'Äventyrare', level: 5, hp: { current: 38, max: 38 }, abilities: { STR: { score: 13, mod: 1 }, DEX: { score: 14, mod: 2 }, CON: { score: 13, mod: 1 }, INT: { score: 12, mod: 1 }, WIS: { score: 13, mod: 1 }, CHA: { score: 12, mod: 1 } }, ac: 14, traits: ['Mångsidig', 'Överlevnadsinstinkt'] } };
      }
      return req('/api/character/generate', { method: 'POST', body: JSON.stringify({ prompt, model_id: modelId }) });
    },

    // ── Karaktärsvalvet ──
    async vaultList() {
      if (MOCK) {
        const raw = localStorage.getItem('dnd_mock_vault');
        return { characters: raw ? JSON.parse(raw) : [] };
      }
      return req('/api/vault');
    },

    async vaultSave(character) {
      if (MOCK) {
        const raw = localStorage.getItem('dnd_mock_vault');
        const list = raw ? JSON.parse(raw) : [];
        list.unshift({ id: 'mock-' + Date.now(), character, campaign_name: 'Mock', saved_at: new Date().toISOString() });
        localStorage.setItem('dnd_mock_vault', JSON.stringify(list));
        return { ok: true };
      }
      return req('/api/vault/save', { method: 'POST', body: JSON.stringify({ character }) });
    },

    async vaultUse(charId) {
      if (MOCK) throw new Error('Ej i mock-läge');
      return req('/api/vault/use', { method: 'POST', body: JSON.stringify({ char_id: charId }) });
    },

    async vaultDelete(charId) {
      if (MOCK) {
        const raw = localStorage.getItem('dnd_mock_vault');
        const list = raw ? JSON.parse(raw) : [];
        localStorage.setItem('dnd_mock_vault', JSON.stringify(list.filter(e => e.id !== charId)));
        return { ok: true };
      }
      return req('/api/vault/' + charId, { method: 'DELETE' });
    },

    // ── Regeloraklet (Qwen-driven) ──
    async oracle(question, modelId = 'qwen3.6-flash') {
      if (MOCK) {
        await new Promise(r => setTimeout(r, 900));
        return { answer: 'Slå en d20 och lägg till relevant modifierare mot DM:ns DC.' };
      }
      return req('/api/oracle', { method: 'POST', body: JSON.stringify({ question, model_id: modelId }) });
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
      if (MOCK) throw new Error('Ej i mock-läge');
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

    async triggerChapter(title) {
      if (MOCK) return { ok: true, title, summary: 'Kapitlet avslutades.', chapter_count: 1 };
      return req('/api/campaign/chapter', { method: 'POST', body: JSON.stringify({ title }) });
    },

    // ── Auth-guard för sidor ──
    guard() {
      if (!sessionStorage.getItem('dnd_user')) {
        location.href = 'login.html';
        return false;
      }
      return true;
    },
  };
})();
