# Dashboardens datakomplethet — analys + patch-plan (2026-09-28, kväll)

> Loop-pass 1. Underlag: **skarp data** i containern (`loreweavers-cauldron`, upp 20 h,
> `main` = `000dff9`) läst READ-ONLY via backendens egna funktioner, plus statisk
> genomgång av `frontend/admin.js` (2 115 rader). Inget skrivet i prod av det här passet.

## 1. Vad jag mätte (facit att verifiera mot)

| Mätning | Värde | Kommentar |
|---|---|---|
| Konton | 159 | alla med `turn_cap = 30` |
| `promo_bonus > 0` | **0** | promo borttagen ur modellen (`d813317`) |
| `turn_bonus > 0` | **3** | chup 396 · andreasmaurel 300 · nomis 289 |
| Kodning live | **free 156 · paid 3 · granted 0** | `granted`-ytan är nu alltid tom |
| Obegränsade konton (`cap 0`) | **0** | ∞-grenarna kan aldrig träffas |
| Grant-ledger | 10 rader, alla `opening_balance`, 1 048 turns | **7 av 10 har 0 turns** |
| Turn-ledger | 2 052 rader, 2026-08-07 → 2026-09-28 | unknown 1 918 · paid 63 · free 71 |
| Senaste dygnet (lokal dag) | free 71 · paid 63 · **unknown 7** | se fynd B |
| `turns_used_unknown_total` vs ledgern | **0 avvikelser** av 159 | invarianterna håller |
| `pott == _turns_available()` | **0 brott** av 159 | den server-side sanningen står |
| `last_active` saknas | **54 av 159 (34 %)** | tomt dygn, tom kolumn |
| `pool_data_since` | 132 satta · 27 utan (alla utan historik) | ärlighetsgränsen är korrekt satt |

## 2. Fynd, rankade efter hur mycket de stör läsningen

**A. Hela "granted"-benet är tomt — men ytan finns kvar.**
Kod-donuten har en slice, chip-filtret en knapp, `drawerCode` en sektion, `CODE_LABEL`
en etikett — för **0 konton**. Klickar man får man tomt. (`admin.js` ~500-560, 2011-2050.)

**B. Den staplade grafen visar "legacy/unknown" inpå dagens stapel.**
`turns_by_bucket_day` bucketeras på **lokal dag** (`_day_key`, Europe/Stockholm,
`backend/main.py:11427`), medan turn-gaten och "fri kvot i dag" räknar **UTC-dygn**.
Ledgern fick hinkar först när nya koden gick live **2026-09-27 22:58 UTC** — de 7 rader
som skrevs 22:00–22:58 UTC hamnar därför på *28:e* i den lokala serien och ser ut som
legacy-turns i dag. Facit: serie 28:e = free 71 + paid 63 + unknown 7 = 141, medan
ledgern på UTC-dygnet har 127 rader. Samma tal, två dagsgränser → ser fel ut i ett svep.

**C. 7 grant-rader med 0 turns renderas som riktiga paket.**
`scripts/remove_intro_startbonus_2026-09-28.py` (f684687) skulle skriva om dem till
`expired_intro` med turns=0; live-filen har dem kvar som **`opening_balance`** med
turns=0 (`left_after=0`, `pool_after=0`). `grantsTable()` (`admin.js:1304`) listar dem
som "Purchases and grants · 0 turns in 1 row" — ett paket som ser bokfört ut men är tomt.

**D. "Köpt" går inte att belägga för de tre som faktiskt betalat.**
Grant-ledgern innehåller bara `opening_balance` (källan som med flit räknas som *okänt*),
medan `_billing_ledger.json` har riktiga betalningar (chup 70 kr m.fl.). Dashboarden
säger därför "buy unknown before 2026-09-28" för en spelare vars betalning finns på
papper. Ingen rad ljuger — men uppgiften "hur mycket har spelaren köpt" är fortfarande
obesvarad för alla utom de 3 som har saldo.

