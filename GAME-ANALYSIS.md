# 🐉 Mörkrets Rike — Speldesignanalys

**Datum:** 2026-07-28
**Analys:** Fullständig spelupplevelse, inte kodgranskning
**Dom:** Vacker fasad, trasig spelkärna. Potentialen är enorm — men just nu är det en chatbot med en fantastisk kostym.

---

## 1. Spelflödet (Player Journey)

### Steg-för-steg: vad spelaren faktiskt upplever

#### 🔐 Login (login.html)
**Spelaren ser:** En atmosfärisk port med glödande sigill, ember-partiklar, vinjett. "Vem vågar stiga in i mörkret?" Två fält: namn och lösenord.
**Spelaren gör:** Skriver in namn/lösenord, klickar "Stig in i mörkret".
**Känsla:** Utmärkt. Skakning vid fel, guldflash vid lyckat, ljud. Det känns som att kliva genom en portal. Bäst i hela appen.
**Problem:** "Glömt lösenordet?"-länken är död (`href="#"`). Inget registreringsflöde — nya spelare kan inte skapa konto utan att någon manuellt lägger till dem i `users.json`.

#### 🗺️ Vägskälet (adventure.html)
**Spelaren ser:** "Steg ett av fyra". Tre vägar: Förbered äventyr, Importera äventyr, Nytt äventyr. Om en kampanj redan finns syns en "Fortsätt"-panel.
**Spelaren gör:** Väljer en av tre vägar.
**Känsla:** Vackert presenterat. Hover-effekterna är läckra.
**Kritiska problem:**
- **"Förbered äventyr" är fejk.** Progressbaren är `setInterval` med slumpade procenttal. Resultatet ("4 NPCs, 3 platser, 2 uppdrag") är `Math.random()`. Inget skickas till backend. Spelaren tror att Qwen bygger en värld — det gör den inte.
- **"Importera äventyr" är också fejk.** Samma simulerade progressbar, samma slumpade siffror. Backend har en riktig `/api/import`-endpoint, men frontend anropar den aldrig.
- **"Nytt äventyr" fungerar** — men skickar bara `mode='freestyle'` till `sessionStorage` och redirectar. Backend skapar en kampanj med en slumpad öppningsstil, men spelaren får aldrig se vilken.
- **Stegräknaren säger "ett av fyra"** men det finns bara tre synliga steg (vägskäl → karaktär → chatt). Vad är det fjärde?

#### ⚔️ Karaktärsskapande (newgame.html)
**Spelaren ser:** "Steg ett av tre" (konflikter med adventure.html:s "ett av fyra"). Sex arketypskort med fantastisk lore. En textarea med prompt-mall. En "Frammana karaktär"-knapp.
**Spelaren gör:** Väljer arketyp (eller skriver fritt), klickar "Frammana".
**Känsla:** Arketypkorten är genuint bra skrivna. "Den Fallne Riddaren", "Askhäxan", "Gravjägaren" — varje kort har en hook, en hemlighet, ett mål. Tärningsanimationen under "vävningen" är charmig.
**Kritiska problem:**
- **Karaktärsgenereringen är helt simulerad.** `summon()` kör en `setTimeout(2400)` och visar sedan **hårdkodad data** från `ARCHETYPES[key].char`. Den anropar ALDRIG `API.generateCharacter()`. Backend-endpointen finns, men frontend använder den inte.
- **"Slå om ödet"** genererar inte en ny karaktär — den visar samma hårdkodade data igen.
- **Fri prompt ger "Vandraren"** — en hårdkodad fallback-karaktär, oavsett vad spelaren skriver.
- **"Till bordet"** sparar bara karaktärsnamnet i `sessionStorage` och redirectar till chat.html. Karaktärsarket (stats, HP, utrustning, bakgrundshistoria) sparas INGENSTANS. Det försvinner.

