# Wave 2 — Subagent S1 Report: login.html + adventure.html UX fixes
**Date:** 2026-09-17 · **Files touched (ONLY these two):** `frontend/login.html`, `frontend/adventure.html`
**Sources:** audit-a1-onboarding-2026-09.md (full), audit-a2-ingame-2026-09.md (§2.2, §4.3)
**Constraints honored:** no other files edited · no `?v=` cache-bust changes · no git add/commit · no docker/bump_versions · no live-site login.

---

## A) login.html

| # | Change | Before → After (anchors) |
|---|--------|--------------------------|
| A1 | CTA per auth mode | `#auth-btn` static HTML (~:726) `What will the Cauldron Foretell?` → `Enter the Realm`; `setAuthBusy()` (~:960–967) busy labels → login `Opening the gate…` / register `Forging your name…` / reset `Re-forging your password…`, idle labels → `Enter the Realm` / `Forge Your Name` / `Set a New Password`; `applyAuthMode()` (~:976) same table. Foretell wordplay moved to login-mode `#gate-sub` (static ~:692 + JS ~:982): `The fire has been kept burning — what will the Cauldron foretell?`. Hero `.of` span tagline (:536) kept per audit §1.2. |
| A2 | Reset-mode copy | `#gate-reset` (~:712) `Lost your name? Re-forge it` → `Lost your password?` (plain link, no gold `<b>`); reset `#gate-title` (JS ~:977) `Re-forge Your Name` → `Lost Your Password?`; reset gate-sub → `Speak your name and choose a new secret word. The pot remembers the rest.` |
| A3 | Compact gate (§1.1) | `#keep-logged-in-row` + `#gate-reset` merged into new flex row `.gate-opt-row#gate-opt-row` (checkbox left, reset link right) at ~:707–713; CSS `.gate-opt-row`/`.gate-reset-link` added in head block (~:255–259, scoped `.gate-opt-row .gate-reset-link` to out-specify `.gate-toggle` defined later); `applyAuthMode()` hides `#gate-opt-row` outside login mode (~:992). Exactly one toggle row (`#gate-toggle`) + mode-specific `#reset-link-btn` under the CTA. `.gate-foot` (~:731) trimmed to `No email needed to play.<br>Powered by Qwen, DeepSeek & StepFun`. |
| A4 | Update banner → Qwen Flash | `#update-banner` (:418): v1.2 Honest-Dice copy → `✦ Qwen 3.8 Flash — now in the free tier. A fast Dungeon Master mind, free for every account.` linking `releases.html`; NEW localStorage key `qwen_flash_seen` in both inline onclick handlers and init JS (:897, read+write identical spelling). Old key `rn_12_seen` fully removed from this file. |
| A5 | P2 copy (§1.4/§1.5/§1.7) | pitch-list item 1: `no hourglass` → `no countdown`; item 2 → `Your identity stays yours. No player tracking, no analytics profiles — just a name and a secret word.` (ledger double-meaning dropped); `#hero-begin` (:545) `href="#pricing"` → `href="#gate"`. |
| A6 | Reduced motion (§1.9) | head block (~:403–408) extended: `.scroll-cue,.head-logo,.hero-bg{animation:none}` (covers hero-breathe), `#update-banner.show{animation:none}` (upd-glow), `.gate-card.shake{animation:none}`, `.myst-quote{transition:none}`. Quote rotator JS (~:944): `RM = matchMedia('(prefers-reduced-motion: reduce)').matches` → swaps text instantly, no opacity fade. login.html has no embers canvas (verified — nothing to gate). |

## B) adventure.html

