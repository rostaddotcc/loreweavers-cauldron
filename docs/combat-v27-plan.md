# Combat v27 — Split View + Dice Transparency + Flow Fixes

## Diagnosis (marielle campaign, 2026-08-02)

### Bug 1: DM narrates outcome BEFORE dice roll
- Turn 5: player attacks → DM narrates full outcome, no [KAST:] tag
- Root: DM prompt says "use [KAST:]" but model ignores it when the action is "obvious"
- Fix: DM prompt must EMIT [KAST:] BEFORE any narration of an uncertain outcome. Split the DM response into two phases: (a) lead-in + [KAST:] tag, (b) after player rolls → narration of result.

### Bug 2: Initiative after attack
- Turn 5: attack narrated, Turn 6: initiative rolled
- Root: [STRID:] tag triggers combat_start in Guardian, but initiative [KAST:] is in the DM prompt's "combat start" block — the DM skipped it
- Fix: Guardian's combat_start should require an initiative roll_grant BEFORE any attack. DM prompt: "När strid bryter ut, begär ALWAYS [KAST:1d20+DEX|INITIATIV] först — innan någon attackerar."

### Bug 3: Healing potion without dice
- Turn 11: Guardian set HP to max (9/9) without rolling 2d4+2
- Root: Guardian's `healing` field applies a fixed amount from DM narration, not a dice roll. No roll_grant generated for potion healing.
- Fix: Guardian prompt — when player consumes a healing item, generate `roll_grants` with notation "2d4+2" (or item-specific). DM prompt — "När spelaren dricker en läkedryck, begär [KAST: 2d4+2|LÄKNING] — spelaren rullar själv."

### Bug 4: Stuck in round 1
- `acted: false` for both combatants, `current_index: 0` after 12 turns
- Root: `_chat_locked` doesn't call `end_turn`/`advance_turn` in chat-first mode. The Guardian's `combat_round` field updates `round` but `acted` flags and `current_index` never advance.
- Fix: In chat-first combat, the "turn" is the player's action + DM response. After the Guardian post-DM runs, if combat is active, mark `acted=true` for the current combatant and advance `current_index`. When all have acted, increment `round` and reset `acted` flags.

### Bug 5: Enemy dice not visible
- Enemy dice are in `combat.log[].text` (e.g., "träffar dig — 5 skada (fire) (🎲 d20=11+3=14 · 1d6+1: [4]=5)")
- But `renderRoundSummary` renders them as plain `cl-row` text — buried in a summary box
- Fix: Extract dice notation from combat log entries and render as inline dice badges with distinct colors (blood-red for enemy, gold for player).

### Bug 6: No split view
- Everything in one chat column
- Fix: When `combat.active === true`, split the chat area into two panes:
  - Left (60%): DM narration (story, dialogue, [KAST:] prompts)
  - Right (40%): Battle log (enemy cards, HP bars, dice rolls, round summaries, status bar)
  - On mobile: stack vertically, battle log as a collapsible drawer

## Implementation Plan

### Task A: Backend — Combat flow fixes (main.py + guardian.py + models.py)
1. DM prompt (models.py): enforce [KAST:] BEFORE narration of uncertain outcomes
2. DM prompt: initiative [KAST:] required at combat start, before any attack
3. DM prompt: healing items require [KAST: Nd+M | LÄKNING]
4. Guardian prompt (guardian.py): generate roll_grants for healing potions
5. Guardian apply_mechanics: fix turn rotation — mark acted, advance current_index, increment round
6. Guardian combat_start: don't replace existing combat (merge enemies)

### Task B: Frontend — Split view + enemy dice (chat.html + snes.css)
1. Dual-pane layout when combat.active (CSS grid: 60/40 desktop, stacked mobile)
2. Route combat elements (enemy cards, HP changes, round summaries, dice) to battle-log pane
3. Keep DM narration in main chat pane
4. Enemy dice badges with blood-red color, player dice with gold
5. Battle-log pane: scrollable, auto-updated, collapsible on mobile
6. Status bar stays sticky above input (already exists, just restyle for split)

### Task C: Backend — DM prompt restructure for two-phase combat responses
1. Phase 1 (pre-roll): DM writes brief lead-in + [KAST:] tag, NO outcome narration
2. Phase 2 (post-roll): DM narrates the full outcome based on [Resultat:] input
3. This requires the chat endpoint to detect when a [KAST:] is pending and NOT call the DM for a full response — just the lead-in + tag
4. When [Resultat:] arrives, the DM gets the roll result and narrates the outcome