#### 💬 Vid bordet (chat.html)
**Spelaren ser:** En topbar med kampanjnamn, modellväljare, knappar. En sidebar med "Thalindra Mörkeld" (hårdkodad), fem NPCs, och platsen "Den Övergivna Kvarnen". Ett chattområde. En tärningsbricka. Ett inmatningsfält.
**Spelaren gör:** Skriver vad karaktären gör, trycker Enter.
**Känsla:** Demo-scriptet som spelar vid laddning (Session 4, kvarnen, Kael och Lyra) är stämningsfullt. DM-tankarna ("Väver berättelsen…", "Låter skuggorna tala…") är ett fantastiskt grepp. Tärningsbrickan är tillfredsställande att klicka på.
**Kritiska problem:**
- **Demo-scriptet spelar ALLTID vid laddning**, oavsett om det är en ny kampanj eller session 47. Spelaren möts av "Session 4 börjar" och en förskriven scen med Kael och Lyra — även om de just skapade en helt ny karaktär.
- **Sidebaren är hårdkodad.** "Thalindra Mörkeld", "Morvaine", "Kael Asksvärd" — dessa NPCs kommer från `NPCS`-objektet i JavaScript, inte från backend-state. Om DM:n skapar en ny NPC via `[NPC:...]`-taggen läggs den till i listan, men försvinner vid sidladdning.
- **Platsen är hårdkodad:** "Den Övergivna Kvarnen · Askans Dal · Natt, regn". Backend har `world.current_location` men frontend läser den aldrig.
- **Regel-oraklet är en uppslagsbok med fem hårdkodade svar.** "klättra", "smyga", "initiative", "besvärjelse", och en fallback. Det känns smart i 30 sekunder, sedan inser spelaren att det inte förstår frågor.

#### 🧙 Karaktärsark (character.html)
**Spelaren ser:** "Thalindra Mörkeld, Halvälva · Eldbesvärjare · Nivå 7". HP-mätare, besvärjelseplatser, XP-bar, förmågor, egenskaper, sparingskast. Tre flikar: Karaktär, Utrustning, Skattkammare.
**Spelaren gör:** Justerar HP manuellt, klickar på besvärjelseplatser, lägger till föremål, justerar mynt.
**Kritiska problem:**
- **Allt är hårdkodat.** `state`-objektet i JavaScript innehåller Thalindras stats, inventory, currency. Det har INGENTING att göra med den karaktär spelaren skapade i newgame.html eller den kampanj som finns i backend.
- **Ingen koppling till chatten.** Om DM:n säger "du tar 12 skada" måste spelaren manuellt klicka "−5 Skada" två gånger och sedan "−1" en gång. Det bryter immersionen totalt.
- **Ingen koppling till backend.** `exportState()`-funktionen finns men anropas aldrig. Backend har `state["character"]`, `state["inventory"]`, `state["currency"]` — men frontend skickar aldrig sin hårdkodade data dit.
- **XP och nivåer är statiska.** 23 400 / 34 000 XP. Inget i spelet ger XP. Nivå 7 för alltid.

#### 📖 Gestalter (npcs.html)
**Spelaren ser:** "Minnets hall" — en lista med sex NPCs. Klicka på en för att se dossier: första mötet, förtroende, uppdrag, handel, anteckningar, konversationshistorik.
**Spelaren gör:** Bläddrar bland NPCs, filtrerar, köper föremål från handlare.
**Känsla:** Det här är den BÄST skrivna delen av hela appen. Morvaine, Kael, Lyra, Borg, Halvard, Den Gröna Damen — varje NPC har en röst, en agenda, hemligheter. Konversationsloggarna känns som riktiga D&D-sessioner. Förtroendebaren, quest-statusarna, handelsgränssnittet — allt är genomtänkt.
**Kritiska problem:**
- **Allt är hårdkodat.** `NPCS`-arrayen i JavaScript. Ingen data från backend. Inga NPCs som DM:n skapar i chatten hamnar här.
- **Handel är lokal.** `buyItem()` drar från en lokal `purse`-variabel. Kommentaren säger "I produktion: POST /api/campaign/{id}/buy" — den endpointen finns inte.
- **Konversationer är statiska.** De visas som historik men uppdateras aldrig med nya samtal från chatten.
- **"Tala med X vid bordet"** länkar till chat.html men sätter inget kontext. Spelaren hamnar i chatten utan att spelet vet att de ville prata med Morvaine.

### Sammanfattning av flödet
```
Login ──→ Vägskäl ──→ Karaktär ──→ Chatt
  ✅        ⚠️ fejk      ⚠️ fejk      ⚠️ delvis
```
De tre första stegen är i princip en film. Spelaren klickar på saker, ser animationer, men inget av det de "gör" sparas eller påverkar spelet. Först i chatten finns en riktig backend-koppling — men chatten vet inget om karaktären, världen, eller NPCs:erna.

