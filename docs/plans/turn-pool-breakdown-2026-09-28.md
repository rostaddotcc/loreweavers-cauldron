# Turn-pott per spelare — patch-plan (2026-09-28)

> **STATUS 2026-09-28: GENOMFÖRD OCH DEPLOYAD.** P1 (backend), P2 (dashboard),
> P3.1 (backfill) och P3.2 (rail-etiketten) är implementerade, testade mot skarp
> data och körda i produktion. Se "Genomfört" sist i dokumentet för bevis och
> kvarvarande punkter.

> Underlag: live-filerna i `backend/data/` (users.json 159 konton, `_billing_ledger.json`
> 5 rader, `turn_ledgers/*.jsonl` 67 filer / 1 913 rader) + genomläsning av
> `backend/main.py` (`_consume_turn` 1562-1639, `_append_turn_ledger` 1654-1677,
> `_turn_ledger_breakdown` 1698-1709, `_user_stat_row` 10816-10888, `_value_delivered`
> 11038-11122, `/api/admin/overview` 11216+, `/api/admin/user/{u}` 11798+),
> `frontend/admin.js` (1 694 rader) och spelar-railarna `frontend/chat.html` /
> `adventure.html`. Alla siffror nedan är uppmätta, inga antaganden.

## 1. Vad rostad bad om

Dashboarden ska visa **per spelare**: hur stor potten är, hur mycket som köpts,
hur mycket som gått åt — uppdelat **free vs paid turns** — och det ska gå att läsa
i ett svep i stället för dagens två spretiga sifferrutor.

Tillägg 2026-09-28 (rostad, samma beställning):

2. **Overview ska visa "senast 5 aktiva spelarna"** — vilka som spelade senast, med
   deras pott, så man ser vilka konton som faktiskt är levande just nu.
3. **Spelare ska kodas med free/paid-tiers** i hela dashboarden — varje rad/kort ska
   direkt visa om kontot är betalande eller inte (i dag visas fyra tieretiketter,
   varav "free" täcker 158 av 159 konton och därför säger nästan ingenting).

Båda är formulerade så att de måste samma sanning som potten: kodningen räknas
server-side i **en** funktion, aldrig i klienten.

## 2. Diagnos — varför det är svårläst i dag

### 2.1 Pottens tre hinkar syns aldrig tillsammans

Potten har tre hinkar och en fast spenderingsordning (`_consume_turn`, main.py:1622-1636):

```
promo_bonus (legacy, spenderas FÖRST)  →  daglig cap (turns_used)  →  turn_bonus (köpta, SIST)
```

Live-läget just nu:

| Hink | Fält i users.json | Konton | Summa |
|---|---|---|---|
| Legacy-promo | `promo_bonus` | **92** | **26 621** |
| Daglig cap | `turn_cap` / `turns_used` | 153 × cap 30, 1 × cap 100 (chup), 1 × cap 300 (boblin), 4 × cap 0 = ∞ | använt i dag: 126 (chup 100, adam 25, admin 1) |
| Köpta/grants | `turn_bonus` | **10** | **2 953** (chup 464, nomis 289, lunny 100, 7 × 300) |

**Rotorsak #1 till att det är oläsligt:** eftersom promo spenderas först ser en
spelare med 300 promo ut som "0/30 använt" även efter 20 spelade turns — allt
försvinner i en hink som UI:t inte ens visar. 92 av 159 konton sitter i det läget.

### 2.2 "Hur mycket har spelaren köpt" finns inte lagrat

`turn_bonus` är **kvarvarande** köpta turns, aldrig "köpta totalt":

- 7 konton har `turn_bonus = 300` men **noll rader** i `_billing_ledger.json`
  (som totalt har 5 rader: nomis 44 kr, andreasmaurel 139 kr, chup 70 kr donation
  + två churn/cancel-markörer). Köpen/grantsen har alltså aldrig bokförts någonstans.
- Admin-topup (`PUT /api/admin/user/{u}/turn-topup`, `frontend/admin-actions.js:128`)
  adderar till `turn_bonus` utan spår.

Summa: "köpt totalt" går **inte** att rekonstruera bakåt. Det måste börja bokföras.

