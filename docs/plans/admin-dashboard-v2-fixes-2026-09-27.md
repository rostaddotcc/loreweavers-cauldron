# Admin Dashboard v2 — diagnos & åtgärdsplan "loose ends" (2026-09-27)

> Underlag: live-payloadar från containern (`/api/admin/overview?window=all|30d|7d|24h`,
> `/api/admin/billing`, `/api/admin/feedback`, `/api/admin/user/{u}`, `/api/admin/visits_country`)
> + genomläsning av `frontend/admin.js` (1210 rader), `frontend/admin.html`, `backend/main.py`,
> `backend/iplog.py`. Alla siffror nedan kommer från riktiga anrop, inget antagande.

## 1. Vad rostad bad om

1. Kolla att **drilldowns** fungerar (och syns).
2. Kolla att **samtliga traffic-referrals syns**.
3. Kolla att **modellanrop per spelare** går att se.
4. Gå igenom övriga **loose ends**.
5. Diagnos → plan → genomför.

## 2. Diagnos — vad som faktiskt är trasigt

### 2.1 Traffic: referrers (rostads punkt 2 — bekräftat trasig)

| Fakta | Värde |
|---|---|
| Källor i payloaden (`traffic.referrers`) | **24** |
| Källor som renderas | **8** (`Object.keys(referrers).slice(0, 8)`, admin.js:528) |
| Osynliga källor | 16 — t.ex. `rostadexe.itch.io` 14, `producthunt.com` 5, `LinkedIn` 4, `Bing` 4, `duckduckgo` 2, `github.com` 2, `rollspel.nu` 1, `checkout.stripe.com` 1 |
| Sortering | ingen i frontend (förlitar sig på payloadens insättningsordning) |
| Klickbarhet | **ingen** — `hbars()` i "Top referrers" har ingen `data-drill`; klick gör ingenting |
| Semantik i UI | "Top referrers" utan att säga att talet = **unika besökare per källa** (iplog räknar `len(ips)`) |

Dessutom: `traffic.by_country` skickas som **dict** `{cc: n}` men klickhanteraren (admin.js:1058)
testar `(TRAF().by_country || []).some(...)` → på en dict är `.some` `undefined` → **klick på
ett land i Traffic är en död klick** (faller igenom till `return`). Länder är dessutom kapade
till 10 av 79 (`items.slice(0, 10)`).

### 2.2 Traffic: besöksserien ljuger om fönstret

`iplog.visits_summary()` kapar `by_day` och `by_day_unique` till **de senaste 14 dagarna**
(iplog.py:371-376) medan `visits.json` har 32 dagar. Med `window=all` eller `30d` visar grafen
"window all" ändå bara 14 staplar — ingen notis i UI. Dessutom:

- `uniques.today / 7d / total` beräknas i backend men **skickas inte med** i overview-payloaden.
- Overview-KPI:n **"Unique visitors"** visar `sum(series.visits_day)` = **antal request**, inte
  unika besökare. Fel etikett på rätt tal (och `visits_day` är antal besök, `by_day_unique` är unika IP:n).

### 2.3 Usage: modelldrilldown är en återvändsgränd (rostads punkt 3)

- `drawerModel()` läser `USAGE().models_day[key]` (admin.js:709) — **nyckeln finns inte**:
  `_usage_breakdown()` returnerar bara `providers` + `models`. Backend producerar aldrig
  `models_day`. Varje modellklick visar därför fallback-texten "This payload carries the per-day
  series only for the models the backend tracks individually…" i stället för en kurva.
- **Det går inte att se vilka spelare som anropat en modell.** Ingen endpoint, ingen vy.
  Modell→spelare är alltså omöjligt i dag; spelare→modell finns bara i dossiéns Usage-flik.
- Spelaredossiéns modellista kapas till 8 (`mix.slice(0, 8)`, admin.js:827) och visar bara anrop,
  inte tokens — och raderna är inte klickbara.
- `model_mix` innehåller pseudo-modeller: `undo-voided` (chup, 20 "calls") räknas som modell.

### 2.4 Drilldowns: halvfärdigt routerspår

Planen (§2, §3) lovade hash-router med djup­länkar och **Back-knappen**:
`#/revenue/product/unlock10`, `#/usage/model/step-3-7-flash`, "deep links must survive a reload".
Verkligheten: `history.replaceState(null,'','#'+S.view+'?w='+S.win)` (admin.js:978).
Ingen `pushState`, ingen `popstate`-lyssnare, ingen drawer-state i hashen, ingen parsning av
`#view/kind/key`. Back-knappen lämnar admin-sidan, och en drilldown kan inte delas eller
återladdas. (Positivt: `#players?w=7d`-formad länk fungerar vid kallstart.)

