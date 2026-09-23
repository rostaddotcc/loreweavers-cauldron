# Track FORM-D report — shape-alignment sweep (2026-09-23)

Spec: docs/form-alignment-spec-2026-09-23.md **as corrected mid-run** (global flat reset
`*{border-radius:0!important}` is canon; non-!important radii are dead code → token-mapped
or deleted; no new !important; book-souls keeps its radii).

Files: admin, newgame, characters, help, mechanics, models, pricing, releases,
screenshots, reset, 404, book-souls/index (12). snes.css/rail.css/rail.js untouched.

## Key facts driving the sweep

- **Zero legacy `!important` radius rules in all 12 files** (grep verified) — every literal
  radius here was already dead under the global reset. So token-mapping = documentation,
  visually inert. No `.soft`/`.soft-full` class conversions were needed: nothing in these
  files renders round today, and per §1 we do NOT restore roundness that already died.
- book-souls/index.html does NOT load snes.css → no global reset → its radii are LIVE.
  Per correction (4): kept all radius values as-is; only the border pass applied.
- 404.html already flat (lost-btn has no radius — kept flat); its single change was
  `min-height:44px → var(--tap-min)` + gold-border pass.

## Per-file changes (radius before → after, heights, borders)

| file | radius before | radius after | height fixes | border pass |
|---|---|---|---|---|
| admin.html | 2×2px, 10×3px, 19+1×4px, 2×5px, 6×6px (40) | 4×xs, 10×sm, 20×md (34) — 6×6px **deleted** (6px=.soft-class-only per snes.css 2026-09-10 rule; dead, so inert), 2×5px badge spans→xs | ≤640px touch-floor list extended to 6 input/select selectors (.filter-input, .create-user-form input/select, .act-input, .cap-input, .prem-grant select) + 44px→var(--tap-min). Chips already met the 44px floor via existing @media block — verified. Desktop 34-40px table-control floors left (dense admin tables, not ≤640 floor scope) | 2 gold borders→rgba(var(--gold-rgb),…) |
| newgame.html | 15×2px, 1×3px, 1×4px, 7×50%, 1×0 (25) | 15×xs, 1×sm, 1×md, 7×full, 1×0 | summon-btn+pv-go ≤640 56px→**var(--tap-lg)** (start CTA per §2); insp pv-go 50px→tap-lg; scroll-select+pv-reroll 48px→tap-min; 8×44px→tap-min | n/a |
| characters.html | 7×2px, 3×3px, 3×50% (13) | 7×xs, 3×sm, 3×full | summon-btn @900+@640 48/54px→tap-lg; pv-go/pv-reroll 48/50px→tap-lg; select 48px→tap-min; 3×44px→tap-min; insp-prompt textarea 52px = content box, left per §2 | n/a |
| help.html | 1×`border-radius:0` (universal flat) | unchanged (0 = intentional flat, keep) | none needed | n/a |
| mechanics.html | 0 radii | 0 | 9×44px→tap-min. `.slot-pool` min-height:46px left: display container of non-interactive .ss-pip spans (no listeners — JS verified); not a touch target. `.r-btn` already 44px→tap-min. **SVG rx/ry untouched** | 11 gold borders→gold-rgb |
| models.html | 0 | 0 | none | 5 gold borders |
| pricing.html | 0 | 0 | tier-btn/plan-cta (main CTA) collapsed triplicated min-height junk (48/44/44)→single **var(--tap-lg)**; currency-toggle + .back dedup→tap-min; 5×44px→tap-min | 6 gold borders |
| releases.html | 0 | 0 | hist-toggle dedup 48/44→tap-min; 6×44px→tap-min | 8 gold borders |
| screenshots.html | 0 | 0 | 1×44px→tap-min | n/a |
| reset.html | 0 | 0 | 1×44px→tap-min | n/a |
| 404.html | 0 (flat canon) | 0 | 1×44px→tap-min (lost-btn) | 1 gold border (hover bg kept — not a border) |
| book-souls/index.html | 14 radii (LIVE — no snes.css, no reset) | **14 unchanged as-is** per correction (4): 14px book cover + multi-value cover shapes (0 14px 14px 0 etc. = book geometry), 9px/8px level+align+meet plaques, 6px xp bar, 4px scrollbar thumb, 50% npc dot. Forcing flat would visually redesign a page that never had the reset | none (no stray heights) | 8 gold borders→gold-rgb |

## Verification (§5, all steps, all files)

1. **Brace-check vs HEAD** — 10/12 GREEN→GREEN. characters.html RED (depth 1) and
   book-souls RED (negative @line 368) are **identical to HEAD = pre-existing false REDs**
   (the known character/npcs class of bug), zero introduced.
2. **Style-tag balance** — all 12 files `<style` count == `</style>` count. ✓
3. **node --check inline scripts** — 13 script bodies across 12 files (ld+json + src-only
   skipped): 0 failures. ✓
4. **Radius census leftovers** (all justified): admin 34 tokens only; newgame
   15xs/1sm/1md/7full/1×0; characters 7xs/3sm/3full; help 1×0 (intentional flat);
   mechanics/models/pricing/releases/screenshots/reset/404: zero; book-souls: 14 live
   pixel literals kept by explicit spec correction. No stray 5/6-18px remain on any
   snes.css page. ✓
5. **Stray min-heights** — `min-height:4[6-9]px|5[0-9]px` on interactive controls: 0.
   Remaining matches are non-interactive: mechanics .slot-pool 46px (pip display strip),
   characters insp textarea 52px (content box, §2 exempt). ✓
6. **Live smoke** — docker cp → curl :8092: all 11 public pages **200**; admin.html
   **302 → /chat.html** (correct non-admin behavior = pass). Served bodies confirmed to
   contain the new tokens (tap-lg×3 newgame, radius-xs×7 characters, gold-rgb×8
   book-souls, tap-lg pricing, tap-min×4 mechanics). ✓
7. Report: this file.

## Cross-file notes (parent-owned, not touched)

- pricing/releases/models `.tier::before`-style double-border blocks carry BOTH
  `border:1px solid var(--edge)` and a later gold override in the same declaration —
  harmless but redundant; a future wave could dedupe (colors = out of scope here).
- characters.html brace-check RED (depth 1) and book-souls negative-depth @368 deserve a
  dedicated fix track (pre-existing, same as HEAD).
