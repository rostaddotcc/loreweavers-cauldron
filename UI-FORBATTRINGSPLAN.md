# 🗡️ UI/UX-förbättringsplan — The Lore Weaver's Cauldron

**Audit-datum:** 2026-07-29
**Omfattning:** chat.html, loggbok.html, platser.html, npcs.html, valvet.html, character.html, snes.css, sprites.js + backend (main.py, logbook.py, state-schema.json)
**Designprincip:** Terminal Gothic (Castlevania × DOS × terminal). Inget får kännas som en 50%-mall — allt ska kännas som ett riktigt spel.

---

## 0. Nuläge — vad som finns idag

| Yta | Status |
|---|---|
| **chat.html** | Fungerande spelbrygga. Topbar med 9 knappar i ologisk ordning. Sidebar: Sällskapet → Kända NPCs → Plats. Chatt med dm/npc/player/system/effekt-meddelanden. @NPC-autocomplete finns redan (rad 989–1031) men skickas aldrig till backend. |
| **loggbok.html** | Renderar `{title, days[], summary}` från `/api/campaign/logbook`. **Flaskhals: endpointen kör ett LLM-anrop på hela transkriptet vid VARJE sidladdning** (main.py rad 1519–1572). |
| **platser.html** | Dynamisk från `/api/campaign/locations` (locations.py). ASCII-karta 50×18 med **slumpat brus** (Math.random, rad 143–149) — kartan ser olika ut varje laddning. Platser har x/y (0–100), current/visited, terrain, travel_days, landmarks. |
| **npcs.html** | Minnets hall + dossier. Läser redan `campaign._raw.quests` (rad 297) och visar relaterade uppdrag per NPC. |
| **valvet.html** | Karaktärsvalv — spara/återaktivera hjältar. Fungerar, ingen förändring behövs. |
| **character.html** | Karaktärsark med 4 flikar. Fungerar, ingen förändring behövs. |
| **snes.css** | Terminal-override med `!important` överallt. **Hårdkodar `.msg.npc { border-left: 2px solid var(--arcane) }` (rad 249)** — dödar per-NPC-färger. |
| **sprites.js** | 8×8 pixel-sprites som ersätter emojis via MutationObserver. ~90 sprites finns. Saknar: ⚔-flagga för quests på karta, kompass, sömn/måne för ny-dag. |

---

## 1. KARTAN (platser.html) — ska spegla berättelsen

### Nuläge
- Byggs dynamiskt från state (`get_locations_with_travel(state)` i locations.py).
- ASCII-kartan är en 50×18-matris där terrängbruset slumpas fram varje laddning (`Math.random()` rad 143–149) → kartan "flimrar" och känns inte som en riktig plats.
- Platser ritas som `◉` (nuvarande), `◆` (besökt), `◇` (känd ej besökt). Inga vägar, ingen rutt, inga quest-markörer, ingen fog of war.
- Under kartan: ett rutnät av platskort med restid, status och sevärdheter.

### Ska den slås ihop med loggboken?
**Nej.** Kartan är *rumslig* navigation, loggboken är *temporal* berättelse. En ihopslagning skulle ge en förvirrande hybrid. Istället: **koppla ihop dem** med korslänkar (se §1.4) och ge kartan sitt eget berättelselager.

### Konkret design

**1.1 Deterministisk karta (ersätt slumpbruset)**
- Fil: `platser.html`, funktionen `renderMap()` (rad 137–173).
- Byt `Math.random()` mot en **seedad PRNG** (t.ex. enkel mulberry32 seedad med kampanjnamnets hash) så att terrängen är identisk varje gång.
- Eller steget vidare: byt ASCII-matrisen mot en **SVG-karta i pixel-estetik**: rutnät som bakgrund, platser som sprite-ikoner (sprites.js har redan 🌲⛰️🌊🏰🏠), scanline-overlay från snes.css behålls globalt. SVG ger möjlighet till linjer (vägar) och glöd.
- Rekommendation: börja med seedad ASCII (liten insats, behåller DOS-känslan), bygg SVG som fas 2 om tid finns.

