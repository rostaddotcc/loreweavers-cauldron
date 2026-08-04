# 🐉 The Lore Weaver's Cauldron

> A conversational D&D 5e game where a large language model is your Dungeon Master.
> Speak, roll, fight, and explore a dark fantasy world that remembers everything you do.

**Status:** 🔧 Pre-1.0 · active development · **License:** MIT · **Stack:** Python 3.11 / FastAPI · Vanilla JS (no build step)

The Lore Weaver's Cauldron is a single-player, browser-based D&D 5e campaign engine. Instead of a rulebook and a dice tower, you get a living table: an LLM weaves the narration, plays every NPC, and reacts to whatever you type — while a dedicated *Guardian* module silently handles all the mechanics (dice, damage, XP, items, gold, quests) so the story never has to stop for bookkeeping.

The game speaks **Svenska and English** (campaign-aware, chosen when you start a campaign), carries a retro terminal aesthetic, and keeps a persistent memory of your adventures — facts, NPCs, places, and quests survive across sessions.

---

## ✨ Features

### 🗣️ Conversational Dungeon Master
- Full LLM-driven DM that narrates scenes, plays NPCs with colored names, and reacts to free-form input
- **`@NPC` direct chat** — address any known NPC by name and the DM role-plays them with their own context (personality, relation, memories)
- **Oracle rule-lookups** — ask rules questions in a sidebar without breaking the scene
- **Streamed narration** — tokens appear as the DM "speaks"

### 🎲 Dice & Combat
- Full **dice engine** (`NdX±M` notation) with a dramatic d20 animation — gold flash on a natural 20, blood on a natural 1
- **Turn-based combat engine** with initiative order, action economy (action / bonus action / reaction), status effects with durations, enemy AI that rolls against your AC, allies (`ALLIERAD:`), and flee attempts
- Combat actions: **attack · cast · bonus · flee · end-turn** — the engine owns the math, the DM owns the narration

### 🧙 Character Creation
- Pick from a roster of **hand-crafted archetypes** (the Fallen Knight, the Ash Witch, the Hunter, the Void Scribe…) or write your own prompt
- The LLM weaves a full **character sheet** (stats, HP, AC, saves, traits, equipment, backstory) as JSON per `state-schema.json`
- **Character vault** — save characters, inspect them, generate avatars, load them into any campaign
- Templates are fully bilingual (SV/EN)

### 🏰 World, NPCs & Memory
- **NPC codex** — a living registry of every NPC: colors, icons, conversations, meeting places, quests, trade, and trust
- **Facts register** — structured, deduplicated, versioned lore extracted from every DM reply (categories: npc, location, item, event, promise, world, relationship), injected back into the DM's context
- **Quest tracker**, **logbook** (an LLM-written day-by-day adventure journal), **pin notes**, and **lore entries**
- **Campaign usage panel** — token spend per player and per model, turn counts, TTS minutes

### 🗺️ Places & Travel
- Dynamic, seeded map with **fog of war**, quest markers, and a glowing "current location"
- Realistic **travel times** by terrain (`väg 0.5 · stig 0.8 · slätt 0.6 · hav 0.4 · skog 1.2 · berg 1.8 · träsk 1.5 · is 1.4 · okänd 1.0`; travel time = distance ÷ 10 × modifier)
- Places are placed deterministically from the campaign seed — the same place always lands on the same spot

### 🧠 RAG Memory (retrieval-augmented generation)
- Every transcript is chunked, embedded (**nomic-embed-text**, 768-dim, via local Ollama) and indexed into **Qdrant** (collection `loreweavers_cauldron`)
- Before each turn, relevant memories are retrieved and injected into the DM's system prompt — the world truly remembers
- Deterministic content-hash IDs prevent duplicate indexing

### 🔮 Models & Voice
- **Multi-provider model router**: Qwen (DashScope / Alibaba Token Plan), DeepSeek, MiMo (Xiaomi), StepFun, and local **Ollama** models — switch the DM's brain per campaign, mid-game
- **TTS narration**: StepFun voices (always free) or Qwen TTS — male/female narrator voices, per-campaign settings, style phrases
- Keys never leave the server — the frontend only ever sees model IDs

