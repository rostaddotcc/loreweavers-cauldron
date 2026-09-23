# Track FORM-B report — shape-alignment sweep (2026-09-23)

Spec: docs/form-alignment-spec-2026-09-23.md **incl. the mid-run correction** (global flat reset
`*,*::before,*::after{border-radius:0!important}` in snes.css §0 is canon). Strategy applied:

1. **Deleted ALL live legacy soft-corner `!important` radius rules/blocks** on all six pages →
   they converge to flat like the rest of the site (zero `border-radius:…!important` left anywhere
   in the six files). Mixed rules kept their non-radius declarations (transitions, box-shadow,
   min-height) verbatim.
2. **Dead literals (no `!important`) → tokens** per §1 mapping (buttons/inputs `--radius-sm`,
   cards/panels/boxes `--radius-md`, badges/tags/chips/bars `--radius-xs`); pure-radius inline
   styles tokenized too. No new `!important` added anywhere.
3. **Live roundness preserved via sanctioned classes**: adventure's `.pv-portrait` / `.pp-portrait`
   (the only elements whose round shape was LIVE via `50%!important`) got `class="… soft-full"` in
   HTML; their ad-hoc `50%!important` decls were removed. Everything else was already square under
   the reset — left square (no roundness "restored").
4. Heights §2: stray 48/52px literals on interactive controls → `var(--tap-lg)`.
5. Border light pass §3: hardcoded `rgba(201,162,39,X)` **in border declarations** →
   `rgba(var(--gold-rgb),X)` (character 18×, facts 5×). Non-border uses (--gilt token value,
   repeating-linear-gradient ornaments) untouched per "do NOT rewrite colors otherwise".

## Per-file detail

### adventure.html
- Blocks deleted: "Login-känslan mjuka knappar" radius line, `MJUKA UPP RUNDA 2` radius rules
  (9 lines: ep-card/lang-card/vcard/panel-box/continue-panel/cc-card+campaign-card/world-prompt+
  field inputs/start-btn/pv-go/gen-btn), `MJUKA UPP RUNDA 3` whole block (rn-inner/htp-card/rn-ver/
  htp-toggle/mi-modal+pf-box+step+vault-empty+toast/wa-reasoning/tags-group), "Onboarding mjukare
  kanter" radius line, `.step-actions .go-btn` radius, CTA-group `8px !important`. 24 live
  `!important` radii → 0. Comment headers renamed (no "mjuka" claims left).
- Big literal panel radii mapped per brief: `.panel-box/.step/.lang-card/.htp-card/.rn-inner/.mi-modal/
  .adv-details/.pf-thumb-img/.pf-lb-frame/.wa-reasoning/.news-banner/.path/… 16px/18px/14px/12px/10px`
  → `var(--radius-md)`; buttons/inputs (`top-btn/go-btn/start-btn/gen-btn/pv-go/pv-reroll/tab-btn/
  blank-btn/mi-close/av-btn/pf-cell/pf-bar/textareas/selects/ask-tip`) → `var(--radius-sm)`;
  tags/chips/badges (`.path .tag/.arch .tag/.pv-trait/.vcard-use/dropzone/file-item/cc-del/cc-go/
  name-input/danger-btn/ex-bar/ex-fill/ep-card`) → `var(--radius-xs)` (ex-bar/ex-fill/pf-cell are
  progress-bar/cell shapes → md/sm per §1 usage column).
