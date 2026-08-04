# Implementation Plan — 2026-08-04: Mail-reset, Backup, Profil, Stripe

> **För Hermes:** körs sekventiellt per spår; subagenter bara med strikt fil-whitelist + egna autouse-tester. Data-filer (users.json, kampanjer, ledger) rörs ALDRIG i tester — tmp-pekar via autouse-fixtures (users.json-incidenten 2026-08-04).

**Mål:** (1) E-postbaserad lösenordsåterställning för konton med e-post, (2) varannan-timmes-backup av hela spelet till Proton Drive, (3) spelarprofil i adventure.html med samma stats som adminvyn (exkl. land), (4) Stripe checkout + webhook med live-nyckel (testa flödet, ej fullständig lansering).

**Arkitektur:** FastAPI-backend (main.py) + statiska HTML. Mail via Proton Bridge (SMTP 1025) med Python-klienten. Backup via rclone → `protondrive:/backups/loreweavers-cauldron/`. Stripe via `stripe`-paketet (eller rå httpx) med Checkout Session (hosted) + verifierad webhook.

---

## Spår A — Lösenordsåterställning via e-post

**Bakgrund:** 12/44 konton har e-post. Nuvarande reset (POST /api/auth/reset-password) kräver bara användarnamn — ingen identitetskontroll. Ny design: konton MED e-post får engångs-token-länk i mailen; konton UTAN e-post behåller nuvarande flöde.

**Designval (svar på "länk eller kod?"):** **Engångs-token-länk är bäst** — säkrare än kod (ingen brute-force på 6 siffror), one-time-use, expirerar (30 min), och leder direkt till "ange nytt lösenord"-sidan. Kod i mail kräver extra inmatningssteg + rate-limit-skydd. Token-länk = standardpraxis.

**Backend (main.py):**
- `POST /api/auth/request-reset` `{username}` → om kontot har e-post: generera `reset_token` (secrets.token_urlsafe(32)) + `reset_token_expiry` (now+30min) i users.json, skicka mail med länk `https://dnd.rostad.cc/reset.html?token=...`. Svara alltid `{ok:true}` (även om användaren inte finns / saknar e-post — ingen användar-uppräkning). Rate-limit: 1 per 5 min per användare.
- `POST /api/auth/reset-with-token` `{token, password}` → verifiera token + expiry (one-time: radera token efter användning), sätt nytt lösenord, sätt session-cookie (inloggad direkt).
- Mail via Proton Bridge: ringa `python3 ~/.hermes/scripts/email/proton_client.py send --from loreweaver@rostad.cc --to X --subject ... --body ...`. Backend körs i Docker — kan inte nå hostens Bridge rakt av. **Lösning:** mail-utskick sker via en lokal helper på hosten (Hermes-skript) ELLER backend skriver en "outbox"-fil som hosten skickar. Enklast för v1: backend POST:ar till en liten host-endpoint? Nej — **enklast: backend gör subprocess-anrop till hosten via `host.docker.internal`?** Bridge lyssnar på 127.0.0.1 (host) — inte i containern.
  **Beslut:** lägg mailskick i en separat host-side-service: Hermes cron/script pollar `backend/data/outbox/*.json` var 2:a minut och skickar via proton_client.py. Backend skriver outbox-fil (data, gitignored). Robust + ingen Docker-nätverkshack. (Bridge-portar 1025/1143 var NERE vid kartläggning — måste fixas först, se proton-bridge-troubleshooting.)
- Login-sidan: nytt fält "Forgot your word?" → skicka användarnamn → "Check your inbox" (om kontot har e-post) eller "No email on file — use the forge" (fallback till nuvarande direkt-reset... NEJ: svara identiskt för att inte läcka vilka konton som har e-post; visa neutral text + admin kan fortfarande reset:a manuellt).

**Frontend:**
- `login.html`: knapp → modal/vy "Request reset link" (användarnamn). Vid success: "If that adventurer has an email, a reset link is on its way."
- `reset.html` (NY): läser `?token=`, fält för nytt lösenord ×2 → POST reset-with-token → redirect till chat.html.

**Tester (test_auth.py, autouse):**
- request-reset på konto med e-post → outbox-fil skapad med token-länk
- request-reset på konto utan e-post / okänt → samma `{ok:true}`, ingen outbox
- reset-with-token: giltig token → lösenord ändrat + inloggad; ogiltig/expired/återanvänd token → 400/401
- rate-limit: andra request inom 5 min → 429

---

## Spår B — Backup var 2:e timme → Proton Drive

**Kopia av mönstret i server-backups-skillen** men för dnd-llm, tätare, eget mål.

**Skript `~/.hermes/scripts/dnd-cauldron-backup.sh`:**
1. `tar czf /tmp/dnd-cauldron-<ts>.tar.gz` av:
   - `~/dnd-llm/backend/data/` (users.json, kampanjer, vaults, ledger, feedback, ip_geo)
   - `~/dnd-llm/backend/*.py` + `backend/tests/` (källkod — "o allt")
   - `~/dnd-llm/frontend/` (HTML/CSS/JS — inbakas i imagen men bra att ha)
   - `~/dnd-llm/docker-compose.yml`, `.env.example`, `docs/`
   - EXKLUDERA: `backend/.env`, `backend/.env.stripe`, `__pycache__`, `*.pyc`
2. `rclone copyto /tmp/... protondrive:/backups/loreweavers-cauldron/dnd-cauldron-YYYYMMDD-HHMM.tar.gz`
3. Rensa lokala temp + behåll senaste 30 på remote (samma retention som övriga).
4. Printa `✅ Cauldron backup: <storlek> → protondrive` (notis varje körning — användaren vill alltid ha notis).

