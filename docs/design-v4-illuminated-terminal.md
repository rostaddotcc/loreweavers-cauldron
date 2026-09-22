# Design v4 — "Illuminated Terminal" · canonical design-system spec

Status: **CANON** (2026-09-22). This is the reference for all future dnd-llm frontend
work. Implemented foundation lives in `frontend/snes.css` (§5b button tiers, `--fs-*`
tokens in `:root`). Source brief: `tmp/design-brief-v4-2026-09-22.md`.

## 1. Aesthetic thesis

A **grimoire displayed inside a DOS terminal**. The chrome stays flat, dark and
terminal-ish (scanlines, mono labels, box-drawing, literal command syntax in
terminal-green/amber) — the CONTENT gets manuscript craft: reading typography with
real hierarchy, illuminated initials, small-cap gold rubrics. Scary but colorful,
never flashy. We evolve Terminal Gothic — we do not abandon it.

The boldness is spent in ONE place: the **Illuminated DM initial** (§6). Everything
else stays quiet and disciplined.

## 2. Palette — one source, fixed semantics

`snes.css :root` is the **only** colour source. No theme switcher, no
`data-default-theme`, no runtime `setProperty`. Each hue means exactly one thing —
never shift hue families:

| Token | Meaning | Use for |
|---|---|---|
| `--gold` / `--gold-bright` | sacred / UI | headings, rubrics, primary button, highlights |
| `--blood` / `--blood-bright` | HP / danger | HP bars & **fills** (`--blood`); danger **text** (`--blood-bright`) |
| `--arcane` / `--arcane-bright` | magic / player | player voice, spells, magic items |
| `--ember` | quests / warmth | quest markers, warm warnings |
| `--poison` | success / equipped | heals, success, equipped badges |
| `--teal` | info | Guardian/system info, factual asides |
| `--bone` / `--bone-bright` / `--bone-dim` | reading text | body / emphasis / meta-captions |
| `--ink`, `--stone`, `--stone-2`, `--stone-3` | surfaces | page → panels → raised chips |
| `--edge`, `--edge-hi` | borders | 1px hairlines |
| `--term-green`, `--term-amber` | terminal chrome | literal command/keycap syntax ONLY |

Rules:
- **Never hardcode a colour.** Solid → `var(--token)`; alpha → `rgba(var(--token-rgb), α)`.
  Every colour token has a `--*-rgb` twin in `:root` — change both, together.
- **Contrast floors (measured, see §8):** bone on ink ≥ 7:1 (measured 11.36:1); every
  text token ≥ 4.5:1 on ink/stone/stone-2. `--blood` is fills/bars/borders only —
  as text it is 2.5:1 and therefore banned; use `--blood-bright`.
- Flat language: **no gradients on panels**. Gradients allowed in exactly two places:
  the `.btn-gold` sheen sweep and HP/XP trough fills.
- Panels separate by **value** (ink < stone < stone-2 < stone-3), not by shadow.

## 3. Typography

Fixed 4-role hierarchy (no font switcher):
`--font-display:'Cinzel'` labels/headings/buttons · `--font-body:'Spectral'`
narration/chat · `--font-mono:'IBM Plex Mono'` numbers/system ·
`--font-accent:'Silkscreen'` micro-labels only.

### Type scale (`--fs-*`, root 16px) — use these instead of naked rem values

| Token | Value | Role |
|---|---|---|
| `--fs-micro` | .65rem | Silkscreen chips/micro-labels ONLY |
| `--fs-tiny` | .78rem | meta/captions (contrast ≥4.5:1 required) |
| `--fs-sm` | .9rem | secondary UI |
| `--fs-base` | 1.0625rem | default reading text — **never below 1rem anywhere** |
| `--fs-chat` | 1.125rem | player chat + composer |
| `--fs-narr` | 1.2rem | DM narration |
| `--fs-npc` | 1.16rem | NPC speech |
| `--fs-h3` | 1.35rem | h3 / section rubrics |
| `--fs-h2` | 1.7rem | h2 |
| `--fs-h1` | 2.2rem | h1 (Cinzel 800, tracking .06em) |

- Headings/labels: Cinzel uppercase — labels tracking .14em, h1 tracking .06em.
- Section rubrics (manuscript style): Cinzel 700 uppercase, gold, tracking .14em,
  at `--fs-h3` (see help.html `h2`).
- Narration line-height 1.65–1.8. Inputs ≥16px (iOS zoom floor — enforced ≤900px in
  snes.css), 18px preferred on the chat composer.
- The **one sanctioned non-token size**: button labels = Cinzel 700 `.8rem`
  uppercase tracking `.1em` (§5b bakes it in — never set button font-size by hand).

## 4. Buttons — three tiers, defined once (snes.css §5b)

Page-local button CSS is a bug. Use these classes on `<button>` **or** `<a>`:

- **`.btn-gold`** — primary / CTA. THE action on any surface. Gold rubrication:
  flat `--stone-3` fill, 1px `--gold` border, `--gold-bright` Cinzel label, subtle
  top highlight line. Hover: 8% gold tint + border glow. **One sheen sweep on
  `::after` — nothing more.**
- **`.btn-ghost`** — secondary. `--bone-dim` border + text on transparent; hover brightens.
- **`.btn-blood`** — danger (delete, leave, reset). `--blood` border, `--blood-bright`
  text; hover fills blood with `--bone-bright` text.

Shared geometry (all three): flat, `border-radius: 0` (opt-in `.soft` 6px /
`.soft-full` 50% only), `min-height: 38px` desktop / **44px mobile** (≤900px floor),
`min-width: 44px` (icon-only buttons), label style per §3. States:

