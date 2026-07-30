"""
Guardian — Mörkrets Rikes mekaniska väktare
============================================
Avlastar DM från all mekanisk bokhållning. Två lägen:

  PRE-DM  (guardian_check_roll)
    Körs FÖRE DM-anropet. Analyserar spelarens handling och avgör
    om ett tärningskast krävs. Returnerar i så fall en kast-begäran
    som skickas till spelaren INNAN DM narrerar utfallet.

  POST-DM (guardian_extract_mechanics)
    Körs i BAKGRUND efter DM-svaret. Extraherar ALLA mekaniska
    effekter ur narrationen: skada, läkning, XP, föremål, valuta,
    quests, NPC-ändringar, tid, vila, platser, loggbok.

Designprinciper:
  - DM skriver INGA mekaniska taggar — Guardian äger mekaniken.
  - Guardian är den enda auktoriteten för state-ändringar.
  - Pre-DM måste vara snabb (<2s) — StepFun + reasoning_effort=high (debiterar per prompt).
  - Post-DM kör i bakgrunden — latens spelar ingen roll.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Callable, Coroutine

logger = logging.getLogger("morkrets.guardian")

ModelCallFn = Callable[[list[dict]], Coroutine[None, None, str]]

# ═══════════════════════════════════════
# 1. PRE-DM: KAST-DETEKTION
# ═══════════════════════════════════════

GUARDIAN_PRE_SYSTEM = """\
Du är en mekanisk väktare för ett D&D 5e-rollspel.
Din ENDA uppgift: avgör om spelarens handling kräver ett tärningskast.

## Regler
1. KRÄV kast vid: attack, smygning, klättring, hopp, övertalning under press, \
sökande efter dolda ting, undvika fälla, balans på osäker yta, \
magisk handling med osäker utgång, inbrott, pickpocket, flykt.
2. KRÄV INTE kast vid: vanlig gång, normalt samtal, plocka upp saker, \
läsa, öppna olåst dörr, köpa/sälja, vila, äta, dricka, titta, lyssna, \
gå en väg, beskriva vad man gör (utan risk), prata med NPCs (utan press).
3. Vid tvekan: KRÄV INTE kast. Bara faktiska risker med meningsfulla konsekvenser \
rättfärdigar ett slag. Om handlingen är rutin eller redan besluten → inget kast.
4. Ange ALLTID korrekt tärningsnotation med modifierare och DC.
5. Använd spelarens faktiska modifierare (nedan).
6. Returnera ENDAST ett JSON-objekt.

## Kontext — Viktigt!
Du får se vad DM (Dungeon Master) nyss berättade. Använd detta för att förstå \
situationen. Om DM beskriver en strid och spelaren attackerar → kast krävs. \
Om DM beskriver en värdshusscen och spelaren beställer dryck → inget kast. \
Om DM inte har nämnt något om risker och spelarens handling är rutin → inget kast.

## Format — kast krävs
{"needs_roll": true, "notation": "1d20+2", "label": "SMIDIGHET (DC 14)", "skill": "DEX"}

## Format — inget kast
{"needs_roll": false}

## Exempel
DM: "Du står i värdshuset. Borget, värdshusvärden, torkar en mugg och nickar åt dig."
Spelare: "Jag går fram till bardisken och beställer en öl"
→ {"needs_roll": false}

DM: "Tre goblins har omringat dig i skogen. De har knöliga dolkar och väser."
Spelare: "Jag hugger närmaste goblin med mitt svärd"
→ {"needs_roll": true, "notation": "1d20-1", "label": "ATTACK mot AC 13", "skill": "STR"}

DM: "En tung järnport blockerar gången. Det finns inget synligt lås."
Spelare: "Jag letar efter en dold mekanism eller knapp"
→ {"needs_roll": true, "notation": "1d20+2", "label": "VARSEBLIVNING (DC 15)", "skill": "WIS"}

DM: "Du vandrar längs en lugn landsväg. Solen står högt."
Spelare: "Jag går vidare längs vägen"
→ {"needs_roll": false}

Spelare: "Jag försöker övertala vakten att släppa in mig"
→ {"needs_roll": true, "notation": "1d20+2", "label": "ÖVERTALNING (DC 15)", "skill": "CHA"}
"""

GUARDIAN_PRE_SYSTEM_EN = """\
You are a mechanical guardian for a D&D 5e RPG.
Your ONLY task: determine whether the player's action requires a dice roll.

## Rules
1. REQUIRE a roll for: attack, stealth, climbing, jumping, persuasion under pressure, \
searching for hidden things, avoiding a trap, balance on uncertain surface, \
magical action with uncertain outcome, burglary, pickpocket, escape.
2. DO NOT require a roll for: normal walking, casual conversation, picking up items, \
reading, opening an unlocked door, buying/selling, resting, eating, drinking, \
looking, listening, walking a path, describing actions (without risk), talking to NPCs (without pressure).
3. When in doubt: DO NOT require a roll. Only actual risks with meaningful consequences \
justify a roll. If the action is routine or already decided → no roll.
4. ALWAYS provide correct dice notation with modifiers and DC.
5. Use the player's actual modifiers (below).
6. Return ONLY a JSON object.

## Context — Important!
You will see what the DM (Dungeon Master) just narrated. Use this to understand \
the situation. If the DM describes combat and the player attacks → roll required. \
If the DM describes a tavern scene and the player orders a drink → no roll. \
If the DM hasn't mentioned any risks and the player's action is routine → no roll.

## Format — roll required
{"needs_roll": true, "notation": "1d20+2", "label": "DEXTERITY (DC 14)", "skill": "DEX"}

## Format — no roll
{"needs_roll": false}

## Examples
DM: "You stand in the tavern. Borget, the innkeeper, wipes a mug and nods at you."
Player: "I walk up to the bar and order an ale"
→ {"needs_roll": false}

DM: "Three goblins have surrounded you in the forest. They wield crude daggers and hiss."
Player: "I slash the nearest goblin with my sword"
→ {"needs_roll": true, "notation": "1d20-1", "label": "ATTACK vs AC 13", "skill": "STR"}

DM: "A heavy iron gate blocks the passage. There is no visible lock."
Player: "I search for a hidden mechanism or button"
→ {"needs_roll": true, "notation": "1d20+2", "label": "PERCEPTION (DC 15)", "skill": "WIS"}

DM: "You travel along a quiet country road. The sun is high."
Player: "I continue down the road"
→ {"needs_roll": false}

