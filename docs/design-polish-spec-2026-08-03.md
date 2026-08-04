# Design Polish Spec — The Lore Weaver's Cauldron (2026-08-03)

D&D LLM game at `~/dnd-llm/`. Brand: **The Lore Weaver's Cauldron** (dnd.rostad.cc). Dark-fantasy × terminal, **not** flashy. English UI chrome (game language separate). Do NOT use generic templates / "50% template" looks.

## Client / design tokens (AUTHORITATIVE — from snes.css, which wins via `!important`)

CSS custom properties on `:root` (also overridable per-theme by themes.js):
- `--ink` (bg), `--stone`/`--stone-2`/`--stone-3` (panels), `--edge`/`--edge-hi` (borders)
- `--bone`/`--bone-bright`/`--bone-dim` (text), `--gold`/`--gold-bright` (sacred/UI/CTA)
- `--blood`/`--blood-bright` (HP/danger), `--ember` (warmth/quests), `--arcane`/`--arcane-bright` (magic/player), `--poison` (success/equipped)
- Fonts: `--font-display` (Cinzel), `--font-body` (Spectral), monospace = `VT323`/`IBM Plex Mono`
- Semantic: gold = sacred/UI · blood = HP/danger · arcane = magic/player · ember = warmth/quests · poison = success/equipped

Any new CSS must use these vars (never hardcoded hex) so every theme (5 palettes) and the theme switcher keep working. **snes.css is the theme** — new classes that snes.css might kill via `!important` need unique names (e.g. `.myst-fog` not `.fog`).

## Stack / deploy
- Backend FastAPI `backend/main.py` (~5.2k lines), frontend vanilla JS in `frontend/`.
- Deploy: `docker compose up -d --build` (background), health=`curl localhost:8092/api/health`, then `git add -A && git commit && git push origin main`.
- Verify backend: `cd backend && python3 -c "import main"`. Verify frontend JS: extract inline `<script>` and `node --check`.
- **After every edit to a shared asset (snes.css / api.js / themes.js), bump the `?v=N` cache-bust version on ALL pages that load it** (monotonic counter).

## File ownership (NON-NEGOTIABLE — subagents must NOT touch files outside their whitelist)

| Track | Files (whitelist) | Scope |
|---|---|---|
| **A — Login redesign** | `frontend/login.html` ONLY | Item 2 |
| **B — Feedback feature** | `backend/main.py`, `frontend/api.js`, `frontend/adventure.html` ONLY | Item 1 (adventure/cauldron part) |
| **Parent — Chat polish** | `frontend/chat.html`, `frontend/snes.css`, `frontend/themes.js` | Items 3,4,5,6,8,9 + in-game feedback button (Item 1 chat part) |

**Parent also adds the in-game feedback button in chat.html** (Item 1 chat half) — so Track B must NOT touch chat.html. Track B defines the shared API method name in api.js; parent calls it.

---

## Item 1 — Feedback button + form (NEW feature)

Button in TWO places:
- **adventure.html** (the Cauldron landing/onboarding) — Track B.
- **chat.html** (in-game) — Parent.

Behavior: a small form modal with **email field (optional)** + **suggestion/feedback textarea (required)** + submit. On submit → POST to backend → stored → toast "Thanks / Tack". Must be keyboard-accessible (Esc closes), styled with the dark-fantasy tokens (gold CTA, stone card, corner ornaments).

**API contract (Track B defines; parent consumes):**
- `POST /api/feedback` body `{email: string|null, message: string}` (cookie auth; optional email; validate loosely, message required non-empty).
- Response: `{ok: true}` or 400 with `{detail}`.
- Store: append to `backend/data/feedback.jsonl` (create dir if missing). No DB.
- api.js method: `API.sendFeedback({email, message})` → `fetch('/api/feedback', {method:'POST', headers:{'Content-Type':'application/json'}, credentials:'include', body: JSON.stringify(...)})`.

### adventure.html button (Track B)
- Place a subtle **"💬 Feedback"** link/button in the footer of adventure.html (near the existing footer links / Release Notes). Opens a small modal (reuse the `.tablet`/`.rv` card styling or a new `.fb-modal` overlay). Keep it small and styled to match.

### chat.html button (Parent)
- Add a subtle **"💬 Feedback"** icon button in the topbar (or Tools dropdown) that opens the same modal. Parent owns the modal markup in chat.html.

---

## Item 2 — Login page redesign (Track A, login.html ONLY)

Goal: "Begin Your Journey" hero heading + the login (gate) forms prettier + **smaller/more compact**.

Current: `.gate-grid` two-column, `.gate-card` (blurred card + corner ornaments), "Return to the Cauldron" login card, toggle link to register. Brand hero "Begin Your Journey" CTA at `<a class="btn-gold" id="hero-begin">`.

