# Audit A1 — Entry & Onboarding UX/UI
**Date:** 2026-09-17 · **Scope:** `frontend/login.html`, `frontend/adventure.html`, `frontend/newgame.html`, `frontend/characters.html`
**Method:** read-only code audit against the `frontend-design` principles (typography carries personality; structure is information; copy is design material; motion deliberate + reduced-motion respected; one aesthetic risk per surface).
**Identity baseline (keep):** dark fantasy Castlevania×DOS×terminal · gold+bone+arcane on ink · Cinzel display / Spectral body / mono data · UI copy in English · atmospheric but never obscure.

All line numbers verified against the files as of this audit. They will shift — implementation subagents should anchor on the element IDs/classes given alongside.

Severity: **P0** blocker · **P1** fix now · **P2** nice to have.

---

## 1. login.html — The Gate & landing

### 1.1 Compact gate layout (focus area 1)

**Current anatomy of `#gate` (login.html:660–735):**
- Left column: eyebrow + `h2 "Swear yourself in."` (666) + `.pitch-list` 3 items (667–676) + `.pitch-note` (677–678)
- Right column `.gate-card#gate-card` (681–722): `#gate-title`/`#gate-sub` (683–684) → username field (687–692) → password field (693–698) → `#keep-logged-in-row` (699–702) → hidden `#confirm-field` (703–708) → hidden `#email-field` (709–714) → `#auth-btn` CTA (715) → **three stacked toggle rows**: `#gate-toggle` (716), `#gate-reset` (717), `#reset-link-btn` (718) → `#gate-error` (719) → `.gate-foot` (721)

**Finding 1.1 — P1 — the gate card is vertically loose and bottom-heavy.**
Three separate centered toggle rows plus a 3-line gate-foot make the card ~40 % chrome below the CTA. The primary action competes with four text links.

**Proposed tighter layout (same elements, less stacking):**

```
┌────────────────────────────────────┐
│  Return to the Cauldron            │  #gate-title (h3)
│  The fire has been kept burning.   │  #gate-sub (italic, 1 line max)
│                                    │
│  ADVENTURER                        │
│  [ > Your name, brave one…      ]  │
│  PASSWORD                          │
│  [ > The secret word…           ]  │
│                                    │
│  ☑ Keep me logged in (30 days)     │  one row: checkbox left,
│                     Lost password? │  #gate-reset right-aligned link
│  ┌──────────────────────────────┐  │
│  │      ENTER THE REALM         │  │  #auth-btn — the only button
│  └──────────────────────────────┘  │
│  New here? Forge your name         │  #gate-toggle — the only text row
│  ─────────────────────────────     │
│  No email needed to play.          │  .gate-foot — one short line
└────────────────────────────────────┘
```

Concrete changes:
- Merge `#keep-logged-in-row` (699–702) and `#gate-reset` (717) into a single flex row: `display:flex;justify-content:space-between;align-items:center;margin:.2rem 0 .8rem`. `#gate-reset` becomes a right-aligned inline link (`Lost your password?` — no `<b>` gold treatment; it must not outshine the CTA). In register/reset modes the checkbox hides (already handled at :978–979) and the row collapses to just the link or nothing.
- Keep exactly **one** text-toggle row under the CTA (`#gate-toggle`) plus the mode-specific `#reset-link-btn` (718), which only appears in reset mode.
- Trim `.gate-foot` (721) — see finding 4.2.
- Net effect: card loses ~2 stacked rows; CTA is the visual terminus, toggles are footnotes.

**Finding 1.2 — P1 — CTA `#auth-btn` (login.html:715) says "What will the Cauldron Foretell?"**
A question, not an action; violates "a control says exactly what happens". DECISION ALREADY MADE: replace with active voice. The Foretell wordplay survives in `#gate-sub` only (and in the hero `.of` span at :528, which is a tagline, not a control — keep that one).

**Exact copy — all 3 auth modes.** Update in four places: static HTML :715, `setAuthBusy()` :950–952, `applyAuthMode()` :964–970, and the toggle rows :971–977.

| Element | login | register | reset |
|---|---|---|---|
| `#gate-title` (:683, :965) | `Return to the Cauldron` | `Forge Your Name` | `Lost Your Password?` |
| `#gate-sub` (:684, :966–970) | `The fire has been kept burning — what will the Cauldron foretell?` | `The Cauldron has been waiting for someone like you.` | `Speak your name and choose a new secret word. The pot remembers the rest.` |
| `#auth-btn` (:715, :964) | `Enter the Realm` | `Forge Your Name` | `Set a New Password` |
| `#auth-btn` busy (:950–952) | `Opening the gate…` | `Forging your name…` | `Re-forging your password…` |
| `#lbl-username` (:961) | `Adventurer` | `New Adventurer` | `Adventurer` |
| `#lbl-password` (:962) | `Password` | `Create a Password` | `New Password` |
| `#gate-toggle` (:971–975) | `New here? <b>Forge your name</b>` | `Already sworn in? <b>Return to the cauldron</b>` | `Remembered it after all? <b>Return to the cauldron</b>` |
| `#gate-reset` (:717) | `Lost your password?` | hidden | hidden |