**E. "Promo / legacy"-raden och ∞-grenarna är strukturellt döda.**
0 konton har promo kvar, 0 ledger-rader har `bucket: promo`, 0 konton är obegränsade.
Ändå finns: Promo-raden i `poolBreakdown` (`admin.js:1288`), promo i legend/serie
(`POOL_PARTS`), `promo_left` i CSV, ∞-texten i `poolLines`/`poolBreakdown`, ∞-sortering i
`sortVal`, `poolSum`-undantaget och "Unlimited accounts"-blocket i den aggregerade
pott-drawern. Motsatsen till "rena siffror": fem ytor som alltid visar 0 eller aldrig syns.

**F. Fyra nyckeltal är återvändsgränder (drilldown saknas).**
| Yta | Vad man vill kunna göra |
|---|---|
| `bucketSplit`-barrarna (free/paid/promo/legacy) | klicka hinken → **vilka turns var det** (ledger-rader, konto, dag, action) |
| `grantsTable`-raderna | klicka ett paket → raden i ledgern + spelarens förbrukning efteråt |
| "Spent"-cellen i Players (`admin.js:780`) | klicka → hink-uppdelningen för det kontot |
| `poolBreakdown`-tabellens rader | klicka en hink-rad → samma ledger-vy som ovan |
Död kod i samma veva: `data-peak` finns i klick-delegationen (`admin.js:1838`) men
renderas ingenstans.

**G. En tredjedel av spelarna har ingen aktivitetsstämpel.**
`last_active` saknas för 54 konton → tom cell i Players och bortfiltrerade ur "Recently
active" (notisen räknar dem, men cellen är bara tom). "Tomt" läses som "nyss" eller "0".

**H. Ledgern beskärs vid 2 000 rader** (`_TURN_LEDGER_KEEP`), nu 2 052 rader totalt.
Hink-serien och dag-grafen tappar därför äldre dagar bakåt, medan `used_lifetime` i
users.json står kvar. "Used in total" och grafen kommer att glida isär — värt en notis i
UI:t *innan* någon upptäcker det som en bugg.

## 3. Vågor (fil-/radankare, tester, risk)

**P1 — Städa de döda ytorna (liten, ingen risk).**
Visa bara hinkar/koder/cap-lägen som finns i datat: Promo-raden och promo-serien ritas
bara när `promo_left + used_lifetime.promo > 0` (`admin.js:1288`, `POOL_PARTS`), Code-chippen
"Granted" blir disabled med räknaren 0 i stället för en tom träffyta, ∞-grenarna behålls
men får en kommentar om att de är tillfälligt overksamma (de behövs om en cap-0-kund
kommer tillbaka), `data-peak` tas bort ur delegationen. Test: jsdom-assertion att
Promo-raden inte finns när promo är 0 och att legendens summa == `pool_totals.available`.

**P2 — Sätt dagsgränsen på ett ställe (medelrisk, rör serien).**
`turns_by_bucket_day` bucketeras i UTC-dagar som gaten, **eller** märks tydligt "local
day" i både KPI och graf. Inför `BUCKET_TRACKING_SINCE_TS = "2026-09-27T22:58:00+00:00"`
och lägg rader före den i `legacy` (egen nyckel, egen notis) så dagens stapel slutar
visa legacy. Test: `sum(turns_by_bucket_day[d]) == turns_day[d]` för varje dag, och
antalet `legacy` == antal ledger-rader före tidsstämpeln.

**P3 — Gör "köpt" så sant som möjligt (rör data, kräver ditt OK).**
Rekonciliera de 3 betalarna mot `_billing_ledger.json`: deras `opening_balance`-rad får
`source: opening_balance:payer` + belopp/datum från betalningsloggen (aldrig påhittat
antal turns), så UI:t kan skriva "bought before tracking started — 70 kr on record
2026-08-27" i stället för "buy unknown". De 7 tomma raderna skrivs om till
`expired_intro` (som det committed skriptet avsåg) och `grantsTable` filtrerar bort
rader med 0 turns ur UI:t men behåller dem i API:t som revisionsspår.

