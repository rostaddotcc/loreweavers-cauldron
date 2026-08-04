# Design Polish Spec v2 — Onboarding models + Gate removal + Loading + CLI chat (2026-08-03)

Project: `~/dnd-llm/` — The Lore Weaver's Cauldron (dnd.rostad.cc). Dark-fantasy × terminal. English UI chrome.

## File ownership (NON-NEGOTIABLE)

| Track | Files | Scope |
|---|---|---|
| **A** | `frontend/adventure.html` ONLY | Items 1+2 onboarding side |
| **B (parent)** | `frontend/chat.html`, `frontend/snes.css` | Items 2 chat side, 3, 4 |

Do NOT touch other files. Do NOT run git. The tree has uncommitted work — build on top.

---

## Item 1 — Character-sheet model picker in onboarding (Track A)

**Problem:** `generateHero()` at adventure.html:888 hardcodes `'step-3.7-flash'` when calling `API.vaultGenerateStream(advPrompt(), 'step-3.7-flash', ...)`. Non-admin players should be able to pick the character-generation model, restricted to the rules.

**Changes (adventure.html):**
1. In step 3 (`#hero-tab-summon`, near the `#gen-row` action row ~line 411), add a small model select: `<select id="adv-char-model" class="dm-model-select" style="max-width:260px"></select>` with a label "🧠 Character model" (or place it in the `.step-actions` row before the Generate Hero button). Style with existing `.dm-model-select` class.
2. Populate it with the same logic as `populateModelGate()` (~line 1022): admin → `API.models()` all; non-admin → `PLAYER_DM_MODELS` (`['qwen3.8-max', 'qwen3.6-flash', 'deepseek-v4-flash-0731', 'step-3.7-flash', 'ollama:heretic']`). Default select `step-3.7-flash`. **Backend clamps non-admin anyway** (`_clamp_player_model` in vault_generate_stream), so this is a UX picker.
3. `generateHero()` uses `document.getElementById('adv-char-model').value` instead of the hardcoded string. Add a `let advCharModel = 'step-3.7-flash';` and set it on change if cleaner.
4. Show the chosen model name in the weaving status text: `status.textContent = '🧙 The Dungeon Master is weaving your hero with <model>…'` (keep English).

Verify: node --check inline scripts; grep that `'step-3.7-flash'` no longer appears as the vaultGenerateStream arg (may still appear as default value).

---

## Item 2 — Remove model gate popup; onboarding step 4 covers everything; auto-wake

**Problem:** chat.html shows a `#model-gate` popup whenever the transcript is empty (new campaign). User wants it GONE: the last onboarding step should set ALL models, and entering the chat should auto-wake the DM.

### Track A (adventure.html):
1. Expand step 4 (`#step-model`, ~line 457) to include FOUR selects (mirroring the gate):
   - `#adventure-dm-model` (existing — DM)
   - `#adventure-guardian-model` (new — Lorekeeper/Guardian)
   - `#adventure-extraction-model` (new — background/extraction)
   - `#adventure-tts` (new — StepFun/Qwen TTS provider)
   Add small labels + hints (reuse `.dm-model-note` / new small labels). Non-admin: PLAYER_DM_MODELS for DM/Guardian/Extraction; TTS = `[{id:'stepfun',name:'StepFun (Step Plan)'},{id:'qwen',name:'Qwen (Token Plan)'}]`. Admin: all models for DM/Guardian/Extraction via `API.models()`.
