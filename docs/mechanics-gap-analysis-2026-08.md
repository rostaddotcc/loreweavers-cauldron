# Mechanics Gap Analysis — The Lore Weaver's Cauldron (2026-08-08)

Jämförelse: vad spelet har idag vs. D&D 5e:s kärnmekanik. Grundad i kodgranskning
(guardian.py apply_mechanics, main.py taggar, models.py prompts, combat.py,
state-schema.json, chat.html tärningsceremoni) + skill-referenserna.

## Implementerat — engine-förstärkt (hård kod)

| Mekanik | Var | Kommentar |
|---|---|---|
| Tärningar + ceremoni | chat.html `rollDice` + [KAST:]/[Resultat:] | Adv/dis (2d20 best/worst) via label, nat 20/1, DC-medvetna resultat |
| Fiende-attacker | guardian.py `enemy_attacks` | KODEN rullar d20+attack_bonus mot AC + skada — LLM fyller inte i |
| Spelar-attacker/skada | [SKADA:], `player_attacks` | HP-dedup (double-damage-dedup) |
| Stridsflöde | `combat_start/round/initiative_entries/combat_end` + [STRID:] | turn_order byggs; allierade via [ALLIERAD:] |
| Flykt | [KAST: 1d20+DEX \| FLEE] | Misslyckad flykt → opportunity attack (prompt) |
| XP + level-up | `_XP_THRESHOLDS` (5e-tabell) | Auto level-up + HP-ökning |
| Quest | `quests_new/completed/failed` | Rewards (XP+guld), dedup, ID-match |
| Inventory | `items_add/remove` + ITEM_SCHEMA | Equip-regel (en per typ), vikt, lore |
| Valuta | 4 valörer (pp/gp/sp/cp) | |
| Vila | `rest` + `_ensure_hit_dice` | Short rest = 1 hit die; long rest = full HP + slots + hit dice |
| Spell slots | `spell_slots {current,max}` | Restore vid long rest; **spending = LLM-styrt** (se gap 2) |
| Death saves | main.py [Resultat:]-handler | 3 succé/fail, 5e-regler |
| Statusar (conditions) | combat.py STATUS-tabell | poison/burn/bleed/stun/frighten/prone/charm/blind — men tick-körs ej (gap 5) |
| Platser/tid/väder | world-state + locations.py | travel days beräknas |
| NPC-relationer, @NPC-chatt, allierade | npc_relations, [ALLIERAD:] | |
| Minne | FactRegister + RAG | 8 fakta + 4 chunks per tur |

## Implementerat — prompt-drivet (LLM avgör, ingen motor)

- Ability checks + saving throws: Guardian PRE rekommenderar kast (`{notation, label, skill, DC}`) + DM sätter DC per skala (8–25). Ingen skill-proficiency.
- Advantage/disadvantage: prompt-instruerat, UI stödjer 2d20.
- Concentration (DC 10 CON-save vid träff).
- Action economy (1 action + bonus + reaction) — DM påminner.
- Random encounters (20 % vid vila; var 4–5:e resa).
- Rest-vakt, Rule of Cool, anti-hallucination.
- Balance guardrails (fiende-HP/AC per nivå, max 3 fiender < lvl 3).

## GAP — saknas eller kosmetiskt

### P0 — bryter 5e-regler eller lovar mer än det levererar

1. **Skills / proficiency finns inte.** Inga skills på karaktärsbladet (Athletics,
   Perception, Stealth, Arcana…), ingen skill-proficiency, och proficiency-bonusen
   (`character.proficiency`) läggs aldrig till i kast — den visas bara i
   Guardian-sammanfattningen. Alla kast = d20 + ability-mod. För ett spel som
   säger "riktiga D&D 5e-regler" är det den största luckan.
   **Fix:** (a) skills-lista i state + char-gen prompt, (b) Guardian PRE bygger
   notation med prof-bonus för kända skills, (c) UI-sektion på character.html.