**Finding 1.3 — P1 — reset mode copy is factually wrong.** `#gate-toggle` row at :717 says "Lost your name? **Re-forge it**" and reset-mode title/button (:964–965) say "Re-forge My/Your Name" — but the flow resets the **password**, not the name. Users scanning for "password" won't find it. Fixed by the table above ("Lost Your Password?" / "Set a New Password" / link "Lost your password?"). `#reset-link-btn` (:718) "📧 Send me a reset link" is fine as-is.

### 1.2 pitch-list & gate-foot (focus area 5)

**Finding 1.4 — P2 — pitch-list item 2 contradicts the page's own vocabulary (login.html:671–672).**
"We don't log who you are at the table — no names to the ledger, no tracking of players." The page itself has a section titled **"From the Ledger"** (:774–777) full of game data. "Ledger" doing double duty (release notes vs. surveillance) muddies the privacy promise.
**Fix (exact):** `<b>Your identity stays yours.</b> No player tracking, no analytics profiles — just a name and a secret word.`

**Finding 1.5 — P2 — pitch-list item 1 (:668–670) "no hourglass" is mildly obscure.** Borderline against "atmospheric but never obscure". Suggest: `No card, no countdown, no metered fate.` (Optional; the rest of the item is strong.)

**Finding 1.6 — P2 — `.gate-foot` (:721) is a run-on legal sentence.**
Current: "Powered by Qwen, DeepSeek & StepFun · self-registration, no email required — an email is added to your account before your first purchase". The last clause is confusing (an email *address* is added *by the user*, and only needed for purchases/reset links).
**Fix (exact):** `Powered by Qwen, DeepSeek &amp; StepFun · No email needed to play — add one any time for purchases or password resets.`
If 1.1's compact layout lands, shorten further to `No email needed to play.` and let the pricing page carry the rest.

**Finding 1.7 — P2 — hero CTA takes two hops to the gate.** `#hero-begin` "Begin Your Journey" (:537) points at `#pricing`; the single Free tier card there (:620–627) is itself an `onclick` to `#gate`. A newcomer clicking "Begin Your Journey" expects the gate. **Fix:** point `#hero-begin` at `#gate` directly (`href="#gate"`), keep the pricing card link as secondary.

**Finding 1.8 — P2 — logged-in continue card (:725–732).** CTA "Continue to the realm →" is fine and active; for vocabulary cohesion with 1.2 consider `Enter the Realm →` so the realm-entry action keeps one name across surfaces.

### 1.3 Reduced motion & errors (login)

**Finding 1.9 — P2 — reduced-motion block exists (:398–402) but is incomplete.** It covers `.rv` reveals, `scroll-cue` and smooth-scroll, but not: `upd-glow` banner pulse (:145–146), `hero-breathe` (:173–177), the `.gate-card.shake` error animation (:260–261), `myst-quote` 1 s opacity fade driven by JS `setInterval` (:925–940), and the embers canvas. **Fix:** extend the block:
```css
@media (prefers-reduced-motion:reduce){
  html{scroll-behavior:auto}
  .rv{opacity:1;transform:none;transition:none}
  .scroll-cue,.head-logo,.hero-bg{animation:none}
  #update-banner.show{animation:none}
  .gate-card.shake{animation:none}
  .myst-quote{transition:none}
}
```
and in the quote rotator (:936) skip the fade (`el.textContent = …` immediately) when `matchMedia('(prefers-reduced-motion: reduce)').matches`. Embers canvas: don't start `tick()` under reduced motion.

**Finding 1.10 — keep (no change).** Error copy is a model example of the house voice directing without apologizing: "The Cauldron remains sealed. Wrong name or password." (:1064), "Write your adventurer's name first." (:997), "The passwords do not match." (:1042). `#gate-error` has reserved height (:258) so the card doesn't jump. Keep.

**Finding 1.11 — P2 — i18n:** the gate hardcodes English throughout (i18n.js is loaded at :880 but unused in this section). That matches the "UI copy in English" identity — no action needed now, but note that any SV mirror of these strings must be added to `applyAuthMode()` in one place (the table in 1.2 is the single source).

---

## 2. adventure.html — Onboarding stepper

