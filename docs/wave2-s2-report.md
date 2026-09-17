# Wave 2 · S2 report — chat.html + snes.css UX fixes (2026-09-17)

Spec: `docs/audit-a2-ingame-2026-09.md` (§1.1, §1.2, §1.3, §2.1, §3.3, §4.2, §4.3, §5-chat).
Scope touched: **only** `frontend/chat.html` and `frontend/snes.css`. No deploy, no commit, i18n.js NOT edited.

## Change table

| # | Item | Anchor(s) — post-edit line numbers | Change |
|---|------|-----------------------------------|--------|
| 1 | P0 turns tooltip | chat.html:1353 (title attr); renderTurnTally ~:2117 | Static title → `Turns left · current turn · day number`. Deleted the per-tick `tallyEl.title` rebuild block (7 lines) — also removes the 1 Hz DOM attribute write. |
| 2a | `.drop-head` CSS | chat.html:178 (after `.drop-sep`, minified one-liner) | Added `.drop-head` + `.drop-head:first-child` per audit §1.1 (Silkscreen micro-caps, gold @ .75). |
| 2b | `.settings-menu` overflow | chat.html:~80 | Added `max-height: calc(100dvh - 70px); overflow-y: auto;`. Mobile `position:fixed` override untouched. |
| 2c | Settings-menu regroup | chat.html:1371–1398 | New order: **Your game** (How to Play — '?' dropped, Feedback) / **Settings** (Models card unchanged, Chat style toggle, About the Models) / **Account** (Usage, Export campaign — hint "download as .zip") / **Leave** (red, last). `.drop-sep` between groups. |
| 2d | Chat-style toggle copy | chat.html:1389 (static) + `syncCliChatLabels()` :~8028 | di-name `Chat style: Terminal`/`Chat style: Bubbles`; di-hint `click to switch to bubbles`/`click to switch to terminal`. Swap code sets both. |
| 3a | ☰ mobile menu regroup | chat.html:1335–1358 | Mirrors settings groups: **Navigate** (Codex) / **Your game** (How to Play, Feedback) / **Settings** (Chat style) / **Account** (Usage, Export campaign, Admin — admin-only) / **Leave** (red). Turns strip stays on top. |
| 3b | Tools sheet merge + delete | chat.html:~8388 (nav tab), old sheet markup deleted | ⚙️ bottom-nav tab now calls `toggleMobileMenu()`. `#sheet-tools` + backdrop deleted (its two unique items — How to Play, Export — already in ☰). Dead `openSheet()`/`closeSheet()` functions removed; the Esc handler's `.sheet.open` sweep removed (zero sheets left in DOM). |
| 4a | `.drawer-btn` CSS | snes.css:523–546 | Shared shape rule for `.drawer-btn`/`.drawer-logout`; neutral variant `border:1px solid var(--edge); color:var(--bone)`; red kept for `.drawer-logout`; new `.drawer-sep` separator rule. |
| 4b | drawer-extras HTML | chat.html:1578–1585 | Character/Engine Room/Admin → `.drawer-btn`; `.drawer-sep`; Leave stays `.drawer-logout`, relabeled **Leave the table**. |
| 5 | Leave label everywhere | chat.html settings-menu, ☰, drawer | All three now read "Leave the table" (target stays `adventure.html`, hint "return to adventure select"). |
| 6a | Sidebar avatar single-layer | chat.html:1536–1546, refreshAvatars :~3080 | `#pc-avatar` element deleted; `#pc-avatar-bg` kept; `refreshAvatars()` pcAv block removed (bg block untouched). Added §3.3 🔍/🎨 hover badges (`.pc-badge` markup + CSS in body-level style block :1507–1517, incl. `@media (hover:none)` always-visible + `.pc-card{position:relative}`). |
| 6b | `openPcLightbox()` | chat.html:3049–3052 | Routes through `openMsgAvatarLightbox('player')` → painted portrait = lightbox at 512px w/ title from `CHAR_NAME` (fallback `#pc-name`); no portrait → `pickAvatar('player')` fallback. |
| 6c | NPC rows single-layer | renderNpcSidebar chat.html:~7588 | `.npc-av-thumb` dropped when `.has-av`; `.npc-bg` kept; dot+icon fallback unchanged. |
| 7a | Lightbox upgrade | chat.html:9197–9209 (HTML), :159–165 (CSS) | `#avatar-lightbox` extended: `‹ n/N ›` bar (`hidden` unless `AVATAR_GAL[kind].count > 1`) + 🎨 "Paint a new portrait" button (`lbPaint()` → `pickAvatar(_lbKind)`); `role=dialog/aria-modal` added. Esc (:8936) + backdrop + ✕ all route through the upgraded `closeAvatarLightbox()` which now also hides bar/paint and clears `_lbKind`. |
| 7b | Lightbox JS | chat.html:2968–3059 | New: `_lbKind`, `_lbBusy`, `_lbUpdateBar()`, `lbRotate(±1)` (own gallery rotate via `API.rotateAvatar`, updates `AVATARS`/`AVATAR_GAL`, mirrors to `refreshAvatars()` + `rerenderChatAvatars()`), `_lbOpenForKind()`, `openMsgAvatarLightbox(kind)`, `lbPaint()`. |
| 7c | msg-avatar lightbox-first | avatarHtml() :2386, NPC variant :3503 | `onclick` → `openMsgAvatarLightbox(kind)`; title → `Click to enlarge`. `pickAvatar` now reachable only via 🎨 badges (sidebar, lightbox) and internal modal refresh calls (:2511, :2832, :2864 — paint-modal preview updates, not click targets). |
| 8 | Release toast | chat.html:8345–8352 | `RELEASE_TOAST_VERSION = 'v1.4-20260917'`; text → `✦ New: Qwen 3.8 Flash — now in the free tier. A fast DM mind, free for every account. Pick it in Settings.` |
| 9a | Reduced-motion CSS | snes.css end-of-file (:2986–2999) | Global `@media (prefers-reduced-motion: reduce)` block per audit §5 (animation/transition → .01ms, `scroll-behavior:auto`). |
| 9b | Embers gating | chat.html:8425–8451 | `EMBERS_RM = matchMedia('(prefers-reduced-motion: reduce)').matches` — skips spawn loop + `tick()`, hides canvas under RM. |
| 10 | Quest empty state | chat.html:1560 | → `No quests yet — the DM will post one when the story hooks you.` |
| 11 | Icon table | chat.html:1566, :6038–6042, :7348, :8786 | 📖 now Codex-only in visible strings: Journey section → 📜; `/chapter` messages → 📜 (journal content); `character_update` event icon 📖→🧙; Codex Journal tab 📖→📜. 📜 usage elsewhere verified journal/lore-only (JRNL tab, "Opening the tome", lore-added messages, quest events) — compliant with "📜 = journal/logbook". |