- `:focus-visible` → 2px `--gold` outline + 2px offset (ALL interactive elements,
  global rule in §5c — do not suppress outlines).
- `:active` → `translateY(1px)` press.
- `:disabled` / `[aria-disabled="true"]` → opacity .45, `pointer-events: none`.

Legacy classes (`.gate-btn`, `.go-btn`, `.danger-btn` …) still work (§5 flattening)
but new surfaces use the three tiers.

## 5. Layout constants (unchanged canon)

- **z-index ladder** — 280 nav < 290 drawer-backdrop < 300 drawer < 310 sheet <
  320 console < 400 d20 < 500 modal < 520 mobile menu < 999 scanlines < 9990
  backdrop < 9995 codex panel < 10000 overlays < 11000 lightbox < 12000+ feedback.
  0–99 = local component stacks. Never invent rungs.
- **Rounding is opt-in:** `.soft` (6px) / `.soft-full` (50%). No ad-hoc radii.
- **Touch targets:** ≥44×44px on mobile for buttons/chips (WCAG 2.5.8 AAA + Apple
  HIG). The floor in snes.css covers `button`, `[role=button]`, the three tiers and
  chips (`.fchip/.vault-chip/.mini-btn/.top-btn/.rr-btn`); deliberate exceptions must
  beat it with higher specificity AND be documented (current one: Composer v5
  mic/undo/send at 32px — snes.css §36).
- **Sprites, not emoji** (sprites.js). Monochrome CLI glyphs (✦ ✕ ✓ ♫ …) are exempt.

## 6. Signature element — "Illuminated DM initial"

The one bold move. On **DM narration only**: the first letter of the first paragraph
renders as a **2-line gold drop-cap** — `float: left`, Cinzel, `--gold`, slight
text-shadow glow, line-height ~.8, small right/top margin so text wraps cleanly.

Contract for chat.html (Agent 2):
- Apply to the first letter of the DM narration's **first paragraph** only (both
  transcript load and live messages). NOT on NPC, player, system or Guardian text.
- **Bubble mode yes; CLI mode:** apply only if it stays legible in the mono terminal
  skin — if it harms CLI, scope it to bubble mode (`body:not(.cli-chat)`) and skip
  it there. CLI legibility wins over the flourish.
- Implementation sketch: `::first-letter` on the first `.text` paragraph of
  `.msg.dm` (e.g. `body:not(.cli-chat) .msg.dm .text:first-of-type::first-letter`),
  or a one-time wrapper span if the typewriter needs plain text nodes — if wrapped,
  keep it invisible to `startTypewriter` text-node collection unless intended, and
  never break `dataset.key` dedup or TERM_LEXICON highlighting.
- Everything else on the page stays quiet. No second flourish.

## 7. Motion

Keep existing micro-interactions (typewriter, D20 ceremony, pixel bursts, live
effects, sheens); add nothing flashy. New motion budget: the `.btn-gold` sheen sweep
(§4) and nothing else. **Everything** respects the global `prefers-reduced-motion`
block at the end of snes.css — never remove or reorder it (it must stay last-ish so
it wins ties).

## 8. Measured contrast floors (WCAG 2.2, values from shipped `:root`)

| token | hex | on ink | on stone | on stone-2 | on stone-3 |
|---|---|---|---|---|---|
| bone | #d9c9a6 | **11.36** | 9.81 | 8.71 | 7.55 |
| bone-bright | #f2e6c8 | 14.96 | 12.92 | 11.46 | 9.95 |
| bone-dim | #ab9b80 | 6.83 | 5.90 | 5.24 | 4.54 |
| gold | #d4a92c | 8.41 | 7.26 | 6.44 | 5.59 |
| gold-bright | #f0d675 | 12.89 | 11.13 | 9.87 | 8.57 |
| blood-bright | #e66977 | 5.88 | 5.08 | 4.50 | — |
| ember | #e07326 | 5.88 | 5.08 | 4.50 | — |
| arcane | #a47ee3 | 5.90 | 5.09 | 4.52 | — |
| poison | #7aa35e | 6.39 | 5.52 | 4.90 | — |
| teal | #609ba4 | 5.94 | 5.13 | 4.55 | — |

Floors: bone ≥7:1 on ink; all text tokens ≥4.5:1 on ink/stone/stone-2. Text on
stone-3 (button fills) uses `--gold-bright` (8.57), `--bone` (7.55) or `--bone-dim`
(4.54) only. If you change a palette value, re-run the contrast script
(`tmp/agent3-designsystem-report-v4.md` §V3 embeds it) and update this table.

## 9. Do / Don't

**Do**
- Use `--fs-*` tokens for every font-size; `.btn-gold/.btn-ghost/.btn-blood` for
  every button; `var()`/`--*-rgb` for every colour.
- Keep chrome terminal (mono, box-drawing, scanlines) and content manuscript
  (Spectral reading text, gold rubrics, drop-cap).
- Put shared component looks in snes.css, and give interactive elements a visible
  `:focus-visible` state.

**Don't**
- Don't hardcode colours, invent radii (only `.soft`/`.soft-full`), invent z-rungs,
  or add gradients to panels.
- Don't write page-local button CSS or page-level `!important` override blocks
  ("MJUKA UPP" antipattern).
- Don't use `--blood` as text colour; don't put body text below `--fs-base`/1rem.
- Don't wrap snes.css in `@layer` (cascade-layer `!important` inversion — see the
  flag at the top of snes.css).
- Don't add a theme/font switcher or a second palette source. Don't shift hue
  semantics. Sprites over emoji.
- i18n.js stays untouched (canon); new UI strings are static EN.