- Radius census before: 86 literals (incl. 24 live `!important`). After: 0 literals except
  `0`×1 (keep, intentional flat doc), `50%`×16 (circles — all dead under reset, harmless),
  `999px`×1 (`.pf-tier` pill intent — dead under reset, kept per §1 "don't create new pills",
  it's existing markup). Tokens: md×16, sm×17, xs×13.
- Heights: `.name-input` 48px→`var(--tap-lg)`, `.go-btn/.danger-btn` 52px→`var(--tap-lg)`,
  `.cc-go` 48px→`var(--tap-lg)`, `.cc-del` min-height 48px→`var(--tap-lg)`. 44px literals left
  (equal to --tap-min value; pre-existing pattern, not strays).
- Borders: no hardcoded rgba(201,162,39) existed.
- `.pv-portrait`/`.pp-portrait` → added `soft-full` class (2 HTML class edits).

### character.html
- Blocks deleted: first-block `MJUKA UPP — Codex-knappar` radius (`8px !important` on av-btn/
  rune-btn/forge-export-btn/top-btn group — min-height/display kept), second (post-snes) block:
  top-btn/tab/panel/ability/trait/coin-btn/rune-btn/av-btn radius stripped from mixed rules,
  7 pure-radius lines deleted (inv-card-row/forge-row/stat/att-item/growth-item/tx/add-form).
  16 live `!important` radii → 0.
- Dead literals → tokens: forge-export-btn/trait/insp-badge/sk-row/ft-item 8px→sm-or-md,
  inv-badge/item-modal-prop-tag/add-form inputs/rune-btn/#notes-editor/att-dropzone/att-item/
  coin-btn 2px→xs, ft-lvl 4px→md, `.tab` `6px 6px 0 0`→`var(--radius-lg) var(--radius-lg) 0 0`
  (multi-value shape kept token-mapped, still dead under reset). Census after: 50%×6, 999px×3
  (res-chip/tr-track/tr-bar pills — existing pill intent, kept), tokens md×3 sm×5 xs×8, lg-pair×1.
- Heights: no 46/48/50/52 strays (all already 44px min-heights).
- Borders: 18× hardcoded rgba(201,162,39,X) in border/border-color decls → rgba(var(--gold-rgb),X)
  (tab border-color, panel/ability/spell-card/stat-group borders, trait border-color, mobile
  tab border-color). --gilt definition and gradient ornaments untouched.

### facts.html
- Blocks deleted: `MJUKA UPP — Codex fakta` block (7 rules) fully removed except `.fchip`/
  `.fact-card` transitions + `.talk-btn` min-height (kept as non-radius rules); `.talk-btn,`
  dangling selector + MJUKA comment in the earlier block was ALREADY broken at HEAD
  (dangling `.talk-btn,` before `:hover` rule) — left as-is, shape-only, noted below.
  6 live `!important` radii → 0.
- Dead literals → tokens: search input/sup-close/fchip/talk-btn/sf-repl/frank×2/f-repl 6-8px→sm,
  sup-modal/fact/sup-fact 8-12px→md. JS-template inline 7px→sm (2×). Census after: md×3, sm×10, zero literals.
- Heights: `.search-wrap input` mobile 48px→`var(--tap-lg)`. Others already 44px.
- Borders: 5× rgba(201,162,39,X) borders → rgba(var(--gold-rgb),X) (sup-modal/fact/fact mobile/
  archive-head panel borders + sup-fact).

### loggbok.html
- Blocks deleted: whole `MJUKA UPP — Codex loggbok` override block (5 rules) → only
  `.day-card{transition:all .2s!important}` kept; later empty `MJUKA UPP — Codex-knappar`
  comment (block was already empty at HEAD) removed. 5 live `!important` radii → 0.
- Dead literals → tokens: scrollbar-thumb 6px→sm, `.tl-ctl` 6px→sm. Census after: sm×2 only.
- Heights/borders: no strays, no hardcoded gold borders.

### npcs.html
- Blocks deleted: `MJUKA UPP — Codex-knappar` (pre-snes, group 8px line + comment; hover rule
  kept) and full `MJUKA UPP — Codex NPC-hall` radius rules (13 rules; top-btn box-shadow/fchip
  transition kept). 13 live `!important` radii → 0.
- Dead literals → tokens: top-btn/hall-search input/fchip/talk-btn/d-back/badge/q-status/
  avatar textarea 6-8px→sm, ncard/sigil/scrollbar-thumbs 8-10px/4px→md, npc-letter/npc-list::after
  2px→xs, player-bubble `8px 2px 8px 8px`→`var(--radius-md) var(--radius-xs) var(--radius-md)
  var(--radius-md)` (multi-value shape expression kept, token-mapped; dead under reset either way).
  Census after: 0×3 (sigil img/d-portrait img intentional flat — keep), 50%×6 (dots/circles),
  tokens md×4 sm×8 xs×2 + bubble multi×1.
- Heights: `.hall-search input` mobile 48px→`var(--tap-lg)`.
- Borders: no hardcoded rgba(201,162,39).

### platser.html
- Blocks deleted: whole `MJUKA UPP — Codex karta` block (9 rules) → top-btn box-shadow/
  transition + ml-item transition kept. 8 live `!important` radii → 0.
- Dead literals → tokens: top-btn/mf-chip 8px→sm, tt-go/map hover/scrollbar 6px→sm.
  Census after: sm×5 only, zero literals.
- Heights/borders: no strays, no hardcoded gold borders.

## Verification (spec §5, all files)

1. **css-brace-check vs HEAD**: adventure 0→0, facts 0→0, loggbok 0→0 GREEN; character 1→1,
   npcs 1→1, platser 1→1 — **pre-existing REDs, identical to HEAD** (character: negative depth at
   JS-line — false RED from JS braces; npcs: "unterminated comment" in JS string; platser: depth 1
   from JS template literals). No new REDs introduced.
2. **`<style` == `</style>`**: 5/5, 3/3, 3/3, 2/2, 2/2, 2/2 — all balanced.
3. **`node --check` every inline script** (ld+json skipped): all six files OK.
4. **Radius census**: every remaining literal is 0 (intentional flat), 50% (circles, dead under
   reset), 999px (existing pills only: adventure `.pf-tier`, character res-chip/tr-track/tr-bar),
   or token-multi-value shape expressions (character tab top-corners, npcs bubble tail).
   **Zero live `!important` radii remain** in the six files. Justifications listed per-file above.
5. **min-height strays** `4[6789]|5[02]px`: zero in all six files (tokenized or absent).
6. **Live smoke**: `docker cp` all six → `loreweavers-cauldron:/app/frontend/`; curl :8092 →
   **200 ×6**; served pages contain tokens (adventure: 44 token hits, 2× soft-full) and contain
   **zero** `8px !important`/`10px !important`; `tap-lg` present in served adventure/facts/npcs.

## Leftovers / notes for parent

- **Pre-existing broken selector in facts.html** (~L223): dangling `.talk-btn,` selector before
  the `:hover` rule inside the old MJUKA block — exists at HEAD, untouched (shape-only brief;
  fixing = editing a rule that isn't radius/height).
- facts/loggbok/npcs/platser/character still have `min-height:44px` **literals** (equal to
  --tap-min's value). Not strays per §2 grep; tokenizing all ~40 of them is a cosmetic churn —
  left for a possible follow-up if parent wants literal-free heights.
- `50%` literals on non-.soft-full elements (adventure cp-icon/cc-icon/arch-icon/ask-ico/pv-*
  circles, npcs dots/arrows, character coin-disc/arrows): dead under the global reset → they
  render flat today, kept as dead documentation per §1 "map or delete, don't make live". If any
  of those circles should actually BE round on these pages, that's a design decision needing
  `.soft-full` classes — flagged, not done.
- snes.css/rail.css untouched. No cross-file needs: `--tap-lg`, `--gold-rgb`, `--radius-*`,
  `.soft-full` all already exist in snes.css (verified L88/95/3228).
