# SHARED SPEC — Fas A+B+D (free-tier + admin) — 2026-08-04

Repo: `~/dnd-llm` (branch main, HEAD 5aac6c3). Container `loreweavers-cauldron` (port 8092).
Backend: FastAPI `backend/main.py` (~7576 rader), state `backend/state_manager.py`.
Frontend: `frontend/chat.html`, `frontend/admin.html`.

## GEMENSAMT (alla subagenter)

- **Får INTE:** git commit/push, docker build/cp, ändra data-filer (users.json, campaigns/, _billing_ledger.json, _account_usage.json).
- **Får:** skriva kod + tester. Verifiera med `python3 -m pytest backend/tests/ -x -q` (använd venv-python: `~/.hermes/hermes-agent/venv/bin/python -m pytest ...`) och `node --check`.
- **Språk:** UI-chrome engelska, kommentarer svenska ok, kod-identifierare engelska.
- **DEFAULT_TURN_CAP=50** (main.py ~1648/7515). Befintligt: `_turn_cap_for(username)` (~976), `PUT /api/admin/user/{u}/turn-cap` (~7521), `total_turns()` i state_manager (~188, summerar alla kampanjers turn_count), `/api/me` (~1686).

## users.json — ny datamodell (alla fält med setdefault för bakåtkompatibilitet)

```json
{ "turn_cap": 50, "turns_used": 0, "turn_bonus": 0,
  "reset_date": "2026-08-04", "subscription_status": "free",
  "stripe_customer_id": null, "stripe_subscription_id": null,
  "subscription_until": null }
```
- `turns_used` = spenderade turns DENNA period (nollställs vid reset_date).
- `turn_bonus` = admin top-up, förbrukas FÖRE cap-turns.
- `subscription_status`: free|premium. Premium → turn_cap effektivt 0 (oändligt).
- Period = 30 dagar från reset_date.

## FAS A — backend free-system (main.py + state_manager.py + tester)

Whitelist: `backend/main.py`, `backend/state_manager.py`, `backend/tests/test_free_tier.py` (ny).

1. **Tier-hjälpfunktioner** (nära _turn_cap_for, ~976):
   - `_tier_for(username) -> str` — "premium" om subscription_status=premium OCH subscription_until ej passerad, annars "free". Om premium men passerad → demote i users.json (status=free).
   - `_turns_available(username) -> int` — `turn_bonus + max(0, turn_cap - turns_used)` om free; `999999` om premium.
   - `_consume_turn(username) -> None` — turns_used += 1, spara users.json (med _USER_LOCK).
2. **Reset-rollover:** i `_turns_available`/`_consume_turn`: om `reset_date` passerad (idag >= reset_date) → `turns_used=0`, `turn_bonus` behålls, `reset_date = idag + 30 dagar`.
3. **/api/chat cap-check** (~4112): ersätt `turns_used = store.total_turns(username)`-logiken med `_turns_available(username) <= 0` → 403 med `detail` innehållande `cap_reached:true` (lägg i en dict med "cap_reached": True, "reset_date": ...). BEHÅLL total_turns för admin-stats men använd den INTE för cap. Notera: total_turns används även i admin — rör inte den funktionen.
   - Anrop `_consume_turn(username)` när turen faktiskt skickas (efter alla 403-checks, före LLM-anropet helst — annars i slutet; viktigast att den bara körs vid godkänd turn).
4. **Modellgating:** `_clamp_player_model(model_id, tier=None)` (~1002) — om tier free → returnera ALLTID "step-3.7-flash". Premium → befintlig logik (PLAYER_MODELS). Uppdatera anropsstället (~4109) att skicka tier. Char-gen-modellen klampas också (sök andra _clamp_player_model-anrop).
5. **/api/me** (~1686): lägg till `turns_used`, `turn_bonus`, `reset_date`, `subscription_status`, `subscription_until`, `turns_available`.
6. **Register + admin-create** (~1648/7515): lägg till `turns_used: 0, turn_bonus: 0, reset_date: <idag ISO>, subscription_status: "free", subscription_until: null`. Befintliga konton: setdefault i `_turn_cap_for` eller en migration vid load — använd `setdefault`-mönstret.
7. **Tester** (backend/tests/test_free_tier.py):
   - test_turns_used_increments: register→login→chat 1 turn → turns_used 1
   - test_cap_reached_403: sätt turn_cap=1, chat 1 → ok; chat 2 → 403 + cap_reached
   - test_reset_date_rollover: reset_date igår → nollställning vid nästa koll
   - test_turn_bonus_consumed_first: bonus 100, cap 1 → available 100 innan cap räknas
   - test_free_model_clamp: free + model_id=qwen3.8-max → step-3.7-flash
   - test_premium_model_ok: premium + qwen3.8-max → behålls
   - test_premium_unlimited: premium → available huge
   Testa med TestClient + monkeypatch av _USER_LOCK (använd samma mönster som test_feedback_inbox.py).