### 💳 Billing & Admin
- **Stripe subscriptions**: free tier (50 turns/day, step-3.7-flash only), tier1 (3 €/mo — 50 turns per 6 h + AI avatars), tier2 (9 €/mo — all player models + Qwen TTS), **lifetime** (100 €, uncapped); StepFun TTS is always free
- Password reset flow via mail bridge, **promo endpoint** for time-limited offers
- **Admin dashboard** with SVG charts: token spend, players by country, role split, TTS minutes; per-user controls (turn caps, top-ups, resets, subscriptions)
- **IP geolocation** of players (private/LAN IPs are never sent anywhere) to flag abuse
- **Feedback inbox** and a full **billing ledger** (MRR, transactions per user)

### 📦 Import · Export · i18n
- **World import** — upload `.md`, `.pdf`, or images and Qwen extracts characters, NPCs, and places
- **Campaign export** as a structured archive (transcript, character sheets, attachments) + save/load slots
- **Bilingual UI** (SV/EN) with theme and sound settings; retro `snes.css` terminal theme, custom fonts and sprites
- Backend serves the frontend statically — **no frontend build step**, cache-busting via `?v=` params

---

## 🏗️ Architecture

The core idea: **the DM tells the story, the Guardian owns the mechanics, and the Extraction layer remembers.** One turn looks like this:

```
  Player message
       │
       ▼
┌───────────────────────────────────────────────┐
│  GUARDIAN — pre-DM check (guardian_check_roll) │  ◀─ is a dice roll needed?
└───────────────────┬───────────────────────────┘     (returns a roll request
                    │                                 BEFORE the DM narrates)
                    ▼
┌───────────────────────────────────────────────┐
│  DM — LLM narration (streamed)                │  ◀─ RAG memories + relevant
│  qwen3.8-max · deepseek · mimo · ollama ·     │     facts injected into the
│  step-3.7-flash                               │     system prompt
└──────┬──────────────────────┬─────────────────┘
       │                      │
       ▼                      ▼
┌────────────────────────────────┐
│  GUARDIAN — post-DM extraction  │  ◀─ [SKADA:12] damage,
│  → state.json (single source    │     [GULD:15] gold,
└───────────────┬────────────────┘     [XP:], [FÖREMÅL:] items,
                ▼                     [PLATS:namn] places
┌───────────────────────────────────────────────┐
│  EXTRACTION — facts → FactRegister            │  ◀─ npc · location · item ·
│  (deduplicated + versioned, injected next     │     event · promise · world ·
│   turn so the DM never contradicts itself)    │     relationship
└───────────────────────┬───────────────────────┘
                        ▼
┌───────────────────────────────────────────────┐
│  RAG — transcript chunked + embedded          │  ◀─ nomic-embed-text (768-dim)
│  → Qdrant collection "loreweavers_cauldron"   │     via local Ollama
└───────────────────────────────────────────────┘

  Combat runs alongside: combat.py owns initiative, action economy,
  status effects and enemy AI; the Guardian extracts, the DM narrates.
```

| Module | Role |
|---|---|
| `backend/main.py` | FastAPI app — all routes, auth & tiers, DM prompt construction, streaming |
| `backend/guardian.py` | Mechanics authority — pre-DM roll checks + post-DM extraction of damage, XP, items, currency, quests, time, rest, places, logbook entries |
| `backend/combat.py` | Combat engine — turn order, action economy, status effects, enemy AI, allies, fleeing |
| `backend/extraction.py` | `FactRegister` — structured, deduplicated, versioned lore/facts |
| `backend/rag.py` | Qdrant + Ollama — transcript/lore indexing and semantic retrieval |
| `backend/state_manager.py` | JSON persistence — campaigns, saves, vaults, rolling summaries (scene → chapter → arc) |
| `backend/models.py` | Model router — provider configs & keys read from env, **never** exposed to clients |
| `backend/auth.py` | JWT (HS256) + bcrypt against `data/users.json` |
| `backend/locations.py` | Dynamic seeded map, deterministic placement, terrain travel times |
| `backend/logbook.py` | LLM-generated day-by-day adventure journal |
| `backend/dice.py` | Dice notation parser (`NdX±M`) |
| `backend/iplog.py` | IP geolocation for the admin dashboard (private IPs never leave the server) |

