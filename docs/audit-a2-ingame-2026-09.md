# Audit A2 — In-game + Content Pages UX/UI (2026-09-17)

READ-ONLY audit. No frontend files were modified. All line numbers verified against the files on disk 2026-09-17 (chat.html 9135 lines, snes.css v46).

Scope: `chat.html`, `character.html`, `npcs.html`, `platser.html`, `loggbok.html`, `facts.html`, `help.html`, `mechanics.html`, `releases.html`, `pricing.html`, `models.html`, `reset.html`, `screenshots.html`, `admin.html` (light pass), `book-souls/index.html`. adventure.html gear-menu (:528–537) was audited separately and is skipped except where the turns-tooltip and lightbox briefs touch it.

Identity kept throughout: dark-fantasy Castlevania×DOS×terminal, gold+bone+arcane on ink, Cinzel/Spectral/IBM Plex Mono/Silkscreen, UI in English.

Severity: **P0** = factually wrong / broken output visible to players now. **P1** = core UX defect, fix this cycle. **P2** = polish / consistency.

---

## 1. Menu structure

### 1.1 chat.html ⚙️ settings-menu — flat jumble (P1)

**Where:** `chat.html:1371–1393` (`.settings-menu#settings-menu`), CSS `chat.html:77–86`, item CSS `:173–178`, toggle `toggleSettingsMenu()` `:7732–7743`.

Current order: Usage / How to Play? / ── / Chat UI: CLI / Feedback / **Models card (3 selects + 2 hints)** / About the Models / ── / Export / ── / Leave. Eight unrelated concerns at one level; the only structure is three arbitrary `.drop-sep` rules. "Usage" (account data) sits above "How to Play" (help); the Models card (a dense form) is wedged between Feedback and About the Models; Export (account data) sits alone between separators.

**Proposed grouped structure** (section labels + separators). New tiny label class, matching the DOS/terminal register (Silkscreen micro-caps, gold-dim):

```css
/* add after .drop-sep rule (chat.html:178) */
.drop-head{
  font-family: var(--font-accent); font-size: .55rem; letter-spacing: .22em;
  text-transform: uppercase; color: var(--gold); opacity: .75;
  padding: .5rem .7rem .2rem; user-select: none;
}
.drop-head:first-child{ padding-top: .25rem; }
```

```html
<div class="settings-menu" id="settings-menu">
  <div class="drop-head">Your game</div>
  <a class="drop-item" href="help.html">❓ How to Play — commands & tips</a>
  <button class="drop-item" onclick="openFeedbackModal();closeSettingsMenu()">💬 Feedback — suggestions or bug reports</button>
  <div class="drop-sep"></div>
  <div class="drop-head">Settings</div>
  <div class="model-picker-card"> …unchanged (chat.html:1377–1387)… </div>
  <button class="drop-item" data-cli-label onclick="toggleCliChat();closeSettingsMenu()">🖥️ Chat style …</button>
  <button class="drop-item" onclick="openModelInfo();closeSettingsMenu()">ℹ️ About the Models — what each DM does</button>
  <div class="drop-sep"></div>
  <div class="drop-head">Account</div>
  <button class="drop-item" onclick="openUsageModal();closeSettingsMenu()">📊 Usage — model & token stats</button>
  <button class="drop-item" onclick="exportCampaign();closeSettingsMenu()">📦 Export campaign — download as .zip</button>
  <div class="drop-sep"></div>
  <div class="drop-head">Leave</div>
  <button class="drop-item" style="color:var(--blood-bright)" onclick="location.href='adventure.html'">🚪 Leave — return to adventure select</button>
</div>
```

Keep the existing `.di-name`/`.di-hint` markup inside each item (shown abbreviated above); only the order, labels and heads change. Copy fixes inside the menu:

- **"How to Play?" → "How to Play"** (`chat.html:1373`, also `:1340`, `:8394`). A menu entry is a destination, not a question.
- **"Export" → "Export campaign"**, hint "download as .zip" (`chat.html:1390`). Names the object of the action.
- **Chat UI toggle** (`chat.html:1375`, label swapped by `:7950–7953`): the label names the *current* state ("Chat UI: CLI") and the hint re-describes that state ("terminal style — toggle to bubbles"). Per active-voice copy rules, hint should name the result: keep `di-name` = "Chat style: Terminal"/"Chat style: Bubbles", change `di-hint` to **"click to switch to bubbles"** / **"click to switch to terminal"** (update the swap code at `:7950–7956` to set both).
- The `.settings-menu` has no `max-height/overflow-y` (`chat.html:77–86`) — after grouping it grows ~2 label rows taller. Add `max-height: calc(100dvh - 70px); overflow-y: auto;` to `.settings-menu`.

### 1.2 chat.html ☰ mobile menu — mirror the same groups (P1)

**Where:** `chat.html:1334–1345` (`#mobile-menu`), CSS `:86–96`. Current: turns strip / Codex / Admin / ── / Usage / How to Play? / Chat UI / Feedback / ── / Leave. No Export, no Models — those live in a *third* menu (bottom-nav "Tools" sheet, `chat.html:8388–8397`: only How to Play + Export). "How to Play?" is duplicated in ☰ (`:1340`) and the Tools sheet (`:8394`).

