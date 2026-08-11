# Design Consistency Audit — 'Mörkrets Rike' (Lore Weaver's Cauldron) frontend

Date: 2026-08-11 · Audit-only (no project files modified) · Scope: ~/dnd-llm/frontend (19 HTML + snes.css + 9 JS)
Method: targeted greps + narrow excerpts (chat.html 8.6k lines never read end-to-end). Counts are raw regex counts; treat as upper bounds.

---

## ⚠️ THE ONE HEADLINE FINDING: the app has TWO skins

`git grep` for the snes.css link shows the frontend is split in half:

| Skin A — Terminal Gothic (snes.css loaded, 11 pages) | Skin B — legacy "warm" skin (NO snes.css, 7 pages) |
|---|---|
| chat, adventure, admin, character, newgame, npcs, characters, platser, loggbok, facts, help | **login, mechanics, releases, pricing, models, screenshots, reset** |

Skin B pages keep everything snes.css was written to kill: rounded corners (login.html block#3: `border-radius:14px 0 0 14px` etc.; reset.html:31 `border-radius:14px`), gradients + hover-lift (login.html `.tablet:hover{transform:translateY(-5px);box-shadow:0 14px 44px…}`), visible `.corner` decorations (releases.html emits 120 corner elements), and no sprites.js / i18n.js / fonts.js at all (see per-file matrix below). They also define **different values for the same CSS vars** (see §1). Result: the app's own login/landing pages look like a different product than the game.

Per-file contract matrix:

| page | snes.css | themes.js | sprites.js | i18n.js | fonts.js | data-default-theme |
|---|---|---|---|---|---|---|
| chat/adventure/admin/character/newgame/npcs/characters/platser/loggbok/facts/help | ✅ | ✅ | ✅ | ✅ | ✅ | blood |
| login/releases/pricing/models/screenshots/reset | ❌ | ✅ | ❌ | ❌ | ❌ | blood |
| mechanics | ❌ | ❌ | ❌ | ❌ | ❌ | (none — fully self-contained inline CSS, own :root) |

---

## 1. COLOR — hardcoded hexes vs var contract

### 1a. Old warm palette (#0b0812 #161020 #d9c9a6 #8b5fd4) still present in 12/19 pages
chat.html, adventure.html, admin.html, character.html, newgame.html, npcs.html, characters.html, platser.html, loggbok.html, facts.html, help.html, index.html. In most terminal pages it is redeclared in sync with snes.css (so it renders identically) — a maintenance trap, not a visual bug. Where it is NOT in sync it is visible drift:
- adventure.html:11-14 `:root{--ink:#0b0812;--stone:#161020;--bone:#d9c9a6;--arcane:#9a6fe0…}` — the page's own :root re-declares the old warm palette. Largely dead (snes.css :root wins), but see 1c.
- index.html (1KB shell): `#0b0812` + `#d9c9a6` in a tiny inline script — the redirect page still carries the old palette.

### 1b. Hex counts per file (see table in v1 of this doc; summary)
chat.html 270 (147 in <style>), adventure 72 (71), mechanics 88 (61), login 68 (41), character 56 (56), newgame 51 (44), admin 31 (19), characters 29, npcs 24, models 24, pricing 22, releases 20, platser 19, loggbok 19, facts 25 (19), help 15, screenshots 15, reset 15, index 3.

### 1c. Inline hues that duplicate/contradict semantic vars (worst offenders)
- **chat.html**: `#a8b2c0` ×18 (≈--stone-2 slate, also default `--npc-color`), old-gold `rgba(232,198,90` ×64 + `rgba(201,162,39` ×75 vs `var(--gold)` ×182 — **~139 hardcoded old-gold values that never change when themes.js swaps the palette**, so theme switching only partially works on the main page. `#d43a4d` ×5 (old --blood-bright), `#8cc4cc` ×4 (teal), `#33cc33` ×4 (term-green), `#fff8dc` ×4 (bone), `#333` ×5. Example lines: 452-459 (npc-color), 565, 628, 972.
- **adventure.html**: full second palette inlined as CSS — `#1a1206` ×10, `#8a6d14` ×7, `#6e5510` ×7, `#100b18` ×5, `#0d0817` ×5, `#120c1c` ×4. `#1a1206`/`#8a6d14` survive snes.css because they're in non-var rules: e.g. `.tab-btn.active{color:#1a1206;background:linear-gradient(180deg,var(--gold-bright),var(--gold) 55%,#8a6d14)}` — the active tab renders in old warm gold under every theme.
- **newgame.html**: `#1a1206` ×4 — same warm-gold copied (not shared) from adventure.
- **mechanics.html** (own :root): `--ink:#08080d` + its own extra `--term-red:#ff5566` — a var that exists nowhere else in the app.
- **login.html** :root: `--ink:#07070c; --stone:#0e0e14; --bone:#b8b8c8; --gold:#c9a227` — a THIRD palette (blue-gray) for the same var names; legacy pages render visibly colder/darker than snes pages even where they use vars.

### 1d. rgbs with alpha hardcoded per file (inline styles)
Chat: 232,198,90 (old gold) ×64, 201,162,39 (old gold dark) ×75, 11,9,15 ×8, 90,120,220 ×2, 4,3,8 ×3. These should be `color-mix(in srgb, var(--gold) …)` like the 182 var-based usages already are.

---

## 2. FONTS — the 2026-08 sweep did NOT hold in chat.html

- **chat.html: 90 hardcoded font-family declarations** vs var(--font-*): `'Cinzel', serif` ×63 (should be `var(--font-display)`), `'Press Start 2P', monospace` ×7 (lines 136, 160…), `'VT323', 'IBM Plex Mono', monospace` ×6 (lines 843-857 — CLI log), `'Courier New', monospace` ×5 (108, 138, 142…), `'Spectral', serif` ×3, `'Silkscreen'` ×2, `var(--cli-mono, ui-monospace,…)` ×1. Only ONE rule (1166) uses the var: `.pc-name{font-family:var(--font-display,'Cinzel',serif) !important}` — the post-snes block switched one rule and left 89 behind.
- **Three different pixel fonts coexist**: `--font-accent` says 'Silkscreen' but chat.html hardcodes 'Press Start 2P' (7×) and 'VT323' (6×). Only Cinzel is <link>ed on most pages; snes.css @imports all four (snes.css:6). 'Press Start 2P' is only actually loaded on help.html. So the 13 chat.html pixel-font rules silently render as generic monospace.
- **Skin B font drift**: legacy pages (login/mechanics/releases/pricing/models/screenshots/reset) load only Cinzel; their `--font-body:'Spectral'` falls back to Georgia, `--font-accent:'Silkscreen'` → monospace. Same var, different rendered font per skin.
- **font-size < 1rem in chat body text**: snes.css:680 `.msg .text{font-size:1rem !important}` enforces the rule — good. BUT `.msg.dm .reasoning-body .inner p` (chat.html:449) is `0.9rem` — the "thinking/reasoning" body is chat text and sits below the 1rem rule. `.msg.system` chips at 0.88/0.82rem (505-509) are borderline; `.msg.dm .npc-quote .nq-who` labels at 0.62rem are labels (ok).
- chat.html also ships tiny micro-labels at 0.6-0.66rem in places (387, 473, 501, 126-126) — Cinzel letter-spaced caps; consistent in style but far below any readable floor.

---

## 3. SPACING / SIZING

- **Border style**: solid dominates everywhere (chat 141, adventure 77, login 64, admin 49, character 50); dashed is used inconsistently for "system" messages (chat.html:506 `.msg.system` 1px dashed vs 510 `.msg.system .err` 1px solid) and for `border-top:1px dashed` section dividers (chat 447, adventure 2, mechanics 2). No double anywhere. Dashed-vs-solid for the same "system note" concept within one file = minor drift.
- **Button sizing — .top-btn has 3 sizes + 2 selector strategies**:
  - chat.html:68-70 `.top-btn{font-size:0.8rem…}`; `.top-btn.icon-btn` = 38×34px (chat.html ~75); `.top-btn.compact{height:34px !important}` (chat.html:1557).
  - adventure.html:24-27 `.top-btn{font-size:.75rem;border-radius:8px;…}` + 44px min-height only at ≤640px (adventure.html:288).
  - npcs/platser/loggbok/facts: `.topbar .top-btn{min-height:44px!important;padding:.4rem .65rem!important}` — always ≥44px.
  - character.html: `body > header .top-btn{min-height:44px !important…}` — different selector for the same fix.
  Same component: 34px (chat), ~40px (adventure desktop), 44px (lore pages, always). The lore-page 44px !important patches post-date chat's 34px design — the app is mid-migration from small to 44px touch targets, and chat hasn't been migrated.
- **Panel/padding scales**: chat `.bubble` padding .5rem/.7rem (461) vs adventure quote cards and newgame cards use .85-1.2rem; login `.tablet{padding:1.5rem 1.2rem}` — three different card padding scales.
- **radius chaos** is covered in §7 (13 distinct !important radius values in chat alone).

---

## 4. COMPONENT DRIFT (same concept, different implementation)

1. **Topbar — 3 patterns**:
   - chat.html:1452 `<header class="topbar">` — brand-centered, hamburger + drop-item mobile menu, user-tag quota card (1526-1555). No labeled nav buttons.
   - adventure.html:459 `<div class="topbar">` — labeled buttons (`.top-btn` with emoji+text: 🪞 Profile, ⚙️ gear menu z-900), quota pill (463-468). `<div>`, not `<header>`.
   - facts.html:193 / npcs / platser / loggbok — `<header class="topbar">` with brand + page-tag + spacer + `.top-btn` LINKS (⚔ To the Table, 📖 NPCs, 🗺️ The Map, 📜 Logbook, 🧙 Character, 🚪 Leave). A link-bar. chat/adventure use buttons+JS; lore pages use anchors.
2. **Tabs — 4 systems**: character.html `.tabs/.tab` stone tablets (0.82rem, 44px min-height, grid 2×2 on mobile); adventure.html `.tab-btn` (0.72rem, active = gold gradient + `#1a1206` text); chat.html `.cx-tab` (originally a VERTICAL stack `flex-direction:column`, then re-overridden to a 2-row tab bar in 3 successive !important patches, 0.62rem); mechanics.html `<nav class="index rv">` list. Four geometries, four sizes, four active states.
3. **Drawer/modal overlay z-scales — 4 different ladders**: login drawer-backdrop 80 / drawer 85 / about-overlay 95 (login.html:415-484); adventure modals 110/120/130 (393, 526, 557); characters.html insp-overlay 500 + toast 600 (76, 85); chat cd-backdrop 9990 / cd-drawer 10000 (900-904), mi-overlay 10000, av-lightbox 11000, fb 12000/12001, cp-overlay 10000. See §5.
4. **Toast**: chat.html:832 `z-index:10000` bottom-right; characters.html:85 `z-index:600` bottom-center; mechanics.html:335 `z-index:9000` bottom-center; snes.css:271 re-skins `.toast` but never unifies position/z. Same toast, three positions, three z-values.
5. **"tablet" class collision**: login.html uses `.tablet` = feature card with sig-icon, gold corner brackets, hover-lift, expandable on mobile (login.html ~560-590); releases.html uses `.tablet` = changelog entry card (releases.html ~60-80: "stone tablet"). Same class name, two different components, two different stylesheets.
6. **Lore pages' left rail**: facts/npcs/loggbok/platser each hand-roll `.shelves` with different widths (facts 300px→240px, others differ) and different pre/post-snes split — platser.html has NO pre-snes block at all (100% post-snes "MJUKA UPP" block, platser.html:11-26) while npcs/facts are mostly pre-snes base + small post-snes patch. Same "archive shelves" concept, 4 different CSS architectures.

---

## 5. Z-INDEX CHAOS

Established ladder (snes.css): bottom-nav 280 < drawer-backdrop 290 < drawer 300 < sheet 310 < oracle/console 320 < scanlines body::before 999 < overlays 10000+; extras: theme-pop 30000 (snes.css:331), px-smoke 209 (1371), console-as-sheet 10000!important (674).

Per-page z-index vocabularies (distinct values):

| page | values |
|---|---|
| chat.html | 1,2,3,4,5,30,50,60,70,90,200,210,400,520,950,9990,9995,10000×5,11000×2,12000,12001 |
| adventure.html | 1,2,40,50,110,120,130,900,950 |
| login.html | 1-5,40,45,50,55,60,80,85,90,95 |
| admin.html | 1,2,50 |
| character.html | 1,2,5,40,50,10000,11000 |
| mechanics.html | 1,2,3,8000,9000,9999 |
| newgame.html | 1,2,500 |
| characters.html | 1,2,500,600 |
| npcs.html | 1,2,3,5,6,7,50,10000,11000 |
| platser.html | 1,2,3,5,50,60 |
| loggbok/facts | 1,2,5,50 |
| help.html | 999 (duplicate scanlines) |
| snes.css | 1,2,5,209,270,280,290,300,310,500,999,10000,30000 |

Conflicts:
- **Drawer z-scale triplicated**: ladder 290/300 vs login 80/85 vs chat 9990/10000. On login, if a 290+ drawer ever opens over it, it would cover login's drawer. In chat, `.cd-drawer` at 10000 ties with 4 other overlays (mi-overlay, toast, cp-overlay) — order is DOM-order, not intent.
- **chat.html:900-904**: backdrop 9990 sits just 10 below the 10000 overlay class — any new 10000 element (there are 5) renders above the codex backdrop without a backdrop.
- **adventure.html inversion**: gear-menu tooltip z-900 and quota-tip 950 are ABOVE the page's own modals (110-130). An open modal backdrop at 110 is under its own page's tooltips; the "New turn" overlay (mi-overlay 120) can be visually pierced by the quota tooltip (950).
- **adventure 110-130 < drawer 300**: any app-wide drawer/sheet would cover adventure's modals.
- **mechanics.html self-contained 8000/9000/9999** and **characters 500/600** belong to no ladder.
- **help.html:24** re-declares `body::before z-index:999` scanlines that snes.css:92-93 already provides — the inline copy is dead (snes.css wins) but duplicates the concept.

---

## 6. DEAD CSS / DEAD MARKUP

- **`.corner` — killed by snes.css but still emitted**: snes.css:116 `.corner{display:none !important}` yet 11 pages still render corner nodes: mechanics 104, releases 120, login 30, character 24, models 20, pricing 16, screenshots 12, adventure 8, newgame 8, chat 4, npcs 4 (≈350 hidden elements per full load on releases/mechanics) plus 52 inline `.corner` rule blocks. chat.html:622 `.ascii-art .corner{…}` re-styles them in the pre-snes block — still dead (display:none !important wins). Intentional kill, but the markup and rules were never removed.
- **`.fog` — 9 inline rule sets, 0 real uses**: character.html (~line 60-75: full "Drivande dimma" vignette with .fog::before/::after radial gradients) and mechanics.html define drifting-fog CSS; no page has a `<div class="fog">` (the only "fog" string left in chat.html:566 is a weather keyword). mechanics.html even has its own `.fog{display:none}` self-kill (mechanics block#0).
- **`.dice-tray`, `.inv-table`, `.font-switcher`, `.hp-bar`, `.oracle`, `.bottom-nav`, `.scanlines` — zero rules, zero uses**: the removed dice-tray/inv-table/font-switcher features left NO css behind (clean). Note: `.bottom-nav` (ladder 280) has zero uses — the 280 rung is orphaned; snes.css:513 z-280 attaches to something else (battle-drawer-toggle area).
- **`.panel-box`: 7 definitions, 2 uses** (adventure 3 defs/1 use, npcs 4 defs/1 use) — a component that is defined per-page but barely used.
- **adventure.html:11-14 old-palette :root** — largely dead (snes.css :root wins on all overlapping vars).
- **help.html:24 inline scanlines** — dead duplicate of snes.css:92.
- **mechanics.html .fog{display:none}** — dead self-kill.

---

## 7. THEME OVERRIDES — the "mjuka upp" war

Pages with a post-snes.css override block (rounded corners restored against snes.css's global `border-radius:0 !important`, snes.css:40): chat (463 lines post-snes!), adventure (235), platser (181), loggbok (24), npcs (15), admin (14), character (17), facts (10).
Pages WITHOUT any post-snes block (corners stay 0): newgame, help, characters, and all Skin B pages (login, mechanics, releases, pricing, models, screenshots, reset — which never load snes.css and keep 6-16px corners natively).

So corner rounding is a 3-state mess: 0px (newgame/help/characters), 6-20px via !important (chat/adventure/platser…), 8-16px native (Skin B). Within chat.html alone the post-snes block uses **13 distinct border-radius !important values** (0,3,4,5,6,7,8,10,12px; 10px 14px 14px 10px; 10px 20px 20px 20px; 14px 0 0 14px; 20px 10px 20px 20px) and 24 `box-shadow:…!important` rules (chat.html:1250-1279: `.bubble{border-radius:10px 20px 20px 20px !important; box-shadow:…!important}`; 8517: `.cp-box{border-radius:16px}` + backdrop blur) — the page undoes snes.css with equal-force !important, and then patches ITSELF (cx-tab radius bumped 6→8px in yet another block, chat.html ~1430). snes.css has 970 !important declarations; chat.html adds 332 more. This is not theming, it's an escalating CSS war — every new patch needs !important to beat the last one.

---

## 8. EMOJI vs SPRITES

- sprites.js walks TEXT NODES only (sprites.js:1944 `createTreeWalker(root, NodeFilter.SHOW_TEXT)`) with a MutationObserver (1954-1962); it never scans `title=` or `placeholder=` attributes.
- **Raw emoji still shipped in HTML/JS** (all sampled text-node emojis — ☰📖📊❓🖥️💬🚪👤⚔🪞⚡📜💳⚒🧙🗺️ — ARE covered by the 190-entry EMOJI_MAP, so sprites.js replaces them in visible text):
  - adventure.html (~460-478): topbar buttons `🪞 Profile`, `⚙️`, quota pill `⚡`, gear rows `📜💳⚒`; chat.html:1454-1465 mobile menu `☰📖📊❓🖥️💬🚪`, user-tag `👤` (1472); facts.html:197-202 `⚔📖🗺️📜🧙🚪`; chat.html:1626 JS-built `🗺 Unknown location`.
  - **title attributes are never spritized**: sprites.js walks TEXT NODES only (sprites.js:1944 `NodeFilter.SHOW_TEXT`); it never scans `title=`/`placeholder=`. adventure.html `title="🔍 Enlarge portrait"` renders a raw color emoji in the tooltip — the one confirmed leak. Any emoji in a tooltip/placeholder bypasses the whole sigil system.
  - Buttons with emoji+text (adventure `.top-btn`) get the emoji replaced by an 8×8 sigil while their text stays — icon and label render at very different visual weights vs chat's text-only buttons.

---

## 9. i18n

- Mechanism: HTML is authored in Swedish; i18n.js walks the DOM replacing Swedish strings from a dictionary when lang==='en' (i18n.js:8-10). No data-i18n attributes anywhere (0 across all pages) — by design.
- **Doc/code contradiction**: header comment says "Swedish is the original… pre-campaign pages default to Swedish" (i18n.js:8, 6) but the code says `let _lang = 'en'; // English-first: UI är engelska; svenska bara via DM-språk-toggle` (i18n.js:21). Which one is true determines whether every string needs a dictionary entry.
- **Dictionary key explosion from emoji variants**: same string must be listed with and without emoji prefixes — 'Till bordet', '⚔ Till bordet', '⚔️ Till bordet' (i18n.js:41-43); '🚪 Lämna' and 'Lämna' (44-45); '🧙 Karaktär'/'Karaktär' (54-55); '🗺️ Kartan'/'Kartan' (56-57). Root cause is the HTML mixing emoji-prefixed and bare labels — the same inconsistency §8 flags.
- No page mixes languages visibly in static UI (chat static text is English, matching the English-first default; Swedish survives in JS comments and in `I18N.t('…')` call args, which is correct usage).

---

## 10. MOBILE (≤900px treatment)

- Pages with a ≤900px (or 960) layout treatment: chat (900/768/640/520/420), adventure (900/700/640/520/400), login (900/720/640/520/1080), admin (900 + min-901), character (900/760/720/640/400), mechanics (1000/760/480), newgame (900/640/480/400), npcs (900/640/400), platser (960/640/400), loggbok (960/900/640/400), facts (900/640/400), help (900/640/400), screenshots (900/860).
- **Missing the ≤900px treatment**: pricing.html (only 640px), characters.html (only 640/400), models.html (only 720/420/640), releases.html (only 720/640). On pricing (multi-column `.tiers` grid, pricing.html:74) at 700-900px there is no reflow — desktop columns persist until 640. characters.html is a game-facing page (adventurer roster) with z-500 modals and no 900px handling.
- Breakpoint zoo overall: 400/420/480/520/640/700/720/760/768/860/900/960/1000/1080 — 14 different breakpoints across 18 pages; the ≤900px group is the only semi-shared convention.

---

# PART 4 — CONCEPT PROPOSALS (game-UI thinking, Terminal Gothic respect)

Design constraints honored: flat, dark, monospace/pixel, scanlines, gold accents, 0-2px radii default, no glassmorphism, no gradient buttons, no rounded-2xl. Taste: "läskigt men färgglatt, ej flashigt", chat-first, no dead UI.

### C1 — "The Rite-Rail": one topbar for all pages
Replace the 3 topbar patterns (§4.1) with a single component: a flat 48px iron rail with (left) the Cauldron brand sigil + page-tag, (center, on game pages) the turn/quota status as tabular-nums mono, (right) a fixed order of sigil buttons — Codex, Sound, Theme, Menu — all 44px targets, sprite icons only (no emoji+text). Lore pages keep the same rail with the nav links inside the Menu drawer instead of a 6-button link bar. Why it beats current: one component, one height, one touch target everywhere; kills the emoji-button/link-bar/topbar trinity; gives every page the same muscle memory. Effort: M (one shared CSS block + rewrite 11 topbars; chat's user-tag card moves into the rail's right cluster).

### C2 — "The Ledger": chat as a terminal first, bubbles as a toggle skin
CLI mode (body.cli-chat) is already the identity — make it the *base layer*: message log as scrolled parchment lines with `>` prompts, timestamps in mono, dice as text glyphs (already built: chat.html:4315-4319). Bubble mode becomes a CSS skin on the SAME DOM (bubbles = ledger rows with left-rule + sigil), not a parallel styling war (today bubble mode is 463 lines of post-snes !important patches). One font-size: 1.0rem for ALL chat text including reasoning-body (fix chat.html:449 0.9rem). Why it beats current: kills the !important war (§7), makes CLI/bubble a theme preference instead of a fork, and finally enforces the ≥1rem rule everywhere. Effort: L (DOM/CSS refactor of the message renderer; the two modes already share markup, so mostly CSS debt removal).

### C3 — "The Codex Grimoire": sidebar as a book with visible spine
Replace the 2-row micro-tab bar (0.62rem cx-tab, chat.html post-snes) with a spine-tabbed sidebar: 4-5 large vertical sigil tabs down the left edge (Codex/Maps/NPCs/Logs), active tab = gold left-rule + ink fill, labels revealed on hover/expand. On mobile it becomes the existing bottom sheet. Why it beats current: 0.62rem tabs with three stacked override layers (§4.2) are unreadable and patched to death; a spine metaphor fits Terminal Gothic (box-drawing corners, no rounded-2xl), gives 44px targets, and one source of truth for Codex nav on chat + lore pages. Effort: M (one shared .codex-rail block; delete the cx-tab override layers).

### C4 — "One Overlay, One Ladder": the z-index constitution
Collapse the 4 overlay scales (§5) into the existing ladder and enforce it in snes.css: backdrop 290 / drawer 300 / sheet 310 / modal 1000 / lightbox 1100 / feedback 1200 / theme-pop 30000. A 15-line comment block in snes.css listing the ladder + a grep test in CI. Fix the concrete inversions: adventure modals 110-130 → 1000; characters insp-overlay 500 → 1000; login drawer 80/85 → 290/300; chat cd-backdrop/drawer 9990/10000 → 290/300; unify toast at 1200, bottom-center, all skins. Why it beats current: the single most dangerous class of bug (modal under drawer, tooltip over modal) disappears without new CSS — it's a rename sweep. Effort: S-M.

### C5 — "The Archive Spine": kill the two-skin split, one :root palette
Terminal-ize the 7 Skin B pages: link snes.css, delete their custom :root palettes (login/mechanics keep only the extra vars: mechanics' --term-red moves into snes.css), strip corner markup (releases -120, mechanics -104 hidden nodes), and let snes.css's radius:0/box-shadow:none contract apply — which is exactly what the "mjuka upp" pages fought against, so keep the door open: a single `.soft` opt-in class for the few surfaces that legitimately need 6-8px (avatar rings, pills). Why it beats current: one palette (the purple-tinted snes :root), one font pipeline (Spectral actually loads), one radius language; login/pricing/releases stop looking like a different product (§headline). Effort: L (7 pages, mostly deletions; the pages are the least complex in the app).

### C6 — "The Turn-Tally": replace the floating status clutter
The user-tag quota card (chat.html:1526-1555, z-950 tooltip), the adventure quota pill (adventure.html:463), and the header turns info are three implementations of one thing: session state. Merge into one mono strip in the topbar: `TURNS 42 · RESET 14:32 · ⚡` — tabular-nums, term-amber, one tooltip (z-950 is fine once the ladder is constitutional). Why it beats current: one component instead of three, kills the emoji-in-title 🔍 class of bugs (§8), and puts the game's most important scarcity metric one glance away. Effort: S.

---

## Appendix — worst findings ranked
1. Two skins: 7 pages never load snes.css → different palette, fonts, radii, no sprites/i18n.
2. chat.html: 90 hardcoded font-family, 139 hardcoded old-gold rgba, 332 !important, 13 radius values — the sweep failed and the page fights snes.css.
3. Z-index: 4 overlay ladders (80-95 / 110-130 / 500-600 / 9990-12001), tooltips above own modals on adventure.
4. 3 topbar patterns, 4 tab systems, 3 toast positions, 3 drawer scales.
5. 3 palettes for the same var names (snes purple-tinted vs login/mechanics blue-gray vs adventure/newgame warm-gold inline).
6. ~350 hidden .corner nodes + 52 dead .corner rule blocks + dead .fog CSS (character/mechanics).
7. Mobile: pricing/characters/models/releases lack the ≤900px treatment; 14 distinct breakpoints.
8. Sprites never touch title/placeholder attrs (🔍 adventure.html title) — emoji leaks.
9. i18n doc says Swedish-original/Swedish default; code says English-first — dictionary key explosion from emoji-variant labels.
10. Fonts: Spectral/Silkscreen/IBM Plex Mono only load via snes.css @import → Skin B pages silently render Georgia/monospace; 'Press Start 2P' + 'VT323' declared in chat.html but only Cinzel is loaded.
