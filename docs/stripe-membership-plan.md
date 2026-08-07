# 💳 Stripe + Free Tier + Medlemskap — Implementationsplan (The Lore Weaver's Cauldron)

Uppdaterad: 2026-08-04. Föregående affärsplan: `docs/monetization-plan.md`.

## Arkitekturöversikt

```
Free-spelare:  turn_cap = FREE_TURN_CAP (50), modell = step-3.7-flash enbart
     │
     │  varje /api/chat → turns_used++ (sparas i users.json)
     │
     ├─ 403 när turns_used >= turn_cap → "Uppgradera" modal
     │
     └─ Cron (dagligen): förnya turns_used = 0 + uppdatera reset_date
             │
             └─ Premium: turn_cap = 0 (oändligt), alla modeller + Qwen TTS
```

## Datamodell — users.json (utöver befintliga fält)

```json
{
  "turn_cap": 50,                  // finns redan; 0 = oändligt
  "turns_used": 37,                // NY — spenderade turns denna period
  "turn_bonus": 0,                 // NY — top-up-turns, förbrukas före cap (admin)
  "reset_date": "2026-08-04",      // NY — när turns_used nollställs
  "subscription_status": "free",   // free | premium
  "stripe_customer_id": "cus_xxx",
  "stripe_subscription_id": "sub_xxx",
  "subscription_until": null
}
```

- Free: `turn_cap=50`, `reset_date` = nästa periodstart
- Premium: `turn_cap=0`, `subscription_until` = slutdatum
- **Top-up:** `turn_bonus` läggs till av admin, förbrukas före cap-turns
- **Modellgating:** `_clamp_player_model()` (main.py:1002) tar en `tier`-param — free får bara `step-3.7-flash`, premium får `qwen3.8-max`, `qwen3.6-flash`, `deepseek-v4-flash` + Qwen TTS

---

## 🅰️ FAS A — Free Account Systemet (KAN GÖRAS NU, ingen Stripe)

*Gör detta först — det ger värde direkt och bygger infrastrukturen Stripe sedan kopplar in i.*

### A1. Backend (`main.py`)
| Ändring | Detalj |
|---|---|
| `turns_used`-räkning | I `/api/chat` (rad ~4112): `turns_used++` sparas i users.json. Befintlig cap-check utökas: `if turns_used >= turn_cap → 403` |
| `reset_date`-logik | Vid cap-check: om `reset_date` passerad → nollställ `turns_used=0`, sätt ny `reset_date` |
| `DEFAULT_TURN_CAP` | Behåll 50 (finns redan). Lägg till `turns_used: 0, reset_date: <idag>` vid register + admin-create |
| `/api/me` | Returnera `turns_used`, `reset_date`, `subscription_status`, `tier_models` (vilka modeller spelaren får) |
| **Modellgating** | `_clamp_player_model(model, tier)` — free → `step-3.7-flash` (force), premium → PLAYER_MODELS. Både DM-val och char-gen-val klampas. `PLAYER_MODELS` (rad 999) används redan — lägg till tier-filter |

### A2. Header-info (chat.html, `.topbar .campaign`)
Bredvid kampanjnamnet, kompakt rad (desktop) / i mobil-menyn:

```
⚔️ The Lore Weaver's Cauldron · Tur 47 · Dag 3 · 🆓 37/50 free turns · reset 4 sep
```

- Data hämtas via `/api/me` + `/api/campaign/state` (dag = `world.day` eller `world.last_day_turn`)
- Stil: `--bone-dim`, liten font, `--gold` på free-turns-siffran, röd pulserande om < 5 kvar
- Mobil: flyttas in i ☰-menyns topp (topbaren är för trång)

### A3. Cap-modal (chat.html)
När 403 med `cap_reached`:
- **Om free + slut:** modal: *"⛔ Dina 50 free turns är slut. Nytt på <reset_date> — eller uppgradera för oändliga turns."* + knapp `👑 Uppgradera` (→ pricing.html)
- **Om premium + expired:** modal: *"Medlemskapet har gått ut."* + knapp till pricing

### A4. Tester (backend/tests/)
| Test | Verifierar |
|---|---|
| `test_turns_used_increments` | varje /api/chat ökar turns_used |
| `test_cap_reached_403` | 50/50 → 403 med `cap_reached:true` |
| `test_reset_date_rollover` | reset_date passerad → turns_used nollställs automatiskt |
| `test_free_model_clamp` | free anropar qwen3.8-max → klampas till step-3.7-flash |
| `test_premium_model_ok` | premium får qwen3.8-max |