Proposed — one grouping vocabulary as §1.1:

```
(turns strip #mobile-menu-turns stays on top — chat.html:1335)
NAVIGATE      📖 Codex — lore · map · character
YOUR GAME     ❓ How to Play   💬 Feedback
SETTINGS      🖥️ Chat style
ACCOUNT       📊 Usage   📦 Export campaign   👑 Admin (admin only)
LEAVE         🚪 Leave (red)
```

Then the bottom-nav **Tools sheet becomes redundant** — either delete it and point the ⚙️ tab at `toggleMobileMenu()` (`chat.html:8380`), or keep it as the sole home of Settings+Account items and strip those from ☰. Recommendation: **merge into ☰** (one mobile menu, fewer places to learn); bottom nav keeps Party | Codex | Tools→opens ☰-sheet with the same grouped content. If kept, remove the duplicate "How to Play?" from the sheet.

### 1.3 chat.html sidebar drawer-extras — every button styled destructive (P1)

**Where:** HTML `chat.html:1566–1571`; CSS `snes.css:523–536`: `.drawer-extras .drawer-logout{ border:1px solid var(--blood); color:var(--blood-bright) }`.

All four buttons (Character / Engine Room / Admin / Leave) carry class `drawer-logout` → **all render blood-red**, i.e. "Character" and "Engine Room" look like destructive logouts. Fix: introduce `.drawer-btn` (neutral: `border:1px solid var(--edge); color:var(--bone)`), keep `.drawer-logout` red **only** for Leave, insert a `.drop-sep`-style separator before Leave, mirroring the group system:

```html
<div class="drawer-extras">
  <button class="drawer-btn" onclick="openCodex('character')">🧙 Character</button>
  <button class="drawer-btn" onclick="toggleConsole()">🛠️ Engine Room</button>
  <button class="drawer-btn" id="admin-drawer-btn" style="display:none" onclick="location.href='admin.html'">👑 Admin</button>
  <div class="drawer-sep"></div>
  <button class="drawer-logout" onclick="location.href='adventure.html'">🚪 Leave</button>
</div>
```

### 1.4 "Leave" means two different things across the app (P1)

Verified semantics:

| Location | Label | Actual action |
|---|---|---|
| chat settings-menu `chat.html:1392`, ☰ `:1344`, drawer `:1570` | Leave | → adventure.html (session kept) |
| help.html archive `help.html:145` | 🚪 Leave | → adventure.html (session kept) |
| THE ARCHIVE on npcs/platser/loggbok/facts (`npcs.html:152`, `platser.html:274`, `loggbok.html:91`, `facts.html:290`) | 🚪 Leave | `doLogout()` → login.html (**logs out**) |
| character.html topbar `character.html:598` | 🚪 Leave | `doLogout()` (**logs out**) |
| adventure gear-menu `adventure.html:535` | Log Out | `leaveGate()` (logs out) |

Same icon+word, one keeps the session, one destroys it. Adopt two fixed items app-wide:
- **🚪 Leave the table** → adventure.html (never logs out).
- **🔒 Log out** → `doLogout()`/login.html, red, always last.

Apply: codex-page archive dropdowns + character.html topbar rename "Leave"→"Log out" (they call `doLogout`); chat menus keep "Leave" with hint "return to adventure select".

### 1.5 Icon collisions & gaps (P2)

- **📖 is both Codex and NPCs.** chat rail Codex = 📖 (`chat.html:1360`), mobile Codex = 📖 (`:1336`), Codex spine journal tab = 📜 JRNL, but character.html topbar "📖 NPCs" (`character.html:597`) while the archive dropdowns use "👥 NPCs" (`npcs.html:148` etc.). Fix: **📖 = Codex only; 👥 = NPCs everywhere** (change `character.html:597`).
- **📜 is both Logbook and Releases** (`loggbok` archives use 📜 Logbook; `help.html:147` "📜 Releases"; adventure gear `adventure.html:529` "📜 Release Notes"). Keep 📜 = Logbook/Journal; Releases → **✒** (or 📰 if the fantasy register allows — recommend ✒ Release Notes).
- **Facts page is in no menu.** `facts.html` is reachable only through the in-chat Codex spine (`chat.html:1679`). THE ARCHIVE dropdowns (npcs/platser/loggbok/facts/help) never link to it — a standalone visitor on facts.html cannot navigate to Facts siblings consistently. Add `✦ Facts` to all archive dropdowns.

### 1.6 App-wide icon/label/group system (proposal)

One table, used by every menu (settings, ☰, Tools sheet, drawer, THE ARCHIVE, topbars, adventure gear):