---

## 📁 Project Structure

```
loreweavers-cauldron/
├── backend/                       # FastAPI application (Python 3.11)
│   ├── main.py                    # ~8.9k lines — app, all endpoints, DM prompt build
│   ├── guardian.py                # Mechanics extraction (pre/post DM)
│   ├── combat.py                  # Combat engine
│   ├── extraction.py              # Facts register (FactRegister)
│   ├── rag.py                     # Qdrant + Ollama vector memory
│   ├── state_manager.py           # Campaign / vault JSON persistence
│   ├── models.py                  # LLM model router (keys stay server-side)
│   ├── auth.py · iplog.py
│   ├── locations.py · logbook.py · dice.py
│   ├── requirements.txt · .env.example
│   ├── data/                      # Runtime data (git-ignored): campaigns/, vaults/,
│   │                              #   users.json, billing ledger, geo cache
│   └── tests/                     # 15 pytest suites (see Testing)
├── frontend/                      # Vanilla HTML/CSS/JS — served statically, no build step
│   ├── login.html · reset.html · index.html (→ login)
│   ├── adventure.html             # Campaign hub: continue / import / new game
│   ├── newgame.html · characters.html · character.html
│   ├── chat.html                  # Main game table (~6.7k lines)
│   ├── npcs.html · platser.html   # NPC codex · map & travel
│   ├── facts.html · loggbok.html  # Facts register · adventure journal
│   ├── mechanics.html             # Engine diagnostics, tag list, travel table
│   ├── models.html · pricing.html · admin.html · releases.html · help.html
│   ├── api.js                     # Frontend ↔ backend bridge (+ standalone MOCK mode)
│   ├── archetypes.js · i18n.js · themes.js · fonts.js · sprites.js
│   ├── sfx.js · modal.js · embed.js · snes.css
│   └── assets/ · vendor/          # Logo/cauldron art · legacy three.js
├── docs/                          # Architecture (arkitektur.html, kodex.html) + specs
│                                  #   (combat, design polish, monetization, Stripe, audit…)
├── scripts/                       # DOM-level test scripts (combat split, dice render)
├── docker-compose.yml             # 8092:8090 · ./backend/data volume · healthcheck
├── Dockerfile                     # python:3.11-slim + libmupdf-dev (PyMuPDF)
├── state-schema.json              # JSON schema for campaign state
└── LICENSE                        # MIT
```

Root-level `*.md` files (ARCHITECTURE.md, BACKLOG.md, BRAINSTORM.md, …) are historical planning documents kept for reference.

---

## 🚀 Quickstart

### 🐳 Docker (recommended)

```bash
# 1. Create your environment file and fill in API keys + a strong JWT secret
cp backend/.env.example backend/.env
#    edit backend/.env  →  DASHSCOPE_API_KEY, JWT_SECRET, ADMIN_PASSWORD, …

# 2. Create the shared network used to reach Qdrant (skip if it already exists)
docker network create ai-services

# 3. Build and start
docker compose up -d
docker compose logs -f        # watch it boot
```

Open **http://localhost:8092/login.html** — the host port **8092** maps to the container's **8090**. Register a normal account, or sign in with the admin account (`ADMIN_USER` / `ADMIN_PASSWORD`, created automatically at first start).

> **RAG memory** activates automatically when Qdrant (on the shared `ai-services` network) and Ollama with `nomic-embed-text` are reachable. Without them the game runs fine — it simply plays without vector memory.

