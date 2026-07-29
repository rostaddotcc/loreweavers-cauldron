# 🗡️ BACKLOG — Mörkrets Rike

Kommande features och förbättringar. Uppdaterad 2026-07-29.

---

## 🎯 Från SoloQuest-artikeln (dev.to, Austin Amento)

### 🔴 Prio 1 — Spell management per caster-typ
DM-prompten skiljer inte på magiklasser. Lägg till caster-specifika regler:
- **Prepared casters** (Cleric, Druid, Paladin): förbereder spells efter long rest
- **Known casters** (Bard, Sorcerer, Warlock): kan bara sina kända spells
- **Spellbook casters** (Wizard): kan byta ur spellbook, men bara förberedda
- **Warlock-varning:** slots laddas på SHORT rest, inte long rest (vanligaste AI-felet)

### 🔴 Prio 1 — Riktigt valutasystem (inventory-baserat)
Pengarna ska vara en del av inventory, inte en separat placeholder. D&D 5e-valutor:
- **Konvertering:** 10 cp = 1 sp · 10 sp = 1 ep · 10 ep = 1 gp · 10 gp = 1 pp
  (eller förenklat: 100 cp = 10 sp = 1 gp · 10 gp = 1 pp)
- **Backend:** `[GULD:n]` → lägg till i rätt valör, auto-konvertera överflöde
  (t.ex. +250 cp → +2 sp +5 cp). `[GULD:-n]` → dra av, vägra om saldo < belopp.
- **Frontend:** Valvet/character.html visar alla valörer (pp/gp/ep/sp/cp)
  med ikoner. Guld-räknaren i chatten visar gp men hover visar alla.
- **Köp-mekanik:** NPC-handlare med prislista. Köp → dra av guld, lägg till föremål.
- **Vikt:** Mynt väger (50 mynt = 1 lb). Påverkar carry capacity.
- Just nu: `currency: {pp:0, gp:0, ep:0, sp:0, cp:0}` i state men ingen konvertering,
  ingen vikt, ingen köp-logik. Bara placeholder.

### 🔴 Prio 1 — Rikare strids-state
`truth_block()` har HP/inventory men saknar stridsfält. Lägg till:
- Initiative-ordning + vars tur det är
- Distans till fiender + line of sight + cover-värden
- Villkor med rundvaraktighet (concentration, prone, poisoned)
- Poisons med DC, disease stage progression
- Reser: travel pace, light level, time elapsed, passive perception

### 🟡 Prio 2 — Klientvalidering av tärningskrav
SoloQuest har en `roll:true`-flagga på varje förslag som klienten kollar
innan en handling skickas. Vi har inline-knappar men ingen hård gate.

### 🟡 Prio 2 — Commitment-based RNG
DM deklarerar DC FÖRE slaget (inte efter). Förhindrar "jag ändrar DC:n i efterhand".

---

## 🔮 Fas 3 (från DM Harness-planen)

### RAG + Qdrant (DELVIS KLAR)
- ✅ Qdrant-integration, index_transcript(), retrieve()
- ✅ purge_user() vid kampanjradering
- 🔲 Embedding-modell: utvärdera om nomic-embed-text räcker eller om vi vill ha bättre
- 🔲 Keyword-triggered lore (Story Cards / Lorebook-mönster)

### Faktaregister (DELVIS KLAR)
- ✅ FactRegister per kampanj, facts.json
- ✅ /api/facts endpoint + Minnesarkivet (facts.html)
- 🔲 Faktatillförlitlighet: automatisk konfliktupplösning (nya fakta ersätter gamla)
- 🔲 Viktning: pinmade fakta > extraherade > RAG

### Extraktionsmodell (KLAR)
- ✅ extract_facts() med billig modell (EXTRACTION_MODEL)
- 🔲 Utvärdera kvalitet: extraherar den rätt saker?

---

## 🎨 UI/UX

### Tärningskast-spektakel (efterfrågat av rostad)
- Partikelsystem: glittriga pixelpartiklar vid kast
- Nat 20 → diamant-explosion
- Nat 1 → dödskalle
- Rullningsanimation innan resultat

### XP-mekanik (efterfrågat av rostad)
- XP-bar i UI
- Level-up banner
- Nya effekt-typer för level up

### Quests i loggboken (efterfrågat av rostad)
- Quest-sektion med status (aktiv/slutförd/misslyckad)
- Quest-kort
- Data från /api/campaign/quests

### Kartförbättringar
- ✅ Dynamisk karta (inga hårdkodade platser) — KLAR 2026-07-29
- ✅ Seedad terräng, fog of war, quest-markörer — KLAR
- 🔲 Karta som reflekterar storyn: vägar mellan besökta platser
- 🔲 DM styr placering explicit: [PLATS:namn|norr|2 dagar]

---

## ✅ Nyligen klart (2026-07-29)
- 🛠️ Maskinrummet: live debug-konsol (ringbuffer + /api/debug/logs + frontend)
- 🗺️ Dynamisk karta: place_location() med md5-seed, inga DEFAULT_LOCATIONS
- 🧠 DM Harness Fas 1-2: truth_block, sliding window, Pydantic-validering,
  hierarkisk summering, per-turn regelinjicering, /save-kommandon
- ⚖️ Balansguardrails + prompt-versionering (v10) + combat/narrative-split