---

## 🅱️ FAS B — Automatisk förnyelse (cron)

**Behov:** free-spelares turns förnyas automatiskt utan att de måste göra något.

### B1. Cron-jobb (Hermes cron, dagligen ~06:00)
```
skript: ~/.hermes/scripts/renew-turns.sh
→ python3 renew-turns.py
→ för varje user med turn_cap > 0:
     turns_used = 0
     reset_date = idag + period (1 mån / 30 dagar)
→ logga antal förnyade till Telegram (deliver=telegram, no_agent=true watchdog)
```

### B2. Endpoint-alternativ (om du hellre vill ha det i appen)
`POST /api/admin/renew-all` (admin-only) — anropas av cron via JWT. Eller helt backend-inbyggt: `reset_date`-check i `/api/chat` räcker egentligen — **cron behövs bara om du vill ha en fast reset-dag för alla** (t.ex. alla förnyas 1:a varje månad).

**Rekommendation:** kör BÅDA — `reset_date`-rollover i chat (lat, per-användare, funkar även om cron dör) + cron för att hålla datumen synkade.

---

## 🅲 FAS C — Stripe (kopplas in när FAS A är stabilt)

Som tidigare skissat:
- `backend/billing.py`: `create_checkout_session`, `verify_webhook`, `handle_event`
- Endpoints: `POST /api/billing/checkout`, `POST /api/billing/webhook` (ingen auth — Stripe-signatur), `GET /api/billing/status`
- Webhook `checkout.session.completed` → `subscription_status=premium`, `turn_cap=0`
- Webhook `customer.subscription.deleted` / `invoice.payment_failed` → demote till free
- Admin-override: `PUT /api/admin/user/{u}/subscription`
- Test: `stripe listen --forward-to localhost:8092/api/billing/webhook` + kort `4242`

---

## 🅳 Admin-vyn (admin.html)

### D1. Stat-kort (toppen — nya)
```
💰 MRR: 147 kr      🧾 Transaktioner: 4      💰 Total intäkt: 294 kr
```
- **MRR** = summa av aktiva premium-abonnemangs priser (49 kr × antal aktiva premium)
- **Antal transaktioner** = count i intäktsledgern
- **Total intäkt** = summa alla lyckade betalningar någonsin
- Källa: `_billing_ledger.json` (lokal) + Stripe-API när kopplat. Vid Stripe-live: `GET /api/admin/billing` slår mot Stripe (`stripe.billing.meter` / subscriptions + payment_intents) och cachar i ledger.

### D1b. Intäktsledger (`backend/data/_billing_ledger.json` — committas ALDRIG)
```json
[
  {"ts": "2026-09-04T10:00:00", "user": "anna", "amount_sek": 49,
   "type": "subscription_created", "stripe_sub_id": "sub_xxx", "event_id": "evt_xxx"}
]
```
- Skrivs av webhook-handlern vid varje betalningshändelse
- `GET /api/admin/billing` → `{mrr, transactions, total, per_user: {...}, ledger: [...]}`
- Ger både totalsiffror OCH per-spelare-split (transaktioner + summa per användare)

### D2. Spelartabellen — nya kolumner
```
User │ Role │ … │ Turn Cap │ Turns använda │ 💳 Medlemskap │ Reset │ 💰 Intäkt
bob  │ player│ … │ 50       │ 37            │ 🆓 Free       │ 4 sep │ 0 kr
anna │ player│ … │ 0        │ –             │ 👑 Premium    │ –     │ 147 kr
```
- Sortable: `turns_used`, `subscription_status` (premium först), `reset_date`, `revenue` (högst först)
- Premium-rader får guldglow (`box-shadow`, som `.pc-card.active`)
- Turn Cap-kolumnen visar `50 (37 använda)` med mini progress-bar — röd vid slut
- Intäktskolumnen summerar spelarens ledger-poster

### D2b. Top-up / quota-justering (per spelare — detaljvy)
Tre reglage i detaljvyn (ersätter/dvs utökar befintlig Turn Cap-kolumn):
1. **Turn Cap** (finns redan): sätter taket — `PUT /api/admin/user/{u}/turn-cap`
2. **➕ Top up** — nytt: lägg till BONUS-turns utan att röra taket
   - `PUT /api/admin/user/{u}/turn-topup` med `{bonus: 100}` → lagras som `turn_bonus` i users.json
   - `turns_used` förbrukar bonus först: `available = turn_bonus + max(0, turn_cap - turns_used)`
   - Perfekt för "här får du 100 extra turns som tack" — taket förblir 50/mån
