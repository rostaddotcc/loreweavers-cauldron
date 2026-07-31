# 🐉 Mörkrets Rike — Projektdokumentation

> Senast uppdaterad: 2026-07-30 · 117 commits · Pre-1.0

## Översikt

Mörkrets Rike är en LLM-driven D&D Dungeon Master. Spelaren pratar med en AI-DM som narrerar fritt, spelar NPCs, och bygger världen dynamiskt. En separat **Guardian** hanterar all mekanik (tärningar, skada, XP, föremål, quests) så att DM:n kan fokusera helt på berättelsen.

- **URL**: https://dnd.rostad.cc
- **Repo**: github.com/rostaddotcc/morkrets-rike (privat till 1.0)
- **Docker**: port 8092, container `morkrets-rike`
- **Admin**: admin / rostad2026

---

## Designfilosofi

- **Inget hårdkodat innehåll** — världen växer fram ur spelet, inga fördefinierade platser/NPCs
- **DM:n är fri** — prompten är temafri/kreativ, inte låst till mörk fantasy
- **Frontend: Castlevania × DOS × terminal** — pixel-sprites, scanlines, terminal-grönt+guld
- **Tärningskast ska vara spektakulära** — D20-stil, ~3s spänning, glitter vid nat 20, skärmskakning vid nat 1

---

## Arkitektur

```
Spelare → Frontend (vanilla JS) → FastAPI Backend → LLM (DM)
                                        ↓
                                   Guardian (bakgrund)
                                   ├── Pre-DM: kastdetektion
                                   └── Post-DM: mekanikextraktion
                                        ↓
                                   State (JSON per kampanj)
```

### Två-modellsprincipen

| Roll | Modell | Uppgift |
|------|--------|---------|
| **DM** | Qwen 3.8 Max | Narration, NPCs, världsuppbyggnad |
| **Guardian Pre-DM** | StepFun 3.7 Flash | Kastdetektion (<2s, reasoning_effort=high) |
| **Guardian Post-DM** | Qwen 3.8 Max | Mekanikextraktion (bakgrund, latens oviktig) |
| **Extraktion** | Qwen 3.6 Flash / StepFun 3.7 | Fakta, sammanfattningar, orakel |
| **Karaktärsgenerering** | Qwen 3.8 Max | Fullt karaktärsark från prompt |

### Guardian — Mekanisk väktare (guardian.py, 1 257 rader)

**Pre-DM** (`guardian_check_roll`): Körs FÖRE DM-anropet. Analyserar spelarens handling, avgör om tärningskast krävs, och returnerar en kast-begäran som skickas till spelaren INNAN DM narrerar.

**Post-DM** (`guardian_extract_mechanics` + `apply_mechanics`): Körs i BAKGRUND efter DM-svaret. Extraherar ALL mekanik ur narrationen:
- Skada/läkning, XP + level-up
- Föremål (add/remove/dedup med D&D-stats)
- Valuta, quests, NPCs (nya/relationer/anteckningar)
- Platser, tid, vila (kort/lång → HP), ny dag, loggbok

**Designprincip**: DM skriver INGA mekaniska taggar — Guardian äger mekaniken.

### Kontexthantering

Hybrid-modell: State + Summary + Recent + Archive
- System prompt: DM-persona + character_state.json + senaste summaries + ~15 meddelanden verbatim
- Varje 20:e drag → LLM-summary (3-5 meningar)
- State uppdateras efter varje drag (JSON)
- RAG med Qdrant (Phase 3) för långtidsminne

---

## Tech Stack

| Lager | Val |
|-------|-----|
| LLM | Qwen 3.8 Max (backbone), StepFun 3.7 Flash, DeepSeek, MiMo, Ollama |
| Frontend | Vanilla HTML/CSS/JS (inget build-steg), snes.css |
| Backend | Python 3.11 / FastAPI |
| State | JSON per kampanj |
| RAG | Qdrant (lokal) |
| Auth | JWT (24h expiry) |
| Deploy | Docker Compose, nginx reverse proxy (dnd.rostad.cc) |
| Ljud | 16-bit SFX + musik (Web Audio API) |

---

## Backend (7 726 rader)

| Fil | Rader | Ansvar |
|-----|-------|--------|
| main.py | 3 405 | FastAPI app, routes, DM-prompt, chat, kampanjer |
| guardian.py | 1 257 | Pre/Post-DM Guardian, kastdetektion, mekanikextraktion |
| extraction.py | 763 | LLM-baserad item/fact-extraktion |
| atmosphere.py | 668 | Atmosfärssystem (ljud, visuella effekter) |
| state_manager.py | 472 | Kampanjstate-hantering, export/import |
| rag.py | 448 | RAG med Qdrant, embedding, retrieval |
| models.py | 408 | Modellrouter (7 modeller, 4 providers) |
| locations.py | 121 | Platsregistrering |
| logbook.py | 85 | Loggbokssystem |
| auth.py | 55 | JWT-autentisering |
| dice.py | 44 | Tärningskast |

---

## Frontend (12 832 rader)

