# Admin Dashboard v2 — "Mission Control" (2026-09-27)

> **Status: riktning godkänd av rostad 2026-09-27 (§6) — bygge pågår. INGEN commit, INGEN deploy förrän han säger till.**
> Companion sketch: `frontend/preview-admin-v2.html` (clickable mock, real aggregates, pseudonymised per-player rows).

**Goal:** Replace the dark-fantasy CEO view in `frontend/admin.html` with a modern, interactive
analytics console whose first job is **income** — revenue, breakdowns, and drill-down from any
number on screen to the records behind it.

**Not aligned with the game.** The admin page gets its OWN design system (`frontend/admin.css`,
no `snes.css`, no pixel fonts, no parchment). Game canon ends at the login door.

**Architecture:** one shell page + own design system + own JS module; a *small* set of aggregation
endpoints; a hash router (`#/revenue/product/unlock10`) so every drill-down is deep-linkable and
the browser Back button works; hand-rolled inline-SVG charts (no libraries — must work on LAN).

**Tech stack:** FastAPI (existing `backend/main.py` helpers), vanilla JS (ES modules or one IIFE),
inline SVG, pytest, CDP visual-QA battery (`scripts/qa_run.py`).

---

## 0. Ground truth measured for this plan (2026-09-27)

| Fact | Value | Source |
|---|---|---|
| Accounts | 159 (156 players, 3 admins) | `backend/data/users.json` |
| Tiers | 144 free · 9 patron (tier2) · 6 support (tier1) · 0 lifetime | same |
| Campaigns | 132 dirs / 118 transcripts | `backend/data/campaigns` |
| Transcript calls logged | 3 315 · 41.3 M tokens | scan of `*/transcripts/*.jsonl` |
| Visits | 14 630 total · peak 928 (2026-09-21) | `backend/data/visits.json` |
| Billing ledger | 5 rows · 253 SEK lifetime · 3 paying accounts (DE 139, GB 70, SE 44) | `backend/data/_billing_ledger.json` + cached geo |
| Value delivered | 1 839 consumed turns across 67 accounts (dm 1 320 · tts 236 · image 168 · undo 38 · char_gen 27 …) | `backend/data/turn_ledgers/*.jsonl` |
| Ledger row types in use | `stripe:tier1`, `stripe:patron500`, `stripe:donation`, `stripe:churn`, `stripe:cancel_scheduled` | same |
| New product (2026-09-27) | `unlock10` (10 € one-time: +100 turns, permanent features) | `STRIPE_PRICES` main.py:10863 |
| Endpoints the page uses | `/api/admin/stats`, `/api/admin/billing`, `/api/admin/feedback`, `/api/admin/user/{u}`, `/api/admin/user/{u}/ledger`, `/api/admin/visits_country` | grep of `main.py` |
| Current page | 2 660 lines, 2 inline `<style>` blocks (16–732) + 1 inline script (800–2658) | `frontend/admin.html` |

`_ledger_totals()` already gained `month_revenue` + `month_key` today (uncommitted, main.py:10327).
The transcript scan is cheap right now (0.1 s for all 118 files) → **no caching layer yet** (YAGNI);
re-measure in Fas 0 and only add a TTL cache if the payload exceeds ~1.5 s.

---

## 1. Non-goals (YAGNI — do not build these)

- No chart library, no CDN, no build step. Inline SVG only.
- No Stripe API calls for fees/refunds — the local ledger is the single source of money.
- No auth/permission change; admin gate stays exactly as it is (sessionStorage + 401/403).
- No historical backfill of transcripts whose `meta.model` is missing ("unlabelled" stays a category).
- No new pricing/pro tier logic. Only *display* of what the ledgers already contain.
- **No subscription concepts at all** (owner decision 2026-09-27): no churn view, no MRR/ARR panel, no
  renewals. The shop is one-time purchases; legacy subscription rows appear only as transactions.
- **No fallback to the old page.** Admin v2 replaces `/admin.html` outright — the old markup, CSS and
  inline JS are deleted, not parked behind a URL.