### 2.3 Turn-ledgern vet inte vilken hink som betalade

`_append_turn_ledger` skriver `{ts, action, model, tokens}` — 1 913 rader sedan
2026-08-07, samtliga utan hink. Free vs paid per turn är därför omöjligt i
efterhand; `_consume_turn` *vet* vilken hink den just tömde men slänger bort svaret.
Dessutom beskärs ledgern (>2 000 rader) så den kan aldrig bli livstids-sanning.

### 2.4 Där det borde stå något står inget

| Plats | Vad som finns i dag | Problem |
|---|---|---|
| `/api/admin/overview` kompakta rader (main.py:11269-11283) | username/roll/tier/land/campaigns/tokens/turns/revenue | **inga pott-fält alls** → Players-tabellen kan inte visa potten |
| `_user_stat_row` (10854-10861) | `turn_cap`, `turns_used`, `turn_bonus`, `promo_bonus`, `turns_available` | finns, men blandas inte in i overview-raden |
| Dossierns Summary (admin.js:1155-1156) | "Daily cap 30 · used 5 this period" + "Bonus turns 464 + 0 promo" | tre tal i två rutor, ingen pott, ingen koppling |
| Dossierns Usage (admin.js:1175) | "Turns consumed = antal ledger-rader" | antal rader ≠ turns förbrukade (ledgern beskärs) |
| Spelar-railarna (chat.html:1385, adventure.html:540) | `BOUGHT n` | etiketten ljuger: talet är `turn_bonus` = **kvar**, inte köpt |
| `_value_delivered` (11038) | `turns_day`, `by_action` | ingen hink-uppdelning |

## 3. Målbild

Ett block som svarar på allt i en blick — samma siffror i Players-tabellen,
dossiern och en egen pool-drawer:

```
┌ Turn pool — chup ────────────────────────────────────────────┐
│  KVAR I POT TEN            464   (100 fria i dag + 0 promo + 464 köpta) │
│  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░░  100 free · 464 paid · 0 promo      │
│                                                              │
│  Fri kvot i dag     100 / 100 använda   (nollställs 00:00 UTC) │
│  Legacy-promo         0 kvar av 300     (spenderas först)      │
│  Köpt / grantat     464 kvar av 464     köpt: okänt före 2026-09-28 │
│                                                              │
│  Förbrukat totalt   412 turns   varav 412 fria · 0 köpta       │
└──────────────────────────────────────────────────────────────┘
```

Server-side sanning = **en** funktion (`_turn_pool`) som både API:t och
`turns_available()`-gaten lutar sig mot, så dashboarden aldrig kan visa något
annat än det spelet faktiskt gör.

## 4. Patch-plan

### P1 — backend-sanning (måste landa först, UI:t läser nya fält)

**P1.1 Ledgern bokför hink + pott-läge** (`backend/main.py:1562-1639`, 1654-1677)

- `_consume_turn(...)` returnerar nu vilken hink den tömde (`"promo" | "free" | "paid" |
  "none"`) och vilket `pool_after`-värde potten hade. Ingen ändrad spenderingsordning,
  ingen ändrad gate — bara att svaret behålls.
- `_append_turn_ledger(username, action, model, tokens, bucket=None, pool_after=None)`:
  raden blir `{ts, action, model, tokens, bucket, pool_after}`. Gamla rader utan
  `bucket` ska tolkas som `"unknown"` (inte krascha, inte gissas).
- Fällan från 2026-08-05 står kvar i koden och i planen: `_tier_for` får **inte**
  anropas innanför `_USER_LOCK` (main.py:1568).

**P1.2 Livstids-räknare som aldrig nollställs** (main.py:1249-1272, 1451-1511)

Nya fält i `_FREE_FIELD_DEFAULTS` så backfill-mönstret täcker gamla konton:

```python
"turns_used_free_total": 0,   # fria cap-turns, livstid (överlever rollover)
"turns_used_paid_total": 0,   # köpta/grants, livstid
"turns_used_promo_total": 0,  # legacy-promo, livstid
"turn_grants_total": 0,       # summan av alla beviljade turns (P1.3)
"pool_data_since": None,      # ISO-datum: från när siffrorna är tillförlitliga
```