### 💻 Local development (no Docker)

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # fill in keys
uvicorn main:app --host 0.0.0.0 --port 8090 --reload
```

FastAPI serves the frontend itself, so the game lives at **http://localhost:8090/login.html**. For pure frontend work, `frontend/api.js` ships a **MOCK mode** (`MOCK = true`) that lets every page run standalone against `localStorage`.

---

## ⚙️ Configuration

All configuration lives in environment variables (`backend/.env` for the app, `backend/.env.stripe` for billing — both loaded by docker-compose).

| Variable | Required | Description |
|---|---|---|
| `ADMIN_USER` / `ADMIN_PASSWORD` | ✅ | Bootstrap admin account, created at first start (password bcrypt-hashed in `data/users.json`) |
| `DASHSCOPE_API_KEY` | ✅ | Qwen / DashScope (Alibaba Token Plan) — default DM provider |
| `QWEN_BASE_URL` | | DashScope OpenAI-compatible base URL (sensible default provided) |
| `QWEN_DEFAULT_MODEL` | | Documented default Qwen DM model (see `.env.example`) |
| `DEEPSEEK_API_KEY` | | DeepSeek provider key |
| `DEEPSEEK_BASE_URL` | | DeepSeek API base URL (default provided) |
| `MIMO_API_KEY` | | MiMo (Xiaomi) provider key |
| `MIMO_BASE_URL` | | MiMo API base URL (default provided) |
| `STEPFUN_API_KEY` | | StepFun key — free-tier DM model + always-free TTS |
| `STEPFUN_BASE_URL` | | StepFun Step Plan base URL (default provided) |
| `OLLAMA_BASE_URL` | | Local Ollama chat-completions endpoint (`http://localhost:11434/v1`; in Docker: `http://host.docker.internal:11434/v1`) |
| `OLLAMA_URL` | | Ollama host used for RAG embeddings (`http://localhost:11434`) |
| `QDRANT_URL` | | Vector database URL for RAG (`http://localhost:6333`; in Docker: `http://qdrant:6333`) |
| `JWT_SECRET` | ✅ | Signs auth tokens — **change this to something long and random** |
| `JWT_EXPIRY_HOURS` | | Auth token lifetime in hours (default `24`) |
| `GUARDIAN_MODEL` | | Model for mechanics extraction (default `step-3.7-flash`) |
| `EXTRACTION_MODEL` | | Model for facts extraction (default `step-3.7-flash`) |
| `TTS_PROVIDER` | | `stepfun` (default, always free) or `qwen` |
| `TTS_VOICE_MALE` / `TTS_VOICE_FEMALE` | | Narrator voice IDs (defaults `longanlufeng` / `longanlingxin`) |
| `TTS_DASHSCOPE_KEY_ENV` | | Env var holding the Qwen TTS key (default `DASHSCOPE_API_KEY`) |
| `HOST` / `PORT` | | Uvicorn bind address/port (default `0.0.0.0:8090`) |
| `COOKIE_SECURE` | | Set `1` behind HTTPS (Cloudflare/nginx) to add the `Secure` flag to the auth cookie |
| `STRIPE_SECRET_KEY` | (billing) | Stripe API key — loaded from `backend/.env.stripe` |
| `STRIPE_WEBHOOK_SECRET` | (billing) | Stripe webhook signing secret |
| `STRIPE_PRICE_LIFETIME` / `STRIPE_PRICE_LIFETIME_PROMO` | (billing) | Lifetime-plan price IDs (regular + promo) |
| `STRIPE_PUBLIC_BASE` | (billing) | Public base URL for Stripe redirects |

---

## 🔌 API Overview

All endpoints live under `/api` and are served by FastAPI (interactive docs at `/docs` when running). This is a brief map — not exhaustive.