**Current flow:** `#step-lang` (:909) → `#step-name` (:934) → `#step-arch` (:950, tabs Summon/Forge, `#gen-row` :993–1000, reveal `#adv-preview` :1008–1026) → `#step-model` (:1047–1089). Navigation via `revealStep`/`goStep` (:1449–1470). Returning players get the whole stepper collapsed behind `#stepper-toggle` (:908, :1232–1243).

### 2.1 Progress indicator (structure = information)

**Finding 2.1 — P1 — a real 4-step sequence with zero progress signals.** All four steps carry the same `↓` glyph in `.step-num` (:911, :936, :952, :1049) — decorative, encodes nothing. A newcomer on step 3 has no idea a step 4 exists (and step 4 is where "Start" lives). This is exactly the case where numbering *is* appropriate: the content is a typed sequence.

**Fix — two parts:**
1. **Per-step counter:** replace the `↓` in each `.step-num` with `1 / 4`, `2 / 4`, `3 / 4`, `4 / 4` (mono or Cinzel, keep the gold glow + `step-float` animation). Cheap, no new elements.
2. **Rail above the stepper:** insert once, directly above `#step-lang` (after `#stepper-toggle`, :908):
```html
<div class="step-rail" id="step-rail" role="list" aria-label="Adventure setup progress">
  <span class="sr-stop on" data-for="step-lang" role="listitem"><i>1</i> Language</span>
  <span class="sr-stop" data-for="step-name" role="listitem"><i>2</i> Name</span>
  <span class="sr-stop" data-for="step-arch" role="listitem"><i>3</i> Adventurer</span>
  <span class="sr-stop" data-for="step-model" role="listitem"><i>4</i> Dungeon Master</span>
</div>
```
CSS: flex row, small caps Cinzel .62rem, letter-spacing .14em, dim bone; `.on` = gold + filled dot; `.done` = bone-bright with ✓ replacing the number. Wire-up: one function `updateStepRail(activeId)` called from `revealStep()` (:1449) and `goStep()` (:1459) — mark stops before active as `done`, active as `on`. Clicking a `done` stop may call `goStep()` (free; back-nav already exists). Hide the rail inside `.stepper-collapsed` alongside the steps (:104 selector list — add `#step-rail`).

### 2.2 step-model restructure (the big one)

**Current `#step-model` (:1047–1089):** 4 selects — DM (:1055–1059), Lorekeeper/Guardian (:1061–1065), Extraction (:1067–1071), TTS (:1073–1080) — each with a `?` ask-tooltip, **plus 5 `.dm-model-note` rows** (:1060, :1066, :1072, :1081, :1082) and the upgrade note `#model-gate-upgrade-note` (:1083). Notes :1060/:1066/:1072 duplicate their tooltips verbatim. For a newcomer this is 4 infrastructure decisions dressed as story choices.

**Finding 2.2 — P1 — step-model overwhelms; only the DM choice is a real player decision.**
**Fix — exact restructure:**

1. **Keep visible:** step-head (:1048–1054) + the DM row (:1055–1059) + its ask-tooltip. Keep note :1060 **only if** the tooltip is dropped; otherwise cut :1060 (redundant with the tooltip at :1058 — my recommendation: keep the note, drop the `?` tooltip on the DM row, since the note is always-visible and the tooltip is hover-only).
2. **Cut outright:** `.dm-model-note` :1066 and :1072 (verbatim duplicates of tooltips :1064, :1070).
3. **Move into collapsed Advanced:** everything from the Guardian row (:1061) through TTS row (:1080), plus note :1081 (OpenRouter quota) — wrapped in:
```html
<details class="adv-details" id="adv-model-advanced">
  <summary>⚙ Advanced — Lorekeeper, Extraction &amp; Voice <span class="adv-sum-hint">sensible defaults are set</span></summary>
  <!-- #adventure-guardian-model row (:1061–1065) -->
  <!-- #adventure-extraction-model row (:1067–1071) -->
  <!-- #adventure-tts row (:1073–1080) -->
  <!-- .dm-model-note (:1081) OpenRouter shared-quota note -->
</details>
```
`<details>` gives free keyboard/screen-reader support and collapsed-by-default state. **All element IDs stay identical** — `populateModelGate()` (:2184–2275), `advTTSChanged()` (:2279) and `startAdventure()` (:2297–2301) keep working untouched; selects inside a closed `<details>` still read/write `.value` fine.
4. **Keep visible below the details:** note :1082 (`🔄 Can be changed at any time in the campaign…`) — it's the reassurance that makes collapsing safe. Reword slightly: `🔄 Every choice here can be changed mid-campaign, from Settings inside the chat.`
5. **Upgrade note `#model-gate-upgrade-note` (:1083) — P2 rewrite.** Current copy front-loads the paywall into the last onboarding step and mixes model marketing with a price. Keep the element ID and the tier-gated display logic (:2268–2269); shorten to one line placed directly under the DM select:
   `🔒 Patron (one-time 30€) unlocks the premium minds — <a href="pricing.html">view the paths →</a>`