Kritiskt: det dagliga rollovert (main.py:1597-1621) nollställer `turns_used` — den
får **aldrig** röra `*_total`-fälten. Räknarna ökas i samma lås som dekrementeringen.

**P1.3 Grant-ledger — "hur mycket köpte spelaren"** (ny fil
`backend/data/turn_grants.jsonl`, en rad per beviljat paket)

```json
{"ts":"2026-09-28T21:00:00+00:00","user":"robert","turns":300,"source":"admin","note":"opening balance 2026-09-28"}
```

Skrivs från **alla** ställen som i dag rör `turn_bonus`:
- Stripe-vägen: Unlock 10 € `+100` (main.py:11648), legacy `support300 +300` (11620),
  donation `+amount_total` (11659) — kopplat till det event som redan hanteras.
- Admin: `PUT /api/admin/user/{u}/turn-topup`.
- Migration: en `opening_balance`-rad per konto (se P3.1).

"Hur mycket köpt" = summan av grant-raderna. Kvar = `turn_bonus`. Använt =
differensen. Inga gissningar.

**P1.4 `_turn_pool(username) -> dict` — enda källan** (ny, läggs vid `_turns_available`
main.py:1514)

```python
{
  "free":  {"cap": 30, "used_period": 25, "left_period": 5, "unlimited": False},
  "promo": {"left": 0, "granted": 300, "used": 300},
  "paid":  {"left": 464, "granted": 464, "used": 0, "granted_known": False},
  "used_lifetime": {"free": 412, "paid": 0, "promo": 300},
  "available": 469,               # == _turns_available() — hård invariant
  "period_reset": "2026-09-29",   # UTC, samma klocka som gaten
  "data_since": "2026-08-07",
  "buckets_known_since": "2026-09-28"
}
```

- `cap == 0` (tornmentor, geelorkius, komigenbrittmarie, onetry) → `unlimited: True`,
  aldrig "0 av 0".
- `granted_known: False` när grant-ledgern bara har en `opening_balance`-rad →
  UI:t skriver "okänt före 2026-09-28" i stället för att hitta på ett köp.

**P1.5 API-additivt** (inga brytande ändringar)

- `/api/admin/user/{username}` (11798+): lägg till `"turn_pool": _turn_pool(username)`.
- `/api/admin/overview` (11216+): kompakt `turn_pool` (6 tal: free_left, free_cap,
  paid_left, paid_granted, promo_left, available) i varje rad + i `_OVERVIEW_USER_FIELDS`
  (10900). Payload-höjning ≈ 6 tal × 159 konton — försumbart.
- `/api/admin/user/{u}/ledger` (11918+): additivt `by_bucket` + `by_bucket_today`.
- `_value_delivered` (11038): additivt `turns_by_bucket_day = {dag: {free, paid, promo,
  unknown}}` ur samma scan (gamla rader → `unknown`), så staplarna i Overview summerar
  exakt mot dagens `turns`.

**P1.6 `_player_coding(username) -> dict` — free/paid-kodningen (rostads tillägg 2)**

En funktion, samma svar i tabell, kort, dossier, drawer och CSV — ingen klientlogik
som kan glida isär. Tre koder, för att två vore oärligt när 7 konton har 300 turns kvar
utan någon betalningsrad:

| Kod | Regel | Live-exempel |
|---|---|---|
| `paid` | `revenue > 0` (betalningsrad i `_billing_ledger.json`) eller `tier2`/`lifetime` | chup (70 kr), nomis (44 kr), andreasmaurel (139 kr) |
| `granted` | inga betalningsrader, men pott utöver den dagliga capen: `turn_bonus > 0` \| `promo_bonus > 0` \| `turn_cap` skild från standard | robert/matt/duncan/bobby1/sweetbrown/euana (300 bonus, 0 betalningsrader), 92 promo-konton |
| `free` | ren gratispott: standardcap, ingen promo, ingen bonus, ingen betalning | 153-kontonsklassen |

