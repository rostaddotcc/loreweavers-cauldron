# ⚔️ Combat Tracker + Audit Fixes — Implementation Spec (2026-07-31)

Projekt: `~/dnd-llm` (repo rostaddotcc/morkrets-rike). Live: dnd.rostad.cc:8092.
Kontrakt mellan tre parallella subagent-spår. Läs HELA denna fil innan du börjar.

## SHARED JSON KONTRAKT (alla spår)

### world.combat (backend-state, nyckel `world["combat"]`)
```json
{
  "active": true,
  "round": 1,
  "initiative": [
    {"key": "player", "name": "Faelyndra", "value": 17},
    {"key": "enemy:0", "name": "Goblin A", "value": 14}
  ],
  "enemies": [
    {"id": 0, "name": "Goblin A", "hp": 3, "max_hp": 7, "ac": 13, "alive": true, "statuses": []}
  ],
  "log": [
    {"round": 1, "actor": "enemy:0", "name": "Goblin A", "text": "träffar dig — 6 skada"},
    {"round": 1, "actor": "player", "name": "Faelyndra", "text": "hugger Goblin A — 4 skada"}
  ],
  "started_turn": 42,
  "ended_turn": null
}
```
- `key`: `"player"` eller `"enemy:<id>"`. `id` = index i enemies-arrayen.
- `enemies[].id` = index i arrayen (0-baserat). Behåll stabilt.
- `actor` i log: `"player"` eller `"enemy:<id>"`.

### character.death_saves (backend-state)
```json
{"successes": 0, "failures": 0}
```
Nollställs vid healing/återuppvaknande.

### Maskinläsbar tagg i Guardian-meddelandet (frontend-kontrakt)
Guardian-rapporten avslutas med (om combat ändrades):
```
[COMBAT:{"active":true,"round":2,"initiative":[{"key":"player","name":"X","value":17},{"key":"enemy:0","name":"Goblin A","value":14}],"enemies":[{"id":0,"name":"Goblin A","hp":3,"max_hp":7,"ac":13,"alive":true,"statuses":[]}]}]
```
JSON i taggen är URL-encoded (inga raw `"` — använd `urllib.parse.quote`/`JSON.stringify` på ett säkert sätt; frontend: `decodeURIComponent` + `JSON.parse`). Frontend tar bort taggen ur synlig text, parsar den, uppdaterar combat-panelen. F5-safe: `loadTranscript()` måste också parsa taggen.

---

## SPÅR A — backend/guardian.py (ENDAST denna fil + state-schema.json)

