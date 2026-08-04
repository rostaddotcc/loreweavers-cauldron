# DM-HARNESS: Arkitekturforskning för LLM-drivna D&D-spel

**Fördjupad forskningsrapport för The Lore Weaver's Cauldron (dnd.rostad.cc)**
*Datum: 2026-07-29 · Författare: Hermes-forskningssubagent*

---

## Sammanfattning (TL;DR)

En "DM-harness" är kodlagret mellan LLM:n och spelet. Dess jobb är att **LLM:n aldrig ska behöva komma ihåg något — harnessen kommer ihåg åt den.** Forskningen visar att mogna implementationer (NarrativeEngine-P, SoloQuest, Multihog, dnd-llm-game) alla konvergerar mot samma fem principer:

1. **Prompten monteras varje tur** av en deterministisk pipeline med en hård token-budget — aldrig "skicka med hela historiken".
2. **Auktoritär state i JSON** deklareras som sanning och får aldrig motsägas av narrationen.
3. **Strukturerat svar** (prosa + maskinläsbara taggar/JSON) valideras och parsas efter varje anrop, med retry vid fel.
4. **Flerlagsminne**: korttids (verbatim) + episodisk (arkiv) + semantisk (faktaregister/kunskapsgraf) + hämtning via RAG.
5. **Två modeller**: en kreativ för narration, en billig för state-extraktion och validering.

The Lore Weaver's Cauldron har redan en stark grund (mekaniska taggar, rullande summaries, tagg-enforcement). De största vinsterna ligger i: **hierarkisk minnessökning (RAG), ett auktoritärt faktaregister, strukturerad JSON-validering med retry, och en dedikerad extraktionsmodell.**

---

## 1. Kontextfönster-hantering

### 1.1 Token-budget: hur produktionsspel fördelar utrymmet

Det finns ingen universell procentsats, men mönstret är konsekvent: **systemprompt + auktoritär state är skyddad (aldrig trimmad), historiken är den flexibla bufferten.**

AI Dungeon använder en uttrycklig **70%-regel**: om de "nödvändiga elementen" (instruktioner, plot essentials, summary, story cards) överstiger 70% av fönstret, trimmas lägre-prioriterade sektioner. Minnet närmast nutid och senaste handlingen inkluderas alltid i sin helhet.

En praktisk budget för ett 32k-fönster (Qwen3.8-max) i The Lore Weaver's Cauldron:

```
┌──────────────────────────────────────────────────────────┐
│  SYSTEM (skyddat, ~25-30%)                               │
│  ├─ DM-persona + regler + taggprotokoll      ~1 500 tok  │
│  ├─ Auktoritär state-JSON (kompakt)          ~800 tok    │
│  ├─ Faktaregister (pinmade sanningar)        ~500 tok    │
│  └─ Aktiva lore-kort (nyckelordsutlösta)     ~700 tok    │
├──────────────────────────────────────────────────────────┤
│  MINNE (~15-20%)                                         │
│  ├─ Hierarkisk summary (kapitelöversikter)   ~600 tok    │
│  └─ RAG-hämtade relevanta scener             ~1 500 tok  │
├──────────────────────────────────────────────────────────┤
│  HISTORIK (flexibel buffert, ~40-50%)                    │
│  └─ Senaste N meddelanden verbatim           ~6 000 tok  │
├──────────────────────────────────────────────────────────┤
│  GENERERING (reserverat, ~10-15%)                        │
│  └─ DM:ns svar + resonemang                  ~2 000 tok  │
└──────────────────────────────────────────────────────────┘
```

**Nyckelinsikt:** historiken är den enda delen som skalas. När fönstret fylls, komprimeras *äldre* historik — aldrig state, aldrig regler, aldrig de senaste 8 meddelandena.

### 1.2 Sliding window: hur många meddelanden?

The Lore Weaver's Cauldron kör idag `last_n=16`. Det är rimligt, men gränsen är skör: ett meddelande kan vara allt från 20 till 400 tokens. Bättre strategi är en **token-baserad** window, inte meddelandebaserad:

```python
def sliding_window_by_tokens(transcript, budget_tokens, min_messages=8):
    """Fyll baklänges tills budgeten är slut, men behåll minst min_messages."""
    kept, used = [], 0
    for entry in reversed(transcript):
        t = count_tokens(entry["content"])
        if used + t > budget_tokens and len(kept) >= min_messages:
            break
        kept.append(entry)
        used += t
    return list(reversed(kept))
```