```python
{"code": "paid|granted|free", "tier": "free|tier1|tier2|lifetime",
 "paid": True, "granted": False, "why": "70 kr donation"}
```

`tier` följer med oförändrad (den gamla fyra-nivå-etiketten blir verktygstips/secondary
text så inget tappas). `why` är en kort orsak — den håller kodningen granskningsbar i
drawern, så en `granted`-kod aldrig ser ut som ett köp.

- Läggs i overview-raden (11269-11283) + `_OVERVIEW_USER_FIELDS` (10900) — 3 små fält
  per konto — och i `/api/admin/user/{u}` (11798+).
- Kodningen läser `turn_pool` när den finns (P1.4) så `granted` inte behöver gissas.

### P2 — dashboarden (`frontend/admin.js`, `admin.html`, `admin.css`)

**P2.1 Overview** (admin.js:319-393)
- Ny KPI "Turn pool" (drill `pool`): `469 available · 100/100 free today · 464 paid left`.
- "Turns delivered per day" (admin.js:355) → **staplad** stapel free/paid/promo ur
  `turns_by_bucket_day`. `vchart` klarar inte stacking i dag → lägg en `vchartStacked`
  bredvid (samma utseende, egen legend), eller utöka `vchart` med `stack:true`.
- "What the turns bought" (356) behåller `actionSplit` men får hink-legend.
- **Nytt kort "Recently active"** (rostads tillägg 1) — de **5 senast aktiva spelarna**,
  egen rad i grid:en (card(12) eller card(6) vid sidan av "New accounts per day"):

```
Recently active · last 5 players                    [ 4 accounts have no activity stamp ]
 ────────────────────────────────────────────────────────────────────────────────────
 ● PAID     chup        464 left (100 free today)      active 12 min ago   · 100 turns today
 ● FREE     adam         25 / 30 free used             active 14 h ago     · 25 turns today
 ● GRANTED  lunny       100 paid left (grant)          active 4 days ago   · —
 ● FREE     radek         0 / 30 free used             active 5 days ago   · —
```

- Datakälla: overview-payloaden har redan `last_active` + `role` per konto i den
  **kompletta** tabellen (159 rader, 11281) → sorteringen görs i klienten mot samma
  payload som tabellen, utan ny endpoint. Om listan någon gång server-pagineras måste
  topp-5 flyttas till backend (noteras i koden).
- Konton **utan** aktivitetsstämpel (inga transkript) exkluderas och antalet skrivs ut i
  kortets notis — aldrig en påhittad tid.
- Relativ tid räknas mot payloadens (UTC-)tidsstämplar; tomt fält får aldrig bli "0 min".
- Varje rad är klickbar → samma dossier som Players-tabellen (kod-chip, pott, senast aktiv).
- **Beslut som krävs:** admin-kontot är i dag näst mest aktivt. Förval i planen: `role=admin`
  exkluderas ur "senast 5 aktiva **spelarna**", och kortets notis säger det rakt ut
  ("admins excluded"), så listan aldrig ser ofullständig ut utan förklaring.

**P2.2 Players-tabellen** (admin.js:498-560, `sortVal` 469-483)
- **Kodningskolumnen** (rostads tillägg 2): Tier-kolumnen (admin.js:536, `tierTag`) blir
  **Code** med `Paid` / `Granted` / `Free` (fyra-nivå-tieren kvar i `title` + som liten
  secondary-text), plus en färgad vänsterkant på raden (`<tr class="coded paid">`) så
  kodningen syns även när man skannar 159 rader. Legend ovanför tabellen.
- Ny kolumn **Pool**: `5/30 free · 464 paid` + mini-segmentbar (grön fri / amber köpt /
  dim promo). Sortbar på `available` och `paid_left`.
- `mobCard` (561): samma kod-chip + pool-rad i mobilkortet.
- `ftot`-raden (530-534): lägg `ftot('Turns left in pool', ...)` och
  `ftot('Paying accounts', ...)` (antal `paid`/`granted` i urvalet).

