# 🔍 GAP-ANALYS — Mörkrets Rike

**Datum:** 2026-07-28
**Omfattning:** Alla frontend/*.html, frontend/sfx.js, backend/*.py, *.md, state-schema.json
**Syfte:** Identifiera allt som blockerar en sammanhängande 1.0

---

## Innehåll

1. [Trasiga/döda länkar](#1-trasigadöda-länkar)
2. [Utelovade men ej implementerade funktioner](#2-utlovade-men-ej-implementerade-funktioner)
3. [Inkonsistenser: state-schema.json vs frontend](#3-inkonsistenser-state-schemajson-vs-frontend)
4. [Saknade pusselbitar för 1.0](#4-saknade-pusselbitar-för-10)
5. [UX-brister](#5-ux-brister)
6. [Övrigt](#6-övrigt)
7. [Sammanfattning per prioritet](#7-sammanfattning-per-prioritet)

---

## 1. Trasiga/döda länkar

### P0 — Inga auth-vakter på någon sida

**Alla sidor** kan öppnas direkt utan inloggning. `login.html` sparar `dnd_user` och `dnd_token` i `sessionStorage` (rad 227–228), men **ingen annan sida läser dessa värden**. Man kan gå direkt till `chat.html`, `character.html`, `npcs.html`, `adventure.html` eller `newgame.html` utan att logga in.

**Fix:** Lägg till en auth-guard i början av varje sidas `<script>`:
```js
if (!sessionStorage.getItem('dnd_user')) { location.href = 'login.html'; }
```

### P1 — newgame.html: Tillbaka-knappen går fel

`newgame.html` rad 194:
```html
<a class="back" href="login.html">← Till porten</a>
```
Borde gå till `adventure.html` (Vägskälet), inte tillbaka till inloggningen. Spelaren har redan loggat in och valt äventyrstyp.

**Fix:** `href="adventure.html"` och text `← Till vägskälet`.

### P1 — character.html är en återvändsgränd

`character.html` har **ingen navigation alls** tillbaka till `chat.html` eller `npcs.html`. Sidan har bara flikar (Karaktär/Utrustning/Skattkammare) men ingen topbar med länkar. Enda sättet att komma tillbaka är webbläsarens bakåtknapp.

Jämför med `npcs.html` som har en topbar med "⚔ Till bordet", "🧙 Karaktär" och "🚪 Lämna".

**Fix:** Lägg till en topbar i `character.html` med samma navigationslänkar som `npcs.html`.

### P1 — npcs.html: "Lämna" rensar inte sessionen

`npcs.html` rad 200:
```html
<a class="top-btn danger" href="login.html">🚪 Lämna</a>
```
Går direkt till `login.html` utan att rensa `sessionStorage`. Jämför med `chat.html` rad 640–644 där `logout()` tar bort `dnd_user` och `dnd_token` innan redirect.

Konsekvens: Efter att ha "lämnat" via npcs.html kan man gå tillbaka till chat.html och fortfarande vara "inloggad".

**Fix:** Anropa en `logout()`-funktion istället för direkt länk, eller rensa sessionStorage i login.html vid sidladdning.

### P2 — login.html: "Glömt lösenordet?" är en död länk

`login.html` rad 196:
```html
<a href="#">Glömt lösenordet?</a>
```
Gör ingenting. Eftersom auth är hårdkodad och det inte finns någon återställningsmekanism bör länken antingen tas bort eller visa ett toast-meddelande ("Kontakta din DM 😏").

### P2 — adventure.html: Ingen länk till login eller character

`adventure.html` har ingen "Lämna"-knapp och ingen länk till `character.html`. Mindre problem eftersom det är en genomgångssida, men inkonsistent med övriga sidor.

---

## 2. Utlovade men ej implementerade funktioner

### P0 — Exportknappen gör ingenting

`chat.html` rad 616–618:
```js
function exportCampaign() {
  toast('📦 Bygger kampanj-export… (zip med transkript, karaktärsark, bilagor)');
}
```
Visar bara ett toast-meddelande. Ingen zip byggs, ingen fil laddas ner.

**ARCHITECTURE.md** (rad 95–123) specificerar en hel zip-struktur med `README.md`, `karaktar/`, `transkript/`, `varlden/`, `summaries/`, `bilagor/`. Inget av detta är implementerat.

**README.md** rad 15 lovar: "📦 Export — kampanj som strukturerad .zip (transkript, karaktärsark, bilagor)".

**Fix för 1.0:** Implementera minst en grundläggande export som samlar ihop `state` (från character.html), NPC-data och chattranskript till en zip. Kan börja som klient-side JSZip-lösning tills backend finns.

### P0 — Modellväljaren används aldrig

`chat.html` rad 303–316 har en modellväljare med 7 modeller. `switchModel()` (rad 633–639) sätter en lokal variabel `currentModel` och visar ett toast — men variabeln används **aldrig** någonstans. Inget API-anrop, ingen backend-integration.

`backend/models.py` har ett komplett modellregistry med `get_model()`, `get_api_key()` och `list_models_for_frontend()` — men ingen anropar dem.

**Fix:** När backend (`main.py`) byggs, skicka `currentModel` med varje chat-request. Frontend bör också hämta modellistan från `GET /api/models` istället för att hårdkoda den.

### P0 — Ingen riktig LLM-integration någonstans

Hela chatten är ett manus. `chat.html` har:
- `script[]` (rad 487–494) — förprogrammerad öppningsscen
- `dmResponses[]` (rad 558–563) — 4 förprogrammerade DM-svar som loopas

`dmRespond()` (rad 566–575) ignorerar helt vad spelaren skriver och svarar med nästa förprogrammerade replik.

**ARCHITECTURE.md** beskriver en hybrid-kontextmodell (State + Summary + Recent + Archive), summary-var 20:e drag, state-uppdatering efter varje drag — inget implementerat.

**backend/models.py** har en `DM_SYSTEM_PROMPT` (rad 140–157) som är redo att användas, men ingen motor som anropar den.

### P1 — Import/Prepare är simulerat

`adventure.html`:
- `startPrepare()` (rad 329–346) — visar en fejkad progressbar, anropar inget API
- `finishPrepare()` (rad 348–357) — visar **slumpmässiga** antal NPCs/platser/uppdrag/lore
- `startImport()` (rad 362–377) — samma fejkade progressbar
- `finishImport()` (rad 379–387) — samma slumpmässiga siffror

Den extraherade datan sparas **inte** och skickas **inte** vidare till `newgame.html` eller `chat.html`. `proceed()` (rad 392–396) sparar bara `dnd_adventure_mode` i sessionStorage — inte world-data, inte filer, inte extraherad JSON.

**ARCHITECTURE.md** (rad 127–154) beskriver ett komplett import-flöde med Qwen-extrahering, förhandsgranskning och merge till campaign state.

### P1 — Auth är hårdkodad i frontend

`login.html` rad 210–213:
```js
const USERS = {
  'rostad': 'drake2026',
  'hastis': 'enhorn2026',
};
```
Lösenord i klartext i klienten. Ingen bcrypt, ingen JWT, ingen httpOnly cookie.

**ARCHITECTURE.md** (rad 158–174) specificerar: `POST /api/login`, bcrypt-hashad `data/users.json`, JWT i httpOnly cookie, 24h expiry.

**Fix:** Flytta validering till backend. Frontend ska bara skicka credentials och ta emot en token.

### P1 — Qwen Vision / Bildanalys

`character.html` har porträttuppladdning (rad 665–681) som sparar base64 i `state.character.portrait` — men ingen Qwen-analys sker. Toasten säger "redo för Qwen-analys" men inget anrop görs.

`adventure.html` accepterar bilder i dropzones men de skickas aldrig någonstans.

**ARCHITECTURE.md** (rad 57–65) lovar: karaktärsbilder → Qwen beskriver, kartor → Qwen tolkar, handritade NPCs → Qwen skapar statblock.

### P2 — Delad CSS saknas

**ARCHITECTURE.md** rad 188: `style.css — Delad styling (TODO)`.

All CSS är inline i varje HTML-fil. ~400+ rader CSS dupliceras per sida. Ember-partikelanimationen (~30 rader JS) dupliceras i alla 6 HTML-filer. Toast-funktionen dupliceras i alla filer.

**Fix:** Extrahera till `frontend/style.css` och `frontend/app.js` (eller `shared.js`).

---

## 3. Inkonsistenser: state-schema.json vs frontend

### P0 — chat.html har inget state-objekt alls

`chat.html` har **ingen** `state`-variabel. Allt är hårdkodat i HTML:
- Karaktärsnamn: "Thalindra Mörkeld" (rad 335, 441, 365, 489, 491, 493)
- Kampanjnamn: "Askans Dal · Session 4 · Dag 13" (rad 298)
- Plats: "Den Övergivna Kvarnen" (rad 349)
- NPCs: eget `NPCS`-objekt (rad 400–407) med `{name, color, icon, role}` — helt annorlunda struktur än schemats `npcs[]`

### P0 — newgame.html sparar bara karaktärens namn

`newgame.html` rad 541–545:
```js
function enterGame() {
  sessionStorage.setItem('dnd_character', document.getElementById('pv-name').textContent);
  location.href = 'chat.html';
}
```
Bara **namnet** sparas. Hela karaktärsarket (stats, HP, AC, traits, gear, story) kastas. `chat.html` läser aldrig `dnd_character`.

### P1 — state-schema.json vs character.html: fält som saknas eller avviker

| Schema-fält | character.html | Status |
|---|---|---|
| `meta` (campaign_id, campaign_name, created, last_updated, turn_count, session_count) | Saknas helt | ❌ |
| `character.alignment` | Saknas | ❌ |
| `character.background` | Saknas | ❌ |
| `character.ac` | Hårdkodat i HTML (rad 479: `<b>14</b>`) | ❌ |
| `character.initiative` | Hårdkodat i HTML (rad 480) | ❌ |
| `character.perception` | Hårdkodat i HTML (rad 481) | ❌ |
| `character.speed` | Hårdkodat i HTML (rad 482) | ❌ |
| `character.proficiency` | Hårdkodat i HTML (rad 483) | ❌ |
| `character.hp.temp` | Saknas | ❌ |
| `character.spell_slots` | `spellSlots` (camelCase) | ⚠️ Namn |
| `character.xp.next_level` | `xp.next` | ⚠️ Namn |
| `character.traits[].description` | Saknas (bara `name` + `magic`) | ⚠️ |
| `character.saves` | Schema: `{ability, bonus, proficient}` → Frontend: `{name, prof}` | ❌ Struktur |
| `inventory[].id` | Saknas | ⚠️ |
| `inventory[].description` | Saknas | ⚠️ |
| `world` (current_location, visited_locations, time, weather) | Saknas helt | ❌ |
| `quests` | Saknas i character.html | ❌ |
| `npcs` | Saknas i character.html | ❌ |

### P1 — npcs.html: NPC-struktur matchar inte schemat

`state-schema.json` definierar `npcs[]` som:
```json
{ "name": "...", "role": "...", "relation": "allierad|fiende|neutral|okänd", "notes": "string", "alive": true }
```

`npcs.html` använder en mycket rikare struktur:
```js
{ id, name, icon, color, glow, role, race, relation, trust, alive,
  met: { location, when, how },
  merchant: { items: [{name, price, rarity, stock}] },
  quests: [{name, status, desc, reward}],
  notes: [string],  // array, inte string!
  conversations: [{when, location, lines: [{who, text}]}] }
```

Schema och frontend är **o kompatibla**. Antingen måste schemat utökas kraftigt, eller så måste frontend förenklas.

**Rekommendation:** Utöka `state-schema.json` till att matcha den rikare frontend-strukturen — den är bättre designad.

### P1 — chat.html och npcs.html har olika NPC-data

`chat.html` `NPCS` (rad 400–407):
```js
{ morvaine: { name: 'Morvaine', color: '#8b5fd4', icon: '🧙', role: 'Den gåtfulla trollkarlen' }, ... }
```
Ett objekt med 5 NPCs (dm, morvaine, kael, lyra, borg, vakt).

`npcs.html` `NPCS` (rad 231–352):
En array med 6 NPCs (morvaine, kael, lyra, borg, halvard, damen) med mycket mer data.

Overlapp men inte identiska: `vakt` i chat.html heter `halvard` i npcs.html. `damen` (Den Gröna Damen) finns bara i npcs.html. Data kan divergera.

**Fix:** Ett enda NPC-registry i delad JS-fil eller i campaign state.

### P2 — newgame.html karaktärsformat matchar ingenting

`newgame.html` arketyper använder:
```js
{ name, cls, icon, stats: {STR, DEX, ...}, hp, ac, init, prof, traits: [string], gear: "html-string", story: "text" }
```
Detta matchar varken `state-schema.json` eller `character.html`'s state. `traits` är strängar (inte objekt), `gear` är en HTML-sträng (inte inventory-array), `stats` är bara nummer (inte `{score, mod}`).

---

## 4. Saknade pusselbitar för 1.0

### P0 — Karaktären når aldrig chatten

Flödet borde vara: `newgame.html` → generera karaktär → spara → `chat.html` använder den.

**Verkligheten:**
1. `newgame.html` genererar en karaktär (förprogrammerad eller "slumpad")
2. `enterGame()` sparar **bara namnet** i `sessionStorage.dnd_character`
3. `chat.html` läser **aldrig** `sessionStorage.dnd_character`
4. `chat.html` hårdkodar "Thalindra Mörkeld" överallt
5. `character.html` hårdkodar "Thalindra Mörkeld" överallt

**Konsekvens:** Spelaren kan skapa en karaktär som heter "Aldric Vane" i newgame.html, men chatten och karaktärsarket visar fortfarande "Thalindra".

**Fix:**
1. Spara hela karaktärsobjektet i sessionStorage (eller bättre: skicka till backend)
2. `chat.html` och `character.html` läser karaktären vid sidladdning
3. Ersätt alla hårdkodade "Thalindra"-referenser med dynamiskt namn

### P0 — Ingen kampanjhantering

Det finns inget sätt att:
- Skapa en ny kampanj med ett ID
- Spara kampanjstate mellan sessioner
- Ladda en befintlig kampanj
- Fortsätta där man slutade

`sessionStorage` rensas när fliken stängs. Allt är flyktigt.

**ARCHITECTURE.md** specificerar `data/campaigns/` med `state.json`, `summaries/`, `sessions/` per kampanj. Inget av detta existerar.

### P0 — Backend saknas (main.py)

`backend/` innehåller bara `models.py` och `.env.example`. Alla endpoints som frontend refererar till saknas:
- `POST /api/login`
- `POST /api/character/generate`
- `POST /api/world/build`
- `POST /api/session/model`
- `GET /api/campaign/{id}/export`
- `POST /api/campaign/{id}/buy`
- Chat/DM-endpoint

**OBS:** Enligt uppgift byggs `main.py` just nu — detta noteras men behandlas inte som en bugg. Men frontend har **noll** felhantering för när backend inte svarar.

### P1 — "Ett spel per användare"-regeln

**ARCHITECTURE.md** rad 166: "Ingen registrering — bara vi skapar konton (litet projekt)".

Men det finns ingen mekanik för att koppla en användare till en kampanj. `sessionStorage.dnd_user` finns men används aldrig för att hämta/spara kampanjdata.

**Fix:** Backend behöver: `GET /api/user/{username}/campaign` → returnera aktiv kampanj eller 404. Frontend: vid sidladdning, hämta kampanjstate.

### P1 — Flera karaktärer / party

`BRAINSTORM.md` rad 49: "Flera karaktärer per spelare (party?)".

`chat.html` sidebar visar ett "Sällskapet"-kort men bara en karaktär. Det finns ingen mekanik för att byta karaktär eller lägga till party-medlemmar.

### P2 — Multiplayer

`BRAINSTORM.md` rad 64–68 listar multiplayer som stretch goal. Inget är designat eller implementerat. Noteras här för fullständighet — blockerar inte 1.0.

---

## 5. UX-brister

### P1 — Mobil: chat.html tappar all kontext

`chat.html` rad 283–288:
```css
@media (max-width: 900px) {
  .sidebar { display: none; }
  .oracle.open { width: 260px; }
  .topbar .campaign { display: none; }
}
```

På mobil (< 900px):
- **Sidebar försvinner helt** — ingen HP-bar, ingen NPC-lista, ingen platsinfo
- **Kampanjnamnet döljs** — spelaren vet inte vilken kampanj de spelar
- **Oracle-panelen tar 260px** av ~360px skärmbredd
- **Topbar-knapparna** (7 st) kommer att flöda över eller klippas — ingen hamburgermeny eller wrapping

**Fix:**
- Hamburgermeny för topbar-knappar på mobil
- Collapsible sidebar eller bottom-sheet för party/NPC-info
- Oracle som fullskärmsoverlay på mobil

### P1 — Ingen felhantering för backend-anrop

När backend byggs kommer frontend att göra `fetch()`-anrop. Just nu finns:
- **Ingen** `try/catch`
- **Ingen** loading-state vid API-anrop (förutom fejkade progressbars)
- **Ingen** error-toast vid nätverksfel
- **Ingen** timeout-hantering
- **Ingen** retry-logik
- **Ingen** offline-detektering

**Fix:** Skapa en delad `api.js` med wrapper:
```js
async function api(path, opts) {
  try {
    const res = await fetch(API_BASE + path, opts);
    if (!res.ok) throw new Error(res.statusText);
    return await res.json();
  } catch (e) {
    toast('⚠ Något gick fel — försök igen');
    throw e;
  }
}
```

### P1 — Inga loading-states för riktiga operationer

- `newgame.html` "Frammana karaktär" — fejkad 2.4s timeout, ingen riktig loading
- `adventure.html` "Bygg världen" / "Extrahera" — fejkade progressbars
- `chat.html` DM-svar — fejkad typing-indikator, ingen riktig väntan
- `chat.html` Export — ingen loading alls

När riktig LLM-integration kommer kan svar ta 5–30 sekunder. Behöver:
- Typing-indikator som visar verklig status
- Avbryt-knapp
- Timeout med felmeddelande

### P2 — Toast-meddelanden försvinner för snabbt

Alla sidor: toast visas i 2.2–2.6 sekunder. För viktiga meddelanden ("Karaktären är vävd!", "Kampanj extraherad!") kan det vara för kort.

**Fix:** Längre duration för viktiga meddelanden, eller klickbar toast som stannar.

### P2 — Ingen bekräftelse vid destruktiva handlingar

- `character.html` `removeItem()` — raderar direkt utan bekräftelse
- `chat.html` `logout()` — ingen "Är du säker?"
- `npcs.html` `buyItem()` — köp utan bekräftelse

### P2 — Ingen favicon

Alla sidor saknar `<link rel="icon">`. Webbläsarfliken visar en tom ikon.

**Fix:** Lägg till en 🐉-favicon eller en enkel SVG.

### P2 — login.html: `overflow: hidden` på body

`login.html` rad 37: `overflow: hidden` på body. På mycket små skärmar (landscape-läge på telefon) kan formuläret klippas utan att kunna scrolla.

---

## 6. Övrigt

### P1 — Ember-partiklar och toast dupliceras i alla filer

Varje HTML-fil innehåller:
- ~30 rader identisk ember-canvas-JS
- ~8 rader identisk toast-funktion
- ~15 rader identisk CSS för toast

Totalt ~300+ rader onödig duplication.

**Fix:** Extrahera till `frontend/shared.js` och `frontend/style.css`.

### P1 — `dnd_adventure_mode` sparas men används aldrig

`adventure.html` rad 394 och 400:
```js
sessionStorage.setItem('dnd_adventure_mode', mode);  // 'prepare', 'import', 'freestyle'
```
`newgame.html` läser **aldrig** detta värde. Mode-valet (Förbered/Importera/Freestyle) påverkar ingenting.

**Fix:** `newgame.html` bör läsa moden och anpassa flödet (t.ex. visa world-prompten vid "prepare", visa importerad data vid "import").

### P1 — `sfx.js` saknas i adventure.html och newgame.html

`adventure.html` och `newgame.html` laddar inte `sfx.js`. De använder visserligen inga SFX-anrop just nu, men:
- `adventure.html` har knappar och interaktioner som skulle må bra av `SFX.click()`
- `newgame.html` har "Frammana karaktär" som skulle kunna använda `SFX.dice()`
- Inkonsistent med övriga sidor

### P2 — `character.html` rad 719: Bugg i spell slot-toast

```js
toast(i < ss.current + 0 ? '🔮 Besvärjelse kastad' : '✨ Plats återställd');
```
`+ 0` är meningslöst. Logiken är också fel: efter att `ss.current` satts till `i` (rad 717) kommer `i < ss.current` alltid vara `false` (eftersom `ss.current === i`). Toasten visar alltid "Plats återställd" oavsett om man spenderade eller återställde.

**Fix:** Spara gamla värdet innan ändring:
```js
const wasLit = i < ss.current;
ss.current = wasLit ? i : i + 1;
toast(wasLit ? '🔮 Besvärjelse kastad' : '✨ Plats återställd');
```

### P2 — `backend/.env.example`: Qwen-modellnamn stämmer inte med models.py

`.env.example` rad 10: `QWEN_DEFAULT_MODEL=qwen3.8-max`
`models.py` rad 31: `api_model="qwen3.8-max-preview"`

`QWEN_DEFAULT_MODEL` används aldrig i `models.py`. Antingen ta bort den ur `.env.example` eller implementera default-modell-logik.

### P2 — `MARKNAD.md` och `BRAINSTORM.md` är interna dokument

Dessa är värdefulla för kontext men bör kanske flyttas till en `docs/`-mapp för att städa upp i roten.

### P2 — Ingen `index.html` eller redirect

Om man öppnar `http://localhost:8090/` utan filnamn får man ett directory listing eller 404.

**Fix:** Lägg till en `index.html` som redirectar till `login.html`.

---

## 7. Sammanfattning per prioritet

### 🔴 P0 — Blockerar 1.0 (7 st)

| # | Problem | Fil | Fix |
|---|---------|-----|-----|
| 1 | Inga auth-vakter — alla sidor öppna | Alla HTML | Auth-guard i varje sida |
| 2 | Exportknappen gör ingenting | chat.html:616 | Implementera zip-export |
| 3 | Modellväljaren används aldrig | chat.html:633 | Skicka modell till backend |
| 4 | Ingen riktig LLM-integration | chat.html:487–575 | Byt manus mot API-anrop |
| 5 | Karaktären når aldrig chatten | newgame.html:541, chat.html:335+ | Spara/hämta karaktärsstate |
| 6 | Ingen kampanjhantering | Hela projektet | Backend: campaign CRUD |
| 7 | Backend saknas (main.py) | backend/ | Bygg FastAPI-server |

### 🟡 P1 — Bör fixas (12 st)

| # | Problem | Fil | Fix |
|---|---------|-----|-----|
| 1 | newgame.html back → login istället för adventure | newgame.html:194 | Ändra href |
| 2 | character.html saknar navigation | character.html | Lägg till topbar |
| 3 | npcs.html "Lämna" rensar inte session | npcs.html:200 | Anropa logout() |
| 4 | Import/Prepare är simulerat | adventure.html:329–387 | Backend-integration |
| 5 | Auth hårdkodad i frontend | login.html:210–213 | Flytta till backend |
| 6 | Qwen Vision ej implementerat | character.html:665 | Backend-anrop |
| 7 | state-schema vs character.html: 12+ avvikelser | state-schema.json, character.html | Synka |
| 8 | npcs.html NPC-struktur ≠ schema | npcs.html:231, state-schema.json:127 | Utöka schema |
| 9 | chat.html ≠ npcs.html NPC-data | chat.html:400, npcs.html:231 | Delat registry |
| 10 | Mobil: sidebar försvinner, topbar flödar | chat.html:283 | Hamburger + bottom-sheet |
| 11 | Ingen felhantering för API-anrop | Alla sidor | Delad api.js |
| 12 | dnd_adventure_mode används aldrig | adventure.html:394, newgame.html | Läs och anpassa flöde |

### 🟢 P2 — Nice to have (10 st)

| # | Problem | Fil |
|---|---------|-----|
| 1 | "Glömt lösenordet?" död länk | login.html:196 |
| 2 | Delad CSS/JS saknas (300+ rader duplication) | Alla filer |
| 3 | Spell slot toast-logik buggig | character.html:719 |
| 4 | Ingen favicon | Alla filer |
| 5 | Toast försvinner för snabbt | Alla filor |
| 6 | Ingen bekräftelse vid destruktiva handlingar | character.html, chat.html |
| 7 | login.html overflow:hidden kan klippa | login.html:37 |
| 8 | QWEN_DEFAULT_MODEL används aldrig | .env.example:10 |
| 9 | Ingen index.html redirect | frontend/ |
| 10 | newgame.html karaktärsformat matchar inget | newgame.html |

---

## Rekommenderad ordning för 1.0

1. **Backend first:** `main.py` med `/api/login`, `/api/chat`, `/api/models`, `/api/campaign/{id}` (P0 #7)
2. **State-hantering:** Synka `state-schema.json` med frontend, skapa delad `state.js` (P0 #5, P1 #7–9)
3. **Auth-guard + riktig auth** (P0 #1, P1 #5)
4. **LLM-integration:** Ersätt manus i chat.html med riktiga anrop (P0 #4)
5. **Karaktärsflöde:** newgame → backend → chat/character (P0 #5)
6. **Export:** Grundläggande zip (P0 #2)
7. **Modellväljare:** Skicka till backend (P0 #3)
8. **Mobil-UX + felhantering** (P1 #10–11)
9. **Städa:** Delad CSS/JS, navigation, toast-buggar (P1 #1–3, P2)

---

*Genererad 2026-07-28. Alla radnummer avser filer vid tidpunkten för analysen.*