- No touching the game's pages, `snes.css`, or `rail.css` in this wave.

---

## 2. Data contract (backend)

### 2.1 `GET /api/admin/overview?window=24h|7d|30d|all` (new)
One payload for the first paint of every panel. Server computes; frontend never re-derives money.

```jsonc
{
  "generated_at": "2026-09-27T20:11:02+02:00",
  "window": "30d",
  "totals":   {"accounts":159,"players":156,"admins":3,"campaigns":132,"turns":0,"tokens":41294305,"ai_calls":3315},
  "revenue":  {"today":70,"month":70,"month_key":"2026-09","lifetime":253,"mrr":0,"transactions":4,
               "paying_customers":3,"conversion_pct":1.9,
               "by_product":[{"key":"unlock10","label":"10 € unlock","sek":0,"count":0}, …],
               "by_month":[{"key":"2026-08","sek":183,"count":2},{"key":"2026-09","sek":70,"count":1}],
               "by_date":{"2026-08-04":44,…},"by_country":[{"cc":"DE","sek":139,"paying":1},…],
               "customers":[{"user":…,"sek":…,"payments":…,"products":[…]}]},
  "value":    {"turns":1839,"tokens":41294305,"ai_calls":3315,"tokens_per_sek":163219,
               "kr_per_1m_tokens":6.13,"turns_windowed":true},   // what players got for the money
  "series":   {"revenue_day":{…},"api_calls_day":{…},"visits_day":{…},"signups_day":{…},"turns_day":{…}},
  "usage":    {"providers":{…},"models":{…},"tts":{…},"images":{…}},
  "traffic":  {"visits":{…},"by_country":[…],"referrers":{…}},
  "tiers":    {"free":144,"tier1":6,"tier2":9,"lifetime":0},
  "users":    [ /* compact rows: no per-user daily dicts — those are per-entity */ ]
}
```

Rules:
- `users` carries the compact table row set (username, role, tier, country, campaigns, tokens, turns,
  revenue, last_active). Drop `daily`/`model_tokens` from this list to keep the payload small —
  they move to the drill-down endpoint.
- Every windowed metric carries the window it was computed for; lifetime counters (`unguarded_tokens`,
  `models` totals) are labeled `lifetime:true`. **Never let a lifetime number sit in a windowed row.**

### 2.2 `GET /api/admin/billing` (extend, keep all existing keys)
Add: `by_product`, `by_month`, `customers` (`[{user, sek, rows, first_ts, last_ts, products[], active}]`),
`churn_by_day`. Keep `mrr/transactions/total/month_revenue/month_key/per_user/ledger/churn` byte-identical.

### 2.3 `GET /api/admin/user/{username}` (extend)
Add `revenue_history` (that user's ledger rows) and `daily` (already produced by
`_scan_user_transcripts`) + `model_mix`. Powers the player dossier drawer.

### 2.4 Untouched
`/api/admin/stats` stays as-is (other surfaces may use it); no action endpoint changes —
`setCap / topUp / grantTier / setTier / setRole / resetTurns / createUser / deleteUser` keep their
exact fetch bodies.

---

## 3. Frontend structure

```
frontend/admin.html          ← shell (~120 lines: header, sidebar, view mounts, script tags)
frontend/admin.css           ← the console design system (own tokens, no snes.css)
frontend/admin.js            ← router + views + charts + drawers (~1 500 lines, one IIFE)
frontend/admin-actions.js    ← extracted existing admin mutations (cap/tier/role/turns/user CRUD)
frontend/preview-admin-v2.html ← the design sketch (mock data, deletable after approval)
```

Design language ("Mission Control"): dark slate surfaces + one accent, **system UI font stack**
(`-apple-system, "Segoe UI", Inter, Roboto, sans-serif`), tabular numerals, 8–10 px radii,
1 px hairline borders, chart grid lines at 8 % opacity, motion ≤160 ms and
`prefers-reduced-motion`-guarded. Light theme via `[data-theme="light"]` on `<html>`.
Contrast floor 4.5:1 on all text; touch targets ≥44 px.

