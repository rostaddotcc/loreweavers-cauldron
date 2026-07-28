/**
 * 🌐 api.js — Frontend ↔ Backend-brygga för Mörkrets Rike
 *
 * MOCK-läge: Sätt MOCK = false när backend körs.
 * I MOCK-läge fungerar alla sidor fristående med localStorage-data.
 */
const API = (() => {
  const MOCK = true; // ← Byt till false när backend är live
  const BASE = '';   // Samma origin i Docker (backend servar frontend)

  // ── Fetch-wrapper med felhantering ──
  async function req(path, opts = {}) {
    try {
      const res = await fetch(BASE + path, {
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', ...opts.headers },
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
          { id: 'mimo-v2', name: 'MiMo V2', provider: 'mimo', vision: true, local: false },
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

    // ── Export ──
    exportUrl() {
      return MOCK ? null : BASE + '/api/campaign/export';
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