**1.2 Ruttlinjer + fog of war**
- Nytt state-fält: `world.travel_log: [{from, to, day}]` — appendas av PLATS-hanteraren i main.py (rad 226–234) varje gång `[PLATS:...]` uppdaterar current_location.
- Kartan ritar en prickad linje mellan sekventiellt besökta platser (i ASCII: `·`/`•` längs Bresenham-linjen mellan koordinater; i SVG: `<path stroke-dasharray>`).
- **Fog of war:** platser som varken är besökta *eller* nämnda i berättelsen döljs helt (idag visas alla som `◇`). Backend filtrerar: returnera `visited + known` (där `known` = platser som förekommit i transkript/sammanfattningar). Okända platser = tomma ytan på kartan — det är så en riktig spelkarta känns.

**1.3 Quest-markörer**
- Quests saknar idag platskoppling. Utöka QUEST-taggen bakåtkompatibelt: `[QUEST:Namn|Beskrivning|Belöning|Plats]` (4:e fältet valfritt, main.py rad 180–191).
- Kartan ritar `⚑` (sprite finns redan i sprites.js, rad 63) bredvid platser med aktiva quests, i `--ember`-orange med pulserande glöd.
- Nuvarande plats: `◉` med pulserande animation + etikett "DU ÄR HÄR".

**1.4 Berättelselager på kartan + korslänkar**
- Under ASCII-kartan, ovanför platskorten: en **"Resejournal"-remsa** — horisontell lista: `Dag 1 · Stenviken → Dag 3 · Mörkskogen → Dag 5 · ⚑ Kryptan`. Klickbar → scrollar till motsvarande platskort.
- Varje platskort får en rad: *"Senast: Dag 5 — 'Striden vid kryptans port'"* (hämtas från loggbokens cache, se §2).
- Loggbokens dag-kort får klickbara plats-tags som länkar till `platser.html#<plats-id>`.

---

## 2. LOGGBOKEN (loggbok.html) — döda flaskhalsen, lägg till ny-dag

### Flaskhalsen (rotorsak)
`/api/campaign/logbook` (main.py rad 1519–1572):
1. Läser in **senaste 100 transkriptinlägg + 10 sammanfattningar**.
2. Skickar ALLT till `ATMOSPHERE_MODEL` med `max_tokens=2048` via `build_log_prompt()` (logbook.py).
3. Väntar på hela LLM-svaret, parsar JSON, returnerar.

→ **Varje sidladdning = en full LLM-regenerering av hela äventyrets historia.** Det är därför det är långsamt (flera sekunder + token-kostnad). Det finns ingen cache, ingen inkrementell uppdatering, inget begrepp om "dag" i state.

### (a) För-generera vid dagsskifte istället för vid laddning

**Ny state-struktur** (lägg till i state-schema.json under `world`):
```json
"day": 3,
"logbook": {
  "summary": "Äventyret hittills (max 50 ord, uppdateras inkrementellt)",
  "days": [
    { "day": 1, "title": "...", "mood": "...", "events": [...],
      "location": "...", "npcs_met": [...], "quests": [...],
      "generated_at": "..." }
  ]
}
```