**Gränshantering:** när ett meddelande kapas vid gränsen, ersätts den kapade delen med en en-rads markör: `[...tidigare i detta samtal sammanfattat i kapitel 3...]`. Detta förhindrar att LLM:n svarar på ett halvt uttalande. NarrativeEngine-P behåller alltid de **8 senaste verbatim** och komprimerar resten.

### 1.3 Hierarkisk summering

The Lore Weaver's Cauldron summerar var 20:e tur till en platt lista. Forskningen (arXiv 2308.15022 "Recursively Summarizing Enables Long-Term Dialogue Memory") visar att **rekursiv/hierarkisk** summering slår platt summering rejält för långa konversationer:

```
Nivå 0 (rådata):    [tur 1..20] [tur 21..40] [tur 41..60] ...
Nivå 1 (scen):      summary-A   summary-B    summary-C    ← var 20:e tur
Nivå 2 (kapitel):      chapter-summary-1      ← var 5:e scen-summary
Nivå 3 (kampanj):          campaign-arc       ← var 3:e kapitel
```

Varje nivå sammanfattar nivån under. Prompten injicerar **senaste 2-3 på varje nivå** — detta ger både detalj (nivå 1) och långtidsbåge (nivå 3) inom en fast token-budget oavsett kampanjlängd.

**Vilken modell?** En billig/snabb modell (The Lore Weaver's Cauldron's `ATMOSPHERE_MODEL`-mönster, eller `qwen3.6-flash`) — summering kräver precision, inte kreativitet. dnd-llm-game använder `granite4:350m` för denna typ av utility-arbete.

**Vad ska bevaras exakt?** NarrativeEngine-P:s regel: tärningsresultat, HP/MP-värden och alla egennamn bevaras ordagrant genom varje komprimering. "Dramatiska ögonblick" taggas och överlever omkomprimering. Detta är kritiskt — en summary som tappar att "Kael dog" eller "spelaren lovade att återlämna svärdet" bryter immersionen permanent.

### 1.4 Prioritetssystem: vad kapas först?

När fönstret svämmar över, i stigande kapningsordning (det som kapas först → sist):

1. Äldsta verbatim-historik (ersätts av summary)
2. Äldsta scen-summaries (ersätts av kapitel-summary)
3. Icke-aktiva lore-kort (de som inte triggarats nyligen)
4. **ALDRIG:** auktoritär state, pinmade fakta, senaste 8 meddelanden, taggprotokoll

---

## 2. DM-harness-mönstret

En harness är en pipeline med tre faser: **PRE → LLM → POST**. The Lore Weaver's Cauldron har redan en ansats till detta i `chat()`-endpointen, men den kan formaliseras.

### 2.1 Pre-processing (FÖRE LLM-anropet)

```python
def pre_process(state, player_input, turn):
    # 1. Extrahera avsikt ur spelarens input (nyckelord → regelbehov)
    intent = extract_intent(player_input)        # "attack", "smyga", "social"

    # 2. RAG: hämta relevanta minnen/lore för just denna input
    memories = retrieve_relevant(player_input, state, k=3)

    # 3. Regelinjicering: topp-3 relevanta regler (SoloQuest-mönster)
    rules = score_and_pick_rules(intent, top_k=3)

    # 4. Montera systemprompt med token-budget
    system = assemble_system(
        persona=DM_SYSTEM_PROMPT,
        state=compact_authoritative_state(state),
        facts=state["pinned_facts"],
        lore=active_lore_cards(player_input),
        rules=rules,
        memories=memories,
    )

    # 5. Bygg meddelandelista (system + summaries + sliding window + input)
    return build_messages(system, state, player_input)
```

**Per-turn regelinjicering (SoloQuest):** istället för att hoppas att modellen minns Sneak Attack från träningsdata, körs en lätt nyckelordsextraktor på spelarens input som matchas mot en strukturerad regel-DB (exakt tagg-match > lös innehålls-match), och topp-3 injiceras i user-prompten. Modellen måste inte *erindra* regeln — den ligger rätt framför den. Skalar bra: ny mekanik = ett nytt regelobjekt.