**P4 — Fyra drilldowns (störst nytta per rad).**
Ny drawer `bucket:<konto|all>:<hink>` (+ `:dag`) som listar ledger-raderna i hinken med
`ts · action · model · pool_after`, kopplad från `bucketSplit`-barrarna,
`poolBreakdown`-raderna och "Spent"-cellen; `grant:<ts>` som öppnar paketet + de rader
som förbrukats efter `left_after`. Samma hash-state-mönster som `openByState`
(`admin.js:1783`), så djuplänkar fungerar. Test: jsdom klickar baren → drawer med rätt
antal rader; `hex`-routing fram och tillbaka.

**P5 — Ärliga tomrum (litet).**
`last_active` tom → "never played" i cellen och i recency-notisen (räkningen finns
redan); notis i `drawerValue` om att hink-serien bara täcker de senaste 2 000 raderna
medan `used_lifetime` är livstid.

## 4. Öppna beslut (behöver din rad innan P1-P3)

1. **Granted-koden:** döljs när den är 0, eller ska koden bort helt (då försvinner även
   framtida grants ur flödet)? Jag lutar mot att behålla regeln och bara dölja ytan.
2. **"Köpt" för betalare:** räcker *belopp + datum från betalningsloggen* som "belagt",
   eller ska vi stanna vid "okänt före tracking" tills ett riktigt köp loggas framåt?
3. **Dagsgräns:** ska den staplade grafen följa gaten (UTC) eller fortsätta vara lokal
   dag — och ska "fri kvot i dag" i så fall etiketteras med tidszonen?
4. **Tomma grant-rader:** omskrivning till `expired_intro` (rekommenderas, spåret finns)
   eller arkivering till en `.trash`-fil?
5. **`last_active`:** "never played" i cellen, eller filtrera bort konton utan stämpel
   helt i Players (som recency-kortet gör)?

## 5. Verifieringsfacit för passet

- `pott == _turns_available()` för **159/159** konton (0 brott) — ingen ny källa får bryta det.
- `turns_used_unknown_total` == ledgerns hinklösa rader för **159/159** konton.
- `sum(turns_by_bucket_day[d]) == turns_day[d]` för varje dag, efter P2.
- Code-chippens räknare == `coding_summary` == `ftot`-raden == CSV:n.
- jsdom-harnesset (`~/.hermes/cache/scratch/qa/qa_dashboard.js`) utökas med: Promo-raden
  borta vid 0, bucket-bar → drawer, grant-rad → drawer, Spent-cell → drawer.

---

## 6. Pass 2 (loop-varv 2) — fält som finns men aldrig når en yta

Mätt mot skarp data + statisk läsning av `admin.js` (2 115 rader). Alla fyra är
"ofullständig dashboard", inte "ofullständig data" — siffrorna finns redan server-side.

**O1 — Ledger-drawern visar inte dagens hinkar.** `/api/admin/user/{u}/ledger` returnerar
`entries`, `breakdown_all`, `breakdown_today`, `by_bucket`, `by_bucket_today` — UI:t läser
bara `entries` (+ all-time-breakdownen). Facit för chup i dag: **free 71 · paid 56 ·
unknown 0** (`by_bucket_today`) medan all-time är free 71 · paid 63 · unknown 308.
→ **P4a (ren frontend, ingen backend-ändring):** visa "Which bucket paid · today" i
ledger-drawern och gör hink-barrarna klickbara så de filtrerar `entries` (klient-side,
samma mönster som bucketSplit i dossién). Högst nytta/lägst risk av allt kvar.