**P2.3 Dossierns Summary** (admin.js:1149-1162)
- Ersätt de två rutorna "Daily cap" + "Bonus turns" (1155-1156) med **ett**
  pool-block per målbilden: kvar-i-potten i stort, tre rader (fri kvot i dag / promo /
  köpt), förbrukat-total med free/paid-split, reset-klocka.
- Ärlighetsnoten ligger kvar i blocket: `granted_known: False` → "köpt: okänt före
  2026-09-28".

**P2.4 Dossierns Usage** (admin.js:1167-1179)
- "Turns consumed" (1175) slutar räkna ledger-rader och läser `turn_pool.used_lifetime`
  (gamla rader räknas som `unknown` med notis, inte som free).
- Ledger-action-staplarna får hink-chips när raderna har `bucket`.

**P2.5 Ny drawer `drawerPool()`** (mönster: `drawerValue` 936, `drawerLedger` 972)
- Per-dag staplad free/paid/promo, grant-tabellen (datum/turns/källa/not) och senaste
  ledger-raderna med hink-chip. Nås från pool-KPI:n, Players-kolumnen och dossién.

**P2.6 Free/paid-kodning i hela dashboarden** (rostads tillägg 2)

En kod, alla ytor — ingen vy får visa en egen variant:

| Yta | Var | Vad som ändras |
|---|---|---|
| Players-tabellen | admin.js:548-560 | Code-kolumn + färgad radkant + legend |
| Mobilkortet | admin.js:561-567 | kod-chip + pool-rad |
| Filter | admin.js:519-529 | ny chip-rad `Code: All / Paid / Granted / Free` (de fyra tier-chipsen finns kvar) |
| Dossiern | admin.js:1076-1200 | kod-chip i drawer-headern + rad i Summary-blocket med `why`-orsaken |
| Recently active | nytt kort, P2.1 | kod-punkt per rad |
| CSV-export | `data-csv="players"` | ny kolumn `code` + `pool_available` |
| Pool-drawern | P2.5 | kodningen förklaras överst (samma `why` som API:t) |

- `tierTag` (admin.js:281) → `codeTag(u)`; återanvänder befintliga `.tag`-stilar.
  `.tag.paid` finns redan (admin.css:984); lägg `.tag.granted` med **befintliga**
  variabler (teal/violet — ingen ny färg) och behåll `.tag.free` dim.
- Kodningen läses från payloaden (`coding.code`), aldrig räknad i JS — samma funktion
  som API:t (P1.6) så tabell, kort, dossier och CSV inte kan säga olika saker.
- Nya färgpar in i samma kontrastpar-mätning som dashboard-v2 (224/224-passet).

**P2.7 Design**
- Endast befintliga byggstenar (`card`, `kpi`, `dgrid`, `donut`, `hbars`, `vchart`,
  `PALETTE`) — ingen ny temayta, inga nya fonter. Färgerna ligger redan i accent/
  amber/dim; kontrastpar ska mätas som i dashboard-v2-passet (224/224-passet).
- Cache-busta efter varje frontend-ändring: `python3 frontend/bump_versions.py
  admin.js=<ver> admin.css=<ver>`.

### P3 — migration, ärlighet, spelarsidan

**P3.1 `scripts/backfill_turn_pool.py`** (dry-run som förval, `--write` för att köra)
- Skriver **en** `opening_balance`-rad per konto med dagens `turn_bonus` (+ ev.
  `promo_bonus`) som `turns` — aldrig påhittade köp. Efter körning är
  "kvar = grantat, använt = 0" för legacy-konton, vilket är sant och läsbart.
- Sätter `pool_data_since` / `buckets_known_since` på konton med gammal historik.
- Livstids-räknarna får sitt **kända golv**: antal ledger-rader per konto från
  2026-08-07 (1 913 rader, hink = `unknown`), inte en fabricerad livstidssiffra.
- Backup först: `users.json.bak-<datum>-turnpool` (mönstret från
  `tmp/migrate_demote_premium.py`), och `_billing_ledger.json` rörs inte.

**P3.2 Spelar-railarnas etikett** (chat.html:1385, adventure.html:540)
- `BOUGHT n` → `LEFT n` (talet är kvarvarande `turn_bonus`). Alternativt visa båda:
  `BOUGHT 300 · LEFT 464` när grant-ledgern har rader. Beslut krävs (se §8).

