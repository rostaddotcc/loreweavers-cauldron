# 🗡️ BACKLOG — Mörkrets Rike / The Lore Weaver's Cauldron

Kommande features och förbättringar. Uppdaterad 2026-08-02.

---

## 🔴 Öppna punkter

### 🐛 TTS — Qwen-audio-3.0-TTS (OÅTGÄRDAD)
`ConnectionError: WebSocket connection is not established` från
`dashscope/audio/tts_v2/speech_synthesizer.py:820` (call → `__start_stream` →
`__send_str`). Model `qwen-audio-3.0-tts-plus`, voice `longanlingxin`,
`wss://token-plan.ap-southeast-1.maas.aliyuncs.com/api-ws/v1/inference`.
Nyckel finns (DASHSCOPE_API_KEY). POST /api/tts → 502. Anslutningen etableras
aldrig — sannolikt SDK/endpoint-version eller fel `base_websocket_api_url`.

### 🔴 Prio 1 — Spell management per caster-typ
Spells-tilldelning är KLAR (char-gen + Guardian `spells_add` + karaktärsblad).
Men DM-prompten skiljer fortfarande inte på magiklasser:
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
- Distans till fiender + line of sight + cover-värden
- Villkor med rundvaraktighet (concentration, prone, poisoned)
- Poisons med DC, disease stage progression
- Reser: travel pace, light level, time elapsed, passive perception
- ✅ Dödsräddningar finns (character.death_saves, DÖDSRÄDDNING-tag, nat 1/20)

### 🟡 Prio 2 — Klientvalidering av tärningskrav
SoloQuest har en `roll:true`-flagga på varje förslag som klienten kollar
innan en handling skickas. Vi har inline-knappar men ingen hård gate.

### 🟡 Prio 2 — Commitment-based RNG
DM deklarerar DC FÖRE slaget (inte efter). Förhindrar "jag ändrar DC:n i efterhand".

### 🟡 Kartförbättringar (kvar)
- 🔲 Karta som reflekterar storyn: vägar mellan besökta platser
- ✅ Dynamisk karta + Guardian-position fixad (current_location i Guardian-schema)

### 🟡 RAG / Faktaregister (kvar)
- 🔲 Embedding-modell: utvärdera om nomic-embed-text räcker
- 🔲 Keyword-triggered lore (Story Cards / Lorebook-mönster)
- 🔲 Faktatillförlitlighet: automatisk konfliktupplösning
- 🔲 Viktning: pinmade fakta > extraherade > RAG

---

## ✅ Nyligen klart (2026-08-02)

### ⚔️ Combat v28 — Allies i strid + @NPC-chatt (commit a648efa)
- `[ALLIERAD:namn|HP|AC]`-tag → allies registreras mitt i striden, egna turer i
  turn_order (`ally-{id}`), döda hoppas över, initiativ re-synkas
- Guardian: `ally_attacks` + `ally_damage` — HP, död, faller-log
- Frontend: 🛡️ ally-kort (HP-bar, arcane-lila), fallen-state, turn-chip, statusbar
- **@NPC-chatt:** `@Mimmrick: ...` → NPC-kontext injiceras i DM-prompten efter
  RAG-blocket → DM svarar i roll. "Talking to X"-chip i chatten
- Tester: 18 backend + 19 DOM (31 totalt) + 18 NPC-chatt = **36/36 pytest, 31/31 DOM**

### ✨ Spells tilldelade (commit 3594c8e)
- Char-gen-schemat kräver klass-anpassade besvärjelser (≥2 cantrips + ≥2 nivå-1
  för kasterklasser, icke-kaster → [])
- `_finalize_character` normaliserar spells-listan (rensar skräp, single-dict)
- Guardian `spells_add`: tilldelar spells vid level-up/scroll/undervisning, dedup
- Karaktärsbladet renderar ✨ Spells-kort (nivå, skola, casting time, 🎲, beskrivning)
- Tester: 12 nya (avatar + spells) = **48/48 pytest**

### 🎨 DM-avatar: slumpade arketyper (commit 3594c8e)
- Bort med hårdkodad "horned mask" → 18 arketyper × 10 moods × 9 paletter
- Seed-styrd slump: samma seed = samma bild, ny seed = nytt motiv
- Testat: aldrig döskalle/horn, deterministiskt per seed

### 🐛 PLAYER_MODELS + deepseek-v4-flash (commit 3594c8e)
- Direkt DeepSeek (api.deepseek.com, DEEPSEEK_API_KEY) saknades i PLAYER_MODELS →
  icke-admin klampar till qwen3.8-max (token-plan) → 429
- Nu: robert m.fl. kan köra `deepseek-v4-flash` som motor direkt
- E2E verifierat: DM vaknar + öppnar scenen på svenska med DeepSeek som motor

### 🪶 Scribe-loader v27.3 (commit b6a05a5)
- Pergament + fjäderpenna + bläck i CLI/ascii-stil, typewriter-tankar,
  flygande bläckpixlar (DM + Lorekeeper)

### 🦉 Lorekeeper-rebrand (commit f476580)
- Guardian → Lorekeeper i all användarvänd text (tekniska identiteter bevarade)

### ⚔️ Combat v27 / v27.2 (commits caff8aa, e48f47b)
- Stridslogg med split-view (chat + stridspanel), turn-order, statusar
- Hybrid turn-avancering: LLM driver + deterministiskt skyddsnät
- Dag-dropdowns i kampanjöversikten

---

## 🎨 UI/UX (klart sedan tidigare)

- ✅ Tärningskast-spektakel: partiklar, nat 20 → diamant-explosion, nat 1 → dödskalle
- ✅ XP-bar + level-up-banner (XP_THRESHOLDS, level_up-effekt)
- ✅ Quests i loggboken (status, kort, /api/campaign/quests)
- ✅ Dynamisk karta: seedad terräng, fog of war, quest-markörer
- ✅ "Så spelar du"-onepager på Vägskälet (DM / Guardian / Tärningar)
- ✅ Maskinrummet: live debug-konsol med användarfiltrerade loggar
- ✅ Vikt/loggning: max_weight_lbs = STR×15, Guardian-vikter, övervikt-vägran
- ✅ Item-system konsoliderat: _normalize_item enda källa, lore-fallback, roll-knapp