**O2 — Dossién skickar ledgern i tre former, ingen av dem läses.**
`turn_ledger` (breakdown), `turn_ledger_today` och `turn_ledger_recent` (upp till 50
hela rader) — 0 träffar i `admin.js`. Uppmätt: **6,8 kB per dossier** för chup
(2,4 kB för adam); den senaste ledgern hämtas ändå separat av `drawerLedger`.
→ **P6a:** ta bort `turn_ledger_recent` ur dossién (dubbelarbete i varje dossier-anrop).
`turn_ledger_today` är den enda av de tre som tillför något — använd den i Usage-fliken
**eller** stryk den, inte båda.

**O3 — Den kompakta raden bär 15 fält som ingen yta läser.**
`turn_bonus`, `promo_bonus`, `turn_cap`, `turns_available`, `period_turns_used`,
`cap_until`, `features_until`, `stripe_customer_id`, `model_tokens`, `image_gen_calls`,
`tts_calls`, `tts_minutes`, `tts_seconds`, `tts_chars`, `char_creation_calls` (0 träffar
i `admin.js`; de råa kvotfälten är ersatta av `turn_pool`).
Två av dem är faktiskt intressanta för en admin: **vem använder TTS och bildgenerering**
(dyra funktioner) — data finns per spelare men syns bara i dossién, aldrig i Players-tabellen.
`stripe_customer_id` bör **inte** gå till klienten alls.
→ **P6b:** antingen en "Extras"-kolumn i Players (tts_minutes + image_gen_calls, sorterbar)
eller stryk fälten ur overview-payloaden; `stripe_customer_id` bort oavsett.

**O4 — `ip` skickas i dossién men visas ingenstans.** `ip` finns i svaret (0 träffar i
`admin.js`), liksom `country`/`country_code`/`country_flag` som *visas*. Skicka inte
personlig data som ingen yta renderar → visa IP:n i dossién (admin-verktyg) eller stryk den.

**O5 — Mobilkortet är tunnare än tabellen.** `mobCard` visar `codeTag`, `poolText`,
`poolBar`, `used_lifetime`, `spent`, `revenue` — men **inte `last_active`** och inte de
radvisa pottdetaljerna (`poolLines`) som desktop-kolumnen har.
→ **P1b:** samma `poolLines` + relativ "last seen" på mobilkortet, så mobilen säger exakt
samma sak som tabellen.

### Uppdaterad vågordning efter pass 2

| Våg | Innehåll | Risk |
|---|---|---|
| P1 | döda ytor (promo/granted/∞) bort | liten |
| **P1b** | mobilparitet (`poolLines` + last seen) | liten |
| P2 | dagsgräns (UTC vs lokal) + `legacy`-nyckel | medel |
| P3 | grant-sanning (betalarnas belopp + `expired_intro`) | rör data — **kräver ditt OK** |
| P4 | bucket-drilldown (bucketSplit-rader, grant-rader, Spent-cell, poolBreakdown) | medel |
| **P4a** | ledger-drawern: dagens hinkar + klickbara barrar | **liten, ingen backend-ändring → kan köras först** |
| P5 | ärliga tomrum (never played, 2 000-radersnotis) | liten |
| **P6** | payload-hygien (O2-O4): bort med oläst, ev. "Extras"-kolumn | liten/medel |

---

## 7. Pass 3 (loop-varv 3) — varför token-siffrorna aldrig kan summera

Value-vyns `tokens` / `ai_calls` byggs av **tre olika källor**, varav bara en är daterad:

| Källa | Daterad? | Var |
|---|---|---|
| Transkript-poster (`meta.tokens` + `guardian_pre_dm_tokens`) | **ja** — hela `daily` | `campaigns/<user>/<cid>/transcripts/*.jsonl` |
| `state.meta.unguarded_tokens` (bakgrundsanrop: extraktion, sammanfattningar, dag-entries, Battle AI) | **nej** — ren livstidsräknare | `campaigns/<user>/<cid>/state.json` |
| Raderade kampanjers ackumulator (`_add_deleted_campaign`) | **nej** — ren livstidsräknare | `backend/data/*deleted*` via `_scan_user_transcripts` |

