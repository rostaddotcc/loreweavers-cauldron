/* ============================================================================
 * admin-actions.js — Mission Control: every admin mutation + the feedback loader
 * ----------------------------------------------------------------------------
 * Plain classic script (no build step, no ES modules). Loaded by admin.html
 * BEFORE admin.js and exposes exactly one global: window.AdminActions.
 *
 * This file owns BEHAVIOUR ONLY. No DOM reads, no DOM writes, no toasts —
 * no `document`, no `querySelector`, no `confirm()`. The parent (admin.js)
 * renders everything, confirms destructive actions and prints the raw error
 * message we throw. A DOM write in here is a defect.
 *
 * Every /api/admin/... call below is a byte-identical port of the fetch calls
 * that used to live in the inline <script> of frontend/admin.html (verified
 * 2026-09-27): same URL, same method, same body keys, credentials:'include'.
 *
 * Surface:
 *   setCap(username, cap)                 PUT    /api/admin/user/{u}/turn-cap     {turn_cap:int}
 *   topUp(username, amount)               PUT    /api/admin/user/{u}/turn-topup   {bonus:int}
 *   grantTier(username, tier)             PUT    /api/admin/user/{u}/grant        {tier:str, days:30}
 *   setTier(username, tier, untilDays)    PUT    /api/admin/user/{u}/subscription {status:str, until:null}
 *                                         PUT    /api/admin/user/{u}/grant        {tier:str, days:int}
 *   setRole(username, role)               PUT    /api/admin/user/{u}/role         {role:str}
 *   resetTurns(username)                  PUT    /api/admin/user/{u}/turn-reset   {}
 *   createUser(username, password, role)  POST   /api/admin/user                  {username,password,role}
 *   deleteUser(username)                  DELETE /api/admin/user/{u}
 *   loadFeedback()                        GET    /api/admin/feedback              → parsed json
 *   isBusy(username) / setBusy(username, bool) / onChange
 *
 * Contract for every action:
 *   - returns a promise resolving to the parsed JSON body
 *   - non-OK response → throws Error('HTTP <status>: <server detail>')
 *     with a machine-readable err.status (401 stays distinguishable: the
 *     parent redirects to login on 401)
 *   - sets isBusy(username) for the duration and always clears it in a
 *     finally block, even when the request fails
 *   - calls AdminActions.onChange?.(username) after a successful mutation
 *     so the parent can re-fetch that row
 * ========================================================================== */