**Dagsskifte-detektering:**
- Ny mekanisk tagg: `[NY_DAG:valfri beskrivning]` i DM:s svar (lägg till i `_MECH_PATTERNS`, main.py rad 99–111). DM-prompten instrueras: *"När spelaren sover/vilar till nästa dag, avsluta svaret med [NY_DAG:kort beskrivning av morgonen]."*
- Alternativt: detektera om `[TID:...]`-värdet (rad 236–241) innehåller ett nytt dagnummer.
- När NY_DAG triggar, i `parse_mechanical_tags()` (main.py):
  1. `world['day'] += 1`
  2. **Generera gårdagens entry direkt** (async, i bakgrunden): anropa snabb modell med endast transkriptet *sedan förra dagsskiftet* (spåra `world['last_day_turn']`) + befintliga sammanfattningar → en enda dag-entry (max ~200 tokens, snabbt).
  3. Append till `world['logbook']['days']`.
  4. Uppdatera `world['logbook']['summary']` inkrementellt (prompt: "Här är nuvarande sammanfattning + gårdagens händelser. Skriv en ny sammanfattning, max 50 ord.").
  5. Emit effekt `{type: 'ny_dag', value: dag}` → chatten visar en **"Ny dag"-banderoll** (se §2.2).

**Ny endpoint-logik** (`/api/campaign/logbook`):
```python
# Returnera cache direkt — ingen LLM vid laddning
logbook = state.get("world", {}).get("logbook")
if logbook and logbook.get("days"):
    return {"title": campaign_name, "days": logbook["days"], "summary": logbook["summary"]}
# Fallback: generera en gång vid första besöket och cacha
```
→ Laddningstid: **flera sekunder → <100 ms**.

**Frontend (loggbok.html):**
- `loadLogbook()` (rad 195–208) renderar direkt från cache. "Krönikören bläddrar…"-animationen (rad 116–120) visas endast om `days` saknas (första gången).
- Lägg till en diskret "✦ Uppdaterad: [datum]"-stämpel + en **"Uppdatera krönikan"**-knapp som triggar en manuell regenerering av *endast innevarande (pågående) dag* via ny endpoint `POST /api/campaign/logbook/refresh-today`.

### (b) Vad en "ny dag"-entry ska innehålla

Varje dag-kort i loggboken (och banderollen i chatten) ska innehålla:

| Fält | Källa | Exempel |
|---|---|---|
| **Dag + spelvärldens datum** | `world.day` + `world.time` | "Dag 4 — 12:e Nattmånad" |
| **Plats** | `world.current_location` | "Mörkskogens utkant" |
| **Väder** | `world.weather` | "Kall dimma, vindstilla" |
| **Gårdagens sammanfattning** | LLM (2–3 meningar) | "Ni följde spåret till kryptan. Eira sårades av en gravvaktare." |
| **Aktiva uppdrag** | `state.quests` (status=aktiv) | "⚑ Hitta den försvunna vakten" |
| **Sällskapets status** | `character.hp`, level | "HP 23/52 · Nivå 3" |
| **Omen/dröm (flavor)** | LLM, 1 mening | "Du drömmer om en port som andas." |

**"Ny dag"-banderoll i chatten** (renderas av `renderEffects()` när `fx.type === 'ny_dag'`, main.py rad 1121–1165):
```
☀ ─── DAG 4 ─── ☀
12:e Nattmånad · Mörkskogens utkant · Kall dimma
Du drömmer om en port som andas.
[HP 23/52 · ⚑ 2 aktiva uppdrag]
```
Stil: centrerad, guldramad, med `day-in`-animation (återanvänd loggbokens `@keyframes day-in`). SFX: mjuk "morgon"-ton.

---

## 3. QUEST-TRACKER — var ska den bo?

### Slutsats: **I chat.html:s sidebar**, inte i loggboken, inte som separat panel.

**Resonemang:**
- Loggboken är *retrospektiv* (man lämnar spelbordet för att läsa den). En quest-tracker måste vara **synlig under spel** — annars glöms den.
- En separat panel krockar med Regel-oraklet (höger) och gör layouten trång.
- Sidebaren är alltid synlig på desktop och har redan ledig plats mellan "Kända NPCs" och "Plats" (rad 499).
- **Datat finns redan:** `state.quests = [{name, description, reward, status: 'aktiv'|'slutförd'|'misslyckad'}]` (state-schema.json rad 140–150, main.py rad 179–209). npcs.html läser redan `campaign._raw.quests` (rad 297) — chat.html får samma data via `API.getCampaign()` utan ny endpoint.

