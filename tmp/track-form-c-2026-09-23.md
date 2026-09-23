# Track FORM-C report — login.html + chat.html (2026-09-23)

Executed under the CORRECTED spec §0/§1 (global flat reset `*{border-radius:0 !important}` in snes.css §0 → flat is canon; `.soft`/`.soft-full` are the only sanctioned radii; no new `!important` radius).

## frontend/login.html

### Vars & override block
- DELETED private vars `--r-card:10px; --r-btn:8px; --r-in:7px` (line ~135) — live legacy softness, converged to flat per corrected §1.
- DELETED the legacy soft-radius override block (was ~644-649): 6 `!important` radius rules gone (`.btn/.gate-btn/inputs`, `.tablet/.ptier/cards`, `6px` chips, `.f-icon` 9px, `.rail-dots` 99px, `.rail-arrow` 50%). KEPT the non-radius parts of that block: `.rail-arrow` transition rule and `.rail-arrow:hover/:active`, `.rdot-pause` etc. untouched.
- Kept exactly two live radius rules with justification:
  - `.rail-dots{border-radius:999px !important}` — existing pill (spec §1: pills stay), normalized 99px→999px.
  - `.rail-arrow` roundness re-expressed as sanctioned `.soft-full` CLASS on the two buttons (`#trail-prev`/`#trail-next`, HTML edit allowed per §1) — same live 50% render, no ad-hoc `!important`.

### Dead base-rule literals (mapped/tokens or deleted)
- `.btn`, `.tablet`, `.ptier`, `.faq details`: dead `var(--r-*)` declarations removed (element renders flat via reset — identical computed result, no dead refs).
- `.f-icon` 9px dead literal removed (icon tile; was square already? No — its `!important` twin lived; per §1 roundness was live → icon tiles are not shape-defining (38px sigil frame); converged to flat. `.pt-flag` `0 0 5px 5px` dead multi-value removed (flag now flat, matches canon).
- `.fs-badge` 5px → `var(--radius-xs)` (dead literal, documented intent; was live 6px via override → now flat; badge is a tiny chip, flat is canon).
- `.faq::-webkit-scrollbar-thumb` 3px → `var(--radius-sm)` (pseudo-element thumb: reset flattens it too; tokenized for documentation, same-value).
- `.ledger-fold` dead 99px base removed (its override rendered 8px, so it was never a pill — override dies → flat, per "don't restore roundness that already died / flat is canon").

### Heights (§2)
- `.field input{min-height:46px}` → `var(--tap-min)` (mobile media block).
- `.gate-btn{min-height:46px}` → `var(--tap-lg)` — gate CTA is the large primary CTA named in §2. Desktop `.btn` already `var(--tap-min)`.

### Radius census after (login.html)
`var(--radius-xs)` ×1, `var(--radius-sm)` ×1 (scrollbar thumb), `999px !important` ×1 (rail-dots pill), `999px` ×1 (dead base, same pill), `50%` ×1 (i.corner::after ornament — decorative corner dot, dead under reset, harmless documentation), `0` ×1 (global `*` reset). Zero stray literals.

## frontend/chat.html

### Radius mapping (§1, corrected: dead literals → tokens, nothing made live, no new `!important`)
- `2px` ×18 → `var(--radius-xs)`; `3px` ×10 → `var(--radius-sm)`; `4px` ×7 → `var(--radius-md)`; `5px` ×3 → `var(--radius-sm)` (tts-select/tts-auto-btn/tts-pop-opt); `6px` ×3 → `var(--radius-md)` (bubble, fb-modal) / cp-close → `var(--radius-sm)` (button); `8px` ×5 → sm/md by role (scrollbar-thumb, tts-pop menu, cp-paint-btn button, JS-string CTA `border-radius:8px`→md); `10px` ×4 → md; `12px` ×1 → md (large avatar frame); `14px` ×1 → md (event-card); batch-turn badge 8px → xs (tiny chip).
- Existing `3px !important` scrollbar thumbs ×2 (`.cx-row`, `.sidebar`) → `var(--radius-sm) !important` (value-equal token; !important pre-existing, none added).
- KEPT as-is (allowed census values): `50%` ×20 (avatars/dots/pc-badge/ttp-toggle), `999px` ×2 (cp pill), `0`/`0 !important` ×6, `inherit` ×1, `1px` hairline (bubble corner bracket), and the three shape expressions: bubble tail `2px 4px 4px 2px`, event tail `0 3px 3px 0`, wax seal `55% 55% 62% 62% / 72% 72% 44% 44%` — all dead under the global reset (no `!important`), kept as documentation per §1 ("keep with token mapping or delete; do NOT make them live"). Multi-value px tails have no token equivalent; tokenizing them would destroy the asymmetric intent, so left verbatim.
- Settings-menu/drawer redesign hooks (`.drop-item`, `.di-name`, `.di-hint`, `#settings-menu`, `#rr-*`) untouched except same-value radius tokens inside those lines.

### Heights (§2)
- Only `min-height:48px` hit is on `.chat-scroll::-webkit-scrollbar-thumb` — a scrollbar thumb, NOT an interactive control → left (spec §2 targets controls). No 46/47/50/52px control strays existed. `.rr-*` 56px roll-request rules are rail-adjacent combat CTA sizing from earlier waves — outside §2's 46/48/50/52 stray list; left alone.

### Borders (§3 light pass)
- No hardcoded `rgba(201,162,39,…)` in either file (already `var(--gold-rgb)` everywhere). Nothing to convert.

## Verification (spec §5)

| check | login.html | chat.html |
|---|---|---|
| 1. css-brace-check vs HEAD | RED working (depth -1 @1525) / RED HEAD (depth -1 @1528) — **pre-existing false RED**, same failure mode, line shift explained by deleted lines. No new imbalance. | RED working == RED HEAD (ends depth 1, 468/467) — **identical pre-existing false RED** (JS regex/quote literals desync the lexer). |
| 2. `<style>` balance | 4 == 4 ✅ | 4 == 4 ✅ |
| 3. `node --check` inline scripts | 2 OK, 2 ld+json skipped ✅ | 3 OK ✅ |
| 4. Radius census | clean (see above; all 0/token/50%/999px) ✅ | clean (tokens/0/50%/999px/inherit/1px + 3 documented shape expressions) ✅ |
| 5. min-height strays | 0 ✅ | 1 hit = scrollbar thumb, not a control ✅ |
| 6. Live smoke | docker cp → curl :8092/login.html = 200; `--r-card` gone, `soft-full` ×3 (2 buttons + comment), `tap-lg` present ✅ | docker cp → curl :8092/chat.html = 200; `var(--radius-md)` ×15 present ✅ |

## Leftovers & notes for parent
- login.html: `.rail-arrow` now relies on `.soft-full` from snes.css — confirm snes.css ships `.soft-full{border-radius:var(--radius-full)!important}` (verified present at ~line 3229). No cross-file changes needed.
- chat.html line ~9174: inline `border-radius:50%` on `#avatar-modal-img` (avatar lightbox) — allowed value, dead under reset but semantically an avatar circle; left verbatim.
- No edits to snes.css/rail.css/rail.js. No text/copy/identifier changes. Transform script kept at `tmp/formc_transform.py` (exact-count assertions, all passed).
- Brace-check false REDs are pre-existing at HEAD for BOTH files — no introduced breakage.
