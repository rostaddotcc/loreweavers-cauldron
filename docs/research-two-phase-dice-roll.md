# Two-Phase Dice-Roll Research: "Roll First, Narrate After"
## Findings from Open-Source AI-DM Projects, VTT Patterns & LLM Architectures
### 2026-08-02 · for ~/dnd-llm/ (FastAPI + vanilla-JS)

---

## 1. The Core Problem

When a player says "I attack the goblin," the DM LLM narrates the full outcome
(hit/miss/damage) BEFORE emitting a `[KAST:]` tag. The player never gets to roll.
Regex-trimming the narration is fragile because the LLM weaves outcome into prose
("Ditt svärd träffar! 8 skada.") rather than cleanly separating setup from result.

This is a **universal problem** in AI-DM design. Every project we studied has
converged on the same insight: **you cannot trust an LLM to self-gate**. The
solution is always architectural, not promptological.

---

## 2. Four Patterns Found in the Wild

### Pattern A: Tool-Calling Gate (strongest enforcement)
**Used by:** Project Infinity (electronistu, 41★), yowza-AI/ai-dungeon-master-analysis

The LLM has **no ability to generate numbers**. All mechanics go through tool calls
to a deterministic engine. The LLM literally cannot narrate an outcome because it
doesn't know the result until the tool returns it.

**Project Infinity's "Phased Resolution Protocol" (v16):**
```
turn_cycle:
  mechanical_resolution_phase:
    step 1: TOOL_BATCH — emit ALL tool calls, NO narrative
    step 2: AUDIT_LOOP — re-check checklist, emit more tool calls if needed
    step 3: SYNC_TOKEN — emit {{_NEED_AN_OTHER_PROMPT}}, NO narrative
    step 4: RESUME — wait for {{_CONTINUE_EXECUTION}}
  narrative_phase:
    step 5: NARRATIVE — prose + mechanics block from tool results
```

Key constraints from their system prompt:
- "Never combine tool calls with narrative text."
- "Never provide interstitial narration between tool batches."
- "Every perform_check, resolve_attack, resolve_magic call MUST have a
  corresponding line in the narrative using narrative_format."

**OMISSION_RECOVERY state:** If the AI realizes mid-narrative it forgot a tool
call, it STOPS narrative mid-sentence, emits the tool call + sync token, waits,
then produces a COMPLETE narrative including all results. This is the most
sophisticated failure-recovery we found.

**yowza-AI architecture:**
```
Player Action (free form)
  → DM Agent (LLM + tools): parse intent, decide which mechanic
  → Rules Engine (deterministic): attack rolls, damage, saves, conditions
  → Tool Results (actual numbers)
  → DM Agent (narration): incorporates real outcomes
```
"The LLM never invents mechanics. It decides which tool to call, then narrates
the actual result." NPC turns use deterministic heuristics (no LLM per turn),
with optional LLM flavor added AFTER mechanics are locked.

**Applicability to dnd-llm:** Requires tool-calling support from the LLM provider.
Qwen/StepFun/DeepSeek all support OpenAI-compatible tool calling, so this is
technically feasible. However, it's the most invasive refactor — the entire DM
prompt and chat endpoint would need restructuring.

---

### Pattern B: Pre-DM Referee + PendingRoll (best fit for dnd-llm)
**Used by:** tegridydev/dnd-llm-game (FastAPI + React, closest architecture match)

A **separate small LLM** (the "rules referee") decides BEFORE the DM narrates
whether a roll is needed. The flow:

```
1. Player sends action
2. Utility model (small, fast) → JSON:
   {
     "requires_roll": true,
     "narration": "short setup text before the roll",
     "formula": "1d20+2",
     "ability": "Strength",
     "skill": "Athletics",
     "dc": 13,
     "reason": "why the roll is required"
   }
3. If requires_roll:
   a. Create PendingRoll in DB
   b. Frontend shows: narration + dice button
   c. Player clicks → roll_formula() → DiceRoll stored
   d. SECOND DM call with roll result injected:
      "Dice result: 1d20+2 = 17 vs DC 13 → success.
       Resolve the action as the Dungeon Master.
       Reflect the dice result directly."
4. If no roll needed:
   a. Single DM call as normal
```

