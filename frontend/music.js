/**
 * 🎵 music.js — Stämningsbaserad MIDI/SNES-musik för D&D-äventyret
 * Syntas via Web Audio API. Inga ljudfiler. Loopar per stämning.
 *
 * Användning: MUSIC.setMood('night'), MUSIC.toggle(), MUSIC.stop()
 */
const MUSIC = (() => {
  let ctx = null;
  let master = null;
  let playing = false;
  let enabled = localStorage.getItem('dnd_music') !== 'off';
  let currentMood = null;
  let loopTimer = null;
  let activeNodes = [];

  function ensure() {
    if (!ctx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return null;
      ctx = new AC();
      master = ctx.createGain();
      master.gain.value = 0.18;
      master.connect(ctx.destination);
    }
    if (ctx.state === 'suspended') ctx.resume();
    return ctx;
  }

  // En ton i loopen
  function tone(freq, start, dur, type = 'square', vol = 0.15) {
    const c = ensure(); if (!c) return;
    const t0 = c.currentTime + start;
    const osc = c.createOscillator();
    const g = c.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(freq, t0);
    g.gain.setValueAtTime(vol, t0);
    g.gain.setValueAtTime(vol, t0 + dur * 0.7);
    g.gain.exponentialRampToValueAtTime(0.001, t0 + dur);
    osc.connect(g); g.connect(master);
    osc.start(t0); osc.stop(t0 + dur + 0.05);
    activeNodes.push(osc);
  }

  // Bas-ton (lägre, fylligare)
  function bass(freq, start, dur, vol = 0.2) {
    tone(freq, start, dur, 'triangle', vol);
  }

  // ── LOOP-DEFINITIONER ──
  // Varje loop: { bpm, bars, fn(play) } — fn spelar en iteration
  const LOOPS = {
    // 🌙 NATT — mörk, mystisk, långsam (D-moll, 70 BPM)
    night: {
      bpm: 70, bars: 4,
      play() {
        const B = 60 / 70; // beat
        // Bas: D2, A1, Bb1, A1
        [73.42, 55, 58.27, 55].forEach((f, i) => bass(f, i * B * 2, B * 1.8, 0.18));
        // Pad: D-moll ackord, mjuka
        [146.83, 174.61, 220].forEach(f => tone(f, 0, B * 4, 'sine', 0.06));
        [130.81, 164.81, 196].forEach(f => tone(f, B * 4, B * 4, 'sine', 0.06));
        // Melodi: ensam, sorglig
        tone(293.66, B * 0.5, B * 0.8, 'triangle', 0.1);
        tone(349.23, B * 2.5, B * 0.6, 'triangle', 0.08);
        tone(293.66, B * 4.5, B * 1.2, 'triangle', 0.1);
        tone(261.63, B * 6, B * 1.5, 'triangle', 0.09);
      }
    },

    // ☀️ DAG — ljus, hoppfull (F-dur, 100 BPM)
    day: {
      bpm: 100, bars: 4,
      play() {
        const B = 60 / 100;
        // Bas: F2, C2, D2, C2
        [87.31, 65.41, 73.42, 65.41].forEach((f, i) => bass(f, i * B * 2, B * 1.5, 0.15));
        // Ackord: F-dur, C-dur
        [174.61, 220, 261.63].forEach(f => tone(f, 0, B * 2, 'square', 0.05));
        [196, 246.94, 293.66].forEach(f => tone(f, B * 2, B * 2, 'square', 0.05));
        [174.61, 220, 261.63].forEach(f => tone(f, B * 4, B * 2, 'square', 0.05));
        [196, 246.94, 293.66].forEach(f => tone(f, B * 6, B * 2, 'square', 0.05));
        // Melodi: glad, stigande
        [349.23, 392, 440, 523.25].forEach((f, i) => tone(f, B * i + B * 0.5, B * 0.4, 'square', 0.08));
        [523.25, 440, 392, 349.23].forEach((f, i) => tone(f, B * (i + 4) + B * 0.5, B * 0.4, 'square', 0.08));
      }
    },

    // ⚔️ STRID — intensiv, drivande (D-moll, 150 BPM)
    battle: {
      bpm: 150, bars: 4,
      play() {
        const B = 60 / 150;
        // Drivande bas
        [73.42, 73.42, 73.42, 73.42, 65.41, 65.41, 58.27, 55].forEach((f, i) =>
          bass(f, i * B, B * 0.8, 0.2));
        // Lead: aggressiv
        [587.33, 698.46, 880, 783.99, 698.46, 659.25, 587.33, 523.25].forEach((f, i) =>
          tone(f, i * B + B * 0.1, B * 0.5, 'square', 0.1));
        // Trummor
        for (let t = 0; t < 8; t += 2) {
          tone(60, t * B, 0.1, 'sine', 0.25); // kick
          tone(200, (t + 1) * B, 0.05, 'square', 0.08); // snare
        }
      }
    },

    // 🏰 FÄNGELSEHÅLA — kuslig, ekande (C-moll, 60 BPM)
    dungeon: {
      bpm: 60, bars: 4,
      play() {
        const B = 60 / 60;
        // Djup bas
        [65.41, 61.74, 58.27, 55].forEach((f, i) => bass(f, i * B * 2, B * 2.5, 0.15));
        // Dissonanta toner
        tone(246.94, B * 1, B * 1.5, 'sine', 0.06);
        tone(233.08, B * 3, B * 1.5, 'sine', 0.05);
        tone(220, B * 5, B * 2, 'sine', 0.06);
        tone(207.65, B * 7, B * 1, 'sine', 0.04);
        // Viskande höga toner
        tone(987.77, B * 2, B * 0.3, 'sine', 0.03);
        tone(1046.5, B * 6, B * 0.3, 'sine', 0.03);
      }
    },

    // 🏘️ STAD — livlig, medeltida (G-dur, 120 BPM)
    town: {
      bpm: 120, bars: 4,
      play() {
        const B = 60 / 120;
        // Gångbas
        [98, 98, 73.42, 73.42, 87.31, 87.31, 98, 98].forEach((f, i) =>
          bass(f, i * B, B * 0.7, 0.12));
        // Melodi: dansande
        [392, 440, 493.88, 587.33, 493.88, 440, 392, 329.63].forEach((f, i) =>
          tone(f, i * B + B * 0.2, B * 0.4, 'square', 0.08));
        // Harmoni
        [196, 246.94, 293.66].forEach(f => tone(f, 0, B * 4, 'triangle', 0.04));
        [196, 246.94, 293.66].forEach(f => tone(f, B * 4, B * 4, 'triangle', 0.04));
      }
    },

    // 🕯️ VILA — lugn, trygg (C-dur, 50 BPM)
    rest: {
      bpm: 50, bars: 4,
      play() {
        const B = 60 / 50;
        // Mjuk bas
        [65.41, 65.41, 55, 55].forEach((f, i) => bass(f, i * B * 2, B * 2.5, 0.1));
        // Varmt ackord
        [130.81, 164.81, 196, 261.63].forEach(f => tone(f, 0, B * 8, 'sine', 0.04));
        // Enkel melodi: vaggvisa
        tone(523.25, B * 1, B * 1, 'sine', 0.07);
        tone(493.88, B * 3, B * 0.8, 'sine', 0.06);
        tone(440, B * 5, B * 1.5, 'sine', 0.07);
        tone(392, B * 7, B * 1, 'sine', 0.05);
      }
    },
  };

  function scheduleLoop(mood) {
    if (!playing || !enabled || currentMood !== mood) return;
    const loop = LOOPS[mood];
    if (!loop) return;
    loop.play();
    const durMs = (60 / loop.bpm) * loop.bars * 2 * 1000;
    loopTimer = setTimeout(() => scheduleLoop(mood), durMs);
  }

  return {
    get enabled() { return enabled; },
    get mood() { return currentMood; },
    get isPlaying() { return playing; },

    toggle() {
      enabled = !enabled;
      localStorage.setItem('dnd_music', enabled ? 'on' : 'off');
      if (enabled && currentMood) {
        this.setMood(currentMood);
      } else {
        this.stop();
      }
      return enabled;
    },

    setMood(mood) {
      if (!LOOPS[mood]) return;
      const c = ensure(); if (!c) return;
      // Stoppa föregående
      this.stop();
      if (!enabled) { currentMood = mood; return; }
      currentMood = mood;
      playing = true;
      scheduleLoop(mood);
    },

    stop() {
      playing = false;
      clearTimeout(loopTimer);
      activeNodes.forEach(n => { try { n.stop(); } catch (_) {} });
      activeNodes = [];
    },

    // Auto-detect stämning från DM-text
    detectMood(text) {
      const t = (text || '').toLowerCase();
      if (/strid|attack|fiende|skelett|slåss|vapen|blod/.test(t)) return 'battle';
      if (/natt|mörker|måne|skugga|stjärn/.test(t)) return 'night';
      if (/grotta|fängelse|krypta|valv|tunnel|djup/.test(t)) return 'dungeon';
      if (/stad|by|torg|värdshus|marknad|hamn/.test(t)) return 'town';
      if (/vila|läger|eld|sömn|ro|trygg/.test(t)) return 'rest';
      if (/dag|sol|morgon|ljus|fält|skog/.test(t)) return 'day';
      return null;
    },
  };
})();

// ── Global musik-knapp ──
function musicToggleBtn() {
  const on = MUSIC.toggle();
  const btns = document.querySelectorAll('.music-btn');
  btns.forEach(b => { b.textContent = on ? '♫' : '♪'; b.classList.toggle('off', !on); });
  if (on && !MUSIC.isPlaying) MUSIC.setMood(MUSIC.mood || 'night');
  return on;
}