Player: "I try to persuade the guard to let me in"
→ {"needs_roll": true, "notation": "1d20+2", "label": "PERSUASION (DC 15)", "skill": "CHA"}
"""

# Skill names → ability (SV + EN)
_SKILL_MAP = {
    "akrobatik": "DEX", "fingerfärdighet": "DEX", "smygning": "DEX",
    "arcana": "INT", "historia": "INT", "utredning": "INT", "natur": "INT", "religion": "INT",
    "djurhantering": "WIS", "insikt": "WIS", "medicin": "WIS", "varseblivning": "WIS", "överlevnad": "WIS",
    "bedrägeri": "CHA", "intimidation": "CHA", "uppträdande": "CHA", "övertalning": "CHA",
    "athletics": "STR", "attack": "STR",
    # English skill names
    "acrobatics": "DEX", "sleight of hand": "DEX", "stealth": "DEX",
    "history": "INT", "investigation": "INT", "nature": "INT",
    "animal handling": "WIS", "insight": "WIS", "medicine": "WIS", "perception": "WIS", "survival": "WIS",
    "deception": "CHA", "performance": "CHA", "persuasion": "CHA",
}

# Ability abbreviations → localized labels (SV + EN)
_ABIL_LABELS = {
    "STR": "STYRKA", "DEX": "SMIDIGHET", "CON": "KONSTITUTION",
    "INT": "INTELLIGENS", "WIS": "VISDOM", "CHA": "KARISMA",
}

_ABIL_LABELS_EN = {
    "STR": "STRENGTH", "DEX": "DEXTERITY", "CON": "CONSTITUTION",
    "INT": "INTELLIGENCE", "WIS": "WISDOM", "CHA": "CHARISMA",
}


def _format_char_context(state: dict, language: str = "sv") -> str:
    """Build compact character context for Guardian (language-aware)."""
    ch = state.get("character", {})
    abilities = ch.get("abilities", {})
    abil_str = ", ".join(
        f"{k}: {v.get('score', 10)} ({v.get('mod', 0):+d})"
        for k, v in abilities.items()
    )
    prof = ch.get("proficiency", 2)
    level = ch.get("level", 1)
    hp = ch.get("hp", {})
    cls = ch.get("class", "Unknown" if language == "en" else "Okänd")

    if language == "en":
        parts = [
            f"Class: {cls}, Level: {level}, Proficiency: +{prof}",
            f"Abilities: {abil_str}",
            f"HP: {hp.get('current', '?')}/{hp.get('max', '?')}",
        ]
    else:
        parts = [
            f"Klass: {cls}, Nivå: {level}, Proficiency: +{prof}",
            f"Abilities: {abil_str}",
            f"HP: {hp.get('current', '?')}/{hp.get('max', '?')}",
        ]

    # Combat context
    npcs = state.get("npcs", [])
    enemies = [n["name"] for n in npcs if n.get("relation") in ("fiende", "enemy") and n.get("alive", True)]
    if enemies:
        if language == "en":
            parts.append(f"⚔ COMBAT IN PROGRESS — enemies: {', '.join(enemies)}")
        else:
            parts.append(f"⚔ STRID PÅGÅR — fiender: {', '.join(enemies)}")

    # Latest location
    world = state.get("world", {})
    if world.get("current_location"):
        label = "Location" if language == "en" else "Plats"
        parts.append(f"{label}: {world['current_location']}")

    return "\n".join(parts)


async def guardian_check_roll(
    player_msg: str,
    state: dict,
    model_call_fn: ModelCallFn,
    language: str = "sv",
    dm_context: str = "",
) -> dict | None:
    """
    Pre-DM: Does the player's action require a dice roll?

    Args:
        dm_context: Last DM reply (for situational awareness). Empty on first turn.

    Returns:
        dict with {notation, label, skill} if a roll is required, else None.
    """
    # [Resultat:] = player responding to a roll → never a new roll
    if player_msg.startswith("[Resultat:"):
        return None

    # Awakening → never a roll
    if player_msg == "__VAKNA_DM__":
        return None

    char_ctx = _format_char_context(state, language)
    if language == "en":
        system_prompt = GUARDIAN_PRE_SYSTEM_EN
        # Include DM context if available
        context_block = ""
        if dm_context:
            context_block = f"## DM's last narration\n{dm_context[:500]}\n\n"
        user_msg = (
            f"## Character\n{char_ctx}\n\n"
            f"{context_block}"
            f"## Player's action\n{player_msg}\n\n"
            "Does this require a dice roll?"
        )
        default_label = "Dice roll"
    else:
        system_prompt = GUARDIAN_PRE_SYSTEM
        context_block = ""
        if dm_context:
            context_block = f"## DM:s senaste berättelse\n{dm_context[:500]}\n\n"
        user_msg = (
            f"## Karaktär\n{char_ctx}\n\n"
            f"{context_block}"
            f"## Spelarens handling\n{player_msg}\n\n"
            "Kräver detta ett tärningskast?"
        )
        default_label = "Tärningsslag"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg},
    ]

    try:
        raw = await model_call_fn(messages)
    except Exception as e:
        logger.warning("Guardian pre-DM failed: %s", e)
        return None

    # Parse JSON
    result = _parse_json(raw)
    if not result or not result.get("needs_roll"):
        return None

    notation = result.get("notation", "1d20")
    label = result.get("label", default_label)
    skill = result.get("skill", "")

    # Validate notation (must contain 1d20)
    if "1d20" not in notation.lower() and "d20" not in notation.lower():
        notation = "1d20"

    logger.info("🛡️ Guardian pre-DM: roll required → %s (%s)", notation, label)
    return {"notation": notation, "label": label, "skill": skill}


# ═══════════════════════════════════════
# 2. POST-DM: MEKANISK EXTRAKTION
# ═══════════════════════════════════════

GUARDIAN_POST_SYSTEM = """\
Du är den mekaniska väktaren för ett svenskt D&D 5e-rollspel.
Läs DM-svaret, spelarens handling och den senaste konversationshistoriken. \
Extrahera ALLA mekaniska effekter och uppdateringar.

## Vad du ska extrahera

### Strid & Hälsa
- damage: Skada som spelaren eller NPCs tar. Ange target ("player" eller NPC-namn), amount, type.
- healing: Läkning. Ange target och amount.
- death: NPCs som dör i denna scen.

### Progression
- xp: Erfarenhetspoäng spelaren förtjänar (strid, upptäckter, sociala segrar).
- level_up: Sätt true om XP når nästa nivå.

### Föremål & Valuta
- items_add: Föremål spelaren FÅR (tar, hittar, köper, stjäl). Ange name, type, qty.
  Inkludera D&D-stats: damage (t.ex. "1d8 slashing"), damage_dice ("1d8"), damage_type ("slashing"),
  ac_bonus (heltal, t.ex. 14 för kedjerustning), range ("melee", "ranged 30/120"),
  properties (array: ["finesse","light"]), magic_bonus (0-3), charges, max_charges, description, effects.
  Vapen ska ha damage/damage_dice/damage_type. Rustning ska ha ac_bonus. Magiska föremål ska ha charges/effects/magic_bonus.
  Exempel vapen: {"name":"Långsvärd","type":"Vapen","qty":1,"damage":"1d8 slashing","damage_dice":"1d8","damage_type":"slashing","range":"melee","properties":["versatile"],"magic_bonus":0}
  Exempel rustning: {"name":"Kedjerustning","type":"Rustning","qty":1,"ac_bonus":16,"description":"AC 16, stealth disadvantage"}
  Exempel magiskt: {"name":"Eldtrollstav","type":"Magisk","qty":1,"damage":"2d6 fire","damage_dice":"2d6","damage_type":"fire","range":"ranged 120","magic_bonus":1,"charges":5,"max_charges":7,"effects":"Kan avfyra eldbollar"}
