# Wave 2 · S3 implementation report — content/onboarding pages UX fixes

**Date:** 2026-09-17 · **Agent:** S3 of 3 (disjoint files)
**Specs:** `docs/audit-a2-ingame-2026-09.md` (§1.4–1.7, §4, §5) + `docs/audit-a1-onboarding-2026-09.md` (§3–4)
**Scope:** newgame, characters, character, npcs, platser, loggbok, facts, help, mechanics, releases, pricing, models, reset, screenshots, book-souls/index, admin + new `frontend/assets/screens/` (5 jpgs copied from `docs/screenshots/`).
**Untouched (hard constraint honored):** chat.html, snes.css, login.html, adventure.html, i18n.js, api.js, all `?v=` strings. No git add/commit. No deploy.

---

## 1. newgame.html

| Change | Anchor (post-edit) | Detail |
|---|---|---|
| Stale step label | `.over` (was :191) | "Step one of three" → **"A New Adventure"** |
| Language default | `#lang-select` (was :200–204) | Removed `<option value="" disabled selected>`; only `en`/`sv` remain. Boot call added after the `mode-label` init: `onLangChange(I18N.getLang()==='sv' ? 'sv' : 'en')` — sets select, hint text, and re-renders templates (safe: `onLangChange` re-sets `sel.value` and the untouched-prompt guard applies) |
| Swedish block-toast | `summon()` `!selLang` guard (~:850) | **Kept as dead-safety per spec.** With a default now applied at boot, `selectedLang()` can no longer return empty in practice; the `I18N.t('Välj kampanjspråk först!')` toast stays but is unreachable via UI. Dict entries `i18n.js:131/:880` still valid (see i18n section) |
| Advanced model picker | `#ng-char-model-advanced` (was :238–248) | `#char-model` select + "🧙 Character:" label wrapped in `<details class="adv-details">` with summary **"⚙ Advanced — character model · sensible default is set"**. IDs unchanged → `API.me()` role-gating (~:332) and `summon()` (~:842) keep working. New `.adv-details` CSS appended to page style block (before `</style>` at old :175) |
| Reveal actions | `.pv-actions` (was :278–293) | **#pv-avatar-reroll removed from reveal** — actions are now only "⚔️ To the Table" + "🔄 Reroll Fate". `#pv-icon` made clickable: `role="button" tabindex="0"` + click/Enter/Space → `openPvPortrait()` lightbox (portrait preview + 🎨 paint action inside, per audit A1 §3.3 "lightbox-first, paint one click deeper") |
| Portrait lightbox | new `#pv-lightbox` + CSS | Shared §4.3 pattern: Esc + backdrop close, gold frame, lazy img slot, title = character name, `.av-lb-act` paint button → `pvLbPaint()` (reuses existing `rerollAvatar()`; button state synced in its `finally`). When no portrait is painted yet, shows the sigil big + offers "🎨 Paint a portrait" (paint still reachable — no dead-end after removing the reveal button) |
| De-Swedish toasts | `rerollAvatar()` (was :974/:977) | `'Kunde inte generera avatar'` → **"Could not paint the avatar"** (both occurrences) |
| Retry copy | `#w-retry-msg` (was :267) + JS fallback (~:895) | "…contact the game creator for a top-up." → **"…write to web@rostad.cc."** (static + EN/SV JS strings, audit A1 §3.5) |
| Reduced motion | embers canvas (~:1010) + style block | JS gate: `const RM = matchMedia('(prefers-reduced-motion: reduce)').matches;` → `if(!RM)tick();` and resize listener only when !RM. Page CSS: `@media (prefers-reduced-motion: reduce){html{scroll-behavior:auto}}` — deliberately minimal; the global animation block lands in snes.css (S2) and is NOT duplicated here |

Note: `autoAvatar()`/`rerollAvatar()` still reference `pv-avatar-reroll` via `getElementById` — all uses are null-guarded (`if (rerollBtn)`), so removal is safe; lightbox paint button (`#pv-lb-paint`) state is now also reset in `rerollAvatar()`'s finally.

## 2. characters.html (The Forge)