### 2.2 Post-processing (EFTER LLM-anropet)

The Lore Weaver's Cauldron gör redan mycket här (`_parse_npcs`, `_parse_roll_requests`, `_parse_mechanical_tags`). Det som saknas är **validering och retry**:

```python
async def post_process(raw_reply, state, max_retries=2):
    for attempt in range(max_retries + 1):
        # 1. Extrahera struktur (prosa vs taggar vs JSON)
        parsed = parse_response(raw_reply)   # → {narration, tags, state_update}

        # 2. Validera mot Pydantic-schema
        errors = validate(parsed, state)

        if not errors:
            break

        if attempt < max_retries:
            # 3. Repair-prompt: skicka tillbaka felen, be om rättelse
            raw_reply = await llm_call(repair_prompt(parsed, errors))
        else:
            # 4. Sista utväg: behåll prosan, kassera trasig mekanik
            parsed = sanitize_to_prose_only(parsed)

    # 5. Applicera validerade state-förändringar
    new_state, effects = apply_effects(parsed.tags, state)

    # 6. Uppdatera faktaregister + minne (asynkront, billig modell)
    schedule_extraction(parsed.narration, new_state)

    return parsed.narration, new_state, effects
```

### 2.3 Response structure enforcement

Det finns tre nivåer av strukturering, i stigande tillförlitlighet:

**Nivå 1 — Inline-taggar (The Lore Weaver's Cauldron's nuvarande):** `[SKADA:12]` i fri prosa. Lätt att implementera, men LLM:n kan "glömma" taggar eller narrera skada utan tagg. Kräver enforcement-streaks (som redan finns).

**Nivå 2 — Sektionsblock (SoloQuest):** kräv fyra explicita sektioner varje tur:

```
<NARRATIVE>
Fri prosa — det spelaren ser.
</NARRATIVE>
<MECHANICS>
[SKADA:12] [XP:50]
</MECHANICS>
<SUGGESTIONS>
- "Anfall skelettet" (roll:true, dc:14)
- "Fly norrut" (roll:false)
</SUGGESTIONS>
<STATE_UPDATE>
{"enemy_hp": {"skelett": 4}}
</STATE_UPDATE>
```

Parsern mappar MECHANICS direkt till state-övergångar. Klienten kollar `roll:true` innan en handling skickas — **LLM:n kan bokstavligen inte hoppa över tärningen.**

**Nivå 3 — Constrained decoding / JSON mode:** grammatikbegränsad avkodning (Outlines, XGrammar, OpenAI `response_format`) *garanterar* giltig JSON vid genereringstillfället. Kombinera med post-validering (Pydantic/Instructor) för innehållskorrekthet — "defense in depth". Instructor-biblioteket patchar LLM-klienten, validerar mot en Pydantic-modell och **retry:ar automatiskt med valideringsfelet** om det blir fel.

**Rekommendation för The Lore Weaver's Cauldron:** behåll inline-taggar för prosa-nära mekanik (de fungerar och är spelarvänliga), men lägg till ett `<STATE_UPDATE>`-JSON-block + Pydantic-validering med retry för de tunga state-förändringarna. Qwen3.8 stödjer `response_format`/JSON-läge via DashScope.

### 2.4 Multi-pass-arkitektur

Separata anrop för separata bekymmer:

```
Pass 1 (kreativ modell):  narration + inline-taggar
Pass 2 (billig modell):   state-extraktion → "State Memo"
Pass 3 (valfri):          validering/konsistenskontroll (lore check)
```

**Multihog-mönstret:** en separat billig modell (Gemini Flash-Lite) kör en andra pass på varje AI-svar och extraherar HP/inventory/buffs/XP. Resultatet injiceras som en "State Memo" i varje efterföljande prompt. Detta **frikkopplar extraktionskvalitet från narrationskvalitet** — DM-modellen får vara kreativ medan utility-modellen är precis.

**dnd-llm-game:** DM-modell (`llama3.2:1b`) för narration (cap 1000 tecken/200 ord), utility-modell (`granite4:350m`) för tärningsbeslut, world-state-extraktion och spelarval-knappar.

---

## 3. Texthantering

### 3.1 Narrationslängd

The Lore Weaver's Cauldron har "håll narration under 150 ord" i prompten. Det fungerar, men modeller driver mot längre svar över tid. Tre förstärkningar:

- **Hård `max_tokens`** (redan 1024) — det fysiska taket.
- **Explicit intervall** istället för tak: "Skriv 80-150 ord. Action: kortare (60-100). Atmosfär: längre (120-180)."
- **dnd-llm-games kapning:** DM-svar kapas hårt vid 1000 tecken/200 ord i backend. Brutalt men effektivt — garanterar konsekvens.

### 3.2 NPC-dialog-separation

The Lore Weaver's Cauldron har redan `@NPC`-konvention och NPC-registry med färger/ikoner. Nästa steg (från NarrativeEngine-P):

- **Personlighets-hexagon** per NPC (6 axlar, −3 till +3: Drive, Diligence, Boldness, Warmth, Empathy, Composure) som styr *hur* NPC:n talar. Värdena driver naturligt över tid — ett svek urholkar Warmth.
- **Voice-profil i state:** ålderdomligt för gamla, kort för soldater, poetiskt för alver (finns redan i prompten — gör det till data per NPC istället för global instruktion).

### 3.3 Tonkonsistens över hundratals turer

- **Author's Note / ton-ankare (NovelAI):** en kort ton-beskrivning injiceras *sent* i prompten (nära generation = högre uppmärksamhetsvikt). The Lore Weaver's Cauldron lägger ton i början av systemprompten; att duplicera en komprimerad ton-påminnelse precis före historiken förstärker efterlevnaden.
- **Lore Check (NarrativeEngine-P):** ett QA-verktyg som kör på valfritt meddelande och korsrefererar mot lore + arkiv, returnerar en dom (consistent / unsupported / contradicts) med citat och omskrivningsförslag. Kan automatiseras som ett bakgrundspass.

### 3.4 Spelar-synlig vs intern text

Allt som lagras ska inte visas:

| Innehåll | Lagras | Visas för spelare |
|---|---|---|
| Narration (prosa) | ✅ | ✅ |
| Mekaniska taggar | ✅ (som effects) | ❌ (renderas som systemmeddelande) |
| STATE_UPDATE-JSON | ✅ (state) | ❌ |
| DM-intern resonemang (`<think>`) | ❌ (strippas) | ❌ |
| Faktaregister-extraktion | ✅ | ❌ (kan visas i debugpanel) |

The Lore Weaver's Cauldron strippar redan `<think>`-taggar i `_extract_json` — bra. Utöka så att *all* intern struktur strippas innan `append_message` sparar till transkriptet, så att arkivet bara innehåller ren prosa.

---

## 4. State-serialisering

### 4.1 JSON vs naturligt språk vs hybrid

Forskning och praktik pekar mot **hybrid**: strukturerad JSON för maskinläsbar state, men *renderad till kompakt naturligt språk* i prompten. Ren JSON med `indent=2` (The Lore Weaver's Cauldron's nuvarande `json.dumps(char, indent=1)`) slösar tokens på formatering.

```python
# FÖRE (slösar tokens):
{"hp": {"current": 38, "max": 52}, "level": 7, "class": "Krigare"}

# EFTER (kompakt, LLM-vänligt):
"Thalindra, Krigare niv 7. HP 38/52. AC 16. Bär: Frostens Egg (rare)."
```

**Regel:** JSON är lagringsformatet (persistens, export, validering). Inför prompten renderas en `compact_state()`-funktion som producerar tät, läsbar text. Behåll full JSON endast för de fält LLM:n faktiskt behöver resonera om.

### 4.2 Auktoritär state

SoloQuest-mönstret: deklarera state som `authoritative` i prompten med explicita konsekvenser:

```
## SANNING (auktoritär — motsäg ALDRIG detta)
Följande är det enda sanna tillståndet. Du får INTE narrera att spelaren
träffar en fiende bakom fullt skydd, att en död NPC talar, eller att ett
föremål finns i inventariet om det inte står nedan.
HP: 38/52 | Plats: Kvarnens källare | Fiender: Skelett (4/22 HP)
```

The Lore Weaver's Cauldron har redan "Motsäg dig inte" i prompten — gör det till en **maskingenererad, alltid-närvarande sanningsektion** snarare än en allmän instruktion.

### 4.3 Delta vs full state