## Verification evidence (all run post-edit)

- **JS syntax**: 8 `<script>` blocks extracted via `re.findall` → `node --check` each → **all pass, 0 failures**.
- **CSS brace balance** (comments stripped): chat.html style[0..3] = 933/933, 89/89, 41/41, 52/52; snes.css = 841/841 → **all balanced**.
- **HTML parse**: `html.parser` over chat.html → **no exceptions**.
- **`#pc-avatar` grep**: remaining hits are only `#pc-avatar-bg` (element + CSS + refreshAvatars bg block), `.cd-npc-avatar` (unrelated drawer component), and the inert `.pc-avatar`/`.pc-avatar .pxs` CSS rules (kept harmless per audit §3.3; `.pc-avatar` id no longer exists in DOM or JS).
- **Symbol consistency**: `pc-badge` 10 (CSS+markup), `openPcLightbox` 2 (def+badge), `lbRotate` 3 (def+2 arrows), `_lbKind` 9 (all inside lightbox fns), `lbPaint` 2 (def+button), `openMsgAvatarLightbox` 4 (def+avatarHtml+pc wrapper+NPC variant) — every def has its callers, no orphans.
- **Dead-code check**: `openSheet`/`closeSheet`/`sheet-tools` → **0 hits** in chat.html.
- **Esc/backdrop close**: :8936 `closeAvatarLightbox()` in Escape handler intact; backdrop `if(event.target===this)` + ✕ intact; upgraded close hides bar/paint/clears `_lbKind`.
- **git diff --stat**: `frontend/chat.html | 255 ++++--`, `frontend/snes.css | 28 +-` — no other files touched by this agent (other dirty files in the tree are sibling agents' completed work + runtime data).

## i18n.js flags (NOT edited — for the i18n pass)

Dict is SV→EN; walker runs for EN campaigns only. New/changed strings in chat.html are authored in English (UI-in-English identity), so EN is fine. Stale dict entries whose chat.html source strings changed or disappeared:

| i18n.js line | Entry | Status |
|---|---|---|
| :477 | `'Klicka för att byta bild' → 'Click to change image'` | **Stale in chat.html** (msg-avatar titles now `Click to enlarge`). Check character.html/npcs.html before deleting. |
| :634 | `'Inga uppdrag ännu…' → 'No quests yet…'` | Stale — quest empty state is now English copy with direction; SV campaigns will show the English string. |
| :777 | `'Lämna' → 'Leave'` | Stale for chat menus ("Leave the table" now, English). Check other pages. |
| :704/:376 | `'Hur spelar man?' / 'Hur spelar man' → 'How to Play'` | Chat menus now say "How to Play" directly; entries may still serve other pages. |
| — | New English strings with no SV counterpart (drop-heads Your game/Settings/Account/Navigate/Leave, "Chat style: Terminal/Bubbles", "click to switch to bubbles/terminal", "Export campaign", "download as .zip", "Leave the table", "Paint a new portrait", "Click to enlarge", new quest empty state, v1.4 toast, 📜 Journey) | SV campaigns will render these in English. If SV parity is wanted, the dict direction (SV→EN) can't cover them — needs the §5 suggestion "flip static HTML to EN and let walker translate to SV" or added reverse entries. |

Note: `syncCliChatLabels()` writes labels via `textContent` at runtime — bypasses the walker either way (same as before this change).