---

## 2. Spelsinne / Game Feel

### Pacing
**DM:s svarstid:** Backend anropar LLM med `max_tokens=1024` och `temperature=0.8`. Med Qwen 3.8 Max innebär det 3–15 sekunders väntan. Under tiden roterar DM-tankarna ("Väver berättelsen…", "Målar dimman över dalen…") — det är bra, det fyller väntan med karaktär.

**DM:s svarslängd:** Systemprompten säger "Håll svar under 150 ord för narration, kortare för NPC-dialog." Det är en BRA instinkt. Bords-D&D dör när DM:n monologiserar. Men 150 ord kan vara för kort för att bygga en scen — och det finns ingen mekanism för att DM:n ska kunna säga "det här kräver mer utrymme" vid viktiga ögonblick.

**Feedback mellan handlingar:** Spelaren skriver → väntar → får ett textblock. Inget mer. Ingen ASCII-art garanteras (bara om miljön triggar). Ingen ljudfeedback vid DM-svar (bara `SFX.receive()`). Ingen visuell markör för "det här är en viktig händelse". Det är en chatt. Det känns som en chatt.

**Problem:** Det finns ingen pacing-variation. Varje tur är: text → text → text. I bords-D&D varierar tempot: utforskning (långsamt) → strid (snabbt, tärningar) → social encounter (dialog) → vila (reflektion). Här är allt samma cadens.

### Agency
**Kan spelaren faktiskt GÖRA saker?** Ja och nej. Spelaren kan skriva vad som helst i chattfältet — det är fri text, inte val ur en lista. Det är bra. Men:
- Det finns inga mekaniska konsekvenser. Om spelaren skriver "jag hoppar över ravinen" säger DM:n antingen "du klarar det" eller "du faller". Det finns ingen tärning, ingen DC, ingen risk om DM:n inte själv väljer att begära ett kast.
- Tärningsbrickan finns men är frikopplad. Spelaren kan slå d20 när som helst, men resultatet påverkar ingenting om inte DM:n specifikt begärde det.
- `/rulla 1d20+4`-kommandot visar resultatet i chatten men skickar det INTE till DM:n. DM:n vet inte att spelaren slog.

**Känsla:** Spelaren är en författare som skriver vad karaktären gör, och DM:n är en medförfattare som skriver vad som händer. Det är kollaborativt berättande, inte ett spel. Det saknas det som gör D&D till D&D: att tärningarna kan säga NEJ.

### Immersion
**Bygger immersion:**
- Ember-partiklarna, vinjetten, kornet — den visuella atmosfären är konsekvent mörk och vacker
- DM-tankarna ("Låter skuggorna tala…") ger DM:n en närvaro
- NPC-färger och ikoner i chatten gör dialogen läsbar
- ASCII-art från atmosfär-subagenten (när den fungerar) är ett fantastiskt grepp
- SFX-systemet (ljud för kritiskt, misslyckande, tärningar, strid)
- Cinzel + Spectral-typografin känns som en gammal bok

**Bryter immersion:**
- Demo-scriptet vid chattstart — "Session 4" för en ny spelare
- Hårdkodade "Thalindra Mörkeld" i sidebaren när spelaren heter något annat
- Att karaktärsarket visar en helt annan karaktär än den man skapade
- Att NPC-kodexen visar NPCs man aldrig mött (eller inte finns i ens kampanj)
- Regel-oraklet som bara kan svara på fem frågor
- Att "Förbered äventyr" visar fejkade siffror ("7 NPCs, 5 platser") som inte existerar

### Tension
**Finns det risk?** I texten, ja. DM-systemprompten säger "Var INTE rädd för att säga nej. Konsekvenser ska kännas." Men det är en instruktion till LLM:n, inte en mekanism. Det finns:
- Inget HP-system i chatten (karaktärsarket är fristående)
- Ingen dödsmekanism (vad händer vid 0 HP? Ingenting.)
- Inga conditions (förgiftad, skrämd, blödande)
- Ingen resource management i spel-loopen (besvärjelseplatser, pilar, facklor)
- Ingen tidspress (det finns ingen "klocka" som tickar)

**Kan du misslyckas?** DM:n kan säga "du misslyckas" i text. Men det finns ingen mekanisk konsekvens. Inget HP avdrag. Inget förlorat föremål. Inget misslyckat uppdrag som markeras i systemet.