**P3.3 Konsolidering**
- `_user_stat_row` (main.py:10854-10861) ersätter `turn_cap`/`turns_used`/`turn_bonus`/
  `promo_bonus` med `turn_pool`-objektet *utöver* de gamla fälten (behåll dem en våg
  så inga gamla vyer går sönder), och `/api/admin/stats` får samma additiva fält.

## 5. Testplan

| Fil | Vad som läggs till |
|---|---|
| `backend/tests/test_turn_pool.py` (ny) | spenderingsordning promo→free→paid ger rätt `bucket`; `*_total`-räknarna är monotona över rollover; pott = gate (`available == _turns_available()`, hård invariant); `turn_cap 0` = ∞; konto utan grant-rader → `granted_known: False`; grant-loggens summa = `turn_bonus`-ökningen; hink-konsistens (summan av hinkarna = `available`) |
| `backend/tests/test_turn_ledger.py` (185 rader) | nya rader har `bucket`; **gamla** rader utan `bucket` parsas och räknas som `unknown` (bakåtkompatibilitet) |
| `backend/tests/test_admin_overview.py` (798 rader) | overview-rader bär `turn_pool`; staplad serie summerar mot `value.turns`; payloaden växer inte över tröskeln |
| `backend/tests/test_player_coding.py` (ny) | `paid` kräver betalningsrad (grant utan betalning → `granted`, aldrig `paid`); `turn_cap 0` (lifetime) → `paid`; cap 300 utan betalning (boblin) → `granted`; promo-only → `granted`; ren gratispott → `free`; kodningen ändras **inte** av att spelaren konsumerar turns. Live-facit mot fixture (inte mot skarp users.json): **paid 7 · granted 98 · free 54** av 159 |
| `backend/tests/test_me_stats.py` | `/api/me`-svaret oförändrat (inga nya spelarfält läckta i onödan) |
| jsdom-harness mot **riktiga** payloads | samma mönster som dashboard-v2-passet: pool-kolumnen renderas för alla 159 rader, inga `undefined`/`NaN` i HTML, siffror lika payloaden, drawer öppnar från KPI + kolumn + dossier. **Nytt:** "Recently active"-kortet renderar exakt 5 rader (inte 4/6), admin exkluderas och notisen säger det, konton utan tidsstämpel räknas i notisen, kod-chipen matchar `coding.code` för samtliga kort/rader/CSV |

Kör hela sviten (`~/.hermes`-mönstret): backend-testerna i containern/virtuellt,
npm-fritt jsdom-skript för admin.js. Krav innan deploy: 0 failures, inga nya kontrastpar
under tröskel.

## 6. Deploy & verifiering (verifierat recept)

```bash
cd ~/dnd-llm
docker compose up -d --build          # backend ligger i imagen
tools/deploy-frontend.sh              # frontend kopieras EFTER compose up
python3 frontend/bump_versions.py admin.js=<ver> admin.css=<ver>
curl -s http://localhost:8092/health
md5sum frontend/admin.js ; docker exec loreweavers-cauldron md5sum /app/frontend/admin.js
```

Live-kontroll mot facit — två konton som tillsammans täcker alla hinkar:

| Konto | Varför | Förväntat |
|---|---|---|
| `chup` | patron, cap 100, `turns_used` 100, paid 464 | free 100/100 använt i dag, 464 paid kvar, available 464 |
| `euana` | promo-spelare | promo 191 kvar, fri kvot orörd → visar varför "free used 0" inte betyder "spelade inget" |
| `robert` | `turn_bonus 300`, inga köp-rader | "köpt: okänt före 2026-09-28", 300 kvar |
| `tormentor` | `turn_cap 0` | ∞, inte 0 av 0 |
| `adam` | free, 25/30 använt i dag | "25/30 free used", kod `free` |
| `mainchat` | promo-spelare (225 kvar) | "0 free used" **men** 225 promo i potten — beviset att hinken syns |
| `bobby1` | 300 bonus, noll betalningsrader | kod `granted` (aldrig `paid`), "köpt: okänt före 2026-09-28" |