### 2.5 Döda eller missvisande klick

| Element | Vad som händer |
|---|---|
| Land-stapel i Traffic | ingen lyssnare (dict/some-buggen) |
| Referrer-stapel | ingen lyssnare |
| Donut-slice "What the turns bought" (Overview/Revenue) | alla action-slices öppnar samma generiska `drawerValue()` — klicket ignorerar vilken slice som valdes |
| "Peak day"-KPI (Traffic) | ingen drill alls |
| KPI `drill:'usage:calls' / 'traffic' / 'players'` | fungerar, men etiketten "drill down →" lovar en postlista; de byter bara vy |
| Modell-stapel i Usage | öppnar en drawer som per konstruktion saknar innehåll (2.3) |

### 2.6 Övriga loose ends

1. **System-panelen dokumenterar `/api/admin/visits_country`** som "geo windows" — endpointen
   anropas **aldrig** av admin.js. Antingen koppla in den eller ta bort raden (nu är panelen en osanning).
2. `usage.models` blandar LLM- och mediamodeller; TTS/bild har `tokens: 0` → "Token share by
   provider" kan visa "—" för modeller som ändå listas. Ingen förklaring i UI:t.
3. Ingen CSV för referrers/länder (endast `visits_day`, 14 dagar).
4. Drawer saknar fokusfälla (`aria-modal` finns inte; Tab går ut i sidan bakom) — planens Fas 4.3.
5. `S.billing` hämtas alltid men används bara för `ledger`; `REV().ledger` finns inte i payloaden
   → `ledgerRows()` faller tillbaka på `[]` tills billing landat (första målningen kan visa
   "No transactions yet" i en sekund).
6. `drawerDay()` är död kod (alias till `drawerBucket`, anropas aldrig).
7. `show all`-mönstret saknas helt: alla långa listor kapas tyst (8 referrers, 10 länder,
   6 modeller, 8 modellmix, 40 tiers) utan "visa alla".

## 3. Åtgärdsplan

### Fas A — backend (additivt, inga brytande ändringar)
- **A1** `_scan_user_transcripts`: ny aggregering `model_daily` = `{modell: {dag: anrop}}`
  (poster utan tidsstämpel placeras inte, samma regel som `daily`).
- **A2** `iplog.visits_summary(country_range, days=14)`: parametriserad dagkapa + skicka med
  `by_day_unique` och `uniques {total, today, last_7, last_14}`.
- **A3** `iplog.referrer_detail(cutoff)`: per källa → `{uniques, countries:{cc:n}, first_seen, last_seen}`
  ur `by_referrer` + geo-cachen (cache-läsning, aldrig nätverk i requesten).
- **A4** Ny route `GET /api/admin/model/{model}?window=` → `{model, provider, calls, tokens, day:{},
  users:[{username, calls, tokens, country_code, flag, country, revenue, last_active, campaigns}],
  windowed, media_only}`. Enda vägen till modell→spelare och modellens kurva.
- **A5** `/api/admin/overview`: `traffic.uniques`, `traffic.by_day_unique` (fönstrade),
  `traffic.referrer_detail`, `series.visits_unique_day`; `visits_summary(days=400)` så grafen
  täcker hela fönstret.
- **A6** Tester: `tests/test_admin_overview.py` + nya fall för modell-endpointen, referrer-detaljen
  och att `by_day` inte längre kapas i overview (men är oförändrat 14 för gamla anropare).

### Fas B — frontend (`frontend/admin.js` + minimala `admin.css`-tillägg)
- **B1** Traffic-vyn görs om: alla referrers (sorterade, andel i %), alla länder (scrollbart),
  klickbara → drawer med unika besökare, andel, länder (för referrer) / källor (för land),
  first/last seen. KPI-raden: Visits / Unique visitors (riktigt tal) / Peak day / Countries resolved.
  Seg-väljare Requests | Unique visitors på dagsgrafen. CSV för båda listorna.
- **B2** `drawerModel()` → hämtar `/api/admin/model/{key}`, visar dagskurva + tabell "who called it"
  med klickbara spelarrader → dossié.
- **B3** Spelaredossiéns Usage-flik: modelltabell (anrop, tokens, andel) i stället för 8 kapade staplar,
  klickbar → modelldrawer.
- **B4** Riktig hash-router: `#view?w=<win>&d=<kind>&k=<key>` med `pushState` + `popstate`;
  Back stänger drawer / går tillbaka i historiken; djup­länk öppnar rätt drawer vid kallstart.
- **B5** Städa döda/missvisande klick: land- och referrer-staplar får lyssnare, actionslices
  öppnar rätt drawer, "Peak day" får drill, `usage:calls`-KPI etiketteras ärligt.