**Kan du dö?** Teoretiskt kan DM:n skriva "du dör". Men det finns ingen mekanism för det. Ingen "death saves". Ingen "du vaknar med 1 HP". Ingen konsekvens utöver texten.

### Reward loop
**Vad får spelaren?**
- XP: Ingenting ger XP. XP-baren på karaktärsarket är statisk (23 400 / 34 000).
- Loot: DM:n kan nämna "du hittar ett svärd" i text, men det hamnar inte i inventoryt.
- Guld: Karaktärsarket har en skattkammare, men ingen koppling till spelet.
- Quests: NPC-kodexen har quests, men de är statiska. Inget markerar "slutförd" när spelaren faktiskt löser dem.
- Nivå: Inget leveling-system. Nivå 7 för alltid.
- Berättelse: Det enda som faktiskt fungerar. DM:n kan skapa berättelseframsteg. Men utan mekaniska belöningar känns det som att läsa en bok, inte spela ett spel.

**Tillfredsställelse:** Låg. Spelaren får text. Text är bra, men det är inte en reward loop.

### Surprise
**Finns det överraskningar?**
- Äventyrsöppningen slumpas (5 stilar: meeting, alone, in_media_res, awakening, summoned) — men spelaren märker det inte, det är bara en systemprompt-instruktion.
- ASCII-art genereras ibland — det är en genuin överraskning, men kvaliteten varierar.
- DM:n kan skapa oväntade NPCs via `[NPC:...]`-taggen — det fungerar och är bra.
- Det finns INGA: slumpmässiga encounters, loot-tabeller, kritiska tabeller, väderförändringar, NPC-förräderier (utom om DM:n hittar på det), miljöhazarder, eller tidsbaserade events.

---

## 3. DM-beteende (AI as Dungeon Master)

### Systemprompt-analys

Prompten är 36 rader. Det är för kort för att styra en komplex D&D-session. Jämför med vad en mänsklig DM förbereder: kampanjstruktur, NPC-motivationer, stridsbalans, pacing-kurvor, session-mål.

#### Styrkor
- **Rollfördelningen är tydlig:** Narratör, NPC-skådespelare, Regeldomare, Världsbyggare. Det ger LLM:n en ram.
- **NPC-taggsystemet** (`[NPC:Namn|Roll|relation]`) är smart. Det gör att NPCs automatiskt hamnar i state.
- **Kastformatet** (`[KAST: 1d20+4 | SMIDIGHET]`) är väldefinierat och frontend parsar det.
- **150-ordsgränsen** förhindrar monologer.
- **"Avsluta alltid med en öppning"** är en utmärkt instruktion — den ger spelaren agency.

#### Svagheter

**Stridshantering: obefintlig.**
Prompten säger "Vid stridsstart: begär initiative med [KAST: 1d20+3 | INITIATIV]". Det är allt. Ingen instruktion om:
- Hur initiativordningen ska presenteras
- Hur HP ska spåras (DM:n har ingen tillgång till karaktärsarket)
- Hur attacker ska slås (attack roll vs AC? Skada?)
- Hur fienders HP ska hanteras
- Hur conditions fungerar
- Hur striden avslutas
- Hur XP delas ut efter striden

Resultatet: DM:n kommer att narrera strider som text. "Du hugger skelettet. Det faller." Inga tärningar, ingen spänning, ingen mekanik.

**Konsekvensspårning: obefintlig.**
Prompten säger "Kom ihåg detaljer" men ger ingen mekanism. Backend har sammanfattningar var 20:e tur, men:
- Sammanfattningarna är generiska ("Sammanfatta följande D&D-session")
- De fångar inte mekaniska tillstånd (HP, inventory, quest-status)
- DM:n ser bara de 2 senaste sammanfattningarna + 16 senaste meddelandena
- Efter 36+ meddelanden har DM:n glömt början av sessionen

**Balans narration vs. agency:**
Prompten säger "Bygg världen tillsammans med spelaren" men ger ingen vägledning om NÄR. Ska DM:n fråga spelaren "vad finns det för dörrar i rummet?" eller ska den bestämma själv? Utan riktlinjer kommer DM:n att antingen överstyra (bestämma allt) eller under-styra (fråga spelaren om allt, vilket bryter immersionen).

