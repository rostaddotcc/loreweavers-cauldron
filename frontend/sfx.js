/**
 * 🔊 sfx.js — 16-bitars ljudeffekter för Mörkrets Rike
 * Allt syntas via Web Audio API. Inga ljudfiler. Äkta SNES-känsla.
 *
 * Användning: SFX.coin(), SFX.battle(), SFX.dice() …
 * Mute-toggle: SFX.toggle() (sparas i localStorage)
 */
const SFX = (() => {
  let ctx = null;
  let master = null;
  let enabled = localStorage.getItem('dnd_sfx') !== 'off';

  function ensure() {
    if (!ctx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return null;
      ctx = new AC();
      master = ctx.createGain();
      master.gain.value = 0.5;
      master.connect(ctx.destination);
    }
    if (ctx.state === 'suspended') ctx.resume();
    return ctx;
  }

  // ── Byggstenar ──
  // En ton: frekvens, start-offset (s), längd (s), vågform, volym, ev. glide
  function note(freq, start, dur, type = 'square', vol = 0.25, glideTo = null) {
    const c = ensure(); if (!c || !enabled) return;
    const t0 = c.currentTime + start;
    const osc = c.createOscillator();
    const g = c.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(freq, t0);
    if (glideTo) osc.frequency.exponentialRampToValueAtTime(glideTo, t0 + dur);
    g.gain.setValueAtTime(vol, t0);
    g.gain.exponentialRampToValueAtTime(0.001, t0 + dur);
    osc.connect(g); g.connect(master);
    osc.start(t0); osc.stop(t0 + dur + 0.03);
  }

  // Brusburst — trummor / träffar
  function noise(start, dur, vol = 0.18, hp = 1000) {
    const c = ensure(); if (!c || !enabled) return;
    const t0 = c.currentTime + start;
    const len = Math.max(1, Math.floor(c.sampleRate * dur));
    const buf = c.createBuffer(1, len, c.sampleRate);
    const d = buf.getChannelData(0);
    for (let i = 0; i < len; i++) d[i] = Math.random() * 2 - 1;
    const src = c.createBufferSource(); src.buffer = buf;
    const f = c.createBiquadFilter(); f.type = 'highpass'; f.frequency.value = hp;
    const g = c.createGain();
    g.gain.setValueAtTime(vol, t0);
    g.gain.exponentialRampToValueAtTime(0.001, t0 + dur);
    src.connect(f); f.connect(g); g.connect(master);
    src.start(t0);
  }

  // Bas-thump (kick)
  function thump(start, vol = 0.3) {
    note(120, start, 0.12, 'sine', vol, 40);
  }

  return {
    get enabled() { return enabled; },

    toggle() {
      enabled = !enabled;
      localStorage.setItem('dnd_sfx', enabled ? 'on' : 'off');
      if (enabled) this.click();
      return enabled;
    },

    // ═══════════ UI ═══════════
    // Kort tick — knappar, flikar
    click() { note(880, 0, 0.05, 'square', 0.12); },
    // Mycket subtilt — hover (används sparsamt)
    hover() { note(1300, 0, 0.025, 'sine', 0.04); },
    // Spelaren skickar ett meddelande
    send() { note(520, 0, 0.09, 'sine', 0.2, 780); },
    // DM/NPC svarar
    receive() { note(660, 0, 0.11, 'triangle', 0.18, 440); },
    // Fel / nekat
    error() { note(150, 0, 0.22, 'square', 0.25, 110); note(110, 0.12, 0.25, 'square', 0.2, 80); },
    // Porten öppnas (login klar)
    gate() {
      note(55, 0, 0.7, 'sine', 0.3, 45);           // muller
      [440, 523, 659, 880].forEach((f, i) =>       // stigande glittring
        note(f, 0.15 + i * 0.09, 0.3, 'triangle', 0.12));
    },

    // ═══════════ PENGAR ═══════════
    // Klassiskt mynt-pling (B5 → E6)
    coin() {
      note(987.77, 0, 0.08, 'square', 0.22);
      note(1318.5, 0.08, 0.4, 'square', 0.22);
    },
    // Flera mynt i rad (skattkista!)
    coins(n = 5) {
      for (let i = 0; i < n; i++) {
        note(987.77, i * 0.09, 0.06, 'square', 0.18);
        note(1318.5, i * 0.09 + 0.05, 0.12, 'square', 0.18);
      }
    },

    // ═══════════ TÄRNINGAR ═══════════
    dice() {
      for (let i = 0; i < 7; i++) {
        note(200 + Math.random() * 300, i * 0.06, 0.04, 'square', 0.12);
      }
      note(150, 0.45, 0.1, 'sine', 0.25, 70);      // slutgiltig duns
    },
    // Naturlig 20!
    crit() {
      this.coin();
      [1318.5, 1568, 1975.5, 2637].forEach((f, i) =>
        note(f, 0.2 + i * 0.07, 0.25, 'square', 0.18));
    },
    // Naturlig 1…
    fail() {
      [329.6, 261.6, 220, 174.6].forEach((f, i) =>
        note(f, i * 0.18, 0.22, 'triangle', 0.2));
    },

    // ═══════════ STRID ═══════════
    // Skada
    damage() {
      noise(0, 0.15, 0.25, 400);
      note(300, 0, 0.18, 'sawtooth', 0.25, 80);
    },
    // Helande
    heal() {
      [523.25, 659.25, 783.99, 1046.5].forEach((f, i) =>
        note(f, i * 0.07, 0.2, 'sine', 0.18));
    },

    /**
     * ⚔️ KAMPJINGEL — ~5 sekunder, D-moll, 150 BPM.
     * Drivande bas, lead-melodi, trummor. Spelas när strid börjar.
     */
    battle() {
      const c = ensure(); if (!c || !enabled) return;
      const E8 = 0.2;   // åttondel @ 150 BPM

      // Öppnings-stab
      note(73.42, 0, 0.15, 'square', 0.3);
      note(146.83, 0, 0.15, 'square', 0.25);
      noise(0, 0.3, 0.2, 2000);

      // Bas (triangle) — 24 åttondelar
      const bass = [
        73.42,73.42,73.42,73.42,73.42,73.42,73.42,73.42,   // D2
        65.41,65.41,65.41,65.41,                            // C2
        58.27,58.27,58.27,58.27,                            // Bb1
        55.00,55.00,55.00,55.00,                            // A1
        73.42,73.42,73.42,73.42,                            // D2 (tillbaka)
      ];
      bass.forEach((f, i) => note(f, i * E8, E8 * 0.9, 'triangle', 0.32));

      // Lead (square) — melodi på fjärdedelar
      const lead = [
        [0.0, 587.33], [0.4, 698.46], [0.8, 880], [1.2, 783.99],
        [1.6, 698.46], [2.0, 659.25], [2.4, 587.33], [2.8, 523.25],
        [3.2, 587.33], [3.6, 659.25], [4.0, 698.46], [4.4, 880],
      ];
      lead.forEach(([t, f]) => note(f, t, 0.35, 'square', 0.2));

      // Trummor — kick på 1 & 3, virvel på 2 & 4
      for (let t = 0; t < 4.8; t += 0.8) thump(t, 0.3);
      for (let t = 0.4; t < 4.8; t += 0.8) noise(t, 0.1, 0.15, 3000);

      // Final ackord — D-moll, hållen + crash
      [146.83, 174.61, 220, 293.66].forEach(f => note(f, 4.8, 0.9, 'square', 0.18));
      note(1174.66, 4.8, 0.7, 'square', 0.15);
      noise(4.8, 0.5, 0.2, 2000);
    },

    // ═══════════ FANFARER ═══════════
    // Level up!
    levelup() {
      [261.6, 329.6, 392, 523.25, 659.25, 783.99, 1046.5].forEach((f, i) =>
        note(f, i * 0.08, 0.15, 'square', 0.18));
      note(1046.5, 0.6, 0.6, 'square', 0.2);
      note(1318.5, 0.6, 0.6, 'triangle', 0.15);
    },
    // Seger
    victory() {
      [392, 523.25, 659.25].forEach((f, i) => note(f, i * 0.15, 0.12, 'square', 0.2));
      note(783.99, 0.45, 0.4, 'square', 0.22);
      note(659.25, 1.0, 0.12, 'square', 0.2);
      [783.99, 523.25, 659.25, 392].forEach(f => note(f, 1.15, 1.0, 'square', 0.16));
      note(1046.5, 1.15, 1.0, 'triangle', 0.14);
    },
  };
})();

// ── Global mute-knapp för topbarer ──
function sfxToggleBtn() {
  const on = SFX.toggle();
  const btns = document.querySelectorAll('.sfx-btn');
  btns.forEach(b => b.textContent = on ? '🔊' : '🔇');
  return on;
}