### Sidor
| Fil | Beskrivning |
|-----|-------------|
| login.html | Inloggning (Porten) |
| adventure.html | Vägskälet: Förbered / Importera / Nytt äventyr |
| newgame.html | Karaktärsskapande (Välj ditt öde) + modellval |
| chat.html | Huvudchatt (Vid bordet) — DM, NPCs, tärningar, Guardian-logg |
| character.html | Karaktärsark + item cards + valuta |
| npcs.html | NPC-kodex (Minnets hall) |
| admin.html | Admin-dashboard (spelare, tokens) |
| facts.html | Regel-orakel |
| loggbok.html | Kampanjlogg |
| platser.html | Platsregister |
| help.html | Hjälp |

### JS/CSS
- `snes.css` — Huvudstylesheet (Castlevania/DOS-tema)
- `api.js` — API-klient
- `i18n.js` — Språkstöd (SV/EN)
- `sprites.js` — Pixel-sprite-rendering
- `sfx.js` / `music.js` — 16-bit ljudeffekter och musik
- `modal.js` — Modala dialoger
- `fonts.js` — Typsnitt

---

## Funktioner (implementerade)

### Core
- ✅ Karaktärsskapande via LLM-prompt (arketyp eller fritt)
- ✅ Huvudchatt med DM-narration, färgade NPC-namn
- ✅ Tärningsceremoni (D20, 3s spänning, glitter/skakning)
- ✅ Modellval (7 modeller, byte i farten)
- ✅ Multi-kampanj (skapa, byta, namnge)
- ✅ Export/Import (.zip / .md/.pdf/bilder)

### Guardian & Mekanik
- ✅ Pre-DM kastdetektion (automatisk tärning vid behov)
- ✅ Post-DM mekanikextraktion (skada, XP, items, valuta, quests, NPCs, tid, vila)
- ✅ Item cards med D&D-stats (damage, AC, charges, rarity)
- ✅ XP-reform (endast strid/quest/milstolpe/pussel)
- ✅ NPC-relationer och anteckningar (automatiskt)
- ✅ Event cards i chatten (Guardian-logg synlig)

### UX
- ✅ Mobil UX (drawer, bottom nav, responsive, 100dvh)
- ✅ i18n (SV/EN, engelska default)
- ✅ 16-bit SFX + musik
- ✅ DM-footer (modell, tokens, tid)
- ✅ Modellgate (val innan äventyret startar)
- ✅ Admin-dashboard (spelare, token-användning)
- ✅ Dynamisk narrationslängd (kort för action, lång för bakgrund)

---

## Fas-status

| Fas | Status | Innehåll |
|-----|--------|----------|
| **Phase 1** | ✅ Klar | Core: DM, chat, karaktär, auth, export |
| **Phase 2** | ✅ Klar | Guardian, items, dice, mobile, i18n, admin |
| **Phase 3** | 🔄 Pågående | RAG (Qdrant), fact register, extraction model |
| **Framtid** | 💭 Planerad | Multi-user, kostnadskontroll, onboarding, kommersialisering |

---

## Multi-user design (diskuterad, ej implementerad)

- Session seed med kampanjkod
- Delat kampanj-state, per-spelare karaktärs-state
- Tre turordningslägen: fri chat, DM-initierad, initiativ-runda
- MVP: 2 spelare, fri chat, delad kampanj

---

## Kända problem & Backlog

- `PROSE_ITEM_PATTERN` saknar vanliga verb (hittar, köper, tar) → items kan missas
- Hårdkodad noun-lista saknar många D&D-föremål
- Tre tags (FÖREMÅL_BORT, NPC_RELATION, NY_DAG) parsas men DM känner inte till dem
- Saknar auto-triggered chapter summaries
- Weather och temp HP oanvänt
- Multi-user ej implementerat
- Kostnadskontroll för kommersialisering saknas
- Onboarding för nya spelare saknas

---

## Deploy

```bash
# Bygg och starta
cd ~/dnd-llm && docker compose up -d --build

# Health check
curl -s http://localhost:8092/health | python3 -m json.tool

# Loggar
docker logs -f morkrets-rike --tail 50

# Nginx proxy: dnd.rostad.cc → localhost:8092
# proxy_read_timeout=300s (långa DM-svar)
```

---

## Miljövariabler (.env)

| Variabel | Beskrivning |
|----------|-------------|
| DASHSCOPE_API_KEY | Qwen/Alibaba (backbone) |
| DEEPSEEK_API_KEY | DeepSeek |
| MIMO_API_KEY | MiMo (Xiaomi) |
| OLLAMA_BASE_URL | Lokal Ollama (localhost:11434) |
| QWEN_DEFAULT_MODEL | qwen3.8-max |
| GUARDIAN_MODEL | Modell för Guardian |
| ATMOSPHERE_MODEL | qwen3.6-flash |
| JWT_SECRET | Auth-hemlighet |
| ADMIN_USER / ADMIN_PASSWORD | Admin-konto |

---

## Licens

MIT (vid 1.0-release). Privat repo till dess.