- **B6** System-panelen: endpointlistan uppdateras till det som faktiskt anropas (inkl. den nya
  modell-endpointen och visits_country som nu används).
- **B7** Drawer: fokusfälla + `aria-modal`, fokus tillbaka till utlösaren vid stängning.
- **B8** "Show all"-mönster (`.list-scroll` + `Show all N / Show top N`) i stället för tyst kapning.
- **B9** Ta bort död kod (`drawerDay`), rätta ledger-fallbacken så första målningen inte visar
  "No transactions yet" medan billing hämtas.

### Fas C — verifiering
- **C1** jsdom-harnessen (`qa/jsdom-check/v2run-real.cjs`) uppdateras: den motar `admin.html` (inte
  `admin-v2.html`), får färska fixturer från containern och nya kontroller för varje åtgärd ovan
  (referrer-antalen = payloadens 24, modellendpointen anropas, djup­länk öppnar drawer, inga döda klick).
- **C2** Backend: hela pytest-sviten + de nya testerna.
- **C3** CDP-rendering på bot-desktop (Xvfb :20) av Traffic/Usage/dossier/mobilläge → pixelgranskning.
- **C4** Deploy till containern (`bump_versions.py` + build/up), md5-repo == container, `curl -I` 200.
  **Ingen commit** (rostads stående regel).

## 4. Utanför denna våg (medvetet)

- Ingen historisk backfill av referrer-per-dag (kan inte rekonstrueras ur `by_referrer`; endast
  first/last seen finns). UI:t säger det rakt ut i stället för att gissa.
- Ingen churn/prenumerationsvy (ägarbeslut 2026-09-27 §6.4).
- Ingen CSS-omdesign: bara tillägg för lista/scroll/drawer-markup.

## 5. Genomfört (2026-09-27, kväll) — avvikelser och bevis

Alla fyra punkter i diagnosen är åtgärdade och verifierade. Det som avvek från planen
och det som tillkom under arbetet:

### Extra fynd som inte stod i diagnosen (hittade under implementationen)

1. **`Copy ids`-knappen i ledger-drawern var kapad av routern.** Knappen bar `data-ref`
   (stripe-/event-id) men `data-ref` betyder "öppna referrer-drawern", och den grenen
   läses FÖRE `data-act`. Klick öppnade alltså en påhittad referrer-drawer i stället för
   att kopiera id:na. → attributet heter nu `data-copyref`.
2. **`known`-flaggan ljög om riktiga modeller.** `/api/admin/model/qwen3.8-max` svarade
   `known: false` (291 anrop, 20 spelare) eftersom modellen är pinnad för tunga körningar
   och aldrig står i `MODELS`. → `known` är nu "registrerad ELLER media ELLER provider
   kunde attribueras", plus egna flaggor `registered`/`media` så UI:t kan säga
   "not in the active registry" i stället för "okänd".
3. **`data-slicekey` sattes men lästes aldrig** — slice-fallbacken gissade på legendtexten.
   → läses nu (modell/tier/action/produkt/land via nyckel).
4. **Fler tysta kapningar i drawer-marker:** land-drawerns källista kapades till 12,
   referrer-drawerns länder till 12, spelardossiéns turn-actions till 10, overviewns
   action-donut till 6, land-drawerns kontolista till 40 utan notis. → alla listor är
   kompletta och skrollbara; kontolistan får en notis när den visar första 40.
5. **Drawer-historiken staplades per steg** (spelare → modell → …) så Back gick till
   föregående drawer i stället för ut ur drawer-lagret. → en historikpost per
   drawer-session (replaceState vid djupare steg).

### Bevis

- **Backend-tester:** `backend/tests/test_admin_overview.py` — 30 passed (varav 14 nya:
  referrer_detail komplett/fönstrad/legacy, `days`-parametern, unika-vs-requests,
  traffic-payloaden, visits_country, modellendpointens kurva+spelare, okänd modell,
  mediamodell utan dagserie, `registered`/`media`, 403/400).
- **Frontend (jsdom mot RIKTIGA payloadar** från `backend/data`, nya backendkoden):
  `qa/jsdom-check/v3run-real.cjs` 65 passed / 0 failed (drilldowns, referrer-antal ==
  payloadens 24, show-all, Back-knappen stänger utan extra historikpost, Copy ids,
  fokus, inga JS-fel).
  `qa/jsdom-check/v3deeplink.cjs` 22 passed / 0 failed (kallstartad delad länk för
  varje drawertyp: model, player+tabs, referrer, geo, day, tier, action, value,
  product, tx, bucket, country, bogus-länkar).
- **Deploy:** compose-bygge + `tools/deploy-frontend.sh`, md5 jämförd mot containern,
  admin-endpoints svarar 200 med admin-cookie.
- **Ingen commit** (rostads stående regel).
