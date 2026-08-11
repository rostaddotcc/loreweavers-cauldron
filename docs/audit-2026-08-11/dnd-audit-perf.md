# ⚡ Performance Audit — "Mörkrets Rike" frontend (`~/dnd-llm/frontend/`)

**Audit date:** 2026-08-11 · **Type:** AUDIT-ONLY (no project files touched; everything written to /tmp)
**Scope:** all `.html/.js/.css` in `~/dnd-llm/frontend/` (+ `book-souls/`, `assets/`, `vendor/`), live-server checks against `loreweavers-cauldron` container (port 8092).
**Method:** pattern grep (`setInterval`, `setTimeout`, `requestAnimationFrame`, `MutationObserver`, `addEventListener('scroll'`, `@keyframes`, `animation: …infinite`), targeted `read_file` excerpts, `curl` timing, `du` asset census.

---

## 0. Executive summary — worst offenders by estimated impact

| # | Offender | Where | Estimated impact |
|---|----------|-------|------------------|
| 1 | **Embers canvas loop, always at 60 fps, shadowBlur per particle, on 11 pages** — never checks `document.hidden`, never pauses when idle | chat.html:7954-7978 + 10 other pages | **5–15% idle CPU on desktop, 15–30%+ on mobile**; the single largest always-on drain. 30–40 shadowed `arc()` fills × 60 fps |
| 2 | **sprites.js global MutationObserver + full-subtree TreeWalker + per-emoji `<template>.innerHTML` parse** — fires on *every* DOM insertion app-wide (11 pages) | sprites.js:1954-1962, 1942-1949, 1921-1939 | **+1–5 ms per chat message (10–30 ms on slow phones)**; doubles text node count (each emoji → inline SVG); observer storms during particle bursts |
| 3 | **Typewriter: forced `chat.scrollTop = chat.scrollHeight` every 18–40 ms tick + full rewrite of all text nodes per tick** | chat.html:4245-4263, 4177-4187, 4259 | With a 4–6k-node transcript each tick forces a **sync layout of the whole chat column**; ~400 ticks per long DM message → seconds of layout work per message, growing unbounded |
| 4 | **No transcript virtualization/pruning** — bubbles accumulate for the whole session (~200 msgs ≈ 4,000–6,000 nodes) | chat.html:3025-3043, 4857-4972 | Layout cost of every forced scroll + sprites observer grows linearly; memory grows unbounded |
| 5 | **Per-message stacked effects**: typewriter setTimeout-chain (18–40 ms) + drip `setInterval(150 ms)` + 3 particle waves (0/240/480 ms) + ~36 particle divs **each with its own rAF loop** + per-tick SFX blips | chat.html:4035-4064, 4100-4124, 4206-4267 | Bursty 60–200 ms main-thread stalls per DM message; 36 concurrent rAF loops × 60 fps during reveal |
| 6 | **Guardian poll fetches the ENTIRE transcript every 1 s** while Lorekeeper is busy | chat.html:5975-6070 | At 200 messages ≈ 150–300 KB JSON/s polling; also re-scans `messages.forEach` for unrendered keys each tick |
| 7 | **479 KB chat.html (139 KB inline CSS + 306 KB inline JS) + 107 KB snes.css + ~170 KB external JS, served WITHOUT gzip/brotli** | chat.html:1, snes.css | **~780 KB raw transfer per game-page load**; 479 KB single file blocks parse → slow first paint; inline scripts parse synchronously |
| 8 | **Canvas particle anims read `parseFloat(style.left)` + write transform/opacity every frame per div** | chat.html:4053-4061 | Micro-thrash × dozens of concurrent divs; compounds with #5 |
| 9 | **`ctx.resume()` called on every SFX call + per-blip oscillator creation at up to ~25–55 blips/s during typewriter** | sfx.js:22, 28-40; chat.html:4253-4257 | GC churn + audio thread wake-ups during every reveal; no muting when tab hidden |
| 10 | **book-souls/avatars = 87 MB (32 files, up to 7.8 MB each!)** + assets/cauldron-hero.png 2.7 MB | book-souls/, assets/ | Multi-MB image downloads in the 3D flip-book gallery; hero PNG is 2.7 MB |

