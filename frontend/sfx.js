/**
 * 🔊 sfx.js — 16-bit sound effects for The Lore Weaver's Cauldron
 * Everything is synthesized via the Web Audio API. No audio files. Genuine SNES feel.
 *
 * Usage: SFX.coin(), SFX.battle(), SFX.dice() …
 * Mute toggle: SFX.toggle() (saved in localStorage)
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

  // ── Building blocks ──
  // One note: frequency, start offset (s), duration (s), waveform, volume, optional glide
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

  // Noise burst — drums / hits
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

  // Bass thump (kick)
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
    // Short tick — buttons, tabs
    click() { note(880, 0, 0.05, 'square', 0.12); },
    // Very subtle — hover (used sparingly)
    hover() { note(1300, 0, 0.025, 'sine', 0.04); },
    // Typewriter tick — soft blip while chat text reveals. Pitch walks a
    // small pentatonic scale so the ticks never drone. Respects mute.
    type(i = 0) {
      const scale = [440, 493.88, 523.25, 587.33, 659.25, 783.99];
      note(scale[i % scale.length], 0, 0.022, 'square', 0.045);
    },
    // Typewriter tick for an NPC voice — slightly lower, warmer
    typeNpc(i = 0) {
      const scale = [329.63, 349.23, 392, 440, 493.88, 587.33];
      note(scale[i % scale.length], 0, 0.024, 'triangle', 0.06);
    },
    // Typewriter completes — soft little chime up
    typeDone() { note(880, 0, 0.05, 'sine', 0.07, 1174.66); },
    // The player sends a message
    send() { note(520, 0, 0.09, 'sine', 0.2, 780); },
    // DM/NPC responds
    receive() { note(660, 0, 0.11, 'triangle', 0.18, 440); },
    // Error / denied
    error() { note(150, 0, 0.22, 'square', 0.25, 110); note(110, 0.12, 0.25, 'square', 0.2, 80); },
    // The gate opens (login complete)
    gate() {
      note(55, 0, 0.7, 'sine', 0.3, 45);           // rumble
      [440, 523, 659, 880].forEach((f, i) =>       // rising shimmer
        note(f, 0.15 + i * 0.09, 0.3, 'triangle', 0.12));
    },

    // ═══════════ COINS ═══════════
    // Classic coin ping (B5 → E6)
    coin() {
      note(987.77, 0, 0.08, 'square', 0.22);
      note(1318.5, 0.08, 0.4, 'square', 0.22);
    },
    // Several coins in a row (treasure chest!)
    coins(n = 5) {
      for (let i = 0; i < n; i++) {
        note(987.77, i * 0.09, 0.06, 'square', 0.18);
        note(1318.5, i * 0.09 + 0.05, 0.12, 'square', 0.18);
      }
    },

    // ═══════════ DICE ═══════════
    dice() {
      for (let i = 0; i < 7; i++) {
        note(200 + Math.random() * 300, i * 0.06, 0.04, 'square', 0.12);
      }
      note(150, 0.45, 0.1, 'sine', 0.25, 70);      // final thud
    },
    // Natural 20!
    crit() {
      this.coin();
      [1318.5, 1568, 1975.5, 2637].forEach((f, i) =>
        note(f, 0.2 + i * 0.07, 0.25, 'square', 0.18));
    },
    // Natural 1…
    fail() {
      [329.6, 261.6, 220, 174.6].forEach((f, i) =>
        note(f, i * 0.18, 0.22, 'triangle', 0.2));
    },

    // ═══════════ BATTLE ═══════════
    // Damage
    damage() {
      noise(0, 0.15, 0.25, 400);
      note(300, 0, 0.18, 'sawtooth', 0.25, 80);
    },
    // Healing
    heal() {
      [523.25, 659.25, 783.99, 1046.5].forEach((f, i) =>
        note(f, i * 0.07, 0.2, 'sine', 0.18));
    },

    /**
     * ⚔️ BATTLE JINGLE — ~5 seconds, D minor, 150 BPM.
     * Driving bass, lead melody, drums. Plays when battle begins.
     */
    battle() {
      const c = ensure(); if (!c || !enabled) return;
      const E8 = 0.2;   // eighth note @ 150 BPM

      // Opening stab
      note(73.42, 0, 0.15, 'square', 0.3);
      note(146.83, 0, 0.15, 'square', 0.25);
      noise(0, 0.3, 0.2, 2000);

      // Bass (triangle) — 24 eighth notes
      const bass = [
        73.42,73.42,73.42,73.42,73.42,73.42,73.42,73.42,   // D2
        65.41,65.41,65.41,65.41,                            // C2
        58.27,58.27,58.27,58.27,                            // Bb1
        55.00,55.00,55.00,55.00,                            // A1
        73.42,73.42,73.42,73.42,                            // D2 (back)
      ];
      bass.forEach((f, i) => note(f, i * E8, E8 * 0.9, 'triangle', 0.32));

      // Lead (square) — melody on quarter notes
      const lead = [
        [0.0, 587.33], [0.4, 698.46], [0.8, 880], [1.2, 783.99],
        [1.6, 698.46], [2.0, 659.25], [2.4, 587.33], [2.8, 523.25],
        [3.2, 587.33], [3.6, 659.25], [4.0, 698.46], [4.4, 880],
      ];
      lead.forEach(([t, f]) => note(f, t, 0.35, 'square', 0.2));

      // Drums — kick on 1 & 3, snare on 2 & 4
      for (let t = 0; t < 4.8; t += 0.8) thump(t, 0.3);
      for (let t = 0.4; t < 4.8; t += 0.8) noise(t, 0.1, 0.15, 3000);

      // Final chord — D minor, sustained + crash
      [146.83, 174.61, 220, 293.66].forEach(f => note(f, 4.8, 0.9, 'square', 0.18));
      note(1174.66, 4.8, 0.7, 'square', 0.15);
      noise(4.8, 0.5, 0.2, 2000);
    },

    // ═══════════ FANFARES ═══════════
    // Level up!
    levelup() {
      [261.6, 329.6, 392, 523.25, 659.25, 783.99, 1046.5].forEach((f, i) =>
        note(f, i * 0.08, 0.15, 'square', 0.18));
      note(1046.5, 0.6, 0.6, 'square', 0.2);
      note(1318.5, 0.6, 0.6, 'triangle', 0.15);
    },
    // Victory
    victory() {
      [392, 523.25, 659.25].forEach((f, i) => note(f, i * 0.15, 0.12, 'square', 0.2));
      note(783.99, 0.45, 0.4, 'square', 0.22);
      note(659.25, 1.0, 0.12, 'square', 0.2);
      [783.99, 523.25, 659.25, 392].forEach(f => note(f, 1.15, 1.0, 'square', 0.16));
      note(1046.5, 1.15, 1.0, 'triangle', 0.14);
    },
  };
})();

// ── Global mute button for topbars ──
function sfxToggleBtn() {
  const on = SFX.toggle();
  const btns = document.querySelectorAll('.sfx-btn');
  btns.forEach(b => b.textContent = on ? '🔊' : '🔇');
  return on;
}