**Tärningskast vs. auto-resolve:**
Prompten säger "Begär kast när det passar" men definierar inte "passar". Ska ett enkelt hopp kräva ett kast? Ska social manipulation kräva CHA? Ska perception vara passiv? Utan riktlinjer blir det inkonsekvent — ibland begär DM:n kast för att öppna en dörr, ibland inte.

**Meningsfulla val:**
Prompten säger inget om hur DM:n ska skapa val. I bords-D&D är "meningsfulla val" kärnan: "Vill du rädda byborna eller jaga trollkarlen?" "Litar du på Morvaine eller Kael?" Utan instruktion om att skapa dilemman, konsekvenser av val, och förgrenande vägar blir det linjärt: "Du går framåt. Du ser en dörr. Du öppnar den."

**Svensk ton för dark fantasy:**
Prompten säger "Mörk, atmosfärisk, lite hotfull men aldrig hopplös. Tänk Dark Souls möter Sagan om Ringen." Det är en bra riktningsangivelse. Men:
- Inget om språkregister (ska NPCs tala ålderdomligt? Modernt? Dialekt?)
- Inget om hur mörkt det får bli (tortyr? Död? Förlust?)
- Inget om humor (dark fantasy behöver kontrast — en torr skämt, en absurd detalj)
- Inget om pacing inom ett svar (kort mening. Längre beskrivning. Kort igen.)

### Vad DM:n faktiskt producerar
Med `temperature=0.8` och `max_tokens=1024` får vi en DM som:
- Skriver atmosfäriskt men generiskt (LLM:ns default-fantasy)
- Skapar NPCs med namn men sällan med djup (prompten säger "egna agendor" men ger inga exempel)
- Hanterar strider som narration (ingen mekanik)
- Glömmer detaljer efter ~20 turer (kontextfönstret)
- Är konsekvent i ton (mörkt, svenskt) men inte i kvalitet

---

## 4. Karaktärsupplevelsen

### Skapandet
**Känns det meningsfullt?** Ja och nej. Arketyperna är fantastiskt skrivna — varje kort har en hook, en hemlighet, ett mål. Spelaren KÄNNER att de väljer en karaktär med djup. Men:
- Valet påverkar ingenting. Alla karaktärer hamnar i samma chatt, samma demo-script, samma hårdkodade sidebar.
- "Frammana karaktär" genererar inte en unik karaktär — den visar den hårdkodade arketypen.
- Fri prompt ger alltid "Vandraren" oavsett input.
- Karaktärens stats, HP, utrustning, bakgrundshistoria — allt försvinner när spelaren klickar "Till bordet".

### Påverkar stats spelet?
**Nej.** Karaktärsarket (character.html) visar STR 8, DEX 14, INT 18 — men ingenting i chatten eller backend läser dessa värden. DM:n vet inte att spelaren har INT 18. Tärningskasten är frikopplade. Det finns ingen mekanisk koppling mellan "min karaktär är stark" och "jag lyfter stenen".

### Koppling mellan ark och chatt
**Obefintlig.** Två helt separata världar:
- `character.html`: Hårdkodad Thalindra med HP 38/52, inventory, currency
- `chat.html`: Hårdkodad sidebar-Thalindra med HP-bar (73%), ingen koppling till backend
- `backend/state.json`: `character: {}` (tomt om inte `/api/character/generate` anropats)

Spelaren kan justera HP på karaktärsarket, men DM:n vet inte om det. DM:n kan säga "du tar 15 skada", men karaktärsarket uppdateras inte.

### Kan karaktären växa?
**Nej.** Inget XP-system i spel-loopen. Ingen leveling. Inga nya förmågor. Inga magiska föremål som hamnar i inventory. Karaktären är statisk från skapande till radering.

---

## 5. Sociala upplevelsen

### NPCs: levande eller statister?
**I kodexen (npcs.html): fantastiskt levande.** Morvaine med darrande händer och en kristall som "minns allt som någonsin dött". Kael som hatar odöda "personligt, inte principiellt". Borg som "säljer information lika gärna som öl — dyrare än ölet". Den Gröna Damen som "viskar namn. Mest Thalindras."

Det här är NPC-skriveri av hög kvalitet. Varje NPC har:
- En röst (konversationsloggar visar hur de talar)
- En agenda (quests med egna mål)
- Hemligheter (anteckningar)
- En relation till spelaren (förtroende-bar)
- Ekonomiska intressen (handlare med lager och priser)