| # | Change | Before → After (anchors) |
|---|--------|--------------------------|
| B1 | P0 quota tip | `#quota-tip` (:567): `Each DM, TTS, Image-gen and background llm-calls counts towards the turns quota` → `Your turn quota — and when it refills. Click for your profile.` |
| B2 | News banner corrected | HTML (:885–892): `🔥 New — Qwen 3.8 Max (full release)` + spec text → `✦ New — Qwen 3.8 Flash in the free tier` / `Fast answers, light thinking, free for every account — set it as your Dungeon Master at the model gate or in Settings.` JS (~:2929–2948): `newsQwenLocked` variable + entire Patron branch + `API.me()` dependency **deleted** (banner now shows unconditionally unless dismissed — also removes one slow /api/me call); toast → single free-tier message; NEW dismiss key `news_qwen_flash_dismissed` (read :2934 / write :2944 identical); old key `news_qwen38_dismissed` untouched (only mentioned in a comment) so every existing user sees the corrected banner once. |
| B3 | Stepper label | `#stepper-toggle-label` (:958) `Nytt äventyr?` → `New adventure?` hardcoded. **i18n flag:** `i18n.js:605` maps `'Nytt äventyr?': 'New adventure?'` — the string is dictionary-translated. With the HTML now English, the dictionary entry becomes inert (SV→EN swap finds no Swedish source; `I18N.init('sv')` restoration of saved originals keeps English as-is). No i18n.js edit made per constraints. See "i18n follow-ups" below. |
| B4 | step-model restructure (§2.2) | (:1112–1150) DM row stays visible, its hover `?` tooltip dropped in favor of the always-visible merged note `The storyteller — every scene, every NPC, every whisper. Unsure? The default is safe — you can ask the DM once the tale begins.` (audit §2.2.1 recommendation). Duplicate notes :1066/:1072 cut. Guardian + Extraction + TTS rows (IDs unchanged: `adventure-guardian-model`, `adventure-extraction-model`, `adventure-tts` incl. `onchange="advTTSChanged(this)"`) + OpenRouter-quota note moved into collapsed `<details class="adv-details" id="adv-model-advanced">`, summary `⚙ Advanced — Lorekeeper, Extraction & Voice · sensible defaults are set` (hint in `.adv-sum-hint` span). Upgrade note `#model-gate-upgrade-note` shortened to one line under the DM select: `🔒 Patron (one-time 30€) unlocks the premium minds — view the paths →` (ID + tier-gated display logic at ~:2384 untouched). `🔄` note kept visible, reworded: `Every choice here can be changed mid-campaign, from Settings inside the chat.` Start button/hint kept. |
| B5 | ⭐ tag + default switch | `optionHtml()` (~:2320–2324): `qwen3.8-flash` option renders as `qwen3.8-flash ⭐ — free & fast` (premium-locked models still render `🔒 … — Patron (30€)`; flash is not in `PREMIUM_MODELS`). New `defaultModel()` (~:2325): DM/Guardian/Extraction/Char selects default to `qwen3.8-flash` when present, else `step-3.7-flash`, else first — replaces the old `step-3.7-flash` default at fill() (rostad-approved switch). |
| B6 | Progress indicator (§2.1) | All four `.step-num`: `↓` → `1 / 4`, `2 / 4`, `3 / 4`, `4 / 4` (:967, :993, :1009, :1113); restyled mono in new CSS block, gold glow + `step-float` animation kept. New `#step-rail` (4 stops: Language · Name · Adventurer · Dungeon Master) inserted directly above `#step-lang` (:959–964); `updateStepRail(activeId)` + `railGo()` (~:1588–1602) called from `revealStep()` and `goStep()`; done-stops clickable (back-nav), future stops inert. `#step-rail` added to the `.stepper-collapsed` hide-list (:104 minified selector). |
| B7 | localStorage memory (§2.3) | `pickLang(lang, noAdvance)` (~:1560) writes `dnd_onb_lang` and gained a `noAdvance` param + hides the welcome-back line on real picks. DM select: `change` listener (~:2349) + `startAdventure()` (~:2437) write `dnd_onb_dm_model`; `fill()` (~:2333–2346) reapplies the saved DM if it exists among **enabled** options (`CSS.escape` lookup, disabled check). Restore IIFE (~:1850–1866, placed after `ASK_HINTS`/`DARK_ARCH_KEYS` consts — TDZ-safe) reads `dnd_onb_lang`, calls `pickLang(saved, true)` — preselects the card + runs side effects but does NOT auto-reveal step-name — and shows `#lang-welcome-back`: `Welcome back — still English? Pick to continue, or switch.` (SV variant included). `resetStepper()` does not clear these keys (unchanged). |
| B8 | Character reveal (§2.4) | `#adv-char-model` label + `?` ask-wrap moved out of `#gen-row` into `<details class="adv-details" id="adv-char-model-advanced">` (summary `⚙ Which mind weaves your adventurer · default is fine`) directly under `#fw-wrap` (:1056–1064); `#gen-row` keeps Summon button + hint only. IDs unchanged — `populateModelGate`/`generateAdventurer` (:1918 reads `.value` inside closed details — works) untouched. Reveal polish in new CSS block: `.preview.show .pv-portrait` 78→132px (104px ≤640px), `.pv-head` centered, `.pv-name` → 1.8rem `!important` (needed: snes.css §26 forces `.9rem !important`). `.pv-actions` already Reroll + Continue only — verified, unchanged. Portrait-click paint modal kept. |
| B9 | Lightbox Esc fix (A2 §4.3) | keydown handler (~:2677–2680) gained the two audit one-liners: `if (#pf-lb-overlay.show) return closePfLightbox();` and `if (#adv-portrait-overlay.show) return closeAdvPortraitPreview();` — placed before the `#pf-overlay` check (innermost modal wins). |
| B10 | Gear-menu grouping | (:576–587) reordered: `Account` head → 🪞 Profile, 💳 Upgrade · `Realm` head → ✒ Release Notes (icon 📜→✒ per app-wide table), ⚒ The Forge · 👑 Admin (admin-gated, unchanged) · `.gm-sep` · 🔒 Log Out (red `.danger`, last; icon 🚪→🔒 per vocabulary table; label already `Log Out`, kept; `leaveGate()` unchanged). New `.drop-head` CSS in post-snes block (new class name — safe). No dropdown added; existing menu already has the ≤640px `position:fixed` override (:312), untouched. |
| B11 | Reduced motion | Page-level `@media (prefers-reduced-motion: reduce)` block added at END of the post-snes.css style block (~:528–537, wins cascade): scroll-behavior auto, step/continue/prepare/htp reveals static, `.step-num`/`.head-logo`/`.hero-bg .hb.on`/`.wa-status`/`.news-banner` animation none. JS: embers canvas fully gated — `const ADV_RM = matchMedia(...)`; `resize/spawn/glowSprite/tick()` + `tick()` call wrapped in `if (!ADV_RM) {…}` (~:2962–2976). `revealStep`/`goStep` scrolls routed through new `rmScroll()` helper (~:1542) → `behavior:'auto'` under reduced motion. |
| B12 | P2 quick wins | `.prompt-size-hint` static Swedish (:994 `#fw-size-hint`, :1123 `#wp-size-hint`) → `Drag the corner to make the box bigger` (bilingual `updateSizeHints()` dict kept). Ask-tips (§2.2.7): all five `ASK_HINTS` entries EN+SV reworded — onboarding instances now `Unsure? The default is safe — you can ask the DM once the tale begins.` (char/dm) / `Unsure? The default is safe.` (guardian/extraction/tts); matching static HTML tooltips updated. `<noscript><style>.step,.continue-wrap,.prepare-link,.htp{opacity:1;transform:none}</style></noscript>` added at end of body (:3105). |