> **Radius note:** the game's flat canon comes from `snes.css`'s global
> `*,*::before,*::after{border-radius:0 !important}`. Since admin does not load `snes.css`,
> the console is free to use radii — document this in the file header so nobody "fixes" it later.

**Money next to value (owner decision):** every money surface carries the matching value-delivered
number — turns delivered, tokens served, AI calls, tokens per kr and kr per 1M tokens — so a payment can
be read against what it bought. Turns come from `turn_ledgers`, tokens/calls from the transcripts.

**Revenue drill-down dimensions (owner decision): product · country · date · transactions.** No churn,
no renewals, no subscription lenses anywhere.

Views (sidebar): **Overview · Revenue · Players · Usage · Traffic · Feedback**
(+ optional **System** stretch: container/DB sizes, job health).

Global **scope bar** above the canvas: window (24 h/7 d/30 d/all) · tier · country · role,
with a chip summary, an honest `filtered N of M` label, and a `⟲` auto-refresh toggle (60 s) plus a
"last updated" stamp.

Drill-down = right-hand **drawer** (not modal): click a KPI tile, a chart bar/slice, a table row, or a
ledger entry → the drawer opens with the records behind that number. `Esc`, `‹ back`, or the
breadcrumb closes it. State lives in the hash: `#/revenue/product/unlock10`, `#/players/player-03`,
`#/usage/model/step-3.7-flash`. Deep links must survive a reload (fetch on cold load).

---

## 4. Execution phases (bite-sized tasks; each ends with a verification command)

### Fas 0 — Baseline (30 min, no behaviour change)
1. `git status` must show only the known uncommitted `backend/main.py` pricing work; **do not commit it, do not revert it**.
2. Time the current payload: `curl -s -o /dev/null -w '%{time_total}\n' -b "morkrets_token=$TOK" localhost:8092/api/admin/stats` (×3, note the max).
3. Snapshot for rollback: `cp frontend/admin.html /tmp/admin-classic-2026-09-27.html`.
4. Baseline test run: `cd backend && DASHSCOPE_API_KEY=test-key .venv/bin/pytest -q | tail -3` → record pass count.
5. Verify `bump_versions.py` covers `.css`/`.js`: `grep -n "rglob\|glob" frontend/bump_versions.py`.

### Fas 1 — Backend aggregation (~2–3 h)
1. `_revenue_breakdown(ledger)` in `main.py` next to `_ledger_totals` → `by_product`, `by_month`, `customers[]`, `churn_by_day`. Product map (label + whether it is live):
   `unlock10` (current), `donation`, `patron500`, `lifetime`, `tier1`/`tier2` (legacy subs), `renewal`.
   Admin-granted tiers must stay OUT of revenue (guard from `test_mrr_ignores_admintier_without_payment`).
2. `_admin_overview(window)` → the 2.1 payload, reusing `_user_stat_row`, `_ledger_totals`, `iplog.visits_summary`, `api_daily`.
3. `GET /api/admin/overview` route with `_require_admin` + `window` validation (`all` default).
4. Extend `admin_billing()` (2.2) and `admin_user_detail()` (2.3) — additive keys only.
5. Tests `backend/tests/test_admin_overview.py` (new, 10–14 cases): fixture repoints `users_file` + `ledger_file` to tmp (NEVER real data); assert by_product sums == `total`; assert month_revenue uses Europe/Stockholm; assert unlabelled models land in one bucket; assert window filter changes only windowed keys.
6. Verify: `cd backend && DASHSCOPE_API_KEY=test-key .venv/bin/pytest -q tests/test_admin_overview.py tests/test_billing_admin.py` → all green, plus the full suite at the end of the wave.