| Change | Anchor | Detail |
|---|---|---|
| Vault cards keyboard-accessible | `renderVault()` template (was :415) | `.vcard` now `role="button" tabindex="0" aria-label="Open <name>"` + `onkeydown` Enter/Space → `openInspect(...)`. `.vcard:focus-visible` gold outline added. Inner `.vcard-dl` already stops propagation (unchanged) |
| Native confirm → Modal.confirm | `saveForged()` (was :361) | **Modal.confirm exists** (modal.js loaded at :213). Replaced `confirm(...)` with `await Modal.confirm({title:'Save a twin?', body:'"<name>" already rests in your Vault. Save this one anyway?', confirmText:'Save anyway', cancelText:'Cancel'})` per audit A1 §4.5. `saveForged` was already `async` |
| Roman numeral dropped | section label (was :190) | "III. The Vault" → **"The Vault"** (I./II. kept — forge→result is a real sequence) |
| Lang labels | `#forge-lang` (was :148–149) | "English sheet"/"Svenskt ark" → **"English"/"Svenska"** |
| Textarea aria-labels | `#forge-prompt` (:133), `#insp-prompt-input` (was :481) | Added `aria-label`; inspect textarea also switched from Cinzel .72rem to `var(--font-body,'Spectral',serif)` .85rem (audit A1 §4.7) |
| Lightbox | new `#vault-lightbox` + CSS + JS | Shared §4.3 pattern (Esc + backdrop close, gold frame, lazy img, title). Wired to: `.vcard-avatar` (stopPropagation → `openVaultLightbox(id,name)`, keyboard too), `#insp-avatar` in inspect modal (when painted), `#pv-icon` forge preview (`openPvLightbox()` — shows sigil large when unpainted). No paint action (per spec), no arrows (gallery not trivially available). `:focus-visible` outlines on all three targets |
| Reduced motion | style block + embers JS | Page CSS `html{scroll-behavior:auto}` under reduce; embers canvas gated with the same `RM` const as newgame (audit A1 §4.1 explicitly covers characters.html) |

## 3. character.html

**Choice: minimal relabel + cleanup (NOT the ARCHIVE dropdown conversion).** Rationale: the dropdown conversion requires porting the rite-rail markup+CSS+toggle JS from siblings while keeping embed.js hiding and the existing mobile rules (`body > header .top-btn` at :404) intact — medium risk for a codex-iframe page; the spec explicitly allows minimal. 

| Change | Anchor (was :590–599) | Detail |
|---|---|---|
| Icon fix | NPCs link | "📖 NPCs" → **"👥 NPCs"** (icon table §1.5/§1.6) |
| Leave semantics | logout button | Calls `doLogout()` → relabeled **"🔒 Log out"**, keeps `.top-btn.danger` (red via snes.css + new page rule) |
| Inline styles stripped | whole `<header>` | ~1,400 chars of duplicated inline `style=` removed; extracted into page CSS after the snes.css link: `.topbar` layout, `.topbar-brand`, `.topbar-sub`, `.top-btn` base + `.danger` colors, `.topbar-sub` hidden ≤900px |
| embed.js compat | `<header class="topbar">` | **class="topbar" kept** — `embed.js` `header.topbar` selector still matches |

## 4. Leave/Log-out semantics (§1.4) + ✦ Facts links

| File | Line (post-edit) | Before → After | Target integrity |
|---|---|---|---|
| npcs.html | :152–153 | "🚪 Leave" → **"🔒 Log out"**; added **"✦ Facts"** above it | `onclick="doLogout();return false"` unchanged ✔ |
| platser.html | :274–275 | same | same ✔ |
| loggbok.html | :91–92 | same | same ✔ |
| facts.html | :290–291 | same; Facts link gets `class="cur"` | same ✔ |
| help.html | :148 | "🚪 Leave" → **"🚪 Leave the table"** (goes to adventure.html, session kept — correct per §1.4) | `href="adventure.html"` unchanged ✔ |
| admin.html | :721 | "🚪 Leave" → **"🚪 Leave the table"** | `href="adventure.html"` unchanged ✔ |
| character.html | :610 | see §3 | `onclick="doLogout()"` unchanged ✔ |

All five THE ARCHIVE dropdowns (npcs/platser/loggbok/facts/help) now carry **✦ Facts** → facts.html is reachable from every sibling (§1.5).

## 5. help.html