Kodningen som helhet: **paid 7 · granted 98 · free 54** av 159 konton (räknat mot
users.json + betalningsledgern 2026-09-28). Samma tre tal ska stå i tabellens legend,
`ftot`-raden och CSV:n — annars visar ytorna olika sanning.

"Senast 5 aktiva" ska vid verifiering visa samma fem konton som en oberoende
mtime-scan av `backend/data/campaigns/*` (admin exkluderad) — mätt 2026-09-28:
chup, adam, draco, zkh, lunny.

Verifiera med `curl` mot `/api/admin/user/<u>` **och** i webbläsaren (Prompts siffra i
UI:t måste vara identisk med payloaden — inga klientside-gissningar).

## 7. Risker & fallgropar

1. **Deadlock**: `_tier_for` innanför `_USER_LOCK` (main.py:1568) — gäller även den nya
   grant-skrivningen.
2. **UTC vs lokal dag**: `turns_used` nollställs på **UTC**-midnatt (`_today_date`),
   medan dashboardens serier bucketeras i lokal tid (`_day_key`). "Fri kvot i dag" måste
   läsa samma UTC-dag som gaten, annars säger dashboarden 5/30 när spelet säger 12/30.
3. **Ledger-beskärning** (2 000 rader) → hink-historik försvinner; livstids-räknarna i
   users.json är den varaktiga sanningen, ledgern bara detalj.