**Critical design detail:** The DM NEVER sees the raw player action without
either (a) a pending roll blocking it, or (b) explicit "no roll needed" context.
The two-call split means the DM literally cannot narrate the outcome in the
first call — it doesn't have the result.

**Fallback:** Keyword-based `_fallback_roll_decision()` if the utility model
fails (sneak→Stealth DC 13, attack→Attack DC 12, etc.). This is similar to
rostad's existing `ACTION_KEYWORDS` regex.

**Applicability to dnd-llm:** This maps almost 1:1 onto the existing Guardian
pre-DM (`guardian_check_roll`). The Guardian already runs before the DM and
returns `{notation, label, skill}`. The missing piece is: when Guardian says
"roll needed," the system still calls the DM and hopes it emits `[KAST:]`
correctly. Instead, it should SKIP the full DM call, show a lead-in, wait for
the roll, THEN call the DM with the result.

---

### Pattern C: Prompt Enforcement + Tag Parsing (rostad's current approach)
**Used by:** dnd-llm (current), Dungeo_ai, samvoisin/ai-dungeon-master

The DM prompt says "write [KAST:] BEFORE narrating outcome." Regex parses tags.
Safety nets catch failures.

**rostad's current safety nets (3 layers):**
1. `PROSE_ROLL_PATTERN` — detects "rulla tärningen" in prose, auto-spawns 1d20
2. Guardian pre-DM fallback — if DM forgot [KAST:] but Guardian recommended one
3. `ACTION_KEYWORDS` — detects attack/sneak/climb verbs (currently unused for
   auto-spawning, but the regex exists)

**Why this pattern fails:** LLMs are autoregressive — once they start writing
"Ditt svärd träffar goblinen i bröstet...", the outcome is already committed to
the token stream. No amount of prompt instruction can reliably prevent this.
The prompt says "ABSOLUT REGL (KRITISKT)" and the model still violates it ~10-20%
of the time (worse with smaller models).

**This pattern is necessary but not sufficient.** It works as a safety net
under Pattern B, but cannot be the primary enforcement mechanism.

---

### Pattern D: Structured JSON Output (eliminates regex entirely)
**Used by:** tegridydev (utility model), Project Infinity (tool call results),
claude-dnd-skill (script-first)

Instead of free-text with embedded tags, force the LLM to return structured JSON.
For the DM response:

```json
{
  "lead_in": "Du lyfter svärdet och hugger mot goblinen!",
  "roll_request": {
    "notation": "1d20+5",
    "label": "ATTACK mot AC 13",
    "dc": 13,
    "advantage": null
  },
  "outcome_narration": null,
  "npcs": [{"name": "Goblin", "role": "Fiende", "relation": "fiende"}]
}
```

The `outcome_narration` field is **explicitly null** on the first call. The
prompt says: "Leave outcome_narration as null. You will narrate the outcome
AFTER receiving the roll result in a follow-up message."

After the roll, a second call:
```json
{
  "lead_in": null,
  "roll_request": null,
  "outcome_narration": "Svärdet biter djupt in i goblinens bröst..."
}
```

**Advantages over regex:**
- No fragile tag parsing — JSON is validated by the LLM's structured output mode
- The null field is a hard contract — the LLM can't "accidentally" fill it
- Pydantic validation on the backend catches malformed responses
- Works with OpenAI-compatible `response_format: {type: "json_object"}`

**Applicability:** Qwen and DeepSeek support JSON mode. StepFun may need
verification. This could replace `_parse_roll_requests`, `_parse_npcs`, and
`_parse_mechanical_tags` with a single Pydantic model.

---

## 3. The D&D 5e API / SRD Approach

**dnd5eapi.co** (5e-bits/5e-srd-api) is a pure **data API** — monster stat
blocks, spells, conditions, equipment. It does NOT resolve combat. Example:
`GET /api/monsters/goblin` returns `{armor_class: [{value: 15}], hit_points: 7,
actions: [{name: "Scimitar", attack_bonus: 4, damage: [{damage_dice: "1d6+2"}]}]}`.

