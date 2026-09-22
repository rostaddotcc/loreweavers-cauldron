# P1 Mechanics Spec — Morale, Flee/Escape & Status Expiry

**Date:** 2026-09-22 · **Status:** design spec (no code) · **Depends on:** P0 code-rolled enemy attacks (shipped, guardian.py enemy_attacks path), mechanics-p2-s3 (resistances/exhaustion/darkvision)
**Architecture invariants (binding):** chat-first (DM narrates everything, Guardian extracts JSON mechanics, `apply_mechanics` applies server-side); all dice rolled server-side with `secrets` — the LLM narrates results, never invents them (P0 enemy-attack pattern: code rolls d20+bonus vs AC, log row + effect dict, DM narrates); combat bookkeeping lives in `state["world"]["combat"]` with log rows `{round, actor, name, text}`; player dice go through the `[KAST: …]` roll-request contract (`/api/dice`, dice-lock in chat.html); **both application paths must be specified** — Guardian extraction (`guardian.apply_mechanics`) AND DM regex tags (`main._parse_mechanical_tags`) — they diverge today and every new mechanic must declare both.

---

## 0. Research grounding (sources)

| Topic | Source | Take-away for this spec |
|---|---|---|
| B/X (Moldvay) morale | The Alexandrian, "Thinking About Morale" — https://thealexandrian.net/wordpress/2477/roleplaying-games/thinking-about-morale | Morale score 2–12 (6–8 average; 12 = never checks). Check **after a side's first death** and **when half the side is down**. 2d6 > score → retreat/fighting withdrawal; two passed checks → fight to the death. Adjustments capped ±2. Surrender usually follows a failed check **when escape isn't safe**. |
| Retreat behavior (OSR play) | r/osr "Retreating From Combat" — https://www.reddit.com/r/osr/comments/bxtc4j/retreating_from_combat/ ; r/osr "When and how to use morale and reaction roll rules" — https://www.reddit.com/r/osr/comments/gnadji/when_and_how_to_use_morale_and_reaction_roll_rules/ | Failed morale doesn't have to mean a stampede: low = flee, mid = fighting withdrawal/parley, and pursuers' reaction can be roll-driven ("low pursue, high withdraw too"). Good source for the 3-outcome split (fight / flee / surrender). |
| 5e DMG chase rules | Arcane Eye, "D&D Chase Rules" — https://arcaneeye.com/dm-tools-5e/dnd-chase-rules/ | DMG p.252: Dash limited to 3 + CON mod per participant; **no opportunity attacks** during a chase (everyone moves the same direction); chase ends by breaking line of sight (Stealth) or running the quarry down. Known weakness: pure Dash economy degenerates — skill-challenge/clock variants are the community fix (also https://www.hipstersanddragons.com/new-chase-mechanics-5e-dnd/ — 3–4 "gaps" opened to escape). |
| Blades in the Dark engagement/retreat | https://bladesinthedark.com/planning-engagement (SRD) | Position/effect framing (controlled → risky → desperate); **"Giving up on a score"** = clean exit to downtime with cost (heat/entanglements) — a good model for "flee now, consequences later" instead of a dead-end. Clock-style resolution (counted successes) suits one-roll-per-turn chat play. |
| Condition duration semantics | PF2e Conditions — https://2e.aonprd.com/Conditions.aspx ; PF2e Afflictions — https://2e.aonprd.com/Rules.aspx?ID=2389 ; rpg.SE "When/How do conditions end" — https://rpg.stackexchange.com/questions/206948/when-how-do-conditions-end-when-not-specified | Two proven models: (a) 5e — duration in rounds + end-of-turn save to end early; (b) PF2e — value-stages (worsened/improved saves) for poisons/afflictions with max duration. Best practice across both: **explicit end conditions** (save, duration, rest) — never let a condition silently persist. |

---

## 1. Morale

### 1.1 Data model — where morale lives