**Uppmätt (read-only, skarp data):**
- Livstid **70 407 061** tokens · i den daterade dagboken **49 908 590** → **70,9 %** daterat.
- Diffen förklaras *exakt*: chup 1 780 387 == unguarded ✓, adam 119 413 == unguarded ✓.
- **12 av 159 konton** bär raderade kampanjer: **11 188 578 tokens**. Störst: euana 3 566 581
  (77 turns), sineval 3 436 094, admin 2 953 177.
- Diffen för just de kontona == raderade kampanjer på decimalen: admin 2 953 177 ==
  `deleted.total_tokens` 2 953 177 · sineval 3 436 094 == 3 436 094.

**Följd i UI:t:** "tokens"/"ai_calls" blandar tre källor utan att säga det, "Turns delivered
per day" visar bara den daterade delen, och en dag-drilldown på tokens visar en delmängd.
Samma glidning finns på turns-sidan: `turns_day`/KPI:n kommer från ledgern (295 rader för
admin) medan kontots egna `turns` (366) + raderade (113) = 479 — ledgern är *turn-bokföringen*,
inte kontots livstid, och den beskärs dessutom vid 2 000 rader.

**P7a (liten, ingen datamigrering).** Token-KPI:n i Value-vyn får en rad per källa:
`dated 49,9 M · background 0,3 M · deleted campaigns 11,2 M`, med samma notis i dag-grafen
("only transcript-dated calls; background and deleted-campaign usage has no day").

**P7b (medel).** Gör skillnaden synlig i Players/dossién: kontots `turns` (scan + raderade)
vs **ledger rows** (daterade, beskurna) — två tal, två etiketter, en notis om varför de
skiljer sig. Dagens "Turns"-kolumn läser `total_turns` (scan) medan `turns_day`-grafen läser
ledgern.

**P7c — facit att verifiera mot:** `tokens == dated + background + deleted` för varje konto,
och `Σ turns_by_bucket_day == ledgerns rader inom fönstret` (aldrig kontots livstid).
Påverkade konton att kontrollera: euana, sineval, admin, lunny, nomis, pickles, adamkad1, john.

---

## 8. Genomfört: "de ofarliga" (loop-varv 3 → implementation, 2026-09-28)

Rostad: *"kör de ofarliga"*. Vågorna **P1, P1b, P4a, P7a** är byggda, testade och
deployade. Inga siffror i produktionen ändrades — allt är datadrivet (ytan ritas
bara när den har data) eller rent additivt.

### P1 — döda ytor bort (datastyrt, inget borttaget ur modellen)
- **Kod-donuten** (`codeDonut`) ritar bara koder med konton. `keepZero` borttagen;
  `CODE_LABEL` och reglerna finns kvar.
- **Kod-chipen** visar `All 159` / `Paid · 3` / `Free · 156` — bara koder som
  faktiskt har konton, plus den aktivt filtrerade (filtret kan inte försvinna
  under fingrarna).
- **ftot-räknarna** (Paid/Granted/Free) ritas bara när koden är > 0.
- **Staplade legendens** noll-hinkar ritas inte (`poolLegend` filtrerar `value > 0`).
- **Promo-raden** i pottabellen ritas bara när `promo_left || usedPromo`.
- **Aggregerade pott-drawern** döljer Promo-, ∞- och köplogg-raderna när de är 0;
  kod-raden blir `Coding: Free 156`.
- **Död `data-peak`** bort ur delegationen (ingen yta satte den).
- ∞-grenarna, sorteringen och `turn_cap 0`-logiken är kvar (datastyrd, inte död kod).

### P1b — mobilparitet
`mobCard` bär nu samma **radvisa pottdetaljer** som tabellens pott-cell
(`poolLines`: `97/100 free left · 464 paid left`) och **senast aktiv** som
`datum · relativ tid` ("2026-09-28 · 3 h ago"), med "never active" när stämpeln
saknas — samma ärlighet som tabellen.