- **Full state varje tur** för små states (<1k tokens) — enkelt, robust, ingen drift. The Lore Weaver's Cauldron är här idag och det fungerar.
- **Delta-uppdateringar** när statet växer: skicka full state var N:e tur, däremellan bara `[FÖRÄNDRAT sedan förra turen: HP 52→38, ny NPC: Aldric]`. Kräver att harnessen diff:ar state mellan turer.
- **Previous-turn mechanical trace (SoloQuest):** skicka med förra turnens *faktiskt applicerade* mekanik ("Goblin Scout tog 6 skada, nu 4 HP"). Förhindrar drift där modellen åter-narrerar en träff som egentligen var en miss.

### 4.4 Entitet-relation-representation

The Lore Weaver's Cauldron's `npcs[]` är en platt lista. Nästa steg är en **typad relationsgraf** (open-tabletop-gm, NarrativeEngine-P):

```json
{
  "entities": [
    {"id": "npc_aldric", "type": "npc", "name": "Aldric"},
    {"id": "loc_kvarn", "type": "location", "name": "Kvarnens källare"},
    {"id": "item_egg", "type": "item", "name": "Frostens Egg"}
  ],
  "relations": [
    {"from": "npc_aldric", "to": "pc", "type": "allierad", "weight": 2,
     "source": "tur 42: 'Jag svär att följa dig'"},
    {"from": "npc_aldric", "to": "loc_kvarn", "type": "vistas_vid"},
    {"from": "pc", "to": "item_egg", "type": "äger"}
  ]
}
```

Varje relation har en **verbatim käll-ankare** (vilken tur den uppstod). En `scene-context`-fråga drar automatiskt vem-som-känner-vem för den aktuella scenen utan att läsa hela NPC-filer. NarrativeEngine-P går längre med **NPC-mål i tre nivåer** (kort/medel/lång sikt), **pressure-system** (ignored/engaged-räknare med decay) och **knowledge boundaries** (witness tracking — en NPC refererar aldrig till en hemlighet den inte bevittnade).

---

## 5. Minnesarkitekturer

### 5.1 RAG för kampanjhistorik

The Lore Weaver's Cauldron's största gap. Idag: senaste 2 summaries + 16 meddelanden. Allt äldre är osynligt för LLM:n.

**Tvåfas-hämtning (NarrativeEngine-P):**
1. **Kapitel-skann:** utvärdera LLM-genererade kapitelöversikter för att identifiera vilka förseglade kapitel som är relevanta.
2. **Scen-hämtning:** inom dessa kapitel hämtas specifika scener via lokala vektor-embeddings (lagrade i `sqlite-vec`), rankade efter vikt, och injiceras **verbatim**.

Resultat: "GM:n kan exakt minnas att Bob svek sällskapet i kapitel 3 och citera den exakta dialogen — även om det var 50 kapitel och 200 sessioner sedan."

**Implementation för The Lore Weaver's Cauldron:**
- Embedding-modell: `nomic-embed-text` (Ollama, lokalt) eller DashScope-embedding.
- Vektorlager: `sqlite-vec` (passar den befintliga JSON-per-kampanj-strukturen) eller LanceDB (dnd-llm-game).
- Chunkning: en embedding per scen/summary + en per NPC-interaktion.
- Hämtning: `retrieve(player_input, k=3)` → injiceras som "Relevanta minnen" i prompten.

### 5.2 Kunskapsgrafer

Zep (arXiv 2501.13956) och MRAgent (arXiv 2606.06036) visar att **hybrid-hämtning** slår ren vektorsökning: kombinera **vektor (semantisk) + BM25 (nyckelord) + graftraversering** i en fråga. Zep rapporterar sub-sekund latens vid 95:e percentilen — tillräckligt snabbt för realtidsspel.

**Episodisk vs semantisk minne** (den viktigaste distinktionen):

| Typ | Innehåll | Lagring | Exempel |
|---|---|---|---|
| **Episodisk** | "vad hände" — händelser i tid | Vektor-arkiv, tidsstämplar | "I tur 42 stred vi mot skelett i kvarnen" |
| **Semantisk** | "vad är sant" — fakta om världen | Faktaregister / kunskapsgraf | "Kael är död. Byn Gråvakt brändes. Spelaren är skyldig Aldric 50 gp." |

