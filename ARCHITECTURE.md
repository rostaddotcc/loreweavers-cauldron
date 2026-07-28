# 🐉 D&D LLM Dungeon Master — Arkitektur & Beslut

## Tech-stack (beslutat)

| Lager | Val | Anledning |
|-------|-----|-----------|
| **LLM** | Qwen (via API) | Back-bone, vision-stöd för bilduppladdning |
| **Frontend** | Vanilla HTML/CSS/JS | Enkelt, inga build-steg, lätt att iterera |
| **Backend** | Python (FastAPI) | Enkel, snabb, bra LLM-integration |
| **State** | JSON-filer per kampanj | Maskinläsbart, kompakt, versionshanterbart |
| **Bildanalys** | Qwen Vision | Spelaren laddar upp kort → Qwen ger feedback / skapar karaktärsark |

## Kontexthantering (beslutat)

### Hybrid-modell: State + Summary + Recent + Archive

```
┌─────────────────────────────────────────────────┐
│  SYSTEM PROMPT (injectas varje drag)            │
│                                                 │
│  1. DM-persona + regler                         │
│  2. character_state.json (kompakt)              │
│  3. Senaste 2-3 summaries                       │
│  4. Senaste ~15 meddelanden (verbatim)          │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│  ARCHIVE (läses ej av LLM, bara export)         │
│                                                 │
│  sessions/2026-07-28_session-01.md              │
│  sessions/2026-07-29_session-02.md              │
│  summaries/summary-001.json                     │
│  summaries/summary-002.json                     │
└─────────────────────────────────────────────────┘
```

### Varje 20:e drag → LLM:n skriver en summary
- Prompt: "Sammanfatta de senaste 20 dragen i 3-5 meningar. Fokusera på: viktiga NPCs, platser, beslut, strider, loot."
- Summary sparas som JSON med metadata (drag-nummer, datum, plats)
- Äldsta summarian arkiveras till .md

### State uppdateras efter varje drag
- HP, inventory, currency, XP, quest-status
- Backend uppdaterar JSON, frontend pollar/websocket

### Varför inte bara .md?
- .md växer obegränsat → Qwen drunknar i context
- JSON = kompakt, strukturerat, alltid aktuellt
- Rullande summary = narrativ utan att spara varje "jag går norrut"

### Varför inte bara summaries?
- Tappar konversationsdetaljer
- Senaste 15 verbatim = naturligt flyt

---

## Bilduppladdning (Qwen Vision)

Spelaren kan ladda upp:
- **Karaktärsbilder** → Qwen beskriver, ger feedback, skapar karaktärsark
- **Kartor** → Qwen tolkar, beskriver platser
- **Handritade NPCs** → Qwen skapar NPC-statblock
- **Magiska föremål** → Qwen genererar item-beskrivning

Ingen bildGENERERING i v1 — bara bildANALYS.

---

## Chat-UX (beslutat)

### EN huvudchatt + Regel-orakel sidopanel

**Inte flera chattfönster.** D&D spelas vid ETT bord.

| Element | Design |
|---------|--------|
| **Huvudchatt** | En ström. DM narrerar (kursiv, guld-kant), NPCs med färgade namn, spelaren i lila bubbla |
| **NPC-identitet** | Varje NPC: färg + ikon + roll. DM:n växlar automatiskt. NPC-registry i state |
| **Regel-orakel** | Hopfällbar högerpanel. Fråga om regler utan att störa narrativet |
| **Systemmeddelanden** | Inline, centrerade, streckad kant: tärningskast, strid, XP |
| **Sidebar** | Vänster: party-kort (HP-bar), kända NPCs, aktuell plats |

### Meddelandetyper
- `dm` — Dungeon Master narration (kursiv, guld vänsterkant)
- `npc` — NPC-dialog (färgat namn + ikon)
- `player` — Spelarens handling (lila bubbla, högerställd)
- `system` — Tärningskast, initiative, level-up (centrerad, streckad)

### Tärningskommandon
- `/rulla 1d20+4` → inline tärningskast med resultat
- DM:n kan begära kast → systemmeddelande med resultat

### DM-tankar (statusindikator)

Medan DM:n "tänker" visas en roterande runspinner + atmosfärisk fras.
Fraserna roterar var 2.5:e sekund med mjuk fade. Kategorier:

| Kategori | När | Exempel |
|----------|-----|---------|
| `narrate` | DM skriver narration | "🐉 Väver berättelsen…" |
| `memory` | DM söker i tidigare konversationer/sammanfattningar | "🕰️ Tittar bakåt i tiden…" |
| `rules` | Regel-oraklet svarar | "⚖️ Rådgör med reglerna…" |
| `npc` | NPC talar | "🎭 Lånar en annans röst…" |
| `world` | Världsbyggande/import | "🗺️ Ritar världen på nytt…" |