| Change | Anchor | Detail |
|---|---|---|
| Menu order | archive drop (was :138–148) | Now: To the Table · NPCs · The Map · Logbook · Character · **✦ Facts** · **⚙️ Mechanics** · **✒ Release Notes** · **🚪 Leave the table** (Mechanics/Releases above leave; leave last) |
| Releases icon | same | 📜 → **✒** (§1.5: 📜 stays Logbook) |
| "How to Play?" | — | **0 occurrences in my files** (only chat.html :1373/:1340/:8394 — S2's scope); help.html `<h1>` already reads "How to Play" |
| Mobile type hierarchy | :75/:77, :86 | `@media ≤640px`: h1 `.85rem` → **1.1rem** (line-height 1.6→1.4); `@media ≤400px`: h1 `.75rem` → **.95rem**. h1 now ≥ body (.87rem) at all breakpoints |
| Avatar copy | :319 | → **"Click any portrait to see it full-size — paint a new one from there."** (matches lightbox-first model §4.2) |
| Silkscreen body decl | :21 | `font-family:var(--font-accent,'Silkscreen',monospace)` **deleted** from body (snes.css overrides to Spectral anyway) |

## 6. reset.html

:132 — `btn.textContent = 'Re-forging&hellip;'` → `'Re-forging…'` (real ellipsis char via textContent).

## 7. pricing.html

- :258 — tier-fine → **"Premium models run as long as they can be financed — a donation keeps the cauldron burning."**
- Added `@media (prefers-reduced-motion: reduce){html{scroll-behavior:auto}}` (page has `scroll-behavior:smooth` at :32; animations covered by the incoming global snes.css block).
- Bonus (§1.7, in-scope): nav unified — was "Return to the realm / Enter", now **Paths · The Minds · Ledger · Guide · Enter** with plain-English `title=` attrs + `.nav-link.active` rule added.

## 8. screenshots.html (P1)

- **Created `frontend/assets/screens/`** and copied all 5 jpgs (hero-login, at-the-table, dice-and-narration, book-of-souls, mobile-table) — verified byte-identical names.
- Gallery: six "Screenshot coming soon" slots → **five real `<img loading="lazy">` slots** with descriptive alt text + matching captions: **The Gate** (hero-login) · **At the Table** (at-the-table) · **Honest Dice** (dice-and-narration) · **Book of Souls** (book-of-souls, new caption copy) · **Mobile Play** (mobile-table, new caption copy). Sixth slot removed entirely. **Zero "coming soon" strings remain** (verified by grep).
- Added reduced-motion `scroll-behavior:auto` block.
- Bonus (§1.7, in-scope): nav unified to the shared set (Paths · The Minds · Ledger · Guide · Enter) with titles — audit flagged this page's divergent link set.

## 9. book-souls/index.html

| Change | Anchor | Detail |
|---|---|---|
| Counter fix | `updateCnt()` (was :394–398) | `B.total ? 'Tale N of M' : 'No souls summoned yet'` — same branch covers fetch-failure (total stays 0). Static HTML counters (:240/:260) also changed from "Tale 1 of 0"/"Encounter 1 of 0" → "No souls summoned yet" so the pre-fetch paint is honest; fetch-failure hint copy (:529) unchanged — the counter branch handles it |
| Header nav | new `.bos-nav` after grain/vignette | Brand + **"← Back to the Gate"** → `../login.html` (page lives in `/book-souls/`) + CSS |
| Click-to-enlarge `.art` | `endDrag()` click branch + new lightbox | Click on `.art`/`.scrim` (not `.body`) → `openArtLightbox(pg)`: extracts `background-image` url, lazily builds `<img>` in gold frame, title = soul name. Esc + backdrop + ✕ close. Clicks elsewhere still turn the page; drag unaffected. No paint action per spec |
| Reduced motion | style block | `.pg{transition:none}` (flip → instant), curlsweep animation off, `.face` opacity switch off, h2 flicker off, `.rv` reveals static |

## 10. mechanics.html

- **Footer link** (:1096 area): added **"← Back to the Guide"** → help.html (gold-bordered link above the compile note). Page no longer a dead end (§5 mechanics).
- **Boot-overlay skip persisted** (§5 mechanics): `bootDone()` now sets `sessionStorage.mech_boot_seen`; at boot (~:1157) `if(sessionStorage.getItem('mech_boot_seen')) bootSkip(); else bootStep2();` — wrapped in try/catch (private-mode safe). First visit keeps the ceremony; repeat visits in the same session skip it.

## 11. releases.html + models.html (§1.7)

- **Both navs now identical:** Paths (pricing.html) · The Minds (models.html) · Ledger (releases.html) · Guide (help.html) · Enter (login.html#gate), each fantasy name with a plain-English `title=`. models.html: dropped "The Crossroads" (adventure.html), added Ledger+Guide, `active` kept on The Minds. releases.html: added The Minds/Ledger/Guide, `active` on Ledger; added `.nav-link.active{color:var(--gold)}` rule (releases lacked it).
- **releases.html version chip-row:** new `.ver-chiprow` under the current-box: v1.3 · v1.2 · v1.1 · v1.0 · v0.10 · v0.9 · v0.8 → anchors `#s13 #s12 #s11 #s10 #s010 #s09 #s08`. Sections 1.1/1.0/0.10/0.9/0.8 previously had **no ids** — added `id=` to each `<div class="sec rv">` (verified: every chip anchor resolves to an existing id). `.rv` reveal class on the row so it fades in with siblings; IO fallback (2.5s) guarantees visibility.

---

## i18n.js dict updates NEEDED (flagged, NOT applied — i18n.js is out of S3 scope)

1. `i18n.js:611` — `'Steg ett av tre': 'Step one of three'` — **obsolete**: newgame.html's static string is now "A New Adventure" (EN). If the walker ever needs the SV mirror, a new entry `'A New Adventure': …` (SV: "Ett nytt äventyr") would be required for SV rendering; the old entry can be removed at next dict sweep.
2. `i18n.js:131` + `:880` — `'🌐 Välj kampanjspråk först!'` / `'Välj kampanjspråk först!'` — still referenced by newgame.html's now-unreachable dead-safety guard; harmless, keep or drop with the guard.
3. The new English strings introduced (Log out / Leave the table / ✦ Facts / No souls summoned yet / Could not paint the avatar / retry copy / avatar-copy line / chip labels) are **EN-native UI copy** — the walker translates SV→EN, so no dict entries are needed for EN campaigns. If a future SV mirror is wanted, these need SV entries.
4. No edited string in my files was found in the SV→EN dict except the three above (grepped: `Svenskt ark`, `Click any avatar`, `coming soon`, `Leave`, `Re-forging`, `consider a donation` — none present).

## Verification evidence (all re-run after final edits)

- **node --check**: every inline `<script>` block of all 16 edited files extracted via `re.findall(r'<script>(.*?)</script>', src, re.S)` → all pass (0 failures).
- **CSS brace balance**: every `<style>` block, `count('{')-count('}') == 0` → all pass.
- **html.parser sanity pass**: all 16 files feed without error; `<div>` open/close counts balanced per file.
- **onclick target integrity**: grep-verified — npcs/platser/loggbok/facts still `onclick="doLogout();return false"` behind "🔒 Log out"; help.html still `href="adventure.html"` behind "🚪 Leave the table"; admin.html still `href="adventure.html"`; character.html still `onclick="doLogout()"`.
- **assets**: `frontend/assets/screens/` contains exactly the 5 copied jpgs; screenshots.html references exactly those 5 filenames (set-equality verified); no "coming soon" text remains.
- **releases chip anchors**: all 7 `#s…` anchors resolve to existing section ids (verified programmatically).
- **embed.js compat**: `class="topbar"` kept on character.html header; npcs/platser/loggbok/facts headers untouched (`class="topbar rite-rail"`).
- **?v= strings**: `git diff | grep '?v='` over all 16 files → empty (none changed).
- **git**: no add/commit performed; only the 16 listed files + assets/screens/ modified in frontend (login.html/adventure.html dirty state belongs to parallel agent S1).

## Notes / judgment calls

- **character.html**: kept minimal relabel+cleanup instead of ARCHIVE dropdown conversion (spec-sanctioned; reason in §3 above).
- **newgame reveal**: removing #pv-avatar-reroll left `rerollAvatar()` only reachable through the new lightbox's paint button — deliberate, matches "paint one click deeper" (§4.2).
- **book-souls keyboard arrows** still drive only the adventurers book (audit P2 note) — out of this task's explicit list; left as-is.
- **screenshots.html + pricing.html navs** were unified to the §1.7 set as well (both in my file list; audit flags both as divergent navs — this completes the "one link set everywhere" intent for my pages).