The Lore Weaver's Cauldron har embryot till semantiskt minne i `lore[]` (via `[KONSEKVENS:]`-taggen) och `state.json`. Det som saknas är att **systematiskt extrahera och deduplicera** fakta.

### 5.3 Minneskonsolidering

NarrativeEngine-P:s **Divergence Register** är den bästa referensimplementationen:

- Extraherar automatiskt world-state-fakta efter varje tur: vem är var, vem äger vad, allianser, dödsfall, löften, skulder.
- Kategoriserat: locations, NPC events, promises & debts, world state, party facts, lore & rules.
- **Pinna** högprioriterade fakta så de alltid är i kontext oavsett token-budget.
- **Semantisk deduplicering och faktaklustring** förhindrar att redundanta poster sväller kontexten.

**Konsoliderings-pipeline för 100 sessioner:**
```
Råtranskript (100 sessioner)
  → scen-summaries (1 per ~20 tur)          [episodisk, vektor-indexerad]
  → kapitel-summaries (1 per ~5 scen)       [episodisk, injiceras]
  → kampanj-båge (1, uppdateras löpande)    [semantisk, alltid i kontext]
  → faktaregister (deduplicerade sanningar) [semantisk, pinmade + RAG]
```

---

## 6. Riktiga implementationer (kodnivå)