**I chatten: statister.** DM:n kan skapa NPCs via `[NPC:...]`-taggen, men:
- NPCs från kodexen finns inte i DM:ns kontext (backend skickar bara namn/roll/relation, inte personlighet, hemligheter, eller konversationshistorik)
- DM:n kan inte referera till tidigare samtal med en NPC
- Förtroende, quest-status, handelslager — inget av det påverkar DM:ns beteende
- NPCs som DM:n skapar i chatten hamnar i backend-state men visas inte i kodexen

### Levande värld?
**Nej.** Världen är en textsträng: `world.current_location = "Den Övergivna Kvarnen"`. Det finns:
- Ingen karta eller spatial struktur
- Ingen tidsflyt (dagen är alltid "Natt, regn" i sidebaren)
- Ingen vädermekanik
- Inga händelser som sker oberoende av spelaren (marknadsdagar, festivaler, NPC-resor)
- Ingen känsla av att världen fortsätter när spelaren inte är där

### Quests som narrativ struktur?
**I kodexen: ja.** Quests har status (aktiv/slutförd/misslyckad), beskrivning, belöning. Det är en bra struktur.
**I spelet: nej.** Backend har `state["quests"]` men:
- DM:n skapar inte quests via taggar (bara NPCs)
- Quest-status uppdateras aldrig automatiskt
- Belöningar delas inte ut mekaniskt
- Spelaren kan inte se sina aktiva quests i chatten

---

## 6. Konkreta förbättringsförslag

### P0 — Gör spelet trasigt eller tråkigt (fixa först)

#### P0-1: Koppla karaktärsskapandet till backend
**Problem:** Spelaren skapar en karaktär som försvinner.
**Lösning:** `enterGame()` i newgame.html ska anropa `API.generateCharacter(prompt, model)` och spara resultatet i backend-state. Chat.html ska läsa karaktärens namn, klass, HP från backend och visa det i sidebaren. Character.html ska läsa och skriva till backend-state.
**Designmål:** Spelaren ska se SIN karaktär, inte Thalindra.

#### P0-2: Ta bort demo-scriptet i chat.html
**Problem:** Varje sidladdning spelar "Session 4" med Kael och Lyra, oavsett kampanjstatus.
**Lösning:** Om `turn_count === 0`, visa en välkomstscen baserad på `opening_style` från backend. Om `turn_count > 0`, ladda de senaste meddelandena från backend-transcriptet. Inget hårdkodat script.
**Designmål:** Spelaren ska se SIN historia, inte en demo.

#### P0-3: Gör "Förbered äventyr" och "Importera" äkta
**Problem:** Progressbarer och resultat är simulerade. Spelaren luras.
**Lösning:** Anropa riktiga endpoints. `startPrepare()` → `POST /api/world/build` (ny endpoint). `startImport()` → `POST /api/import` (finns redan). Visa riktiga resultat.
**Designmål:** Spelaren ska kunna lita på att det de ser är verkligt.

#### P0-4: Implementera en grundläggande stridsmekanik
**Problem:** Strider är ren narration. Ingen tärning, ingen HP, ingen risk.
**Lösning:** Utöka DM-systemprompten med stridsregler:
```
## Strid
- Vid stridsstart: begär initiative [KAST: 1d20+DEX | INITIATIV]
- Presentera initiativordningen: "1. Thalindra (18) 2. Skelett (12)"
- Varje runda: beskriv fiendens handling, be spelaren om sin
- Vid attack: begär [KAST: 1d20+MOD | ATTACK mot AC X]
- Vid träff: slå skada [KAST: XdY+MOD | SKADA]
- Spåra HP i svaret: "(Skelett: 12/22 HP)"
- Vid 0 HP: fienden besegras. Vid spelarens 0 HP: death saves.
- Efter strid: dela ut XP, beskriv byte.
```
**Designmål:** Strider ska ha mekanisk spänning, inte bara text.

#### P0-5: Koppla karaktärsarket till chatten
**Problem:** HP, inventory, currency är fristående från spel-loopen.
**Lösning:**
- DM:n ska kunna skicka `[SKADA:12]`, `[HELA:8]`, `[XP:250]`, `[GULD:50]`, `[FÖREMÅL:Svärd av frost]`-taggar
- Backend parsar dessa och uppdaterar state
- Character.html läser från backend-state
- Chat.html visar en mini-HP-bar i sidebaren som uppdateras i realtid
**Designmål:** "Du tar 12 skada" ska faktiskt minska HP.

