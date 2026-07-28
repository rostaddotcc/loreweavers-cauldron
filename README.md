# 🐉 Mörkrets Rike — AI Dungeon Master

En LLM-driven D&D Dungeon Master i mörk fantasy. Prata med en AI som narrerar,
spelar NPCs, slår tärningar och bygger världen tillsammans med dig.

> **Status: Pre-1.0 — aktiv utveckling.** Frontend-prototyper fungerar, backend på gång.

## ✨ Funktioner

- **🧙 Karaktärsskapande via prompt** — välj en arketyp eller skriv fritt, LLM:n genererar ett fullt karaktärsark
- **💬 En huvudchatt** — DM-narration, NPCs med färgade namn, tärningskast, regel-orakel i sidopanel
- **📖 Minnets hall** — NPC-kodex med konversationer, mötesplatser, quests, handel och förtroende
- **🎒 Karaktärsark** — HP/spell slots/XP, inventory, valuta
- **🔮 Modellval** — byt LLM i farten (Qwen, DeepSeek, MiMo, lokal Ollama)
- **📦 Export** — kampanj som strukturerad .zip (transkript, karaktärsark, bilagor)
- **📥 Import** — .md/.pdf/bilder → Qwen extraherar karaktärer/NPCs/platser
- **🔑 Enkel auth** — username/password, nycklar stannar på servern

## 🏗️ Tech-stack

| Lager | Val |
|-------|-----|
| LLM | Qwen (backbone), DeepSeek, MiMo, Ollama |
| Frontend | Vanilla HTML/CSS/JS (inget build-steg) |
| Backend | Python / FastAPI |
| State | JSON per kampanj |
| Bildanalys | Qwen Vision |

## 📁 Struktur

```
dnd-llm/
├── frontend/
│   ├── login.html        ← Inloggning (Porten)
│   ├── adventure.html    ← Vägskälet: Förbered / Importera / Nytt äventyr
│   ├── newgame.html      ← Karaktärsskapande (Välj ditt öde)
│   ├── chat.html         ← Huvudchatt (Vid bordet)
│   ├── character.html    ← Karaktärsark + inventory + valuta
│   └── npcs.html         ← NPC-kodex (Minnets hall)
├── backend/
│   ├── models.py         ← LLM model router (nycklar ur .env)
│   └── .env.example      ← Mall för API-nycklar
├── ARCHITECTURE.md       ← Arkitektur & beslut
├── BRAINSTORM.md         ← Feature-idéer
├── MARKNAD.md            ← Marknadsanalys
└── state-schema.json     ← JSON-schema för kampanjstate
```

## 🚀 Kom igång

### Docker (rekommenderat)

```bash
# 1. Skapa .env med dina API-nycklar
cp backend/.env.example backend/.env
# Redigera backend/.env — fyll i DASHSCOPE_API_KEY etc.

# 2. Starta
docker compose up -d

# 3. Öppna
# → http://localhost:8092/login.html
```

**Port: 8092** (8090=beszel, 8091=upptagen, 8096=jellyfin)

Admin-konto: `admin` / `rostad2026` (ändra i `backend/.env`)

### Utan Docker

```bash
# Frontend — öppna direkt i webbläsaren
cd frontend && python3 -m http.server 8090

# Backend
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8090
```

## 🔐 Säkerhet

API-nycklar läses ur `backend/.env` (committas aldrig). Frontend ser aldrig nycklar —
bara modell-ID:n. `list_models_for_frontend()` returnerar enbart publikt synlig info.

## 📜 Licens

Kommer släppas under en open source-licens vid 1.0. Se [LICENSE](LICENSE).