| Icon | Label | Target | Group |
|---|---|---|---|
| ⚔ | To the Table | chat.html | Navigate |
| 📖 | Codex | openCodex() | Navigate |
| 🧙 | Character | character.html / Codex char | Navigate |
| 👥 | NPCs | npcs.html | Navigate |
| 🗺️ | The Map | platser.html | Navigate |
| 📜 | Logbook | loggbok.html | Navigate |
| ✦ | Facts | facts.html | Navigate |
| ❓ | How to Play | help.html | Your game |
| 💬 | Feedback | feedback modal | Your game |
| ⚙️ | Mechanics | mechanics.html | Your game (content pages only) |
| ✒ | Release Notes | releases.html | Your game (content pages only) |
| 🧠 | Models (card) | — | Settings |
| 🖥️ | Chat style | toggleCliChat | Settings |
| ℹ️ | About the Models | model-info modal | Settings |
| 🎵 | Sound | sfxToggleBtn | Settings |
| 🛠️ | Engine Room | toggleConsole | Settings (admin/dev) |
| 📊 | Usage | usage modal | Account |
| 📦 | Export campaign | exportCampaign | Account |
| 🪞 | Profile | profile modal | Account |
| 💳 | Upgrade | pricing.html | Account |
| 👑 | Admin | admin.html | Account (admin only) |
| 🚪 | Leave the table | adventure.html | Leave (red, last) |
| 🔒 | Log out | doLogout → login.html | Leave (red, last) |

Group order is always: **Navigate → Your game → Settings → Account → Leave (red, last)**, with `.drop-head` labels + `.drop-sep` between groups.

### 1.7 Content-page navs are four different systems (P2)

- **THE ARCHIVE dropdown** (rite-rail): npcs `:147–153`, platser `:269–275`, loggbok `:84–91`, facts `:283–290` — identical 6 items (good), but help.html's copy (`help.html:138–148`) adds Mechanics + Releases **after** Leave and points Leave at adventure.html instead of logout. Reorder help.html: Leave→"Leave the table" placed before nothing — put Mechanics/Releases above it; adopt §1.6 order.
- **Marketing nav** (`.nav`): pricing `:203–212` ("Return to the realm" + Enter), models `:166–177` (Paths / The Minds / The Crossroads / Enter), releases `:188–198` (Paths / The Crossroads / Enter — **no models link**), screenshots `:106–117` ("How to Play & Underlying Mechanics" / Pricing / Enter — different words again). Pick one link set — recommend: **Paths (pricing) · The Minds (models) · Ledger (releases) · Guide (help) · [Enter]** — and use it verbatim on all four (+ the cryptic names get a `title` in plain English).
- **mechanics.html has no nav at all** — hero → index (`mechanics.html:377`) → footer (`:1095–1099`) with zero links off-page. Dead end; add the shared marketing nav or at minimum a "← Back to the Guide" link in the footer.
- **book-souls/index.html has no nav** (zero `href` links to any page; body starts `book-souls/index.html:224`). Dead end for anyone who lands on it directly. Add a minimal one-line header: brand + "← Back to the Gate" (login.html).
- **character.html topbar** (`character.html:590–599`): 5 buttons, every one carrying ~200 chars of duplicated inline `style=` — the `.top-btn` class already exists in page CSS. Also: no Facts link, no "current page" marker, "Leave" logs out (see §1.4). Convert to THE ARCHIVE dropdown markup used by the other codex pages (they're siblings; embed.js hides all `header.topbar` when embedded — character.html's header is `class="topbar"` so this already works in both contexts).
- **admin.html** masthead (`admin.html:715–724`): Expand all / Collapse all / Leave / To the Table — fine for an internal tool; just rename Leave→"Leave the table" per §1.4 (it links to adventure.html, no logout).

---

## 2. Turns tooltip

### 2.1 The two wrong tooltips in chat.html (P0 — factually wrong billing copy)

1. **Static attribute** `chat.html:1353`:
   `title="Turns quota — one chat message costs 1 turn; TTS, image-gen and background calls count too (the DM's internal calls are free)"` — self-contradictory ("background calls count too" *and* "internal calls are free") and wrong: Guardian/extraction/background calls are free internal; the truthful copy already exists in `help.html:250` and `releases.html:432`.
2. **Rebuilt every second** by `renderTurnTally()` `chat.html:2117–2123`: `tallyEl.title = 'Tier: … · X/Y turns left · resets … — one chat message costs 1 turn; TTS, image-gen and background calls count too (the DM's internal calls are free)'` — same wrong sentence, plus a per-tick DOM write on a 1s loop (`updateHeaderInfo` `:2125–2133`).

**Fix (decision already made — short):**
- Replace `chat.html:1353` title with: **`title="Turns left · current turn · day number"`**
- **Delete** the title-rebuild block `chat.html:2117–2123` (`const tallyEl …` through the closing `}`) — the static short title suffices; also removes the 1 Hz attribute write. (Detail lives one click away in the ⚗ profile modal, which already shows tier/quota/reset correctly, `chat.html:2645–2660`.)

### 2.2 Every other turns-quota tooltip found (full inventory)