- items_remove: Föremål spelaren FÖRLORAR (tappar, ger bort, säljer, förbrukar).
- currency: Valutaändringar. Ange denom (pp/gp/sp/cp) och amount (+ för in, - för ut).

### Uppdrag
- quests_new: Nya uppdrag. Ange name, description, reward.
- quests_completed: Uppdrag som slutförs.
- quests_failed: Uppdrag som misslyckas.

### NPCs (KRITISKT — uppdatera alltid vid förändringar)
- npcs_new: Nya NPCs som introduceras. Ange name, role, relation (allierad/neutral/fiende/okänd).
- npc_relations: Relationsändringar. Ange name och new_relation. \
  DETEKTERA ÄVEN IMPLICITA ändringar: om en NPC hjälper spelaren → allierad. \
  Om en NPC attackerar eller hotar → fiende. Om en NPC avslöjar en hemlighet → uppdatera notes.
- npc_notes: Nya anteckningar om NPCs (personlighet, mål, hemligheter, utseende). \
  DETEKTERA NAMNAVSLÖJANDEN: om en "okänd" NPC får ett namn, eller om en NPC:s \
  identitet/roll avslöjas ("den gamle mannen visar sig vara..."), uppdatera notes.
- npc_name_reveals: Om en NPC:s sanna namn eller identitet avslöjas. \
  Ange old_name (eller "okänd"), new_name, och reveal_text (vad som avslöjades).

### Karaktärsuppdateringar
- character_updates: Om spelarens karaktär lär sig något nytt, upptäcker en förmåga, \
  eller om bakgrundshistorien utvecklas. Ange field (t.ex. "trait", "backstory", "ability") \
  och text (beskrivning av vad som ändrades).

### Värld & Tid
- locations_new: Nya platser som nämns eller upptäcks.
- time_passed: Tid som förflyter. Ange hours och description.
- rest: Om spelaren vilar. Ange kind ("short" eller "long").
- new_day: Om en ny dag börjar. Ange description.

### Tärningsresurser (roll_grants)
- roll_grants: Om DM ger spelaren en mekanisk fördel som innebär ett framtida tärningskast \
  (Bardic Inspiration, Second Wind, Bless, Guidance, Heroism, spell slot-dice, etc.). \
  Ange notation (t.ex. "1d6", "1d8+2"), label (kort namn), och reason (varför). \
  Exempel: DM säger "du får Bardic Inspiration" → {"notation": "1d6", "label": "Bardic Inspiration", "reason": "DM gav inspiration"}. \
  Om DM ger en buff utan tärning (t.ex. "du känner dig starkare") → tom array.

### Loggbok
- logbook: En kort sammanfattning av vad som hände denna tur (max 2 meningar). \
Skriv i dåtid, tredje person. T.ex. "Faelyndra smög förbi vakten och tog sig in i källaren."

### Dagsammanfattning (VID NY DAG)
- day_summary: Fylls I ENDAST när new_day inte är null. Sammanfatta den DAG SOM JUST AVSLUTADES:
  - 3-5 meningar om dagens viktigaste händelser
  - Vilka quests som påbörjades, avslutades eller misslyckades
  - Vilka NPCs som möttes och deras relation till spelaren
  - Stämning/atmosfär (t.ex. "Blodig men hoppfull")
  - Format: {"title": "Dagens titel", "events": "...", "quests": "...", "mood": "..."}

### ASCII-art (stämning)
- ascii_art: En liten ASCII-art (max 10 rader, max 50 tecken bred) som matchar scenens miljö/stämning. \
Använd enkla tecken: /\|_-~^*.+#@. Exempel: träd, berg, eld, vatten, skallar, svärd. \
Sätt null om scenen är ren dialog eller inomhus utan tydlig miljö. \
Generera art varannan tur — inte varje tur.

### Korrigeringar (KRITISKT)
- corrections: Om DM:s narration implikerade att något hände som INTE borde ha hänt, korrigera det här. \
  Exempel: DM skrev "du tar boken" men spelaren bara läste i den → korrigera: {"field": "items_add", "action": "retract", "reason": "Spelaren läste bara i boken, plockade inte upp den"}. \
  Andra exempel: DM gav XP för något spelaren inte gjorde, DM lade till föremål spelaren bara tittade på. \
  Om allt stämmer → tom array. Använd reason för att förklara för spelaren varför.

## Regler
1. Ta ENDAST med effekter som faktiskt sker — inte saker som nämns eller hotas.
2. "Du siktar mot flaskan" → INGET föremål. "Du tar flaskan" → items_add.
3. VIKTIGT — Föremål: lägg ENDAST till i items_add om spelaren FAKTISKT tar, får, köper eller stjäl föremålet i sin ägo. \
   "Du ser en bok" → INGET föremål. "Du läser boken" → INGET föremål (boken stannar). "Du plockar upp boken" → items_add. \
   "Du hittar en nyckel" → bara om spelaren tar den. "Du öppnar asken" → INGET föremäl om spelaren bara tittar i den.
4. Skippa föremål som redan finns i inventory (nedan) om de inte ges/tas igen.
5. XP ska vara rimligt: 50-100 för enkel strid, 200-500 för svår, 25-50 för upptäckt.
6. Returnera ENDAST ett JSON-objekt. Inga förklaringar.
7. NPC-UPPDATERINGAR: Var AGGRESSIV med att uppdatera NPC-kort. Om en NPC nämns \
   i konversationen och du kan härleda ny information (namn, roll, relation, \
   personlighet, mål) → lägg till i npc_notes eller npc_relations. \
   Om en "okänd" NPC avslöjar sitt namn → npc_name_reveals.
8. KARAKTÄRSUPPDATERINGAR: Om spelaren upptäcker en ny förmåga, lär sig en \
   besvärjelse, eller om bakgrundshistorien utvecklas → character_updates.

## Format
{
  "damage": [{"target": "player", "amount": 12, "type": "slashing"}],
  "healing": [],
  "death": [],
  "xp": 0,
  "items_add": [{"name": "...", "type": "Vapen", "qty": 1, "damage": "1d8 slashing", "damage_dice": "1d8", "damage_type": "slashing", "ac_bonus": null, "range": "melee", "properties": ["versatile"], "magic_bonus": 0, "charges": null, "max_charges": null, "description": "", "effects": null}],
  "items_remove": [],
  "currency": [{"denom": "gp", "amount": 15}],
  "quests_new": [],
  "quests_completed": [],
  "quests_failed": [],
  "npcs_new": [{"name": "...", "role": "...", "relation": "neutral"}],
  "npc_relations": [],
  "npc_notes": [{"name": "...", "note": "..."}],
  "npc_name_reveals": [{"old_name": "okänd", "new_name": "...", "reveal_text": "..."}],
  "character_updates": [{"field": "trait", "text": "..."}],
  "locations_new": [],
  "time_passed": null,
  "rest": null,
  "new_day": null,
  "day_summary": null,
  "logbook": "",
  "ascii_art": null,
  "roll_grants": [],
  "corrections": []
}