**claude-dnd-skill** bundles a 1.2MB `dnd5e_srd.json` locally — the full SRD
as a lookup database. Their `lookup.py` script queries it for monster stats,
spell effects, conditions.

**Relevance to dnd-llm:** The Guardian currently guesses AC/HP from the DM's
narration. If the DM says "en goblin", the system could look up the actual SRD
goblin (AC 15, HP 7, scimitar +4) and use those numbers for roll requests and
combat tracking. This makes the `[KAST: 1d20+5 | ATTACK mot AC 13]` tag
accurate instead of LLM-hallucinated.

**Concrete integration:** Add a `srd_lookup(monster_name)` function that queries
a local SRD JSON (or the API). When Guardian pre-DM detects combat, inject the
monster's real AC/HP into the roll request. When the DM narrates "en goblin",
Guardian post-DM can auto-populate combat state with SRD-accurate numbers.

---

## 4. Concrete Recommendations for dnd-llm

### Priority 1: Guardian-Gated Two-Call Architecture (Pattern B adapted)
**Effort: Medium. Impact: Eliminates the problem at the root.**

Modify the chat endpoint flow in `main.py`:

```python
# CURRENT FLOW (broken):
# 1. Guardian pre-DM → guardian_roll (maybe)
# 2. DM call → reply (may narrate outcome before [KAST:])
# 3. Parse [KAST:] from reply
# 4. If no [KAST:] but guardian_roll → fallback spawn
# 5. Send reply + roll_requests to frontend

# NEW FLOW:
# 1. Guardian pre-DM → guardian_roll
# 2. IF guardian_roll:
#    a. Generate lead-in (tiny LLM call or template)
#       "The player attacks the goblin. Write 1-2 sentences of
#        tension/setup. Do NOT describe the outcome. STOP."
#    b. Return {lead_in, roll_request} to frontend
#    c. Frontend shows lead-in + dice button
#    d. Player rolls → POST /api/chat with "[Resultat: ...]"
#    e. FULL DM call with roll result injected:
#       "Roll result: 17 vs AC 13 → HIT. Narrate the outcome."
# 3. IF no guardian_roll:
#    a. Normal DM call (no roll expected)
```

**Why this works:** The DM never has the roll result when it writes the lead-in.
It physically cannot narrate "you hit" because it doesn't know if the player
rolled a 2 or a 20. The outcome narration happens in a separate call where
the result is known.

**Lead-in generation options (pick one):**
- **Template-based** (zero LLM cost): "Du gör dig redo att attackera goblinen..."
  with variation by action type (attack/sneak/climb/persuade)
- **Tiny LLM call** (100-200 tokens, cheap model): "Write 1-2 sentences of
  setup for this action. Do NOT describe the outcome." Use the smallest
  available model.
- **Reuse Guardian's narration field**: Extend `guardian_check_roll` to return
  a `lead_in` field alongside `{notation, label, skill}`. The Guardian already
  understands the situation — it can write the setup text.

**Frontend changes:**
- New message type: `{type: "roll_pending", lead_in: "...", roll: {notation, label}}`
- Existing dice button UI already handles this — just wire the lead-in text
  as a preceding chat bubble
- After roll: existing `[Resultat:]` flow already sends the result back

### Priority 2: Structured JSON for DM Output (Pattern D)
**Effort: Medium. Impact: Eliminates regex parsing, enables validation.**

Replace tag-based parsing with a Pydantic response model:

```python
class DMResponse(BaseModel):
    narration: str                    # The prose the player sees
    roll_request: RollRequest | None  # If a roll is needed
    npcs: list[NPCTag] = []           # New NPCs
    # outcome_narration is NOT a field — it's a separate call

class RollRequest(BaseModel):
    notation: str    # "1d20+5"
    label: str       # "ATTACK mot AC 13"
    dc: int | None   # 13
    advantage: bool | None  # True/False/None
```

Use `response_format={"type": "json_object"}` in the LLM call. Validate with
Pydantic. On validation failure: one retry with the error message, then fall
back to the current tag-parsing path.

