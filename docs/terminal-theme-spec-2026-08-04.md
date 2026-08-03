# Terminal Theme + Avatar Prompt Clarity — Spec 2026-08-04

User request (rostad, 2026-08-04): The "CLI theme" should be a REAL terminal, not just
bubble-frames removed. Plus: make it obvious how the avatar free-prompt is sent.

## Goals

1. **Avatar free-prompt clarity** — the user can't tell whether they are "painting a new
   card" from the free prompt or from the character sheet. Make it unambiguous.
2. **Real terminal chat UI** — every line renders like an oh-my-zsh terminal: no separate
   boxes, no borders between messages and composer, dice as plain text glyphs with
   animations that stay inside the text line. Combat log untouched this iteration.
3. **Classic terminal themes** — Dracula, Catppuccin (Mocha), Nord/Gruvbox-style palettes
   added to themes.js. If it lands well these become the default.

## Current state (verified 2026-08-04)

- CLI mode = `body.cli-chat` class toggled in chat.html (`CLI_CHAT_KEY='dnd_cli_chat'`,
  default ON). CSS in snes.css section 36 (lines ~1484–1549): removes bubble frames,
  adds `❯` prefix via `.who::before`, transparent composer.
- **BUT**: `.msg.system .box` still has dashed border (snes.css ~173), `.roll-request`
  card still has frames, `.inline-dice` uses 68px SVG d20 (`d20Svg()`, chat.html 2540),
  `.event-batch`/`.event-card` still card-styled, `.guardian-box` still boxed, composer
  is a separate `.input-area` with `border-top` (snes.css 1546–1549).
- TTS button is inside the bubble (`<button class="tts-btn">🔊` in buildMessage dm,
  chat.html ~1962), TTS voice picker sits above the composer (chat.html 1121–1132).
- Avatar modal (chat.html 6000–6027): `#avatar-prompt-input` textarea + "Paint a new
  avatar" (`generateAvatarAction()`, mode 'new', sends freePrompt) + "Update from sheet"
  (`updateAvatarAction()`, mode 'edit', **does NOT send freePrompt** — gap!) + upload.
  Same pattern in character.html (1269/1343), npcs.html (419/500), characters.html
  (484: `insp-prompt-input`, vault avatar).
- Backend `generate_avatar` (main.py 6224): prompt merges user_prompt FIRST (heaviest)
  + auto context, trimmed to 512 (`_trim_prompt`). Works for both new and edit modes.

## Track A — Avatar free-prompt clarity

Files: `frontend/chat.html`, `frontend/character.html`, `frontend/npcs.html`,
`frontend/characters.html`. (Do NOT touch snes.css, backend, api.js, login.html,
adventure.html, newgame.html in this track.)

Requirements:
1. **Label the free prompt clearly**: replace the bare textarea with a labeled section:
   - Heading: `🎨 YOUR OWN WORDS (optional)` + hint `Overrides the auto-built prompt from
     your sheet — describe exactly what you want painted.`
   - Keep textarea id `avatar-prompt-input` (chat/character/npcs) and
     `insp-prompt-input` (characters.html) — id changes break API call sites.
2. **Make the two buttons' difference explicit** (chat.html + character.html + npcs.html):
   - "Paint a new avatar" → `✨ Paint new from my words` (uses free prompt; status text
     shows `✨ New avatar painted — used your words` when freePrompt non-empty,
     otherwise `used your character sheet`).
   - "Update from sheet" → `🔄 Update from sheet (keeps face)` — and it SHOULD also send
     the free prompt now (fix the gap): `API.generateAvatar(kind, seed, 'edit', freePrompt)`.
     Status: `✨ Avatar updated — used your words` vs `used your character sheet`.
   - In `characters.html` (vault forge): one button `🎨 Paint avatar` already sends
     `insp-prompt-input`; add the same labeled section.
3. **Status line feedback**: after generation, always state which source won:
   `used your words` vs `used your character sheet` (bonus: `(free prompt)` suffix).
4. **Do not change backend** — merge logic already correct.
5. Verify: `node --check` on extracted inline scripts (chat.html has 3 blocks,
   character.html/npcs.html/characters.html 1–2 each); grep that `generateAvatar(kind,
   ..., 'edit'` calls now pass the 4th freePrompt arg in chat.html/character.html/npcs.html.

## Track B — Real terminal core (chat.html + snes.css)

Files: `frontend/chat.html`, `frontend/snes.css`. Do NOT touch backend, api.js,
themes.js, login.html, adventure.html, newgame.html, character.html, npcs.html,
characters.html.

Requirements (all scoped to `body.cli-chat` so bubble mode stays intact):

1. **Messages = terminal lines, no boxes**:
   - `.msg.system .box`, `.roll-request`, `.event-batch`, `.event-card`,
     `.guardian-box`, `.scene-card`, `.resume-card` → transparent bg, no border
     (or 1px solid var(--ink) for barely-visible line separation), no box-shadow,
     no border-radius. System lines get a dim `# ` prefix (comment-style) or `·`.
   - `.msg` padding tightened; `.who` becomes a prompt segment: `❯ DM` (gold),
     `❯ You` (arcane), `❯ NPC` (npc color), lowercase-ish, monospace.
   - Player messages: no right-alignment, no bubble — same left flow as everything else.
2. **Composer merges with the stream** (this is the "not 2 boxes" requirement):
   - `.input-area`/`.composer`: no `border-top`, no background box, no padding wall —
     sits flush under the last message. Use a single line `───`-style separator or
     just the blinking `❯` caret.
   - Prompt glyph: `❯` in gold, monospace; textarea transparent with no border;
     send button restyled as terminal text `[ENTER]` or `⚔` → keep `.send-btn` but
     flat/transparent, monospace, gold text on hover.
   - The `>` prefix should not overlap text (padding-left must accommodate it).