## FAS D — admin billing + top-up (main.py + admin.html + tester)

Whitelist: `backend/main.py`, `backend/tests/test_billing_admin.py` (ny), `frontend/admin.html`.

1. **Ledger** `backend/data/_billing_ledger.json` — lista av `{"ts","user","amount_sek","type","stripe_sub_id","event_id"}`. Helpers `_ledger_load()`, `_ledger_append(entry)`, `_ledger_per_user()` (summerar amount_sek per user), `_ledger_totals()` → {mrr, transactions, total}. MRR = 49 × antal users med subscription_status=premium (ej passerad). Skapa filen tom om saknas. ALDRIG commit.
2. **Endpoints (admin-only, samma mönster som turn-cap):**
   - `GET /api/admin/billing` → {mrr, transactions, total, per_user: {user: sek}, ledger: senaste 50}
   - `PUT /api/admin/user/{u}/turn-topup` body {bonus: int} → turn_bonus += bonus
   - `PUT /api/admin/user/{u}/turn-reset` → turns_used=0
   - `PUT /api/admin/user/{u}/subscription` body {status: "free"|"premium", until: "YYYY-MM-DD"|null} → sätter subscription_status + subscription_until (premium → turn_cap sätts till 0, free → DEFAULT_TURN_CAP om det var 0)
3. **admin.html:**
   - 3 nya stat-kort i `#stat-cards` (renderStats ~866): 💰 MRR, 🧾 Transactions, 💰 Total revenue — hämtas från GET /api/admin/billing
   - Ny sortbar kolumn `💳 Medlemskap` (free/premium) + `💰 Rev` (per_user-summa). Premium-rad → guldglow (klass .premium-row med box-shadow gold).
   - Turn Cap-kolumnen visar `cap (used använda)` + mini progress-bar (röd vid slut). Top-up-knapp i detaljvyn: input + "➕ Top up" → PUT turn-topup, samt "🔄 Reset" → turn-reset, samt premium-toggle (Ge Premium 1 mån / Återställ Free).
   - Mobilkort: samma info kompakt.
   - Sortering: lägg till keys i befintlig sort-logik (~511, ~552).
4. **Tester** (test_billing_admin.py): topup-grant, topup-consumed-first (via _turns_available), billing-stats (manuell ledger), admin-403 på icke-admin, turn-reset.

## FAS A-frontend + FAS B — header-info, cap-modal, cron (chat.html + skript)

Whitelist: `frontend/chat.html`, `~/.hermes/scripts/renew-turns.py` (ny), ingen backend-kod.

1. **Header-info** (`.topbar .campaign` ~48/1399): efter kampanjnamnet visa `· Tur N · Dag M · 🆓 X/Y · reset D` (desktop). Data: /api/me (turns_used/turn_bonus/turn_cap/reset_date) + /api/campaign/state eller DOM (turn/dag). Free: visa turns kvar; premium: `👑`. Mobil (≤900px): lägg info i ☰-menyns topp istället (topbaren trång).
2. **Cap-modal:** fånga 403 med cap_reached i send-message-flödet → visa modal: "Your free turns are spent. New turns on <reset_date> — or upgrade for unlimited." + knapp till pricing.html (länk, sidan finns inte än — href="pricing.html" funkar ändå, 404 ok för nu eller visa bara text). Premium-expired → egen text.
3. **Cron-skript** `~/.hermes/scripts/renew-turns.py`: läser backend/data/users.json (path: ~/dnd-llm/backend/data/users.json), för varje user med turn_cap>0: turns_used=0, reset_date=idag+30d. Skriver tillbaka. stdout: "Förnyade N konton" eller tom vid inget att göra. Körbar via python3 direkt.
   - NOTERA: skriptet ska vara robust — läs/skriv atomiskt (tmp+rename), hantera saknad fil.
   - Ingen cron-scheduling i subagenten (görs av huvudagenten efteråt).

## Verifiering (alla)

- `~/.hermes/hermes-agent/venv/bin/python -m pytest backend/tests/ -q` (alla gröna, befintliga 79 + nya)
- `node --check` på extraherade inline-scripts i admin.html/chat.html
- Admin.html: style-brace-balans via python räkning av { }
- Rapportera: exakta ändringar per fil, testresultat, ev. avvikelser från spec.
