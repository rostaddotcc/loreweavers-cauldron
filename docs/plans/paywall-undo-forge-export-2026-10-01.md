# Betalvägg: undo + adventure-export bakom donationen ("the supporter unlock") — plan 2026-10-01

Underlag: verifierat mot HEAD `2e86b04`. **Beslut (rostad 2026-10-01):**
- **Unlock = donationen.** Any donation (1€+) är en egen "unlock" som låser upp **både** undo-knappen **och** adventure-export.
- **The Forge (forga + valvet/cooked souls) lämnas orörd i den här vågen** — egen framtida våg (avsnitt 7).
- "cooked souls" = The Forge-valvets sparade karaktärer (`characters.html`) när den vågen blir aktuell.

## 0. Nuläget (verifierat i kod)

| Yta | Backend-gate idag | Var |
|---|---|---|
| Ångra senaste turen | **ingen** — bara 1 turn via `_gate_turn_quota` | `main.py:4774-4830`, UI `chat.html:6394-6410` + `/undo` |
| Kampanj-export (adventure export, zip) | `_tier_for()` i (tier1/tier2/lifetime) → **plain 403-sträng** | `main.py:11266-11282` |
| The Forge (orörd nu) | ingen gate förutom porträtt (10€-grind `_require_image_gen_tier`) | `main.py:8842`, `8972-9060`, `11956` |

Gärdmekanik som återanvänds: `features`-dict + `features_until` (`main.py:1248-1287`), `_tier_for` (`1408`),
`_benefits_active` (`1372`), 403-formen `detail={"feature_locked": "tts"|"image", "message": …}` (`4128`, `11966`),
`/api/me` features-block (`2173-2186`), admin-bypass (`role == "admin"`).
Donationsgrenen idag (`main.py:13627-13636`): **bara** `turn_bonus += amount_total`, inga features.
Admin-grant-vägen sätter `features.export/wan1080/all_models` (`main.py:13589-13622`, `14252-14261`).

## 1. Ny grind: `supporter` = "har någonsin betalat"

- Flagga `features["supporter"] = True` **utanför** `TIER_ORDER`, sätts **permanent** utan `features_until`.
- Sätts i **alla** grant-vägar: donationsgrenen + unlock10 + support300 + patron500 + lifetime + admin-grant.
  **Krav (korrekthet, inte policyval):** en unlock10-köpare betalar 10× en 1€-donator — gatas de bort från undo är det en bugg.
  Därför = "har någonsin betalat", inte "har donerat".
- Egen helper `_is_supporter(username, udata)` som läser flaggan **direkt** ur features-dicten.
  Får **inte** gå via `_benefits_active` (`1372`) — den dömer alla features mot EN gemensam `features_until`,
  så ett utgånget legacy-fönster skulle låsa en betalare.
- **`_tier_for` rörs inte** (`1408`): den läser `features.export` → tier1 (`1438`), så en ny flagga som räknas där
  ger en 1€-donator hela 10€-paketet (modeller, TTS, bilder) i smyg.
- `_require_supporter(username, payload, feature)` → 403 `{"feature_locked": "undo"|"export", "message": …}`.
  Vid läs-fel på users.json: **503**, inte tyst 403 (en betalare ska aldrig se "låst" pga transient fel).
- Backfill: `scripts/backfill_supporter.py` — källa = `backend/data/_billing_ledger.json` **och** grant-ledgern
  (`stripe:donation|unlock10|support300|patron500`) **och** `turn_cap == 0` (lifetime). Mönster:
  `tmp/migrate_demote_premium.py` → **dry-run först, backup `users.json.bak-<ts>`, EXEMPT admin**, skriv antal nya flaggade.
  `backend/data/` commitas aldrig.
- `/api/me`: `"supporter": bool(...)` i features-blocket (`main.py:2173`) → läses av `api.js` och alla sidor.

## 2. Gates (endast två endpoints i den här vågen)

1. **Undo** — `POST /api/campaign/undo` (`main.py:4774`): ordning auth → `_require_supporter(..., "undo")` →
   `_gate_turn_quota` → snapshot/restore. Låst anrop får **inte** kosta en turn, **inte** bumpa epoch och
   **inte** konsumera snapshoten (undo ska funka direkt efter donationen).
2. **Export** — `GET /api/campaign/export` (`main.py:11278`): byt tier-kollen mot `_require_supporter(..., "export")` och
   byt den plain-strängade 403:an mot `feature_locked`-formen. Legacy tier1-köpare passerar per automatik (har betalat).

The Forge: **inga ändringar** i denna våg.

## 3. Frontend — copy-wave (undo är marknadsförd, väggen måste följa med)

Fakta: `login.html:1198` ("Undo your last turn — New"), `adventure.html:833`, `mechanics.html:579` + §11
`1095-1134`, `releases.html:345` (v1.3), `help.html:229` (`chat.html:1869` kbd-hint, `6342` /help), Reddit-promon.
Donationskortet säger idag **"No feature unlock, no subscription — just fuel for the fire"**
(`pricing.html:310` + `PLAN_DATA.donation` `393-401`) — den raden motsäger hela väggen och rivs.