Backend kan skicka en specifik kategori i svaret: `{ thought: 'memory' }`
→ frontend visar minnes-fraserna medan context byggs innan LLM-anropet.

---

## Export (beslutat)

### Kampanjexport som strukturerad .zip

```
kampanj-as kans-dal-2026-07-28.zip
├── README.md                    ← Kampanjöversikt, metadata
├── karaktar/
│   ├── thalindra-morkeld.json   ← Fullt karaktärsark (state-schema)
│   └── thalindra-portratt.png   ← Uppladdad bild (om finns)
├── transkript/
│   ├── session-01.md            ← Formaterad konversation
│   ├── session-02.md
│   └── session-03.md
├── varlden/
│   ├── npcs.json                ← Alla NPCs med relationer
│   ├── platser.json             ← Besökta platser + beskrivningar
│   └── lore.md                  ← Sammanfattad världshistoria
├── summaries/
│   ├── summary-001.json         ← Rullande sammanfattningar
│   └── summary-002.json
└── bilagor/
    ├── karta-askans-dal.png     ← Uppladdade bilder
    └── morvaine-skiss.jpg
```

- Transkript formateras som läsbar markdown med NPC-färger som namn-prefix
- JSON-filer valideras mot state-schema.json
- Export via backend: `GET /api/campaign/{id}/export` → zip-stream

---

## Import (beslutat)

### Importera stories/världar/karaktärer från filer

| Format | Qwen-extrahering |
|--------|-----------------|
| **.md** | Parsa direkt (struktur, headers, listor) → karaktärsark, NPC-listor, lore |
| **.pdf** | Textextrahering (PyMuPDF) → Qwen tolkar → strukturerad data |
| **Bilder** (jpg/png) | Qwen Vision → "Beskriv karaktären, ge förslag på statblock" |

### Import-flöde
1. Spelaren drar in fil(er) i en "Import"-dropzone
2. Backend: extrahera text/bild → skicka till Qwen med prompt:
   *"Extrahera D&D-relevant information: karaktärer (namn, ras, klass, nivå, förmågor), NPCs, platser, lore. Returnera JSON."*
3. Qwen svarar med strukturerad JSON
4. Frontend visar förhandsgranskning: "Hittade: 2 karaktärer, 5 NPCs, 3 platser"
5. Spelaren bekräftar → merge:a in i campaign state

### Import-prompt (Qwen)
```
Du är en D&D-dataextraherare. Analysera följande text/bild och extrahera:
- characters: [{name, race, class, level, abilities, hp, ac, traits}]
- npcs: [{name, role, relation, description}]
- locations: [{name, description}]
- lore: [string]
- items: [{name, type, rarity, description}]
Returnera ENDAST giltig JSON.
```

---

## Auth (beslutat)

### Enkel username/password

- **Backend**: `POST /api/login` → validerar mot `data/users.json` (bcrypt-hashed)
- **Session**: JWT-token i httpOnly cookie, 24h expiry
- **Frontend**: `login.html` → redirect till `chat.html`
- **Admin**: du och jag sätter upp användare manuellt i `users.json`
- **Ingen registrering** — bara vi skapar konton (litet projekt)

```json
// data/users.json
{
  "rostad": { "hash": "$2b$...", "created": "2026-07-28", "role": "admin" },
  "hastis": { "hash": "$2b$...", "created": "2026-07-28", "role": "player" }
}
```

---

## Filstruktur

```
dnd-llm/
├── BRAINSTORM.md
├── MARKNAD.md
├── ARCHITECTURE.md          ← du är här
├── frontend/
│   ├── character.html       ← Karaktärsark + inventory + currency (KLAR)
│   ├── chat.html            ← Chat-interface med DM (TODO)
│   └── style.css            ← Delad styling (TODO)
├── backend/
│   ├── main.py              ← FastAPI server (TODO)
│   ├── dm_engine.py         ← Qwen-prompter, DM-logik (TODO)
│   ├── state_manager.py     ← JSON state, summaries (TODO)
│   ├── dice.py              ← Tärningssystem (TODO)
│   └── vision.py            ← Qwen Vision, bildanalys (TODO)
├── data/
│   ├── campaigns/           ← Sparade kampanjer (JSON)
│   │   └── demo/
│   │       ├── state.json
│   │       ├── summaries/
│   │       └── sessions/
│   └── templates/           ← Karaktärsmallar
└── state-schema.json        ← State-format (nedan)
```

---

## State-schema (JSON)

Se `state-schema.json` i projektroten.