| Repo | Nyckelmönster | Lärdom för The Lore Weaver's Cauldron |
|---|---|---|
| **NarrativeEngine-P** (Sagesheep) | Förlustfritt scen-arkiv, tvåfas RAG, auto-condensation (3 strategier), Divergence Register, NPC personlighets-hexagon, witness tracking, Lore Check, scene-level rollback | Den mest kompletta referensen. Prioritera: Divergence Register + tvåfas RAG. |
| **dnd-llm-game** (tegridydev) | Dual model (DM + utility), SSE-streaming, LanceDB RAG för PDF-lore, hård svarskapning (1000 tkn), utility-modell genererar spelarval | Bekräftar dual-model + RAG. Lätt att läsa (FastAPI, som The Lore Weaver's Cauldron). |
| **SoloQuest** (dev.to) | 4-lagers prompt (Rules Contract, per-turn SRD-injection, authoritative state, enforced structure), WRONG/RIGHT-exempel, previous-turn trace | The Lore Weaver's Cauldron har redan WRONG/RIGHT + authoritative-inslag. Lägg till per-turn regelinjicering. |
| **Multihog D&D Framework** (SillyTavern) | Second-pass state-extraktion, Lorebook Agent, World Progression, hybrid RNG (commitment-based), temporal buff-decay | Second-pass extraktion + commitment-RNG (deklarera DC före kast). |
| **open-tabletop-gm** (Bobby-Gray) | Allt i Markdown, typad relationsgraf med käll-ankare, scene-context-fråga, Python hanterar ALL mekanik (noll LLM) | Relationsgraf + "LLM rör aldrig mekanik"-princip. |
| **llm_RPG** (gddickinson) | Strukturerat JSON-protokoll för NPC-dialog, retrieval-scored NPC-minne, "Legendarium" (världens kollektiva minne), heuristisk offline-fallback | JSON-protokoll + fallback om LLM:n fallerar. |
| **RPGBench** (arXiv 2502.00595) | Benchmark för strukturerad event-state, regelbaserad + LLM-baserad utvärdering | Ger en utvärderingsmetod för att mäta om harnessen faktiskt fungerar. |

---

## 7. Föreslagen DM-HARNESS-ARKITEKTUR för The Lore Weaver's Cauldron

Konkret design byggd på den befintliga kodbasen (`main.py`, `state_manager.py`, `models.py`).

### 7.1 Prompt-monteringspipeline

```
┌─────────────────────────────────────────────────────────────┐
│                    DM HARNESS PIPELINE                       │
├─────────────────────────────────────────────────────────────┤
│  IN: player_input, state.json                               │
│                                                              │
│  ① INTENT      extract_intent(input) → {action, skill, dc}  │
│  ② RETRIEVE    RAG(input, state) → 3 relevanta minnen       │
│  ③ RULES       score_rules(intent) → topp-3 regler          │
│  ④ STATE       compact_state(state) → tät text + sanning    │
│  ⑤ ASSEMBLE    montera systemprompt (token-budgeterad)      │
│  ⑥ WINDOW      sliding_window_by_tokens(hist, 6000)         │
│  ⑦ LLM CALL    kreativ modell → rått svar                   │
│  ⑧ PARSE       parse_response() → {narration, tags, json}   │
│  ⑨ VALIDATE    Pydantic → retry (max 2) vid fel             │
│  ⑩ APPLY       apply_effects() → ny state + effects[]       │
│  ⑪ EXTRACT     (async) billig modell → faktaregister        │
│  ⑫ PERSIST     spara state, transkript (ren prosa), minne   │
│                                                              │
│  OUT: {narration, effects[], roll_requests[], state}         │
└─────────────────────────────────────────────────────────────┘
```

### 7.2 Token-budget (32k-fönster)

```python
TOKEN_BUDGET = {
    "system_persona":   1500,   # DM_SYSTEM_PROMPT (versionerad)
    "authoritative_state": 800, # compact_state() + sanningsektion
    "pinned_facts":      500,   # faktaregister, pinmade
    "active_lore":       700,   # nyckelordsutlösta lore-kort
    "injected_rules":    400,   # topp-3 per-turn regler
    "rag_memories":     1500,   # 3 hämtade scener
    "summaries":         800,   # hierarkiska (2 per nivå)
    "history":          6000,   # sliding window (flexibel)
    "generation":       2000,   # reserverat för svar
    # ~14 200 använt av 32 000 — marginal för resonemangsmodeller
}
```

### 7.3 State-serialiseringsformat

Lagring: nuvarande `state-schema.json` (JSON, oförändrat). Nytt: `compact_state()` + faktaregister.

```python
def compact_state(state) -> str:
    c = state["character"]
    lines = [
        f"{c['name']}, {c['class']} niv {c['level']}. "
        f"HP {c['hp']['current']}/{c['hp']['max']}. AC {c.get('ac','?')}.",
        "Bär: " + ", ".join(i["name"] for i in state["inventory"] if i.get("equipped")),
        f"Plats: {state['world']['current_location']}. Tid: {state['world'].get('time','?')}.",
        "Fiender: " + ", ".join(f"{e['name']} ({e['hp']} HP)" for e in state.get("enemies", [])) or "inga",
        "Aktiva uppdrag: " + ", ".join(q["name"] for q in state["quests"] if q["status"]=="aktiv"),
    ]
    return "\n".join(lines)

def truth_block(state) -> str:
    return ("## SANNING (auktoritär — motsäg ALDRIG)\n"
            + compact_state(state)
            + "\nPinmade fakta:\n"
            + "\n".join(f"- {f}" for f in state.get("pinned_facts", [])))
```

### 7.4 Svarsparsning & validering

```python
from pydantic import BaseModel, ValidationError

class MechanicsBlock(BaseModel):
    damage: int | None = None
    heal: int | None = None
    xp: int | None = None
    gold: int | None = None
    new_npcs: list[str] = []
    new_quests: list[str] = []

class DMResponse(BaseModel):
    narration: str
    mechanics: MechanicsBlock
    roll_requests: list[dict] = []
    state_update: dict = {}

async def parse_and_validate(raw, state, max_retries=2):
    for attempt in range(max_retries + 1):
        narration, tags = strip_tags(raw)          # befintlig logik
        try:
            parsed = DMResponse(
                narration=narration,
                mechanics=tags_to_mechanics(tags),
                roll_requests=parse_rolls(raw),
                state_update=extract_json_block(raw),
            )
            validate_against_state(parsed, state)   # HP inom 0..max, etc.
            return parsed
        except (ValidationError, ValueError) as e:
            if attempt < max_retries:
                raw = await llm_call(repair_prompt(raw, str(e)))
            else:
                return DMResponse(narration=narration, mechanics=MechanicsBlock())
```

### 7.5 Minneslager

```
┌─ L1 KORTTIDS:   senaste 8-16 meddelanden verbatim (alltid)
├─ L2 EPISODISK:  scen-summaries (var 20:e tur) + kapitel (var 5:e)
│                 → vektor-indexerade (sqlite-vec + nomic-embed-text)
├─ L3 SEMANTISK:  faktaregister (Divergence Register-liknande)
│                 → extraheras asynkront, dedupliceras, pinmade fakta alltid med
├─ L4 LORE:       nyckelordsutlösta lore-kort (NPCs, platser, fraktioner)
└─ L5 ARKIV:      fullt transkript per session (.jsonl) — ALDRIG i prompt, bara export/RAG-källa
```

### 7.6 Retry/valideringslogik

```
rått svar
  ├─ strippa <think>/reasoning (finns redan)
  ├─ parse tags + JSON
  ├─ Pydantic-validering
  │    ├─ OK → applicera
  │    └─ FEL → repair-prompt (max 2 retries)
  │              ├─ fixat → applicera
  │              └─ fortfarande fel → kassera mekanik, behåll prosa, logga
  ├─ state-konsistens: HP clamp, död-NPC-talar-kontroll, plats-existerar
  └─ enforcement-streaks (finns redan): tag_streak, missing_roll_streak
```

---

## 8. Prioriterad implementeringsroadmap

### Fas 1 — Omedelbar högsta effekt (1-2 dagar)
1. **`compact_state()` + sanningsektion** — byt `json.dumps(indent=1)` mot tät text + "SANNING (auktoritär)". Sparar tokens, minskar motsägelser. *(Högsta ROI — direkt mätbar.)*
2. **Token-baserad sliding window** — ersätt `last_n=16` med `sliding_window_by_tokens(budget=6000, min=8)`.
3. **Previous-turn mechanical trace** — injicera förra turnens applicerade effekter i prompten.
4. **Strippa intern struktur ur transkriptet** — spara bara ren prosa i arkivet.

### Fas 2 — Strukturell robusthet (3-5 dagar)
5. **Pydantic-validering + retry-loop** för mekanik-block (Instructor-mönster).
6. **Hierarkisk summering** — lägg till kapitel-nivå (var 5:e scen-summary) + kampanj-båge.
7. **Per-turn regelinjicering** — nyckelord → score → topp-3 regler i user-prompten.
8. **`<STATE_UPDATE>`-JSON-block** i svaret + Qwen JSON-läge.

### Fas 3 — Minne & uthållighet (1-2 veckor)
9. **Faktaregister (Divergence Register)** — async extraktion, dedup, pinmade fakta. *(Löser "DM:n glömmer saker" på riktigt.)*
10. **RAG för kampanjhistorik** — sqlite-vec + nomic-embed-text, tvåfas-hämtning.
11. **Dedikerad extraktionsmodell** — billig modell för state-extraktion (Multihog-mönster).
12. **Lore-kort med nyckelordsutlösning** — NPCs/platser som bara injiceras när de är relevanta.

### Fas 4 — Avancerat (valfritt)
13. **Typad relationsgraf** för NPCs med käll-ankare + witness tracking.
14. **Commitment-based RNG** — deklarera DC före kast (anti-sycophancy).
15. **Lore Check** — automatisk konsistenskontroll som bakgrundspass.
16. **RPGBench-liknande utvärdering** — mät regelbaserat om harnessen håller state konsistent.

---

## Källor

- **NarrativeEngine-P** — github.com/Sagesheep/NarrativeEngine-P (minnesarkitektur, Divergence Register, NPC-agency)
- **dnd-llm-game** — github.com/tegridydev/dnd-llm-game (dual model, LanceDB RAG, FastAPI)
- **SoloQuest** — dev.to/austin_amento_860aebb9f55 (4-lagers prompt, authoritative state)
- **Multihog D&D Framework** — github.com/MultihogAurelius/SillyTavern-MultihogDnDFramework
- **open-tabletop-gm** — github.com/Bobby-Gray/open-tabletop-gm (relationsgraf)
- **llm_RPG** — github.com/gddickinson/llm_RPG (JSON-protokoll, Legendarium)
- **Recursively Summarizing Enables Long-Term Dialogue Memory** — arXiv 2308.15022
- **Zep: Temporal Knowledge Graph for Agent Memory** — arXiv 2501.13956
- **Graph Memory for LLM Agents (MRAgent)** — arXiv 2606.06036
- **Memory for Autonomous LLM Agents (survey)** — arXiv 2603.07670
- **RPGBench** — arXiv 2502.00595
- **Structured output / Instructor + Pydantic** — techsy.io, collinwilkins.com, letsdatascience.com
- Befintlig intern forskning: `~/llm-dnd-research-report.md`, `llm-app-architecture`-skillen