- `pricing.html` (pengasidan, egen våg-ägare):
  - Donationskortet får riktig förmånslista: **"Unlocks ↶ Undo last turn + campaign export (your story as a zip)"**, 1€ = 100 turns kvar.
  - `unlock10`-kortets bullet `Export & uploaded avatars` (`pricing.html:294`, `389`) → droppa "Export &" (exporten bor numera på donationen).
  - FAQ-raden (`pricing.html:320`), meta/OG/Twitter (`9/15/23`), JSON-LD `offers`, `PLAN_DATA.donation`, plan-modal-texten.
  - Deep-link: låsta ytor pekar på `pricing.html?plan=donation` (stöds redan, `pricing.html:595-613`).
- `chat.html`: låst läge på inline-knappen — `↶ Undo last turn · 🔒 part of the supporter unlock` → klick = deep-link.
  `/undo` → ärlig rad: vad som låser upp, att turen finns kvar, ingen turn debiterad. Rör inte `.undo-inline`-observern.
- `login.html` (hero-lista + Paths-rummet + top-up-kortet `ptier-topup`), `adventure.html:833`, `mechanics.html` §11
  (chip + demo-knapp + "costs 1 turn" → "+ supporter unlock"), `help.html:229`.
- `releases.html`: **ny** version-sektion (historik skrivs aldrig om).
- i18n: chrome alltid engelska, nya strängar via `I18N.t()`/ren engelska — aldrig hårdkodad svenska.
- Cache-bust per sida: `python3 frontend/bump_versions.py <fil>=<ver>` + rekursiv assert att noll filer kvarstår på gamla versionen.

## 4. Tester

- Ny `backend/tests/test_supporter_gate.py`: free → 403 `feature_locked:"undo"` + **0 turns debiterade + oförändrad epoch
  + snapshot kvar**; donator → 200 + ledger `action=undo`; unlock10-köpare passerar; lifetime passerar; admin passerar;
  donator med utgånget legacy-`features_until` passerar; export: free 403 `feature_locked:"export"`, donator 200, legacy tier1 200.
- **Stale-tester som skrivs om (förväntat):** `test_undo_turn.py` (18 tester seedar free-konton → sätt supporter i fixturen),
  `test_tiers.py:381-393` (`"10€ unlock" in detail`, `test_campaign_export_support_ok`),
  `test_campaign_export.py`, `test_stripe_billing.py` (donationsgrenen ska nu även sätta `features.supporter`),
  `test_billing_admin.py` (grant-vägen), ev. `test_tts_tiers.py`-grannar.
- Kör **helsviten** (≈824 gröna idag), inte delsvit.

## 5. Vågor

- **V0 (parent, server, sekventiellt):** flagga + helper + alla grant-vägar + `/api/me`-fältet + backfill-skriptet
  (dry-run → backup → kör → verifiera antal; **chup** = riktig donator vars features rensades 2026-09-27 → facit för backfillen).
- **V1 (backend, EN ägare — allt i `main.py`):** undo-gaten + export-gaten + 403-formen + tester (nya + omskrivna).
- **V2 (parallellt 3, disjointa filer):** (a) `pricing.html` (b) `chat.html` + `help.html` (c) `login.html` + `adventure.html` + `mechanics.html` + `releases.html`.
- **V3 (parent):** helsvit + syntax + bump_versions-assert + deploy i ordning: `docker compose up -d --build`
  (backend ligger i imagen) → `tools/deploy-frontend.sh` **efter** compose up → md5 repo vs container +
  `curl` mot `localhost:8092` och `https://dnd.rostad.cc` med **två** konton: free (låst) och donator (öppen).
- **V4:** scoped commits med explicita sökvägar — aldrig `git add -A`; `frontend/book-souls/*` + `tmp/` utanför.

## 6. Öppna detaljfrågor (byggs med rimlig default om inget annat sägs)

1. **`undo_available`-kontraktet:** default = fältet är kvar som idag, frontend äger låst läge via `/api/me`.
2. **Grandfathering:** default = väggen gäller bakåt för gratiskonton, men **alla som någonsin betalat passerar** (även unlock10/lifetime/legacy tier1).
3. **Donationskortets namn:** default = kortet heter kvar "Any" men får en explicit "Unlocks"-rad.

## 7. Risker

- Undo är skeppad och marknadsförd (v1.3, login-hero, mekaniksida, Reddit) → gating bakåt kräver copy-svepet i samma deploy,
  annars läses det som falsk reklam.
- **Export lämnar 10€-kortet och blir 1€-bar** — medvetet beslut, men 10€-kortets säljcopy måste uppdateras i samma andetag,
  annars säljer kortet en förmån det inte längre äger.