6. **⭐ tag on qwen3.8-flash — P1.** In `optionHtml()` (:2200–2204) label the free-tier fast model: `qwen3.8-flash ⭐ — free &amp; fast`. `qwen3.8-flash` is absent from `PREMIUM_MODELS` (:2199), i.e. genuinely free-tier, and the Ledger (login.html:780–785) already recommends it — the ⭐ makes the recommendation visible where the choice happens. **Decision for rostad:** also change the default at :2212/:2218 from `step-3.7-flash` to `qwen3.8-flash` when present (matches the Ledger's "our recommendation for the table tonight"); if not, at minimum the ⭐ tag must not contradict the preselected value.
7. **Ask-tooltip copy — P2:** "Ask the Dungeon Master if unsure." (:1058, :1064, :1070, :1079, :997) is illogical *during onboarding* — the DM doesn't exist yet. Change the onboarding instances to: `Unsure? The defaults are safe — you can ask the DM once the tale begins.`
8. **Start button (:1086):** `⚔️ Start — Awaken the Dungeon Master` is active-voice and on-brand. Keep. Hint :1087 keep.

### 2.3 localStorage memory for returning players

**Finding 2.3 — P1 — no memory of onboarding choices.** Only `dnd_tts_provider` (:2235, :2281), news dismissal and textarea heights persist. A returning player who collapses the stepper and clicks "New Adventure" (:902, :1237) re-answers language from scratch and loses their DM pick.
**Fix:**
- On `pickLang()` (:1483): `localStorage.setItem('dnd_onb_lang', lang)`.
- On page init (near `populateModelGate`, :2184): read `dnd_onb_lang`; if `'en'|'sv'`, pre-select the matching `.lang-card` (`classList.add('selected')`), set `advLang`, run the same side effects as `pickLang` minus auto-advance (`I18N.init`, `renderArchetypes`, `renderDarkSelect`, `renderAskHints`, button labels :1491–1500). Do **not** auto-reveal step-name — let the player confirm with one click; add to `#step-lang` a small line: `Welcome back — still <b>English</b>? Pick to continue, or switch.`
- On `#adventure-dm-model` `change` and in `startAdventure()` (:2297): `localStorage.setItem('dnd_onb_dm_model', dmModel)`. In `fill()` (:2205–2219), after setting defaults, apply the saved value if it exists among enabled options. Same pattern for guardian/extraction (`dnd_onb_guardian_model`, `dnd_onb_extraction_model`) — optional, they're in Advanced anyway.
- `resetStepper()` (:1472) must NOT clear these keys (it's a "start over this run", not "forget me").

### 2.4 Character reveal in adventure.html (focus area 3)

**Finding 2.4 — P1 — `#adv-char-model` dropdown sits in the generation row directly above the reveal (`#gen-row`, :993–1000).** The reveal moment (`#adv-preview`, :1008–1026) should be "look them in the eye": portrait, name, Continue/Reroll. Today the eye-line is preceded by a model selector + `?` tooltip + hint. 
**Fix:** move the `<label class="dm-model-label" for="adv-char-model">` (:994–996) and its ask-wrap (:997) **into the same `#adv-model-advanced` `<details>`** from 2.2 — or, since generation happens in step 3 before step 4 exists, into a small `<details>` of its own directly under the Fateweave editor (`#fw-wrap`, :978–992):
```html
<details class="adv-details" id="adv-char-model-advanced">
  <summary>⚙ Which mind weaves your adventurer <span class="adv-sum-hint">default is fine</span></summary>
  <!-- label + #adv-char-model (:994–996) + ask-wrap (:997) move here, IDs unchanged -->
</details>
```
`#gen-row` (:993) then holds only `#gen-btn` "🔮 Summon Adventurer" and `#gen-hint`. JS at :1802–1803 and :2188/:2214–2219 keeps working (IDs unchanged).
**Reveal hierarchy polish (same pass):** in `.preview.show` state make the portrait the hero — `.pv-portrait` (:241) from 78px to ~132px, `pv-head` centered, `.pv-name` (:243) up to ~1.8rem; vitals row (:1858–1864) already leads with ❤️ HP — keep. `.pv-actions` (:1021–1025) already contains only Reroll + Continue — good; keep the portrait-click → paint modal (:1010, `openAdvPaintModal`) since it's a modal, not inline clutter, and it has keyboard support (`role="button"`, `tabindex`, keydown) — a good pattern the other pages should copy.

### 2.5 Language & motion issues (adventure)

**Finding 2.5 — P1 — Swedish string in an English UI: `#stepper-toggle-label` (:908) reads "Nytt äventyr?".** This is the *first thing a returning player sees* when the stepper is collapsed. **Fix:** `New adventure?` (keep the 🎲). If bilingual is wanted, set it via `isEn()` — but the identity says UI copy in English; hardcode `New adventure?`.

**Finding 2.6 — P2 — Swedish initial text in `.prompt-size-hint` (:990, :1109) "Dra i hörnet för att göra rutan större".** `updateSizeHints()` (:1733–1739) only runs after a language pick (`renderAskHints` ← `pickLang` :1490) — before that, the English-default page shows Swedish microcopy. **Fix:** ship the English string in the HTML (`Drag the corner to make the box bigger`) and/or call `updateSizeHints()` once on init.

**Finding 2.7 — P1 — no `prefers-reduced-motion` anywhere in adventure.html.** The page has: `step-float` infinite bob (:119–120), `rise` reveals, `head-float` (:23), `hero-breathe` (:23), `w-blink` (:220), `cp-breathe` (:67), reveal-on-scroll opacity/transform (:224–226), the embers canvas `tick()` (:2835–2837), and smooth `scrollIntoView` in JS (:1454, :1468, :1241, :1806…). snes.css's single reduced-motion rule (snes.css:2807) only covers `.ward-pulse`. **Fix:** add the global block (same as characters/newgame, see 4.1) **plus**:
```css
@media (prefers-reduced-motion: reduce){
  html{scroll-behavior:auto}
  .step,.continue-wrap,.prepare-link,.htp{opacity:1;transform:none;transition:none}
  .step-num,.head-logo{animation:none}
  .hero-bg .hb.on{animation:none}
  .w-status{animation:none}
}
```
and in JS gate `scrollIntoView({behavior:'smooth'})` + `tick()` behind `!matchMedia('(prefers-reduced-motion: reduce)').matches` (use `behavior:'auto'` / don't start embers).

**Finding 2.8 — P2 — steps start at `opacity:0` (:224) and only appear via JS.** login.html has a `<noscript>` failsafe (:876); adventure.html has none — with JS blocked the entire onboarding is invisible. **Fix:** add `<noscript><style>.step,.continue-wrap,.prepare-link,.htp{opacity:1;transform:none}</style></noscript>`.

---

## 3. newgame.html — "Choose Your Fate"

**Finding 3.1 — P1 — stale label "Step one of three" (:191).** The page is one long scroll (language → Vault → I. Archetypes → II. Fateweave → III. preview); nothing is step one of anything, and adventure.html's stepper owns the "steps" concept now. **Fix (exact):** replace `<div class="over">Step one of three</div>` with `<div class="over">A New Adventure</div>` — or delete the `.over` line entirely; `h1 "Choose Your Fate"` (:192) + `.destiny-sub` (:194) carry it.

**Finding 3.2 — P1 — language select forces a choice with no default (:200–204).** `<option value="" disabled selected>— click to select Campaign Language —</option>`, and `summon()` hard-blocks with a toast (:819–828, `'Välj kampanjspråk först!'` — itself a Swedish toast on an English page). The code comment at :818 says "no default — deliberate design", but the decision is now reversed: a default removes a pointless decision gate while keeping the choice visible.
**Fix:**
```html
<select id="lang-select" class="dark-select lang-dropdown" onchange="onLangChange(this.value)">
  <option value="en">🌐 English</option>
  <option value="sv">⚔️ Svenska</option>
</select>
```
On init call `onLangChange(I18N.getLang() === 'sv' ? 'sv' : 'en')` (i18n.js already loaded at :310; `onLangChange` :492–522 sets select value, hint text and re-renders templates — safe to call once at boot). Keep the `!selLang` guard in `summon()` (:820) as dead-safety. Also note: the ⚔️ emoji for Svenska is a branding quirk shared with adventure.html (:926) — harmless, keep for consistency, or swap both to 🇸🇪 in one pass (decision for rostad; don't diverge the two pages).

**Finding 3.3 — P1 — reveal is not a clean "look them in the eye" moment (:273–295).**
- `#char-model` raw-ID dropdown (:239–248) sits in `.scroll-actions` immediately above the preview; labels are raw model IDs (`PLAYER_CHAR_LABELS` identity map, :322–323 — "deepseek-v4-flash-0731" etc.). The comment says raw IDs are deliberate; that's acceptable for the *Forge* power-user surface, but on the newcomer path the dropdown should at least not compete with the reveal. **Fix:** wrap the "🧙 Character:" label + `#char-model` (:238–248) in `<details id="ng-char-model-advanced"><summary>⚙ Which mind weaves your adventurer <span>default is fine</span></summary>…</details>` (same pattern as 2.4; IDs unchanged so :332–348 keep working).
- `.pv-actions` (:289–293) has **three** buttons: "⚔️ To the Table", "🔄 Reroll Fate", "🎨 Paint Avatar" (`#pv-avatar-reroll`, hidden until an avatar exists). Per the brief, Continue/Reroll must be the only choices. **Fix:** make `#pv-icon` (:278) clickable like adventure.html's `#adv-pv-portrait` (:1010): add `onclick`, `role="button"`, `tabindex="0"`, keydown handler → open a small paint/preview modal (port `openAdvPortraitPreview`/paint-modal pattern from adventure.html :746–761, :1980+), and remove `#pv-avatar-reroll` from `.pv-actions`.
- Portrait size in reveal: `.pv-portrait` is 84px (:117 block), 68px ≤640px (:123). For the reveal moment bump to ~120px centered (same treatment as 2.4) — name (`pv-name` 1.5rem) / class / vitals hierarchy is already correct.

**Finding 3.4 — P2 — mixed-language toasts.** `'Kunde inte generera avatar'` (:974, :977) hardcoded Swedish inside English flows (other toasts use `I18N.t` or English). **Fix:** wrap in `I18N.t(...)` or hardcode English: `Could not paint the avatar`.

**Finding 3.5 — P2 — retry copy (:267).** "The weaving broke. You can try again — each attempt costs one turn. If it keeps failing, contact the game creator for a top-up." Direct and honest — keep the first two sentences; "contact the game creator for a top-up" is vague (top-up of what?). **Fix:** `…If it keeps failing, write to web@rostad.cc.`

**Finding 3.6 — P1 — no `prefers-reduced-motion` in newgame.html.** Animations: `msg-in` (:117), `card-in` (:118), `w-blink` (:85), `w-pulse` (:111), embers `tick()` (:1016–1018), smooth scrolls in `summon()` (:811). **Fix:** same global block as 4.1 + JS gating of `tick()`/`scrollIntoView`.

---

## 4. characters.html — The Forge

**Finding 4.1 — P1 — zero reduced-motion coverage.** The page runs: infinite `w-blink` (:39–40), `msg-in` reveals (:47–48), toast slide (:85), hover transforms (:63), `html{scroll-behavior:smooth}` (:18), smooth `scrollIntoView` in JS (:289, :303, :370), and the embers canvas loop (:565–574 — pauses on `document.hidden` only). **Fix — add before `</style>` (:109):**
```css
@media (prefers-reduced-motion: reduce){
  html{scroll-behavior:auto}
  *,*::before,*::after{animation-duration:.01ms!important;animation-iteration-count:1!important;transition-duration:.01ms!important}
  .w-status{animation:none}
}
```
and in JS: `const RM = matchMedia('(prefers-reduced-motion: reduce)').matches; if (!RM) tick();` + `behavior: RM ? 'auto' : 'smooth'` in the three `scrollIntoView` calls. (Same JS pattern for newgame/adventure.)

**Finding 4.2 — P1 — vault cards are mouse-only.** `.vcard` is a `<div onclick="openInspect(...)">` (:415, built in `renderVault()` :409–433) with `cursor:pointer` (:61) but no `role`, `tabindex`, or keyboard handler — keyboard/AT users cannot open any character sheet. Contrast: adventure.html's portrait (:1010) does it right. **Fix:** in the card template add `role="button" tabindex="0" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();openInspect('${esc(c.id)}')}"`, plus `:focus-visible{outline:2px solid var(--gold);outline-offset:2px}` on `.vcard`. Keep the inner `.vcard-dl` button (:422) with `event.stopPropagation()` (already done at :496).

**Finding 4.3 — P2 (flag for lightbox workstream) — portraits have no enlarge ability.** Integration points:
- `#pv-icon` `.pv-portrait` (:171, filled in `renderPreview()` :339) — fresh forge preview; currently static (unlike adventure.html where the same class is clickable).
- `.vcard-avatar` (:66–67 CSS; template :417 in `renderVault`) — clicking it opens the inspect modal (whole card does); a lightbox should trigger on the avatar itself with `stopPropagation`, or the inspect modal's portrait should be the zoom target.
- `#insp-avatar` (:461–462, inside `openInspect()` template) — **primary lightbox target**: user is already focused on the character; the 84px portrait is the only place the painted art shows at all.
- Reusable prior art: adventure.html `#adv-portrait-overlay` / `.pp-portrait` modal (:746–761) with re-roll + close; the lightbox workstream can lift that pattern (and should also add Esc-to-close + focus trap, which the mi-overlay modals partially have).
- Note `.vcard-dl` "Download portrait" (:422, :495–504) exists — a lightbox should sit beside it, not replace it.

**Finding 4.4 — P2 — Roman numerals encode a sequence that isn't one.** Section labels: `I. Forge an Adventurer` (:131), `II. The Forged Adventurer` (:168), `III. The Vault` (:190). II only exists after forging; III (the Vault) is a permanent gallery, not a step. Structure-is-information says the numbering lies. **Fix:** keep `I.`/`II.` (forge → result *is* a sequence) and drop the numeral on the Vault: `The Vault` (the `✦`-style divider already separates it). Or drop all numerals and let order speak.

**Finding 4.5 — P2 — two different confirm dialogs.** Native `confirm()` for the duplicate-name warning (:361) vs the themed `Modal.confirm` for delete (:523–530). The native dialog breaks the world completely (browser chrome, English only). **Fix:** use `Modal.confirm({title:'Save a twin?', body:'"' + name + '" already rests in your Vault. Save this one anyway?', confirmText:'Save anyway', cancelText:'Cancel'})`.

**Finding 4.6 — P2 — mixed-language labels.** `#forge-lang` options "English sheet" / "Svenskt ark" (:148–149) — half-Swedish in an English UI. **Fix:** `English` / `Svenska` (the select's context — "🌐" label at :146 — already says it's language).

**Finding 4.7 — P2 — textarea has no accessible name.** `#forge-prompt` (:133) relies on placeholder only. **Fix:** `aria-label="Describe your adventurer"`. Same for the inspect-modal prompt textarea (:481), which additionally uses Cinzel (display face) at .72rem for *input text* — hard to read; switch that textarea to `var(--font-body)`.

**Finding 4.8 — keep (no change).** The empty state (:192) "The vault is empty. Forge an adventurer above — or save one from an adventure." is a proper invitation to act. Error toasts (:284, :310, :372) are direct. The placeholder-sigil SVG (:384–389) instead of a broken 🎭 emoji is a thoughtful touch. The delete confirm's "Unmake" vocabulary (:524–527) is the house voice at its best.

---

## 5. Cross-page notes

**Finding 5.1 — P1 — reduced-motion is a systemic gap.** Only login.html (:398) and one snes.css rule (:2807) have any coverage. adventure.html, newgame.html, characters.html have none, and all three run a permanent embers canvas + infinite blink/float animations. One shared block (4.1) + the JS `RM` guard fixes all three; consider hoisting the CSS into snes.css §-new so future pages inherit it (page-level blocks must still come after the snes.css link per the override ordering — but a reduced-motion block in snes.css itself needs no override).

**Finding 5.2 — P2 — the "advanced model picker" pattern should be one component.** Findings 2.2, 2.4, 3.3 all introduce the same `<details class="adv-details">` with identical summary styling. Define the CSS once (adventure.html's post-snes.css override block, :317–496, is the right home; characters/newgame inline their own copies as they already do for shared components — e.g. `.pv-*` is duplicated in all three).
Summary copy standard: `⚙ Advanced — <what's inside>` + dim hint `sensible defaults are set`. Closed by default. Never required to complete onboarding.

**Finding 5.3 — P2 — vocabulary cohesion check.** After the login CTA change, the realm-entry action appears as: "Enter the Realm" (login CTA), "Continue to the realm →" (login continue-card :730), "Enter" (nav :427), "⚔️ To the Table" (newgame :290), "⚔️ Start — Awaken the Dungeon Master" (adventure :1086). That's acceptable register variation (gate → table), but "Enter the Realm" should be the canonical phrase wherever a *login/gate* action is meant; don't introduce new synonyms in the implementation pass.

---

## 6. Prioritized fix list

| # | Sev | File:line (anchor) | Fix |
|---|-----|--------------------|-----|
| 1 | P1 | login.html:715, :950–952, :964–970 (`#auth-btn`, `setAuthBusy`, `applyAuthMode`) | Replace "What will the Cauldron Foretell?" with active-voice CTAs per mode table (§1.2): login `Enter the Realm`, register `Forge Your Name`, reset `Set a New Password`; move Foretell wordplay to login `#gate-sub` |
| 2 | P1 | login.html:717, :965 (reset mode copy) | "Lost your name? Re-forge it" → "Lost your password?" / title "Lost Your Password?" — reset resets the password, not the name |
| 3 | P1 | login.html:699–702 + :717 (`.keep-logged-in` row) | Compact gate: merge keep-logged-in checkbox and password-reset link into one flex row; single toggle row under CTA; trim gate-foot (§1.1) |
| 4 | P1 | adventure.html:908 (`#stepper-toggle-label`) | "Nytt äventyr?" → "New adventure?" |
| 5 | P1 | adventure.html:1047–1089 (`#step-model`), :2184–2275 (`populateModelGate`) | Collapse Guardian/Extraction/TTS + notes :1066/:1072/:1081 into `<details id="adv-model-advanced">`; DM select stays visible with ⭐ on `qwen3.8-flash — free & fast` (:2200–2204); shorten upgrade note :1083; keep "can be changed any time" note (§2.2) |
| 6 | P1 | adventure.html:911/:936/:952/:1049 (`.step-num`) + new `#step-rail` above :909 | Progress: `N / 4` counters + 4-stop rail updated from `revealStep`/`goStep`; hide under `.stepper-collapsed` (§2.1) |
| 7 | P1 | adventure.html:1483 (`pickLang`), :2205–2219 (`fill`) | localStorage memory: `dnd_onb_lang`, `dnd_onb_dm_model` — preselect on return, no auto-advance (§2.3) |
| 8 | P1 | adventure.html:993–997 (`#gen-row` → `#adv-char-model`) | Move character-model select + tooltip out of the generation row into `<details id="adv-char-model-advanced">`; reveal keeps portrait/name/Reroll/Continue only; enlarge portrait in `.preview.show` (§2.4) |
| 9 | P1 | newgame.html:191 | Stale "Step one of three" → "A New Adventure" (or remove) |
| 10 | P1 | newgame.html:200–204 (`#lang-select`), :492 (`onLangChange`) | Remove empty disabled option; default to `I18N.getLang()` or `en`; call `onLangChange` at init (§3.2) |
| 11 | P1 | newgame.html:238–248 (`#char-model`), :289–293 (`.pv-actions`), :278 (`#pv-icon`) | Collapse model select into `<details>`; make portrait clickable (paint/preview modal) and drop `#pv-avatar-reroll` from reveal actions — "To the Table" + "Reroll Fate" only (§3.3) |
| 12 | P1 | characters.html:415 (`renderVault` template) | Vault cards keyboard-accessible: `role="button" tabindex="0"` + Enter/Space handler + `:focus-visible` outline (§4.2) |
| 13 | P1 | adventure.html (none), newgame.html (none), characters.html (none), snes.css:2807 | Add reduced-motion blocks + JS guard for embers `tick()` and smooth `scrollIntoView` on all three pages (§4.1, §5.1) |
| 14 | P2 | login.html:398–402 | Extend existing reduced-motion block: upd-glow, hero-breathe, shake, myst-quote fade (§1.9) |
| 15 | P2 | login.html:671–672, :668–670, :721 | pitch-list privacy copy (drop "ledger" double-meaning), "hourglass"→"countdown", gate-foot rewrite (§1.2) |
| 16 | P2 | login.html:537 (`#hero-begin`) | Point hero CTA at `#gate` instead of `#pricing` (§1.7) |
| 17 | P2 | adventure.html:990, :1109 (`.prompt-size-hint`) | Ship English initial hint text / call `updateSizeHints()` at init (§2.6) |
| 18 | P2 | adventure.html:1058/:1064/:1070/:1079/:997 (`.ask-tip`) | "Ask the Dungeon Master if unsure" → onboarding-appropriate copy (§2.2.7) |
| 19 | P2 | adventure.html — end of `<body>` | Add `<noscript>` failsafe for `.step{opacity:0}` reveals (§2.8) |
| 20 | P2 | newgame.html:974/:977, :267 | De-Swedish avatar error toasts; sharpen retry contact copy (§3.4–3.5) |
| 21 | P2 | characters.html:131/:168/:190, :361, :148–149, :133/:481 | Section numerals (drop III), native `confirm()`→`Modal.confirm`, lang labels EN/SV, textarea aria-labels + body font for inspect prompt (§4.4–4.7) |
| 22 | P2 | characters.html:171/:339, :417, :461–462 | Lightbox integration points flagged for the separate workstream; reuse adventure.html `#adv-portrait-overlay` pattern (:746–761) (§4.3) |
| 23 | P2 | decision for rostad: adventure.html:2212/:2218 | Switch onboarding DM default `step-3.7-flash` → `qwen3.8-flash` (Ledger already recommends it; must not contradict the ⭐ tag) (§2.2.6) |

**No P0s found.** Nothing blocks a user from entering or completing onboarding today; the P1 set is about clarity, the stale Swedish strings, the wrong reset vocabulary, keyboard access, and reduced-motion — all cheap, high-leverage fixes.