| Location | Current copy | Verdict / fix |
|---|---|---|
| `adventure.html:519` `#quota-tip` (styled hover tip on `#quota-pill`, CSS `:574–579`) | "Each DM, TTS, Image-gen and background llm-calls counts towards the turns quota" | **P0 wrong** (background calls are free). Replace with: **"Your turn quota — and when it refills. Click for your profile."** |
| `chat.html:1347` `.rr-sigil` | `title="Profile — stats, tier, turns"` | OK (profile, not quota math). |
| `chat.html:1335` `#mobile-menu-turns` | text only via `turnInfoText()` (`:2014–2043`), no tooltip | OK. |
| chat profile modal (`openChatProfileModal` `:2608`, `renderChatProfile` `:2645+`) | "Turns X / cap per day" cells, no titles | OK — correct copy ("per 6h"/"per day" at `:2660–2663`). |
| adventure profile modal (`openProfileModal` `:2556`, `renderProfile` `:2714+`) | cells only, no quota tooltip | OK. |
| `chat.html:5725` `/undo` help row, `:5785–5786` undo button `title="Undo last turn (costs 1 turn)"`, `:5815` confirm text | "costs 1 turn" | OK — factual, keep. |
| `adventure.html:523` `#quota-benefits` | `title="Support/Patron benefits expire in"` | OK. |
| `help.html:250`, `pricing.html:236–237,253,288–292`, `releases.html:432–433` | long-form turn-cost copy | **Correct** — use `help.html:250` as the canonical sentence if any tooltip ever needs the long version. |

No other `title=`/tooltip containing quota math exists in login.html, newgame.html, characters.html (searched `turn|quota` × `title|tip`).

---

## 3. Sidebar avatar (.pc-wrap) — two layers of the same face

### 3.1 Current state (verified)

- CSS: `.pc-wrap`/`.pc-avatar-bg` block `chat.html:203` (minified one-liner): bg = absolute inset-0, `background-size:cover`, opacity 0 → `.62` under `.has-bg`, plus a 3-stop ink gradient `::after`. `.pc-avatar` `chat.html:204–206`: 44px circle — **overridden by `snes.css:297` to `54px !important`, radius 8px**.
- HTML: `chat.html:1506–1520` — `#pc-avatar-bg` (`:1507`) inside `.pc-wrap`, then `.pc-card` (`:1508`, click → `openCodex('character')`) containing `#pc-avatar` (`:1509`, click → `event.stopPropagation(); pickAvatar('player')`, `title="Click to change image"`).
- Render: `refreshAvatars()` `chat.html:2970–2987` — paints the **same portrait twice**: `#pc-avatar` with `_avW(AVATARS['player'],128)` (`:2972–2974`) and `#pc-avatar-bg` with `_avW(...,256)` (`:2980–2982`).
- Sidebar width: **250px** (`chat.html:179`), padding `1rem .9rem` → ~221px content; `.pc-card` gap .6rem + padding .6rem → text column ~145px. Mobile drawer: `min(85vw, 340px)` (`snes.css:486–487`).
- Context: `releases.html:240` documents a deliberate fix ("The party portrait blends again … the image now sits behind the name, class and health bars") — the bg layer is *intended* identity; the leftover 54px thumbnail is what makes it read as "a miniature on top of a rendered image".
- Same double-layer pattern repeats for sidebar NPC rows: `.npc-row.has-av` renders `.npc-bg` (128px) **and** `.npc-av-thumb` (48px) of the same face (`chat.html:270–277`, render `renderNpcSidebar()` `:7570–7584`).

### 3.2 Option evaluation

- **(a) Drop bg, enlarge thumbnail (~96px):** loses the painted-atmosphere look the Sep release explicitly restored; at 221px width a 96px thumb leaves a cramped text column; NPC rows would need the same treatment. Rejected.
- **(b) Drop thumbnail, keep bg + overlay name/HP:** one layer, zero width impact (bg is already inset-0), keeps the release-note intent, matches the NPC "hall" aesthetic. The 54px thumb's only jobs are (i) identity — redundant with bg, (ii) `pickAvatar` click target — replaceable by a hover badge (pattern already exists: npcs.html `.d-portrait::after` 🎨 badge `npcs.html:45–46`, adventure `.pf-paint-mini` `adventure.html:717`). **Recommended.**
- **(c) Portrait column left / stats right:** needs ≥320px; sidebar is 250px and the drawer 340px max — would force a sidebar redesign across two breakpoints. Rejected for this cycle.

### 3.3 Exact changes for (b)

HTML (`chat.html:1506–1520`):

```html
<div class="pc-wrap" id="pc-wrap">
  <div class="pc-avatar-bg" id="pc-avatar-bg"></div>
  <div class="pc-card active" onclick="openCodex('character')" title="Open character sheet in Codex">
    <button class="pc-badge pc-badge-zoom" onclick="event.stopPropagation();openPcLightbox()" title="Enlarge portrait" aria-label="Enlarge portrait">🔍</button>
    <button class="pc-badge pc-badge-paint" onclick="event.stopPropagation();pickAvatar('player')" title="Paint a new portrait" aria-label="Paint a new portrait">🎨</button>
    <div style="flex:1;min-width:0">
      <div class="pc-name" id="pc-name">—</div>
      <div class="pc-sub" id="pc-sub">—</div>
      <div class="pc-hp" id="pc-hp-bar"><i id="pc-hp-fill" style="width:0%"></i></div>
      <div class="pc-vitals" id="pc-vitals" aria-live="polite"></div>
    </div>
  </div>
  …pc-xp / pc-xp-label / pc-gold unchanged…
</div>
```