2. **Spell slot spending är ren LLM-narration.** Slots syns på bladet och
   återställs vid long rest, men ingenting decrementerar `current` när spelaren
   kastar. Fram till 2026-08-08 fanns `/api/combat/cast` (hård check+decrement)
   men frontend anropade den aldrig — redan kosmetiskt. Dead-code-passet tog
   bort den sista hårda vägen.
   **Fix:** nytt Guardian-fält `spell_slots_spend [{name, level}]` i
   apply_mechanics (check: current ≥ level, decrementera, logga) + prompt-sektion.

3. **mechanics.html §5 ljuger om tärningarna.** Sidan påstår: "When you roll…
   /api/dice rolls it. The algorithm is server-side Python's secrets…".
   Verkligheten: spelarens kast rullas **client-side** (`rollDice` +
   `Math.random` i chat.html) — `/api/dice` anropas aldrig. Fiende-kast är
   server-side (secrets), spelarkast är inte det. Antingen koppla tillbaka
   `/api/dice` (fusksäkra kast) eller korrigera kopian.

### P1 — viktig 5e-mekanik som saknas

4. **Class features vid level-up.** Level-up ger XP + HP men inga klassförmåner
   (Action Surge, Cunning Action, Extra Attack, Spellcasting-tak…). Inget
   `features`-fält i state-schemat (endast `traits`). Guardian kan skriva via
   `character_updates` men ostrukturerat.
5. **Inspiration (5e meta-valuta).** Bardic Inspiration som die-resurs finns,
   men 5e:s Inspiration (DM belönar → spelaren spenderar för advantage på ett
   kast) saknas helt — varken state, prompt eller UI.
6. **Conditions tickar inte i strid.** STATUS-tabellen (poison/burn/bleed…)
   finns i combat.py men `advance_turn`/`_tick_all_statuses`/`tick_statuses`
   anropas inte i tag-combat (endast av tester sedan REST-lagret togs bort).
   När Guardian sätter en status på fiende sker ingen automatisk tick-skada
   eller attack-disadvantage per runda — allt via LLM-narration.

### P2 — fördjupning

7. **Resistans/sårbarhet/immunitet + damage types.** `damage_type` finns som
   data men ingen resistanshantering (fire resistance, bludgeoning immunity…).
8. **Movement/avstånd i strid.** `speed` finns på bladet men inget rörelse- eller
   avståndskoncept (reach, disengage, movement halverad av svår terräng —
   prompt-narrerat).
9. **Encumbrance.** Vikt finns på items men ingen bärkapacitet (STR×15) eller
   encumbrance-koll.
10. **Exhaustion.** Saknas (6 nivåer).
11. **Vision/ljus (darkvision, mörker).** Saknas — bara prompt-disadvantage.
12. **Special-attacker.** Grapple, shove, two-weapon fighting, knock prone —
   fria via narration, inga egna mekanikvägar.
13. **Cover.** Fri AC-justering via DM.
14. **Downtime/crafting/mounts.** Helt fria.

## Rekommenderad ordning

1. P0-1 Skills/proficiency (störst trovärdighetsvinst per insats)
2. P0-2 Spell slot spending (regel som bryts idag)
3. P0-3 mechanics.html "fair dice"-fix (dokumentation vs verklighet)
4. P1-4 Class features vid level-up
5. P1-5 Inspiration
6. P1-6 Conditions tick i tag-combat (koppla `_tick_all_statuses` till
   `combat_round`-applicering)
7. P2 efter behov

## Noteringar

- Arkitekturen är medvetet **LLM-first**: Guardian extraherar mekanik ur
  narration och motorn förstärker ett fåtal hårda regler (fiende-attacker,
  XP, quest, items, vila, death saves). Gaps 1–6 handlar om att lägga till
  hård förstärkning där 5e-regler annars är godtyckliga.
- Testerna (334 st) är säkerhetsnätet — varje ny mekanik-förstärkning bör
  läggas i apply_mechanics med egna tester (mönster: test_combat_allies,
  test_guardian_spell_slots).