Changes:
- Reduce the gate-card form size: smaller padding, smaller headings, tighter field spacing, smaller button. Keep it elegant, not cramped.
- Make the "Begin Your Journey" hero + nav CTA more refined (consistent gold styling, subtle glow).
- Do NOT change the dark-fantasy visual language, the cauldron 3D background, or the features grid. Keep `.gate-toggle` (login↔register switch) working — the JS (`#auth-form`, `#gate-title`, `#gate-sub`, `#username`, `#password`, register toggle) must stay intact.
- Verify: `node --check` the inline `<script>`, and confirm the login/register flow still submits (don't break the submit handler).

---

## Item 3 — Chat composer too tall (Parent, chat.html + snes.css)

Current composer: `.composer` (stone-2, 1px edge, gold focus) + `.input-row textarea` (min-height 52px, max 140px, padding 0.8rem 0.9rem 0.8rem 1.7rem) + `.send-btn` "⚔ Act". `.input-area` has extra top padding (0.7rem) + `.tts-voice-picker` row above.

Goal: **make the composer shorter in height** (it's too big). Reduce textarea min-height (~52→40px), reduce padding, reduce `.input-area` top padding, tighten `.send-btn` padding. Keep touch-target ≥44px on mobile (snes.css mobile block may hardcode `.input-area textarea` padding — adjust there too, noting the mobile `>`-overlap pitfall: keep left padding ~1.8rem). Keep the gold focus glow.

---

## Item 4 — Combat log button placement (Parent)

Current: `.battle-drawer-toggle` button ("⚔ Stridslogg ▲") sits centered under the chat (`margin: .3rem auto .15rem`), inline in the layout flow — user finds it misplaced. It opens the battle-log pane (right column) / maximizes.

Goal: **move it out of the chat flow** to a clean, fixed, always-available spot. Options the user suggested: a small icon button with crossed swords/knives (⚔️) for a maximize toggle. Recommended: a **fixed bottom-right floating button** (above the composer, clear of mobile bottom-nav) with a sword icon, toggling the battle log. Keep the existing `toggleBattleLog()` JS + `#battle-drawer-toggle` + `body.battle-drawer-open` CSS contract — just relocate/restyle the button (change its position to fixed, give it a sword glyph, compact size). Update the mobile CSS (snes.css) for the new position. Don't break the auto-open-on-combat behavior.

---

## Item 5 — CLI-terminal chat (design question → implement a tasteful version)

User asks: incorporate the chat like a CLI terminal — a caret/prompt that "ticks" in the chat itself.

Feasible + already partially present: the composer uses a `>` prompt (`.input-row::before` / `.scribe-prompt "❯"`), and the DM status uses a `❯` + blinking `▌` cursor. 

Implementation (Parent, tasteful, not overdone):
- Add a **blinking terminal block cursor** (`▌`, `@keyframes` blink) inline at the end of the composer when focused — a terminal-style prompt feel. Keep the existing `>` glyph.
- Optionally make the composer prompt a `❯` in a terminal-green accent (subtle).
- Do NOT rewrite the whole chat into a terminal UI — just the prompt/caret affordance. Keep it dark-fantasy, low-key.

---

## Item 6 — Chat log bubbles (Parent)

Goal: nicer frames for DM-said vs player-said, softer.

Current:
- `.msg.dm .bubble` = gold gradient, gold border, italic serif text, corner ornaments `.bubble::before/::after` (gold accent). DM text 1.18rem.
- `.msg.player .bubble` = arcane (purple) border, right-aligned, bone-bright text.
- `.bubble` = 1px `--edge` border, radius 3px, corner brace ornaments.

Changes: soften/refine the bubbles — slightly rounder corners (radius 3→4-6px), softer border colors, more subtle gradient, better spacing between bubbles, refined corner ornaments. Keep the role color-coding (DM gold / player arcane / NPC neutral). Make DM vs player visually distinct but harmonious. Don't break the `.who` nameplate, `.text` rendering, TTS button, or dice badges.

---

## Item 8 — Debug log placement (Parent)

Current: `.console` (MASKINRUMMET / "Engine Room") is a fixed bottom-right panel (420px, max-height 45vh, flat #0a0a12, VT323 monospace). Opened via Tools dropdown "The Engine Room" / `toggleConsole()`.

Goal: better placement. User finds it awkward. Recommended: keep it as a bottom-right floating panel but make it **collapsible to a slim tab**, more compact, and ensure it doesn't cover the composer abruptly. Give it a clear "Engine Room" (🛠️) title and a collapse/minimize affordance. Keep the filter chips (All/Debug/Info/Warn), autoscroll, clear, count. Don't break `toggleConsole`, `pollConsole`, `setConsoleLevel`, `clearConsole`.

---

## Item 9 — Theme switcher prettier (Parent)

Current: `themes.js` injects a single `🎨 ThemeName` button into the topbar (`.theme-btn`) that `cycle()`s through 5 palettes (terminal/blood/arcane/ember/iron) on click. Works but is a bare text button.

Goal: make it prettier. Recommended: a compact **🎨 swatch button** — a small button showing a palette (3-4 color dots) + current theme name, that opens a small popover/menu listing all 5 themes with live color swatches; clicking one applies + closes. Reuse the existing THEMES API (`THEMES.cycle()`, `THEMES.apply(id)`, `THEMES.current()`, `PALETTES`). Keep `syncToServer()` + `hydrateFromServer()` working. Keep the `.theme-btn` class so existing injection logic still finds it. Mobile: keep it compact in the topbar.

---

## Item 7 — Inconsistent design decisions (audit + fix)

Parent performs a read-only audit of the frontend for obvious design inconsistencies (mismatched radii, inconsistent spacing, competing border styles, leftover dead classes, mixed SV/EN UI strings that should be EN, duplicate/inconsistent controls). Fix the clear ones inline. Do NOT spawn a subagent for this — parent does it (per rostad's preference: cleanup done sequentially by parent).

## Constraints / pitfalls recap
- snes.css wins with `!important` — new classes need unique names if snes.css targets a generic name.
- Bump `?v=N` on all pages after editing snes.css / api.js / themes.js.
- Mobile: text inputs ≥16px font (iOS zoom), ≥44px touch targets, safe-area padding.
- Emoji in inline shell commands trips the approval gate — use ASCII-command scripts via write_file.
- Don't touch working-tree uncommitted work (there's a lot); build on top.
- English UI chrome (except campaign language + newgame language toggle + SV archetypes).