### Fas 2 — Shell + design system + router + Revenue view (vertical slice, ~4–5 h)
1. `frontend/admin.css`: tokens, layout grid, cards, KPI tiles, tables, chips, drawer, chart primitives, light theme.
2. `frontend/admin.html`: header (brand, scope bar, refresh, theme toggle, "⚔ To the Table", Log out), sidebar, `<main id="view">`; still loads `api.js` + `i18n.js`, **not** `snes.css`/`rail.js`.
3. `frontend/admin.js`: `route()` (hash parse → view render), `api()` wrapper keeping `credentials:'include'` + 401 → login, toast helper, `fmtSek/fmtNum/fmtTokens/fmtPct`.
4. Chart helpers in SVG: `lineChart({series,bands})`, `barChart`, `donut`, `sparkline`, `hBarList` — all resolve colours via `getComputedStyle(document.documentElement).getPropertyValue(...)` (never `var()` inside SVG attributes).
5. Revenue view end-to-end: 6 KPI tiles → product donut → timeline (day/week/month) → ledger table (sortable, filterable) → customer list by LTV; **every** element opens the drawer.
6. Verify: `python3 -c "import re;src=open('frontend/admin.html').read();open('/tmp/a.js','w').write('\n'.join(re.findall(r'<script>(.*?)</script>',src,re.S)))" && node --check /tmp/a.js && node --check frontend/admin.js`; then serve `frontend/` with `python3 -m http.server 8899`, override `window.fetch` with mock payloads, and drive the view in the browser console.

### Fas 3 — Remaining views + dossier (~4–6 h)
1. **Players:** keep the 18-column table, filters, 10/page pagination and mobile cards (all of it
   currently works — port it, do not simplify it away), plus row → dossier drawer:
   Summary / Usage / Revenue / Campaigns tabs, quick actions wired to the existing fetch bodies.
2. **Usage:** model list (calls|tokens toggle) → drawer with that model's per-day series;
   provider donut; TTS minutes + image counts.
3. **Traffic:** visits/uniques per day, referrers, country breakdown with the window selector
   (reuse `/api/admin/visits_country`).
4. **Overview:** KPI band (money + value pairs) + AI-calls line + turns-per-day line + action-mix donut
   + tier donut + top models + recent transactions.
5. **Feedback:** port the inbox + window/sender chips, restyled.
6. `frontend/admin-actions.js`: move every mutation out of `admin.html`'s inline script byte-identical
   (fetch URL, method, body keys, `credentials:'include'`), then re-grep that 100 % of the old
   `onclick` handler names still exist somewhere in `frontend/admin*.js`.

### Fas 4 — Polish, QA, deploy gate (~3 h)
1. Empty states ("no revenue yet — the ledger is quiet"), skeletons while loading, error state with the raw HTTP status (canon: surface the underlying error, `references/error-display-and-dark-archetypes`).
2. CSV export per panel (client-side Blob) + `⌘K`-style quick jump to a player/model/product.
3. A11y: focus-visible rings, drawer focus trap, `aria-current` on nav, chart data also present as a table/tooltip, contrast measured (not guessed) on the final palettes.
4. Mobile ≤640 px: sidebar collapses to a bottom tab bar; table → cards (existing pattern).
5. **Revenue drill-down completeness check:** each of product / country / date / transaction drill-downs
   must end in the same list of ledger rows, and the four sums must each reconcile to `total`.
6. **QA battery (parent runs it, not a subagent):** `scripts/qa_run.py` against the container with an admin cookie — desktop/tablet/mobile × all six views, zero console errors, zero horizontal overflow, screenshots cropped per region for vision review (whole-page shots are noisy: `references/design-direction-preview-workflow`).
7. **Deploy only after rostad's explicit OK:** `tools/deploy-frontend.sh` (or `bump_versions.py admin.css=… admin.js=…` + `docker compose build && up -d`), md5 repo == container, `curl -I` 200 on `/admin.html`. Commit is a SEPARATE, later action — he asked for no commit yet.

---