Filwhitelist: `backend/guardian.py`, `state-schema.json`. RÖR INTE main.py, models.py, frontend/*.

### A1. GUARDIAN_POST_SYSTEM — nya fält (lägg till i prompten)
- `combat_start`: `{"enemies": [{"name": "Goblin A", "hp": 7, "ac": 13}]}` — sätts när DM börjar en strid och INTE använde [STRID:]-taggen. Fiender med HP och AC.
- `initiative_entries`: `[{"name": "Goblin A", "value": 14}]` — fiendernas initiativ (spelarens sätts av main.py från [Resultat:]).
- `combat_end`: `{"reason": "alla besegrade" | "flydde" | "spelaren flydde" | "..."}` — sätts när striden är över.
- Ta BORT `ascii_art` från prompten helt (ATMOSPHERE_ENABLED=0 ändå) — sparar tokens.
- Anti-dubbel-regel: "Om en mekanisk effekt redan applicerats via en tagg i DM-narrationen (t.ex. [SKADA:12]), extrahera INTE samma effekt igen."
- Dödsräddning: "Om spelaren är på 0 HP och slår dödsräddningar, notera resultatet i logbook/combat-log."
- Uppdatera JSON-exemplet i prompten med de nya fälten (combat_start, initiative_entries, combat_end) och ta bort ascii_art-raden.

### A2. apply_mechanics — ny signatur + combat-logik
```python
def apply_mechanics(state, mech, skip_effects=None) -> list[dict]:
```
- `skip_effects`: optional lista av `(type, value)`-tupler (eller dicts med type/value) som REDAN applicerats denna tur (från DM-taggar). Skippa matchande `skada`, `hela`, `xp`, `guld`, `föremål`-effekter. Jämför med `e.get("type")` och `str(e.get("value"))`.
- **Item-härdning (P0):** alla `int(item.get(...))` → `int(item.get(...) or 0)` (explicit null får inte krascha). Samma för `damage_dice` etc: använd `.get("x") or default`. Lägg try/except runt items_add-loopen? Nej — gör casting-buggen omöjlig istället.
- **corrections (P0):** `action=="retract" and field=="items_add"` → hitta föremålet med MATCHANDE NAMN i inventory (case-insensitive) och ta bort det, INTE `inv.pop()`. Hittas inget → no-op.
- **combat_start:** skapa `world["combat"]` = `{"active": True, "round": 1, "initiative": [], "enemies": [{"id": i, "name":..., "hp":..., "max_hp":..., "ac":..., "alive": True, "statuses": []}], "log": [], "started_turn": meta.turn_count, "ended_turn": None}`. Effect `{"type": "combat_start", "value": "Goblin A, Goblin B"}`.
- **combat_damage:** existerande `damage`-listan: om `target != "player"` OCH fienden finns i `world.combat.enemies` → minska `hp`, lägg till i `log` (`{"round": world.combat.round, "actor": "enemy:<id>"|"player", "name": ..., "text": f"tar {amount} skada ({type})"}`) och effect `{"type": "combat_dmg", "value": name, "amount": amount}`. Om hp <= 0 → `alive=False`, effect `{"type": "enemy_död", "value": name}`. (Behåll även gamla `_add_npc_note`-beteendet om fienden INTE är i combat.)
- **death:** om fienden finns i combat → `alive=False` + effect `enemy_död`. Alla enemies `alive=False` → auto `combat_end` med reason "alla besegrade".
- **initiative_entries:** merga in i `world.combat.initiative` (ersätt samma key/name). Effect `{"type": "initiativ", "value": "Goblin A: 14"}` per entry.
- **combat_end:** `world.combat.active=False`, `ended_turn=turn`, sätt log-sammanfattning, effect `{"type": "combat_end", "value": reason}`. (Kalla detta även när combat_start aldrig sattes men fiender dött — no-op om ingen combat.)
- **Level-up HP per klass (P2):** ersätt `hp_gain = max(1, 5 + con_mod)` med HD-baserad: HD-map `{"Barbarian": 12, "Fighter": 10, "Paladin": 10, "Ranger": 10, "Bard": 8, "Cleric": 8, "Druid": 8, "Monk": 8, "Rogue": 8, "Warlock": 8, "Sorcerer": 6, "Wizard": 6}`, default 8. `hp_gain = max(1, hd // 2 + con_mod)` (5e medelvärde per nivå). Matca klass case-insensitive.

### A3. format_guardian_summary — combat-rendering + [COMBAT:] tagg
- Ny effekt-rendering för: `combat_start` ("⚔ **STRIDEN BÖRJAR** — Goblin A, Goblin B"), `combat_dmg`, `enemy_död` ("💀 **Goblin A faller!**"), `initiativ`, `combat_end` ("🏁 **Striden är över** — reason").
- I slutet av summary: om `world.combat` ändrats denna tur → lägg till `[COMBAT:<urlencoded-json>]` med hela combat-objektet. (Använd `urllib.parse.quote(json.dumps(combat))`.)
- Sätt `combat_changed`-flagga: true om någon effect i listan är combat-relaterad (combat_start/combat_dmg/enemy_död/initiativ/combat_end) ELLER mech innehöll combat_start/initiative_entries/combat_end.

### A4. state-schema.json
- Lägg till `world.combat` (active/round/initiative/enemies/log/started_turn/ended_turn) och `character.death_saves` i schemat.

### Verifiering Spår A
```bash
cd ~/dnd-llm && backend/.venv/bin/python -c "import sys; sys.path.insert(0,'backend'); import guardian; print('GUARDIAN OK')"
grep -c "combat_start" backend/guardian.py   # ≥ 5 (prompt, apply, summary, effects)
grep -c "skip_effects" backend/guardian.py   # ≥ 2
```

---

## SPÅR B — backend/main.py + backend/models.py

Filwhitelist: `backend/main.py`, `backend/models.py`. RÖR INTE guardian.py (förutom att anropa), frontend/*, state-schema.json.

### B1. [STRID:] tagg (main.py)
- Ny regex: `STRID_PATTERN = re.compile(r'\[STRID:([^\]]+)\]')` — format `[STRID:Goblin A|7|13, Goblin B|7|13]` (name|hp|ac, komma-separerat).
- `_parse_strid_tag(text, state) -> tuple[str, list[dict]]`: skapar `world["combat"]` (samma struktur som Spår A A2 combat_start — KOPIERA strukturen exakt), `round=1`, `log=[]`, `started_turn=turn_count`, effects `[{"type":"combat_start","value": "Goblin A, Goblin B"}]`. Om redan aktiv combat → uppdatera enemies (ersätt listan) men behåll round/initiative.
- Anropa i `/api/chat` efter `_parse_mechanical_tags`-loopen (efter att reply är ren). Taggen stripas ur reply.

### B2. Dedup (P0) — main.py
- `_guardian_post_dm(...)` får ny parameter `skip_effects: list | None = None`.
- I `/api/chat`: när du skapar guardian_task, skicka `meta["last_effects"]` (eller effekterna från denna turs taggparsning) som skip_effects.
- `_guardian_post_dm` skickar dem vidare till `guardian_extract_mechanics`→... nej: till `apply_mechanics(state, mech, skip_effects=skip_effects)`.

### B3. [Resultat:] initiative + death saves (main.py)
- I `/api/chat`, när `req.message.startswith("[Resultat:")`:
  - Parsa `[Resultat: ETIKETT → VÄRDE (rullar)]` — återanvänd befintlig logik om den finns; annars regex `\[Resultat: ([^→]+) → (\d+)(?: \(([^)]*)\))?\]`.
  - Om etiketten innehåller "INITIATIV"/"INITIATIVE" (case-insensitive) OCH `world.combat.active`: lägg till `{"key":"player","name": character.name, "value": int(värde)}` i `world.combat.initiative` (ersätt befintlig player-entry). Sortera INITIATIV-listan? Nej — behåll insättningsordning; frontend sorterar.
  - Om etiketten innehåller "DÖDSRÄDDNING"/"DEATH SAVE" (case-insensitive): uppdatera `character.death_saves`:
    - nat1 (rullar-arrayen innehåller "1" som första värde och notation var 1d20): failures += 2
    - värde >= 20: wakes — `hp.current = max(1, hp.current)`, sätt `hp.current=1` om 0, nollställ death_saves
    - värde >= 10: successes += 1
    - annars: failures += 1
    - successes >= 3 → stabiliserad: nollställ, sätt `character.death_saves.stabilized=true`? — enklast: nollställ + notera i effects. failures >= 3 → DÖD: `character.death_saves.dead=true` (frontend visar).
  - DM:n ska få detta i systemprompten (se B4).
- Behöver en `_parse_result_tag`-hjälpfunktion.

### B4. _build_system_prompt — combat-block + death-save-block
- Om `world.combat.active`: injicera block:
  ```
  ## ⚔️ PÅGÅENDE STRID
  Runda: N
  Fiender (HP/AC): Goblin A (3/7 HP, AC 13), Goblin B (7/7 HP, AC 13)
  Turordning: [Du] → Goblin A → Goblin B
  Ditt HP: X/Y · Ditt AC: Z
  ```
  Hämta från state. Om `initiative` tom → säg "Initiativ ännu ej rullat."
- Om `character.hp.current == 0`: injicera dödsräddningsblock: "Spelaren är på 0 HP. Du MÅSTE begära [KAST: 1d20 | DÖDSRÄDDNING] varje runda tills stabiliserad/död. Framgångar: N, Misslyckanden: N. 3 framgångar = stabil, 3 misslyckanden = död. Nat 20 = vaknar med 1 HP."

### B5. Faktextraktion varannan tur (P2)
- I `_post_turn_tasks`: kör faktextraktion bara när `turn_count % 2 == 0` (Guardian + inventory-ändringar körs som vanligt). Kommentera varför.

### B6. XP_THRESHOLDS-dedup (P2)
- Ta bort `XP_THRESHOLDS`-definitionen i main.py, importera istället `from guardian import _XP_THRESHOLDS as XP_THRESHOLDS` (guardian.py har redan listan). Uppdatera användningar (`_parse_mechanical_tags` level-up + ev. andra).

### B7. CHARACTER_PROMPT + char-gen-endpoint (P1 mekanik)
- CHARACTER_PROMPT_SV/EN: ändra JSON-schemat så `ac`, `initiative`, `perception` INTE är hårdkodade 10/0/10 — skriv istället: `"ac": 10 + DEX-mod (+ rustning om utrustad)`, `"initiative": DEX-mod`, `"perception": 10 + WIS-mod` som instruktion. Be modellen BERÄKNA rätt värden från abilities.
- `saves`: be modellen fylla med klassens save-proficiencies (krigare = STR/CON etc.).
- I char-gen-endpointen (efter LLM-svar): **backup-beräkna** — om `ac <= 10` och DEX-mod > 0 → `ac = 10 + dex_mod`; om `perception <= 10` och WIS-mod > 0 → `perception = 10 + wis_mod`; `initiative = dex_mod` om 0. Se till att abilities finns innan.
- Uppdatera save-proficiencies: om saves tom → fyll från klass (STR/CON för Fighter/Paladin/Barbarian, INT/WIS för Wizard, DEX/INT för Rogue/Monk, WIS/CHA för Cleric/Druid/Sorcerer/Bard/Warlock/Ranger).
- Level-up HP: använd guardian `_XP_THRESHOLDS` (B6) och lämna HP-ökningen till apply_mechanics (Spår A).

### B8. models.py — DM_CORE_PROMPT v23 + DM_COMBAT_PROMPT
- Bump `DM_PROMPT_VERSION = "v23"`.
- DM_CORE_PROMPT tillägg:
  - Sektion "DÖDSRÄDDNING": "Om spelaren når 0 HP: beskriv dödens närhet, begär [KAST: 1d20 | DÖDSRÄDDNING] varje runda. Guardian spårar 3 framgångar/misslyckanden."
  - Sektion "STRID (Guardian håller koll)": "Vid strid skriver du [STRID:namn|HP|AC, namn2|HP|AC] när striden börjar. Nämn fiende-HP/AC när du beskriver striden. Guardian håller reda på skada, rundor och turordning."
  - Skärp längd: ersätt "Standardnarration: håll under 150 ord" med "Standardnarration: 1–3 meningar per handling, kortare i action, längre i atmosfär."
  - Aktiva resurser: "Om spelaren har en aktiv tärningsresurs (Bardic Inspiration, Second Wind etc.), påminn om att använda den när det passar."
- DM_COMBAT_PROMPT: lägg till punkt 0: "Öppna striden med [STRID:namn|HP|AC, ...]." och förtydliga "När spelarens initiativresultat kommer in, nämn turordningen: 'Du agerar först...'". Lägg till: "Efter strid: narrera efterspelet — Guardian avslutar striden."

### Verifiering Spår B
```bash
cd ~/dnd-llm && backend/.venv/bin/python -c "import sys; sys.path.insert(0,'backend'); import main; print('MAIN OK')"
grep -c "STRID" backend/main.py          # ≥ 4
grep -c "DÖDSRÄDDNING" backend/main.py   # ≥ 2
grep -c "v23" backend/models.py          # ≥ 1
```

---

## SPÅR C — frontend/chat.html + frontend/snes.css + frontend/sprites.js

Filwhitelist: `frontend/chat.html`, `frontend/snes.css`, `frontend/sprites.js`. RÖR INTE backend/*, api.js, övriga .html-sidor.

### C1. Parsa [COMBAT:...]-taggen
- I Guardian-rendering (både live via `buildMessage`/`addMessage` och `loadTranscript`): hitta `[COMBAT:<urlencoded>]` i slutet av guardian-texten, `decodeURIComponent` + `JSON.parse`, ta bort taggen ur synlig text, anropa `renderCombatPanel(combat)`.
- Helper: `function parseCombatTag(text) -> {clean, combat|null}`.
- Lägg parsing i en funktion som körs efter att guardian-msg skapats: `applyCombatTag(el, text)`.
- I `loadTranscript`, efter att guardian-msg lagts till, kör samma.
- Dedup: spara senast renderade combat-objekt (`let _lastCombat = null;`) — rendera bara om JSON.stringify ändrats.

### C2. Combat-panelen "Krigsrådet" (battle rail)
- Struktur (lägg in i DOM vid init, gömd tills combat):
  ```html
  <div id="combat-rail" class="hidden">
    <div class="cr-head"><span class="cr-round">⚔ RUNDA 1</span><span class="cr-hp">❤ 12/20</span></div>
    <div class="cr-initiative"></div>   <!-- initiativ-strip -->
    <div class="cr-enemies"></div>      <!-- fiende-tokens + HP bars -->
    <div class="cr-status"></div>       <!-- death save pips etc -->
  </div>
  ```
- **Desktop:** fast rail mellan sidebar och chat (flex-column, width ~220px, stone-bg, edge-border, `pointer-events:auto`). **Mobile (≤900px):** kompakt banner ovanför inputen, horisontell scroll.
- **Rundmarkör:** Cinzel, guld, candle-flicker animation (reuse `.candle` keyframes eller enkel text-shadow pulse).
- **Initiativ-strip:** flex-row chips `[namn: värde]`; aktiv deltagare (första i listan) får glow-ring; spelaren arcane-färg, fiender blood-färg. Klass: `.cr-ip`, `.cr-ip.active`.
- **Fiende-tokens:** använd `SPR.html()`/sprites.js 8×8 sprites (hash på namn som NPCs gör). Varje fiende: sprite + namn + HP-trough (`.cr-hpbar` med fill-width %, blood-gradient, sheen-sweep, alarm-puls < 25%) + status-runor.
- **Death save pips:** om `player.hp.current == 0`: visa `💀 ●●○` (successes gröna, failures blod) i rail-status.
- Dölj panelen när `combat.active == false` (fade-out + collapse). Vid `combat_end` visa kort segerrad i 3s.
- Alla nya klasser prefixas `cr-` (undvik snes.css-kollisioner).
- **snes.css:** lägg `#combat-rail` + `.cr-*` regler i en tydlig sektion. Se till att mobil-klasser hamnar i desktop-hidden-listan om de bara ska synas på mobil.

### C3. Stridslogg i chatten (Guardian-rapport omformaterad)
- Guardian-rapporten är text; behåll den som fallback, MEN: om texten innehåller radbrytningar som börjar med stridsmönster (⚔ STRIDEN BÖRJAR, 💀 X faller, 🏁 Striden är över, 💔/combat_dmg) → rendera som `.combat-log`-kort:
  - Header: `⚔ RUNDA N` (guld, DOS-box-hörn) — gruppera per runda om möjligt (parse "Runda"/turn-text).
  - Rader: fiende-actions blod-röda, spelar-actions arcane, dödsfall med ✕ + fade.
  - Enklast: rendera Guardian-texten i ett `.combat-log`-container istället för `.guardian-box` när combat-taggen finns i meddelandet.
- Använd befintliga design-tokens: `--blood`, `--arcane`, `--gold`, `--term-green`, monospace för loggen.

### C4. Initiativceremoni
- När `[COMBAT:]`-tagg innehåller initiative (och det inte redan visats): rendera i chatten en `.initiative-reveal`-kort: `Goblin A: 14 · Du: 17 → **Du agerar först**` (sortera, markera första). SFX.battle().

### C5. Resume-recap "Senast i Mörkrets Rike…" (P1 UX)
- I `loadTranscript`, om kampanjen har historik (transcript längre än ~2 meddelanden OCH inte redan visat denna session): lägg en hopfällbar `.resume-card` överst i chatten:
  - Titeln: "🕯️ Senast i Mörkrets Rike…"
  - Innehåll: Plats (world.current_location), Dag (world.day), HP (current/max), Aktiva uppdrag (första 3), senaste 1-2 DM-meddelanden (kort, 140 tecken).
  - Data från `API.getCampaign()` + transkriptet. Kollapsbar (klicka headern).
  - Visa bara en gång per sidladdning (sessionStorage-flagga).

### C6. Model-gate snes.css-städning (P2)
- I `#model-gate` inline-styles: ta bort `border-radius: 8px`, `box-shadow`, gradient-bakgrunder (ersätt med `background: var(--stone-2)`, `border-radius: 0`, ingen shadow) så det matchar snes.css flat-stil. Knappen: flat gold (bakgrund var(--gold), text mörk, border-radius 0).

### C7. Design-regler (måste följas)
- Använd befintliga tokens (`--ink`, `--stone*`, `--edge*`, `--gold`, `--blood`, `--arcane`, `--term-green`, `--bone*`). INGA nya färger.
- Fonts: Cinzel för rubriker (med letter-spacing + uppercase + liten storlek), Spectral/monospace för text. ASCII/DOS-känsla: skarpa hörn (border-radius 0).
- Allt ska vara touch-vänligt: minst 44px tap-targets, `:active`-tillstånd.
- Inga placeholder-funktioner — allt ska fungera.

### Verifiering Spår C
```bash
cd ~/dnd-llm/frontend && python3 -c "
import re
html = open('chat.html').read()
scripts = re.findall(r'<script>(.*?)</script>', html, re.DOTALL)
open('/tmp/chat_inline.js','w').write('\n;\n'.join(scripts))
" && node --check /tmp/chat_inline.js && echo "JS OK"
grep -c "renderCombatPanel" chat.html    # ≥ 2 (definition + anrop)
grep -c "combat-rail" chat.html          # ≥ 2
grep -c "resume-card" chat.html          # ≥ 2
grep -c "cr-" snes.css                   # ≥ 10
```

---

## ALLMÄNNA REGLER
1. **Bryt inte saker som fungerar.** Backend: `backend/.venv/bin/python -c "import main"` måste fungera. Frontend: `node --check` på extraherad JS måste klara.
2. **Spara filer med write_file/patch — inte heredoc i terminal.**
3. **Om du stöter på något som inte matchar specen, gör det MINSTA rimliga valet och dokumentera i din slutrapport.**
4. **Verifiera ditt eget arbete med kommandona ovan innan du rapporterar klart.**
5. Rapportera: exakt vilka funktioner/rader du ändrade, vad som är kvar för människan.