CSS (append in chat.html's body-level style block so it beats snes.css by file order; no `!important` needed if placed after the `snes.css` link — the page's `<style>` at `:1397` is body-level and already wins cascade ties):

```css
.pc-badge{ position:absolute; z-index:3; width:24px; height:24px; border-radius:50%;
  border:1px solid var(--gold); background:rgba(6,3,10,.85); color:var(--gold-bright);
  font-size:.7rem; display:flex; align-items:center; justify-content:center; cursor:pointer;
  opacity:0; transition:opacity .2s; padding:0; }
.pc-wrap:hover .pc-badge, .pc-badge:focus-visible{ opacity:1; }
@media (hover:none){ .pc-badge{ opacity:.85; } }        /* touch: always visible */
.pc-badge-zoom{ right:8px; bottom:8px; }
.pc-badge-paint{ right:36px; bottom:8px; }
```

JS:
- `refreshAvatars()` `chat.html:2970–2975`: delete the `#pc-avatar` block (element gone); keep the bg block `:2977–2987` unchanged.
- Delete `#pc-avatar` from `snes.css:297` (`.pc-wrap .pc-avatar` rule) and the `.pc-avatar .pxs` sprite rule reference (`snes.css:126`) once the element is gone — or leave them harmless (they simply stop matching). No other code touches `#pc-avatar` (searched: only `:1509`, `:2970`).
- New `openPcLightbox()` — 4 lines reusing the existing lightbox (§4.3): set img slot to `_avW(AVATARS['player'], 512)`, title to the character name, add `.show`. If no painted portrait exists, fall back to `pickAvatar('player')` (same graceful fallback as `openCpAvatarLightbox()` `chat.html:2950–2952`).
- Interactions preserved: card click → `openCodex('character')` ✔; paint → `pickAvatar('player')` via 🎨 badge ✔; enlarge added via 🔍 badge ✔.
- Apply the same single-layer treatment to sidebar NPC rows (`chat.html:7570–7584`): drop `.npc-av-thumb` when `.has-av` (keep `.npc-bg`), row click already opens the dossier.

---

## 4. Avatar enlarge — one shared lightbox everywhere

### 4.1 Inventory: what exists, what's missing

| Surface | Portrait render | Enlarge today? |
|---|---|---|
| chat.html avatar-modal preview (`:9094`) | `#avatar-modal-img` | ✅ `openAvatarLightbox()` `:2923` |
| chat.html profile modal (`:9068`) | `#cp-avatar` 200px | ✅ `openCpAvatarLightbox()` `:2950` |
| chat.html **sidebar** `#pc-avatar` (`:1509`) | 54px | ❌ click = pickAvatar → §3 badge |
| chat.html **message avatars** `.msg-avatar` (render `avatarHtml()` `:2355–2363`, NPC variant `:3397`; DM/player 240px, `:347`) | click = `pickAvatar(kind)` | ❌ |
| chat.html sidebar NPC rows (`:7579`) | thumb+bg | ❌ (row click → dossier) |
| character.html hero portrait `#portrait` (`:624`, click→`openAvatarModal` `:1159`) | — | ✅ inside modal (`:1875`→`:1844`); lightbox CSS `:437–441`, HTML `:1905–1910`, Esc `:1856` |
| npcs.html dossier `.d-portrait` (`npcs.html:466`, click→`openAvatarModal`) | — | ✅ inside modal (`:794`→`:754`); CSS `:72–76`, HTML `:824–828`, Esc `:766` |
| adventure.html profile thumb `#pf-thumb` (`:715`) | ✅ `openPfLightbox()` `:2590` **with gallery arrows** `:738–740` — the most complete impl | ⚠️ **Esc does NOT close it** (`adventure.html:2529–2539` handles only gear-menu + `#pf-overlay`) — **P1** |
| adventure.html **onboarding reveal portrait** `#adv-pv-portrait` (`:1010`, click→`openAdvPaintModal`) and preview modal `#adv-portrait-img` (`:747–761`) | ❌ true lightbox (preview modal is 340px max, no full-size view); Esc also doesn't close `#adv-portrait-overlay` | ❌ **P1** |
| book-souls `.art` faces (`book-souls/index.html:303`, `:334`) | ❌ nothing | ❌ P2 (public gallery — click-to-enlarge expected) |
| platser/loggbok/facts | no portraits | n/a |

Also: chat's `.av-lightbox` and character/npcs' copies close on Esc + backdrop + ✕ but have **no arrows**; adventure's pf-lightbox has arrows + counter but **no Esc**. Nothing is uniform.

### 4.2 Interaction model for click=portrait surfaces (decision needed — recommendation inside)