**Cron:** `cronjob(action='create', name='dnd-cauldron-backup', schedule='0 */2 * * *', no_agent=True, script='dnd-cauldron-backup.sh', deliver='telegram')`. (Krockar ej med veckojobben — olika mål-sökväg, men stagar 5 min från :00 om rclone gnäller; testa först.)

**Verifiering:** kör skriptet manuellt, `rclone ls protondrive:/backups/loreweavers-cauldron/ | tail -3`.

---

## Spår C — Spelarprofil i adventure.html (kugghjulet)

**Backend:**
- Ny endpoint `GET /api/me/stats` (kräver inloggning, spelare ser BARA sig själv): återanvänd `_scan_user_transcripts` + samma stat-bygge som adminvyns per-user-loop, men:
  - EXKLUDERA: ip, country, country_code, country_flag
  - INKLUDERA: username, role, email (om finns), total_campaigns, total_tokens, prompt/completion, total_turns, last_active, created_at, last_login, turn_cap, turns_used, subscription_status, subscription_until, turn_bonus, period_turns_used, revenue (egen), tts_usage (calls/api/chars/tokens/seconds), char_creation, image_gen_calls, deleted_campaigns
- Refaktorera: extrahera gemensam `_user_stat_row(username, udata, scan)` från admin-loopen (DRY) — används av både admin/stats och /api/me/stats.

**Frontend (adventure.html):**
- Gear-menyn (L363-372): ny rad `🪞 Profile` → öppnar modal med statistik.
- Modalen: samma layout-språk som adminvyns detaljkort (mörkt tema, gold accents), progress-bar för turns_used/turn_cap, tier-badge, tokens, TTS, kampanjer, skapad/senast aktiv.
- Hämta via `fetch('/api/me/stats')` med credentials.

**Tester:** /api/me/stats utan token → 401; som spelare → korrekt data + INGA fält ip/country; admin ser samma (sin egen). Ingen möjlighet att ange annan användare (endpoint tar ingen user-param).

---

## Spår D — Stripe checkout + webhook (live, testa flödet)

**Förutsättning (svar på "behöver du något mer?"):**
- ✅ Live secret key finns (verifierad: /v1/balance OK, konto i SEK)
- ⏳ Webhook-secret: skapas när webhook-endpointen registreras via API → `POST /v1/webhook_endpoints` med URL `https://dnd.rostad.cc/api/stripe/webhook` + events `checkout.session.completed`, `customer.subscription.deleted`, `invoice.paid` → svaret innehåller `secret` → spara i `.env.stripe`
- ⏳ Price IDs: skapas via API (`POST /v1/products` + `/v1/prices`) — tier1 3€/mån, tier2 9€/mån, lifetime 100€ engång (recurring vs one_time)
- Stripe CLI installeras EJ (interaktiv login) — tester körs med konstruerade event + `stripe.WebhookSignature` mot en test-secret (eller live-secret när den finns)

**Backend (main.py):**
- `POST /api/billing/checkout` (inloggad) `{tier}` → skapa Checkout Session `mode=subscription|payment`, `success_url`/`cancel_url` → returnera `{url}`. Klienten redirectar (server-driven, ingen secret i klient).
- `POST /api/stripe/webhook` (ingen auth, Stripe signerar) → verifiera signatur med `STRIPE_WEBHOOK_SECRET` → `checkout.session.completed` → uppdatera users.json (subscription_status=tier, subscription_until, stripe_customer_id, stripe_subscription_id, turn_cap via befintlig tier-logik) + `_append_tier_log` (befintlig!) + ledger (befintlig _ledger_append) → `customer.subscription.deleted` → demote till free.
- Stripe-anrop: använd `stripe`-paketet? Kräver install i Docker-image (Dockerfile). Alternativt rå REST via httpx (ingen ny dep). **Beslut: rå REST via httpx** (redan beroende) — mindre Docker-ändring, strippade headers.
- Prices hämtas från env (`STRIPE_PRICE_TIER1` etc.) — skapas i setup-steget.
- **Aldrig** ge åtkomst i checkout-svaret — bara via webhook.

**Tester (autouse):**
- checkout utan inloggning → 401; checkout okänd tier → 400; checkout giltig → `{url}` innehåller `checkout.stripe.com` (mocka Stripe-REST)
- webhook utan/med fel signatur → 400/401
- webhook `checkout.session.completed` (mockad, korrekt signerad) → users.json uppdaterad till tier + loggpost + ledger-rad
- `customer.subscription.deleted` → free
- Ingen data-ändring utan korrekt signatur

**Setup-steg (körs av mig):**
1. Skapa produkter/priser via API → fyll `.env.stripe`
2. Skapa webhook-endpoint via API → fyll `STRIPE_WEBHOOK_SECRET`
3. Deploy + kör tester + manuell live-check: skapa checkout-session, verifiera URL + webhook-mottagning (utan att slutföra betalning)

---

## Ordning & leverans

1. **B** (backup) — snabbast, oberoende → görs först
2. **A** (mail-reset) — kräver Bridge-fix först
3. **C** (profil) — oberoende backend+frontend
4. **D** (stripe) — sist (kräver setup-steg + live-verifiering)

Varje spår: implementera → autouse-tester → `pytest` (hela sviten grön) → deploy (docker cp / rebuild) → live-verifiering → commit+push (aldrig data-filer).