- `supporter` får inte läcka in i `_tier_for` (se 1) — annars får donatorer hela 10€-paketet.
- Låst undo får inte konsumera snapshoten eller debitera en turn → testas explicit.
- `main.py` är delad fil i aktiv worktree: grep/read regionen direkt före varje patch, `git diff` som bevis efter.

## 8. The Forge — beslut: INTE gata (rostad 2026-10-01)

Frågan om en Forge-våg (gata skapa/spara/använd av valvets själar, "cooked souls") är **lagd på hyllan för gott**:
**bara exporten ska gatas** — The Forge, inklusive valvet, genereringen och karaktärsanvändningen,
lämnas fritt för alla konton. Nuvarande grindar som rör Forge är befintliga och består:
Forge-porträttet går via 10€-grinden `_require_image_gen_tier` för BILDGENERERING (det är en bild, inte en
Forge-förmån), och själva export-ytan är redan gatud i denna våg. Ingen kod ändras för detta —
valvet är redan ogärdat.

## 9. Genomfört + verifierat (2026-10-01)

**Backend (`backend/main.py`)**
- `_is_supporter(username, udata)` (rad 1402) läser `features["supporter"]` **direkt** — aldrig via
  `_benefits_active`; faller tillbaka på legacy-nycklarna (`export`/`wan1080`/`all_models`/`unlock10`)
  och `subscription_status == "lifetime"`, så ingen betalare kan låsas ute.
- `/api/me` exponerar `features.supporter` (rad 2207) — frontendens låsta läge hänger på den.
- Undo-grinden ligger **först** i `undo_last_turn`: 403 `feature_locked:"undo"` innan kvot, epoch eller
  snapshot rörs (ett låst försök kostar 0 turns, lämnar snapshoten kvar och lämnar ledgern utan `undo`-rad).
- Exporten svarar 403 `feature_locked:"export"` (dict-form, samma som tts/image) i stället för den gamla
  plain-strängen; läsfel på kontodata → **503**, aldrig tyst 403.
- Flaggan sätts i donationsgrenen + unlock10 + support300 + patron500 + lifetime + admin-grant.
  `_PAID_FEATURE_KEYS` medvetet utanför `TIER_ORDER` — donationen läcker **inte** in i `_tier_for`
  (bevisat: `test_campaign_export_donor_ok_but_stays_free_tier` → `_tier_for == "free"`).

**Frontend** (`chat.html`, `pricing.html`, `login.html`, `adventure.html`, `help.html`, `mechanics.html`, `releases.html`)
- Undo-knappen finns kvar men i **låst läge** för gratiskonton (`_supporterUnlocked()`); klick går till
  `pricing.html?plan=donation` och anropar aldrig API:t. En backend-403 tas före `handleCapError`
  (annars öppnade den fel cap-modal).
- Export-posten i ☰-menyn speglar låst läge i hinten ("unlocked by any donation") och vägrar navigera
  till API-URL:en när kontot är låst — annars hade spelaren fått rå 403-JSON i en ny flik.
- Donationskortets falska rad ("No feature unlock…") är riven; 10€-kortet behåller exporten i copyn
  (unlock10 sätter flaggan, så det är fortfarande sant). Releases: ny **v1.6 "The Supporter's Coin"**.

**Backfill** — `scripts/backfill_supporter.py` (dry-run default, `--apply` skriver + tar backup).
Källor: betalningsledgern (amount_sek > 0, ej churn/cancel) → grant-ledgern (`stripe:*`) → kontots egna
lifetime/feature-nycklar. **Kört: 5 konton flaggade** (andreasmaurel, bomk, chup, nisse, nomis),
backup `backend/data/users.json.bak-<ts>-supporter`, andra körningen = idempotent no-op.
`turn_bonus` utan betalning (admin-topup, t.ex. `iota`) flaggas medvetet **inte** — grants ≠ betalt.

**Bevis**
- `pytest -q`: **838 passed** (varav 12 nya i `tests/test_supporter_gate.py`).
- `py_compile` + node `--check` på 11 inline-JS-block i de 7 sidorna: 0 fel.
- Deployat: `docker compose up -d --build` → `tools/deploy-frontend.sh`; md5 repo vs container = OK på alla 7 sidor.
- **Live mot https://dnd.rostad.cc** (läs-only, ingen spelardata rörd):
  `iota` (gratis) → `/api/me` `supporter=false`, `POST /api/campaign/undo` → **403 feature_locked:"undo"**,
  `GET /api/campaign/export` → **403 feature_locked:"export"**;
  `chup` (donator, backfillad) → `supporter=true`, `GET /api/campaign/export` → **200** (riktig zip).
  Upplåst **undo** live skulle ha rewound en riktig spelares tur → verifieras av testerna i stället.
- `bump_versions.py` kördes **inte**: alla sidor och assets serveras `no-cache, no-store, must-revalidate`
  (verifierat med `curl -sI`), så det finns ingen cache att busta.