3. **TTS controls in CLI mode**:
   - `.tts-voice-picker` collapses to a single compact line: `🗣` + two small
     transparent selects (provider/voice) + Auto toggle, monospace, dim, no box.
   - `.tts-btn` on DM lines: restyle as text link `[♪]` instead of a round 🔊 button
     (keep the same onclick/playTTS(this), keep `.playing` pulse but as color/underline).
4. **Font**: `body.cli-chat` forces a monospace stack on `.bubble .text`, `.who`,
   `.composer textarea`, `.roll-request`, `.msg.system` — e.g.
   `ui-monospace, 'Cascadia Code', 'JetBrains Mono', Menlo, Consolas, monospace`.
   (Do NOT change themes.js fonts here; font var exists as `--font-mono` if present,
   else hardcode the stack.)
5. **Everything else** (typewriter, particles, dice ceremony internals) untouched —
   Track C handles dice visuals. Combat log/`#battle-log` untouched (user said leave it).
6. Verify: CSS brace balance per section; `node --check` extracted chat.html scripts;
   browser screenshot check at 1280px — no visible borders between messages or between
   chat and composer; TTS picker compact.

## Track C — Dice as text + classic themes (chat.html + themes.js)

Files: `frontend/chat.html`, `frontend/themes.js`. Do NOT touch snes.css in this track
(dice CSS changes go inline in chat.html's `<style>` or via classes Track B already
defined; if you need a CSS rule, add it to chat.html inline style with a
`body.cli-chat` guard). Do NOT touch backend, api.js, other pages.

Requirements:

1. **Dice ceremony → plain text glyphs inside the line** (CLI mode only):
   - New function `inlineDiceCeremonyCli(notation, label, roll)` — used when
     `body.cli-chat` is active; `inlineDiceCeremony()` keeps the SVG path for bubble
     mode. Simpler: at the top of `inlineDiceCeremony`, if `document.body.classList
     .contains('cli-chat')` → build a text version and return.
   - Text version: one system line: `🎲 label (notation)` then a **flicker line**
     `⣿ ⣽ ⣾ ...` or rolling unicode digits `4 9 2 17 ...` for ~2.5–3s (same 3s feel,
     no SVG), then result line: `→ [1d20+4] 17 + 4 = 21` (gold on crit, blood on
     nat-1, `✦ KRITISKT!`/`✦ PATETISKT!` retained). All glyphs stay inline (no
     absolute positioning, no 68px boxes).
   - Advantage: two rolls on one line: `[13, 7] → 13 (FÖRDEL)`.
   - Keep SFX + particle burst calls (position them at the message element rect center).
   - Roll-request card (`.roll-request`): keep the two action buttons but restyle for
     CLI: `[🎲 Slå 1d20+4]` / `[🖊 Skriv]` as monospace text buttons, no card chrome —
     or a single line `DM begär: Stealth (1d20+4) — [🎲] [🖊]`.
2. **Classic themes in themes.js**:
   - Append 3 new palettes to PALETTES (keep existing 5):
     - `dracula` — bg #282a36, current line #44475a, fg #f8f8f2, comment #6272a4,
       cyan #8be9fd, green #50fa7b, orange #ffb86c, pink #ff79c6, purple #bd93f9,
       red #ff5555, yellow #f1fa8c. Map: gold→yellow-ish, blood→red, arcane→purple,
       ember→orange, poison→green, teal→cyan, bone→fg.
     - `catppuccin` (Mocha) — base #1e1e2e, mantle #181825, crust #11111b, surface0
       #313244, text #cdd6f4, subtext #a6adc8, mauve #cba6f7, pink #f5c2e7, red
       #f38ba8, peach #fab387, yellow #f9e2af, green #a6e3a1, teal #94e2d5, sky
       #89dceb, sapphire #74c7ec, lavender #b4befe. gold→yellow, blood→red,
       arcane→mauve, ember→peach, poison→green, teal→teal.
     - `gruvbox` (dark) — bg #282828, fg #ebdbb2, red #fb4934, green #b8bb26, yellow
       #fabd2f, blue #83a598, purple #d3869b, aqua #8ec07c, orange #fe8019, gray
       #a89984.
   - Each palette must define ALL keys the others define (same set as existing 5:
     --ink --stone --stone-2 --stone-3 --edge --edge-hi --bone --bone-bright
     --bone-dim --gold --gold-bright --blood --blood-bright --ember --arcane
     --arcane-bright --arcane-deep --poison --teal --term-green --term-amber).
   - Order in PALETTES: terminal, blood, arcane, ember, iron, dracula, catppuccin,
     gruvbox (new at end). Name shown: 'Dracula', 'Catppuccin', 'Gruvbox'.
3. Verify: `node --check` extracted chat.html scripts + themes.js; grep the new
   palette ids exist; browser screenshot with `body.cli-chat` forced + theme dracula —
   dice ceremony shows text glyphs, result line in terminal style.

## Cross-track rules

- All tracks: NO git commands, NO commits, NO docker. Just edit files.
- English UI strings only (existing code is English-first; keep new strings English).
- `node --check` every touched inline script. CSS brace balance on every touched file.
- Sequential dispatch: Track A → verify → Track B → verify → Track C → verify.
- Parent handles final verification, deploy, commit, push.
- Do NOT touch `backend/data/*` (ip_geo.json/users.json have uncommitted changes —
  unrelated, leave them).