### P1 — Signifikant förbättring av upplevelsen

#### P1-1: Quest-system i spel-loopen
**Design:** DM:n skapar quests via `[QUEST:Namn|Beskrivning|Belöning]`-taggar. Backend sparar dem i state. Chat.html visar aktiva quests i sidebaren. När DM:n skriver `[QUEST_SLUTFÖRD:Namn]` markeras den och belöningen delas ut.
**Varför:** Quests ger struktur. Utan dem är spelet "skriv vad du vill, DM svarar". Med dem finns det mål, riktning, och tillfredsställelse.

#### P1-2: NPC-personlighet i DM-kontexten
**Design:** När DM:n ska tala som en NPC, inkludera NPC:ns personlighet, hemligheter, förtroende, och senaste konversation i systemprompten. Inte bara "Morvaine (Gåtfull trollkarl, okänd)" utan "Morvaine: darrande händer, rädd för kristallen, kallar den 'den som minns', förtroende 35/100."
**Varför:** Just nu skapar DM:n generiska NPCs. Med personlighetsdata kan den spela dem som individer.

#### P1-3: Session-struktur
**Design:** Varje "session" ska ha en början, mitt, och slut:
- Början: "Ni vaknar i lägret. Det är dag 14. Det regnar. Kael snarkar." (atmosfär + status)
- Mitt: Äventyret, quests, strider
- Slut: "Ni slår läger för natten. XP: +350. Nya quests: 1." (sammanfattning + belöning)
Backend ska spåra `session_count` och generera en session-sammanfattning vid avslut.
**Varför:** Utan struktur känns det oändligt och riktningslöst.

#### P1-4: Slumpmässiga encounters och events
**Design:** Backend (eller DM-prompten) ska ha en tabell med slumpmässiga händelser:
- Vid resa: 20% chans för encounter (bakhåll, väder, NPC-möte, fynd)
- Vid vila: 10% chans för nattlig händelse (dröm, besökare, ljud)
- Vid handel: 15% chans för speciell vara eller nyhet
DM:n kan trigga detta via `[SLUMPA:encounter]`-tagg, eller backend kan injecta en systemmeddelande.
**Varför:** Överraskning är kärnan i D&D. Utan slump känns allt förutsägbart.

#### P1-5: Konsekvens-system
**Design:** DM:n ska kunna markera konsekvenser:
- `[KONSEKVENS:Byn brändes ner]` → sparas i state, påverkar framtida NPCs
- `[NPC_DÖD:Kael]` → Kael markeras som död i kodexen, DM:n refererar aldrig till honom igen
- `[QUEST_MISSLYCKAD:Vargens spår]` → quest markeras, NPC-förtroende sjunker
**Varför:** Utan konsekvenser finns inga val. Utan val finns inget spel.

#### P1-6: Karaktärsutveckling
**Design:**
- XP delas ut via `[XP:250]`-taggar
- Vid nivå: DM:n beskriver vad karaktären lär sig, nya förmågor läggs till
- Inventory uppdateras via taggar
- Besvärjelseplatser ökar med nivå
**Varför:** Karaktärsutveckling är den längsta reward-loopen i D&D. Utan den finns ingen anledning att fortsätta.

### P2 — Polish och glädje

#### P2-1: Väder- och tidsystem
**Design:** Backend spårar `world.time` (dag/natt, dag X) och `world.weather`. DM:n uppdaterar det via taggar. Chat.html visar det i sidebaren. ASCII-art kan variera med väder.
**Varför:** "Det är natt och det regnar" är atmosfär. Att veta att det VAR dag för tre timmar sedan ger tidskänsla.

#### P2-2: Karta / platsnavigation
**Design:** En enkel textbaserad karta i sidebaren: "Du är här: Kvarnen → (norr) Skogen → (öster) Väsby". DM:n uppdaterar platsen via `[PLATS:Kvarnens källare]`.
**Varför:** Spatial förståelse gör världen verklig. Utan den är allt "du är i en plats som beskrivs i text".

#### P2-3: Ljud-landskap
**Design:** Utöver SFX (som redan finns), bakgrundsljud per miljö: regn, eld, vind, strid. Aktiveras baserat på `detect_environments()`.
**Varför:** Ljud bygger immersion mer än visuell design.