### P4a — dossiéns ledger-tabell (ren frontend, noll backend-ändring)
- `bucketSplit(turn_ledger_buckets_today, 'today')` bredvid all-time — dagens
  hinkar syntes tidigare bara i pott-drawern.
- **Nytt:** `ledgerBucketTable` listar de ≤200 rader som `/api/admin/user/{u}/ledger`
  redan skickade (tidigare lästes bara `entries.length`): *When · Action · Model ·
  Tokens · Bucket · Pool after*, med **klickbara hink-chips** (`data-ledgerbucket`)
  som filtrerar listan klient-side. Inga nyckeltal räknas i klienten — chipens
  antal kommer ur serverns `bucket`-fält per rad. Fotnoten säger uttryckligen att
  rader före 2026-09-28 är `legacy / unknown`, aldrig gissade till "free".

### P7a — token-siffran märks per källa
- **Backend (additivt):** `_scan_user_transcripts` returnerar `unguarded_tokens`
  (bakgrundsanrop ur `state.meta`), och `_value_delivered` returnerar
  `tokens_sources = {dated, dated_windowed, background, deleted, lifetime}`.
  `dated` = resten av livstiden (`lifetime − background − deleted`), aldrig en
  egen påhittad summa.
- **Frontend:** Value-kortet visar `Dated · transcripts` / `Background calls · no
  date` / `Deleted campaigns · no date` / `Lifetime total` + notisen "only
  transcript calls carry a timestamp … the day series therefore covers the dated
  part only". Raderna ritas bara när de har tal.

### Bonus: latent bugg i `_scan_user_transcripts` (hittad av P7-arbetet)
Läsningen av `state.json` (`meta.unguarded_tokens` + `meta.tts_usage`) låg **inuti
per-sessionsfil-loopen** → en kampanj med N `session-*.jsonl` räknade allt N
gånger, och en kampanj utan transkriptfil tappades helt. Fixat: läses exakt en
gång per kampanj, och roll-/modellattributionen fästs på kampanjens sista
transkriptpost (för enkelfils-kampanjer exakt samma post som förut).
**Mätt mot skarp data innan fixen:** 0 kampanjer med >1 fil och unguarded-data,
0 kampanjer med unguarded-data men utan transkriptfil → **inga visade tal ändras**;
fixen hindrar bara framtida inflation. Oberoende kontroll: summan av
`state.meta.unguarded_tokens` över alla kampanjer = 9 342 237 == scanens
`background` (exakt).

### Verifiering
- **730 python-tester gröna** i engångscontainer (`:ro`-mount, `pip install -q pytest`;
  38 deselected = de kända geo/visits/playtest-felen på HEAD). Nya tester:
  `test_value_delivered_splits_tokens_by_source`,
  `test_scan_user_transcripts.py` (två fall: exakt-en-gång-per-kampanj + kampanj
  utan transkriptfil).
- **jsdom-QA 92/92, 0 konsolvarningar** (var 58). Fixturen genereras av riktig
  backend mot tmp-data; nytt: `tokens_sources` med riktiga tal (1,8 M bakgrund +
  0,5 M raderade på chupish), noll-läget (allt 0 → inga döda ytor), mobilkorten,
  ledger-tabellen med hink-filter.
- **Deployat:** `admin.js`/`admin.css` → `?v=20260928c`, `docker compose build` +
  `up -d --no-deps` + `./tools/deploy-frontend.sh`; md5 repo == container för
  admin.js/admin.css/chat.html/adventure.html; `/api/health` 200; ny kod bekräftad
  i containern (`tokens_sources`, `bg_model_orphans`).
- **Skarp mätning i containern:** `dated 49 993 602 · background 9 365 774 ·
  deleted 11 188 578 · lifetime 70 547 954` (summerar exakt; bakgrundstalet växer
  medan spelet spelas).