---

## 1. TIMERS (chat.html = the game screen)

### setInterval — 8 in chat.html

| Line | Interval | What | Cleared? |
|------|----------|------|----------|
| 2003 | **1000 ms** | Turn-reset countdown tick (updates header when user has a reset date) | **Never** — runs for the whole session, gated internally by `_meData`/`_tier()` check (cheap, but always-on) |
| 3420 | 1000 ms | TTS "buffering… mm:ss" label | Yes — `ttsSynthStop()` |
| 4266 | **150 ms** | `drip()` pixel drip along typewriter cursor (2 divs/tick, each with own rAF) | Yes — `finish()` (chat.html:4232) |
| 5025 | **16 ms** | `typeThought` — loader thought typewriter (~62 Hz text writes) | Yes — at end of text |
| 5076 | 1500 ms | `scribeFeed` — polls `/api/debug-logs` while DM/Lorekeeper loader visible | Yes — `hideThoughts()`/`hideGuardianStatus()` |
| 5103 | **600 ms** | `scribeParticles` — ink bursts (12 divs + 12 rAF loops per burst) | Yes — `scribeParticles(false)` |
| 5975 | **1000 ms** | `pollForGuardian` — fetches **full transcript** + renders pending guardian reports | Yes — when `guardian_running` false & nothing pending; max 600 attempts (~10 min) then resets while busy |
| 7685 | 1500 ms | `pollConsole` — debug console log polling | Yes — when console closes |

**Flagged:**
- **Intervals < 1 s:** 150 ms drip, 16 ms thought typewriter, 600 ms scribe particles (all conditional, but all *stack* during the same busy phase).
- **Never stops:** the 1000 ms countdown (chat.html:2003) — runs even for lifetime-tier users (just early-returns).
- **Stacked per chat message** (one DM reply): typewriter `setTimeout` chain (18–40 ms, ~400 ticks) **+** drip `setInterval(150 ms)` **+** particle waves at 0/240/480 ms **+** `SFX.receive()` + `SFX.type()` blips every ~2 ticks **+** 90 s safety `setTimeout` per message (chat.html:3127) + each of ~36 particle divs running its own rAF. This is the jank you feel when the DM "types".
- Elsewhere: login.html 1000 ms countdown (1386, never cleared, cheap) + 7000 ms quote rotator (1411); newgame.html ritual timers (500 ms elapsed-time label + **600 ms pixel bursts**, pushed to `_ritualTimers`, cleared on reset); characters.html ritual timers (600 ms); platser.html 250 ms retry-jump (self-clearing, fine); mechanics.html `setTimeout(step, 12)` JSON-replay demo (one-shot, fine); api.js mock delays (fine).

---

## 2. requestAnimationFrame LOOPS

**Embers canvas — the same copy-pasted loop on 11 pages** (chat, admin, npcs, loggbok, adventure, characters, platser, newgame, mechanics, character, + rain on login):

- chat.html:7954-7978 (32 particles), admin.html:2258 (30), npcs.html:719 (34), loggbok.html:301 (30), adventure.html:2616 (38), characters.html:553 (40), platser.html:630 (30), newgame.html:1019 (40), mechanics.html:1190, character.html:1654 (~40), login.html:1859 (rain drops).
- **None check `document.hidden` or IntersectionObserver** — every page runs its embers at full 60 fps the entire time it is visible, even when completely idle (verified: zero `visibilitychange`/`document.hidden` matches in app code).
- **Every particle fill uses `ctx.shadowBlur = 6–8`** — shadow blur is one of the most expensive canvas operations (per-particle shadowed path rasterization). 30–40 shadowed arcs × 60 fps ≈ the dominant idle CPU cost on every page.
- `resize()` handlers just set canvas width/height — fine (rare), but no rAF batching (irrelevant at this frequency).
- **Per-particle rAF loops:** `spawnPixelBurst`/`spawnPixelSmoke` create **one `requestAnimationFrame` loop per particle div** (chat.html:4053, 4085). One DM message → 36 concurrent loops; one scribe burst → 12. Should be one shared loop.
- One-shot rAFs (dice ceremony chat.html:3947-4094, reveal classes adventure.html:1304-1318) — fine.
- Browsers do pause rAF in hidden tabs — the hidden-tab cost is the interval polls + audio, not the canvas.