| Group | Endpoints | Purpose |
|---|---|---|
| **Auth** | `POST /api/register` · `/api/login` · `/api/logout` · `/api/auth/request-reset` · `/api/auth/reset-with-token` · `GET /api/me` · `PUT /api/me/appearance` · `PUT /api/me/email` | Accounts, JWT cookie sessions, password reset, profile |
| **Campaign** | `POST/GET /api/campaign` · `GET /api/campaigns` · `POST /api/campaign/activate` · `DELETE /api/campaign` · `PATCH /api/campaign/{dm-model,guardian-model,extraction-model,language,character,inventory}` · `POST /api/campaign/save` · `GET /api/campaign/saves` · `POST /api/campaign/load` | Create, switch, configure, and persist campaigns |
| **Gameplay** | `POST /api/chat` (streamed) · `POST /api/oracle` · `POST /api/dice` · `POST /api/campaign/pin` · `POST /api/campaign/lore` · `POST /api/campaign/chapter` · `POST /api/campaign/consume-resource` · `GET /api/facts` | Play: chat, rule lookups, dice, notes, lore, facts |
| **Combat** | `POST /api/combat/attack` · `/cast` · `/bonus` · `/flee` · `/end-turn` · `GET /api/combat/state` | Turn-based combat actions |
| **Character & Vault** | `POST /api/character/generate` (+ `/stream`) · `GET/POST/DELETE /api/vault/characters…` · `…/use` · `…/avatar/generate` | Character creation and vault |
| **World** | `POST /api/world/build` · `GET /api/campaign/locations` · `GET /api/campaign/logbook` · `POST /api/campaign/logbook/refresh-today` | Import `.md/.pdf/images`, map, journal |
| **Attachments & Avatars** | `POST/GET/DELETE /api/campaign/attachments…` · `POST /api/campaign/avatar…` · `POST /api/campaign/avatar/generate` | Uploaded world material and hero/NPC art |
| **TTS** | `GET /api/tts/voices` · `POST /api/tts` · `POST /api/campaign/tts-settings` | Voice selection and narration audio |
| **Billing** | `POST /api/billing/checkout` · `/api/billing/portal` · `POST /api/stripe/webhook` · `GET /api/promo` | Subscriptions and lifecycle |
| **Admin** | `GET /api/admin/stats` · `/api/admin/billing` · `/api/admin/feedback` · `GET/PUT/DELETE /api/admin/user…` | Dashboard, ledger, user controls |
| **System** | `GET /api/health` · `GET /api/debug/logs` · `GET /api/models` | Health check, debug log ring buffer, model list |

---

## 🧪 Testing

```bash
cd backend
source .venv/bin/activate
python -m pytest tests/ -v
```

**15 pytest suites** cover the mechanics that matter: tier logic and free-tier caps, Stripe billing + billing admin, security hardening, NPC chat, password reset, TTS style & survival across deletions, combat allies, vault export overwrite, avatar spells, feedback inbox, `/api/me` stats, and the travel/system-prompt rules.

DOM-level frontend tests live in `scripts/` (`test-combat-split-dom.js`, `test-enemy-dice-render.js`) for combat UI behavior.

---

## 🛡️ Security Notes

- **API keys never leave the server.** The model router maps frontend model IDs → provider configs; the models endpoint strips keys, base URLs, and internal names.
- **Passwords are bcrypt-hashed** in `data/users.json`; the admin account is bootstrapped from env at first start.
- **JWT (HS256) in an auth cookie** (`credentials: 'include'`); set `COOKIE_SECURE=1` behind HTTPS (Cloudflare/nginx) to enable the `Secure` flag — the production compose file does this.
- **Path traversal is blocked** — campaign and character IDs are server-generated and regex-validated before touching the filesystem.
- **IP geolocation is privacy-safe** — private/LAN/loopback addresses are flagged as local and never sent to the geo lookup API.
- **Stripe webhooks are signature-verified**, and the billing ledger is stored locally for auditing.
- CORS is restricted to the public origin (no wildcard + credentials).

---

## 🔐 Self-Hosting

Everything runs from a **single Docker image**. Your entire world persists in one volume:

```
./backend/data/
├── campaigns/     # per-user campaign state, transcripts, summaries
├── vaults/        # saved characters
├── users.json     # accounts (bcrypt) + billing status
├── _billing_ledger.json
└── ip_geo.json    # geolocation cache
```

Optional companions for vector memory: **Qdrant** on the shared `ai-services` Docker network (or any reachable `QDRANT_URL`) and **Ollama** with `nomic-embed-text` for embeddings. Point the env vars at them and RAG switches on — no code changes. Put the container behind nginx or Cloudflare for HTTPS, set `COOKIE_SECURE=1`, and you have a production instance.

---

## 📜 License

[MIT](LICENSE) — Copyright (c) 2026 rostad (rostad.cc).

This repository is the codebase of **loreweavers-cauldron** (formerly *morkrets-rike*). It is planned to be fully open-sourced at the 1.0 release; until then it is published for transparency and collaboration.

---

*Roll well — and mind what the Cauldron foretells.* ⚗️