(function (root) {
  'use strict';

  // ── In-flight state, one flag per username ────────────────────────────────
  // The parent reads isBusy(username) to disable a row's buttons while its
  // request runs; we never touch the buttons ourselves.
  const _busyUsers = {};

  function isBusy(username) {
    return !!_busyUsers[username];
  }

  function setBusy(username, busy) {
    _busyUsers[username] = !!busy;
  }

  // ── Plumbing ─────────────────────────────────────────────────────────────
  const JSON_HEADERS = { 'Content-Type': 'application/json' };

  // Server detail text (FastAPI convention: {"detail": "..."}).
  // 422 returns a list of validation objects — stringify it rather than
  // printing "[object Object]" on screen. Never invent a message.
  function detailOf(data, res) {
    if (data && typeof data === 'object') {
      if (typeof data.detail === 'string') return data.detail;
      if (data.detail != null) return JSON.stringify(data.detail);
      if (typeof data.message === 'string') return data.message;
    }
    return res.statusText || '';
  }

  // One fetch path for every call: parse JSON, throw on non-OK.
  async function request(url, options) {
    const res = await fetch(url, options);
    let data = null;
    try {
      data = await res.json();
    } catch (e) {
      data = null;   // t.ex. HTML-felsida eller 204 — ingen JSON att läsa
    }
    if (!res.ok) {
      const detail = detailOf(data, res);
      const err = new Error('HTTP ' + res.status + ': ' + detail);
      err.status = res.status;   // maskinläsbart: 401 → föräldern skickar till login
      err.detail = detail;
      err.url = url;
      throw err;
    }
    return data;
  }

  // Busy-lås runt ett anrop. Släpps alltid i finally — även vid fel.
  async function withBusy(username, fn) {
    setBusy(username, true);
    try {
      return await fn();
    } finally {
      setBusy(username, false);
    }
  }

  // Efter lyckad mutation: låt föräldern uppdatera raden.
  function changed(username) {
    const cb = AdminActions.onChange;
    if (typeof cb === 'function') cb(username);
  }

  // ── Actions ──────────────────────────────────────────────────────────────

  // turn-cap: 0 = obegränsat. Gammal kod läste en input och visade toast —
  // här kommer värdet in som argument, valideringen är densamma.
  async function setCap(username, cap) {
    const val = parseInt(cap, 10);
    if (isNaN(val) || val < 0) {
      throw new Error('Turn cap must be 0 (unlimited) or a positive number');
    }
    const data = await withBusy(username, () => request(
      '/api/admin/user/' + encodeURIComponent(username) + '/turn-cap', {
        method: 'PUT',
        credentials: 'include',
        headers: JSON_HEADERS,
        body: JSON.stringify({ turn_cap: val })
      }
    ));
    changed(username);
    return data;
  }

  // Lägg turn_bonus på ett konto (förbrukas före cap-turns).
  async function topUp(username, amount) {
    const bonus = parseInt(amount, 10);
    if (isNaN(bonus) || bonus <= 0) {
      throw new Error('Bonus must be a positive number');
    }
    const data = await withBusy(username, () => request(
      '/api/admin/user/' + encodeURIComponent(username) + '/turn-topup', {
        method: 'PUT',
        credentials: 'include',
        headers: JSON_HEADERS,
        body: JSON.stringify({ bonus: bonus })
      }
    ));
    changed(username);
    return data;
  }

  // Gratis-tier i 30 dagar (samma som gamla grantTier-knappen: days hårdkodat 30).
  async function grantTier(username, tier) {
    const data = await withBusy(username, () => request(
      '/api/admin/user/' + encodeURIComponent(username) + '/grant', {
        method: 'PUT',
        credentials: 'include',
        headers: JSON_HEADERS,
        body: JSON.stringify({ tier: tier, days: 30 })
      }
    ));
    changed(username);
    return data;
  }

  /* TIERS — port av gamla setTier (frontend/admin.html rad 988-1030):
   *   free              → /subscription {status:'free',     until:null}
   *   lifetime (eller duration '0') → /subscription {status:'lifetime', until:null}
   *   tier1/tier2       → /grant {tier:'support'|'patron', days} — exakt vad ett
   *                       riktigt Stripe-köp ger (features + features_until).
   *                       days = parseInt(untilDays) || 30, klämt till 1..365.
   * untilDays är alltså antal DAGAR; null/undefined/NaN → 30 (gammalt beteende).
   */
  async function setTier(username, tier, untilDays) {
    let status = tier || 'free';
    const d = String(untilDays == null ? '' : untilDays);
    if (status === 'lifetime' || d === '0') status = 'lifetime';

    return withBusy(username, async () => {
      let data;
      if (status === 'free') {
        data = await request(
          '/api/admin/user/' + encodeURIComponent(username) + '/subscription', {
            method: 'PUT',
            credentials: 'include',
            headers: JSON_HEADERS,
            body: JSON.stringify({ status: 'free', until: null })
          }
        );
      } else if (status === 'lifetime') {
        data = await request(
          '/api/admin/user/' + encodeURIComponent(username) + '/subscription', {
            method: 'PUT',
            credentials: 'include',
            headers: JSON_HEADERS,
            body: JSON.stringify({ status: 'lifetime', until: null })
          }
        );
      } else {
        // tier1/tier2 → /grant med dagar (riktiga features, Stripe-mirror)
        const days = Math.max(1, Math.min(365, parseInt(d, 10) || 30));
        const apiTier = status === 'tier2' ? 'patron' : 'support';
        data = await request(
          '/api/admin/user/' + encodeURIComponent(username) + '/grant', {
            method: 'PUT',
            credentials: 'include',
            headers: JSON_HEADERS,
            body: JSON.stringify({ tier: apiTier, days: days })
          }
        );
      }
      changed(username);
      return data;
    });
  }

  // Rollbyte. confirm() låg i gamla setRole — föräldern äger bekräftelsen nu.
  async function setRole(username, role) {
    const data = await withBusy(username, () => request(
      '/api/admin/user/' + encodeURIComponent(username) + '/role', {
        method: 'PUT',
        credentials: 'include',
        headers: JSON_HEADERS,
        body: JSON.stringify({ role: role })
      }
    ));
    changed(username);
    return data;
  }

  // Nollställ turns_used för aktuell period (bonus behålls).
  // Gammal kod skickade ingen body alls (backend tar ingen Body-parameter);
  // här skickas ett tomt objekt — samma requestsemantik, inga nya nycklar.
  async function resetTurns(username) {
    const data = await withBusy(username, () => request(
      '/api/admin/user/' + encodeURIComponent(username) + '/turn-reset', {
        method: 'PUT',
        credentials: 'include',
        headers: JSON_HEADERS,
        body: JSON.stringify({})
      }
    ));
    changed(username);
    return data;
  }

  // Nytt konto. Gammal kod läste tre inputs; valideringen är densamma.
  // role faller tillbaka på backendens egen default ('player') så att
  // body-nycklarna alltid är username/password/role.
  async function createUser(username, password, role) {
    if (!username || !password) {
      throw new Error('Fill in username and password');
    }
    if (role == null || role === '') role = 'player';
    const data = await withBusy(username, () => request('/api/admin/user', {
      method: 'POST',
      credentials: 'include',
      headers: JSON_HEADERS,
      body: JSON.stringify({ username: username, password: password, role: role })
    }));
    changed(username);
    return data;
  }

  // Radera konto + kampanjer. Gammal kod frågade först — föräldern äger confirm().
  async function deleteUser(username) {
    const data = await withBusy(username, () => request(
      '/api/admin/user/' + encodeURIComponent(username), {
        method: 'DELETE',
        credentials: 'include'
      }
    ));
    changed(username);
    return data;
  }

  // Spelarfeedback. Gammal kod skrev in i #feedback-inbox och tolkade felen
  // ('API error: 500') — nu returneras payloaden orörd och fel kastas enligt
  // samma HTTP-konvention som resten, så föräldern kan rendera den själv.
  async function loadFeedback() {
    return request('/api/admin/feedback', { credentials: 'include' });
  }

  // ── Global ───────────────────────────────────────────────────────────────
  const AdminActions = {
    // Sätts av föräldern: AdminActions.onChange = (username) => { ... }
    onChange: null,

    isBusy: isBusy,
    setBusy: setBusy,

    setCap: setCap,
    topUp: topUp,
    grantTier: grantTier,
    setTier: setTier,
    setRole: setRole,
    resetTurns: resetTurns,
    createUser: createUser,
    deleteUser: deleteUser,
    loadFeedback: loadFeedback
  };

  root.AdminActions = AdminActions;
})(window);