### Konkret design

**Placering i sidebaren (chat.html rad 480–504):**
```
SÄLLSKAPET          (befintligt pc-card)
⚑ UPPDRAG           ← NY SEKTION
KÄNDA NPCs          (befintlig)
PLATS               (befintlig, längst ner)
```

**HTML** (infogas efter Sällskapet-blocket, före npc-list):
```html
<div>
  <div class="side-label">⚑ Uppdrag</div>
  <div class="quest-list" id="quest-list"></div>
</div>
```

**Rendering:**
- Aktiv quest: `⚑` i `--ember` med pulserande glöd (återanvänd `@keyframes qpulse` från npcs.html rad 128–129), namn i `--bone-bright`, beskrivning avkortad (1 rad, `text-overflow: ellipsis`). Hover → expandera beskrivning + belöning.
- Slutförd: `✓` i `--poison`, namnet nedtonat.
- Misslyckad: `✕` i `--blood-bright`, genomstruket.
- Tomt tillstånd: *"Inga uppdrag ännu. Mörkret väntar…"* (nedtonat, kursivt).
- Klick på aktiv quest → `location.href='npcs.html'` (där relaterade quests redan visas) eller expandera inline.

**Live-uppdatering:**
- `renderEffects()` (chat.html rad 1121–1165) hanterar redan `quest`, `quest_slutförd`, `quest_misslyckad`. Lägg till `refreshQuests()` som anropas efter varje sådan effekt + efter `loadCampaign()`.
- Uppdatera `campaign._raw.quests` lokalt när effekter anländer (backend har redan uppdaterat state; frontend speglar).

**Mobil (sidebar döljs <900px, rad 426–431):**
- Lägg till en quest-räknare i topbar-campaign-taggen: `Kampanj: The Lore Weaver's Cauldron · Tur 12 · ⚑ 2`.

---

## 4. MENY/TOPBAR (chat.html) — ny ordning

### Nuläge (chat.html rad 441–476)
```
[🐉 Brand] [Kampanj: …] [spacer]
[🔮 Modell] [📜 Regel-orakel] [❓ Hur spelar man?] [📖 Gestalter] [🗺️ Kartan]
[📜 Loggbok] [🏰 Valvet] [📦 Exportera] [🧙 Karaktär] [🔊] [♫] [🚪 Lämna]
```
Problemen: Karaktär ligger näst sist (onclick-baserad, inte en riktig länk). Spelvärldsknapparna (Gestalter/Kartan/Loggbok/Valvet) är blandade med verktyg (Orakel/Hjälp) och system (Exportera/Lämna). Två knappar har 📜-ikonen (Regel-orakel + Loggbok).

### Ny ordning
```
[🐉 Brand] [Kampanj: …] [spacer]
[🧙 Karaktär] | [🗺️ Kartan] [📜 Loggbok] [📖 Gestalter] [🏰 Valvet] | [🔮 Modell] [⚖️ Regel-orakel] [❓ Hjälp] | [📦 Export] [🔊] [♫] | [🚪 Lämna]
```
(`|` = tunn vertikal avskiljare, 1px `var(--edge)`, höjd 24px)

**Resonemang per grupp:**
1. **Karaktär först (vänster om äventyrstiteln, enligt användarens önskemål):** Det är spelarens hemknapp — den man oftast trycker på. Gör den till en riktig `<a href="character.html">` (idag `onclick location.href`, rad 472) och ge den subtil guld-kant som primär navigation.
2. **Spelvärlden (Kartan → Loggbok → Gestalter → Valvet):** Rum → Tid → Personer → Ägodelar. Logisk läsordning som speglar hur man tänker om kampanjen.
3. **Verktyg (Modell, Regel-orakel, Hjälp):** Saker som påverkar *hur* man spelar, inte *vad* som hänt. Byt Regel-oraklets ikon till ⚖️ (undviker 📜-krocken med Loggbok).
4. **System (Export, ljud, musik, Lämna):** Sällsynta åtgärder längst till höger, med Lämna sist i rött.

