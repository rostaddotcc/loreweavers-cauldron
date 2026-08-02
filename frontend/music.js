/**
 * 🎵 music.js — Stämningsbaserad musik for The Lore Weaver\'s Cauldron
 * -------------------------------------------------------------------
 * Primär: riktiga OGG-filer (CC0 chiptune via OpenGameArt, SNES/16-bit
 * fantasy RPG-stil) i assets/music/. Varje stämning har en spellista som
 * roterar → 10+ min utan upprepning. Fallback: kort procedursyntes via
 * Web Audio om filerna inte laddar.
 *
 * Användning: MUSIC.setMood('night'), MUSIC.toggle(), MUSIC.stop()
 */
const MUSIC = (() => {
  // ── Riktiga spår per stämning (assets/music/<id>.ogg) ──
  const TRACKS = {
    night:   { list: ['sn_night_shrine', 'sn_night_rain'],
               titles: { sn_night_shrine: 'The Shrine of Mysteries (Aureolus_Omicron)', sn_night_rain: 'Rainy Streets (Aureolus_Omicron)' } },
    day:     { list: ['sn_day_fountain', 'sn_day_airship', 'sn_day_castle'],
               titles: { sn_day_fountain: 'Fountain of the Fairies (Aureolus_Omicron)', sn_day_airship: 'Airship (Aureolus_Omicron)', sn_day_castle: 'Castle on the Mountain (Aureolus_Omicron)' } },
    battle:  { list: ['sn_battle_fury', 'sn_battle_storm', 'sn_battle_hero'],
               titles: { sn_battle_fury: 'Battle Theme 1 (Aureolus_Omicron)', sn_battle_storm: 'Battle Theme 2 (Aureolus_Omicron)', sn_battle_hero: '16-bit Battle Theme I (HydroGene)' } },
    dungeon: { list: ['sn_dungeon_depths', 'sn_dungeon_evil', 'sn_dungeon_gate'],
               titles: { sn_dungeon_depths: 'Dungeon (Aureolus_Omicron)', sn_dungeon_evil: 'The Evil One (Aureolus_Omicron)', sn_dungeon_gate: 'Title Screen (Aureolus_Omicron)' } },
    town:    { list: ['sn_town_medieval', 'sn_town_court'],
               titles: { sn_town_medieval: 'Town (Aureolus_Omicron)', sn_town_court: 'In the Royal Court (Aureolus_Omicron)' } },
    rest:    { list: ['sn_rest_pavane', 'sn_rest_fireside'],
               titles: { sn_rest_pavane: 'Pavane (Aureolus_Omicron)', sn_rest_fireside: 'Bittersweet Story (Aureolus_Omicron)' } },
  };

  let ctx = null;
  let master = null;
  let playing = false;
  let enabled = localStorage.getItem('dnd_music') !== 'off';
  let currentMood = null;
  let loopTimer = null;
  let activeNodes = [];
  let audio = null;          // nuvarande <audio>-element
  let lastTrackId = null;    // senast spelade spår (randomizer undviker repris)
  let audioFailed = false;   // filer laddar inte → fallback till synth

  // ── Web Audio-fallback (korta procedurloopar, används bara om OGG saknas) ──
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
  function bass(freq, start, dur, vol = 0.2) { tone(freq, start, dur, 'triangle', vol); }

  const LOOPS = {
    night: { bpm: 70, bars: 4, play() {
      const B = 60 / 70;
      [73.42, 55, 58.27, 55].forEach((f, i) => bass(f, i * B * 2, B * 1.8, 0.18));
      [146.83, 174.61, 220].forEach(f => tone(f, 0, B * 4, 'sine', 0.06));
      [130.81, 164.81, 196].forEach(f => tone(f, B * 4, B * 4, 'sine', 0.06));
      tone(293.66, B * 0.5, B * 0.8, 'triangle', 0.1);
      tone(349.23, B * 2.5, B * 0.6, 'triangle', 0.08);
      tone(293.66, B * 4.5, B * 1.2, 'triangle', 0.1);
      tone(261.63, B * 6, B * 1.5, 'triangle', 0.09);
    } },
    day: { bpm: 100, bars: 4, play() {
      const B = 60 / 100;
      [87.31, 65.41, 73.42, 65.41].forEach((f, i) => bass(f, i * B * 2, B * 1.5, 0.15));
      [174.61, 220, 261.63].forEach(f => tone(f, 0, B * 2, 'square', 0.05));
      [196, 246.94, 293.66].forEach(f => tone(f, B * 2, B * 2, 'square', 0.05));
      [349.23, 392, 440, 523.25].forEach((f, i) => tone(f, B * i + B * 0.5, B * 0.4, 'square', 0.08));
      [523.25, 440, 392, 349.23].forEach((f, i) => tone(f, B * (i + 4) + B * 0.5, B * 0.4, 'square', 0.08));
    } },
    battle: { bpm: 150, bars: 4, play() {
      const B = 60 / 150;
      [73.42, 73.42, 73.42, 73.42, 65.41, 65.41, 58.27, 55].forEach((f, i) => bass(f, i * B, B * 0.8, 0.2));
      [587.33, 698.46, 880, 783.99, 698.46, 659.25, 587.33, 523.25].forEach((f, i) => tone(f, i * B + B * 0.1, B * 0.5, 'square', 0.1));
      for (let t = 0; t < 8; t += 2) { tone(60, t * B, 0.1, 'sine', 0.25); tone(200, (t + 1) * B, 0.05, 'square', 0.08); }
    } },
    dungeon: { bpm: 60, bars: 4, play() {
      const B = 60 / 60;
      [65.41, 61.74, 58.27, 55].forEach((f, i) => bass(f, i * B * 2, B * 2.5, 0.15));
      tone(246.94, B * 1, B * 1.5, 'sine', 0.06);
      tone(233.08, B * 3, B * 1.5, 'sine', 0.05);
      tone(220, B * 5, B * 2, 'sine', 0.06);
      tone(207.65, B * 7, B * 1, 'sine', 0.04);
      tone(987.77, B * 2, B * 0.3, 'sine', 0.03);
      tone(1046.5, B * 6, B * 0.3, 'sine', 0.03);
    } },
    town: { bpm: 120, bars: 4, play() {
      const B = 60 / 120;
      [98, 98, 73.42, 73.42, 87.31, 87.31, 98, 98].forEach((f, i) => bass(f, i * B, B * 0.7, 0.12));
      [392, 440, 493.88, 587.33, 493.88, 440, 392, 329.63].forEach((f, i) => tone(f, i * B + B * 0.2, B * 0.4, 'square', 0.08));
      [196, 246.94, 293.66].forEach(f => tone(f, 0, B * 4, 'triangle', 0.04));
      [196, 246.94, 293.66].forEach(f => tone(f, B * 4, B * 4, 'triangle', 0.04));
    } },
    rest: { bpm: 50, bars: 4, play() {
      const B = 60 / 50;
      [65.41, 65.41, 55, 55].forEach((f, i) => bass(f, i * B * 2, B * 2.5, 0.1));
      [130.81, 164.81, 196, 261.63].forEach(f => tone(f, 0, B * 8, 'sine', 0.04));
      tone(523.25, B * 1, B * 1, 'sine', 0.07);
      tone(493.88, B * 3, B * 0.8, 'sine', 0.06);
      tone(440, B * 5, B * 1.5, 'sine', 0.07);
      tone(392, B * 7, B * 1, 'sine', 0.05);
    } },
  };

  function scheduleLoop(mood) {
    if (!playing || !enabled || currentMood !== mood) return;
    const loop = LOOPS[mood];
    if (!loop) return;
    loop.play();
    const durMs = (60 / loop.bpm) * loop.bars * 2 * 1000;
    loopTimer = setTimeout(() => scheduleLoop(mood), durMs);
  }

  // ── Riktig audio: spela (slumpmässigt valt) spår i stämningens spellista ──
  function pickRandom(mood, avoidLast) {
    const cfg = TRACKS[mood];
    if (!cfg || !cfg.list.length) return null;
    if (cfg.list.length === 1) return cfg.list[0];
    let pool = cfg.list;
    if (avoidLast && lastTrackId) pool = cfg.list.filter(t => t !== lastTrackId);
    if (!pool.length) pool = cfg.list;
    return pool[Math.floor(Math.random() * pool.length)];
  }

  function playTrack(mood) {
    const cfg = TRACKS[mood];
    if (!cfg || !cfg.list.length) return;
    const id = pickRandom(mood, true);
    lastTrackId = id;
    const src = 'assets/music/' + id + '.ogg';
    if (audio) { try { audio.pause(); audio.src = ''; } catch (_) {} }
    audio = new Audio(src);
    audio.loop = false;            // roterar slumpmässigt efter varje spår
    audio.volume = 0.4;
    audio.preload = 'none';
    audio.addEventListener('ended', () => {
      if (playing && enabled && currentMood === mood) playTrack(mood);
    });
    audio.addEventListener('error', () => {
      // Filer saknas → fallback till Web Audio-syntes
      audioFailed = true;
      if (playing && enabled) { scheduleLoop(mood); }
    });
    const p = audio.play();
    if (p && p.catch) p.catch(() => { audioFailed = true; if (playing && enabled) scheduleLoop(mood); });
    if (typeof toast === 'function' && cfg.titles && cfg.titles[id]) {
      toast('🎵 ' + cfg.titles[id]);
    }
  }

  return {
    get enabled() { return enabled; },
    get mood() { return currentMood; },
    get isPlaying() { return playing; },

    toggle() {
      enabled = !enabled;
      localStorage.setItem('dnd_music', enabled ? 'on' : 'off');
      if (enabled) {
        // Återuppta där vi var — starta INTE om låten vid unmute
        if (audio && currentMood) {
          playing = true;
          audio.play().catch(() => { audioFailed = true; if (currentMood) this.setMood(currentMood); });
        } else if (currentMood) {
          this.setMood(currentMood);
        }
      } else {
        this.stop();
      }
      return enabled;
    },

    // Hoppa till slumpmässigt nästa spår i nuvarande stämning
    next() {
      if (!currentMood) return false;
      this.stop();
      playing = true;
      audioFailed = false;
      clearTimeout(loopTimer); loopTimer = null;
      playTrack(currentMood);
      return true;
    },

    setMood(mood) {
      if (!TRACKS[mood] && !LOOPS[mood]) return;
      const c = ensure(); if (!c) return;
      this.stop();
      if (!enabled) { currentMood = mood; return; }
      currentMood = mood;
      playing = true;
      lastTrackId = null;          // färskt slumpval vid ny stämning
      audioFailed = false;
      // Rensa synth-fallback
      clearTimeout(loopTimer); loopTimer = null;
      playTrack(mood);
      // Safety: om varken audio eller synth startat efter 4s, prova synth
      setTimeout(() => {
        if (playing && enabled && currentMood === mood && audioFailed) scheduleLoop(mood);
      }, 4000);
    },

    stop() {
      playing = false;
      clearTimeout(loopTimer);
      loopTimer = null;
      activeNodes.forEach(n => { try { n.stop(); } catch (_) {} });
      activeNodes = [];
      if (audio) { try { audio.pause(); audio.src = ''; } catch (_) {} audio = null; }
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

// ── Next-track-knapp (slumpmässigt nästa spår) ──
function musicNextBtn() {
  return MUSIC.next();
}

// Auto-injicera ⏭-knapp bredvid ♫-knappen (finns bara i chat.html)
document.addEventListener('DOMContentLoaded', () => {
  const musicBtn = document.querySelector('.music-btn');
  if (musicBtn && !document.querySelector('.music-next-btn')) {
    const next = document.createElement('button');
    next.className = 'top-btn icon-btn music-next-btn';
    next.title = 'Next track';
    next.textContent = '⏭';
    next.onclick = () => musicNextBtn();
    musicBtn.insertAdjacentElement('afterend', next);
  }
});