`.msg-avatar` click currently paints (`pickAvatar`) and `help.html:319` documents it ("Click any avatar … to change its image"). Recommendation — **lightbox-first, paint one click deeper**:

- Click any portrait (msg-avatar, sidebar badges, dossier, hero) → **lightbox**.
- Lightbox footer carries the actions: **🎨 "Paint a new portrait"** (calls `pickAvatar(kind)` / `openAvatarModal()`), plus **‹ n/N ›** gallery arrows where a gallery exists (data already available: `AVATAR_GAL[kind]`, `rotateAvatarImage()` `chat.html:2400`).
- Rationale: viewing is the frequent, low-stakes action; painting costs a turn and deserves a deliberate second click. Update `help.html:319` copy to: **"Click any portrait to see it full-size — paint a new one from there."**
- Rejected alternative: shift-click/double-click to enlarge — undiscoverable, no affordance on touch.

### 4.3 ONE shared lightbox pattern (copy-adapt per page)

Canonical spec (superset of chat's `.av-lightbox` `chat.html:151–157` + adventure's arrow bar `:736–743`), gold frame on ink:

```html
<div class="av-lightbox" id="avatar-lightbox" onclick="if(event.target===this)closeAvatarLightbox()" role="dialog" aria-modal="true" aria-label="Portrait preview">
  <div id="avatar-lightbox-img-slot"><!-- img created lazily --></div>
  <div class="av-lb-bar" id="avatar-lightbox-bar" hidden>
    <button class="av-lb-nav" onclick="lbRotate(-1)" aria-label="Previous portrait">‹</button>
    <span class="av-lb-count" id="avatar-lightbox-count"></span>
    <button class="av-lb-nav" onclick="lbRotate(1)" aria-label="Next portrait">›</button>
  </div>
  <button class="av-lb-act" id="avatar-lightbox-paint" hidden>🎨 Paint a new portrait</button>
  <button class="av-lb-close" onclick="closeAvatarLightbox()">✕</button>
  <div class="av-lb-title" id="avatar-lightbox-title"></div>
</div>
```