**Migration path:** Keep `_parse_roll_requests` and `_parse_npcs` as fallbacks.
Add the JSON path alongside. A/B test. Remove regex when JSON reliability is
proven.

### Priority 3: SRD Data Integration
**Effort: Low-Medium. Impact: Accurate AC/HP/attack bonuses.**

- Download `dnd5e_srd.json` (1.2MB, from claude-dnd-skill or 5e-bits)
- Add `srd_lookup(name) → {ac, hp, attacks, cr, xp}` to `backend/`
- When Guardian pre-DM detects "attack" + a known monster name, inject real AC
- When `[STRID:]` tag fires, auto-populate enemy stats from SRD
- When DM narrates "en goblin", Guardian post-DM can cross-reference

### Priority 4: Prompt Hardening (incremental, lowest effort)
**Effort: Low. Impact: Reduces failure rate but doesn't eliminate it.**

If keeping the current single-call approach as a fallback:
1. Move "KAST FÖRE UTFALL" to the **very first line** of the system prompt
   (position bias — LLMs attend most to the beginning)
2. Add a **stop instruction**: "After writing [KAST:], write NOTHING more.
   Not one more sentence. The next text you write will be in a NEW message
   after receiving the roll result."
3. Add **more negative examples** with the exact failure patterns seen in play
4. Post-processing: if `[KAST:]` found, check text BEFORE it for outcome words
   ("träffar", "missar", "lyckas", "misslyckas", "skada", "dör") and truncate
   to the sentence before the first outcome word

### Priority 5: Deprecate the Tag Pipeline
**Effort: Medium. Impact: Reduces complexity, removes dead code.**

Per the mechanical-flow audit, the tag pipeline is "nearly dead" — the DM prompt
says "you do NOT need mechanical tags." The KAST tag is the only alive tag.
Once Priority 1 (Guardian-gated two-call) is in place, the KAST tag becomes
unnecessary — the Guardian pre-DM handles roll detection, and the roll result
comes back via `[Resultat:]`. The entire `_parse_mechanical_tags` +
`validate_dm_response` + repair loop can be removed.

---

## 5. Architecture Comparison Table

| Aspect | Current (dnd-llm) | Tegridydev | Project Infinity | Recommended |
|--------|-------------------|------------|------------------|-------------|
| Roll detection | Guardian pre-DM + prompt | Utility model (JSON) | Tool calling | Guardian pre-DM (keep) |
| Roll enforcement | Prompt instruction + regex | PendingRoll DB gate | Tool-call gate (LLM can't generate numbers) | Guardian-gated two-call |
| Narration split | Single call, hope for the best | Two calls (setup → resolution) | Two phases (mechanical → narrative) | Two calls (lead-in → outcome) |
| Output parsing | Regex tags | JSON (utility model) | Tool call results | Pydantic JSON + tag fallback |
| Failure recovery | Prose-roll pattern + Guardian fallback | Keyword fallback | OMISSION_RECOVERY state | Guardian fallback + Pydantic retry |
| SRD data | None (LLM guesses) | None | spells.yml + SRD 5.1 | srd_lookup() local JSON |

---

## 6. Sources

| Project | URL | Key Insight |
|---------|-----|-------------|
| Project Infinity | github.com/electronistu/Project_Infinity | Phased Resolution Protocol, sync tokens, OMISSION_RECOVERY |
| yowza-AI DM Analysis | github.com/yowza-AI/ai-dungeon-master-analysis | "Tools handle mechanics, LLM handles narration" |
| tegridydev/dnd-llm-game | github.com/tegridydev/dnd-llm-game | PendingRoll pattern, utility-model referee, two-call resolution |
| claude-dnd-skill | github.com/neuralinitiative/claude-dnd-skill | "Call for the roll and STOP", script-first, roll_mode, SRD JSON |
| D&D 5e API | dnd5eapi.co / github.com/5e-bits/5e-srd-api | SRD data source for accurate monster stats |
| dnd-llm (local) | ~/dnd-llm/ | Current architecture, Guardian pre-DM, KAST tags, audit findings |