## 5. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Admin mutations break during the rewrite (cap/tier/role/delete) | Port fetch bodies byte-identical, grep every old handler name survives, then click each action once in the browser |
| Revenue math duplicated in JS and drifting from the ledger | Server sends every money number; JS only formats. Assert `by_product` sums == `total` in a test |
| `_scan_user_transcripts` × 159 users makes the page slow | Fas 0 measures it; add a TTL cache (`admin_stats_cache.json`, 60 s) only if >1.5 s |
| Removing `snes.css` silently kills styles/JS hooks used by other admin code | Grep `snes` usage before deleting the `<link>`; the page must not depend on game classes |
| Deep links + Back button break | Hash router only, no `history.pushState` paths; test reload on 6 deep links |
| Stale frontend in the container (frontend is baked into the image) | `bump_versions.py` for `admin.css`/`admin.js`, `docker cp` for a quick smoke, md5 diff before declaring victory |
| Old bookmarks/`admin.html` expectations | `/admin.html` keeps its path; the classic page is preserved at `/tmp/admin-classic-2026-09-27.html` until a week of clean use |

---

## 6. Beslut från rostad (2026-09-27) — frågorna är stängda

1. **Ersätt helt.** Admin v2 tar över `/admin.html`; ingenting ska påminna om den gamla vyn — gammal
   markup/CSS/JS raderas (ingen `/admin-classic.html`, ingen dold gammal flik).
2. **Värde bredvid pengarna.** Turns/tokens/calls-utfallet visas parallellt med intäkten, både i
   Overview-bandet och i Revenue-vyn.
3. **Mörkt tema som default.** (Ljust tema behålls som toggle — det kostar inget och skadar inte.)
4. **Ingen churn, inga prenumerationer.** Revenue-vyn drillar i fyra dimensioner: produkt, land, datum,
   transaktioner. Legacyprenumerationsrader syns bara som transaktioner.
5. **Språk:** admin-sidan förblir engelsk (kanon sedan tidigare; inget motsatt beslut fattades).

---

## ✅ Levererad (2026-09-27 22:15) — inne i containern, inget committat

| Fas | Vad | Status |
|---|---|---|
| 1 | Backend (additivt): `/api/admin/overview`, `by_country[].users`, `_value_delivered` (`turns_day`, `by_action`), `series.turns_day` | ✅ **live** — containern omstartad 22:07 (0,98 s, healthy efter 3 s), inga importfel i loggen |
| 2 | Frontend: `admin.html` (skal) + `admin.css` + `admin.js` + `admin-actions.js` | ✅ **live** — gamla 2 660-radersvyn ersatt; `admin-v2.html` borttagen; designskssen flyttad till `docs/design/preview-admin-v2-2026-09-27.html` |
| 3 | Verifiering | ✅ 101/101 DOM-kontroller mot riktiga payloads · 224/224 kontrastpar + 2 059 renderade textelement, 0 fel · 18/18 + **712/712** backend-tester · 12 headless-renderingar, alla vyer granskade |
| 4 | Städning | ✅ 14 falska testkonton (`ip="testclient"`) borttagna ur `backend/data/ip_geo.json` (kopia: `~/.hermes/cache/scratch/deploy-20260927/ip_geo.json.bak`) + autouse-fixture i `tests/conftest.py` som pekar om geo-/besökscachen för **alla** testmoduler |

**Ordning som gäller vid städning av en körande cache:** `docker stop` → redigera filen → `docker start`,
annars skriver den körande processen tillbaka sin in-memory-kopia vid nästa besök.

**Live-verifierat efter deploy** (admin-token, samma endpoint som dashboarden läser):
`value.by_action = {dm 636, tts 165, image 60, undo 42, char_gen 3, logbook 1}` ·
`series.turns_day` 27 dagar · `by_country` DE 139 [andreasmaurel], GB 70 [chup], SE 44 [nomis] ·
253 kr · 4 ledger-rader · 3 betalare · 907 turns / 14,07 M tokens i 30-dagarsfönstret · 3,86 kr per 1M tokens.