3. **🔄 Nollställ** — `PUT /api/admin/user/{u}/turn-reset` → `turns_used = 0` (kanon för tester/kompensation)

### D3. Detaljvyn (expanderad rad)
- `subscription_status`, `subscription_until`, `stripe_customer_id`, `reset_date`, `turns_used/turn_cap`, `turn_bonus`, intäktsposter (ledger per user)
- Knappar: `👑 Ge Premium (1 mån)` / `🆓 Återställ till Free` (via `PUT /api/admin/user/{u}/subscription`)
- Mobilkorten: samma info i kompakt form

### D4. Tester (backend/tests/)
| Test | Verifierar |
|---|---|
| `test_turn_topup_granted` | bonus läggs till, available = cap + bonus |
| `test_turn_topup_consumed_first` | bonus förbrukas före cap-turns |
| `test_admin_billing_stats` | ledger → mrr/transactions/total/per_user |
| `test_webhook_writes_ledger` | betalning → ledger-post + per_user-summa |
| `test_turn_reset` | turns_used nollställs |

---

## 🅴 Spelar-UI

| Yta | Free | Premium |
|---|---|---|
| Header-info | Tur · Dag · 🆓 37/50 · reset | Tur · Dag · 👑 |
| Modellval | bara StepFun 3.7 (dolt lås 🔒 på andra) | alla 4 + TTS-val |
| TTS | bara StepFun | Qwen ⭐ + StepFun |
| Cap-modal | "Uppgradera" → pricing | – |

- `⚙️ → Subscription`-rad i settings: status + "Hantera" (Stripe portal) om premium
- Login-sida: subtil banner om free-status

---

## 🅵 Pricing Page (`pricing.html`)

Ny statisk sida (samma design-språk som login.html — mörk, guld, Cinzel):

```
┌──────────────────────────────────────────────┐
│  ⚖️ PRISER                                   │
│                                              │
│  🆓 FREE          👑 PREMIUM                 │
│  50 turns/mån     ∞ turns                    │
│  StepFun 3.7      Qwen 3.8 Max DM            │
│                   Qwen 3.6 Flash             │
│                   DeepSeek V4 Flash          │
│                   Qwen TTS (alla röster)     │
│                   ───────────────            │
│  0 kr            49 kr/mån                   │
│  [Börja gratis]  [👑 Uppgradera]             │
└──────────────────────────────────────────────┘
```

- Uppgradera-knapp → `POST /api/billing/checkout` → redirect till Stripe
- Länkas från: login (banner), cap-modal, settings, admin
- `DEFAULT_PRICING` i env: `PRICE_FREE_TURNS=50`, `PRICE_PREMIUM_SEK=49`

---

## 🗓️ Ordning & tidsestimat

| Fas | Innehåll | Tid | Beroende |
|---|---|---|---|
| **A** | Free-system: turns_used, reset_date, modellgating, header, modal, tester | ~4–5h | inget |
| **B** | Cron-förnyelse | ~1h | A |
| **D** | Admin-vyn (stat-kort MRR/transaktioner/intäkt, kolumner, top-up, ledger, premium-override) | ~3h | A |
| **F** | Pricing-sida | ~1.5h | – |
| **C** | Stripe (checkout + webhook + portal + ledger-skrivning) | ~4h | A + F |

**Totalt:** ~13–15h. **A + D + B kan byggas helt utan Stripe-konto** (ledgern fylls manuellt/administrativt tills webhooken finns).

## ⚠️ Viktiga detaljer
- **Dataförsiktighet:** users.json committas aldrig — återställ från git vid misstag
- **Idempotens:** webhook-events kan komma 2× — spara `stripe_event_ids`-lista
- **DEFAULT_TURN_CAP=50** redan på plats (register + admin-create) — bara lägga till `turns_used`/`reset_date`
- **Qwen TTS för premium:** `TTS_PROVIDERS`-listan i adventure.html + `populateModelGate` — free ser bara StepFun
- **step-3.7-flash räcker fint för free** — den används redan som EXTRACTION/GUARDIAN-modell och duger som DM