Behavior contract:
1. **Esc closes** (single `keydown` listener; already true in chat `:8865`, character `:1856`, npcs `:766` — **add to adventure.html `:2529` block**: `if (document.getElementById('pf-lb-overlay').classList.contains('show')) return closePfLightbox(); if (document.getElementById('adv-portrait-overlay').classList.contains('show')) return closeAdvPortraitPreview();`).
2. Backdrop click closes; ✕ always visible top-right.
3. Arrows + "3 of 5" counter **only when a gallery exists** (count>1); otherwise the bar stays `hidden`.
4. Gold frame: `border:2px solid var(--gold); box-shadow:0 0 60px rgba(var(--gold-rgb),.25)` (chat.html:154 — keep).
5. `img` created lazily (chat's Fix C `:2907–2922` — keep; prevents broken-image glyph).
6. Title bottom-center in Cinzel micro-caps (`.av-lb-title` chat.html:157).
7. Optional action button (🎨 Paint) wired per page.

Per-page work: chat.html — extend existing lightbox with bar+paint action, wire `.msg-avatar` and pc badges; character.html/npcs.html — add bar (both already have `rotateAvatarImage` + `avatar-gal-prev/next` in their modals, reuse the fns); adventure.html — add Esc (one-line), port bar into `#pf-lb-overlay` (already has arrows — just fix Esc + add to `#adv-portrait-overlay`); book-souls — paste the whole pattern (no paint action; arrows iterate the current book's faces, or omit arrows and just enlarge).

---

## 5. General frontend-design pass — content pages

### help.html
- **P1 — mobile type hierarchy inverts.** `help.html:75` sets `h1{font-size:.85rem}` while `p,li{font-size:.87rem}` (`:77`); at ≤400px h1 is `.75rem` (`:86`). The page title renders *smaller* than body text on phones. Fix: h1 ≥ 1.1rem at 640px, ≥ .95rem at 400px (snes.css only `!important`s heading *family/line-height*, not these page sizes).
- **P2 — Archive menu inconsistent** with siblings (Mechanics/Releases after Leave; Leave≠logout here) — see §1.7.
- **P2 — body font double-declaration:** page sets Silkscreen on `body` (`:21`), snes.css `:131` overrides everything to Spectral `!important`. Rendered result is fine; delete the misleading page declaration.
- **P2 — "How to Play?" title** with question mark in menus (`:1373` etc.) — rename per §1.1.
- Copy quality is otherwise strong: §"What costs a turn" (`:250`) is the canonical correct turn-cost sentence; sections have real structure (loop grid, ledger cells), `.rv` reveals respect reduced-motion (`:50`). One text-wall risk: "Two Minds at the Table" + Ledger + Guardian run ~90 lines of dense bullets (`:190–245`) — acceptable for a reference page; consider `<details>` collapsing per h2 if it grows.

### mechanics.html
- **P2 — dead end:** no nav, footer has no links (`:1095–1099`). Add "← Back to the Guide" (help.html) at minimum.
- **P2 — index numbering vs DOM ids diverge:** index shows §7→`#s10`, §8→`#s7`, §9→`#s8`, §10→`#s9` (`:386–389`; sections at `:838, :863, :928, :992`). Works, but any future anchor fix will trip on it; renumber ids to match display order when convenient.
- Good: full reduced-motion block (`:339–342` — the best in the app, copy this), boot overlay skippable via Esc/Enter/click (`:352`, `:1153`), sticky section index, honest "structure encodes information" (§ numbers are a real sequence).
- **P2 — boot overlay on every visit** is a second signature moment competing with the content; it's skippable, so acceptable, but persist "skip boot" after first dismissal (`sessionStorage`) — repeat readers of a docs page don't want ceremony.

### releases.html
- Good: named versions with narrative titles, FEAT/FIX/UX tag system encodes real categories (`:109–116`), reduced-motion block `:167`.
- **P2 — nav lacks The Minds** (models) while models.html nav has it (`releases.html:193–197` vs `models.html:171–176`) — unify per §1.7.
- **P2 — long page, no jump index:** 8+ version sections (`:217–608`), newest-first; add a compact version chip-row at top linking to anchors (mechanics.html's index pattern, horizontal).

### pricing.html
- **P2 — copy bug:** `pricing.html:258` "Premium models are served as they can be financed. **consider** a donation as well…" — lowercase sentence start; also weak CTA. Rewrite: "Premium models run as long as they can be financed — a donation keeps the cauldron burning."
- Buttons name actions well ("Begin your adventure", "Become a Patron", "Donate", "Continue to checkout" `:299`). Currency toggle is clear (`:221–226`).
- **P2 — reduced-motion missing** (page has `plan-in` animation `:137`); add the mechanics.html block.
- Fine print (`:288–292`) is a genuine text wall but it's contract copy — keep, it's correct and complete.

### models.html
- Good: spec grids give every claim a number; role blocks (DM/Lorekeeper/Extraction/Response time `:192–196`) answer the real user question ("why does thinking take time"). Reduced-motion present (`:147`).
- **P2 — nav "The Crossroads"** for adventure.html is opaque to a first-time visitor on a public page; the §1.7 unified nav should carry plain-English titles (`title="Return to adventure select"`).
- **P2 — no back/link to releases** (siblings in the same nav family).

### reset.html
- **P1 — literal entity bug:** `reset.html:132` `btn.textContent = 'Re-forging&hellip;'` → button visibly reads "Re-forging&hellip;" while submitting. Fix: `btn.textContent = 'Re-forging…'` (real ellipsis char).
- Otherwise a model small page: errors are directive not moody ("The new words do not match." `:129`, "That link is invalid or expired. Ask for a new one." `:139`), broken-token state has a named heading + fix instruction (`:117–122`), success copy stays in voice ("🕊️ Your word is re-forged." `:136`). Mobile pass exists (`:59–71`). No reduced-motion needed (no animations).

### screenshots.html
- **P1 — the page's whole job is unfulfilled:** all six gallery slots still say "Screenshot coming soon" (`:122–163`) — a gallery page with no gallery. Either fill the slots (the app is live; six captures: Gate, Table, Dice, Codex, Forge, Portraits) or unpublish the link from login.html (`login.html:470`, `:564`) until ready. Empty-state copy is fine ("The world waits…") but this is a *placeholder*, not an empty state.
- **P2 — no reduced-motion** (only `scroll-behavior:smooth` `:32`; add `@media(prefers-reduced-motion){html{scroll-behavior:auto}}`).
- Nav here uses yet another link set (§1.7).

### book-souls/index.html
- Strong single signature moment (the page-turn books with spine/fore-edge/curl-sweep `:60–103`) — restraint elsewhere is good.
- **P2 — counter shows "Tale 1 of 0" when the gallery is empty:** `updateCnt()` (`:394–398`) computes `left.length + 1` unconditionally; with `total=0` both books read "… 1 of 0". Fix: `B.total ? (…) : 'No souls summoned yet'`.
- **P2 — fetch failure copy** (`:529`): "Book of Souls awaiting its first summoned souls…" replaces the *hint* text — acceptable, but the counter still says "1 of 0"; handle both in the same branch.
- **P2 — dead end** (no nav, §1.7) and **no enlarge** on `.art` faces (§4.1).
- **P2 — keyboard arrows only drive the adventurers book** (`:517–520`); NPC book is pointer-only. Either scope arrows to the focused/hovered book or note it in the hint.
- **P2 — no reduced-motion**; the 1.1s page flip + curlsweep should degrade to instant under `prefers-reduced-motion`.

### chat.html (in-game general)
- **P1 — zero reduced-motion coverage:** 0 `prefers-reduced-motion` blocks in the page (47 `@keyframes`, incl. infinite loops: `vitals-pulse` `:239`, `type-blink` `:496`, `orb-pulse` `:451`, `hp-flash` `:596`) and snes.css has only one narrow rule (`snes.css:2807` ward-pulse). Add the mechanics.html-style global block to **snes.css** (covers every page that lacks its own — chat, character, npcs, loggbok, facts, pricing, screenshots, book-souls, reset, admin):
  ```css
  @media (prefers-reduced-motion: reduce){
    *,*::before,*::after{ animation-duration:.01ms !important; animation-iteration-count:1 !important; transition-duration:.01ms !important; }
    html{ scroll-behavior:auto; }
  }
  ```
  Plus gate the `#embers` canvas JS (chat.html:1327 etc.) on `matchMedia('(prefers-reduced-motion: reduce)')` — a permanently animating full-screen canvas is the biggest motion load.
  Caveat: the typewriter reveal is functional pacing for some users; the global block reduces it to instant text, which is the correct reduced-motion behavior.
- **P2 — Swedish strings in static HTML** rely on the i18n walker for EN campaigns: "✦ Nära dig" (`:1521`, dict `i18n.js:891`), "⚔ STRIDSLOGG" (`:1586`, dict `i18n.js:43`), `title="Minimera stridslogg"` (`:1589`, dict `:44`), facts "Laddar arkivet…" (`facts.html:342`, JS-patched `:462`), platser "Laddar…" ("`platser.html:303,315`", JS-patched `:910–912`). The walker translates text nodes + titles (`i18n.js:935`), so EN campaigns are covered — but any string missing from the dict leaks Swedish into an English UI. Sweep the dicts when touching these lines; since UI-in-English is the identity, consider flipping the static HTML to EN and letting the walker translate *to* SV.
- **P2 — quest empty state** (`:1530`) "No quests yet…" gives no direction. Per empty-state copy rules: "No quests yet — the DM will post one when the story hooks you."
- Good: the rite-rail is a genuinely distinctive signature (48px grid rail, gold hairline, sigil ⚗ profile); help-card in-chat (`:130–150`) has real structure; composer placeholder names actions ("What do you do? Write freely — fight, sneak, talk, cast a spell…" `:1654`); cap-reached modal is bilingual and directive (`:2175+`).

### admin.html (light pass)
- Internal tool; structure is sound (masthead actions `:715–724`, KPI band, collapse/expand all). Only notes: rename "Leave"→"Leave the table" (§1.4), and it inherits the global reduced-motion fix via snes.css. No further audit.

---

## 6. Prioritized fix list

**P0 — wrong facts about billing (do first, tiny diffs)**
1. `chat.html:1353` — replace static title with `"Turns left · current turn · day number"`.
2. `chat.html:2117–2123` — delete the per-tick `tallyEl.title` rebuild in `renderTurnTally()`.
3. `adventure.html:519` — replace `#quota-tip` text with `"Your turn quota — and when it refills. Click for your profile."`

**P1 — core UX**
4. Settings-menu regroup (§1.1): heads Your game / Settings / Account / Leave + separators; copy fixes ("How to Play", "Export campaign", chat-style hint names the result); add `max-height/overflow-y` to `.settings-menu`.
5. ☰ mobile menu mirrors the same groups; dedupe Tools sheet vs ☰ (§1.2).
6. `drawer-extras`: neutral `.drawer-btn` for Character/Engine Room/Admin; red `.drawer-logout` only for Leave (`chat.html:1566–1571`, `snes.css:523–536`).
7. Unify Leave vs Log out semantics + icons app-wide (§1.4, §1.6 table).
8. Sidebar avatar single-layer: drop `#pc-avatar`, keep bg, add 🔍/🎨 hover badges (§3.3); same for NPC rows.
9. Shared lightbox pattern everywhere (§4.3): msg-avatars lightbox-first with 🎨 action + gallery arrows; **adventure.html Esc closes pf-lightbox & portrait-preview** (one-line add at `:2529`); book-souls enlarge.
10. `reset.html:132` — `'Re-forging&hellip;'` → `'Re-forging…'` via textContent.
11. help.html mobile h1 smaller than body text (`:75,:86`) — restore hierarchy.
12. Global reduced-motion block in snes.css + `#embers` canvas gating (§5 chat).
13. screenshots.html — fill the six slots or unpublish the page.

**P2 — consistency & polish**
14. Icon system: 📖=Codex only, 👥=NPCs (`character.html:597`), ✒=Releases; add ✦ Facts to all archive dropdowns.
15. Unify marketing nav across pricing/models/releases/screenshots; add nav/footer link to mechanics.html and book-souls.
16. character.html topbar → THE ARCHIVE dropdown markup; strip duplicated inline styles.
17. help.html archive menu order (Mechanics/Releases above Leave).
18. pricing.html:258 lowercase "consider" + weak CTA rewrite.
19. book-souls "Tale 1 of 0" counter fix + NPC-book arrow keys.
20. releases.html anchor chip-row; mechanics.html id/§ renumber; persist boot-skip.
21. Empty-state copy with direction (chat quests `:1530`); Swedish-static-string sweep (§5 chat).
22. Update `help.html:319` avatar copy once lightbox-first lands ("Click any portrait to see it full-size — paint a new one from there.").