2. `startAdventure()` (~line 1040) must save ALL of them before navigating to chat.html:
   ```js
   await API.setDmModel(dmModel);
   await API.setGuardianModel(guardianModel);
   await API.setExtractionModel(extractionModel);
   if (tts) { localStorage.setItem('dnd_tts_provider', tts); API.setTtsProvider(tts).catch(()=>{}); }
   ```
   (Keep each in try/catch so one failure doesn't block start.)
3. Keep the "Can be changed at any time" note. Button label: "⚔️ Start — Awaken the Dungeon Master".

### Track B (chat.html):
1. Delete `showModelGate()` (lines ~2846–2972) and `beginAdventure()` (lines ~2975–3006) entirely, OR replace the empty-transcript branch (line ~3144–3145) so it does NOT call showModelGate.
2. On empty transcript, auto-wake: after the transcript renders nothing, directly:
   ```js
   addMessage('system', null, '🕯️ <b>' + I18N.t('Dungeon Master vaknar…') + '</b> ' + I18N.t(' Mörkret rör på sig.'));
   dmRespond(AWAKENING_TRIGGER);
   ```
   Wrap in a small `setTimeout(..., 300)` or use `roleReady.then(...)` so currentModel is hydrated from campaign meta first (loadCampaign already restores `meta.dm_model` into currentModel at ~1300). The models are already saved server-side by adventure.html, so `dmRespond` uses currentModel + guardian from meta.
3. Keep `PLAYER_MODEL_IDS` (used by roleReady clamp) and `modelNames`.
4. The settings-menu model pickers (settings-dm-model etc.) remain — those are the in-game change path.

Verify: grep chat.html for `showModelGate` → 0 hits (or only the deleted-block comment). Grep `model-gate` → 0 hits. Browser: new campaign → no popup, DM wakes with the model chosen in adventure step 4.

---

## Item 3 — Loading animation: color + mix generic terms with debug log (Track B)

**Problem:** `#thought-text` is green (`var(--term-green)` in snes.css ~line 316). User wants a different color AND the loading line should mix generic fantasy/storytelling terms with the debug log's latest post.

**Changes (snes.css + chat.html):**
1. snes.css `#thought-text { color: ... }` — change from `var(--term-green)` to a warm gold/amber (`var(--gold)` or `var(--gold-bright)`) or bone. Pick `var(--gold-bright)` (fits gold DM theme) — NOT green.
2. chat.html `scribeFeed()` (~line 3224): currently it shows ONLY the debug log's latest INFO post, else falls back to pipeline activity. Change so the loading line MIXES:
   - Keep a small rotating pool of generic fantasy terms (e.g. extend THOUGHTS.narrate or add `THOUGHTS.bg`): '🪶 Weaving the tale…', '🌫️ Listening to the dark…', '📜 Turning the page…', '🕯️ The quill writes…', '✨ Stardust settles…'.
   - On each scribeFeed tick, if there's a NEW debug log post → show it (current behavior). Otherwise → show the NEXT generic term from the rotating pool (instead of just leaving the last debug post).
   - Implementation sketch: add `let _thoughtRotateIdx = 0;` and `function _nextGenericThought(){ const pool = THOUGHTS.bg || THOUGHTS.narrate; const t = pool[_thoughtRotateIdx % pool.length]; _thoughtRotateIdx++; return t; }`. In the debug-log branch, after showing a debug post, keep a `_lastDebugT` so the NEXT empty tick shows a generic term. Simple version: if `logs.length` → typeThought(debugText); else → typeThought(_nextGenericThought()) when `_activityShown` matches the last debug text. Do NOT over-engineer — the goal is "player sees generic fantasy line + occasionally the real debug line".
   - Guard: don't spam typeThought on every tick — only when text changes (existing `_activityShown` dedup).

Verify: browser with a live campaign — loading line alternates between fantasy terms and real background log entries; color is gold, not green.

---

## Item 4 — CLI chat UI switch (Track B)

**Goal (user):** "cli känslan" — no frame around the chat box, just a caret/prompt in the chat itself so everything "sits together". Add a switch "use new chat ui" that toggles between the new CLI look and the old bubble look.

**Design:**
1. A persistent setting `dnd_cli_chat` in localStorage (`'1'` = CLI mode ON, `'0'` = bubbles). Default: **bubbles OFF by default?** — user said "Ger dendär gamla bobble spelkänslan tänker jag" (the old bubbles is the fallback). So **default = OFF (bubbles)**, user flips the switch to try CLI. Actually re-read: "Detta kan få ha en switch 'use new chat ui'? Ger dendär gamla bobber spelkänslan tänker jag" — the switch lets you go back to the old bubble feeling. So CLI is the NEW look, bubbles the old. **Default = CLI ON** for new users? Safer: default **ON** (new look is the ask), toggle back to bubbles. Store in localStorage; if unset → treat as CLI ON. Hmm — but existing players would suddenly see a new look. The user is the product owner and is asking for the new look; default ON is what they want to see. Use `localStorage.getItem('dnd_cli_chat') !== '0'` (so unset = ON).
2. In chat.html settings menu (⚙️ `#settings-menu`) add a toggle item: `🖥️ New Chat UI` → `toggleCliChat()`. Also add to mobile menu.
3. `toggleCliChat()`: flips localStorage, adds/removes `body.cli-chat`, updates the toggle label, `SFX.click()`.
4. Apply on load: `document.body.classList.toggle('cli-chat', cliChatOn())` early in init.
5. **CSS (snes.css, scoped under `body.cli-chat`):** the CLI look = remove bubble frames so messages flow as terminal lines:
   - `body.cli-chat .msg{ ... }` — reduce/remove bubble border+background: `.msg.dm .bubble, .msg.player .bubble, .msg.npc .bubble { background: transparent; border: none; box-shadow: none; }` and hide `.bubble::before/::after` corner ornaments.
   - Keep role accent: DM text gold-ish, player text arcane/bone-bright — via `.msg.dm .bubble .text { color: var(--bone); font-style: italic; }` (already similar) and a left border or `❯` prefix per role: e.g. `.msg.dm .bubble::before{ content: '❯ '; color: var(--gold); }` — careful: corner ornaments use ::before/::after, so use a NEW element or `.msg .bubble .who` prefix. Simplest: in CLI mode show the `.who` nameplate as `> DM:` style. Keep it minimal — transparent bubbles, tight margins, everything "sits together", avatars small or hidden, `.bubble` padding reduced to 0.1rem 0.
   - `body.cli-chat .msg-avatar{ display:none; }` (or 24px).
   - `body.cli-chat .msg{ max-width:none; }` and `.bubble{ max-width:none; }`.
   - Composer: keep the `❯` prompt (already terminal-styled). Maybe make `.composer` transparent in CLI mode too.
   - IMPORTANT: snes.css wins with `!important` — write CLI overrides with equal-or-higher specificity AND `!important` where the base rules use `!important`. Add the CLI block at the END of snes.css.
6. Bump `snes.css?v=` on all pages after editing snes.css.

Verify: toggle in browser — bubbles on/off; CLI mode has no bubble frames; composer `❯` stays; everything readable; mobile (375px) still usable; toggle persists across reload.

---

## Design tokens (unchanged)
Use CSS vars: `--ink --stone --stone-2 --stone-3 --edge --edge-hi --bone --bone-bright --bone-dim --gold --gold-bright --blood --blood-bright --ember --arcane --arcane-bright --arcane-deep --poison --teal --term-green --term-amber`. Fonts: Cinzel (display), Spectral (body), VT323/IBM Plex Mono (mono). Semantic: gold=UI, blood=HP, arcane=player/magic, ember=quests, poison=success.

## Verification & deploy
- `node --check` every inline `<script>` + external JS.
- `cd backend && python3 -m pytest tests/ -q` (all pass).
- `docker compose up -d --build` (background), health `curl localhost:8092/api/health`.
- Cache-bust `snes.css?v=N` (monotonic) on ALL pages; `api.js?v=` only if api.js changed (Track A may not need it).
- Commit + push everything (user wants all finished work pushed).