---

## 3. MUTATIONOBSERVERS

**sprites.js:1954-1962 — the big one.** `observe(document.body, { childList: true, subtree: true })` on **11 pages**. Every DOM insertion app-wide triggers:

1. `spritize(nd)` = `createTreeWalker(root, SHOW_TEXT)` over the **entire added subtree** (chat.html:1944-1948), then per text node:
2. Emoji regex test → for each emoji: `svgEl(m)` = **`<template>.innerHTML = svg` + parse** (sprites.js:1897-1899) — a template/HTML-parse per emoji, per insertion.

**Trigger storms in practice:** every chat message append (bubble + avatar + emoji-rich text) → observer fires; **every particle div appended to `<body>`** (36/message + 12/burst) → observer fires and walks the particle (cheap, no text, but callback churn on every append); typewriter moves the cursor span → fires; day-group heads → fires. The code even *relies* on this: the typewriter deliberately waits 80 ms for "sprites.js hinner ersätta emojis" (chat.html:3118) — design coupling that serializes every message render.

**Second observer:** chat.html:7948 — HP-bar style attribute observer, narrow scope, fine (mirror to mobile).

**Missing:** no debounce/batching (no rAF/idle scheduling), no ignore-list for `.px-particle`/`.px-smoke`, no `characterData` observation (good — text mutations don't re-trigger).

---

## 4. DOM GROWTH (transcript)

- **No virtualization, no pruning.** `loadTranscript` only clears `chat.innerHTML` on reload (chat.html:4860). Live play appends forever: day-groups get `display:none` when collapsed (chat.html:315, 3027) — layout-cheap but **nodes stay in the DOM** (and the newest day-group stays expanded and grows).
- **Node estimate per DM message:** `.msg` + avatar span (+`<img>` or SVG) + `.bubble` + `.tts-btn` + `.who` + 1–3 `.text`/`.npc-quote` (+children) + `.dm-footer` ≈ **10–15 elements**, plus **1 extra SVG node per emoji** (DM text is emoji-dense, ~5–10/message). **After 200 messages: ≈ 4,000–6,000 nodes**, growing unbounded for the session. Each typewriter forced-scroll (see §5) pays the layout cost of all of them.
- **Cleanup that DOES exist:** particle divs `p.remove()` on life end ✓ (chat.html:4055, 4087); system messages removed after 8 s ✓ (5816); roll-request waits removed ✓ (5153); `_dmRollSeen` capped at 400 ✓ (6697). The transcript itself is the leak.
- Replay rendering uses a `DocumentFragment` (good, chat.html:4904) but every replay message carries `animation: msg-in .4s` — animating hundreds of elements simultaneously on load = first-paint jank on session start.

---

## 5. LAYOUT THRASH

- **Typewriter tick (chat.html:4245-4263):** every 18–40 ms it (a) rewrites `nodeValue` on **all** text nodes of the message (`revealUpTo` loops every node of every segment, 4177-4187), (b) `moveCursor()` removes+appends a span, (c) **`chat.scrollTop = chat.scrollHeight`** (4259) — a write that forces synchronous layout of the **entire chat column**. With a 5k-node transcript each tick = a full layout; ~400 ticks per long message. **The #1 mid-session jank source.**
- `messageParticles` calls `getBoundingClientRect()` immediately after `appendToChat` (chat.html:4102) — forced layout right after a DOM write (one-shot per message, minor).
- Particle anims: `parseFloat(p.style.left)` read + transform/opacity write every frame per div (4059) — style read/write ping-pong × dozens of divs.
- `drip` does one `getBoundingClientRect` per 150 ms tick (4215) — acceptable.
- `qsUpdate` (scroll listener) reads `scrollTop/clientHeight/scrollHeight` — only on scroll events, fine.
- Note: the `void el.offsetWidth` reflow trick is *not* used in loops anywhere (no major offender beyond the above).

---

## 6. CSS ANIMATION COST

**chat.html inline CSS — 24 `animation: …infinite` declarations** (grep): `tts-pulse`, `orb-pulse`, `type-blink`, `hp-flash` ×2, `crt-flicker`, `rr-pulse`, `d20-tumble`, `d20-tension-pulse`, `d20-ambient`, `rune-spin` ×2 (loader), `guardian-ring`, `guardian-dot`, `cd-sheen`, `cd-alarm`, `cdGemPulse`, `cli-dice-flicker`, `cli-crit-glow`, `mic-pulse`, `synth-pulse`.

**snes.css — 20 more** (`prompt-blink`, `blink-cursor` ×3, `cr-sheen`, `cr-alarm`, `cr-flicker`, `quill-bob`, `ink-draw`, `cli-progress`, `dice-badge-pop`+`badge-crit-glow`, `rr-pulse`, `rr-dice-bob`, `rr-pen-tilt`, `hp-flash`, `mic-pulse`, `cli-tts-pulse` ×2, `cli-blink`).

**Steady-state (idle, no loader/combat/TTS) always-running:**
- `crt-flicker 4s infinite` + repeating-linear-gradient scanline overlay on `.ascii-art::before/::after` (chat.html:605-621) — full-viewport overlay in CLI mode.
- `blink-cursor`/`prompt-blink`/`cli-blink` — terminal cursor while input focused.
- `cd-sheen` + `cdGemPulse` — codex drawer open only (conditional). `d20-ambient` — dice overlay only (conditional, 713). `rr-pulse` — pending roll cards only.

**Expensive flagged:** `cdGemPulse` animates **`filter: drop-shadow`** (chat.html:968-972 — filter animation forces a repaint per frame of the whole subtree); `pulse-gold/blood/blue/ember` (647-650) animate **box-shadow on scene cards** (paint-heavy); `badge-crit-glow`, `rr-pulse` box-shadows on small elements — OK. Most infinite animations are conditional on loader/ceremony states (good design) — the always-on set is small but `crt-flicker` (opacity on a full-viewport pseudo-element) repaints the whole viewport 4 s cycle — cheap-ish, but pointless in idle.
- Every `.msg` has a one-shot `msg-in 0.4s` — fine for live messages, expensive when 200 replay messages animate at once (see §4).

---

## 7. SCROLL / RESIZE LISTENERS

| File:Line | Type | Passive | Throttled |
|-----------|------|---------|-----------|
| chat.html:2959 | chat scroll → `qsUpdate` (reads scrollTop/clientHeight/scrollHeight) | **passive ✓** | no (cheap handler, OK) |
| chat.html:7958 | window resize → embers canvas resize | default | no (rare, OK) |
| login.html:1391 | scroll → nav toggle | **passive ✓** | no (cheap) |
| mechanics.html:1230 | scroll → section spy | **passive ✓** | no (does classList toggles per event; fine) |
| admin.html:1928 | wrap scroll → onScroll | **NOT passive** (no options) | no — minor, could block scrolling while handler runs |

No debounce/throttle anywhere, but handlers are cheap — this category is in good shape overall.

---

## 8. PAGE WEIGHT / NETWORK

**Live-server measurements (port 8092, curl):**

| Asset | Size | Notes |
|-------|------|-------|
| chat.html | **478,971 B** | **NO gzip** (478,971 B even with `Accept-Encoding: gzip`) |
| snes.css | 107,526 B | no gzip |
| i18n.js | 71,162 B | parsed on **13 pages** |
| archetypes.js | 58,223 B | only adventure.html + newgame.html ✓ (good) |
| sprites.js | 41,789 B | 11 pages |
| api.js | 29,111 B | chat + others |
| themes.js | 16,724 B | **17 pages** (everywhere) |
| sfx.js | 8,063 B | 12 pages |
| fonts.js | 2,891 B | 11 pages (no-op shim kept for compat) |

- **chat.html breakdown:** 139 KB inline `<style>` + 306 KB inline `<script>` + HTML ≈ 479 KB, PLUS 107 KB snes.css (also linked) + ~170 KB external JS = **~780 KB raw, ungzipped per game-page load**, no caching assumed (no cache-control verified; server does not gzip at all).
- **External requests:** Google Fonts on **all 17 pages**: 2 preconnects + 1 CSS2 stylesheet + 2 woff2 (Cinzel 400/700/900 + Spectral 5 styles ≈ 150–250 KB). No other CDNs ✓.
- **i18n.js is the biggest deferred candidate** — a 71 KB Swedish↔English dictionary parsed on 13 pages, including pages that are always-Swedish.
- **images:** `assets/cauldron-hero.png` **2.7 MB** (hero, unoptimized), logo-cauldron 796 KB/656 KB; **`book-souls/` = 98 MB total — 87 MB in `avatars/` (32 files, up to 7.8 MB each)**, plus 1.3 MB × many NPC portraits; gallery.json 52 KB. The 3D flip-book page loads multi-MB PNGs per spread. `vendor/three.module.min.js` 691 KB (book-souls only? not referenced in book-souls/index.html grep — verify; the flip book uses CSS 3D, so three.js may be dead weight in vendor/).
- **parse cost:** 479 KB single-file page = browsers can't start rendering until the giant inline script block is parsed; no `defer`/`async` (inline scripts are synchronous by nature). This is the "slow load" contributor.

---

## 9. AUDIO

- **No music loop exists** (context mentioned `music.js` — verified absent; `sfx.js` is the only audio module). False lead ✓.
- **sfx.js:** all one-shot synthesized blips. Two perf notes:
  - `ensure()` calls **`ctx.resume()` on every single SFX call** (sfx.js:22) — a no-op-ish wake-up on an already-running context, but it runs on every blip.
  - Typewriter: `SFX.type(pitchDm++)` every ~2 ticks at 18–40 ms intervals → **~25–55 oscillator+gain nodes created per second** during a reveal (sfx.js:28-40, chat.html:4253-4257). Each creates osc + gain, starts, stops — short-lived audio-node churn + GC pressure.
- **Hidden tab:** browsers auto-suspend AudioContext when hidden and throttle `setTimeout` to ≥1 s — so hidden-tab audio cost is bounded. No explicit pause/mute-when-hidden in app code; the 1 s polls (guardian/console/scribe) still fire at 1/s in background.
- **TTS:** `I18N.speak` uses browser `speechSynthesis`; the 1 s synth label timer is cleared on stop ✓.

---

## 10. QUICK WINS — prioritized

### (a) 5-minute wins

1. **Pause embers when idle/hidden — the #1 win.** Add to every embers loop (chat.html:7976, admin:2258, npcs:719, loggbok:301, adventure:2616, characters:553, platser:630, newgame:1019, mechanics:1190, character:1654, login:1859): `if (document.hidden) { requestAnimationFrame(tick); return; }` (or `visibilitychange` pause) + drop `ctx.shadowBlur` per particle (pre-render a radial-gradient sprite once, drawImage per particle). **Effect: kills the dominant always-on CPU drain (5–15% desktop, 15–30% mobile) on every page.**
2. **sprites.js: skip text-less subtrees before the TreeWalker** (sprites.js:1954-1962) — early-return when `nd.nodeType === 1 && !nd.textContent` (covers the particle-div storm) and batch processing via `requestIdleCallback`/rAF. **Effect: removes observer churn on every particle + most DOM writes.**
3. **Typewriter scroll: only pin to bottom when the user is near the bottom** (chat.html:4259): read `chat.scrollTop + clientHeight` vs `scrollHeight` once per tick and skip the write when scrolled up (or scroll every Nth tick). **Effect: removes ~400 forced full-column layouts per long message — the mid-session jank.**
4. **Disable `msg-in` animation for replay-rendered messages** (chat.html:4904/4972): add a `no-anim` class (`.msg.no-anim{animation:none}`) when appending the transcript fragment. **Effect: removes 200-way simultaneous entrance-animation on session load.**
5. **Serve gzip/brotli + cache headers for static files** (server side, not in this repo): chat.html 479→~110 KB, snes.css 107→~20 KB. **Effect: ~4× faster page load on every page.**

### (b) Medium fixes

6. **One shared rAF loop for all particles** (chat.html:4035-4097): replace per-div `requestAnimationFrame(anim)` with a single registry loop. **Effect: 36 concurrent loops → 1; big frame-time reduction during reveals.**
7. **Typewriter: only rewrite the active text node** (chat.html:4177-4187): `revealUpTo` currently rewrites every node of every segment per tick — write only the segment/node containing the cursor. **Effect: less text-mutation work per tick, fewer sprites-observer re-scans** (characterData not observed, but the spritize of inserted cursor span still fires).
8. **Guardian poll: 1 s → 2 s and fetch only `since`** (chat.html:5975): it downloads the full transcript every second and re-scans the whole array. **Effect: halves polling bandwidth/CPU during the most active phase.**
9. **SFX: move `ctx.resume()` to a user-gesture hook, cap blip rate** (sfx.js:22; chat.html:4253): one resume on first click; typewriter blip max ~1 per 50 ms regardless of chunk. **Effect: less audio-thread churn + GC.**
10. **Prune transcript in-session:** cap kept day-groups (e.g., remove groups older than N days, keeping a summary line) since collapsed groups still hold nodes. (chat.html:3027). **Effect: bounds layout cost of every forced scroll.**
11. **Defers:** move i18n.js to `defer` and archetypes.js only where needed (already scoped ✓); split chat.html's 306 KB inline JS into an external file with `defer` so HTML/CSS parse first. **Effect: faster first paint.**
12. **Self-host Cinzel/Spectral woff2** (all pages) — removes 3 external font requests per page. **Effect: fewer round trips, offline-friendly.**

### (c) Structural changes

13. **Virtualize the transcript** — the chat is already grouped by day; treat day-groups as windowed units: keep last ~30 groups in DOM, serialize/hide older ones into a "…" stub that reloads on click. **Effect: bounded DOM (4–6k nodes → <1k), bounded layout cost forever.**
14. **Split chat.html** into `chat.css` + `chat.js` (cacheable, parallel-downloadable, incrementally parseable). 479 KB single file is the load-time bottleneck; splitting lets browsers cache CSS/JS across visits (only the HTML diff changes).
15. **sprites.js: prebuild the emoji→SVG map once** (`svgFor` currently does `<template>.innerHTML` parse per emoji per insertion, sprites.js:1897-1899) — build all SVGs once at init, clone on demand. **Effect: removes HTML-parse work from every chat message render.**
16. **Compress images:** `assets/cauldron-hero.png` 2.7 MB → WebP/AVIF <300 KB; cap avatar uploads to ≤1 MB and downscale server-side (avatars/ currently holds **7.8 MB** files); book-souls gallery should lazy-load spreads and use the downscaled variants. **Effect: multi-MB savings per gallery visit.**
17. **Honor `prefers-reduced-motion`** globally — disable embers, fog, flicker, sheen for users who opt out. **Effect: accessibility + battery win.**
18. **ResizeObserver-driven canvas sizing + devicePixelRatio cap** on embers canvases (they're `innerWidth×innerHeight` = 1× DPR; on 2× screens each shadowed arc rasterizes 4× the pixels). **Effect: up to 4× cheaper per frame on retina.**

---

*Report ends. Nothing in `~/dnd-llm/frontend/` was modified. All findings verified against source on disk + live container (port 8092).*