On each **enemy entry** in `world.combat.enemies[]` (and `allies[]` for symmetry, optional). New fields, flat (JSON-friendly, tolerant of absence):

```
"morale": 8,            # int 2–12, Moldvay scale (default 8 = average). 12 = never checks (fanatic).
"morale_mod": 1,        # derived at creation: morale - 7, clamped -5..+5 (the "+bonus" of the d20 check)
"morale_checked": [],   # list of trigger tokens already fired for this enemy, e.g. ["first_casualty", "half"]
"morale_state": "steady"  # "steady" | "wavering" | "broken" | "routed"
```

- **Creation sites (both paths):** `combat.start_combat` / `add_allies` (combat.py) — accept `morale` in the enemy dict with default 8; `guardian.apply_mechanics` `combat_start` block (guardian.py ~2455) and `main._parse_strid_tag` (`[STRID:namn|hp|ac|atk|dice|MORALE]` — **6th optional pipe-field**, default 8 when absent). Old states without the fields must be tolerated: `e.get("morale", 8)`.
- Duplicate names: identity is the existing `Name#id` key (`_enemy_key`); morale fields are per-entry, so 3× "Archival Sentinel" can check separately. **Fixtures must include duplicate enemy names** (standing project rule).

### 1.2 Break triggers (when code rolls)

Checked server-side inside `apply_mechanics`/`_auto_advance_round` — **the code detects triggers, the LLM never decides that a check happens** (it can *request* one, see 1.4):