Tomma fält: tom array [] eller null. Utelämna ALDRIG ett fält.

## Språk / Language
Extraheringen ska fungera oavsett om DM-svaret och spelarens handling är på svenska eller engelska. \
Skriv logbook, npc_notes, quest-beskrivningar, day_summary och ascii_art-instruktioner på samma språk som scenen. \
JSON-fältnamnen (damage, healing, xp, items_add osv.) är kodnivå och ändras ALDRIG — de är inte användarvända.
"""

# Language instruction appended dynamically per call
_LANG_INSTRUCTION_SV = "\n\n[VIKTIGT: Skriv alla användarvända texter (logbook, npc_notes, day_summary, quest-beskrivningar) på SVENSKA.]"
_LANG_INSTRUCTION_EN = "\n\n[IMPORTANT: Write all user-facing text (logbook, npc_notes, day_summary, quest descriptions) in ENGLISH.]"


def _format_state_for_guardian(state: dict, language: str = "sv") -> str:
    """Build compact state summary for Guardian post-DM (language-aware)."""
    ch = state.get("character", {})
    hp = ch.get("hp", {})
    xp = ch.get("xp", {})
    inv = state.get("inventory", [])
    cur = state.get("currency", {})
    npcs = state.get("npcs", [])
    quests = state.get("quests", [])
    world = state.get("world", {})

    parts = []

    # Character
    parts.append(f"HP: {hp.get('current', '?')}/{hp.get('max', '?')}")
    lvl_word = "level" if language == "en" else "nivå"
    parts.append(f"XP: {xp.get('current', 0)}/{xp.get('next_level', '?')} ({lvl_word} {ch.get('level', 1)})")

    # Inventory
    if inv:
        inv_str = ", ".join(f"{it['name']}(×{it.get('qty',1)})" for it in inv[:15])
        parts.append(f"Inventory: {inv_str}")

    # Currency
    if any(cur.get(d, 0) for d in ("pp", "gp", "sp", "cp")):
        cur_label = "Currency" if language == "en" else "Valuta"
        parts.append(f"{cur_label}: {cur.get('pp',0)}pp {cur.get('gp',0)}gp {cur.get('sp',0)}sp {cur.get('cp',0)}cp")

    # NPCs
    if npcs:
        dead_word = "dead" if language == "en" else "död"
        alive_word = "alive" if language == "en" else "levande"
        npc_str = "; ".join(
            f"{n['name']}({n.get('relation','?')}, {dead_word if not n.get('alive', True) else alive_word})"
            for n in npcs[:10]
        )
        parts.append(f"NPCs: {npc_str}")

    # Quests
    active_statuses = ("aktiv", "active")
    active = [q for q in quests if q.get("status") in active_statuses]
    if active:
        q_str = "; ".join(q["name"] for q in active[:5])
        q_label = "Active quests" if language == "en" else "Aktiva uppdrag"
        parts.append(f"{q_label}: {q_str}")

    # World
    if world.get("current_location"):
        loc_label = "Location" if language == "en" else "Plats"
        parts.append(f"{loc_label}: {world['current_location']}")
    if world.get("day"):
        day_label = "Day" if language == "en" else "Dag"
        parts.append(f"{day_label}: {world['day']}")

    return "\n".join(parts)


async def guardian_extract_mechanics(
    dm_reply: str,
    player_msg: str,
    state: dict,
    turn: int,
    model_call_fn: ModelCallFn,
    language: str = "sv",
    conversation_history: list[dict] | None = None,
) -> dict:
    """
    Post-DM: Extract all mechanical effects from the DM reply.

    Args:
        conversation_history: Recent transcript entries (role/content dicts)
            for context-aware extraction (NPC reveals, implicit changes).

    Returns:
        Dict with all fields from the GUARDIAN_POST_SYSTEM format.
        Empty fields if nothing is extracted.
    """
    state_ctx = _format_state_for_guardian(state, language)
    lang_instruction = _LANG_INSTRUCTION_EN if language == "en" else _LANG_INSTRUCTION_SV

    # Bygg konversationskontext (senaste 6 meddelanden)
    history_block = ""
    if conversation_history:
        recent = conversation_history[-6:]
        lines = []
        for entry in recent:
            role = entry.get("role", "?")
            content = entry.get("content", "")[:300]
            if role == "guardian":
                continue  # Hoppa över Guardian-rapporter
            if role == "user":
                lines.append(f"Spelare: {content}" if language == "sv" else f"Player: {content}")
            elif role == "assistant":
                lines.append(f"DM: {content}" if language == "sv" else f"DM: {content}")
        if lines:
            history_label = "## Senaste konversation" if language == "sv" else "## Recent conversation"
            history_block = f"{history_label}\n" + "\n".join(lines) + "\n\n"

    if language == "en":
        user_msg = (
            f"## Current state\n{state_ctx}\n\n"
            f"{history_block}"
            f"## DM reply (turn {turn})\n{dm_reply}\n\n"
            f"## Player's action\n{player_msg}\n\n"
            "Extract all mechanical effects and updates:"
        )
    else:
        user_msg = (
            f"## Nuvarande tillstånd\n{state_ctx}\n\n"
            f"{history_block}"
            f"## DM-svar (tur {turn})\n{dm_reply}\n\n"
            f"## Spelarens handling\n{player_msg}\n\n"
            "Extrahera alla mekaniska effekter och uppdateringar:"
        )

    messages = [
        {"role": "system", "content": GUARDIAN_POST_SYSTEM + lang_instruction},
        {"role": "user", "content": user_msg},
    ]

    empty = {
        "damage": [], "healing": [], "death": [], "xp": 0,
        "items_add": [], "items_remove": [], "currency": [],
        "quests_new": [], "quests_completed": [], "quests_failed": [],
        "npcs_new": [], "npc_relations": [], "npc_notes": [],
        "npc_name_reveals": [], "character_updates": [],
        "locations_new": [], "time_passed": None, "rest": None,
        "new_day": None, "day_summary": None, "logbook": "", "ascii_art": None,
    }

    for attempt in range(2):
        try:
            raw = await model_call_fn(messages)
        except Exception as e:
            logger.warning("Guardian post-DM LLM misslyckades (försök %d): %s", attempt + 1, e)
            if attempt == 0:
                continue
            return empty

        result = _parse_json(raw)
        if result is None:
            logger.warning(
                "Guardian post-DM: ogiltig JSON (försök %d). Rådata: %.200s",
                attempt + 1, raw,
            )
            if attempt == 0:
                messages.append({"role": "assistant", "content": raw})
                messages.append({
                    "role": "user",
                    "content": "Ogiltig JSON. Returnera ENDAST JSON-objektet, inget annat.",
                })
                continue
            return empty

        # Normalisera: säkerställ att alla fält finns
        for key, default in empty.items():
            if key not in result:
                result[key] = default

        # Validera och sanera
        result = _sanitize_mechanics(result)

        n_changes = sum(
            len(result.get(k, [])) for k in
            ("damage", "healing", "death", "items_add", "items_remove",
             "currency", "quests_new", "quests_completed", "quests_failed",
             "npcs_new", "npc_relations", "npc_notes", "locations_new")
        ) + (1 if result.get("xp") else 0) + (1 if result.get("rest") else 0)

        logger.info(
            "🛡️ Guardian post-DM (tur %d): %d mekaniska ändringar (försök %d)",
            turn, n_changes, attempt + 1,
        )
        return result

    return empty


# ═══════════════════════════════════════
# 3. APPLICERA ÄNDRINGAR TILL STATE
# ═══════════════════════════════════════

# XP-trösklar (D&D 5e)
_XP_THRESHOLDS = [0, 300, 900, 2700, 6500, 14000, 23000, 34000, 48000, 64000,
                  85000, 100000, 120000, 140000, 165000, 195000, 225000, 265000,
                  305000, 355000]


def apply_mechanics(state: dict, mech: dict) -> list[dict]:
    """
    Applicera Guardian-extraherade mekaniska ändringar på state.

    Returns:
        Lista av effect-dicts (för frontend-visuella effekter).
    """
    effects: list[dict] = []
    ch = state.setdefault("character", {})

    # ── Skada ──
    for dmg in mech.get("damage", []):
        target = dmg.get("target", "player")
        amount = max(0, int(dmg.get("amount", 0)))
        if amount <= 0:
            continue
        if target == "player":
            hp = ch.setdefault("hp", {"current": 1, "max": 1, "temp": 0})
            # Temp HP absorberar först
            temp = hp.get("temp", 0)
            if temp > 0:
                absorbed = min(temp, amount)
                hp["temp"] = temp - absorbed
                amount -= absorbed
            hp["current"] = max(0, hp.get("current", 1) - amount)
            effects.append({"type": "skada", "value": dmg.get("amount", 0)})
            logger.info("🛡️ Guardian: %d skada → HP %d/%d", dmg.get("amount", 0), hp["current"], hp["max"])
        else:
            # NPC-skada — uppdatera NPC-anteckningar
            _add_npc_note(state, target, f"Tog {amount} skada ({dmg.get('type', 'okänd')})")

    # ── Läkning ──
    for heal in mech.get("healing", []):
        target = heal.get("target", "player")
        amount = max(0, int(heal.get("amount", 0)))
        if amount <= 0:
            continue
        if target == "player":
            hp = ch.setdefault("hp", {"current": 1, "max": 1, "temp": 0})
            hp["current"] = min(hp.get("max", 1), hp.get("current", 0) + amount)
            effects.append({"type": "hela", "value": amount})
            logger.info("🛡️ Guardian: %d läkning → HP %d/%d", amount, hp["current"], hp["max"])

    # ── Död ──
    for name in mech.get("death", []):
        for npc in state.get("npcs", []):
            if npc.get("name", "").lower() == name.lower():
                npc["alive"] = False
                effects.append({"type": "npc_död", "value": name})
                logger.info("🛡️ Guardian: NPC '%s' dog", name)
                break

    # ── XP ──
    xp_gain = max(0, int(mech.get("xp", 0)))
    if xp_gain > 0:
        xp = ch.setdefault("xp", {"current": 0, "next_level": 900})
        xp["current"] = xp.get("current", 0) + xp_gain
        effects.append({"type": "xp", "value": xp_gain})
        logger.info("🛡️ Guardian: +%d XP → %d", xp_gain, xp["current"])

        # Level-up check
        level = ch.get("level", 1)
        if level < len(_XP_THRESHOLDS) and xp["current"] >= _XP_THRESHOLDS[level]:
            ch["level"] = level + 1
            xp["next_level"] = _XP_THRESHOLDS[level + 1] if level + 1 < len(_XP_THRESHOLDS) else None
            # Max HP ökar
            hp = ch.setdefault("hp", {"current": 1, "max": 1, "temp": 0})
            con_mod = ch.get("abilities", {}).get("CON", {}).get("mod", 0)
            hp_gain = max(1, 5 + con_mod)  # Enkel HD-baserad ökning
            hp["max"] = hp.get("max", 1) + hp_gain
            hp["current"] = hp["max"]  # Full HP vid level-up
            effects.append({"type": "level_up", "value": ch["level"]})
            logger.info("🛡️ Guardian: LEVEL UP → nivå %d! HP max %d", ch["level"], hp["max"])

    # ── Föremål ──
    inv = state.setdefault("inventory", [])
    for item in mech.get("items_add", []):
        name = item.get("name", "").strip()
        if not name:
            continue
        qty = max(1, int(item.get("qty", 1)))
        existing = next((it for it in inv if it["name"].lower() == name.lower()), None)
        if existing:
            existing["qty"] = existing.get("qty", 1) + qty
            logger.info("🛡️ Guardian dedup: '%s' → qty=%d", name, existing["qty"])
        else:
            inv.append({
                "id": f"guardian-{len(inv)}",
                "name": name,
                "type": item.get("type", "Annat"),
                "qty": qty,
                "weight": 0,
                "equipped": False,
                "rarity": item.get("rarity", "normal"),
                "description": item.get("description", ""),
                "damage": item.get("damage", None),
                "damage_dice": item.get("damage_dice", None),
                "damage_type": item.get("damage_type", None),
                "ac_bonus": item.get("ac_bonus", None),
                "range": item.get("range", None),
                "properties": item.get("properties", []),
                "magic_bonus": int(item.get("magic_bonus", 0)),
                "charges": item.get("charges", None),
                "max_charges": item.get("max_charges", None),
                "effects": item.get("effects", None),
            })
            logger.info("🛡️ Guardian: lade till '%s'", name)
        effects.append({"type": "föremål", "value": name, "qty": qty})

    for item in mech.get("items_remove", []):
        name = item.get("name", "").strip()
        qty = max(1, int(item.get("qty", 1)))
        if not name:
            continue
        existing = next((it for it in inv if it["name"].lower() == name.lower()), None)
        if existing:
            existing["qty"] = existing.get("qty", 1) - qty
            if existing["qty"] <= 0:
                inv.remove(existing)
                logger.info("🛡️ Guardian: tog bort '%s'", name)
            else:
                logger.info("🛡️ Guardian: minskade '%s' → qty=%d", name, existing["qty"])
            effects.append({"type": "föremål_bort", "value": name, "qty": qty})

    # ── Valuta ──
    cur = state.setdefault("currency", {"pp": 0, "gp": 0, "sp": 0, "cp": 0})
    for c in mech.get("currency", []):
        denom = c.get("denom", "gp").lower()
        amount = int(c.get("amount", 0))
        if denom in cur:
            cur[denom] = max(0, cur.get(denom, 0) + amount)
            effects.append({"type": "guld", "value": amount, "denom": denom})
            logger.info("🛡️ Guardian: %+d %s → %d", amount, denom, cur[denom])

    # ── Quests ──
    quests = state.setdefault("quests", [])
    for q in mech.get("quests_new", []):
        name = q.get("name", "").strip()
        if not name:
            continue
        if not any(qq.get("name", "").lower() == name.lower() for qq in quests):
            quests.append({
                "name": name,
                "description": q.get("description", ""),
                "reward": q.get("reward", ""),
                "status": "aktiv",
            })
            effects.append({"type": "quest", "value": name})
            logger.info("🛡️ Guardian: nytt uppdrag '%s'", name)

    for name in mech.get("quests_completed", []):
        for q in quests:
            if q.get("name", "").lower() == name.lower() and q.get("status") == "aktiv":
                q["status"] = "slutförd"
                effects.append({"type": "quest_slutförd", "value": name})
                logger.info("🛡️ Guardian: uppdrag slutfört '%s'", name)
                break

    for name in mech.get("quests_failed", []):
        for q in quests:
            if q.get("name", "").lower() == name.lower() and q.get("status") == "aktiv":
                q["status"] = "misslyckad"
                effects.append({"type": "quest_misslyckad", "value": name})
                logger.info("🛡️ Guardian: uppdrag misslyckat '%s'", name)
                break

    # ── NPCs ──
    npcs = state.setdefault("npcs", [])
    for npc in mech.get("npcs_new", []):
        name = npc.get("name", "").strip()
        if not name:
            continue
        if not any(n.get("name", "").lower() == name.lower() for n in npcs):
            relation = npc.get("relation", "okänd")
            if relation not in ("allierad", "neutral", "fiende", "okänd"):
                relation = "okänd"
            h = int.from_bytes(name.encode("utf-8"), "big")
            _colors = ['#8b5fd4', '#d4691e', '#7aa35e', '#5e9aa3', '#d43a4d', '#c9a227', '#a8b2c0', '#b06fd4']
            _icons = ['🧙', '⚔️', '🏹', '🛡️', '🎭', '👻', '🐺', '🦉', '💀', '🔮', '🗡️', '🌙']
            npcs.append({
                "name": name,
                "role": npc.get("role", "Okänd"),
                "relation": relation,
                "color": _colors[h % len(_colors)],
                "icon": _icons[h % len(_icons)],
                "notes": "",
                "alive": True,
            })
            effects.append({"type": "npc_new", "value": name, "role": npc.get("role", "Okänd"), "relation": relation})
            logger.info("🛡️ Guardian: ny NPC '%s' (%s)", name, relation)

    for rel in mech.get("npc_relations", []):
        name = rel.get("name", "").strip()
        new_rel = rel.get("new_relation", "").strip().lower()
        if not name or new_rel not in ("allierad", "neutral", "fiende", "okänd"):
            continue
        for npc in npcs:
            if npc.get("name", "").lower() == name.lower():
                old = npc.get("relation", "?")
                npc["relation"] = new_rel
                effects.append({"type": "npc_relation", "value": f"{name} → {new_rel}"})
                logger.info("🛡️ Guardian: NPC '%s' relation %s → %s", name, old, new_rel)
                break

    for note in mech.get("npc_notes", []):
        name = note.get("name", "").strip()
        text = note.get("note", "").strip()
        if name and text:
            _add_npc_note(state, name, text)
            effects.append({"type": "npc_note", "value": name, "note": text})

    # ── NPC-namn avslöjanden ──
    for reveal in mech.get("npc_name_reveals", []):
        old_name = reveal.get("old_name", "").strip()
        new_name = reveal.get("new_name", "").strip()
        reveal_text = reveal.get("reveal_text", "").strip()
        if not new_name:
            continue
        # Hitta NPC med gammalt namn (eller "okänd") och uppdatera
        for npc in npcs:
            if npc.get("name", "").lower() == old_name.lower() or (old_name.lower() in ("okänd", "unknown") and not npc.get("name")):
                npc["name"] = new_name
                if reveal_text:
                    _add_npc_note(state, new_name, f"Identitet avslöjad: {reveal_text}")
                effects.append({"type": "npc_reveal", "value": new_name, "old_name": old_name, "reveal_text": reveal_text})
                logger.info("🛡️ Guardian: NPC-namn avslöjat '%s' → '%s'", old_name, new_name)
                break
        else:
            # NPC hittades inte — skapa ny med avslöjat namn
            h = int.from_bytes(new_name.encode("utf-8"), "big")
            _colors = ['#8b5fd4', '#d4691e', '#7aa35e', '#5e9aa3', '#d43a4d', '#c9a227', '#a8b2c0', '#b06fd4']
            _icons = ['🧙', '⚔️', '🏹', '🛡️', '🎭', '👻', '🐺', '🦉', '💀', '🔮', '🗡️', '🌙']
            npcs.append({
                "name": new_name,
                "role": "Okänd",
                "relation": "okänd",
                "color": _colors[h % len(_colors)],
                "icon": _icons[h % len(_icons)],
                "notes": f"• Identitet avslöjad: {reveal_text}" if reveal_text else "",
                "alive": True,
            })
            effects.append({"type": "npc_reveal", "value": new_name, "old_name": old_name, "reveal_text": reveal_text})
            logger.info("🛡️ Guardian: ny NPC via avslöjande '%s'", new_name)

    # ── Karaktärsuppdateringar ──
    ch = state.setdefault("character", {})
    for upd in mech.get("character_updates", []):
        field = upd.get("field", "").strip()
        text = upd.get("text", "").strip()
        if not field or not text:
            continue
        # Spara i character.updates (append-only logg)
        updates = ch.setdefault("updates", [])
        updates.append({"field": field, "text": text, "turn": state.get("meta", {}).get("turn_count", 0)})
        effects.append({"type": "character_update", "value": field, "text": text})
        logger.info("🛡️ Guardian: karaktärsuppdatering '%s': %s", field, text[:60])

    # ── Platser ──
    world = state.setdefault("world", {})
    for loc in mech.get("locations_new", []):
        name = loc.strip() if isinstance(loc, str) else ""
        if not name:
            continue
        visited = world.setdefault("visited_locations", [])
        if not any(
            (v.get("name", "") if isinstance(v, dict) else str(v)).lower() == name.lower()
            for v in visited
        ):
            visited.append({"name": name, "turn": state.get("meta", {}).get("turn_count", 0)})
            effects.append({"type": "plats", "value": name})
            logger.info("🛡️ Guardian: ny plats '%s'", name)

    # ── Tid ──
    tp = mech.get("time_passed")
    if tp and isinstance(tp, dict):
        hours = int(tp.get("hours", 0))
        desc = tp.get("description", "")
        if hours > 0:
            world["time"] = desc or world.get("time", "")
            effects.append({"type": "tid", "value": desc or f"{hours}h"})
            logger.info("🛡️ Guardian: %dh förflyter — %s", hours, desc)

    # ── Vila ──
    rest = mech.get("rest")
    if rest and isinstance(rest, dict):
        kind = rest.get("kind", "short")
        hp = ch.setdefault("hp", {"current": 1, "max": 1, "temp": 0})
        if kind == "long":
            hp["current"] = hp.get("max", 1)
            hp["temp"] = 0
            # Spell slots
            ss = ch.setdefault("spell_slots", {"current": 0, "max": 0})
            ss["current"] = ss.get("max", 0)
            logger.info("🛡️ Guardian: LÅNG VILA → full HP + spell slots")
        else:
            # Kort vila: ~30% HP
            heal = max(1, hp.get("max", 1) // 3)
            hp["current"] = min(hp.get("max", 1), hp.get("current", 0) + heal)
            logger.info("🛡️ Guardian: KORT VILA → +%d HP", heal)
        effects.append({"type": "hela", "value": hp.get("current", 0)})

    # ── Ny dag ──
    nd = mech.get("new_day")
    if nd and isinstance(nd, dict):
        desc = nd.get("description", "En ny dag gryr")
        prev_day = world.get("day", 1)
        world["day"] = prev_day + 1
        world["day_description"] = desc
        world.setdefault("day_log", []).append({"day": world["day"], "description": desc})

        # Dagsammanfattning av den avslutade dagen
        ds = mech.get("day_summary")
        if ds and isinstance(ds, dict):
            world.setdefault("day_summaries", []).append({
                "day": prev_day,
                "title": ds.get("title", f"Dag {prev_day}"),
                "events": ds.get("events", ""),
                "quests": ds.get("quests", ""),
                "mood": ds.get("mood", ""),
            })
            logger.info("🛡️ Guardian dagsammanfattning Dag %d: %s", prev_day, ds.get("title", ""))

        effects.append({"type": "ny_dag", "value": f"Dag {world['day']}: {desc}"})
        logger.info("🛡️ Guardian: NY DAG %d — %s", world["day"], desc)

    # ── Loggbok ──
    logbook = mech.get("logbook", "")
    if logbook:
        world.setdefault("logbook", []).append({
            "day": world.get("day", 1),
            "turn": state.get("meta", {}).get("turn_count", 0),
            "text": logbook,
        })
        logger.info("🛡️ Guardian loggbok: %s", logbook[:80])

    # ── Tärningsresurser (roll_grants) ──
    for grant in mech.get("roll_grants", []):
        notation = grant.get("notation", "").strip()
        label = grant.get("label", "").strip()
        if not notation:
            continue
        # Spara i state så karaktärsbladet kan visa aktiva resurser
        resources = state.setdefault("resources", [])
        resources.append({
            "notation": notation,
            "label": label or notation,
            "reason": grant.get("reason", ""),
            "turn": state.get("meta", {}).get("turn_count", 0),
        })
        effects.append({"type": "roll_grant", "value": label or notation, "notation": notation})
        logger.info("🛡️ Guardian: roll_grant %s (%s)", notation, label)

    # ── Korrigeringar ──
    for corr in mech.get("corrections", []):
        field = corr.get("field", "")
        action = corr.get("action", "")
        reason = corr.get("reason", "")
        if action == "retract" and field == "items_add":
            # Ta bort senast tillagt föremål om det var ett misstag
            inv = state.get("inventory", [])
            if inv:
                removed = inv.pop()
                effects.append({"type": "korrigering", "value": f"Föremål återkallat: {removed.get('name', '?')}", "reason": reason})
                logger.info("🛡️ Guardian korrigering: återkallade '%s' — %s", removed.get("name", "?"), reason[:80])
        elif reason:
            effects.append({"type": "korrigering", "value": reason, "reason": reason})
            logger.info("🛡️ Guardian korrigering: %s — %s", field, reason[:80])

    return effects


# ═══════════════════════════════════════
# HJÄLPARE
# ═══════════════════════════════════════

def _add_npc_note(state: dict, name: str, note: str) -> None:
    """Lägg till en anteckning på en NPC."""
    for npc in state.get("npcs", []):
        if npc.get("name", "").lower() == name.lower():
            existing = npc.get("notes", "")
            npc["notes"] = f"{existing}\n• {note}".strip() if existing else f"• {note}"
            logger.debug("🛡️ Guardian NPC-not: '%s' → %s", name, note[:60])
            return
    logger.debug("🛡️ Guardian: NPC '%s' hittades inte för not", name)


def _parse_json(raw: str) -> dict | None:
    """Parsa JSON-objekt ur LLM-svar. Hanterar markdown och text runt JSON."""
    # Strip markdown code fences
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)

    # Direkt
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    # Hitta { ... }
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end > start:
        try:
            data = json.loads(cleaned[start:end + 1])
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    return None


def _sanitize_mechanics(mech: dict) -> dict:
    """Sanera och validera mekaniska data."""
    # Säkerställ att listor är listor
    for key in ("damage", "healing", "death", "items_add", "items_remove",
                "currency", "quests_new", "quests_completed", "quests_failed",
                "npcs_new", "npc_relations", "npc_notes", "locations_new"):
        if not isinstance(mech.get(key), list):
            mech[key] = []

    # XP ska vara int
    try:
        mech["xp"] = max(0, int(mech.get("xp", 0)))
    except (ValueError, TypeError):
        mech["xp"] = 0

    # Loggbok ska vara str
    if not isinstance(mech.get("logbook"), str):
        mech["logbook"] = ""

    # ASCII-art: ska vara str eller null
    art = mech.get("ascii_art")
    if art and isinstance(art, str):
        # Grundläggande sanering: max 14 rader, max 60 tecken breda
        lines = art.strip().split('\n')
        cleaned = [l for l in lines if len(l) <= 60][:14]
        mech["ascii_art"] = '\n'.join(cleaned) if len(cleaned) >= 3 else None
    else:
        mech["ascii_art"] = None

    # day_summary: ska vara dict eller null
    ds = mech.get("day_summary")
    if ds and not isinstance(ds, dict):
        mech["day_summary"] = None

    return mech


# ═══════════════════════════════════════
# 4. FORMATERING — läsbar Guardian-rapport
# ═══════════════════════════════════════

def format_guardian_summary(
    effects: list[dict],
    state: dict,
    language: str = "sv",
    mech: dict | None = None,
    dm_npcs: list[dict] | None = None,
    turn: int = 0,
) -> str:
    """
    Format ALL Guardian actions as a detailed timeline for the chat.
    Includes: effects, DM-tag NPCs, logbook, time, rest, day changes.
    Returns empty string only if truly nothing happened.
    """
    en = language == "en"
    lines: list[str] = []
    ch = state.get("character", {})
    hp = ch.get("hp", {})
    mech = mech or {}

    # ── DM-taggar: NPCs som DM introducerade direkt ──
    for npc in (dm_npcs or []):
        name = npc.get("name", "?")
        role = npc.get("role", "")
        relation = npc.get("relation", "")
        detail = f" ({role})" if role else ""
        if relation:
            detail += f" · {relation}"
        if en:
            lines.append(f"🧙 **New character:** {name}{detail}")
        else:
            lines.append(f"🧙 **Ny gestalt:** {name}{detail}")

    # ── Mekaniska effekter (från apply_mechanics) ──
    for e in effects:
        t = e.get("type", "")
        v = e.get("value", "")

        if t == "skada":
            if en:
                lines.append(f"💔 **{v} damage** → HP {hp.get('current', '?')}/{hp.get('max', '?')}")
            else:
                lines.append(f"💔 **{v} skada** → HP {hp.get('current', '?')}/{hp.get('max', '?')}")
        elif t == "hela":
            label = "Healing" if en else "Läkning"
            lines.append(f"💚 **{label}** → HP {hp.get('current', '?')}/{hp.get('max', '?')}")
        elif t == "xp":
            xp = ch.get("xp", {})
            lines.append(f"⭐ **+{v} XP** ({xp.get('current', 0)}/{xp.get('next_level', '?')})")
        elif t == "level_up":
            if en:
                lines.append(f"🎉 **LEVEL UP → {v}!**")
            else:
                lines.append(f"🎉 **NIVÅ UPP → {v}!**")
        elif t == "föremål":
            qty = e.get("qty", 1)
            qty_str = f" ×{qty}" if qty > 1 else ""
            label = "New item:" if en else "Nytt föremål:"
            lines.append(f"📦 **{label}** {v}{qty_str}")
        elif t == "föremål_bort":
            qty = e.get("qty", 1)
            qty_str = f" ×{qty}" if qty > 1 else ""
            label = "Item removed:" if en else "Föremål bort:"
            lines.append(f"🗑️ **{label}** {v}{qty_str}")
        elif t == "guld":
            denom = e.get("denom", "gp")
            sign = "+" if int(v) >= 0 else ""
            lines.append(f"🪙 **{sign}{v} {denom}**")
        elif t == "quest":
            label = "New quest:" if en else "Nytt uppdrag:"
            lines.append(f"📜 **{label}** {v}")
        elif t == "quest_slutförd":
            label = "Quest completed:" if en else "Uppdrag slutfört:"
            lines.append(f"✅ **{label}** {v}")
        elif t == "quest_misslyckad":
            label = "Quest failed:" if en else "Uppdrag misslyckat:"
            lines.append(f"❌ **{label}** {v}")
        elif t == "npc_död":
            if en:
                lines.append(f"💀 **{v} has fallen.**")
            else:
                lines.append(f"💀 **{v} har fallit.**")
        elif t == "npc_relation":
            lines.append(f"🤝 **{v}**")
        elif t == "npc_new":
            role = e.get("role", "?")
            relation = e.get("relation", "?")
            if en:
                lines.append(f"🧙 **New character:** {v} ({role}, {relation})")
            else:
                lines.append(f"🧙 **Ny gestalt:** {v} ({role}, {relation})")
        elif t == "npc_note":
            note = e.get("note", "")
            if en:
                lines.append(f"📝 **About {v}:** {note}")
            else:
                lines.append(f"📝 **Om {v}:** {note}")
        elif t == "npc_reveal":
            old = e.get("old_name", "?")
            reveal_text = e.get("reveal_text", "")
            if en:
                lines.append(f"🎭 **Identity revealed:** {old} → **{v}**")
            else:
                lines.append(f"🎭 **Identitet avslöjad:** {old} → **{v}**")
            if reveal_text:
                lines.append(f"  *{reveal_text}*")
        elif t == "character_update":
            text = e.get("text", "")
            if en:
                lines.append(f"📖 **Character update ({v}):** {text}")
            else:
                lines.append(f"📖 **Karaktärsuppdatering ({v}):** {text}")
        elif t == "plats":
            label = "New location:" if en else "Ny plats:"
            lines.append(f"🗺️ **{label}** {v}")
        elif t == "tid":
            label = "Time:" if en else "Tid:"
            lines.append(f"🕐 **{label}** {v}")
        elif t == "ny_dag":
            lines.append(f"🌅 **{v}**")
            # Show day summary of the completed day
            world = state.get("world", {})
            summaries = world.get("day_summaries", [])
            if summaries:
                ds = summaries[-1]
                summary_label = "Summary" if en else "Sammanfattning"
                lines.append(f"📖 **{summary_label} — {ds.get('title', '')}**")
                if ds.get("events"):
                    lines.append(f"  {ds['events']}")
                if ds.get("quests"):
                    lines.append(f"  📜 {ds['quests']}")
                if ds.get("mood"):
                    lines.append(f"  🎭 *{ds['mood']}*")
        elif t == "roll_grant":
            notation = e.get("notation", "")
            label = "Dice granted:" if en else "Tärning tilldelad:"
            lines.append(f"🎲 **{label}** {v} ({notation})")
        elif t == "korrigering":
            label = "Correction:" if en else "Korrigering:"
            reason = e.get("reason", "")
            lines.append(f"🔧 **{label}** {v}")

    # ── Icke-effekt-data från mech (loggbok, tid, vila) ──
    logbook = mech.get("logbook", "")
    if logbook and not any("📖" in l for l in lines):
        lb_label = "Journal" if en else "Loggbok"
        lines.append(f"📖 **{lb_label}:** {logbook}")

    time_passed = mech.get("time_passed")
    if time_passed and not any("🕐" in l for l in lines):
        tp_label = "Time passes" if en else "Tid förflyter"
        lines.append(f"🕐 **{tp_label}:** {time_passed}")

    rest = mech.get("rest")
    if rest:
        if rest == "long":
            lines.append("🏕️ **Lång vila** — HP återställd" if not en else "🏕️ **Long rest** — HP restored")
        elif rest == "short":
            lines.append("⛺ **Kort vila**" if not en else "⛺ **Short rest**")

    if not lines:
        return ""

    turn_label = f" · {('Turn' if en else 'Tur')} {turn}" if turn else ""
    header = "🛡️ **Guardian**" + turn_label

    # ── Maskinläsbara taggar för frontend (parsas och tas bort ur visningen) ──
    tags = []
    for e in effects:
        if e.get("type") == "roll_grant":
            notation = e.get("notation", "")
            label = e.get("value", "")
            if notation:
                tags.append(f"[ROLL_GRANT:{notation}|{label}]")

    return header + "\n" + "\n".join(lines) + ("\n" + "".join(tags) if tags else "")