**CSS-tillägg (chat.html inline-style eller snes.css):**
```css
.topbar .sep { width:1px; height:24px; background:var(--edge); flex-shrink:0; }
.top-btn.primary { border-color: rgba(201,162,39,.5); color: var(--gold-bright); }
```

---

## 5. CHATFÖNSTRET (chat.html) — DM vs NPC, färger, taggning

### Nuläge
- **DM** (`.msg.dm`, rad 158–165): guld vänsterkant + kursiv text. snes.css (rad 243–247) tvingar `border-left: 2px solid var(--gold)` och normal (ej kursiv) text.
- **NPC** (`.msg.npc`, rad 167–175): namnet får NPC:ns färg via inline `style="color:${n.color}"` (rad 735), men **brödtexten är alltid `var(--bone)`** och snes.css **hårdkodar vänsterkanten till `var(--arcane)` för ALLA NPCs** (rad 249). Alla NPC-repliker ser likadana ut utom namnet.
- **Spelare** (`.msg.player`): högerställd lila bubbla — fungerar bra.
- **@mention** (rad 989–1031): autocomplete-popup finns men skickar bara namnet som text — backend vet inte att spelaren vänder sig till en specifik NPC.

### Konkreta CSS/HTML-ändringar

**5.1 Per-NPC-färg via CSS-variabel**
- `addMessage()` (rad 725–757), npc-grenen: sätt `--npc-color` på elementet:
```js
el.style.setProperty('--npc-color', n.color);
el.style.setProperty('--npc-glow', n.color + '40'); // 25% alpha
```
- CSS (chat.html inline, rad 167–175) — ersätt hårdkodade färger:
```css
.msg.npc { border-left: 2px solid var(--npc-color, var(--arcane)); padding-left: 1rem; }
.msg.npc .text {
  background: linear-gradient(90deg, var(--npc-glow, transparent), transparent 65%);
  border-left: none;
}
.msg.npc .who { color: var(--npc-color); }
.msg.npc .who .dot { background: var(--npc-color); box-shadow: 0 0 8px var(--npc-color); }
```
- **Fixa snes.css rad 248–252** (kritiskt — annars dör färgerna):
```css
.msg.npc {
  border-left: 2px solid var(--npc-color, var(--arcane)) !important;
  padding-left: .8rem !important;
  background: transparent !important;
}
```