#### P2-4: "DM:ns anteckningar" — en dold lager
**Design:** DM:n kan skriva "hemliga" anteckningar som spelaren inte ser men som påverkar framtida svar: `[HEMLIGT:Morvaine är egentligen den gröna damens son]`. Spelas upp som en "reveal" senare.
**Varför:** Foreshadowing och reveals är det bästa med D&D. Att DM:n kan planera i förväg (även om det är en LLM) skapar narrativ kohesion.

#### P2-5: Exportera som berättelse
**Design:** Export-funktionen (som redan finns som ZIP) ska kunna generera en formatterad PDF/Markdown-berättelse: kapitel per session, NPC-porträtt, ASCII-art inline, karaktärsark som bilaga.
**Varför:** Spelaren ska kunna visa sin historia. Det är den ultimata belöningen.

#### P2-6: Regel-oraklet → riktig LLM
**Design:** Ersätt de fem hårdkodade svaren med ett LLM-anrop (snabb modell, t.ex. qwen3.6-flash) med en D&D 5e-regelprompt.
**Varför:** Spelaren ska kunna fråga vad som helst om regler utan att bryta spelet.

---

## 7. Jämförelse med bords-D&D

| Vad som gör bords-D&D roligt | Finns det här? | Kommentar |
|---|---|---|
| Delad fantasi | ✅ Delvis | DM-text + ASCII-art bygger bilder. Men spelaren bidrar inte visuellt. |
| Meningsfulla val | ❌ | Inga mekaniska konsekvenser. DM:n kan skapa val i text, men inget system stödjer det. |
| Risk/belöning | ❌ | Ingen HP, ingen död, ingen loot, ingen XP. Tärningar är kosmetiska. |
| Karaktärsutveckling | ❌ | Statisk karaktär. Ingen leveling, inga nya förmågor. |
| Social dynamik | ⚠️ | NPC-kodexen är fantastisk, men NPCs i chatten är generiska. Ingen multiplayer. |
| Överraskning | ⚠️ | ASCII-art och NPC-taggar ger små överraskningar. Inga slump-encounters, inga kritiska tabeller. |
| Spänning i strid | ❌ | Ren narration. Ingen initiativordning, ingen HP-spårning, ingen attack vs AC. |
| Gemensamt skapande | ✅ | Fri text + DM-svar = kollaborativt berättande. Det fungerar. |
| Kampanjkänsla | ⚠️ | Backend har sessions, summaries, export. Men spelaren upplever det inte. |
| Återbesök | ❌ | Inget som lockar tillbaka. Ingen cliffhanger, inget "nästa session", ingen pågående quest. |

---

## 8. Slutdom

**Mörkrets Rike har en av de vackraste fasaderna jag sett i ett webbaserat rollspel.** Login-skärmen, arketypkorten, NPC-kodexen, ember-partiklarna, DM-tankarna — det är genomtänkt, atmosfäriskt, och genuint vackert. Texten i NPC-kodexen är bättre skriven än i många publicerade D&D-äventyr.

**Men under fasaden finns inget spel.** Det finns en chatbot. En väldigt bra chatbot med en fantastisk kostym, men en chatbot. Karaktären spelaren skapar försvinner. NPCs i kodexen existerar inte i chatten. Tärningarna påverkar ingenting. HP är en siffra på en sida som ingen läser. Quests är text som aldrig markeras som slutförd. Världen är en sträng.

**Det som behövs är inte mer frontend-polish.** Det som behövs är den mekaniska ryggraden: att karaktärens stats påverkar tärningarna, att tärningarna påverkar berättelsen, att berättelsen påverkar karaktären. En loop. Ett spel. Just nu är det en berättelsemaskin utan regler — och D&D utan regler är inte D&D, det är improvisationsteater.

**Prioritering:** P0-1 (karaktärskoppling) och P0-4 (stridsmekanik) är de två förändringar som skulle förvandla det här från "chatbot med tema" till "rollspel". Allt annat bygger på dem.

---

*Analysen baserad på: login.html, adventure.html, newgame.html, chat.html, character.html, npcs.html, api.js, backend/main.py, backend/models.py (DM_SYSTEM_PROMPT), backend/atmosphere.py, backend/state_manager.py*
