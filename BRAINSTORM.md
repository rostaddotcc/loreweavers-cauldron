# 🐉 D&D LLM Dungeon Master

En webbapp där spelaren pratar med en LLM som agerar Dungeon Master.
Bygger och spelar D&D-äventyr i realtid.

## Status: Brainstorm-fas

---

## 🎯 Core Features (MVP)

### 1. Chat-baserat DM-interface
- LLM som DM — narrativ, NPCs, miljöbeskrivningar
- Spelaren skriver fritt (inte menyval)
- DM:n anpassar tonen: stämningsfull, beskrivande, konsekvensdriven
- "DM-minne" — ihågkommen kampanj, NPCs, tidigare händelser

### 2. Karaktärsskapande
- Guidad karaktärsgenerering via chat ("Vill du vara en modig krigare eller en slug magiker?")
- Ras, klass, bakgrund, alignment
- Förmågor, HP, AC, saves automatiskt beräknade
- Karaktärsblad alltid synligt (sidebar/panel)

### 3. Tärningskast
- LLM:n begär kast: "Rulla en d20 för att se om du smyger förbi vakten"
- Visuella tärningar (animation?)
- LLM:n tolkar resultatet narrativt
- Fusk-skydd? (server-side rolls vs client-side)

### 4. Stridssystem
- Initiativordning
- Turordningsbaserad strid i chatten
- HP-spårning, attacker, skada
- Fiende-statblocks genererade av DM:n
- Karta? (rutnät, enkel ASCII eller visuell?)

---

## 🔮 Extended Features

### 5. Världsbyggande
- Spelaren och DM:n bygger världen tillsammans
- Platser, fraktioner, lore
- "Världsbok" som LLM:n refererar till (RAG/context injection)
- Kartor (genererade? handritade? ASCII?)

### 6. Kampanjhantering
- Spara/fortsätt kampanjer
- Flera karaktärer per spelare (party?)
- Session-loggar / äventyrsjournal
- "Förra gången i..."-sammanfattningar

### 7. NPC-system
- DM:n skapar NPCs med personlighet, mål, hemligheter
- NPC-relationer (allierade, fiender, neutrala)
- NPCs ihågkommer spelarens handlingar

### 8. Inventory & Ekonomi
- Föremål, guld, utrustning
- Köpa/sälja i butiker (DM-driven)
- Magiska föremål med beskrivningar
- Vikt/bärkapacitet? (eller håll det enkelt)

### 9. Multiplayer (stretch goal)
- Flera spelare i samma kampanj
- DM:n hanterar flera karaktärer
- Turordning i strid med flera spelare
- Delad karta / delat chatrum

---

## 🛠️ Tekniska frågor att bestämma

| Fråga | Alternativ |
|-------|-----------|
| LLM-provider | Local (Ollama), API (DeepSeek, Qwen), eller valbart? |
| Frontend | Vanilla JS? React? Svelte? |
| Backend | Python (FastAPI)? Node? |
| State management | Server-side sessions? LocalStorage? DB? |
| Tärningar | Client-side (snabbt) eller server-side (fuskfritt)? |
| Design | Terminal/mörk fantasi? Minimalistisk? Pixel art? |
| Språk | Svenska? Engelska? Båda? |

---

## 💡 Idéer / Önskelista (brainstorm)

### 🌱 Multiplayer via delad seed (FRAMTIDA — kräver design)
**Koncept:** Varje äventyr genereras från en "seed" (t.ex. `ASKANS-DAL-7X42`). Flera spelare kan ange samma seed och hamna i samma värld, med samma NPCs, platser, och öppningsscen — men med egna karaktärer och egna val.

**Möjlig arkitektur:**
- Seed → deterministisk världsgenerering (LLM + seed → samma NPCs/platser/lore)
- Delad kampanjstate (flera karaktärer i samma state.json)
- Turordning: spelare skriver, DM svarar till alla
- Varje spelare har egen karaktär men delar värld, NPCs, quests

**Öppna frågor att fundera på:**
- Hur synkas tärningskast mellan spelare?
- Kan spelare gå åt olika håll i världen? (split party)
- Hur hanteras "en spelare offline" medan andra spelar?
- Seed-format: slumpad sträng? Delbar länk? (`dnd.rostad.cc/join/ASKANS-DAL-7X42`)
- Räcker det med samma prompt + seed för att LLM:n ska generera samma värld?
- Eller behöver vi en "världsmall" som genereras en gång och delas?

**Status:** Idé — behöver designas innan implementation.

- [ ] Ljud/musik — stämningsmusik som ändras med scenen
- [ ] Bildgenerering — DM:n genererar plats/NPC-bilder
- [ ] Röst — TTS för DM:ns narration
- [ ] Exportera äventyr som PDF
- [ ] "Död" — permadeath eller respawn?
- [ ] Erfarenhetspoäng & level-up i chatten
- [ ] Slumpmässiga encounters (tabeller)
- [ ] Spellista per klass (LLM:n kan reglerna)
- [ ] Husregler — spelaren kan definiera egna regler
- [ ] "DM-läge" — en spelare blir DM, LLM:n assisterar

---

## 📁 Projektstruktur (förslag)

```
dnd-llm/
├── BRAINSTORM.md          ← du är här
├── README.md
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js
├── backend/
│   ├── main.py            ← FastAPI server
│   ├── dm_engine.py       ← LLM-prompter, DM-logik
│   ├── dice.py            ← Tärningssystem
│   ├── character.py       ← Karaktärsmodeller
│   └── world.py           ← Världsstate, NPCs, lore
└── data/
    ├── rules/             ← D&D 5e-regler (referens)
    ├── templates/         ← Karaktärsmallar, klasser
    └── campaigns/         ← Sparade kampanjer
```