**5.2 Tydligare DM-narration vs NPC-dialog**
- DM: behåll guld vänsterkant men lägg till subtil bakgrundston + DM-sigill:
```css
.msg.dm { background: linear-gradient(90deg, rgba(201,162,39,.05), transparent 60%); }
.msg.dm .who::before { content: '◆'; color: var(--gold); }
```
- NPC: lägg till citattecken-färg och tal-stil som skiljer sig från narration:
```css
.msg.npc .text::before { content: '»'; color: var(--npc-color); font-weight:700; margin-right:.3rem; }
```
- **Inline-dialog i DM-text:** när DM:n skriver `Eira: "Vi måste skynda oss"` inuti narrationen, färga den repliken. Frontend-parsing i `mdToHtml()` (rad 1059–1064): efter markdown-konvertering, matcha kända NPC-namn följt av kolon+citat:
```js
// i mdToHtml, efter escapeHtml:
Object.values(NPCS).forEach(n => {
  if (n.name === 'Dungeon Master') return;
  const re = new RegExp(`(^|<br>|\\n)\\s*(${n.name}):\\s*["»]([^"«]*?)["«]`, 'g');
  s = s.replace(re, `$1<span class="inline-npc" style="color:${n.color}">$2: »$3«</span>`);
});
```
- Långsiktigt (backend): låt DM-prompten returnera `npc_replies: [{npc, text}]` som separata fält, så slipper man regex-gissa.

**5.3 @NPC-taggar → individuella svar**
- Frontend finns redan (checkAtMention/showAtPopup/insertAtMention, rad 989–1031). Det som saknas:
  1. `sendPlayer()` (rad 1033–1052): detektera `@Namn` i texten, slå upp i NPCS, skicka `target_npc` till backend:
```js
const mention = text.match(/@([\w\sÅÄÖåäö]+?)(?=\s|$)/);
const targetNpc = mention && Object.values(NPCS).find(n => n.name === mention[1]);
dmRespond(text, targetNpc ? targetNpc.name : null);
```
  2. `API.chat()` (api.js): lägg till `target_npc` i POST-body.
  3. Backend DM-prompt (main.py, system-prompt-bygget ~rad 588): om `target_npc` finns, injicera: *"Spelaren vänder sig direkt till {name}. Låt {name} svara i första person, inled med '{name}: "…"'."*
  4. Rendering: om `target_npc` sattes, rendera svaret som `.msg.npc` med den NPC:ns färg istället för `.msg.dm` (eller dela upp via inline-dialog-parsingen i 5.2).
- Autocomplete-popupen (rad 1008–1021) ska dessutom visa NPC:ns färgprick: `<span class="npc-dot" style="background:${n.color}"></span>`.

---

## 6. IMPLEMENTERINGSPRIORITERING

| Prio | Uppgift | Filer | Insats | Varför först |
|---|---|---|---|---|
| **P0** | Loggboks-cache + NY_DAG-tag + för-generering vid dagsskifte | main.py, logbook.py, state-schema.json, loggbok.html | Medel | Största smärtan (långsam laddning). Data-modellen är grund för allt annat (kartans resejournal, ny-dag-banderoll). |
| **P0** | Quest-tracker i chat-sidebaren | chat.html | Liten | Datat finns redan i `_raw.quests`. Hög spelkänsla för liten insats. |
| **P1** | Per-NPC-färger i chatten (CSS-variabel + snes.css-fix) | chat.html, snes.css | Liten | Kärnupplevelsen. snes.css-rad 249 är en 2-minutersfix som direkt syns. |
| **P1** | Topbar-omordning med grupper + Karaktär först | chat.html | Liten | Snabb vinst, användarens explicita önskemål. |
| **P1** | Ny-dag-banderoll i chatten + DM-prompt för [NY_DAG] | main.py, chat.html | Liten | Bygger på P0-loggboksarbetet, gör dagsskiften till en *händelse*. |
| **P2** | Karta: seedad terräng + ruttlinjer + travel_log i state | platser.html, main.py, locations.py | Medel | Kräver travel_log (P0-beroende). Fog of war + quest-markörer. |
| **P2** | @NPC → target_npc till backend + individuella svar | chat.html, api.js, main.py | Medel | Backend-promptändring; testa noggrant att DM:n inte tappar narrativ kontroll. |
| **P3** | Korslänkar karta↔loggbok + "Senast"-rad på platskort | platser.html, loggbok.html | Liten | Polish. Kräver att loggboks-cachen (P0) finns. |
| **P3** | Backend `npc_replies`-fält (ersätter inline-dialog-regex) | main.py, chat.html | Medel | Robustare långsiktigt, men regex-lösningen (P1) fungerar tills dess. |

### Nyckelberoenden
```
P0 loggboks-cache ──► P1 ny-dag-banderoll ──► P2 karta (travel_log + "Senast"-rader)
P0 quest-data (finns redan) ──► P0 quest-tracker
P1 NPC-färger ──► P2 @NPC-individuella svar
```

### Sprites att lägga till i sprites.js (för nya features)
- `☀` finns redan (rad 119) — används för ny-dag-banderoll.
- `⚑` finns redan (rad 63) — används för quest-tracker + kartmarkörer.
- Saknas: `💤`/`🌙`-variant för "vilar till ny dag" (🌙 finns, rad 118), `🧭` kompass för kartan.
