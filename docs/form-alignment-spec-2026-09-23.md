# Form Alignment — one shape language (2026-09-23)

Shared contract for the UI-shape polish wave. ALL tracks read this first.
Goal (rostad): "putsa UI, aligna former för knappar, boxar etc" — converge the site
onto ONE shape language. The canon is **Den Förbjudna Grimsboken**: flat, sharp,
parchment-dark, gold hairlines. Soft/rounded corners are legacy from an older wave.

## 0. The measured problem (2026-09-23)

**CRITICAL FACT — the global flat reset (snes.css §0, line ~142):**
```css
*, *::before, *::after{ border-radius: 0 !important; }
```
"Platt är språket" (flat is the language — design waves 4+5, c53f7b7). Consequences:
- ANY radius declaration WITHOUT `!important` is **dead code** — it always computes to 0.
- The only LIVE radii are `.soft{border-radius:var(--radius-lg) !important}` / `.soft-full{border-radius:var(--radius-full) !important}` (sanctioned opt-in, snes.css ~line 3225) and legacy ad-hoc `!important` rules with higher specificity than `*` — e.g. adventure's soft-corner blocks (8db4f59, Aug) and login's `--r-*` override block (fe3bed5). Those legacy blocks are exactly what the 2026-09-10 comment forbids: "sätt .soft på elementet. Ett värde, ett ställe. Nya radievärden (6/8/10/12/14/20px) är inte tillåtna."
- So the VISIBLE inconsistency today: login + 6 legacy pages render soft corners, everything else is sharp/flat. The fix is convergence to FLAT + `.soft` opt-in.

- **55 distinct border-radius values** across the site.
- Three competing languages:
  1. snes.css tokens: `--radius-xs:2px --radius-sm:3px --radius-md:4px --radius-lg:6px --radius-full:50%` (canon)
  2. "soft corners" `!important` blocks (8px/10px/12px/14px/16px/18px) on adventure, character, facts, loggbok, npcs, platser + adventure panel boxes — **LIVE and legacy, delete**
  3. login.html private `--r-card:10px --r-btn:8px --r-in:7px` + its own `!important` override block — **LIVE and legacy, delete**
- Button heights: 44px (`--tap-min`, 98×) is canon, but 46/48/50/52px strays exist.

## 1. The ONE radius scale (CORRECTED 2026-09-23 after discovering the global reset)

Live canon: **everything flat (0)** via the global reset; the ONLY sanctioned radii are:
| mechanism | value | use for |
|---|---|---|
| (default, global reset) | 0 | everything: buttons, inputs, cards, panels, boxes, chips |
| `.soft` class | 6px (`--radius-lg`) | avatar rings, image frames that legitimately want softness |
| `.soft-full` class | 50% (`--radius-full`) | circles: avatars, dots, round icon buttons |
| pill (`border-radius:999px !important` + comment) | 999px | ONLY existing pills (turns-pill etc.) — keep as-is, don't create new |

Sweep rules (corrected):
- DELETE every legacy `!important` radius block/value that isn't `.soft`/`.soft-full`/existing-pill — those pages converge to flat (the canon).
- Literals WITHOUT `!important` are dead code: map them to the matching token (`var(--radius-xs/sm/md/full)`) where the intent is documentation (e.g. a card that would want --radius-md if flat ever lifts) OR delete the declaration entirely. Either is acceptable; mapping keeps diffs small and intent readable. Do NOT add new `!important`.
- Elements that visually NEED roundness today via legacy `!important` (avatars, dots, round buttons): convert to `.soft`/`.soft-full` CLASS on the element (HTML edit allowed — shape only) instead of ad-hoc rules. Check current live rendering intent: if the element was square since the reset (because its rule lacked !important), leave it square — flat is canon, don't "restore" roundness that already died.
- Multi-value shape expressions (chat bubble tails `2px 4px 4px 2px`, wax seals `55% 55%...`) — these are already DEAD under the global reset unless `!important`. Treat like other dead literals: keep with token mapping or delete; do NOT make them live.
- `border-radius:0` intentional flat rules — keep (redundant but harmless documentation).

## 2. Heights & touch targets

- Every interactive control (button, chip, tab, link-button, input): `min-height: var(--tap-min)` (44px) on ≤640px; desktop floor 40px for rail-icon buttons (existing `.rr-btn` 50×40 / 44×38 stays — rail.css owns it, don't touch).
- Large primary CTAs (login gate button, pricing main CTA, newgame start): `min-height: var(--tap-lg)` (48px — new token in snes.css).
- Replace stray literal min-heights 46/48/50/52px on interactive controls with the right token.
- Content boxes (textareas 120/150px etc.) are NOT touch targets — leave their heights.

## 3. Borders & spacing (light pass, same wave)

- Border canon: `1px solid var(--edge)` (default), `1px solid var(--gold)` / `rgba(var(--gold-rgb),…)` (accent), `border-top: 2px solid var(--gold)` (btn-gold signature). Convert hardcoded `rgba(201,162,39,X)` borders to `rgba(var(--gold-rgb),X)` where trivial; do NOT rewrite colors otherwise.
- Do not touch: color values, fonts, animations, layout grids. This wave is SHAPE ONLY.

## 4. Track assignments (exclusive file ownership)

- **Track FORM-A** (parent, already done): snes.css — add `--tap-lg:48px` token; nothing else.
- **Track FORM-B**: adventure.html, character.html, facts.html, loggbok.html, npcs.html, platser.html — delete the soft-corner `!important` blocks, map all literal radii to tokens per §1, fix stray control heights per §2.
- **Track FORM-C**: login.html + chat.html — login: repoint `--r-*` to tokens, remove its radius override block if fully redundant; chat: map literal radii to tokens (KEEP bubble-tail multi-values + wax-seal shapes), stray control heights.
- **Track FORM-D**: admin.html, newgame.html, characters.html, help.html, mechanics.html, models.html, pricing.html, releases.html, screenshots.html, reset.html, 404.html, book-souls/index.html — same sweep.

## 5. Verification (every track, per file)

1. `python3 scripts/css-brace-check.py <file>` — diff against `git show HEAD:<file>` through the same checker; report pre-existing vs introduced (known false REDs).
2. `<style` count == `</style>` count.
3. `node --check` on every inline `<script>` body (skip `type="application/ld+json"`).
4. Radius census: `grep -o 'border-radius:[^;}]*' <file> | sort | uniq -c` — every remaining literal must be either 0, a token, 50%, 999px, or a deliberate multi-value shape. List leftovers in the report with justification.
5. Grep `min-height:4[678]px|min-height:5[02]px` — zero on interactive controls (or tokenized).
6. Live smoke: `docker cp` + `curl -s http://localhost:8092/<page>` → 200 + your changes present.
7. Report to `tmp/track-form-<X>-2026-09-23.md`.

## 6. Rules

- NEVER edit snes.css, rail.css, rail.js (parent-owned). Note cross-file needs in your report.
- No copy/text changes. No identifier renames. Shape only.
- The patch tool eats trailing newlines on single-line replacements — restore them.
- A CSS comment containing `*/` kills the block — check comments you touch.
- Budget ≤40 tool calls per track; start editing within the first 8 calls.