| Trigger token | Condition | Scope |
|---|---|---|
| `first_casualty` | first enemy (or ally) in this combat flips `alive=False` (incl. status-damage kills) | each surviving enemy checks once |
| `half_down` | alive enemies ≤ 50% of `max_hp`… i.e. **count-based**: `alive_count * 2 <= initial_count`, or any single enemy at ≤50% HP (use count-based for groups, HP-based for solo) | each surviving enemy not yet checked for this trigger |
| `leader_down` | the enemy with the highest `morale` (or an explicit `leader: true` flag if the DM/Guardian set one) dies/flees | remaining enemies, −2 adjustment |
| `fear_effect` | Guardian `morale_checks` request (e.g. dragon's presence, fireball scare) | named target(s) |

Moldvay doctrine kept: **two passed checks for the same enemy → `morale_state: "steady"`, no further checks ("fights to the death")** until a `leader_down`/`fear_effect` override.

### 1.3 The check — mirror of the P0 enemy-attack arch

New pure function in `combat.py` (server-rolled, testable without state I/O):

```
morale_check(enemy, adjustments: int) -> {"d20": int, "bonus": int, "dc": 10, "total": int,
                                          "outcome": "fight_on"|"waver"|"flee"|"surrender"}
```

- Roll: `d20 + morale_mod + adjustments` vs **DC 10** (flat; Moldvay's flat-scale insight — difficulty varies because *triggers* are toughness-relative, per The Alexandrian). `secrets`-based (`roll_d20`).
- Adjustments (cumulative, clamped −4..+4, per Moldvay's ±2 recommendation extended for leader effects): side losing badly (≤50% vs player at >50%) −2 · leader down −2 · enemy below 25% HP −1 · player visibly wounded (≤50% HP) +1 · `morale == 12` → skip, `fight_on`.
- Outcomes: `total ≥ DC+5` → **fight_on** · `DC ≤ total < DC+5` → **waver** (fighting withdrawal: keeps attacking but seeks exit — narrate, no state change beyond `morale_state: "wavering"`) · `DC−4 ≤ total < DC` → **flee** (leaves combat, 1.5) · `total < DC−4` or flee impossible (cornered, `combat.chase` already active) → **surrender** (drops weapons, `alive=False` + `surrendered: true`; do NOT count as death for XP).
- Every check appends a **log row** `{round, actor: "system", name: <enemy name>, text: "morale check (🎲 d20=N+M=T vs DC 10) — flees!"}` and an effect `{"type": "morale_check", "value": <Name#id>, "d20", "bonus", "total", "dc", "outcome", "trigger"}`.

### 1.4 Chat-first surfacing

1. **Guardian extraction field** (GUARDIAN_POST_SYSTEM + JSON template): `morale_checks: [{"target": "goblin" | "all", "trigger": "first_casualty|half_down|leader_down|fear_effect", "note": "…"}]` — a *request* channel only ("DM narrates the goblins waver → roll for them"); the roll itself is always code-side. Validation (`_sanitize_mechanics`): target non-empty str, trigger ∈ enum (else drop entry — never raise), max 1 entry per (target, trigger) per turn.
2. **`apply_mechanics` handler:** resolve target → matching alive enemies by name (ALL of them if duplicates; "all" = every alive enemy), skip if trigger already in `morale_checked`, roll via `combat.morale_check`, apply outcome (1.5), append log rows.
3. **Effects → chat:** `format_guardian_summary` gets `morale_check` cases (SV/EN): `🏳️ **Goblin** tar ett moralprov … flyr!` — one line per outcome (waver/flee/surrender only; `fight_on` stays silent to avoid noise).
4. **`[COMBAT:]` tag:** new fields ride along automatically (the tag serializes the whole combat dict). Mind the invariants: `_combat_tag` (guardian.py:1285) **copies the dict before mutating** (`tag_data = dict(combat)`) and **caps the log at 20 entries** — do not mutate `combat` inside tag building, and don't add per-check arrays that bypass the log cap. Add `morale_check` to the `_changed` set that decides tag emission (guardian.py ~3746 — NOTE: verified in code 2026-09-22: `enemy_hit`/`enemy_miss`/`enemy_fled`/`status_dmg`/`status_end`/`combat_end` are ALREADY in the set (audit fix 2026-09-06); only NEW P1 effect types like `morale_check` need adding).

### 1.5 Outcome application — enemy disengagement

In `apply_mechanics` (new `morale` section after the death block, before the auto-end check):

- `flee`: set `e["morale_state"] = "routed"`, `e["fled"] = True`, `e["alive"] = False` for combat purposes **but keep `hp`** (they're alive in the fiction); remove from `round_acted` bookkeeping so rounds don't wait on them; log row `"routs and flees!"`; effect `enemy_fled`.
- `surrender`: `e["morale_state"] = "broken"`, `e["surrendered"] = True`, `e["alive"] = False` (same bookkeeping), log row.
- **XP policy:** fled/surrendered enemies grant **no XP** (they weren't defeated); if the player chases them down later in narration, normal death/XP applies then. Quest `gold_reward`-style ransom from a surrendering intelligent enemy = Guardian `currency` field as usual.
- **Combat auto-end extension:** the existing "all enemies defeated" check (guardian.py ~2866 and the earlier block ~1876) becomes `all(not e.get("alive", True))` which already covers fled/surrendered once `alive=False` — update the end-text to distinguish `combat_end.value` ∈ {"all defeated", "enemies fled", "enemies surrendered", "player fled"}. **Double-end guard:** every end path must keep the active-flag gate — `if not (combat and combat.get("active")): return/no-op` at the top, then set `active=False` + `ended_turn` exactly once; the auto-end block already runs only when `combat.get("active")` — every new end path (morale rout, player flee) must go through ONE shared `_end_combat(state, reason, effects)` helper to prevent the known double-end class.

---

## 2. Flee / escape

### 2.1 Player-initiated flee (chat-first)

The player just types "I run / jag flyr" — no new UI button required. Flow:

1. DM narrates the attempt and (when contested) emits a roll request using the **existing `[KAST: …]` contract**: `[KAST: 1d20+3 | FLYKT (SMIDIGHET)]` (label tokens SV/EN: `FLYKT`/`ESCAPE`). The dice-lock/wait-for-player pattern (`references/dice-lock-system.md`: `_pendingRollId` + `_lockChatForDice()`/`_unlockChat()` + "Skriv istället" escape hatch) already handles the pause — declining the roll = the player stays in the fight (DM narrates accordingly).
2. Result returns as `[Resultat: FLYKT … → N (rolls)]` via `_parse_result_tag` (main.py:1008) — extend it with a `FLYKT`/`ESCAPE`/`CHASE` label branch (same shape as the INITIATIV/DÖDSRÄDDNING branches) that records the roll into `combat.chase`.
3. Guardian extraction: `flee_declared: {"target": "player"|"enemy-name"}` so the chase state starts even when the DM forgets the tag (mirrors the `rest`-fallback philosophy — never gate mechanics on one LLM field).

### 2.2 Chase rounds — 3 successes / 3 failures clock

Adopt the skill-challenge/clock variant (Blades position framing + community chase fixes) over the DMG Dash-economy — one roll per chat turn fits the medium, no distance bookkeeping.

State (on the combat dict):

```
"chase": {"active": true, "mode": "player_flee"|"enemy_flee", "successes": 0, "failures": 0,
          "target": 3, "started_round": 2, "quarry": "player"|"Name#id"}
```

- Each chase round (rides `_auto_advance_round`; chase rounds are combat rounds): the fleeing side rolls one check — **player** via `[KAST: …]` (Athletics/Acrobatics/Acrobatics-poor-man's-DEX, label carries skill + FÖRDEL/NACKDEL per the darkvision/cover conventions); **enemy** quarry rolled server-side (`d20 + athletics ≈ attack_bonus + 2` vs the player's opposing `d20 + chosen skill mod`). Success clock tick: winner of the contest gains a success (ties: both gain nothing / one "complication" log row — DM narrates).
- **3 successes** for the quarry → escaped: `_end_combat(state, "player fled" | "enemies fled")` + exit positioning per the Blades "give up on a score" model — the escape is clean but the **consequences land later** (Guardian `world_lore`/`quests` hook: "fled from the toll collectors — they remember"); no XP for the encounter (nothing defeated).
- **3 failures** → caught: chase deactivates, combat continues, and the caught side suffers the 5e DMG "complication" spirit — the pursuer's next attack gains advantage (code: `combat["caught_side"]` flag consumed in the enemy-attack path as a one-shot advantage).
- Cap: 6 chase rounds max (progress clock must resolve); at cap, resolve by remaining successes, ties → the quarry escapes with a cost (half their carried gold dropped — Guardian `currency`).
- Safety rules from DMG kept as prompt guidance: no opportunity attacks while `chase.active` (the enemy-attack code path should skip `enemy_attacks` that are tagged as OA during chase — prompt-level rule is acceptable for P1, hard gate optional), Dash economy out of scope.

### 2.3 Safe preconditions & auto-end rules

- A chase may only start when `combat.get("active")` (flee outside combat = pure narrative travel, no motor).
- All end paths (all defeated / all fled / surrendered / player fled / chase resolved) funnel through `_end_combat` (§1.5) — the **double-end guard**: entry is a no-op when `active` is already False; `ended_turn` set exactly once; `falls!`-cleanup (the existing combat_end zeroing) runs inside the helper.
- Morale-broken enemies don't start a chase against the player; if the PLAYER is fleeing and an enemy breaks morale simultaneously, enemy rout wins (free escape).
- 0-HP player cannot flee (death-save flow owns the turn — `[KAST: 1d20 | DÖDSRÄDDNING]`); document in the DM prompt.

---

## 3. Status expiry (the unwired status/condition motor)

**Current state (verified):** `STATUS_DEFS`/`add_status`/`tick_statuses`/`_tick_all_statuses` exist in combat.py and `_tick_all_statuses` runs on the LLM-signalled `combat_round` path (guardian.py ~2504-2517) — but `status_apply` is in the Guardian contract and sanitized (guardian.py ~2868) yet **consumed by nobody** (`apply_mechanics` never reads it), `add_status` has zero production callers, and the live round advancer `_auto_advance_round` (guardian.py ~2863) does not tick. So statuses can never be created and expiry never has anything to expire. The motor is UNWIRED at exactly two points: **(1) `guardian.apply_mechanics` does not consume `status_apply`** and **(2) the round tick is not invoked from `_auto_advance_round`** (only from the optional LLM `combat_round` signal).

### 3.1 Wiring spec

1. **Creation — `apply_mechanics` new `status_apply` block** (place after the death block, before auto-end): consume `mech["status_apply"]` (`[{name, target, duration, save_dc?}]` — the field already exists in GUARDIAN_POST_SYSTEM:538). Validate: `name` ∈ `STATUS_DEFS` keys (lowercase; `prone|restrain|stun|blind|poison|burn|bleed|frighten|charm`), `target` = "player" or an entity matched via `Name#id`-aware lookup (alive enemy/ally), `duration` int clamped 1–10 (default 2), `save_dc` int 5–25 or null. Apply via `combat.add_status(entity, name, duration)`. Effect `{"type": "status_apply", "value": name, "target": …, "duration": …}` + summary line (`☠️ **Förgiftad** (2 rundor)`).
2. **Creation — DM tag path:** new `[STATUS:namn|target|duration|save_dc]` regex in `_MECH_PATTERNS` + handler in `_parse_mechanical_tags` with identical validation; sets `meta["combat_tag_dirty"]` when the target is in combat. (See §4.)
3. **Expiry — one tick, one owner:** call `combat._tick_all_statuses(state, combat)` from **`_auto_advance_round`** (the only production round advancer) at round transitions, and keep the existing call in the `combat_round` LLM-signal path. The two paths are mutually exclusive per turn (`if mech.get("combat_round"): _reset_round_bookkeeping` else `_auto_advance_round`) — but assert a round-scoped guard `combat["_statuses_ticked_round"]` regardless, since mech payloads can carry both signals across turns. The tick already handles: per-turn DoT damage with resistance (`damage_multiplier`), duration decrement, `status_end` effects, death at 0 HP. Out-of-combat statuses tick on rest only (P1 scope: in-combat rounds; simplest honest rule outside combat is duration decrement on short/long rest).
4. **Save-at-end-of-turn (5e model):** a status with `save_dc` gets a save at the **end of the affected entity's own turn** each round:
   - **Player:** DM emits `[KAST: 1d20+X | <STATUS>SVAR DC N]` (SV label e.g. `GIFTSPAR`/EN `POISON SAVE`) at end of player turn — dice-lock pattern as in §2.1; `_parse_result_tag` gets a generic `SAVE` branch storing the outcome on the status entry → success removes it (effect `status_end`).
   - **Enemies/allies:** rolled server-side inside the tick (`roll_d20 + 0` vs `save_dc`, proficiency-less) — log row with the d20 shown.
5. **Stackable vs refresh:** **refresh, never stack** (5e conditions don't stack with themselves) — this matches the current `add_status` behavior (`duration = max(existing, new)`); re-applying bumps duration only, and `dmg_per_turn` is NOT re-added. PF2e-style value-stages (poison 1→2→3) are explicitly **out of scope**; note in the DM prompt that repeated poison extends, not worsens. A second application with a *higher* `save_dc` raises the DC to the new value (worst-case rule).
6. **Interactions already built (keep):** `has_disadvantage` in the enemy-attack path (guardian.py ~2769) starts working the moment statuses can exist; resistances/exhaustion/darkvision from mechanics-p2-s3 stay untouched.

---

## 4. Tag contract additions — both application paths

Every mechanic below exists in **two paths that must stay semantically identical** (they have diverged before: level-up, currency, quest rewards). Where they can't be identical, the Guardian path is the reference implementation and the tag path must call shared helpers.

### 4.1 Guardian extraction (GUARDIAN_POST_SYSTEM + `_sanitize_mechanics` + `apply_mechanics`)

| Field | Shape | Validation (`_sanitize_mechanics`) | Consumed in `apply_mechanics` |
|---|---|---|---|
| `morale_checks` | `[{target: str, trigger: enum, note: str}]` | drop entries with empty target or trigger ∉ {first_casualty, half_down, leader_down, fear_effect}; `_safe_int`-only numbers; max 4/turn | new morale section (§1.4) — server rolls |
| `flee_declared` | `{"target": "player"\|str}` \| null | dict-or-null (same pattern as `combat_start`); unknown target → log + ignore | starts `combat.chase` (§2.1) |
| `chase_progress` | `[{outcome: "escape"\|"caught"\|"stalemate"}]` | enum check; max 1/turn | ticks the chase clock (enemy-side rolls stay server-side) |
| `status_apply` | `[{name, target, duration, save_dc?}]` (exists — now consumed) | name ∈ STATUS_DEFS enum; duration clamp 1–10; save_dc clamp 5–25 | `add_status` (§3.1) |
| `status_save` | `[{target, name, success: bool}]` | only for the PLAYER's saves the DM already resolved via `[Resultat:]`; drop if no matching status | remove/keep status (dedup vs `[Resultat:]` — see 4.3) |

### 4.2 DM regex tags (`main._MECH_PATTERNS` + `_parse_mechanical_tags`) — they DIVERGE, spec both

| Tag | Regex | Handler behavior (mirrors Guardian path) |
|---|---|---|
| `[MORALE:target\|trigger]` | `\[MORALE:([^|\]]+)\|([^\]]+)\]` | same validation as `morale_checks`; rolls via `combat.morale_check`; sets `meta["combat_tag_dirty"]` |
| `[FLYKT:target]` | `\[FLYKT:([^\]]+)\]` | starts chase (`player` → `mode: "player_flee"`; enemy name → `enemy_flee` + immediate contest roll server-side) |
| `[STATUS:namn\|target\|duration(\|save_dc)]` | `\[STATUS:([^|\]]+)\|([^|\]]+)\|(\d+)(?:\|(\d+))?\]` | identical validation + `add_status`; `combat_tag_dirty` when target in combat |
| `[KAST: …]` / `[Resultat: …]` | existing | new label branches: `FLYKT/ESCAPE/CHASE` → chase tick; `*SPAR/* SAVE` → status save outcome (§2.1, §3.1) — in `_parse_result_tag` only |

Rules that apply to **both** paths:

- **Enum + clamp, never raise:** malformed input drops the entry with a `logger.warning` (the raw `int()` crash class from the Sept audit — all numeric fields via `_safe_int`).
- **Identity:** enemy targets resolve through the `Name#id` rotation (`_enemy_key` semantics); a bare name matching multiple alive enemies affects **all** of them for morale/status (documented choice; per-instance targeting is P2 via an explicit `Name#2` suffix in tags).
- **Tags strip from narration** in both paths (same cleanup regex pattern).

### 4.3 Dedup pitfalls

`skip_effects` / P0-dedup today covers **only `skada`, `hela`, `xp`, `guld`** (exact `(type, str(value))` match from `meta["last_effects"]`). New effects need explicit keys or they double-apply when both paths fire in one turn (e.g. DM writes `[STATUS:poison|goblin|2]` AND Guardian re-extracts it — prompt rule 9 "ANTI-DUBBEL" is LLM-dependent and known to leak):

- `status_apply`: dedup key `("status_apply", f"{name}:{target}")` appended to the effects list so `meta["last_effects"]` carries it; `add_status`'s refresh semantics (§3.5) make double-application idempotent anyway — **belt and suspenders**.
- `morale_check`: server-side idempotence via `morale_checked` (a trigger fires once per enemy) — no skip_effects needed; Guardian re-requests are natural no-ops.
- `flee_declared`/chase: guard on `combat.chase.get("active")` — second declaration is a no-op (double-start guard mirrors the double-end guard).
- Player saves (`[Resultat:]` vs Guardian `status_save`): the `[Resultat:]` path runs **pre-Guardian** (synchronous in chat) and adds `("status_save", f"{name}:{target}")` to the turn's effects; Guardian's `status_save` consumption checks `_skip_keys` first — same pattern as SKADA.

---

## 5. Test plan

**Runner:** the project venv — `cd ~/dnd-llm/backend && ../.venv/bin/pytest tests/…` (never ambient python; `references/backend-test-env-2026-08.md`).

**Fixtures (conftest pitfalls):**
- `turn_ledgers_dir` is autouse in `tests/conftest.py` — keep tests inside `backend/tests/` so ledger writes hit tmp; **seed users directly** (write `users.json` entries / call the store), **never `/api/register`** (`_REGISTER_TIMES` is process-global → 429 leaks across the suite).
- Combat fixtures **must include duplicate enemy names** (e.g. 3× "Archival Sentinel") to exercise `Name#id` keys — the standing regression from 2026-09-13.
- Old-state tolerance: one fixture per mechanic with an enemy entry **missing** the new fields (morale/statuses absent → defaults, no KeyError).

**New test files (LLM-free — call `apply_mechanics`/`combat.*` directly, pass literal `mech` dicts):**

1. `tests/test_p1_morale.py`
   - `morale_check` pure outcomes across the d20 range (monkeypatch `combat.roll_d20` for determinism): fight_on / waver / flee / surrender bands + adjustments + morale 12 skip.
   - Trigger detection: kill one of 3× duplicate-named enemies → exactly the 2 survivors each check once (`morale_checked` idempotence on repeat calls).
   - Flee application: `fled=True`, removed from round bookkeeping, log row `{round, actor, name, text}`, no XP effect.
   - `_end_combat` double-end guard: calling twice → one `combat_end` effect, `ended_turn` stable.
   - `morale_checks` validation: bad trigger dropped, no exception.
2. `tests/test_p1_flee_chase.py`
   - Chase clock: 3 successes → `combat_end` "player fled"; 3 failures → `caught_side` set, chase inactive; 6-round cap → gold-drop stalemate.
   - `[Resultat: FLYKT …]` parsing branch (main `_parse_result_tag`) with advantage rolls-string forms (`7+2`, `15, 11+4`, `2d6+5: [4, 5]` — the three rolls-sträng forms).
   - Double-start guard on `flee_declared` + tag path `[FLYKT:]` equivalence (same final state via both paths).
3. `tests/test_p1_status_expiry.py`
   - `status_apply` consumption (the un-wire regression test): mech with `status_apply` → `entity["statuses"]` non-empty (today this must fail → drives the fix).
   - Refresh-not-stack: apply poison twice → one entry, duration = max, single `dmg_per_turn`.
   - Tick: `_auto_advance_round` transition ticks DoT (respecting `damage_multiplier`), decrements duration, emits `status_end`, kills at 0 HP.
   - Save expiry: enemy save monkeypatched → status removed; player `[Resultat: …SPAR]` branch → status removed; both-path dedup key respected.
   - Tag/Guardian parity: `[STATUS:burn|goblin|3]` vs `status_apply` produce identical state snapshots.

**Smoke recipe (also for the implementer):** build a state dict in a tmp fixture, run `apply_mechanics(state, mech)` with hand-written `mech` JSON for each scenario — no network, no LLM. Full suite must stay green except the known billing/tiers/visits fixture-interference failures.

---

## 6. Effort, risk & the P1a/P1b split

Each half ships independently behind its own tests; P1a touches combat.py + guardian.py morale sections; P1b touches chase + status wiring. No shared blocking dependency (P1b's `_end_combat` helper is trivially back-ported if P1a ships first).

| Piece | Split | Est. effort | Risk | Mitigation |
|---|---|---|---|---|
| Morale fields + `morale_check` + triggers | **P1a** | ~2h | LOW — pure functions, additive fields | defaults for old states; duplicate-name fixtures |
| Morale outcomes → routing/combat_end + `_end_combat` helper | **P1a** | ~2h | MED — touches auto-end paths (double-end class) | single `_end_combat`, double-call test |
| Guardian field + `[MORALE:]` tag + summary/`[COMBAT:]` surfacing (add `morale_check` to the `_changed` set — the `enemy_hit/miss` gap is ALREADY fixed, audit 2026-09-06, verified 2026-09-22) | **P1a** | ~2h | MED — tag emission is subtle (audit bug 4) | repro-style tests on tag emission per effect type |
| Player flee + `[KAST: FLYKT]` + chase clock | **P1b** | ~2.5h | MED — dice-lock interplay, `_parse_result_tag` label branches | reuse dice-lock contract untouched; rolls-sträng tests |
| `status_apply` consumption + `[STATUS:]` tag | **P1b** | ~1.5h | LOW — dormant code becomes live | regression test = the un-wire itself |
| Tick wiring in `_auto_advance_round` + end-of-turn saves | **P1b** | ~2h | MED — tick timing (round boundary) + double-tick risk | round-scoped `_statuses_ticked_round` guard |
| Docs: mechanics.html rulebook entries + DM prompt sections | both | ~1h ea | LOW — but mandatory (spell-slot lesson: invisible mechanics = trust bugs) | mechanics.html honesty check vs code (audit §8) |

**Total ≈ 7h P1a + 7.5h P1b** (≈ 2 agent-sessions). Top risks overall: (1) double-end/double-tick guards, (2) tag-vs-Guardian divergence, (3) prompt contract drift — the DM prompt (models.py `DM_COMBAT_PROMPT`) must stop inventing outcomes for morale/chase rolls the way it does for enemy attacks (audit §6: narration/state divergence) — add the same "describe the attempt, never the result" instruction.

---

## 7. P2 outlook (brief)

**Gold utility.** Gold currently sinks into a weak economy (Sept audit: "guldets nytta är svag"). Tie buyable services to the turn economy so spending gold buys *pacing*, not power: e.g. a healer at the temple restores N HP or removes exhaustion for gp (vs. spending a short rest = turns), a sage identifies/copy-protects a scroll, an inn's "good meal" grants a one-shot `roll_grant` (1d6 inspiration-style die on the next check), a ferry/caravan skips travel turns. All as Guardian `currency` (negative, via `apply_currency`'s refuse-on-overdraft) + `roll_grants`/`rest` effects — no new motor needed beyond a small `services` prompt section and a `[TJÄNST:]`-style tag or Guardian field. Price anchors: quest `gold_reward` default 0–50 with `xp_reward` 100 ⇒ price services in the 5–30 gp band so a quest payout funds 1–3 services.

**Level-gated locations.** With `xp_to_next = 100 × level` and quest `xp_reward` default 100, level-ups come ≈1/level early and stretch later — a natural content gate: locations carry `recommended_level` (int, on the full location objects from Aug 2026) and the DM prompt gets a guardrail "the Ashen Depths are deadly for level < 4 — gate travel with fiction (a collapsed pass, a wary guard), never a hard UI lock". Soft-gating keeps the chat-first promise (the player can try and regret it — morale/flee mechanics then provide the exit); a hard gate would need map/UI changes and fights the open-world tone. Quests can carry the same field so the DM pitches level-appropriate leads. Consistency check: level 2 at 100 XP ⇒ one default quest ≈ one level early on — gate tiers at levels 2/4/6/8 mapping to starter-region → frontier → deep dungeon → endgame, i.e. roughly 100/300/600/1000 XP-earned milestones.