4. **`turn_cap 0` = oändligt**, aldrig "slut". Samma för `turns_available() == 999999`.
5. **Undo ger ingen refund** (`/api/campaign/undo`, main.py:4413-4419: "undo är själv en
   tung action") — räknarna behöver ingen återläggningslogik, men `undo` ska bokföras i
   hink som alla andra actions.
6. **Admin-turn-reset** (`PUT …/turn-reset`) nollställer `turns_used` utanför potten →
   `used_period` sjunker men `*_total` ska stå still. Testas uttryckligen.
7. **Pengavägar**: Stripe-hanteringen får bara få en extra grant-rad — ingen ändring i
   vad spelaren får. Aldrig röra `_billing_ledger.json`.
8. **Ocommittat arbete i trädet** (dashboard v2 ligger ocommittat, se daily 2026-09-27):
   committa/brancha **före** den här vågen så patchen går att backa.

## 8. Öppna beslut till rostad

1. Spelar-railens `BOUGHT n`: byta etikett till `LEFT n`, eller visa `BOUGHT 300 · LEFT 464`?
2. `opening_balance` för legacy-konton: rätt väg (kvar = grantat, använt 0), eller vill du
   att jag gräver vidare i git-historik/backuper för att hitta de riktiga paketen?
3. Overview: egen pool-panel **och** Players-kolumn, eller räcker Players + dossier + drawer?
4. "Senast 5 aktiva **spelarna**": ska admin-kontot räknas bort (förval: ja, med notis i
   kortet), och räcker 5 — eller vill du kunna välja 5/10?
5. Kodningen: räcker `Paid / Granted / Free` som primär etikett (fyra-nivå-tieren kvar i
   tooltip), eller ska de fyra tier-nivåerna stå kvar som huvudtext och bara färgas om?

## 9. Ordning & omfattning

| Våg | Innehåll | Uppskattning |
|---|---|---|
| P1 | Ledger-hink + livstids-räknare + grant-ledger + `_turn_pool` + `_player_coding` + API-additivt + tester | ~3 h |
| P2 | Overview-KPI + staplad graf + **"senast 5 aktiva"** + Players-kolumn + **kodning i alla ytor** + dossier-block + drawer | ~3-4 h |
| P3 | Backfill-skript (dry-run → write) + ärliga etiketter + spelar-rail-etikett | ~1 h |

P1 måste vara grön innan P2 rör `admin.js` (UI:t läser `turn_pool`). Verifiering efter
varje våg, inte bara i slutet.

---

## 7. Genomfört (2026-09-28, samma dag som planen)

### P1 — backend (deployad i imagen)
- `_consume_turn` returnerar hinken (`promo` → `free` → `paid`), `_append_turn_ledger`
  skriver `bucket` + `pool_after`; äldre rader förblir `unknown`.
- Livstidsräknarna `turns_used_free_total|paid_total|promo_total` (+ `turns_used_unknown_total`)
  ligger i users.json och nollas aldrig av dygns-rollovern.
- Grant-ledgern `backend/data/turn_grants.jsonl` bokför varje paket (stripe:support300,
  stripe:unlock10, stripe:donation, admin, opening_balance) — kopplad i alla tre
  Stripe-vägarna + admin-topup.
- **EN form på potten i hela API:t**: `_pool_compact()` ger samma platta nycklar i
  `/api/admin/overview`, `/api/admin/stats` och `/api/admin/user/{u}` (dossién lägger
  till livstid/källor via `_pool_detail()`). `available == _turns_available()` är
  invariant och verifierad för alla 159 konton i skarp data.
- `/api/admin/overview` får `coding_summary`, `pool_totals`, `value.turns_by_bucket_day`
  och kompakta `turn_pool`/`coding` per rad.

### P2 — dashboarden
- Overview: pott-KPI ("Turns left in pools"), **staplad hink-graf** (fri/köpt/promo/legacy),
  **"Recently active" med senast 5 spelarna** (kod + pott + relativ tid, notis om konton
  utan stämpel) och kod-donut med klick → kontona bakom koden.
- Players: **Code**- och **Pool**-kolumner (pott-bar), `Spent`, Code-filtret, summor i
  ftot-raden, mobilkort med pott, och `players.csv` med alla pott-fält.
- Dossier: pott-blocket + grant-tabellen + hink-uppdelning i Summary/Usage.
- Egna drawers: `turn pool` (per spelare + aggregerad) och `players · code`.
- Endast befintliga temavariabler — inga nya färger (paid=--good, granted=--violet,
  promo=--violet, fri=--good/--dim).

### P3 — backfill + spelarsidan
- `scripts/backfill_turn_pool.py` (dry-run förval, `--apply`, backup först): **10**
  konton fick en `opening_balance`-rad (2 948 turns totalt), **132** fick
  `pool_data_since=2026-09-28`, **66** fick `turns_used_unknown_total` (legacy-rader).
  Andra körningen = 0 ändringar (idempotent), `turn_bonus`/`promo_bonus`/`turn_cap`
  oförändrade mot backupen.
- Railarna `chat.html` + `adventure.html`: `BOUGHT n` → `LEFT n` (talet är kvarvarande).

### Bevis
- Python: **727 passerade** i engångscontainer (de 12 kvarvarande felen i
  geo/visits/playtest finns identiskt på HEAD före patchen — verifierat mot
  `git archive HEAD`).
- Frontend: jsdom-harness mot riktiga backend-payloads → **53/53**, 0 konsolvarningar
  (`~/.hermes/cache/scratch/qa/qa_dashboard.js` + `gen_dashboard_fixtures.py`).
- Live: `pott == gate OK (159 konton)`, backfillens spår räknade, inga potter tappade,
  `md5` repo == container för admin.js/admin.css/chat.html/adventure.html, admin.js/css
  serveras med `?v=20260928b`.

### Kvar
- **Committat 2026-09-28:** hela passet ligger i `dd5a3ec` (*Turn-pott per spelare
  (rostad 2026-09-28)*, 14 filer, +2 378/−28), och designunderlaget från v2-vågen i
  `dea1829` (*Admin-dashboard v2: preview-mockup*). Drilldown-koden `20aacd8` var redan
  committad. **Pushat 2026-09-28** till `origin/main`
  (`github.com/rostaddotcc/loreweavers-cauldron`, `main` == `origin/main`).
- Kvar i trädet (medvetet utanför båda commitsen): spelets egna byten i
  `frontend/book-souls/` (avatarer + `gallery.json`) och 84 ostagade scratch-filer i
  `tmp/` (äldre subagentrapporter, migreringsskript, `tmp/backup-turnpool-20260928/`).
- Öppna beslut #1–#5 i planen (admin-kontots kod, primär etikett, m.m.).