---

## Verification evidence

**`node --check` on every inline `<script>` block (final files):**
```
login script#0 OK
adventure script#0 OK
adventure script#1 OK
adventure script#2 OK
adventure script#3 OK
```

**Brace balance, every `<style>` block (final files):**
```
login style#0 278/278 BALANCED · style#1 1/1 BALANCED (noscript)
adventure style#0 393/393 · style#1 121/121 · style#2 56/56 · style#3 48/48 · style#4 1/1 (noscript) — all BALANCED
```

**HTML tag balance** (python HTMLParser, full document): login.html `errors: [] unclosed: []`; adventure.html `errors: [] unclosed: []`. `<details>` 2 open / 2 close in adventure.html (raw `grep -c` counted 4 opens because two are inside comments — parser confirms real balance).

**Orphan-reference greps:**
- `newsQwenLocked` → 1 hit, a comment only (variable + branch deleted).
- `news_qwen38_dismissed` → comment only; `news_qwen_flash_dismissed` read (:2934) + write (:2944) identical.
- `qwen_flash_seen` read+write identical in login.html (:418 ×2 write, :897 read); `rn_12_seen` → 0 hits in login.html.
- `dnd_onb_lang` write (:1561) / read (:1854); `dnd_onb_dm_model` read (:2333) / write (:2350, :2437) — spellings identical.
- `adv-char-model` → HTML (:1059/:1060), JS reads (:1918, :2304) all consistent; `auth-btn`, `gate-reset`, `keep-logged-in-row` all have live HTML+JS pairs in login.html.
- `step-num">↓` → 0 leftovers; `Ask the Dungeon Master if unsure` → 0 leftovers; static `Dra i hörnet` → 0 leftovers (only the bilingual JS dict retains SV, by design).

**git:** working tree only — nothing staged, nothing committed (pre-existing dirty `backend/data/*` untouched). `git diff --stat` limited to the two owned files: adventure.html +298-line delta region, login.html +60 (other files' M flags pre-date this task / belong to S2/S3 waves).

## i18n.js follow-ups (NOT edited — flag only)
1. `'Nytt äventyr?': 'New adventure?'` (i18n.js:605) — now inert; adventure.html ships the English string directly. Safe to leave; remove in a future cleanup.
2. If a Swedish mirror of the new strings is ever wanted, candidates: `New adventure?`, the welcome-back line (already has an SV variant inline via `pickLang` side effects — none needed), `Your turn quota — and when it refills. Click for your profile.`, and the `⚙ Advanced — Lorekeeper, Extraction & Voice` summary. The ask-hints are already bilingual via `ASK_HINTS`.
3. login.html gate strings remain hardcoded English by design (audit §1.11 — single source is the applyAuthMode table).

## Notes for the parent / other agents
- S2 (snes.css): the global reduced-motion block being added there overlaps mine harmlessly — page-level block comes after the link and is the winning tie-breaker for the page-specific selectors.
- `.pv-name` needed `!important` because snes.css §26 sets `.pv-name{font-size:.9rem!important}`; my post-snes block wins on order.
- The news banner no longer calls `API.me()` at all — one fewer slow call on adventure load.
- Deploy (docker rebuild / cache-bust bumps) deliberately NOT done — parent handles it.
